"""HTTP session and headers for NCAA stats requests."""

import re
import time

import requests
from curl_cffi.requests import Session as CurlSession

_INTERSTITIAL_SIGNAL = "/_sec/verify?provider=interstitial"
_VERIFY_URL = "https://stats.ncaa.org/_sec/verify?provider=interstitial"


def _solve_interstitial(session: requests.Session, html: str, page_url: str) -> bool:
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
            headers={"Content-Type": "application/json", "Referer": page_url},
            timeout=15,
        )
        return resp.status_code < 400
    except Exception:
        return False


def fetch_stats_page(session: requests.Session, url: str, timeout: float = 30) -> str:
    """
    GET a stats.ncaa.org HTML page, solving Akamai interstitial if encountered.

    Use for team pages, box scores, and other pages behind the same protection.
    """
    resp = session.get(url, timeout=timeout)

    if _INTERSTITIAL_SIGNAL in resp.text:
        solved = _solve_interstitial(session, resp.text, url)
        if solved:
            time.sleep(1)
            resp = session.get(url, timeout=timeout)

    resp.raise_for_status()
    return resp.text


def create_session(headers: dict | None = None) -> requests.Session:
    """
    Create a curl_cffi Session with Chrome 131 impersonation to bypass Akamai
    bot detection via TLS/HTTP2 fingerprint spoofing.

    curl_cffi sets its own browser-matching headers (UA, Accept, Sec-Fetch-*)
    automatically when default_headers=True (the default). We only add Referer
    to establish session context, since that's not set by the impersonation.
    """
    sess = CurlSession(impersonate="chrome131", default_headers=True)
    # Only add Referer — do NOT override UA or Sec-Fetch headers that
    # curl_cffi sets automatically to match the Chrome 131 fingerprint
    extra = headers or {"Referer": "https://stats.ncaa.org/"}
    sess.headers.update(extra)

    try:
        sess.get("https://stats.ncaa.org/rankings/", timeout=10)
    except Exception:
        pass

    return sess
