import hmac
import os
import time
from collections.abc import Mapping, MutableMapping
from typing import Any

import streamlit as st

from .env import load_environment

AUTH_SESSION_KEYS = (
    "authenticated",
    "auth_provider",
    "auth_principal",
    "auth_last_verified_at",
    "auth_error_message",
    "password_attempt_count",
    "password_locked_until",
    "login_name",
    "login_password",
)


def get_header_value(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def get_positive_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default

    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"Environment variable {name} must be a positive integer.")
    return parsed


def is_anonymous_dev_auth_allowed() -> bool:
    return os.environ.get("APP_ALLOW_ANONYMOUS_DEV_AUTH", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def get_dev_display_name() -> str:
    configured_name = os.environ.get("APP_DEV_DISPLAY_NAME", "").strip()
    if configured_name:
        return configured_name
    return os.environ.get("USERNAME", "").strip()


def clear_auth_session() -> None:
    for key in AUTH_SESSION_KEYS:
        st.session_state.pop(key, None)


def mark_authenticated(provider: str, principal: str = "") -> None:
    st.session_state["authenticated"] = True
    st.session_state["auth_provider"] = provider
    if principal:
        st.session_state["auth_principal"] = principal
    else:
        st.session_state.pop("auth_principal", None)
    st.session_state["auth_last_verified_at"] = time.time()
    st.session_state["auth_error_message"] = ""
    st.session_state["password_attempt_count"] = 0
    st.session_state["password_locked_until"] = 0.0


def get_ui_auth_principal() -> str:
    principal = st.session_state.get("auth_principal", "").strip()
    if principal:
        return principal

    auth_provider = st.session_state.get("auth_provider", "dev")
    if auth_provider == "dev":
        return get_dev_display_name()
    return ""


def get_generic_prompt_error_message() -> str:
    return (
        "Sorry, something went wrong while processing your request. Please try again."
    )


def expire_auth_session_if_needed(now: float | None = None) -> None:
    if not st.session_state.get("authenticated"):
        return

    timeout_seconds = get_positive_int_env("APP_AUTH_SESSION_TIMEOUT_SECONDS", 1800)
    last_verified_at = float(st.session_state.get("auth_last_verified_at", 0.0) or 0.0)
    if not last_verified_at:
        st.session_state["auth_last_verified_at"] = now or time.time()
        return

    current_time = now or time.time()
    if current_time - last_verified_at > timeout_seconds:
        clear_auth_session()
        st.session_state["auth_error_message"] = (
            "Session expired. Please sign in again."
        )


def get_password_lock_state(
    session_state: MutableMapping[str, Any], now: float | None = None
) -> tuple[bool, str]:
    locked_until = float(session_state.get("password_locked_until", 0.0) or 0.0)
    if not locked_until:
        return False, ""

    current_time = now or time.time()
    if current_time >= locked_until:
        session_state["password_locked_until"] = 0.0
        session_state["password_attempt_count"] = 0
        return False, ""

    remaining_seconds = max(1, int(locked_until - current_time))
    return True, (
        f"Too many incorrect password attempts. Try again in {remaining_seconds} second(s)."
    )


def record_failed_password_attempt(
    session_state: MutableMapping[str, Any], now: float | None = None
) -> str:
    max_attempts = get_positive_int_env("APP_PASSWORD_MAX_ATTEMPTS", 5)
    lockout_seconds = get_positive_int_env("APP_PASSWORD_LOCKOUT_SECONDS", 60)

    attempts = int(session_state.get("password_attempt_count", 0) or 0) + 1
    session_state["password_attempt_count"] = attempts
    if attempts >= max_attempts:
        current_time = now or time.time()
        session_state["password_locked_until"] = current_time + lockout_seconds
        return f"Too many incorrect password attempts. Try again in {lockout_seconds} second(s)."
    return "Incorrect password. Please try again."


def validate_trusted_header_auth_config(app_env: str) -> str:
    trusted_header = os.environ.get("APP_TRUSTED_AUTH_HEADER", "").strip()
    expected_value = os.environ.get("APP_TRUSTED_AUTH_VALUE", "").strip()
    user_header = os.environ.get("APP_TRUSTED_USER_HEADER", "").strip()

    if not trusted_header:
        return ""

    if app_env == "dev":
        return ""

    if not expected_value:
        return (
            "APP_TRUSTED_AUTH_VALUE must be configured when APP_TRUSTED_AUTH_HEADER "
            "is used outside dev."
        )

    if not user_header:
        return (
            "APP_TRUSTED_USER_HEADER must be configured when trusted-header auth "
            "is used outside dev."
        )

    if user_header.lower() == trusted_header.lower():
        return (
            "APP_TRUSTED_USER_HEADER must be different from APP_TRUSTED_AUTH_HEADER "
            "outside dev."
        )

    return ""


def check_trusted_header_auth(headers: Mapping[str, str]) -> tuple[bool, str]:
    trusted_header = os.environ.get("APP_TRUSTED_AUTH_HEADER", "").strip()
    if not trusted_header:
        return False, ""

    header_value = get_header_value(headers, trusted_header)
    if not header_value:
        return False, ""

    expected_value = os.environ.get("APP_TRUSTED_AUTH_VALUE", "").strip()
    if expected_value and header_value != expected_value:
        return False, ""

    user_header = os.environ.get("APP_TRUSTED_USER_HEADER", "").strip()
    if user_header:
        principal = get_header_value(headers, user_header)
    elif expected_value:
        principal = trusted_header
    else:
        principal = header_value

    return True, principal or header_value


def check_password() -> bool:
    """Return True when the Streamlit request is authenticated."""
    load_environment()
    app_env = os.environ.get("APP_ENV", "dev").lower()
    expire_auth_session_if_needed()

    trusted_auth_config_error = validate_trusted_header_auth_config(app_env)
    if trusted_auth_config_error:
        st.set_page_config(
            page_title="Earthquake Agent - Configuration Error", page_icon="Lock"
        )
        st.title("Authentication configuration error")
        st.error(trusted_auth_config_error)
        st.stop()
        return False

    trusted_auth, principal = check_trusted_header_auth(dict(st.context.headers))
    if trusted_auth:
        mark_authenticated("trusted-header", principal)
        return True

    required_password = os.environ.get("APP_PASSWORD", "")
    if not required_password:
        if app_env == "dev" and is_anonymous_dev_auth_allowed():
            return True

        st.set_page_config(
            page_title="Earthquake Agent - Configuration Error", page_icon="Lock"
        )
        st.title("Password required")
        st.error(
            "Configure APP_PASSWORD or a trusted auth header. Anonymous access is only allowed when APP_ALLOW_ANONYMOUS_DEV_AUTH=true in dev."
        )
        st.stop()
        return False

    def _submit() -> None:
        locked, message = get_password_lock_state(st.session_state)
        if locked:
            st.session_state["auth_error_message"] = message
            return

        entered = st.session_state.get("login_password", "")
        entered_name = st.session_state.get("login_name", "").strip()
        if hmac.compare_digest(entered, required_password):
            mark_authenticated("password", entered_name)
        else:
            st.session_state["auth_error_message"] = record_failed_password_attempt(
                st.session_state
            )

    if st.session_state.get("authenticated"):
        st.session_state["auth_last_verified_at"] = time.time()
        return True

    st.set_page_config(page_title="Earthquake Agent - Login", page_icon="Lock")
    st.title("Login required")
    st.text_input(
        "Name",
        key="login_name",
        help="Optional display name shown in the UI after sign-in.",
    )
    st.text_input(
        "Password",
        type="password",
        key="login_password",
        on_change=_submit,
    )
    if st.button("Sign in"):
        _submit()
    auth_error_message = st.session_state.get("auth_error_message", "")
    if auth_error_message:
        st.error(auth_error_message)
        st.session_state["auth_error_message"] = ""
    st.stop()
    return False
