"""

Typed configuration settings for the trader.

"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field, model_validator

class Settings(BaseSettings):
    # Environment – "demo" (sandbox) or "live" (production)
    environment: str = "demo"
    # Base URLs for the Capital.com API – change automatically based on environment
    broker_base_url: str = ""
    broker_ws_url: str = "wss://api-streaming-capital.backend-capital.com/connect"
    broker_backend_url: str = 'https://api-capital.backend-capital.com/api/v1/'


    @model_validator(mode="after")
    def set_broker_urls(self) -> "Settings":
        if self.environment == "demo":
            self.broker_base_url = "https://demo-api-capital.com"
        else:
            self.broker_base_url = "https://api-capital.com"
        return self

    # Secrets
    capital_api_key: SecretStr | None = Field(default=None, env="CAPITAL_API_KEY")
    capital_username: SecretStr | None = Field(default=None, env="CAPITAL_USERNAME")
    capital_password: SecretStr | None = Field(default=None, env="CAPITAL_PASSWORD")
    # Runtime
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost/trading"
    redis_url: str = "redis://localhost:6379/0"
    log_level: str = "INFO"
    allow_live_trading: bool = False

    # Trading controls (defaults – can be overridden per‑env)
    max_position_size: float = 0.5
    max_open_positions: int = 5
    max_daily_loss_pct: float = 2.0
    stale_tick_threshold_ms: int = 2000
    max_spread: dict = {"GOLD": 0.50, "US500": 3.0}

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
