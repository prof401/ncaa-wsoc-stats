"""TeamProcessor: fetch team page, extract metadata and schedule."""

import re
from typing import Any

import requests
from bs4 import BeautifulSoup

TEAM_BASE_URL = "https://stats.ncaa.org/teams/"


def fetch_team_page(session: requests.Session, team_id: str) -> str:
    """
    Fetch the team page HTML.

    Args:
        session: Requests session with headers and cookies.
        team_id: NCAA team ID.

    Returns:
        Raw HTML string.
    """
    url = f"{TEAM_BASE_URL}{team_id}"
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def extract_team_metadata(
    soup: BeautifulSoup, team_id: str, season: str | None = None, division: int = 1
) -> dict[str, Any]:
    """
    Extract team metadata from the team page.

    Args:
        soup: Parsed team page HTML.
        team_id: NCAA team ID.
        season: Academic year string (e.g., "2023-24"). Inferred from page if None.
        division: NCAA division (1, 2, or 3).

    Returns:
        Dict with team_id, name, coach, season, conference, division.
    """
    result: dict[str, Any] = {
        "team_id": team_id,
        "name": "",
        "coach": "",
        "season": season or "",
        "conference": "",
        "division": division,
    }

    # Team name: often in h1, or in page title, or in a heading
    h1 = soup.find("h1")
    if h1:
        result["name"] = h1.get_text(strip=True)

    # Fallback: look for common patterns
    if not result["name"]:
        for tag in soup.find_all(["h2", "h3", "span"], class_=True):
            text = tag.get_text(strip=True)
            if text and len(text) < 100 and not text.startswith("http"):
                result["name"] = text
                break

    # Coach: often in a block with "Head Coach" or "Coach"
    for text in soup.stripped_strings:
        if "head coach" in text.lower() or "coach:" in text.lower():
            # Next sibling or nearby might be the name
            pass
    # Look for table or div with coach info
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            label = cells[0].get_text(strip=True).lower()
            if "coach" in label:
                result["coach"] = cells[1].get_text(strip=True)
                break

    # Conference: similar pattern
    for row in soup.find_all("tr"):
        cells = row.find_all(["th", "td"])
        if len(cells) >= 2:
            label = cells[0].get_text(strip=True).lower()
            if "conference" in label or "conf" in label:
                result["conference"] = cells[1].get_text(strip=True)
                break

    # Season: from dropdown or page context
    if not result["season"]:
        sel = soup.find("select", {"id": re.compile(r"year|season", re.I)})
        if sel:
            opt = sel.find("option", selected=True) or sel.find("option")
            if opt:
                result["season"] = opt.get_text(strip=True)

    return result


def extract_contests(soup: BeautifulSoup, team_id: str) -> list[dict[str, Any]]:
    """
    Extract contests from the Schedule/Results table.

    Args:
        soup: Parsed team page HTML.
        team_id: The team being scraped (primary).

    Returns:
        List of dicts with contest_id, team_id, opponent_id, result, attendance, date.
    """
    contests: list[dict[str, Any]] = []

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # Find header row to map columns
        header_cells = rows[0].find_all(["th", "td"])
        headers = [c.get_text(strip=True).lower() for c in header_cells]
        if not any(
            h and ("date" in h or "opponent" in h or "result" in h) for h in headers
        ):
            continue

        # Map column indices
        col_map: dict[str, int] = {}
        for i, h in enumerate(headers):
            if "date" in (h or ""):
                col_map["date"] = i
            elif "opponent" in (h or ""):
                col_map["opponent"] = i
            elif "result" in (h or ""):
                col_map["result"] = i
            elif "attend" in (h or ""):
                col_map["attendance"] = i

        for row in rows[1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) < 2:
                continue

            contest: dict[str, Any] = {
                "contest_id": "",
                "team_id": team_id,
                "opponent_id": "",
                "result": "",
                "attendance": "",
                "date": "",
            }

            # Date
            if "date" in col_map and col_map["date"] < len(cells):
                contest["date"] = cells[col_map["date"]].get_text(strip=True)

            # Opponent: extract /teams/<id> link
            if "opponent" in col_map:
                opp_cell = cells[col_map["opponent"]]
                opp_link = opp_cell.find("a", href=re.compile(r"/teams/\d+"))
                if opp_link:
                    match = re.search(r"/teams/(\d+)", opp_link.get("href", ""))
                    if match:
                        contest["opponent_id"] = match.group(1)

            # Result: W 2-1, L 1-0, etc.
            if "result" in col_map and col_map["result"] < len(cells):
                contest["result"] = cells[col_map["result"]].get_text(strip=True)

            # Contest ID: from result link /contests/<id>/box_score (any cell in row)
            for cell in cells:
                res_link = cell.find("a", href=re.compile(r"/contests/\d+"))
                if res_link:
                    match = re.search(r"/contests/(\d+)", res_link.get("href", ""))
                    if match:
                        contest["contest_id"] = match.group(1)
                        break

            # Attendance
            if "attendance" in col_map and col_map["attendance"] < len(cells):
                contest["attendance"] = cells[col_map["attendance"]].get_text(
                    strip=True
                )

            # Only add if we have meaningful data
            if contest["date"] or contest["opponent_id"] or contest["result"]:
                contests.append(contest)

        if contests:
            break

    return contests
