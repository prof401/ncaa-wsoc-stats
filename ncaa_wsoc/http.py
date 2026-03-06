"""HTTP session and headers for NCAA stats requests."""

import requests

# Minimal headers sufficient to avoid 406/403 - User-Agent and Referer are critical
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://stats.ncaa.org/rankings/",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
}


def create_session(headers: dict | None = None) -> requests.Session:
    """
    Create a session with headers and optional initial visit to establish cookies.

    Some sites require a prior visit before serving the target page.
    """
    sess = requests.Session()
    sess.headers.update(headers or DEFAULT_HEADERS)
    try:
        sess.get("https://stats.ncaa.org/rankings/", timeout=10)
    except requests.RequestException:
        pass
    return sess
