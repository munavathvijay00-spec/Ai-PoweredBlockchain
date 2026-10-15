"""
Configuration loader.
Reads .env file and provides typed access to settings.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from .env file."""

    # Blockchain
    alchemy_api_key: str
    ethereum_rpc_url: str

    # Database
    postgres_user: str = "postgres"
    postgres_password: str = "password"
    postgres_db: str = "blockchain_analytics"
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    database_url: str

    # AI
    openai_api_key: str = "not-set"
    llm_provider: str = "ollama"
    llm_model: str = "llama3.2:1b"
    ollama_url: str = "http://localhost:11434"
    groq_api_key: str = "not-set"
    groq_model: str = "openai/gpt-oss-20b"
    ai_enrichment_batch_size: int = 8
    ai_enrichment_min_score: int = 20

    # API
    api_key: str
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_allowed_origins: str = "*"
    public_rate_limit_per_minute: int = 120
    expensive_rate_limit_per_minute: int = 20
    max_request_body_bytes: int = 1_000_000

    # Risk scoring
    large_transaction_threshold_eth: float = 10.0
    bursty_activity_window_minutes: int = 60
    bursty_activity_threshold: int = 10
    new_wallet_days: int = 30

    # Logging
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    """Returns cached settings instance."""
    return Settings()


if __name__ == "__main__":
    settings = get_settings()
    print("✅ Settings loaded successfully!")
    print(f"   Database: {settings.postgres_db}")
    print(f"   API Port: {settings.api_port}")
    print(f"   LLM Provider: {settings.llm_provider}")
    print(f"   Local LLM Model: {settings.llm_model}")
    print(f"   Groq Model: {settings.groq_model}")
    print(f"   AI enrichment batch: {settings.ai_enrichment_batch_size}")
    print(f"   Ollama URL: {settings.ollama_url}")
    print(f"   Allowed origins: {settings.cors_allowed_origins}")
    print(f"   Public RPM: {settings.public_rate_limit_per_minute}")
    print(f"   Alchemy key (masked): {settings.alchemy_api_key[:8]}...")
