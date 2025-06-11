# config/__init__.py
"""
Centralized config import module.
Use this to load both typed settings (settings.py) and AI provider configs (ai_providers.yaml).
All comments must be in English.
"""
from .settings import DatabaseSettings, RedisSettings, SecuritySettings, MonitoringSettings, AISettings
import yaml
import os
from pathlib import Path

# Import settings with proper error handling
try:
    from .settings import (
        settings,
        DatabaseSettings, 
        RedisSettings, 
        SecuritySettings, 
        MonitoringSettings, 
        AISettings,
        AppSettings,
        get_settings
    )
except ImportError as e:
    print(f"❌ Failed to import settings: {e}")
    raise

def load_ai_providers_config(path: str = "config/ai_providers.yaml") -> dict:
    """
    Loads AI provider configuration from the given YAML file.
    Expands any ${VARNAME} with values from environment variables.
    
    Args:
        path: Path to the YAML configuration file
        
    Returns:
        dict: Configuration dictionary with environment variables expanded
        
    Raises:
        FileNotFoundError: If the configuration file doesn't exist
        yaml.YAMLError: If the YAML file is malformed
    """
    config_path = Path(path)
    
    if not config_path.exists():
        print(f"⚠️  AI providers config file not found: {path}")
        return {}
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        
        # Expand environment variables
        for provider, provider_settings in cfg.items():
            if isinstance(provider_settings, dict):
                for key, value in provider_settings.items():
                    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                        env_key = value[2:-1]
                        env_value = os.getenv(env_key)
                        if env_value is not None:
                            cfg[provider][key] = env_value
                        else:
                            print(f"⚠️  Environment variable {env_key} not found for {provider}.{key}")
        
        return cfg
        
    except yaml.YAMLError as e:
        print(f"❌ Failed to parse YAML config: {e}")
        return {}
    except Exception as e:
        print(f"❌ Unexpected error loading AI providers config: {e}")
        return {}

# Export all settings for convenience
__all__ = [
    'settings',
    'DatabaseSettings',
    'RedisSettings', 
    'SecuritySettings',
    'MonitoringSettings',
    'AISettings',
    'AppSettings',
    'get_settings',
    'load_ai_providers_config'
]