import os
from pathlib import Path

from dotenv import load_dotenv


_ENV_LOADED = False


def load_environment() -> Path:
    """Load the active environment file once and return the resolved path used."""
    global _ENV_LOADED

    app_env = os.getenv("APP_ENV", "dev").lower()
    base_dir = Path(__file__).resolve().parent.parent
    env_file = base_dir / f".env.{app_env}"
    fallback = base_dir / ".env"

    if env_file.exists():
        chosen = env_file
    elif fallback.exists():
        chosen = fallback
    else:
        raise FileNotFoundError(
            f"No environment file found. Expected '{env_file}' or '{fallback}'."
        )

    if not _ENV_LOADED:
        load_dotenv(chosen, override=False)
        _ENV_LOADED = True

    return chosen