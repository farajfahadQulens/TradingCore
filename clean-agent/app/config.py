"""Application settings.

Settings are loaded from environment variables and an optional local `.env`
file. Defaults mirror the existing agent where possible, especially the GPT
OSS 120 model and OpenAI-compatible base URL.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the clean agent."""

    agent_host: str = "127.0.0.1"
    agent_port: int = 8091

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "gpt-oss:120b-cloud"

    trader_base_url: str = "http://localhost:8000"
    trader_timeout_seconds: float = 5.0
    broker_snapshot_timeout_seconds: float = 3.0

    canvas_base_url: str = "https://bi.instructure.com"
    canvas_client_id: str = ""
    canvas_client_secret: str = ""
    canvas_redirect_uri: str = "http://127.0.0.1:8091/integrations/canvas/callback"
    canvas_token_encryption_key: str = ""
    canvas_timeout_seconds: float = 10.0

    database_path: str = "data/agent.sqlite3"
    allow_trading_writes: bool = False
    order_confirmation_phrase: str = "CONFIRM_LIVE_ORDER"
    require_stop_loss: bool = True
    max_ticket_size: float = 0.5
    max_open_positions: int = 5

    notification_watcher_enabled: bool = True
    notification_poll_seconds: float = 20.0
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    telegram_timeout_seconds: float = 5.0

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
