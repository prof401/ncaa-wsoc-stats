"""CLI and orchestration for NCAA WSOC scraper."""

import argparse
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from .discovery import DiscoveryManager
from .http import create_session
from .rankings import build_rankings_url, get_team_ids_for_season
from .storage import append_contest, append_team, load_known_team_ids
from .team import extract_contests, extract_team_metadata, fetch_team_page


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
    team_ids = get_team_ids_for_season(season, division, session=session)
    print(f"Seed: {len(team_ids)} team IDs")

    known = load_known_team_ids(teams_path)
    discovery = DiscoveryManager(known_ids=known)
    discovery.add_seed_ids(team_ids)
    print(f"Queue: {len(discovery)} teams to process (known: {len(known)})")

    processed = 0
    while not discovery.is_empty() and (limit is None or processed < limit):
        team_id = discovery.pop_next()
        if not team_id:
            break

        time.sleep(delay_seconds)
        try:
            html = fetch_team_page(session, team_id)
        except requests.RequestException as e:
            print(f"  Error fetching team {team_id}: {e}")
            continue

        soup = BeautifulSoup(html, "html.parser")

        # Metadata
        meta = extract_team_metadata(soup, team_id, division=division)
        meta["season"] = meta.get("season") or f"{season}-{str(season + 1)[-2:]}"
        appended = append_team(meta, teams_path)
        if appended:
            print(f"  Team {team_id}: {meta.get('name', '?')}")

        # Contests
        contests = extract_contests(soup, team_id)
        for c in contests:
            append_contest(c, contests_path)
            if c.get("opponent_id"):
                discovery.add_if_new(c["opponent_id"])

        processed += 1
        if processed % 10 == 0:
            print(f"  Processed {processed} teams, queue: {len(discovery)}")

    print(f"Done. Processed {processed} teams.")


def main() -> None:
    """Entry point for CLI."""
    parser = argparse.ArgumentParser(description="NCAA WSOC Stats Scraper")
    parser.add_argument(
        "--season",
        type=int,
        default=2024,
        help="Season year (e.g., 2024 for 2024-25)",
    )
    parser.add_argument(
        "--division",
        type=int,
        default=3,
        choices=[1, 2, 3],
        help="NCAA division",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print URL, do not fetch",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for teams.csv and contests.csv",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Seconds between requests (default 1.0)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Max teams to process (for testing)",
    )
    args = parser.parse_args()

    run(
        season=args.season,
        division=args.division,
        dry_run=args.dry_run,
        output_dir=args.output_dir,
        delay_seconds=args.delay,
        limit=args.limit,
    )
