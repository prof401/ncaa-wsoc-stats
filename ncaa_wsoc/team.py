"""TeamProcessor: fetch team page, extract metadata and schedule."""

import re
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from .http import fetch_stats_page

TEAM_BASE_URL = "https://stats.ncaa.org/teams/"


def fetch_team_page(session: requests.Session, team_id: str) -> str | None:
    """
    Fetch the team page HTML, solving Akamai interstitial challenge if encountered.

    Args:
        session: Requests session with headers and cookies.
        team_id: NCAA team ID.

    Returns:
        Raw HTML string, or None if the page returned HTTP 500/502 after one retry.
    """
    url = f"{TEAM_BASE_URL}{team_id}"
    return fetch_stats_page(session, url)


# Banner line when NCAA still shows "School Mascot (W-L)" but removed ATHLETICS_URL / logo.
# Group 1 is the W-L(-T) fragment inside parentheses.
_RECORD_SUFFIX_IN_PARENS = re.compile(
    r"\s*\(\s*(\d+\s*-\s*\d+(?:\s*-\s*\d+)?)\s*\)\s*$"
)
# Same pattern allowed anywhere in the header (some pages append text after "(0-1)").
_RECORD_IN_PARENS = re.compile(
    r"\(\s*(\d+\s*-\s*\d+(?:\s*-\s*\d+)?)\s*\)"
)

# Hyphen / minus / en dash (NCAA sometimes uses U+2212 or U+2013 instead of ASCII "-").
_UNICODE_DASHES = re.compile(r"[\u2010\u2011\u2012\u2013\u2014\u2212]")


def _normalize_dashes_to_ascii(s: str) -> str:
    """Map Unicode dash characters to ASCII hyphen so W-L regexes match."""
    return _UNICODE_DASHES.sub("-", s)


def _normalize_record_text(value: str) -> str:
    """Extract a single W-L or W-L-T token from a label or banner fragment."""
    if not value:
        return ""
    value = _normalize_dashes_to_ascii(value.strip())
    collapsed = re.sub(r"\s*-\s*", "-", value)
    match = re.search(r"\b\d+-\d+(?:-\d+)?\b", collapsed)
    return match.group(0) if match else collapsed.strip()


def _record_from_parens_in_text(text: str) -> str:
    """Prefer end-anchored (banner); else last (W-L) in the string (trailing junk after parens)."""
    text = _normalize_dashes_to_ascii(text)
    m = _RECORD_SUFFIX_IN_PARENS.search(text)
    if m:
        return _normalize_record_text(m.group(1))
    matches = list(_RECORD_IN_PARENS.finditer(text))
    if matches:
        return _normalize_record_text(matches[-1].group(1))
    return ""


def _is_overall_card_header_label(label: str) -> bool:
    """True for 'Overall', 'Overall Record', etc."""
    t = label.strip().lower()
    if not t:
        return False
    if t in ("overall", "overall record"):
        return True
    return bool(re.match(r"^overall\s+record\b", t))


def _extract_record_from_banner_card_header(soup: BeautifulSoup) -> str:
    """
    Overall record shown next to the team name in the top banner card-header
    as 'School (3-4)' when the Overall summary card is missing or different markup.
    """
    for header in soup.find_all("div", class_="card-header"):
        text = header.get_text(" ", strip=True)
        if not text:
            continue
        rec = _record_from_parens_in_text(text)
        if rec:
            return rec

    return ""


def _extract_overall_record(soup: BeautifulSoup) -> str:
    """Extract overall record text from team summary cards/labels."""
    # Current NCAA card layout: card-header "Overall" + card-body first <span>.
    for header in soup.find_all("div", class_="card-header"):
        if _is_overall_card_header_label(header.get_text(" ", strip=True)):
            body = header.find_next_sibling("div", class_="card-body")
            if body:
                span = body.find("span")
                if span:
                    got = _normalize_record_text(span.get_text(" ", strip=True))
                    if got:
                        return got
                raw = body.get_text(" ", strip=True)
                if raw:
                    got = _normalize_record_text(raw)
                    if got:
                        return got

    # Common layout: <dt>Overall</dt><dd>10-2-3</dd>
    for dt in soup.find_all("dt"):
        label = dt.get_text(" ", strip=True).lower()
        if "overall" in label and "record" in label:
            dd = dt.find_next_sibling("dd")
            if dd:
                return _normalize_record_text(dd.get_text(" ", strip=True))
        elif label == "overall":
            dd = dt.find_next_sibling("dd")
            if dd:
                return _normalize_record_text(dd.get_text(" ", strip=True))

    # Fallback: explicit "Overall Record" text in card details.
    text = _normalize_dashes_to_ascii(soup.get_text(" ", strip=True))
    match = re.search(r"overall\s+record[:\s]+([0-9]+(?:-[0-9]+){1,2})", text, re.I)
    if match:
        return _normalize_record_text(match.group(1).strip())

    return _extract_record_from_banner_card_header(soup)


def _short_name_from_header(header: Any) -> str:
    """School short name from logo_image alt text in a card-header."""
    img = header.find("img", class_="logo_image")
    if not img:
        return ""
    alt = (img.get("alt") or "").strip()
    if not alt or alt.upper() == "NCAA":
        return ""
    return alt


def _team_name_from_banner_card_header(soup: BeautifulSoup) -> str:
    """
    Some team pages omit the athletics link and header logo; schedule logos are
    in table cells, not .card-header. The first summary card-header is often
    still 'Nickname (W-L)' or 'School (W-L)'.
    """
    for header in soup.find_all("div", class_="card-header"):
        text = header.get_text(" ", strip=True)
        if not text:
            continue
        text = _normalize_dashes_to_ascii(text)
        if _RECORD_SUFFIX_IN_PARENS.search(text):
            return _RECORD_SUFFIX_IN_PARENS.sub("", text).strip()
        matches = list(_RECORD_IN_PARENS.finditer(text))
        if matches:
            last = matches[-1]
            return (text[: last.start()] + text[last.end() :]).strip()
    return ""


def _extract_team_name(soup: BeautifulSoup) -> str:
    """
    Short team name: NCAA almost always puts it in the banner logo alt next to
    the athletics link. That is the single consistent source when present.

    Order:
      1. logo_image alt in the same .card-header as <a target="ATHLETICS_URL">
      2. Text of that athletics link (often longer; used only if alt missing)
      3. Heuristic: first early .card-header with logo_image (rare if markup
         changes).
      4. First .card-header whose text ends with a (W-L) or (W-L-T) record —
         name is the text before that parenthesis (covers pages with no
         ATHLETICS_URL and no banner logo).
    """
    athletics = soup.find("a", target="ATHLETICS_URL")

    if athletics:
        header = athletics.find_parent("div", class_="card-header")
        if header:
            alt = _short_name_from_header(header)
            if alt:
                return alt
        link_text = athletics.get_text(strip=True)
        if link_text:
            return link_text

    for card in soup.find_all("div", class_="card", limit=40):
        ch = card.find("div", class_="card-header")
        if not ch:
            continue
        alt = _short_name_from_header(ch)
        if alt:
            return alt

    banner = _team_name_from_banner_card_header(soup)
    if banner:
        return banner

    return ""


def _extract_coach_name_from_card_body(card_body: Any) -> str:
    """
    Coach name from the Coach summary card body.

    Multiple <dd> rows appear when there was a mid-season change. The first
    linked coach name in document order is used (season-start coach when the
    site lists chronologically). If no links exist, the first non-empty <dd>
    text is used.
    """
    for dd in card_body.find_all("dd"):
        for a in dd.find_all("a"):
            name = a.get_text(strip=True)
            if name:
                return name
    for dd in card_body.find_all("dd"):
        name = dd.get_text(strip=True)
        if name:
            return name
    return ""


def _is_coach_section_header(header_text: str) -> bool:
    """True for summary cards titled Coach or Coaches (NCAA uses both)."""
    t = header_text.strip().lower()
    return t in ("coach", "coaches")


def extract_division_from_ranking_summary(
    soup: BeautifulSoup, sport_code: str = "WSO"
) -> int | None:
    """
    NCAA team pages link to ranking_summary with division=1.0|2.0|3.0.

    Prefer the link for this scraper's sport_code when multiple exist.
    """
    any_div: int | None = None
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        if "ranking_summary" not in href:
            continue
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        raw = (qs.get("division") or [None])[0]
        if raw is None:
            continue
        try:
            d = int(float(raw))
        except (TypeError, ValueError):
            continue
        if d not in (1, 2, 3):
            continue
        sc = (qs.get("sport_code") or [""])[0].upper()
        if sc == sport_code.upper():
            return d
        if any_div is None:
            any_div = d
    return any_div


def _parse_team_history_org_id(href: str) -> str:
    """
    NCAA Team History URLs use either ?org_id=… or a path ending in …/WSO/<org_id>
    (or other sport code). Return the numeric org id, or "" if not found.
    """
    href = href.replace("&amp;", "&").strip()
    if not href:
        return ""
    parsed = urlparse(href)
    qs = parse_qs(parsed.query)
    raw = (qs.get("org_id") or [None])[0]
    if raw is not None and str(raw).strip().isdigit():
        return str(raw).strip()
    path = (parsed.path or "").rstrip("/")
    if not path:
        return ""
    parts = [p for p in path.split("/") if p]
    if parts and parts[-1].isdigit():
        return parts[-1]
    return ""


def _extract_team_history_org_id(soup: BeautifulSoup, sport_code: str = "WSO") -> str:
    """
    Find the Team History link on a team page and parse the org id (stable across
    seasons for the same school/sport).
    """
    candidates: list[Any] = []
    for a in soup.find_all("a", href=True):
        href = str(a.get("href") or "")
        if "/teams/history" not in href.lower():
            continue
        text = (a.get_text() or "").strip().lower()
        if "team history" in text or sport_code.lower() in href.lower():
            candidates.append(a)
    search_order = candidates if candidates else [
        a
        for a in soup.find_all("a", href=True)
        if "/teams/history" in str(a.get("href") or "").lower()
    ]
    for a in search_order:
        oid = _parse_team_history_org_id(str(a.get("href") or ""))
        if oid:
            return oid
    return ""


def extract_team_metadata(
    soup: BeautifulSoup,
    team_id: str,
    season: str | None = None,
    division: int = 3,
    name_hint: str | None = None,
) -> dict[str, Any]:
    """
    Extract team metadata from the NCAA stats team page.

    Page structure (confirmed from live HTML):
      - Team name (short): <img class="logo_image" alt="…"> in the .card-header
        that contains <a target="ATHLETICS_URL">; else that link's text; else
        rare heuristic: first early .card-header with a logo_image; else first
        .card-header like "School (W-L)" when the banner link/logo is absent
      - Season: selected <option> in <select id="year_list">
      - Coach: .card-header text=="Coach" -> sibling .card-body -> <dd> rows;
        first linked name (multiple rows when coaching changed mid-season)
      - org_id: from the Team History link (same across seasons for a program)

    Args:
        soup: Parsed team page HTML.
        team_id: NCAA team ID.
        season: Academic year string (e.g., "2023-24"). Inferred from page if None.
        division: Fallback NCAA division if the page has no ranking_summary link (default 3).
        name_hint: Optional name from the seed/discovery link; when non-empty, used as
            the team ``name`` written to teams.csv (page-extracted name is ignored).

    Returns:
        Dict with team_id, name, coach, season, overall_record, division, org_id.
    """
    result: dict[str, Any] = {
        "team_id": team_id,
        "name": "",
        "coach": "",
        "season": season or "",
        "overall_record": "",
        "division": division,
        "org_id": "",
    }

    page_division = extract_division_from_ranking_summary(soup)
    if page_division is not None:
        result["division"] = page_division

    name_from_page = _extract_team_name(soup)
    hint = name_hint.strip() if name_hint else ""
    result["name"] = hint if hint else name_from_page

    # Season: selected option in <select id="year_list">
    if not result["season"]:
        year_sel = soup.find("select", id="year_list")
        if year_sel:
            opt = year_sel.find("option", selected=True) or year_sel.find("option")
            if opt:
                result["season"] = opt.get_text(strip=True)

    # Coach: card-header "Coach" or "Coaches" -> card-body (see _is_coach_section_header)
    for header in soup.find_all(class_="card-header"):
        if _is_coach_section_header(header.get_text(strip=True)):
            card_body = header.find_next_sibling(class_="card-body")
            if card_body:
                result["coach"] = _extract_coach_name_from_card_body(card_body)
            break

    result["overall_record"] = _extract_overall_record(soup)
    result["org_id"] = _extract_team_history_org_id(soup)

    if not (result["coach"] or "").strip():
        result["coach"] = "Unknown"

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
                "opponent_name": "",
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
                        contest["opponent_name"] = opp_link.get_text(" ", strip=True)

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

            # Omit rows with no contest page link (canceled, unplayed, malformed rows)
            if contest["contest_id"]:
                contests.append(contest)

        if contests:
            break

    return contests
