"""Configuration for the LLM Council.

Loads settings from config.yaml if present, falls back to defaults.
API keys are always loaded from environment variables.
"""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

# Find project root (where config.yaml lives)
_PROJECT_ROOT = Path(__file__).parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"

# Defaults (used if config.yaml is missing)
_DEFAULTS = {
    "council_models": [
        "openai/gpt-4o-mini",
        "x-ai/grok-3",
        "deepseek/deepseek-chat",
    ],
    "chairman_model": "openai/gpt-4o-mini",
    "openrouter_api_url": "https://openrouter.ai/api/v1/chat/completions",
    "data_dir": "data/conversations",
}


def _load_config() -> dict:
    """Load configuration from YAML file or return defaults."""
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH) as f:
            config = yaml.safe_load(f) or {}
        # Merge with defaults (config values override defaults)
        return {**_DEFAULTS, **config}
    return _DEFAULTS


_config = _load_config()

# API key from environment (never in config file)
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# Council members - list of OpenRouter model identifiers
COUNCIL_MODELS: list[str] = _config["council_models"]

# Chairman model - synthesizes final response
CHAIRMAN_MODEL: str = _config["chairman_model"]

# OpenRouter API endpoint
OPENROUTER_API_URL: str = _config["openrouter_api_url"]

# Data directory for conversation storage
DATA_DIR: str = _config["data_dir"]
