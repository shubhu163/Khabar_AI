"""
Khabar AI — Triage Agent
=============================================
ROLE:  Fast, binary YES/NO filter that decides whether a news headline
       is relevant to a company's supply-chain risk profile.

MODEL: Llama 3.1 70B via Groq  (ultra-low latency, ~200 ms per call).

WHY A SEPARATE TRIAGE STEP?
  • NewsAPI returns broad results; many are marketing fluff, opinion
    pieces, or tangentially related.  Sending *all* of them to the
    expensive Analyst Agent (DeepSeek R1) would waste tokens and money.
  • The Triage Agent is the "99% noise filter" — only articles it
    approves move downstream, dramatically reducing cost and latency.
  • Using a smaller/faster model for binary classification is a
    well-known agentic pattern ("cheap gate → expensive reasoner").

DRY-RUN MODE
  Returns ``True`` for ~30% of articles (simulates realistic filter).
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "llama-3.3-70b-versatile"

_SYSTEM_PROMPT = (
    "You are a fast triage assistant for a supply-chain risk monitoring system. "
    "Your ONLY job is to decide if a news article is directly relevant to "
    "supply-chain disruption, manufacturing delays, logistics problems, "
    "or significant financial risk for a specific company. "
    "Answer with a single word: YES or NO. No explanation."
)

_USER_TEMPLATE = """Analyze this news headline and summary for supply chain or financial risk relevance to {company_name}.

Headline: {headline}
Summary: {summary}

Is this directly relevant to supply chain disruption, manufacturing delays, or significant financial risk for {company_name}?
Answer ONLY with "YES" or "NO". No explanation."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def triage_article(
    company_name: str,
    headline: str,
    summary: str,
) -> bool:
    """
    Ask the Triage Agent whether *headline* is relevant.

    Parameters
    ----------
    company_name : str
    headline : str
    summary : str

    Returns
    -------
    bool
        ``True`` if the article should proceed to the Analyst Agent.
    """
    settings = get_settings()

    # --- Dry-run: deterministic pseudo-random based on headline hash ---
    if settings.dry_run or not settings.groq_api_key:
        # Use hash to get a deterministic but varied result (~30% pass rate)
        h = int(hashlib.md5(headline.encode()).hexdigest(), 16)
        result = (h % 10) < 3  # ~30 % pass
        logger.info(
            "[DRY RUN] Triage for '%s': %s", headline[:60], "YES" if result else "NO"
        )
        return result

    user_msg = _USER_TEMPLATE.format(
        company_name=company_name,
        headline=headline,
        summary=summary,
    )

    payload = {
        "model": _MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.0,  # deterministic for classification
        "max_tokens": 5,     # we only need "YES" or "NO"
    }

    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }

    try:
        import time
        time.sleep(2.5)  # Groq free tier: 30 RPM — space out calls
        with httpx.Client(timeout=30) as client:
            resp = client.post(_GROQ_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        answer = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
            .upper()
        )

        is_relevant = answer.startswith("YES")
        logger.info(
            "Triage [%s] '%s…' → %s",
            company_name,
            headline[:50],
            "YES" if is_relevant else "NO",
        )
        return is_relevant

    except httpx.HTTPStatusError as exc:
        logger.error("Groq API HTTP error: %s — %s", exc.response.status_code, exc.response.text)
        # Fail-open: let the article through so we don't miss a real risk
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error("Triage agent error: %s", exc)
        return True  # fail-open


def triage_batch(
    company_name: str,
    articles: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convenience wrapper — triage a list of article dicts and return
    only those that pass the filter.
    """
    passed: list[dict[str, Any]] = []
    for art in articles:
        if triage_article(company_name, art["title"], art.get("description", "")):
            passed.append(art)
    logger.info(
        "Triage batch: %d / %d articles passed for %s",
        len(passed), len(articles), company_name,
    )
    return passed
