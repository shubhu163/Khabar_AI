"""
Khabar AI — SQLAlchemy ORM Models
=====================================================
Three core tables:
  • RiskEvent           — every supply-chain risk detected by the pipeline
  • KnowledgeGraphEdge  — edges in the supply-chain knowledge graph
  • AlertHistory        — audit trail for every notification dispatched

WHY a headline_hash column?
  Deduplication.  NewsAPI can return the same story from different
  publishers or in successive polling windows.  We hash the headline
  and check before inserting so the dashboard never shows duplicates.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

# WHY declarative_base() instead of DeclarativeBase?
# DeclarativeBase was introduced in SQLAlchemy 2.0.  Using the factory
# function ensures compatibility with both 1.4.x and 2.x, which matters
# when the project is cloned onto machines with different system packages.
Base = declarative_base()


class RiskEvent(Base):
    """
    A single risk signal that passed triage and was analysed.

    Severity uses a traffic-light scheme:
      RED    — high impact, immediate action required
      YELLOW — moderate, monitor closely
      GREEN  — low / resolved
    """

    __tablename__ = "risk_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_name = Column(String(200), nullable=False, index=True)
    event_type = Column(String(100), nullable=False, default="supply_chain")
    severity = Column(String(10), nullable=False, default="GREEN")  # RED / YELLOW / GREEN
    headline = Column(Text, nullable=False)
    headline_hash = Column(String(64), nullable=False, unique=True, index=True)
    source_url = Column(Text, nullable=True)
    stock_impact = Column(Float, nullable=True)  # percentage change
    weather_correlation = Column(Text, nullable=True)
    ai_reasoning = Column(Text, nullable=True)
    impact_estimate = Column(Text, nullable=True)
    mitigation_strategies = Column(Text, nullable=True)  # JSON string
    confidence_score = Column(Float, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    is_notified = Column(Boolean, nullable=False, default=False)

    # Relationship to alert history
    alerts = relationship("AlertHistory", back_populates="risk_event", cascade="all, delete-orphan")

    # ------------------------------------------------------------------
    # Deduplication helper
    # ------------------------------------------------------------------
    @staticmethod
    def compute_headline_hash(headline: str) -> str:
        """
        SHA-256 of the lowered, stripped headline.

        WHY SHA-256?  It's deterministic, fast, and collision-resistant
        enough for dedup across ~100 events/day.
        """
        normalised = headline.strip().lower()
        return hashlib.sha256(normalised.encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        return f"<RiskEvent(id={self.id}, company={self.company_name}, severity={self.severity})>"


class KnowledgeGraphEdge(Base):
    """
    An edge in the supply-chain knowledge graph.

    Example edges:
      Weather("Typhoon")  → Location("Tainan, Taiwan")
      Location("Tainan")  → Supplier("TSMC")
      Supplier("TSMC")    → Company("Apple Inc")
    """

    __tablename__ = "knowledge_graph_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_node = Column(String(300), nullable=False)
    target_node = Column(String(300), nullable=False)
    relationship_type = Column(String(100), nullable=False)
    company = Column(String(200), nullable=False, index=True)
    confidence_score = Column(Float, nullable=True, default=1.0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "source_node", "target_node", "relationship_type", "company",
            name="uq_edge",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<KnowledgeGraphEdge({self.source_node} "
            f"--[{self.relationship_type}]--> {self.target_node})>"
        )


class AlertHistory(Base):
    """
    Audit log for every notification sent about a risk event.

    Channels: "slack", "telegram", "console"
    Status:   "sent", "failed", "pending"
    """

    __tablename__ = "alert_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    risk_event_id = Column(Integer, ForeignKey("risk_events.id"), nullable=False)
    alert_channel = Column(String(50), nullable=False)
    sent_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    status = Column(String(20), nullable=False, default="pending")

    risk_event = relationship("RiskEvent", back_populates="alerts")

    def __repr__(self) -> str:
        return f"<AlertHistory(id={self.id}, channel={self.alert_channel}, status={self.status})>"
