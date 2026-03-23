"""CSV persistence for teams and contests."""

import csv
from pathlib import Path
from typing import Any

TEAMS_CSV = "teams.csv"
CONTESTS_CSV = "contests.csv"

TEAMS_COLUMNS = [
    "team_id",
    "name",
    "season",
    "division",
    "coach",
    "overall_record",
    "org_id",
]
CONTESTS_COLUMNS = ["contest_id", "team_id", "opponent_id", "result", "attendance", "date"]

SCORING_SUMMARY_DEFAULT = "scoring_summary.csv"
SCORING_SUMMARY_COLUMNS = [
    "contest_id",
    "away_team_id",
    "home_team_id",
    "game_datetime",
    "period",
    "clock",
    "scoring_team_id",
    "play_text",
    "away_score_after",
    "home_score_after",
]


def _ensure_file(path: Path, columns: list[str]) -> None:
    """Create file with header if missing, or migrate legacy header."""
    if not path.exists():
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()
        return

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        existing_columns = reader.fieldnames or []
        if existing_columns == columns:
            return
        rows = list(reader)

    migrated_rows: list[dict[str, Any]] = []
    for row in rows:
        migrated = {k: row.get(k, "") for k in columns}
        # Legacy teams.csv used conference; map it forward when needed.
        if "overall_record" in columns and not migrated.get("overall_record"):
            migrated["overall_record"] = row.get("overall_record") or row.get(
                "conference", ""
            )
        migrated_rows.append(migrated)

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(migrated_rows)


def load_known_team_ids(teams_path: Path | str | None = None) -> set[str]:
    """
    Load team IDs from teams.csv if it exists.

    Args:
        teams_path: Path to teams.csv. Defaults to TEAMS_CSV in cwd.

    Returns:
        Set of team IDs already in the file.
    """
    path = Path(teams_path or TEAMS_CSV)
    if not path.exists():
        return set()

    known: set[str] = set()
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            tid = row.get("team_id", "").strip()
            if tid:
                known.add(tid)
    return known


def append_team(row: dict[str, Any], teams_path: Path | str | None = None) -> bool:
    """
    Append a team row if team_id is not already present.

    Args:
        row: Dict with keys matching TEAMS_COLUMNS.
        teams_path: Path to teams.csv.

    Returns:
        True if row was appended, False if team_id already existed.
    """
    path = Path(teams_path or TEAMS_CSV)
    _ensure_file(path, TEAMS_COLUMNS)

    known = load_known_team_ids(path)
    tid = str(row.get("team_id", "")).strip()
    if tid in known:
        return False

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=TEAMS_COLUMNS, extrasaction="ignore")
        writer.writerow({k: row.get(k, "") for k in TEAMS_COLUMNS})
    return True


def append_contest(
    row: dict[str, Any], contests_path: Path | str | None = None
) -> None:
    """
    Append a contest row to contests.csv.

    Args:
        row: Dict with keys matching CONTESTS_COLUMNS.
        contests_path: Path to contests.csv.
    """
    path = Path(contests_path or CONTESTS_CSV)
    _ensure_file(path, CONTESTS_COLUMNS)

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CONTESTS_COLUMNS, extrasaction="ignore")
        writer.writerow({k: row.get(k, "") for k in CONTESTS_COLUMNS})


def load_scraped_contest_ids(scoring_path: Path | str | None = None) -> set[str]:
    """
    contest_id values already present in scoring summary CSV (any row).

    Used for --skip-existing incremental scrapes.
    """
    path = Path(scoring_path or SCORING_SUMMARY_DEFAULT)
    if not path.exists():
        return set()

    out: set[str] = set()
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "contest_id" not in reader.fieldnames:
            return out
        for row in reader:
            cid = (row.get("contest_id") or "").strip()
            if cid:
                out.add(cid)
    return out


def append_scoring_rows(
    rows: list[dict[str, Any]],
    scoring_path: Path | str | None = None,
) -> None:
    """Append one or more scoring-summary rows; creates file with header if missing."""
    path = Path(scoring_path or SCORING_SUMMARY_DEFAULT)
    _ensure_file(path, SCORING_SUMMARY_COLUMNS)

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=SCORING_SUMMARY_COLUMNS, extrasaction="ignore"
        )
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in SCORING_SUMMARY_COLUMNS})
