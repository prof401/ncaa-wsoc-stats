"""Contest box score: fetch and parse scoring summary (extensible for PBP, shots, etc.)."""

# Shot charts on some pages use JS addShot(); parsing may require browser or XHR inspection.
# Team Stats / Individual Stats / Play By Play live on separate paths under /contests/<id>/.

import re
from datetime import datetime
from typing import Any

import requests
from bs4 import BeautifulSoup

from .http import fetch_stats_page

BOX_SCORE_URL = "https://stats.ncaa.org/contests/{contest_id}/box_score"

_TEAM_LINK = re.compile(r"/teams/(\d+)")
_DATETIME_TD = re.compile(
    r"\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*(?:AM|PM)", re.I
)


def fetch_box_score_page(session: requests.Session, contest_id: str) -> str | None:
    """Fetch raw HTML for the box score page, or None on HTTP 500/502 after one retry."""
    url = BOX_SCORE_URL.format(contest_id=contest_id)
    return fetch_stats_page(session, url)


def _first_two_team_ids_from_banner(soup: BeautifulSoup) -> tuple[str, str, str, str]:
    """
    Away is left, home is right in the main scoreboard row (large logos).

    Returns (away_id, home_id, away_label, home_label) where label is anchor text (school name).
    """
    ids: list[str] = []
    labels: list[str] = []
    for img in soup.find_all("img", class_="large_logo_image"):
        a = img.find_parent("a", href=_TEAM_LINK)
        if not a:
            continue
        m = _TEAM_LINK.search(a.get("href", ""))
        if not m:
            continue
        tid = m.group(1)
        if tid in ids:
            continue
        ids.append(tid)
        label = a.get_text(" ", strip=True)
        if not label:
            label = (img.get("alt") or "").strip()
        labels.append(label)
        if len(ids) >= 2:
            break
    if len(ids) < 2:
        return "", "", "", ""
    return ids[0], ids[1], labels[0], labels[1]


def _normalize_name_key(name: str) -> str:
    if not name:
        return ""
    first = name.split()[0].lower() if name.split() else ""
    return first


def _extract_game_datetime(soup: BeautifulSoup) -> str:
    """Return best-effort ISO-like string from the scoreboard subtable (MM/DD/YYYY hh:mm AM/PM)."""
    for td in soup.find_all("td"):
        cls = td.get("class") or []
        if isinstance(cls, str):
            cls = cls.split()
        if "grey_text" not in cls:
            continue
        text = td.get_text(" ", strip=True)
        if _DATETIME_TD.search(text):
            # Single cell like "08/30/2019 02:00 PM"
            m = re.search(
                r"(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}:\d{2}\s*(?:AM|PM))",
                text,
                re.I,
            )
            if m:
                raw = f"{m.group(1)} {m.group(2)}"
                try:
                    dt = datetime.strptime(raw, "%m/%d/%Y %I:%M %p")
                    return dt.isoformat()
                except ValueError:
                    return raw.strip()
    return ""


def _scoring_team_id(
    cell: Any,
    away_id: str,
    home_id: str,
    away_label: str,
    home_label: str,
) -> str:
    link = cell.find("a", href=_TEAM_LINK)
    if link:
        m = _TEAM_LINK.search(link.get("href", ""))
        if m:
            return m.group(1)
    img = cell.find("img", class_="logo_image")
    alt = (img.get("alt") or "").strip() if img else ""
    if not alt:
        return ""
    ak = _normalize_name_key(away_label)
    hk = _normalize_name_key(home_label)
    alt_key = _normalize_name_key(alt)
    if alt_key and ak and (alt_key == ak or ak.startswith(alt_key) or alt_key in ak):
        return away_id
    if alt_key and hk and (alt_key == hk or hk.startswith(alt_key) or alt_key in hk):
        return home_id
    if ak and alt.lower().startswith(ak):
        return away_id
    if hk and alt.lower().startswith(hk):
        return home_id
    return ""


def extract_scoring_summary(soup: BeautifulSoup) -> dict[str, Any]:
    """
    Parse Scoring Summary card: away/home from banner, goals from table.

    Selectors follow current stats.ncaa.org markup; NCAA changes may require updates.

    Returns:
        away_team_id, home_team_id, game_datetime, goals (list of dicts with
        period, clock, scoring_team_id, play_text, away_score_after, home_score_after).
    """
    away_id, home_id, away_label, home_label = _first_two_team_ids_from_banner(soup)
    game_datetime = _extract_game_datetime(soup)

    goals: list[dict[str, Any]] = []

    summary_header: Any = None
    for div in soup.find_all("div", class_="card-header"):
        if div.get_text(strip=True) == "Scoring Summary":
            summary_header = div
            break

    if not summary_header:
        return {
            "away_team_id": away_id,
            "home_team_id": home_id,
            "game_datetime": game_datetime,
            "goals": goals,
        }

    body = summary_header.find_next_sibling("div", class_="card-body")
    table = body.find("table") if body else None
    if not table:
        return {
            "away_team_id": away_id,
            "home_team_id": home_id,
            "game_datetime": game_datetime,
            "goals": goals,
        }

    tbody = table.find("tbody")
    if not tbody:
        return {
            "away_team_id": away_id,
            "home_team_id": home_id,
            "game_datetime": game_datetime,
            "goals": goals,
        }

    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 6:
            continue
        period = cells[0].get_text(strip=True)
        clock = cells[1].get_text(strip=True)
        team_cell = cells[2]
        play_text = cells[3].get_text(" ", strip=True)
        away_after = cells[4].get_text(strip=True)
        home_after = cells[5].get_text(strip=True)
        sid = _scoring_team_id(
            team_cell, away_id, home_id, away_label, home_label
        )
        goals.append(
            {
                "period": period,
                "clock": clock,
                "scoring_team_id": sid,
                "play_text": play_text,
                "away_score_after": away_after,
                "home_score_after": home_after,
            }
        )

    return {
        "away_team_id": away_id,
        "home_team_id": home_id,
        "game_datetime": game_datetime,
        "goals": goals,
    }
