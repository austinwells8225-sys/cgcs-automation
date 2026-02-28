import os

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

    # --- LangSmith ---
    langchain_api_key: str = ""
    langchain_project: str = "cgcs-automation"
    langchain_tracing_v2: bool = True

    # --- Google APIs ---
    google_service_account_file: str = ""
    google_calendar_id: str = "primary"
    pet_tracker_spreadsheet_id: str = ""

    # --- Zoho Mail ---
    zoho_mail_token: str = ""
    zoho_account_id: str = ""

    # --- Email auto-send allowlist ---
    email_auto_send_allowlist: str = "stefano.casafrancalaos@austincc.edu,marisela.perez@austincc.edu"

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()

# Set LangSmith env vars before any LangChain imports elsewhere
if settings.langchain_api_key:
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
    os.environ["LANGCHAIN_TRACING_V2"] = str(settings.langchain_tracing_v2).lower()
