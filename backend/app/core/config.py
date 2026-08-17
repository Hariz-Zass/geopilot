from functools import lru_cache

from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """GeoPilot runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = Field(default="GeoPilot AI", alias="APP_NAME")
    app_env: str = Field(default="local", alias="APP_ENV")
    app_version: str = Field(default="0.0.22", alias="APP_VERSION")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    cors_origins: tuple[str, ...] = Field(
        default=("http://localhost:5173",), alias="CORS_ORIGINS"
    )
    database_url: str = Field(
        default="postgresql+psycopg://geopilot:geopilot@db:5432/geopilot",
        alias="DATABASE_URL",
    )
    db_connect_timeout_seconds: int = Field(
        default=5,
        ge=1,
        le=30,
        alias="DB_CONNECT_TIMEOUT_SECONDS",
    )
    auth_jwt_secret: str = Field(
        default="local-development-change-me-at-least-32-bytes", alias="AUTH_JWT_SECRET"
    )
    auth_jwt_algorithm: Literal["HS256"] = Field(default="HS256", alias="AUTH_JWT_ALGORITHM")
    auth_access_token_minutes: int = Field(
        default=60, ge=5, le=1440, alias="AUTH_ACCESS_TOKEN_MINUTES"
    )
    auth_issuer: str = Field(default="geopilot-ai", alias="AUTH_ISSUER")
    document_storage_root: str = Field(default="/data/documents", alias="DOCUMENT_STORAGE_ROOT")
    raster_storage_root: str = Field(default="/data/rasters", alias="RASTER_STORAGE_ROOT")
    raster_upload_max_bytes: int = Field(default=1073741824, ge=1048576, le=4294967296, alias="RASTER_UPLOAD_MAX_BYTES")
    terrain_auto_acquisition_enabled: bool = Field(default=False, alias="TERRAIN_AUTO_ACQUISITION_ENABLED")
    terrain_auto_provider: Literal["copernicus_cdse"] = Field(default="copernicus_cdse", alias="TERRAIN_AUTO_PROVIDER")
    terrain_auto_target_crs: str = Field(default="EPSG:32647", alias="TERRAIN_AUTO_TARGET_CRS")
    terrain_cdse_client_id: str | None = Field(default=None, alias="TERRAIN_CDSE_CLIENT_ID")
    terrain_cdse_client_secret: str | None = Field(default=None, alias="TERRAIN_CDSE_CLIENT_SECRET")
    track_b_max_analysis_pixels: int = Field(default=16000000, ge=1000000, le=100000000, alias="TRACK_B_MAX_ANALYSIS_PIXELS")
    document_upload_max_bytes: int = Field(default=104857600, ge=1024, le=1073741824, alias="DOCUMENT_UPLOAD_MAX_BYTES")
    ai_provider: Literal["ollama", "openai"] = Field(default="ollama", alias="AI_PROVIDER")
    ai_fallback_provider: Literal["ollama", "openai"] | None = Field(default="openai", alias="AI_FALLBACK_PROVIDER")

    embedding_provider: Literal["ollama", "openai"] = Field(default="ollama", alias="EMBEDDING_PROVIDER")
    embedding_fallback_provider: Literal["ollama", "openai"] | None = Field(default="openai", alias="EMBEDDING_FALLBACK_PROVIDER")
    embedding_batch_size: int = Field(default=64, ge=1, le=256, alias="EMBEDDING_BATCH_SIZE")
    embedding_timeout_seconds: int = Field(default=60, ge=1, le=300, alias="EMBEDDING_TIMEOUT_SECONDS")
    ollama_base_url: str = Field(default="http://host.docker.internal:11434", alias="OLLAMA_BASE_URL")
    ollama_embedding_model: str = Field(default="nomic-embed-text", alias="OLLAMA_EMBEDDING_MODEL")
    openai_base_url: str = Field(default="https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_embedding_model: str | None = Field(default=None, alias="OPENAI_EMBEDDING_MODEL")
    ollama_planning_model: str = Field(default="qwen3:8b", alias="OLLAMA_PLANNING_MODEL")
    openai_planning_model: str = Field(default="gpt-5.6-luna", alias="OPENAI_PLANNING_MODEL")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return tuple(item.strip() for item in value.split(",") if item.strip())
        return value

    @field_validator("auth_jwt_secret")
    @classmethod
    def validate_auth_secret(cls, value: str) -> str:
        if len(value.encode("utf-8")) < 32:
            raise ValueError("AUTH_JWT_SECRET must be at least 32 bytes")
        return value

    @model_validator(mode="after")
    def reject_default_secret_outside_local(self) -> "Settings":
        local_envs = {"local", "development", "dev", "test"}
        if (
            self.app_env.lower() not in local_envs
            and self.auth_jwt_secret == "local-development-change-me-at-least-32-bytes"
        ):
            raise ValueError("AUTH_JWT_SECRET must be changed outside local/development/test")
        return self

    @field_validator("api_v1_prefix")
    @classmethod
    def validate_api_prefix(cls, value: str) -> str:
        cleaned = value.rstrip("/") or "/api/v1"
        if not cleaned.startswith("/"):
            raise ValueError("API_V1_PREFIX must start with '/'")
        return cleaned


@lru_cache
def get_settings() -> Settings:
    return Settings()



