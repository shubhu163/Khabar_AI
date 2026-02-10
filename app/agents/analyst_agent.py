"""
Khabar AI — Analyst Agent
==============================================
ROLE:  Deep-reasoning agent that correlates multiple signals (news,
       stock movement, weather) and produces a structured risk
       assessment with severity, impact estimate, and mitigation
       strategies.

MODEL: OpenAI GPT-OSS 120B via Groq  (120B parameters, reasoning
       capabilities, ~500 tokens/sec).

WHY THIS MODEL?
  • GPT-OSS 120B is the largest and most capable model on Groq —
    120 billion parameters with built-in reasoning capabilities.
  • Produces high-quality structured JSON and multi-step analysis,
    ideal for correlating news + stock + weather signals.
  • Hosted on Groq (same provider as the Triage Agent), so only
    one API key is needed.
  • 128K context window, 64K max completion tokens.
  • To use a different model, just change _MODEL to any model ID
    listed at https://console.groq.com/docs/models

OUTPUT CONTRACT
  The agent is prompted to return valid JSON matching:
  {
    "severity": "RED|YELLOW|GREEN",
    "impact_estimate": "...",
    "reasoning": "...",
    "mitigation_strategies": ["...", "...", "..."],
    "confidence_score": 0-100
  }
  We validate this with a Pydantic model before storing.

DRY-RUN MODE
  Returns a plausible mock analysis so downstream components
  (database, dashboard) can be exercised without API calls.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx
from pydantic import BaseModel, Field, field_validator

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "openai/gpt-oss-120b"

_SYSTEM_PROMPT = (
    "You are a Senior Supply Chain Risk Consultant. You correlate "
    "multi-source signals (news, stock movement, weather) and produce "
    "a structured risk assessment. Always respond in valid JSON."
)

_USER_TEMPLATE = """Analyze the following correlated signals:

COMPANY: {company_name}
SUPPLY CHAIN NODE: {node_location} ({node_type})
NEWS: {headline} - {summary}
STOCK MOVEMENT: {volatility}% change in last trading session
WEATHER CONDITIONS: {weather_description} (severity: {weather_severity})

TASK:
1. Correlate these signals and estimate business impact (Revenue at risk, timeline)
2. Assess severity: HIGH (RED), MEDIUM (YELLOW), or LOW (GREEN)
3. Provide reasoning in 2-3 sentences
4. Suggest 3 mitigation strategies

Respond ONLY with valid JSON (no markdown fences, no extra text):
{{
  "severity": "RED|YELLOW|GREEN",
  "impact_estimate": "string",
  "reasoning": "string",
  "mitigation_strategies": ["string", "string", "string"],
  "confidence_score": 0-100
}}"""


# ---------------------------------------------------------------------------
# Pydantic validation model for the LLM response
# ---------------------------------------------------------------------------
class RiskAssessment(BaseModel):
    """Validated risk assessment from the Analyst Agent."""

    severity: str = Field(..., pattern=r"^(RED|YELLOW|GREEN)$")
    impact_estimate: str
    reasoning: str
    mitigation_strategies: list[str] = Field(..., min_length=1)
    confidence_score: float = Field(..., ge=0, le=100)

    @field_validator("severity", mode="before")
    @classmethod
    def normalise_severity(cls, v: str) -> str:
        return v.strip().upper()


# ---------------------------------------------------------------------------
# Mock response
# ---------------------------------------------------------------------------
_MOCK_ASSESSMENT = RiskAssessment(
    severity="YELLOW",
    impact_estimate="Potential 5-10% revenue impact over next quarter if disruption persists.",
    reasoning=(
        "The news headline indicates a moderate supply-chain concern. "
        "Stock movement is within normal range, and weather conditions "
        "do not exacerbate the situation. Monitor closely."
    ),
    mitigation_strategies=[
        "Engage secondary supplier for critical components.",
        "Increase safety stock at regional distribution centres.",
        "Activate business continuity communication plan with key stakeholders.",
    ],
    confidence_score=62.0,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def analyse_risk(
    company_name: str,
    node_location: str,
    node_type: str,
    headline: str,
    summary: str,
    volatility: float,
    weather_description: str,
    weather_severity: str,
) -> RiskAssessment:
    """
    Run the Analyst Agent on a set of correlated signals.

    Returns a validated ``RiskAssessment`` or a sensible fallback.
    """
    settings = get_settings()

    if settings.dry_run or not settings.groq_api_key:
        logger.info("[DRY RUN] Returning mock analysis for '%s'", headline[:60])
        return _MOCK_ASSESSMENT

    user_msg = _USER_TEMPLATE.format(
        company_name=company_name,
        node_location=node_location,
        node_type=node_type,
        headline=headline,
        summary=summary,
        volatility=volatility,
        weather_description=weather_description,
        weather_severity=weather_severity,
    )

    payload = {
        "model": _MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.3,     # low temp for consistent structured output
        "max_tokens": 1024,
    }

    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }

    try:
        import time
        time.sleep(2.5)  # Groq free tier: 30 RPM — space out calls
        with httpx.Client(timeout=60) as client:
            resp = client.post(_GROQ_URL, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        raw_content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        # LLMs sometimes wrap JSON in ```json … ``` — strip that
        raw_content = _strip_code_fences(raw_content)

        parsed = json.loads(raw_content)
        assessment = RiskAssessment(**parsed)

        logger.info(
            "Analyst [%s]: severity=%s, confidence=%.0f",
            company_name,
            assessment.severity,
            assessment.confidence_score,
        )
        return assessment

    except (json.JSONDecodeError, Exception) as exc:
        logger.error("Analyst agent error: %s", exc)
        # Return a conservative YELLOW so the event is still recorded
        return RiskAssessment(
            severity="YELLOW",
            impact_estimate="Unable to fully assess — manual review recommended.",
            reasoning=f"Automated analysis encountered an error: {exc}",
            mitigation_strategies=[
                "Escalate to human analyst for manual review.",
                "Monitor news feed for follow-up developments.",
                "Review supply-chain contingency plans.",
            ],
            confidence_score=20.0,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _strip_code_fences(text: str) -> str:
    """Remove markdown code fences that LLMs sometimes add around JSON."""
    # Match ```json ... ``` or ``` ... ```
    pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
    match = re.search(pattern, text)
    if match:
        return match.group(1)
    return text
