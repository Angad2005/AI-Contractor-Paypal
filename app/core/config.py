from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Contractor PayPal"
    app_env: str = "development"
    database_url: str = "sqlite:///./app.db"
    generated_dir: str = "generated"

    # PayPal remains mock by default for local development. Use sandbox for the real API.
    paypal_mode: str = "mock"
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_api_base_url: str = "https://api-m.sandbox.paypal.com"
    paypal_return_url: str = "http://localhost:8000/"
    paypal_cancel_url: str = "http://localhost:8000/"

    # Any OpenAI-compatible chat-completions endpoint can be used for the AI pipeline.
    llm_provider: str = "demo"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 60.0

    # Settings-page protection and encryption. Render should provide both values.
    settings_admin_token: str = ""
    settings_encryption_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
ROOT_DIR = Path(__file__).resolve().parents[2]
