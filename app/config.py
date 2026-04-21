import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


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
        raise ValueError(f"Missing required environment variables: {missing_keys}")

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
