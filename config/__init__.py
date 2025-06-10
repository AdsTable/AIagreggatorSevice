# config/__init__.py
"""
Centralized config import module.
Use this to load both typed settings (settings.py) and AI provider configs (ai_providers.yaml).
All comments must be in English.
"""
from .settings import DatabaseSettings, RedisSettings, SecuritySettings, MonitoringSettings, AISettings
import yaml
import os

def load_ai_providers_config(path="config/ai_providers.yaml"):
    """
    Loads AI provider configuration from the given YAML file.
    Expands any ${VARNAME} with values from environment variables.
    """
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    for provider, settings in cfg.items():
        for key, value in settings.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                env_key = value[2:-1]
                cfg[provider][key] = os.getenv(env_key)
    return cfg
