"""
Full end-to-end pipeline demo with real API calls.
Runs realistic news scenarios for multiple companies to populate the dashboard.
"""
import sys
sys.path.insert(0, ".")

from app.agents.triage_agent import triage_article
from app.agents.analyst_agent import analyse_risk
from app.sensors.finance_sensor import fetch_stock_data, clear_cache
from app.sensors.weather_sensor import fetch_weather
from app.action_layer.alert_manager import store_risk_event
from app.database import get_db, init_db

init_db()
clear_cache()

# Realistic news scenarios for different companies
SCENARIOS = [
    {
        "company": "Apple Inc",
        "ticker": "AAPL",
        "headline": "TSMC warns of potential chip supply disruptions amid rising geopolitical tensions",
        "summary": "TSMC CEO warns that escalating tensions could affect semiconductor supply chains globally, impacting major customers including Apple.",
        "node_location": "Tainan, Taiwan",
        "node_type": "semiconductor",
        "coordinates": [23.1243, 120.3029],
    },
    {
        "company": "NVIDIA Corporation",
        "ticker": "NVDA",
        "headline": "AI chip demand outpaces supply as data center buildout accelerates worldwide",
        "summary": "NVIDIA faces growing backlog as hyperscalers race to build AI infrastructure, raising concerns about GPU allocation and delivery timelines.",
        "node_location": "Taipei, Taiwan",
        "node_type": "semiconductor",
        "coordinates": [25.0330, 121.5654],
    },
    {
        "company": "Tesla Inc",
        "ticker": "TSLA",
        "headline": "Lithium prices spike 20% as Chile tightens mining regulations",
        "summary": "New Chilean government regulations on lithium extraction could constrain battery supply for EV manufacturers including Tesla.",
        "node_location": "Atacama, Chile",
        "node_type": "raw_material",
        "coordinates": [-23.6509, -68.1591],
    },
    {
        "company": "Amazon",
        "ticker": "AMZN",
        "headline": "AWS reports brief service degradation in US-East-1 region",
        "summary": "Amazon Web Services experienced intermittent issues in its Virginia data center, affecting thousands of downstream services.",
        "node_location": "Ashburn, Virginia",
        "node_type": "data_center",
        "coordinates": [39.0438, -77.4874],
    },
    {
        "company": "Walmart",
        "ticker": "WMT",
        "headline": "Port of Houston congestion delays consumer goods shipments ahead of spring season",
        "summary": "Cargo backlog at Port of Houston reaches 15-day average wait time, threatening retail inventory levels for major chains.",
        "node_location": "Houston, Texas",
        "node_type": "logistics",
        "coordinates": [29.7604, -95.3698],
    },
]

print("=" * 60)
print("KHABAR AI - FULL DEMO")
print(f"Running {len(SCENARIOS)} scenarios with real API calls")
print("=" * 60)

stored = 0
errors = 0

for i, scenario in enumerate(SCENARIOS, 1):
    company = scenario["company"]
    print(f"\n--- [{i}/{len(SCENARIOS)}] {company} ---")

    try:
        # Triage
        relevant = triage_article(company, scenario["headline"], scenario["summary"])
        print(f"  Triage: {'YES' if relevant else 'NO'}")

        if not relevant:
            print("  Skipped (filtered by triage)")
            continue

        # Finance
        stock = fetch_stock_data(scenario["ticker"])
        print(f"  Stock:  ${stock['price']} ({stock['change_pct']}%)")

        # Weather
        coords = scenario["coordinates"]
        weather = fetch_weather(coords[0], coords[1], scenario["node_location"])
        print(f"  Weather: {weather['description']}, {weather['temperature_c']}C")

        # Analyst
        assessment = analyse_risk(
            company_name=company,
            node_location=scenario["node_location"],
            node_type=scenario["node_type"],
            headline=scenario["headline"],
            summary=scenario["summary"],
            volatility=stock["change_pct"],
            weather_description=weather["description"],
            weather_severity=weather["severity_label"],
        )
        print(f"  Analysis: {assessment.severity} (confidence: {assessment.confidence_score}%)")

        # Store
        with get_db() as db:
            event = store_risk_event(
                db=db,
                company_name=company,
                headline=scenario["headline"],
                source_url="https://demo.khabar.ai",
                stock_impact=stock["change_pct"],
                weather_correlation=weather["description"],
                assessment=assessment,
            )
            if event:
                print(f"  Stored: event id={event.id}")
                stored += 1
            else:
                print("  Duplicate - skipped")

    except Exception as e:
        print(f"  ERROR: {e}")
        errors += 1

print("\n" + "=" * 60)
print(f"DEMO COMPLETE: {stored} events stored, {errors} errors")
print("Refresh your dashboard at http://localhost:8502")
print("=" * 60)
