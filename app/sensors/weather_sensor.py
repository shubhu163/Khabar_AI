"""
Khabar AI — Weather Sensor
===============================================
Checks current weather and alerts for every supply-chain node
(identified by GPS coordinates in companies.yaml).

Severe weather at a manufacturing or logistics hub can cause days-long
disruptions, so this sensor feeds into the Analyst Agent's correlation
logic alongside news and stock signals.

FREE-TIER SAFEGUARDS
  • OpenWeatherMap free tier: 60 calls/min, 1 M/month — more than
    enough for hourly checks on 3–10 locations.
  • Results are cached per coordinate pair for the pipeline run.

SEVERE-WEATHER DETECTION
  We map OpenWeatherMap's numeric *weather condition codes* to
  severity labels.  Codes in the 2xx (thunderstorm), 5xx (rain ≥
  heavy), and 7xx (atmosphere: tornado, squall) ranges plus extreme
  temperature (>45 °C or <-30 °C) are flagged.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants & cache
# ---------------------------------------------------------------------------
_OWM_CURRENT = "https://api.openweathermap.org/data/2.5/weather"
_OWM_FORECAST = "https://api.openweathermap.org/data/2.5/forecast"

# Condition codes considered "severe" (see https://openweathermap.org/weather-conditions)
_SEVERE_CODES = set(range(200, 233)) | set(range(502, 532)) | {771, 781}  # thunderstorm / heavy rain / squall / tornado

_EXTREME_HEAT_C = 45
_EXTREME_COLD_C = -30

_cache: dict[str, dict[str, Any]] = {}  # "lat,lon" -> result


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------
_MOCK_WEATHER: dict[str, Any] = {
    "location": "Mock City",
    "temperature_c": 28.0,
    "description": "scattered clouds",
    "weather_code": 802,
    "wind_speed_ms": 4.2,
    "humidity": 65,
    "is_severe": False,
    "severity_label": "normal",
    "alerts": [],
    "fetched_at": datetime.now(timezone.utc).isoformat(),
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def fetch_weather(
    lat: float,
    lon: float,
    location_name: str = "",
) -> dict[str, Any]:
    """
    Return current weather + severity assessment for a coordinate pair.

    Parameters
    ----------
    lat, lon : float
        GPS coordinates of the supply-chain node.
    location_name : str
        Human-readable label (for logging / display).

    Returns
    -------
    dict with keys:
        location, temperature_c, description, weather_code, wind_speed_ms,
        humidity, is_severe, severity_label, alerts, fetched_at
    """
    settings = get_settings()
    cache_key = f"{lat:.4f},{lon:.4f}"

    if settings.dry_run or not settings.openweather_key:
        logger.info("[DRY RUN] Returning mock weather for %s", location_name or cache_key)
        mock = _MOCK_WEATHER.copy()
        mock["location"] = location_name or "Mock Location"
        return mock

    if cache_key in _cache:
        logger.debug("Weather cache hit for %s", cache_key)
        return _cache[cache_key]

    try:
        # --- Current weather ---
        params = {
            "lat": lat,
            "lon": lon,
            "appid": settings.openweather_key,
            "units": "metric",
        }
        resp = requests.get(_OWM_CURRENT, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        weather_code = data["weather"][0]["id"]
        temp_c = data["main"]["temp"]
        description = data["weather"][0]["description"]

        is_severe, severity_label = _assess_severity(weather_code, temp_c)

        # --- Forecast alerts (simplified: check next 24 h for severe codes) ---
        alerts = _fetch_forecast_alerts(lat, lon, settings.openweather_key)

        result = {
            "location": location_name or data.get("name", ""),
            "temperature_c": round(temp_c, 1),
            "description": description,
            "weather_code": weather_code,
            "wind_speed_ms": data["wind"].get("speed", 0),
            "humidity": data["main"].get("humidity", 0),
            "is_severe": is_severe,
            "severity_label": severity_label,
            "alerts": alerts,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

        _cache[cache_key] = result
        logger.info(
            "Weather for %s: %s, %.1f°C, severe=%s",
            location_name, description, temp_c, is_severe,
        )
        return result

    except requests.RequestException as exc:
        logger.error("OpenWeatherMap request failed for %s: %s", location_name, exc)
        fallback = _MOCK_WEATHER.copy()
        fallback["location"] = location_name
        fallback["severity_label"] = "unknown"
        return fallback


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _assess_severity(code: int, temp_c: float) -> tuple[bool, str]:
    """
    Map a weather condition code + temperature to a severity label.

    Returns (is_severe: bool, label: str).
    """
    if code in _SEVERE_CODES:
        return True, "severe_weather"
    if temp_c >= _EXTREME_HEAT_C:
        return True, "extreme_heat"
    if temp_c <= _EXTREME_COLD_C:
        return True, "extreme_cold"
    return False, "normal"


def _fetch_forecast_alerts(
    lat: float, lon: float, api_key: str
) -> list[dict[str, str]]:
    """
    Check the 5-day / 3-hour forecast for upcoming severe weather
    within the next 24 hours.

    Returns a list of alert dicts (may be empty).
    """
    try:
        params = {
            "lat": lat,
            "lon": lon,
            "appid": api_key,
            "units": "metric",
            "cnt": 8,  # 8 × 3 h = 24 h
        }
        resp = requests.get(_OWM_FORECAST, params=params, timeout=15)
        resp.raise_for_status()
        forecasts = resp.json().get("list", [])

        alerts: list[dict[str, str]] = []
        for fc in forecasts:
            code = fc["weather"][0]["id"]
            temp = fc["main"]["temp"]
            is_severe, label = _assess_severity(code, temp)
            if is_severe:
                alerts.append(
                    {
                        "time": fc.get("dt_txt", ""),
                        "description": fc["weather"][0]["description"],
                        "severity": label,
                    }
                )
        return alerts

    except Exception as exc:  # noqa: BLE001 — forecast is advisory, never crash
        logger.warning("Forecast fetch failed: %s", exc)
        return []


def clear_cache() -> None:
    """Flush the in-memory weather cache."""
    _cache.clear()
