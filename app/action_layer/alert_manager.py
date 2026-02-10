"""
Khabar AI — Alert Manager
==============================================
Responsible for:
  1. **Deduplication** — the same story from multiple publishers must
     not create duplicate risk events.
  2. **Persistence** — validated risk assessments are stored as
     ``RiskEvent`` rows in the database.
  3. **Dispatch routing** — RED severity → immediate notification;
     YELLOW/GREEN → batched for daily digest.

DEDUPLICATION STRATEGY
  We hash the headline (SHA-256 of lowered, stripped text) and enforce
  a UNIQUE constraint on ``headline_hash``.  Before inserting, we
  check if that hash already exists within the last 24 hours.
  This handles:
    • Exact duplicates from successive polling windows.
    • Near-duplicates from different publishers (not perfect, but
      good enough for an MVP — a future improvement would be to use
      sentence-embedding similarity instead of exact hash).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.agents.analyst_agent import RiskAssessment
from app.models import AlertHistory, RiskEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def store_risk_event(
    db: Session,
    company_name: str,
    headline: str,
    source_url: str,
    stock_impact: float | None,
    weather_correlation: str | None,
    assessment: RiskAssessment,
    event_type: str = "supply_chain",
) -> RiskEvent | None:
    """
    Deduplicate and store a risk event.

    Returns
    -------
    RiskEvent | None
        The persisted event, or ``None`` if it was a duplicate.
    """
    headline_hash = RiskEvent.compute_headline_hash(headline)

    # --- Dedup check: same headline within the last 24 h ---
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    existing = (
        db.query(RiskEvent)
        .filter(
            RiskEvent.headline_hash == headline_hash,
            RiskEvent.created_at >= cutoff,
        )
        .first()
    )
    if existing:
        logger.info("Duplicate detected (id=%d) — skipping: %s", existing.id, headline[:60])
        return None

    # --- Build the ORM object ---
    event = RiskEvent(
        company_name=company_name,
        event_type=event_type,
        severity=assessment.severity,
        headline=headline,
        headline_hash=headline_hash,
        source_url=source_url,
        stock_impact=stock_impact,
        weather_correlation=weather_correlation,
        ai_reasoning=assessment.reasoning,
        impact_estimate=assessment.impact_estimate,
        mitigation_strategies=json.dumps(assessment.mitigation_strategies),
        confidence_score=assessment.confidence_score,
        is_notified=False,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    logger.info(
        "Stored RiskEvent id=%d [%s] for %s: %s",
        event.id, event.severity, company_name, headline[:60],
    )
    return event


def should_notify_immediately(event: RiskEvent) -> bool:
    """RED-severity events trigger immediate notification."""
    return event.severity == "RED"


def record_alert(
    db: Session,
    risk_event_id: int,
    channel: str,
    status: str = "sent",
) -> AlertHistory:
    """
    Write an audit record after dispatching a notification.
    """
    alert = AlertHistory(
        risk_event_id=risk_event_id,
        alert_channel=channel,
        status=status,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def mark_notified(db: Session, event: RiskEvent) -> None:
    """Flag the event so we don't re-notify on the next run."""
    event.is_notified = True
    db.commit()


def get_pending_events(db: Session, severity: str | None = None) -> list[RiskEvent]:
    """
    Return all events that haven't been notified yet.

    Optionally filter by severity.
    """
    query = db.query(RiskEvent).filter(RiskEvent.is_notified == False)  # noqa: E712
    if severity:
        query = query.filter(RiskEvent.severity == severity)
    return query.order_by(RiskEvent.created_at.desc()).all()


def get_recent_events(
    db: Session,
    hours: int = 24,
    company_name: str | None = None,
) -> list[RiskEvent]:
    """
    Fetch events from the last *hours* hours, optionally for one company.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    query = db.query(RiskEvent).filter(RiskEvent.created_at >= cutoff)
    if company_name:
        query = query.filter(RiskEvent.company_name == company_name)
    return query.order_by(RiskEvent.created_at.desc()).all()
