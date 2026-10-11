"""The chat model: Azure OpenAI, configured only from settings (environment variables / Key Vault)."""

from fastapi import Depends
from langchain_core.language_models import BaseChatModel

from api.errors import AssistantUnavailable
from api.settings import Settings, get_settings

TIMEOUT_SECONDS = 30
MAX_RETRIES = 2  # the client retries 429 and 5xx itself, with backoff; after that the API answers 503


def get_llm(settings: Settings = Depends(get_settings)) -> BaseChatModel:
    """FastAPI dependency; tests override it with a scripted model. Raises AssistantUnavailable if not configured."""
    missing = [
        name
        for name, value in (
            ("AZURE_OPENAI_ENDPOINT", settings.azure_openai_endpoint),
            ("AZURE_OPENAI_API_KEY", settings.azure_openai_api_key.get_secret_value()),
            ("AZURE_OPENAI_DEPLOYMENT", settings.azure_openai_deployment),
        )
        if not value.strip()
    ]
    if missing:
        # Names only, never values.
        raise AssistantUnavailable(f"not configured: {', '.join(missing)}")

    from langchain_openai import AzureChatOpenAI  # imported here so the API starts without touching OpenAI

    return AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        azure_deployment=settings.azure_openai_deployment,
        api_version=settings.azure_openai_api_version,
        temperature=0,
        timeout=TIMEOUT_SECONDS,
        max_retries=MAX_RETRIES,
    )
