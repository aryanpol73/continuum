"""
Configuration management and runtime date anchor resolution for Continuum.
"""

from __future__ import annotations
import os
from pathlib import Path
from datetime import date, datetime
from typing import Any, Dict, Optional
import yaml
from dotenv import load_dotenv

# Load .env if present
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"

_runtime_today_override: Optional[date] = None


def get_base_dir() -> Path:
    return BASE_DIR


def load_yaml(file_path: Path) -> Dict[str, Any]:
    if not file_path.exists():
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_settings() -> Dict[str, Any]:
    settings_file = CONFIG_DIR / "settings.yaml"
    settings = load_yaml(settings_file)
    
    # Environment variable overrides
    db_env = os.getenv("DATABASE_URL")
    if db_env:
        if "paths" not in settings:
            settings["paths"] = {}
        settings["paths"]["db_url"] = db_env

    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        settings["gemini_api_key"] = gemini_key

    return settings


_cached_rules: Optional[Dict[str, Any]] = None
_cached_mappings: Dict[str, Any] = {}
_cached_templates: Dict[str, Any] = {}


def get_rules() -> Dict[str, Any]:
    global _cached_rules
    if _cached_rules is None:
        _cached_rules = load_yaml(CONFIG_DIR / "rules.yaml")
    return _cached_rules


def get_mapping(mapping_name: str = "mapping_ramraksha.yaml") -> Dict[str, Any]:
    if mapping_name not in _cached_mappings:
        _cached_mappings[mapping_name] = load_yaml(CONFIG_DIR / mapping_name)
    return _cached_mappings[mapping_name]


def get_template(template_id: str) -> Dict[str, Any]:
    if template_id not in _cached_templates:
        template_file = CONFIG_DIR / "templates" / f"{template_id}.yaml"
        _cached_templates[template_id] = load_yaml(template_file)
    return _cached_templates[template_id]


def get_today() -> date:
    """
    Returns the time anchor for clinical evaluations.
    Prioritizes:
    1. Runtime override in memory (e.g. set via Streamlit UI)
    2. TODAY environment variable
    3. today_override setting from settings.yaml
    4. Current system date
    """
    global _runtime_today_override
    if _runtime_today_override is not None:
        return _runtime_today_override

    env_today = os.getenv("TODAY")
    if env_today and env_today.strip():
        try:
            return datetime.strptime(env_today.strip(), "%Y-%m-%d").date()
        except ValueError:
            pass

    settings = get_settings()
    yaml_today = settings.get("today_override")
    if yaml_today:
        if isinstance(yaml_today, date):
            return yaml_today
        if isinstance(yaml_today, str) and yaml_today.strip():
            try:
                return datetime.strptime(yaml_today.strip(), "%Y-%m-%d").date()
            except ValueError:
                pass

    return date.today()


def set_today_override(new_date: Optional[date | str]) -> None:
    """
    Allows setting or clearing the in-memory time anchor.
    """
    global _runtime_today_override
    if new_date is None:
        _runtime_today_override = None
    elif isinstance(new_date, str):
        _runtime_today_override = datetime.strptime(new_date.strip(), "%Y-%m-%d").date()
    else:
        _runtime_today_override = new_date
