"""SeedProcessor: fetch team IDs from National Rankings."""

import re
import time
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from .http import create_session

CHANGE_SPORT_URL = "https://stats.ncaa.org/rankings/change_sport_year_div"


def build_rankings_url(season: int, division: int = 3) -> str:
    """
    Build the change_sport_year_div URL for a given season.

    NCAA uses academic_year: 2024 season (fall) = academic_year 2025.
    Formula: academic_year = season + 1.
    No ranking_period needed.

    Args:
        season: Calendar year of the season (e.g., 2024 for 2024-25).
        division: NCAA division (1, 2, or 3).

    Returns:
        Full change_sport_year_div URL.
    """
    academic_year = float(season + 1)
    params = {
        "sport_code": "WSO",
        "academic_year": academic_year,
        "division": float(division),
    }
    return f"{CHANGE_SPORT_URL}?{urlencode(params)}"


def _extract_national_ranking_url(html: str, stat_seq: int = 60) -> str | None:
    """
    Parse change_sport_year_div HTML for the national_ranking URL (with ranking_period).
    Prefer stat_seq=60 (Winning Percentage) per requirements.
    """
    match = re.search(
        rf'href="(/rankings/national_ranking[^"]*stat_seq={stat_seq}(?:\.0)?[^"]*)"',
        html,
    )
    if match:
        path = match.group(1).replace("&amp;", "&")
        return f"https://stats.ncaa.org{path}" if path.startswith("/") else path
    match = re.search(r'href="(/rankings/national_ranking[^"]+)"', html)
    if match:
        path = match.group(1).replace("&amp;", "&")
        return f"https://stats.ncaa.org{path}" if path.startswith("/") else path
    return None


def fetch_rankings_page(
    season: int,
    division: int = 3,
    stat_seq: int = 60,
    headers: dict | None = None,
    session: requests.Session | None = None,
) -> requests.Response:
    """
    Fetch the rankings page via change_sport_year_div, then national_ranking.

    1. GET change_sport_year_div (no ranking_period) to set context.
    2. Parse page for national_ranking URL (includes ranking_period from page).
    3. GET national_ranking to retrieve team list.

    Args:
        season: Calendar year (e.g., 2024).
        division: NCAA division (1, 2, or 3).
        stat_seq: Stat type (60 = Winning Percentage per requirements).
        headers: Optional extra headers to pass to create_session.
        session: Optional requests.Session for connection reuse.

    Returns:
        Response from national_ranking (team list). Caller should check raise_for_status().
    """
    entry_url = build_rankings_url(season, division)

    if session is None:
        session = create_session(headers)

    resp1 = session.get(entry_url, timeout=30)
    resp1.raise_for_status()

    ranking_url = _extract_national_ranking_url(resp1.text, stat_seq)
    if not ranking_url:
        raise ValueError(
            "Could not find national_ranking link in change_sport_year_div response"
        )

    resp2 = session.get(ranking_url, timeout=30)
    return resp2


def extract_team_ids(html: str) -> list[str]:
    """
    Extract Team IDs from the rankings page HTML.

    Team links follow the pattern /teams/<team_id> on stats.ncaa.org.

    Args:
        html: Raw HTML from the rankings page.

    Returns:
        List of unique Team IDs (strings).
    """
    soup = BeautifulSoup(html, "html.parser")
    team_ids = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        match = re.search(r"/teams/(\d+)", href)
        if match:
            team_ids.add(match.group(1))

    return sorted(team_ids)


def get_team_ids_for_season(
    season: int,
    division: int = 3,
    delay_seconds: float = 1.0,
    session: requests.Session | None = None,
) -> list[str]:
    """
    Fetch the rankings page and return Team IDs for the given season.

    Args:
        season: Calendar year (e.g., 2024).
        division: NCAA division (1, 2, or 3).
        delay_seconds: Optional delay before request (rate limiting).
        session: Optional session for connection reuse (uses create_session if None).

    Returns:
        List of Team IDs.
    """
    time.sleep(delay_seconds)
    if session is None:
        session = create_session()
    resp = fetch_rankings_page(season, division, session=session)
    resp.raise_for_status()
    return extract_team_ids(resp.text)
