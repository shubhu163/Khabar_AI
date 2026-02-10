"""
Khabar AI — Sensor Unit Tests
==================================================
Tests run in DRY_RUN mode so they never hit real APIs.

Run:  pytest tests/ -v
"""

from __future__ import annotations

import os
import sys

import pytest

# Ensure DRY_RUN is set before any app imports
os.environ["DRY_RUN"] = "true"

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import get_settings, get_target_companies
from app.sensors.news_sensor import fetch_news
from app.sensors.finance_sensor import fetch_stock_data, clear_cache
from app.sensors.weather_sensor import fetch_weather, clear_cache as clear_weather


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------
class TestConfig:
    def test_settings_load(self):
        """Settings object should load without error."""
        settings = get_settings()
        assert settings.dry_run is True

    def test_companies_config(self):
        """Companies config should contain at least one company."""
        companies = get_target_companies()
        assert len(companies) >= 1
        assert "name" in companies[0]
        assert "ticker" in companies[0]
        assert "supply_chain_nodes" in companies[0]

    def test_company_has_keywords(self):
        """Each company should have risk keywords."""
        for company in get_target_companies():
            assert len(company.get("risk_keywords", [])) > 0


# ---------------------------------------------------------------------------
# News Sensor tests
# ---------------------------------------------------------------------------
class TestNewsSensor:
    def test_fetch_returns_list(self):
        """fetch_news should return a list of dicts."""
        articles = fetch_news("Apple Inc", ["supply chain", "shortage"])
        assert isinstance(articles, list)

    def test_article_schema(self):
        """Each article should have the expected keys."""
        articles = fetch_news("Apple Inc", ["supply chain"])
        for art in articles:
            assert "title" in art
            assert "description" in art
            assert "url" in art
            assert "published_at" in art
            assert "source" in art

    def test_dry_run_returns_data(self):
        """Dry run should return mock articles (not empty)."""
        articles = fetch_news("Test Company", ["test"])
        assert len(articles) > 0


# ---------------------------------------------------------------------------
# Finance Sensor tests
# ---------------------------------------------------------------------------
class TestFinanceSensor:
    def setup_method(self):
        clear_cache()

    def test_fetch_returns_dict(self):
        """fetch_stock_data should return a dict."""
        result = fetch_stock_data("AAPL")
        assert isinstance(result, dict)

    def test_stock_data_schema(self):
        """Result should have expected keys."""
        result = fetch_stock_data("NVDA")
        assert "ticker" in result
        assert "price" in result
        assert "change_pct" in result
        assert "volatility_label" in result

    def test_ticker_matches(self):
        """Returned ticker should match request."""
        result = fetch_stock_data("TSLA")
        assert result["ticker"] == "TSLA"


# ---------------------------------------------------------------------------
# Weather Sensor tests
# ---------------------------------------------------------------------------
class TestWeatherSensor:
    def setup_method(self):
        clear_weather()

    def test_fetch_returns_dict(self):
        """fetch_weather should return a dict."""
        result = fetch_weather(22.5431, 114.0579, "Shenzhen")
        assert isinstance(result, dict)

    def test_weather_schema(self):
        """Result should have expected keys."""
        result = fetch_weather(25.0330, 121.5654, "Taipei")
        assert "location" in result
        assert "temperature_c" in result
        assert "is_severe" in result
        assert "severity_label" in result

    def test_location_name_preserved(self):
        """Location name should appear in result."""
        result = fetch_weather(23.1243, 120.3029, "Tainan")
        assert result["location"] == "Tainan"


# ---------------------------------------------------------------------------
# Integration-style test (still dry run)
# ---------------------------------------------------------------------------
class TestPipelineIntegration:
    """Verify that sensors + config work together."""

    def test_all_companies_have_fetchable_news(self):
        for company in get_target_companies():
            articles = fetch_news(company["name"], company.get("risk_keywords", []))
            assert isinstance(articles, list)

    def test_all_tickers_fetchable(self):
        clear_cache()
        for company in get_target_companies():
            result = fetch_stock_data(company["ticker"])
            assert result["ticker"] == company["ticker"]

    def test_all_nodes_have_fetchable_weather(self):
        clear_weather()
        for company in get_target_companies():
            for node in company.get("supply_chain_nodes", []):
                coords = node["coordinates"]
                result = fetch_weather(coords[0], coords[1], node["location"])
                assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Triage Agent tests
# ---------------------------------------------------------------------------
class TestTriageAgent:
    def test_triage_returns_bool(self):
        from app.agents.triage_agent import triage_article
        result = triage_article("Apple Inc", "TSMC halts production", "Chip shortage worsens")
        assert isinstance(result, bool)

    def test_triage_batch_filters(self):
        from app.agents.triage_agent import triage_batch
        articles = fetch_news("Apple Inc", ["supply chain"])
        filtered = triage_batch("Apple Inc", articles)
        assert isinstance(filtered, list)
        # In dry run, roughly 30% should pass
        assert len(filtered) <= len(articles)


# ---------------------------------------------------------------------------
# Analyst Agent tests
# ---------------------------------------------------------------------------
class TestAnalystAgent:
    def test_analyse_returns_assessment(self):
        from app.agents.analyst_agent import RiskAssessment, analyse_risk
        result = analyse_risk(
            company_name="Apple Inc",
            node_location="Tainan, Taiwan",
            node_type="semiconductor",
            headline="TSMC reports production delays",
            summary="Delays due to equipment maintenance.",
            volatility=-2.5,
            weather_description="Clear skies",
            weather_severity="normal",
        )
        assert isinstance(result, RiskAssessment)
        assert result.severity in ("RED", "YELLOW", "GREEN")
        assert 0 <= result.confidence_score <= 100


# ---------------------------------------------------------------------------
# Database / Models tests
# ---------------------------------------------------------------------------
class TestModels:
    def test_headline_hash_deterministic(self):
        from app.models import RiskEvent
        h1 = RiskEvent.compute_headline_hash("Test Headline")
        h2 = RiskEvent.compute_headline_hash("Test Headline")
        assert h1 == h2

    def test_headline_hash_case_insensitive(self):
        from app.models import RiskEvent
        h1 = RiskEvent.compute_headline_hash("Test Headline")
        h2 = RiskEvent.compute_headline_hash("test headline")
        assert h1 == h2

    def test_headline_hash_strips_whitespace(self):
        from app.models import RiskEvent
        h1 = RiskEvent.compute_headline_hash("Test Headline")
        h2 = RiskEvent.compute_headline_hash("  Test Headline  ")
        assert h1 == h2
