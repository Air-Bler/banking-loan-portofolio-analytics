from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Read only from environment variables; names match .env.example and the LLM pair's code."""

    app_env: str = "local"  
    api_keys: SecretStr = SecretStr("")  # SecretStr: printed as ********** if settings are ever logged

    databricks_host: str = ""
    databricks_warehouse_id: str = ""
    databricks_token: SecretStr = SecretStr("")
    databricks_catalog: str = "data2026acc123456"
    databricks_schema: str = "team2"

    auth_tenant_id: str = ""
    auth_audience: str = ""

    # The assistant's model (api/assistant/llm.py). Empty means not configured: /assistant/query answers 503.
    azure_openai_endpoint: str = ""
    azure_openai_api_key: SecretStr = SecretStr("")
    azure_openai_deployment: str = ""
    azure_openai_api_version: str = "2024-10-21"  # GA version with tool calling; set only to override

    @property
    def databricks_http_path(self) -> str:
        return f"/sql/1.0/warehouses/{self.databricks_warehouse_id}"

    @property
    def api_key_list(self) -> list[str]:
        return [key.strip() for key in self.api_keys.get_secret_value().split(",") if key.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()