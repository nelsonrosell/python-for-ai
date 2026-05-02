import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path


_HANDLER_NAME = "python-for-ai-file-handler"
_CONSOLE_HANDLER_NAME = "python-for-ai-console-handler"
_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "azure",
    "azure.core.pipeline.policies.http_logging_policy",
    "azure.identity",
    "openai",
)


def _get_positive_int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default

    parsed = int(value)
    if parsed <= 0:
        raise ValueError(
            f"Environment variable {name} must be a positive integer.")
    return parsed


def configure_logging() -> Path:
    level_name = os.getenv("APP_LOG_LEVEL", "WARNING").strip().upper()
    level = getattr(logging, level_name, logging.WARNING)

    log_file = Path(os.getenv("APP_LOG_FILE", "logs/app.log")).expanduser()
    if not log_file.is_absolute():
        log_file = Path(__file__).resolve().parent.parent / log_file
    log_file.parent.mkdir(parents=True, exist_ok=True)

    max_bytes = _get_positive_int_env("APP_LOG_MAX_BYTES", 1_048_576)
    backup_count = _get_positive_int_env("APP_LOG_BACKUP_COUNT", 5)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    if not any(getattr(handler, "name", "") == _HANDLER_NAME for handler in root_logger.handlers):
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        file_handler.set_name(_HANDLER_NAME)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    if not any(getattr(handler, "name", "") == _CONSOLE_HANDLER_NAME for handler in root_logger.handlers):
        console_handler = logging.StreamHandler()
        console_handler.set_name(_CONSOLE_HANDLER_NAME)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    for handler in root_logger.handlers:
        if getattr(handler, "name", "") in {_HANDLER_NAME, _CONSOLE_HANDLER_NAME}:
            handler.setLevel(level)

    # Keep external SDK/network logs quiet unless they escalate to a warning or error.
    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    return log_file
