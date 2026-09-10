from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SUPABASE_URL: str = Field(alias="SUPABASE_URL")
    SUPABASE_SECRET_KEY: str = Field(
        validation_alias=AliasChoices("SUPABASE_SECRET_KEY", "SUPABASE_SERVICE_ROLE_KEY"),
    )
    SUPABASE_JWKS_URL: str | None = Field(None, alias="SUPABASE_JWKS_URL")
    SUPABASE_JWT_SECRET: str = Field("placeholder_jwt_secret", alias="SUPABASE_JWT_SECRET")
    SUPABASE_JWT_AUDIENCE: str = Field("authenticated", alias="SUPABASE_JWT_AUDIENCE")

    SETTINGS_ENCRYPTION_KEY: str = Field(
        "default_secret_key_32_bytes_long_123456",
        alias="SETTINGS_ENCRYPTION_KEY",
        description="32-byte secret key for AES-256-GCM BYOK API key encryption"
    )

    LANGSMITH_TRACING: str = Field("false", alias="LANGSMITH_TRACING")
    LANGSMITH_API_KEY: str | None = Field(None, alias="LANGSMITH_API_KEY")
    LANGSMITH_ENDPOINT: str | None = Field(None, alias="LANGSMITH_ENDPOINT")
    LANGSMITH_PROJECT: str = Field("Paper Mind", alias="LANGSMITH_PROJECT")

    MAX_UPLOAD_MB: int = Field(50, alias="MAX_UPLOAD_MB")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()