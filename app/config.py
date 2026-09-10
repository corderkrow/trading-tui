"""Application settings via Pydantic BaseSettings."""

from pathlib import Path

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    BINANCE_API_KEY: str = ""
    BINANCE_SECRET_KEY: str = ""
    DEFAULT_SYMBOL: str = "BTC-USD"
    ADAPTER_NAME: str = "yahoo"
    ALERTS_DB_PATH: str = str(PROJECT_ROOT / "alerts.db")
    CURRENCY: str = "usd"

    model_config = {"env_file": ".env", "case_sensitive": True}


settings = Settings()
