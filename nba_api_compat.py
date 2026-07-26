"""Compatibility shims for the public NBA data stack, extracted from the
studies where they were first debugged (see the family's tooling-gotchas
finding for the full evidence trail).

- fix_user_agent(): stats.nba.com hangs requests whose User-Agent claims a
  real browser that the TLS fingerprint can't back up (nba_api ships a
  Firefox/72 UA that hangs 30/30). A generic Mozilla UA with no browser
  token returns 200 instantly. Call before any nba_api endpoint use.
- shim_np_in1d(): numpy 2.x removed np.in1d, which nba-on-court still
  calls. Call before importing nba_on_court.
"""
from __future__ import annotations

GENERIC_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36")


def fix_user_agent() -> None:
    from nba_api.stats.library import http
    http.STATS_HEADERS["User-Agent"] = GENERIC_UA


def shim_np_in1d() -> None:
    import numpy as np
    if not hasattr(np, "in1d"):
        np.in1d = np.isin
