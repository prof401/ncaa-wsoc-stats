"""CLI and orchestration for NCAA WSOC scraper."""

import argparse
import csv
import sys
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .contest import extract_scoring_summary, fetch_box_score_page
from .discovery import DiscoveryManager
from .http import ConsecutiveHttpFailures, create_session
from .rankings import build_rankings_url, get_team_seed_entries_for_season
from .storage import (
    SCORING_SUMMARY_DEFAULT,
    SKIPPED_CONTESTS_DEFAULT,
    append_contest,
    append_scoring_rows,
    append_skipped_contest_id,
    append_team,
    load_known_team_ids,
    load_scraped_contest_ids,
    load_skipped_contest_ids,
    remove_skipped_contest_id,
)
from .team import extract_contests, extract_team_metadata, fetch_team_page

_GOAL_FIELDS = [
    "period",
    "clock",
    "scoring_team_id",
    "play_text",
    "away_score_after",
    "home_score_after",
]


def run(
    season: int = 2024,
    division: int = 3,
    dry_run: bool = False,
    output_dir: Path | str | None = None,
    delay_seconds: float = 1.0,
    limit: int | None = None,
) -> None:
    """
    Run the full scrape: seed -> team pages -> discovery -> CSV output.

    Args:
        season: Calendar year (e.g., 2024 for 2024-25).
        division: NCAA division (1, 2, or 3).
        dry_run: If True, only print URL and exit.
        output_dir: Directory for teams.csv and contests.csv. Defaults to cwd.
        delay_seconds: Delay between requests.
        limit: Max teams to process (for testing). None = no limit.
    """
    out = Path(output_dir or ".")
    teams_path = out / "teams.csv"
    contests_path = out / "contests_raw.csv"

    url = build_rankings_url(season, division)
    print(f"Rankings URL: {url}")

    if dry_run:
        return

    print(f"Fetching D{division} rankings for {season} season...")
    session = create_session()
    seed_entries = get_team_seed_entries_for_season(season, division, session=session)
    print(f"Seed: {len(seed_entries)} team IDs")

    known = load_known_team_ids(teams_path)
    discovery = DiscoveryManager(known_ids=known)
    discovery.add_seed_ids(seed_entries)
    print(f"Queue: {len(discovery)} teams to process (known: {len(known)})")

    processed = 0
    while not discovery.is_empty() and (limit is None or processed < limit):
        popped = discovery.pop_next()
        if not popped:
            break
        team_id, name_hint = popped

        time.sleep(delay_seconds)
        try:
            html = fetch_team_page(session, team_id)
        except requests.RequestException as e:
            print(f"  Error fetching team {team_id}: {e}")
            continue
        if html is None:
            continue

        soup = BeautifulSoup(html, "html.parser")

        if not (name_hint or "").strip():
            print(
                f"  Team {team_id}: no name hint; using page extraction for name."
            )

        # Metadata
        meta = extract_team_metadata(
            soup, team_id, division=division, name_hint=name_hint
        )
        meta["season"] = meta.get("season") or f"{season}-{str(season + 1)[-2:]}"
        appended = append_team(meta, teams_path)
        if appended:
            print(f"  Team {team_id}: {meta.get('name', '?')}")

        # Contests
        contests = extract_contests(soup, team_id)
        for c in contests:
            append_contest(c, contests_path)
            if c.get("opponent_id"):
                discovery.add_if_new(
                    c["opponent_id"],
                    c.get("opponent_name") or None,
                )

        processed += 1
        if processed % 10 == 0:
            print(f"  Processed {processed} teams, queue: {len(discovery)}")

    print(f"Done. Processed {processed} teams.")


def _load_contest_ids_from_csv(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "contest_id" not in reader.fieldnames:
            return out
        for row in reader:
            cid = (row.get("contest_id") or "").strip()
            if cid:
                out.add(cid)
    return out


def _scoring_rows_flat(contest_id: str, summary: dict) -> list[dict]:
    """One row per goal; if no goals, one row with empty goal columns."""
    base = {
        "contest_id": contest_id,
        "away_team_id": summary.get("away_team_id", ""),
        "home_team_id": summary.get("home_team_id", ""),
        "game_datetime": summary.get("game_datetime", ""),
    }
    goals = summary.get("goals") or []
    if not goals:
        return [{**base, **{k: "" for k in _GOAL_FIELDS}}]
    rows = []
    for g in goals:
        row = {**base}
        for k in _GOAL_FIELDS:
            row[k] = g.get(k, "")
        rows.append(row)
    return rows


def run_contest(
    contest_ids: list[str],
    output_dir: Path | str | None = None,
    scoring_csv: str | None = None,
    delay_seconds: float = 1.0,
    limit: int | None = None,
    skip_existing: bool = True,
) -> None:
    out = Path(output_dir or ".")
    out.mkdir(parents=True, exist_ok=True)
    path = out / (scoring_csv or SCORING_SUMMARY_DEFAULT)
    skip_list_path = out / SKIPPED_CONTESTS_DEFAULT

    seen_output: set[str] = set()
    if skip_existing:
        seen_output = load_scraped_contest_ids(path)

    skipped_file_ids = load_skipped_contest_ids(skip_list_path)

    # Deduplicate while preserving order
    ordered: list[str] = []
    dup: set[str] = set()
    for cid in contest_ids:
        c = cid.strip()
        if not c or c in dup:
            continue
        dup.add(c)
        ordered.append(c)

    if skip_existing:
        before = len(ordered)
        ordered = [c for c in ordered if c not in seen_output]
        skipped = before - len(ordered)
        if skipped:
            print(f"Skip {skipped} contest(s) already in {path}")

    before_skip_file = len(ordered)
    ordered = [c for c in ordered if c not in skipped_file_ids]
    skipped_from_file = before_skip_file - len(ordered)
    if skipped_from_file:
        print(
            f"Skip {skipped_from_file} contest(s) listed in {skip_list_path}"
        )

    if limit is not None:
        ordered = ordered[:limit]

    if not ordered:
        print("No contests to scrape.")
        return

    session = create_session()
    done = 0
    for i, contest_id in enumerate(ordered):
        if i > 0:
            time.sleep(delay_seconds)
        try:
            html = fetch_box_score_page(session, contest_id)
        except requests.RequestException as e:
            print(f"  Error fetching contest {contest_id}: {e}")
            append_skipped_contest_id(contest_id, skip_list_path)
            continue
        if html is None:
            append_skipped_contest_id(contest_id, skip_list_path)
            continue

        soup = BeautifulSoup(html, "html.parser")
        summary = extract_scoring_summary(soup)
        rows = _scoring_rows_flat(contest_id, summary)
        append_scoring_rows(rows, path)
        remove_skipped_contest_id(contest_id, skip_list_path)
        done += 1
        print(f"  Contest {contest_id}: {len(summary.get('goals') or [])} goal row(s)")

    print(f"Done. Wrote scoring data for {done} contest(s) to {path}")


def _build_legacy_teams_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="NCAA WSOC Stats Scraper (team crawl)")
    p.add_argument(
        "--season",
        type=int,
        default=2024,
        help="Season year (e.g., 2024 for 2024-25)",
    )
    p.add_argument(
        "--division",
        type=int,
        default=3,
        choices=[1, 2, 3],
        help="NCAA division",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print URL, do not fetch",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for teams.csv and contests.csv",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between requests (default 1.0)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Max teams to process (for testing)",
    )
    return p


def _build_main_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="NCAA WSOC Stats Scraper",
    )
    sub = parser.add_subparsers(dest="command", help="Command")

    teams_p = sub.add_parser("teams", help="Crawl rankings and team schedules (default pipeline)")
    teams_p.add_argument(
        "--season",
        type=int,
        default=2024,
        help="Season year (e.g., 2024 for 2024-25)",
    )
    teams_p.add_argument(
        "--division",
        type=int,
        default=3,
        choices=[1, 2, 3],
        help="NCAA division",
    )
    teams_p.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print URL, do not fetch",
    )
    teams_p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for teams.csv and contests.csv",
    )
    teams_p.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between requests (default 1.0)",
    )
    teams_p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Max teams to process (for testing)",
    )

    contest_p = sub.add_parser(
        "contest",
        help="Fetch box score Scoring Summary for contest ID(s)",
    )
    contest_p.add_argument(
        "--contest-id",
        action="append",
        default=[],
        metavar="ID",
        help="Contest ID (repeat for multiple)",
    )
    contest_p.add_argument(
        "--from-csv",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "CSV with contest_id column. If omitted: with --contest-id, only those IDs are "
            "used; without --contest-id, loads <output-dir>/contests_raw.csv"
        ),
    )
    contest_p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for output CSV",
    )
    contest_p.add_argument(
        "--scoring-csv",
        type=str,
        default=None,
        metavar="NAME",
        help=f"Output filename (default {SCORING_SUMMARY_DEFAULT})",
    )
    contest_p.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between requests (default 1.0)",
    )
    contest_p.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Max contests to process (for testing)",
    )
    contest_p.add_argument(
        "--skip-existing",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Skip contest IDs already present in output (default: skip)",
    )

    return parser


def main() -> None:
    """Entry point for CLI."""
    try:
        _main_cli()
    except ConsecutiveHttpFailures as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)


def _main_cli() -> None:
    argv = sys.argv[1:]

    if not argv or argv[0] not in ("teams", "contest"):
        legacy = _build_legacy_teams_parser()
        args = legacy.parse_args(argv)
        run(
            season=args.season,
            division=args.division,
            dry_run=args.dry_run,
            output_dir=args.output_dir,
            delay_seconds=args.delay,
            limit=args.limit,
        )
        return

    parser = _build_main_parser()
    args = parser.parse_args(argv)

    if args.command == "teams":
        run(
            season=args.season,
            division=args.division,
            dry_run=args.dry_run,
            output_dir=args.output_dir,
            delay_seconds=args.delay,
            limit=args.limit,
        )
    elif args.command == "contest":
        out = Path(args.output_dir or ".")
        default_csv = out / "contests_raw.csv"

        id_set: set[str] = set()
        if args.from_csv is not None:
            id_set |= _load_contest_ids_from_csv(args.from_csv)
            for cid in args.contest_id:
                c = cid.strip()
                if c:
                    id_set.add(c)
        elif args.contest_id:
            # Explicit IDs only — do not pull in the whole contests CSV by default.
            for cid in args.contest_id:
                c = cid.strip()
                if c:
                    id_set.add(c)
        else:
            id_set |= _load_contest_ids_from_csv(default_csv)

        if not id_set:
            print(
                "No contest IDs: pass --contest-id, or --from-csv, or rely on "
                f"{default_csv} when neither is given.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Stable sort for reproducibility
        combined = sorted(id_set, key=int)

        run_contest(
            contest_ids=combined,
            output_dir=args.output_dir,
            scoring_csv=args.scoring_csv,
            delay_seconds=args.delay,
            limit=args.limit,
            skip_existing=args.skip_existing,
        )
    else:
        parser.print_help()
        sys.exit(1)
