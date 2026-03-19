"""TeamProcessor: fetch team page, extract metadata and schedule."""

import re
import time
from typing import Any
import requests
from bs4 import BeautifulSoup

TEAM_BASE_URL = "https://stats.ncaa.org/teams/"

_INTERSTITIAL_SIGNAL = "/_sec/verify?provider=interstitial"
_VERIFY_URL = "https://stats.ncaa.org/_sec/verify?provider=interstitial"


def _solve_interstitial(session: requests.Session, html: str, team_url: str) -> bool:
    """
    Solve Akamai Bot Manager interstitial PoW challenge.

    Extracts the bm-verify token and PoW values from the challenge HTML,
    POSTs the answer to /_sec/verify, and updates session cookies.
    Returns True if the POST succeeded (status < 400).
    """
    i_match = re.search(r"var i = (\d+);", html)
    pow_match = re.search(r'Number\("(\d+)" \+ "(\d+)"\)', html)
    token_match = re.search(
        r'xhr\.send\(JSON\.stringify\(\{"bm-verify": "([^"]+)"', html
    )

    if not (i_match and pow_match and token_match):
        return False

    i_val = int(i_match.group(1))
    pow_val = i_val + int(pow_match.group(1) + pow_match.group(2))
    token = token_match.group(1)

    try:
        resp = session.post(
            _VERIFY_URL,
            json={"bm-verify": token, "pow": pow_val},
            headers={"Content-Type": "application/json", "Referer": team_url},
            timeout=15,
        )
        return resp.status_code < 400
    except Exception:
        return False


def fetch_team_page(session: requests.Session, team_id: str) -> str:
    """
    Fetch the team page HTML, solving Akamai interstitial challenge if encountered.

    Args:
        session: Requests session with headers and cookies.
        team_id: NCAA team ID.

    Returns:
        Raw HTML string.
    """
    url = f"{TEAM_BASE_URL}{team_id}"
    resp = session.get(url, timeout=30)

    if _INTERSTITIAL_SIGNAL in resp.text:
        solved = _solve_interstitial(session, resp.text, url)
        if solved:
            time.sleep(1)
            resp = session.get(url, timeout=30)

    resp.raise_for_status()
    return resp.text


def _extract_overall_record(soup: BeautifulSoup) -> str:
    """Extract overall record text from team summary cards/labels."""
    def _normalize_record(value: str) -> str:
        match = re.search(r"\b\d+-\d+(?:-\d+)?\b", value or "")
        return match.group(0) if match else value.strip()

    # Current NCAA card layout: card-header "Overall" + card-body first <span>.
    for header in soup.find_all("div", class_="card-header"):
        if header.get_text(" ", strip=True).lower() == "overall":
            body = header.find_next_sibling("div", class_="card-body")
            if body:
                span = body.find("span")
                if span:
                    return _normalize_record(span.get_text(" ", strip=True))

    # Common layout: <dt>Overall</dt><dd>10-2-3</dd>
    for dt in soup.find_all("dt"):
        label = dt.get_text(" ", strip=True).lower()
        if "overall" in label and "record" in label:
            dd = dt.find_next_sibling("dd")
            if dd:
                return _normalize_record(dd.get_text(" ", strip=True))
        elif label == "overall":
            dd = dt.find_next_sibling("dd")
            if dd:
                return _normalize_record(dd.get_text(" ", strip=True))

    # Fallback: explicit "Overall Record" text in card details.
    text = soup.get_text(" ", strip=True)
    match = re.search(r"overall\s+record[:\s]+([0-9]+(?:-[0-9]+){1,2})", text, re.I)
    if match:
        return _normalize_record(match.group(1).strip())

    return ""


def extract_team_metadata(
    soup: BeautifulSoup, team_id: str, season: str | None = None, division: int = 1
) -> dict[str, Any]:
    """
    Extract team metadata from the NCAA stats team page.

    Page structure (confirmed from live HTML):
      - Team name: <a target="ATHLETICS_URL"> inside .card-header
      - Season: selected <option> in <select id="year_list">
      - Coach: .card-header text=="Coach" -> sibling .card-body -> first <dd> <a>

    Args:
        soup: Parsed team page HTML.
        team_id: NCAA team ID.
        season: Academic year string (e.g., "2023-24"). Inferred from page if None.
        division: NCAA division (1, 2, or 3).

    Returns:
        Dict with team_id, name, coach, season, overall_record, division.
    """
    result: dict[str, Any] = {
        "team_id": team_id,
        "name": "",
        "coach": "",
        "season": season or "",
        "overall_record": "",
        "division": division,
    }

    # Team name: <a target="ATHLETICS_URL">Utah Tech Trailblazers</a>
    athletics_link = soup.find("a", target="ATHLETICS_URL")
    if athletics_link:
        result["name"] = athletics_link.get_text(strip=True)

    # Season: selected option in <select id="year_list">
    if not result["season"]:
        year_sel = soup.find("select", id="year_list")
        if year_sel:
            opt = year_sel.find("option", selected=True) or year_sel.find("option")
            if opt:
                result["season"] = opt.get_text(strip=True)

    # Coach: card-header "Coach" -> card-body -> first dd (contains <a>Name</a>)
    for header in soup.find_all(class_="card-header"):
        if header.get_text(strip=True) == "Coach":
            card_body = header.find_next_sibling(class_="card-body")
            if card_body:
                name_dd = card_body.find("dd")
                if name_dd:
                    coach_link = name_dd.find("a")
                    result["coach"] = (
                        coach_link.get_text(strip=True)
                        if coach_link
                        else name_dd.get_text(strip=True)
                    )
            break

    result["overall_record"] = _extract_overall_record(soup)

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
