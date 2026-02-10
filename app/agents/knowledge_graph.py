"""
Khabar AI — Knowledge Graph Builder
=======================================================
Constructs and queries a simple directed graph that maps the causal
chain from external events down to business impact:

    Weather Event → Location → Supplier → Company
    News Event   → Supplier → Company

WHY A KNOWLEDGE GRAPH?
  • Supply chains are inherently *graph-shaped*: one supplier (TSMC)
    feeds multiple companies (Apple, NVIDIA, AMD).
  • A graph lets us answer questions like "which companies are affected
    if a typhoon hits Tainan?" in O(edges) time.
  • The graph is persisted to the database via ``KnowledgeGraphEdge``
    and visualised in the Streamlit dashboard with ``networkx`` + ``pyvis``.

DESIGN CHOICES
  • We use ``networkx.DiGraph`` as the in-memory representation because
    it ships with rich traversal algorithms and integrates cleanly with
    pyvis for interactive HTML visualisation.
  • Edges are upserted (INSERT … ON CONFLICT DO NOTHING) so the graph
    grows idempotently across pipeline runs.
"""

from __future__ import annotations

import logging
from typing import Any

import networkx as nx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import KnowledgeGraphEdge

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------
class SupplyChainGraph:
    """
    In-memory directed graph of supply-chain relationships.

    Typical node types:
      • "company"    — Apple Inc, NVIDIA
      • "supplier"   — Foxconn, TSMC
      • "location"   — Shenzhen, Tainan
      • "event"      — Typhoon, Strike, Shortage
    """

    def __init__(self) -> None:
        self.graph = nx.DiGraph()

    # ------------------------------------------------------------------
    # Build from YAML config
    # ------------------------------------------------------------------
    def build_from_config(self, companies: list[dict[str, Any]]) -> None:
        """
        Populate the graph from the parsed ``companies.yaml`` config.

        Creates edges:
          Location → Supplier (manufactures_at)
          Supplier → Company  (supplies)
        """
        for company in companies:
            company_name = company["name"]
            self.graph.add_node(company_name, type="company")

            for node in company.get("supply_chain_nodes", []):
                supplier = node["entity"]
                location = node["location"]
                node_type = node.get("type", "unknown")

                self.graph.add_node(supplier, type="supplier")
                self.graph.add_node(location, type="location")

                self.graph.add_edge(
                    location, supplier,
                    relationship=f"manufactures_at ({node_type})",
                )
                self.graph.add_edge(
                    supplier, company_name,
                    relationship="supplies",
                )

        logger.info(
            "Knowledge graph built: %d nodes, %d edges",
            self.graph.number_of_nodes(),
            self.graph.number_of_edges(),
        )

    # ------------------------------------------------------------------
    # Add event nodes (called during pipeline execution)
    # ------------------------------------------------------------------
    def add_event(
        self,
        event_label: str,
        location: str,
        event_type: str = "event",
        severity: str = "",
    ) -> None:
        """
        Attach an event node (e.g. "Typhoon Gaemi") to its location.

        Edge: Event → Location (affects)
        """
        self.graph.add_node(event_label, type=event_type, severity=severity)
        self.graph.add_edge(event_label, location, relationship="affects")

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------
    def companies_affected_by_location(self, location: str) -> list[str]:
        """
        Return company names reachable from *location* via the graph.
        """
        if location not in self.graph:
            return []
        reachable = nx.descendants(self.graph, location)
        return [
            n for n in reachable
            if self.graph.nodes[n].get("type") == "company"
        ]

    def get_supply_chain_for_company(self, company_name: str) -> list[dict[str, Any]]:
        """
        Return all upstream nodes (suppliers + locations) for a company.
        """
        if company_name not in self.graph:
            return []
        predecessors = nx.ancestors(self.graph, company_name)
        result = []
        for node in predecessors:
            result.append({
                "node": node,
                "type": self.graph.nodes[node].get("type", "unknown"),
            })
        return result

    # ------------------------------------------------------------------
    # Persist to database
    # ------------------------------------------------------------------
    def persist_edges(self, db: Session, company_name: str) -> int:
        """
        Upsert all edges related to *company_name* into the database.

        Returns the number of edges written.
        """
        count = 0
        for source, target, data in self.graph.edges(data=True):
            relationship = data.get("relationship", "related_to")

            # Check for existing edge to avoid unique-constraint violation
            existing = (
                db.query(KnowledgeGraphEdge)
                .filter_by(
                    source_node=source,
                    target_node=target,
                    relationship_type=relationship,
                    company=company_name,
                )
                .first()
            )
            if existing:
                continue

            edge = KnowledgeGraphEdge(
                source_node=source,
                target_node=target,
                relationship_type=relationship,
                company=company_name,
                confidence_score=1.0,
            )
            db.add(edge)
            count += 1

        if count:
            db.commit()
            logger.info("Persisted %d new graph edges for %s", count, company_name)

        return count

    # ------------------------------------------------------------------
    # Export for visualisation
    # ------------------------------------------------------------------
    def to_pyvis_html(self, output_path: str = "knowledge_graph.html") -> str:
        """
        Render the graph as an interactive HTML file using pyvis.

        Returns the output path.
        """
        from pyvis.network import Network

        net = Network(
            height="600px",
            width="100%",
            directed=True,
            bgcolor="#0e1117",
            font_color="white",
        )

        # Color mapping by node type
        _colors = {
            "company": "#3B82F6",   # blue — neutral, authoritative
            "supplier": "#4ECDC4",  # teal
            "location": "#A78BFA",  # soft purple
            "event": "#FFA07A",     # orange (fallback)
            "risk_event": "#FFA07A",  # orange (fallback)
        }

        # Severity-specific colors for risk events
        _severity_colors = {
            "RED": "#EF4444",       # red — critical
            "YELLOW": "#F59E0B",    # amber — moderate
            "GREEN": "#10B981",     # green — low risk
        }

        _sizes = {
            "company": 30,
            "supplier": 20,
            "location": 20,
            "event": 22,
            "risk_event": 22,
        }

        for node, attrs in self.graph.nodes(data=True):
            node_type = attrs.get("type", "unknown")
            severity = attrs.get("severity", "")

            # Use severity-based color for events, else fall back to type color
            if node_type in ("event", "risk_event") and severity in _severity_colors:
                color = _severity_colors[severity]
            else:
                color = _colors.get(node_type, "#888888")

            net.add_node(
                node,
                label=str(node)[:50],
                color=color,
                size=_sizes.get(node_type, 18),
                title=f"{node}\n({node_type})" + (f"\nSeverity: {severity}" if severity else ""),
                font={"color": "white", "size": 12},
            )

        for source, target, data in self.graph.edges(data=True):
            net.add_edge(
                source, target,
                title=data.get("relationship", ""),
                arrows="to",
            )

        net.save_graph(output_path)
        logger.info("Knowledge graph exported to %s", output_path)
        return output_path
