"""
LLM Factory

Creates LLM instances based on provider configuration.
Supports Azure OpenAI and Anthropic Claude.
"""
import os
from typing import Any

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel

load_dotenv()


def create_llm(config: dict[str, Any]) -> BaseChatModel:
    """
    Create an LLM instance based on provider configuration.

    Args:
        config: Dict with provider settings:
            - provider: "azure_openai" or "anthropic"
            - model: Model name/deployment (optional for azure, uses env var)
            - temperature: Temperature setting (default 1.0)

    Returns:
        BaseChatModel instance configured for the specified provider

    Raises:
        ValueError: If provider is not supported
        ImportError: If required package is not installed
    """
    provider = config.get("provider", "azure_openai")
    temperature = config.get("temperature", 1.0)
    model = config.get("model")

    if provider == "azure_openai":
        return _create_azure_openai_llm(model, temperature)
    elif provider == "anthropic":
        return _create_anthropic_llm(model, temperature)
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def _create_azure_openai_llm(model: str | None, temperature: float) -> BaseChatModel:
    """Create Azure OpenAI LLM instance."""
    from langchain_openai import AzureChatOpenAI
    from azure_auth import get_azure_ad_token

    return AzureChatOpenAI(
        azure_deployment=model or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        azure_ad_token_provider=get_azure_ad_token,
        temperature=temperature
    )


def _create_anthropic_llm(model: str | None, temperature: float) -> BaseChatModel:
    """Create Anthropic Claude LLM instance."""
    try:
        from langchain_anthropic import ChatAnthropic
    except ImportError:
        raise ImportError(
            "langchain-anthropic package is required for Anthropic provider. "
            "Install it with: pip install langchain-anthropic"
        )

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY environment variable is required for Anthropic provider"
        )

    return ChatAnthropic(
        model=model or "claude-sonnet-4-5-20250929",
        api_key=api_key,
        temperature=temperature,
        max_tokens=4096
    )
