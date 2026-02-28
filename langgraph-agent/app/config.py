from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- Core ---
    anthropic_api_key: str
    database_url: str
    langgraph_api_key: str = ""
    webhook_secret: str = ""
    log_level: str = "INFO"
    environment: str = "production"

    # --- LLM ---
    claude_model: str = "claude-sonnet-4-20250514"
    llm_timeout: int = 60
    llm_max_retries: int = 3
    llm_retry_base_delay: float = 1.0

    # --- Dead letter ---
    dead_letter_max_failures: int = 3

    # --- Admin ---
    admin_email: str = ""

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
