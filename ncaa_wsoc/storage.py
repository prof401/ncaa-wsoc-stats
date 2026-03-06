"""CSV persistence for teams and contests."""

import csv
from pathlib import Path
from typing import Any

TEAMS_CSV = "teams.csv"
CONTESTS_CSV = "contests.csv"

TEAMS_COLUMNS = ["team_id", "name", "season", "division", "coach", "conference"]
CONTESTS_COLUMNS = ["contest_id", "team_id", "opponent_id", "result", "attendance", "date"]


def _ensure_file(path: Path, columns: list[str]) -> None:
    """Create file with header if it doesn't exist."""
    if not path.exists():
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()


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
