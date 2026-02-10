"""
Khabar AI — Continuous Monitor Daemon
======================================
Runs the risk-assessment pipeline on a schedule for a predefined
watchlist of companies.  Start alongside the dashboard:

    python monitor.py              # default: every 60 min
    python monitor.py --interval 30  # every 30 min
    python monitor.py --once        # single run then exit (good for demos)

The daemon writes a small JSON status file (monitor_status.json) so the
Streamlit dashboard can display live monitoring info without coupling.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("khabar.monitor")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
# Companies to auto-monitor.  Edit this list to expand coverage.
WATCHLIST: list[str] = [
    "Apple Inc",
]

STATUS_FILE = Path(__file__).resolve().parent / "monitor_status.json"

# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def _write_status(
    state: str,
    last_run: str | None = None,
    next_run: str | None = None,
    companies: list[str] | None = None,
    last_result: dict | None = None,
    error: str | None = None,
) -> None:
    """Persist a small JSON file the dashboard can read."""
    payload = {
        "state": state,
        "watchlist": companies or WATCHLIST,
        "interval_min": _interval_min,
        "last_run": last_run,
        "next_run": next_run,
        "last_result": last_result,
        "error": error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    STATUS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


_interval_min: int = 60  # updated at parse time


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_cycle() -> dict:
    """Execute one full pipeline cycle for the watchlist."""
    from app.main import RiskMonitor

    logger.info("=" * 60)
    logger.info("MONITOR CYCLE — analysing %s", ", ".join(WATCHLIST))
    logger.info("=" * 60)

    monitor = RiskMonitor(company_names=WATCHLIST)
    stats = monitor.run()

    logger.info(
        "Cycle complete — %d articles, %d passed triage, %d events stored",
        stats.get("total_articles", 0),
        stats.get("triaged_passed", 0),
        stats.get("events_stored", 0),
    )
    return stats


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    global _interval_min

    parser = argparse.ArgumentParser(description="Khabar AI — Continuous Monitor")
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Minutes between each pipeline run (default: 60)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single cycle then exit (useful for demos)",
    )
    args = parser.parse_args()
    _interval_min = args.interval

    logger.info("Khabar AI Monitor starting")
    logger.info("  Watchlist : %s", ", ".join(WATCHLIST))
    logger.info("  Interval  : %d min%s", _interval_min, " (once)" if args.once else "")

    _write_status("starting", companies=WATCHLIST)

    while True:
        now = datetime.now(timezone.utc)
        _write_status("running", last_run=now.isoformat(), companies=WATCHLIST)

        try:
            stats = run_cycle()
            next_at = datetime.now(timezone.utc).isoformat() if args.once else None
            if not args.once:
                from datetime import timedelta
                next_at = (datetime.now(timezone.utc) + timedelta(minutes=_interval_min)).isoformat()

            _write_status(
                "idle",
                last_run=now.isoformat(),
                next_run=next_at,
                companies=WATCHLIST,
                last_result=stats,
            )
        except Exception as exc:
            logger.exception("Monitor cycle failed: %s", exc)
            _write_status(
                "error",
                last_run=now.isoformat(),
                companies=WATCHLIST,
                error=str(exc),
            )

        if args.once:
            logger.info("Single-run mode — exiting.")
            break

        logger.info("Sleeping %d minutes until next cycle...", _interval_min)
        time.sleep(_interval_min * 60)


if __name__ == "__main__":
    main()
