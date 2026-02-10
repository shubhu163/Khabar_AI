"""
Khabar AI — Seed Data Script
=================================================
Pre-populates the database with 3 example risk events so the Streamlit
dashboard looks impressive on first load — even before real API keys
are configured.

RUN:  python seed_data.py

These examples demonstrate the three severity levels and cover multiple
companies, giving recruiters a clear picture of what the system does.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone

# Ensure the project root is on sys.path
sys.path.insert(0, ".")

from app.database import get_db, init_db
from app.models import KnowledgeGraphEdge, RiskEvent


def seed() -> None:
    """Insert demo risk events and knowledge-graph edges."""
    init_db()

    events = [
        # --- RED: TSMC Typhoon Alert for Apple ---
        RiskEvent(
            company_name="Apple Inc",
            event_type="weather_disruption",
            severity="RED",
            headline="TSMC Factory in Taiwan — Typhoon Alert Forces Production Halt",
            headline_hash=RiskEvent.compute_headline_hash(
                "TSMC Factory in Taiwan — Typhoon Alert Forces Production Halt"
            ),
            source_url="https://example.com/tsmc-typhoon-alert",
            stock_impact=-4.2,
            weather_correlation="Typhoon Gaemi — Category 3, direct path over Tainan",
            ai_reasoning=(
                "Typhoon Gaemi is on a direct trajectory toward TSMC's Tainan fab, "
                "which produces ~30% of Apple's A-series chips. Historical data shows "
                "similar typhoons have caused 3-5 day production halts. Combined with "
                "a 4.2% stock decline, this indicates high supply-chain risk."
            ),
            impact_estimate=(
                "Estimated $2-4B revenue at risk over the next quarter if production "
                "halt exceeds 5 days. iPhone 16 launch timeline may shift by 2-3 weeks."
            ),
            mitigation_strategies=json.dumps([
                "Activate secondary semiconductor sourcing from Samsung Foundry.",
                "Pre-position emergency logistics to reroute shipments via air freight.",
                "Engage crisis communication team to manage investor expectations.",
            ]),
            confidence_score=87.0,
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
            is_notified=True,
        ),
        # --- YELLOW: Foxconn Labor Dispute for Apple ---
        RiskEvent(
            company_name="Apple Inc",
            event_type="labor_disruption",
            severity="YELLOW",
            headline="Foxconn Workers in Shenzhen Stage Walkout Over Overtime Policies",
            headline_hash=RiskEvent.compute_headline_hash(
                "Foxconn Workers in Shenzhen Stage Walkout Over Overtime Policies"
            ),
            source_url="https://example.com/foxconn-labor-dispute",
            stock_impact=-1.8,
            weather_correlation="Clear skies, 28°C — no weather factor",
            ai_reasoning=(
                "A partial walkout at Foxconn's Longhua campus affects approximately "
                "15% of the iPhone assembly workforce. Management is negotiating, and "
                "similar disputes in 2022 were resolved within 48 hours. Stock impact "
                "is moderate at -1.8%, suggesting the market views this as containable."
            ),
            impact_estimate=(
                "Potential 1-2 day assembly delay affecting ~200K units. Revenue "
                "impact estimated at $150-300M if extended beyond one week."
            ),
            mitigation_strategies=json.dumps([
                "Monitor negotiation progress hourly via on-site liaisons.",
                "Prepare to shift production allocation to Foxconn's Zhengzhou facility.",
                "Review and pre-approve overtime policy concessions with legal team.",
            ]),
            confidence_score=72.0,
            created_at=datetime.now(timezone.utc) - timedelta(hours=6),
            is_notified=False,
        ),
        # --- GREEN: Port of LA Strike Ends for NVIDIA ---
        RiskEvent(
            company_name="NVIDIA Corporation",
            event_type="logistics_resolution",
            severity="GREEN",
            headline="Port of Los Angeles Dockworkers Reach Agreement — Strike Ends",
            headline_hash=RiskEvent.compute_headline_hash(
                "Port of Los Angeles Dockworkers Reach Agreement — Strike Ends"
            ),
            source_url="https://example.com/port-la-strike-ends",
            stock_impact=2.1,
            weather_correlation="Clear conditions at Port of LA",
            ai_reasoning=(
                "The Port of LA strike that disrupted GPU shipment logistics for 8 "
                "days has ended with a new labor agreement. Backlog clearing is expected "
                "within 3-5 business days. NVDA stock responded positively (+2.1%), "
                "confirming market relief. No further action required."
            ),
            impact_estimate=(
                "Backlog of ~$800M in GPU shipments will clear within 5 days. "
                "Quarterly revenue targets remain on track."
            ),
            mitigation_strategies=json.dumps([
                "Expedite priority shipments for data-center customers with SLA breaches.",
                "Conduct post-incident review to diversify port dependencies.",
                "Update logistics contingency plans with lessons learned.",
            ]),
            confidence_score=91.0,
            created_at=datetime.now(timezone.utc) - timedelta(hours=12),
            is_notified=True,
        ),
    ]

    # Knowledge-graph edges
    edges = [
        # Apple supply chain
        KnowledgeGraphEdge(
            source_node="Shenzhen, China",
            target_node="Foxconn",
            relationship_type="manufactures_at (manufacturing)",
            company="Apple Inc",
        ),
        KnowledgeGraphEdge(
            source_node="Foxconn",
            target_node="Apple Inc",
            relationship_type="supplies",
            company="Apple Inc",
        ),
        KnowledgeGraphEdge(
            source_node="Tainan, Taiwan",
            target_node="TSMC",
            relationship_type="manufactures_at (semiconductor)",
            company="Apple Inc",
        ),
        KnowledgeGraphEdge(
            source_node="TSMC",
            target_node="Apple Inc",
            relationship_type="supplies",
            company="Apple Inc",
        ),
        # NVIDIA supply chain
        KnowledgeGraphEdge(
            source_node="Taipei, Taiwan",
            target_node="TSMC",
            relationship_type="manufactures_at (semiconductor)",
            company="NVIDIA Corporation",
        ),
        KnowledgeGraphEdge(
            source_node="TSMC",
            target_node="NVIDIA Corporation",
            relationship_type="supplies",
            company="NVIDIA Corporation",
        ),
        # Event nodes
        KnowledgeGraphEdge(
            source_node="Typhoon Gaemi",
            target_node="Tainan, Taiwan",
            relationship_type="affects",
            company="Apple Inc",
        ),
        KnowledgeGraphEdge(
            source_node="Labor Dispute",
            target_node="Shenzhen, China",
            relationship_type="affects",
            company="Apple Inc",
        ),
    ]

    with get_db() as db:
        inserted_events = 0
        for event in events:
            # Check for existing (dedup)
            existing = (
                db.query(RiskEvent)
                .filter(RiskEvent.headline_hash == event.headline_hash)
                .first()
            )
            if not existing:
                db.add(event)
                inserted_events += 1

        inserted_edges = 0
        for edge in edges:
            existing = (
                db.query(KnowledgeGraphEdge)
                .filter_by(
                    source_node=edge.source_node,
                    target_node=edge.target_node,
                    relationship_type=edge.relationship_type,
                    company=edge.company,
                )
                .first()
            )
            if not existing:
                db.add(edge)
                inserted_edges += 1

        db.commit()

    print(f"Seed complete: {inserted_events} events, {inserted_edges} graph edges inserted.")


if __name__ == "__main__":
    seed()
