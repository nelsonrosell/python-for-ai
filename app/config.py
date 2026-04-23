import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _load_env() -> None:
    """Load .env.<APP_ENV> first, then fall back to .env for any missing values."""
    env = os.getenv("APP_ENV", "dev").lower()
    base_dir = Path(__file__).resolve().parent.parent
    env_file = base_dir / f".env.{env}"
    fallback = base_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file, override=True)
    elif fallback.exists():
        load_dotenv(fallback, override=True)
    else:
        raise FileNotFoundError(
            f"No environment file found. Expected '{env_file}' or '{fallback}'."
        )


_load_env()


@dataclass(frozen=True)
class AppConfig:
    sql_connection_string: str
    sql_use_access_token_auth: bool
    sql_entra_login_hint: str | None
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_api_version: str
    azure_openai_deployment: str


REQUIRED_KEYS = [
    "SQL_CONNECTION_STRING",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT",
]


def load_config() -> AppConfig:
    missing = [key for key in REQUIRED_KEYS if not os.getenv(key)]
    if missing:
        missing_keys = ", ".join(missing)
        raise ValueError(
            f"Missing required environment variables: {missing_keys}")

    return AppConfig(
        sql_connection_string=os.environ["SQL_CONNECTION_STRING"],
        sql_use_access_token_auth=os.getenv(
            "SQL_USE_ACCESS_TOKEN_AUTH", "false"
        ).lower()
        == "true",
        sql_entra_login_hint=os.getenv("SQL_ENTRA_LOGIN_HINT") or None,
        azure_openai_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_openai_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_openai_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        azure_openai_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
    )
