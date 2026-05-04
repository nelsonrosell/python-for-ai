import os
from dataclasses import dataclass
from .env import load_environment


load_environment()


@dataclass(frozen=True)
class AppConfig:
    app_env: str
    sql_connection_string: str
    sql_allowed_tables: tuple[str, ...]
    sql_use_access_token_auth: bool
    sql_entra_login_hint: str | None
    azure_openai_endpoint: str
    azure_openai_api_key: str
    azure_openai_api_version: str
    azure_openai_deployment: str
    agent_verbose_logging: bool
    max_export_rows: int
    graph_mail_tenant_id: str | None
    graph_mail_client_id: str | None
    graph_mail_client_secret: str | None
    graph_mail_sender: str | None
    auto_email_duplicate_alerts: bool
    duplicate_alert_recipient: str | None


REQUIRED_KEYS = [
    "SQL_CONNECTION_STRING",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_DEPLOYMENT",
]


def _get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _get_positive_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default

    parsed = int(value)
    if parsed <= 0:
        raise ValueError(
            f"Environment variable {name} must be a positive integer.")
    return parsed


def _get_csv_env(name: str) -> tuple[str, ...]:
    value = os.getenv(name, "")
    if not value.strip():
        return ()

    items = [item.strip() for item in value.split(",") if item.strip()]
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        lowered = item.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        normalized.append(item)
    return tuple(normalized)


def load_config() -> AppConfig:
    missing = [key for key in REQUIRED_KEYS if not os.getenv(key)]
    if missing:
        missing_keys = ", ".join(missing)
        raise ValueError(
            f"Missing required environment variables: {missing_keys}")

    app_env = os.getenv("APP_ENV", "dev").lower()
    sql_allowed_tables = _get_csv_env("SQL_ALLOWED_TABLES")
    agent_verbose_logging = _get_bool_env(
        "APP_ENABLE_VERBOSE_AGENT_LOGS", False)
    if app_env != "dev" and not sql_allowed_tables:
        raise ValueError(
            "SQL_ALLOWED_TABLES must be configured when APP_ENV is not 'dev'."
        )
    if app_env != "dev" and agent_verbose_logging:
        raise ValueError(
            "APP_ENABLE_VERBOSE_AGENT_LOGS must be disabled when APP_ENV is not 'dev'."
        )

    return AppConfig(
        app_env=app_env,
        sql_connection_string=os.environ["SQL_CONNECTION_STRING"],
        sql_allowed_tables=sql_allowed_tables,
        sql_use_access_token_auth=os.getenv(
            "SQL_USE_ACCESS_TOKEN_AUTH", "false"
        ).lower()
        == "true",
        sql_entra_login_hint=os.getenv("SQL_ENTRA_LOGIN_HINT") or None,
        azure_openai_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        azure_openai_api_key=os.environ["AZURE_OPENAI_API_KEY"],
        azure_openai_api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        azure_openai_deployment=os.environ["AZURE_OPENAI_DEPLOYMENT"],
        agent_verbose_logging=agent_verbose_logging,
        max_export_rows=_get_positive_int_env("APP_MAX_EXPORT_ROWS", 500),
        graph_mail_tenant_id=os.getenv("GRAPH_MAIL_TENANT_ID") or None,
        graph_mail_client_id=os.getenv("GRAPH_MAIL_CLIENT_ID") or None,
        graph_mail_client_secret=os.getenv("GRAPH_MAIL_CLIENT_SECRET") or None,
        graph_mail_sender=os.getenv("GRAPH_MAIL_SENDER") or None,
        auto_email_duplicate_alerts=_get_bool_env("APP_AUTO_EMAIL_DUPLICATE_ALERTS", False),
        duplicate_alert_recipient=os.getenv("APP_DUPLICATE_ALERT_RECIPIENT") or None,
    )
