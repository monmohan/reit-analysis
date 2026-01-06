"""
LLM Configuration Loader

Loads and validates LLM provider configuration from llm_config.json.
Supports Azure OpenAI and Anthropic Claude providers.
"""
import json
import os
from typing import Any

VALID_PROVIDERS = ["azure_openai", "anthropic"]

DEFAULT_CONFIG = {
    "primary_llm": {
        "provider": "azure_openai",
        "model": None,  # Falls back to AZURE_OPENAI_DEPLOYMENT_NAME env var
        "temperature": 1.0
    }
}


def load_llm_config(config_path: str = "llm_config.json") -> dict[str, Any]:
    """
    Load LLM configuration from JSON file.

    Args:
        config_path: Path to the JSON config file (default: llm_config.json)

    Returns:
        Dict with 'primary_llm' and optionally 'reflection_llm' configs.
        If reflection_llm is not specified, it defaults to primary_llm settings.

    Raises:
        ValueError: If provider is not valid
    """
    config = DEFAULT_CONFIG.copy()

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                file_config = json.load(f)

            # Merge file config with defaults
            if "primary_llm" in file_config:
                config["primary_llm"] = {**DEFAULT_CONFIG["primary_llm"], **file_config["primary_llm"]}

            if "reflection_llm" in file_config:
                config["reflection_llm"] = file_config["reflection_llm"]

        except json.JSONDecodeError as e:
            print(f"Warning: Failed to parse {config_path}: {e}")
            print("Using default configuration (Azure OpenAI)")
    else:
        print(f"Info: {config_path} not found, using default configuration (Azure OpenAI)")

    # Validate providers
    _validate_config(config)

    # Set reflection_llm to primary_llm if not specified
    if "reflection_llm" not in config:
        config["reflection_llm"] = config["primary_llm"]

    return config


def _validate_config(config: dict[str, Any]) -> None:
    """Validate the LLM configuration."""
    for llm_key in ["primary_llm", "reflection_llm"]:
        if llm_key in config:
            provider = config[llm_key].get("provider")
            if provider not in VALID_PROVIDERS:
                raise ValueError(
                    f"Invalid provider '{provider}' for {llm_key}. "
                    f"Valid providers: {VALID_PROVIDERS}"
                )
