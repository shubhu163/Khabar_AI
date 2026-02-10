"""
Khabar AI — Main Orchestrator
==================================================
This is the entry-point for every pipeline run (invoked by GitHub Actions
cron or manually via ``python -m app.main``).

PIPELINE FLOW (per company)
  1. **Ingest** — News Sensor fetches last-hour headlines.
  2. **Triage** — Each headline is passed through the Triage Agent
     (Groq/Llama 3.1 70B).  ~70-90 % of articles are filtered out.
  3. **Enrich** — For articles that pass triage, the Finance Sensor
     and Weather Sensor fetch contextual signals.
  4. **Analyse** — The Analyst Agent (OpenRouter/DeepSeek R1) receives
     the correlated signals and produces a structured risk assessment.
  5. **Act** — The alert manager deduplicates and stores the event.
     RED-severity events trigger immediate notifications.

RESILIENCE
  • Each sensor is wrapped in try/except so a single API failure
    doesn't crash the whole run.
  • Exponential back-off is applied to retryable HTTP errors.
  • A final summary is logged so operators can quickly see what
    happened in the GitHub Actions log.
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Bootstrap logging before anything else
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("khabar")

# ---------------------------------------------------------------------------
# Application imports (after logging is configured)
# ---------------------------------------------------------------------------
from app.action_layer.alert_manager import (
    mark_notified,
    record_alert,
    should_notify_immediately,
    store_risk_event,
)
from app.action_layer.notifiers import dispatch_alert
from app.agents.analyst_agent import analyse_risk
from app.agents.knowledge_graph import SupplyChainGraph
from app.agents.triage_agent import triage_batch
from app.config import get_settings, get_target_companies
from app.database import get_db, init_db
from app.sensors.finance_sensor import clear_cache as clear_finance_cache
from app.sensors.finance_sensor import fetch_stock_data
from app.sensors.news_sensor import fetch_news
from app.sensors.weather_sensor import clear_cache as clear_weather_cache
from app.sensors.weather_sensor import fetch_weather


# ---------------------------------------------------------------------------
# Main orchestrator class
# ---------------------------------------------------------------------------
class RiskMonitor:
    """
    Coordinates the full sensor → triage → analyst → action pipeline
    for all configured companies.
    """

    def __init__(self, company_names: list[str] | None = None) -> None:
        self.settings = get_settings()
        all_companies = get_target_companies()

        if company_names:
            # Filter to only the companies the user asked for.
            # Match case-insensitively against name or ticker.
            requested = {n.lower() for n in company_names}
            self.companies = [
                c for c in all_companies
                if c["name"].lower() in requested
                or c["ticker"].lower() in requested
            ]
            # If a name doesn't match any config entry, create a minimal
            # entry on the fly so the pipeline still runs for it.
            matched_names = {c["name"].lower() for c in self.companies}
            matched_tickers = {c["ticker"].lower() for c in self.companies}
            for name in company_names:
                if name.lower() not in matched_names and name.lower() not in matched_tickers:
                    self.companies.append({
                        "name": name,
                        "ticker": name.upper()[:4],
                        "supply_chain_nodes": [],
                        "risk_keywords": ["supply chain", "disruption"],
                    })
        else:
            self.companies = all_companies

        self.knowledge_graph = SupplyChainGraph()

        # Pipeline-run metrics
        self.stats: dict[str, int] = {
            "total_articles": 0,
            "triaged_passed": 0,
            "events_stored": 0,
            "duplicates_skipped": 0,
            "alerts_sent": 0,
            "errors": 0,
        }

    # ------------------------------------------------------------------
    # Entry-point
    # ------------------------------------------------------------------
    def run(self) -> dict[str, int]:
        """
        Execute the full pipeline and return summary statistics.
        """
        start = time.time()
        logger.info("=" * 60)
        logger.info("Khabar AI — Pipeline Run")
        logger.info("Mode: %s", "DRY RUN" if self.settings.dry_run else "LIVE")
        logger.info("Companies: %d", len(self.companies))
        logger.info("=" * 60)

        # Initialise database tables (idempotent)
        init_db()

        # Build the baseline knowledge graph from config
        self.knowledge_graph.build_from_config(self.companies)

        # Clear per-run caches so each hourly window starts fresh
        clear_finance_cache()
        clear_weather_cache()

        # Process each company
        for company in self.companies:
            try:
                self._process_company(company)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Fatal error processing %s: %s", company["name"], exc, exc_info=True
                )
                self.stats["errors"] += 1

        elapsed = time.time() - start
        self._log_summary(elapsed)
        return self.stats

    # ------------------------------------------------------------------
    # Per-company pipeline
    # ------------------------------------------------------------------
    def _process_company(self, company: dict[str, Any]) -> None:
        name = company["name"]
        ticker = company["ticker"]
        keywords = company.get("risk_keywords", [])
        nodes = company.get("supply_chain_nodes", [])

        logger.info("— Processing: %s (%s)", name, ticker)

        # STEP 1: Fetch news
        articles = fetch_news(name, keywords)
        self.stats["total_articles"] += len(articles)
        if not articles:
            logger.info("  No articles found for %s — skipping.", name)
            return

        # STEP 2: Triage
        relevant = triage_batch(name, articles)
        self.stats["triaged_passed"] += len(relevant)
        if not relevant:
            logger.info("  All articles filtered out for %s.", name)
            return

        # STEP 3 & 4: Enrich + Analyse each relevant article
        # Fetch stock data once per company (it doesn't change per article)
        stock_data = self._safe_fetch_stock(ticker)

        for article in relevant:
            self._analyse_and_store(
                company_name=name,
                article=article,
                stock_data=stock_data,
                nodes=nodes,
            )

        # Persist knowledge-graph edges for this company
        with get_db() as db:
            self.knowledge_graph.persist_edges(db, name)

    # ------------------------------------------------------------------
    # Analyse a single article against all supply-chain nodes
    # ------------------------------------------------------------------
    def _analyse_and_store(
        self,
        company_name: str,
        article: dict[str, Any],
        stock_data: dict[str, Any],
        nodes: list[dict[str, Any]],
    ) -> None:
        headline = article["title"]
        summary = article.get("description", "")
        source_url = article.get("url", "")
        volatility = stock_data.get("change_pct", 0.0)

        # Pick the most relevant supply-chain node (simplified: use the first)
        # A production system would use NER to match the article to a specific node.
        node = nodes[0] if nodes else {"location": "Unknown", "type": "unknown", "coordinates": [0, 0]}
        coords = node.get("coordinates", [0, 0])

        # Fetch weather for that node
        weather = self._safe_fetch_weather(
            coords[0], coords[1], node.get("location", "")
        )

        # Run the Analyst Agent
        assessment = analyse_risk(
            company_name=company_name,
            node_location=node.get("location", "Unknown"),
            node_type=node.get("type", "unknown"),
            headline=headline,
            summary=summary,
            volatility=volatility,
            weather_description=weather.get("description", "unknown"),
            weather_severity=weather.get("severity_label", "unknown"),
        )

        # Add event to knowledge graph
        event_label = f"News: {headline[:50]}…"
        self.knowledge_graph.add_event(
            event_label, node.get("location", "Unknown")
        )

        # Store in database (with dedup)
        with get_db() as db:
            event = store_risk_event(
                db=db,
                company_name=company_name,
                headline=headline,
                source_url=source_url,
                stock_impact=volatility,
                weather_correlation=weather.get("description"),
                assessment=assessment,
            )

            if event is None:
                self.stats["duplicates_skipped"] += 1
                return

            self.stats["events_stored"] += 1

            # Dispatch alerts for RED-severity events
            if should_notify_immediately(event):
                channels = dispatch_alert(event)
                for ch in channels:
                    record_alert(db, event.id, ch, "sent")
                mark_notified(db, event)
                self.stats["alerts_sent"] += len(channels)

    # ------------------------------------------------------------------
    # Safe wrappers (graceful degradation)
    # ------------------------------------------------------------------
    def _safe_fetch_stock(self, ticker: str) -> dict[str, Any]:
        try:
            return fetch_stock_data(ticker)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Stock fetch failed for %s: %s", ticker, exc)
            self.stats["errors"] += 1
            return {"ticker": ticker, "change_pct": 0.0, "volatility_label": "unknown"}

    def _safe_fetch_weather(
        self, lat: float, lon: float, location: str
    ) -> dict[str, Any]:
        try:
            return fetch_weather(lat, lon, location)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Weather fetch failed for %s: %s", location, exc)
            self.stats["errors"] += 1
            return {"description": "unknown", "severity_label": "unknown"}

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    def _log_summary(self, elapsed: float) -> None:
        s = self.stats
        noise_reduction = 0.0
        if s["total_articles"] > 0:
            noise_reduction = (
                (s["total_articles"] - s["triaged_passed"]) / s["total_articles"]
            ) * 100

        logger.info("=" * 60)
        logger.info("PIPELINE SUMMARY")
        logger.info("  Duration:           %.1f s", elapsed)
        logger.info("  Total articles:     %d", s["total_articles"])
        logger.info("  Passed triage:      %d", s["triaged_passed"])
        logger.info("  Noise reduction:    %.1f%%", noise_reduction)
        logger.info("  Events stored:      %d", s["events_stored"])
        logger.info("  Duplicates skipped: %d", s["duplicates_skipped"])
        logger.info("  Alerts dispatched:  %d", s["alerts_sent"])
        logger.info("  Errors:             %d", s["errors"])
        logger.info("=" * 60)


# ---------------------------------------------------------------------------
# CLI entry-point
# ---------------------------------------------------------------------------
def main() -> None:
    """
    Run the pipeline.

    Usage:
        python -m app.main                          # all companies from config
        python -m app.main "Tesla Inc" "Apple Inc"   # specific companies only
        python -m app.main TSLA AAPL NVDA            # by ticker also works
    """
    import sys

    company_names = sys.argv[1:] if len(sys.argv) > 1 else None
    monitor = RiskMonitor(company_names=company_names)
    monitor.run()


if __name__ == "__main__":
    main()
