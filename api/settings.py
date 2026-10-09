from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Read only from environment variables; names match .env.example and the LLM pair's code."""

    app_env: str = "local"  
    api_keys: str = ""  

    databricks_host: str = ""
    databricks_warehouse_id: str = ""
    databricks_token: str = ""
    databricks_catalog: str = "data2026acc123456"
    databricks_schema: str = "team2"

    auth_tenant_id: str = ""
    auth_audience: str = ""

    @property
    def databricks_http_path(self) -> str:
        return f"/sql/1.0/warehouses/{self.databricks_warehouse_id}"

    @property
    def api_key_list(self) -> list[str]:
        return [key.strip() for key in self.api_keys.split(",") if key.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()