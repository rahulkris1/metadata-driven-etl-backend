from functools import lru_cache
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_origins(value: object) -> object:
    if isinstance(value, str) and not value.lstrip().startswith("["):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


CorsOrigins = Annotated[list[str], BeforeValidator(_parse_origins)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "Metadata-driven ETL API"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    cors_allowed_origins: CorsOrigins = Field(default_factory=list)
    cors_allow_credentials: bool = True

    metadata_database_url: str = "sqlite:///./metadata.db"
    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_pool_recycle: int = 1800
    database_echo: bool = False

    azure_tenant_id: str | None = None
    azure_client_id: str | None = None
    azure_client_secret: SecretStr | None = None
    azure_subscription_id: str | None = None
    azure_resource_group: str | None = None

    databricks_host: str | None = None
    databricks_token: SecretStr | None = None
    databricks_http_path: str | None = None
    databricks_catalog: str | None = None
    databricks_schema: str = "default"

    airflow_base_url: str = "http://localhost:8080"
    airflow_username: str | None = None
    airflow_password: SecretStr | None = None
    airflow_api_token: SecretStr | None = None

    storage_provider: Literal["azure_blob", "local", "s3"] = "azure_blob"
    storage_account_name: str | None = None
    storage_account_key: SecretStr | None = None
    storage_connection_string: SecretStr | None = None
    storage_container_name: str = "etl"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
