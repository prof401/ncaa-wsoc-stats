"""HTTP session and headers for NCAA stats requests."""

import re
import sys
import time
from collections.abc import Callable

import requests
from curl_cffi.requests import Session as CurlSession
from curl_cffi.requests.exceptions import Timeout as CurlTimeout

_INTERSTITIAL_SIGNAL = "/_sec/verify?provider=interstitial"
_VERIFY_URL = "https://stats.ncaa.org/_sec/verify?provider=interstitial"

# Abort after this many consecutive URLs that return these codes (after one retry each).
_STATS_RETRY_STATUS_CODES = frozenset({500, 502})
STATS_CONSECUTIVE_FAILURE_ABORT = 4


class ConsecutiveHttpFailures(Exception):
    """Raised when too many consecutive stats.ncaa.org requests fail with HTTP 500/502."""


class _ConsecutiveFailureTracker:
    def __init__(self, abort_at: int = STATS_CONSECUTIVE_FAILURE_ABORT) -> None:
        self.count = 0
        self.abort_at = abort_at

    def record_success(self) -> None:
        self.count = 0

    def record_failure(self) -> None:
        self.count += 1
        if self.count >= self.abort_at:
            raise ConsecutiveHttpFailures(
                f"Aborting: {self.count} consecutive stats.ncaa.org URLs returned "
                f"HTTP 500/502 after one retry each (limit {self.abort_at})."
            )


def _tracker(session: requests.Session) -> _ConsecutiveFailureTracker:
    if not hasattr(session, "_ncaa_stats_failure_tracker"):
        session._ncaa_stats_failure_tracker = _ConsecutiveFailureTracker()
    return session._ncaa_stats_failure_tracker  # type: ignore[attr-defined]


_TIMEOUT_EXCEPTIONS = (requests.exceptions.Timeout, CurlTimeout)


def _retry_once_on_timeout(call: Callable[[], requests.Response]) -> requests.Response:
    """Run ``call()``; on timeout, run once more, then re-raise."""
    try:
        return call()
    except _TIMEOUT_EXCEPTIONS:
        return call()


def request_stats_get(
    session: requests.Session, url: str, timeout: float = 30
) -> requests.Response | None:
    """
    GET a URL on stats.ncaa.org. On timeout, retry once. On HTTP 500 or 502, retry once;
    if still 500/502, log, count toward consecutive failures, and return None.
    Other status codes use raise_for_status.
    """
    tracker = _tracker(session)
    resp: requests.Response | None = None
    for _ in range(2):
        resp = _retry_once_on_timeout(lambda: session.get(url, timeout=timeout))
        if resp.status_code not in _STATS_RETRY_STATUS_CODES:
            break
    assert resp is not None
    if resp.status_code in _STATS_RETRY_STATUS_CODES:
        print(
            f"HTTP {resp.status_code} from stats.ncaa.org after retry, skipping: {url}",
            file=sys.stderr,
        )
        tracker.record_failure()
        return None
    resp.raise_for_status()
    tracker.record_success()
    return resp


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
    tracker = _tracker(session)

    try:
        resp: requests.Response | None = None
        for _ in range(2):
            resp = _retry_once_on_timeout(
                lambda: session.post(
                    _VERIFY_URL,
                    json={"bm-verify": token, "pow": pow_val},
                    headers={"Content-Type": "application/json", "Referer": page_url},
                    timeout=15,
                )
            )
            if resp.status_code not in _STATS_RETRY_STATUS_CODES:
                break
        assert resp is not None
        if resp.status_code in _STATS_RETRY_STATUS_CODES:
            print(
                f"HTTP {resp.status_code} from stats.ncaa.org verify POST after retry, "
                f"skipping: {page_url}",
                file=sys.stderr,
            )
            tracker.record_failure()
            return False
        ok = resp.status_code < 400
        if ok:
            tracker.record_success()
        return ok
    except ConsecutiveHttpFailures:
        raise
    except Exception:
        return False


def fetch_stats_page(session: requests.Session, url: str, timeout: float = 30) -> str | None:
    """
    GET a stats.ncaa.org HTML page, solving Akamai interstitial if encountered.

    On persistent HTTP 500/502 (after one retry), logs and returns None. On timeout,
    ``request_stats_get`` retries once then may raise.
    Use for team pages, box scores, and other pages behind the same protection.
    """
    resp = request_stats_get(session, url, timeout=timeout)
    if resp is None:
        return None

    if _INTERSTITIAL_SIGNAL in resp.text:
        solved = _solve_interstitial(session, resp.text, url)
        if solved:
            time.sleep(1)
            resp = request_stats_get(session, url, timeout=timeout)
            if resp is None:
                return None

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
        request_stats_get(sess, "https://stats.ncaa.org/rankings/", timeout=10)
    except ConsecutiveHttpFailures:
        raise
    except Exception:
        pass

    return sess
