"""
Khabar AI — Notification Dispatchers
=========================================================
Console notifier — prints formatted alerts to stdout when
RED-severity events are detected.
"""

from __future__ import annotations

import json
import logging

from app.models import RiskEvent

logger = logging.getLogger(__name__)

_SEVERITY_ICON = {"RED": "🔴", "YELLOW": "🟡", "GREEN": "🟢"}


def _format_console_text(event: RiskEvent) -> str:
    """Plain-text format for console/log output."""
    icon = _SEVERITY_ICON.get(event.severity, "⚪")
    strategies = ""
    if event.mitigation_strategies:
        try:
            items = json.loads(event.mitigation_strategies)
            strategies = "\n".join(f"  • {s}" for s in items)
        except json.JSONDecodeError:
            strategies = event.mitigation_strategies

    return (
        f"{icon} RISK ALERT — {event.severity}\n"
        f"Company:    {event.company_name}\n"
        f"Headline:   {event.headline}\n"
        f"Impact:     {event.impact_estimate or 'N/A'}\n"
        f"Confidence: {event.confidence_score or 0:.0f}%\n"
        f"Mitigation:\n{strategies}\n"
        f"Source:     {event.source_url or 'N/A'}"
    )


def send_console(event: RiskEvent) -> bool:
    """Print a formatted alert to stdout / log."""
    text = _format_console_text(event)
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60 + "\n")
    logger.info("Console alert dispatched for event id=%d", event.id)
    return True


def dispatch_alert(event: RiskEvent) -> list[str]:
    """Send the alert through all configured channels."""
    succeeded: list[str] = []

    if send_console(event):
        succeeded.append("console")

    return succeeded
