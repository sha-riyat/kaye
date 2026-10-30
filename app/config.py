"""Settings loaded from environment variables (local `.env`, Modal Secret `kaye-secrets` in prod)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # WhatsApp Cloud API
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_business_account_id: str = ""
    whatsapp_app_secret: str = ""
    whatsapp_verify_token: str = ""
    whatsapp_api_version: str = "v26.0"
    whatsapp_graph_base_url: str = "https://graph.facebook.com"

    # Meta models
    meta_model_api_key: str = ""
    meta_model_base_url: str = "https://api.meta.ai/v1"
    transcribe_model: str = "muse-voice-transcribe-1.0"
    spark_open_base_url: str = ""
    spark_open_api_key: str = ""
    spark_open_model: str = ""

    # Storage
    database_url: str = ""
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = "kaye-media"

    # Abuse protection
    daily_message_quota_per_user: int = 100
    global_daily_model_budget_usd: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
