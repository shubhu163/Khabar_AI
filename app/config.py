"""
Khabar AI — Configuration Loader
====================================================
WHY a dedicated config module?
  • Single source of truth for *all* runtime settings.
  • Environment variables (secrets) are loaded via python-dotenv and
    validated with Pydantic-Settings so typos surface immediately.
  • The YAML company config is parsed once and cached as a typed dict
    to avoid re-reading the file on every pipeline iteration.
"""

from __future__ import annotations

import os
import pathlib
from functools import lru_cache
from typing import Any

import yaml
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# ---------------------------------------------------------------------------
# Resolve paths relative to the project root (two levels up from this file)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
_CONFIG_DIR = _PROJECT_ROOT / "config"

# Load .env from the project root (if present)
load_dotenv(_PROJECT_ROOT / ".env")


# ---------------------------------------------------------------------------
# Pydantic-Settings model — validates env vars at import time
# ---------------------------------------------------------------------------
class Settings(BaseSettings):
    """Strongly-typed application settings backed by environment variables."""

    # Data-source keys
    newsapi_key: str = Field(default="", alias="NEWSAPI_KEY")
    alpha_vantage_key: str = Field(default="", alias="ALPHA_VANTAGE_KEY")
    openweather_key: str = Field(default="", alias="OPENWEATHER_KEY")

    # LLM keys
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")
    openrouter_api_key: str = Field(default="", alias="OPENROUTER_API_KEY")

    # Supabase
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_key: str = Field(default="", alias="SUPABASE_KEY")

    # Runtime flags
    dry_run: bool = Field(default=False, alias="DRY_RUN")

    model_config = {
        "env_file": ".env",
        "extra": "ignore",  # ignore unexpected env vars
    }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance (parsed once per process)."""
    return Settings()


# ---------------------------------------------------------------------------
# YAML company-config loader
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def load_companies_config() -> dict[str, Any]:
    """
    Read and cache config/companies.yaml.

    Returns the full dict so callers can iterate over
    ``config["target_companies"]``.
    """
    config_path = _CONFIG_DIR / "companies.yaml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"Company config not found at {config_path}. "
            "Copy config/companies.yaml.example and customise it."
        )
    with open(config_path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def get_target_companies() -> list[dict[str, Any]]:
    """Convenience accessor — returns the list of company dicts."""
    return load_companies_config().get("target_companies", [])
