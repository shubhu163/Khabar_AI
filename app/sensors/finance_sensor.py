"""
Khabar AI — Finance Sensor
===============================================
Fetches real-time stock data from Alpha Vantage and computes a simple
volatility metric (percentage change) used by the Analyst Agent to
correlate news events with market reaction.

FREE-TIER SAFEGUARDS
  • 25 requests / day, 5 / minute on the free key.
  • We cache results per ticker for the duration of the pipeline run
    using an in-memory dict (``_cache``).
  • We only call the API when the Triage Agent has flagged a relevant
    news article — i.e. only *after* filtering, never speculatively.

VOLATILITY METRIC
  % change = ((current - previous_close) / previous_close) * 100
  If |% change| > 3 %, we label the signal "high" volatility.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants & in-memory cache
# ---------------------------------------------------------------------------
_AV_BASE = "https://www.alphavantage.co/query"
_VOLATILITY_HIGH_THRESHOLD = 3.0  # percent
_cache: dict[str, dict[str, Any]] = {}  # ticker -> cached result
_last_call_ts: float = 0.0  # rate-limit: min 12 s between calls (5/min)


# ---------------------------------------------------------------------------
# Mock data for dry-run / testing
# ---------------------------------------------------------------------------
_MOCK_QUOTE: dict[str, Any] = {
    "ticker": "MOCK",
    "price": 185.42,
    "previous_close": 182.10,
    "change_pct": 1.82,
    "volatility_label": "normal",
    "fetched_at": datetime.now(timezone.utc).isoformat(),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def fetch_stock_data(ticker: str) -> dict[str, Any]:
    """
    Return current price, previous close, and volatility for *ticker*.

    Parameters
    ----------
    ticker : str
        e.g. "AAPL", "NVDA"

    Returns
    -------
    dict with keys:
        ticker, price, previous_close, change_pct, volatility_label, fetched_at
    """
    settings = get_settings()

    # --- Dry-run shortcut ---
    if settings.dry_run or not settings.alpha_vantage_key:
        logger.info("[DRY RUN] Returning mock stock data for %s", ticker)
        mock = _MOCK_QUOTE.copy()
        mock["ticker"] = ticker
        return mock

    # --- Cache hit ---
    if ticker in _cache:
        logger.debug("Cache hit for %s", ticker)
        return _cache[ticker]

    # --- Rate-limit guard ---
    _respect_rate_limit()

    params = {
        "function": "GLOBAL_QUOTE",
        "symbol": ticker,
        "apikey": settings.alpha_vantage_key,
    }

    try:
        resp = requests.get(_AV_BASE, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        quote = data.get("Global Quote", {})
        if not quote:
            logger.warning("Alpha Vantage returned empty quote for %s", ticker)
            return _empty_result(ticker)

        price = float(quote.get("05. price", 0))
        prev_close = float(quote.get("08. previous close", 0))
        change_pct = float(quote.get("10. change percent", "0").replace("%", ""))

        result = {
            "ticker": ticker,
            "price": price,
            "previous_close": prev_close,
            "change_pct": round(change_pct, 2),
            "volatility_label": (
                "high" if abs(change_pct) > _VOLATILITY_HIGH_THRESHOLD else "normal"
            ),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        _cache[ticker] = result
        logger.info(
            "Alpha Vantage: %s @ $%.2f (%.2f%% change)",
            ticker, price, change_pct,
        )
        return result

    except requests.RequestException as exc:
        logger.error("Alpha Vantage request failed for %s: %s", ticker, exc)
        return _empty_result(ticker)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _respect_rate_limit() -> None:
    """
    Ensure at least 12 seconds between Alpha Vantage calls
    (5 calls / minute on the free tier → 12 s spacing is safe).
    """
    global _last_call_ts
    elapsed = time.time() - _last_call_ts
    if elapsed < 12:
        wait = 12 - elapsed
        logger.debug("Rate-limiting Alpha Vantage: sleeping %.1fs", wait)
        time.sleep(wait)
    _last_call_ts = time.time()


def _empty_result(ticker: str) -> dict[str, Any]:
    """Return a safe fallback when the API call fails."""
    return {
        "ticker": ticker,
        "price": 0.0,
        "previous_close": 0.0,
        "change_pct": 0.0,
        "volatility_label": "unknown",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def clear_cache() -> None:
    """Flush the in-memory cache (useful between pipeline runs)."""
    _cache.clear()
