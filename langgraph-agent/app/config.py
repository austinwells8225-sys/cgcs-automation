from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str
    database_url: str
    langgraph_api_key: str = ""
    log_level: str = "INFO"
    environment: str = "production"
    claude_model: str = "claude-sonnet-4-20250514"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
