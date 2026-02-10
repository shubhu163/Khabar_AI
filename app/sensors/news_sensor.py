"""
Khabar AI — News Sensor
============================================
Fetches real news headlines using Google News RSS (free, no API key,
no rate limits). Results are normalised and passed to the Triage Agent.
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import requests

from app.config import get_settings

logger = logging.getLogger(__name__)


def fetch_news(
    company_name: str,
    risk_keywords: list[str],
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """
    Fetch recent news articles for *company_name* via Google News RSS.
    """
    settings = get_settings()

    if settings.dry_run:
        logger.info("[DRY RUN] Returning mock news for %s", company_name)
        return [
            {
                "title": "Mock: Supply chain disruption reported",
                "description": f"A mock supply chain event for {company_name}.",
                "url": "https://example.com/mock",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "source": "MockNews",
            }
        ]

    try:
        url = "https://news.google.com/rss/search"
        params = {"q": company_name, "hl": "en-US", "gl": "US", "ceid": "US:en"}
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        items = root.findall(".//item")

        articles = []
        for item in items[:max_results]:
            title = item.findtext("title", "")
            desc_raw = item.findtext("description", "")
            desc = re.sub(r"<[^>]+>", "", desc_raw).strip()
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            source = item.findtext("source", "unknown")

            articles.append({
                "title": title,
                "description": desc if desc else title,
                "url": link,
                "published_at": pub_date,
                "source": source,
            })

        logger.info("Google News returned %d articles for '%s'", len(articles), company_name)
        return articles

    except Exception as exc:
        logger.error("Google News fetch failed for %s: %s", company_name, exc)
        return []
