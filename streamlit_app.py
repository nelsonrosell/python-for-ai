import os
import hmac
import re
import time
from pathlib import Path
from typing import Any, Mapping, MutableMapping

import streamlit as st

from app import SqlAgentApp
from app.env import load_environment


CHATGPT_STYLE_PATH = Path(__file__).with_name("streamlit_app.css")
AUTH_SESSION_KEYS = (
    "authenticated",
    "auth_provider",
    "auth_principal",
    "auth_last_verified_at",
)

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _get_header_value(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def _get_positive_int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default

    parsed = int(value)
    if parsed <= 0:
        raise ValueError(
            f"Environment variable {name} must be a positive integer.")
    return parsed


def _is_anonymous_dev_auth_allowed() -> bool:
    return os.environ.get("APP_ALLOW_ANONYMOUS_DEV_AUTH", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _get_dev_display_name() -> str:
    configured_name = os.environ.get("APP_DEV_DISPLAY_NAME", "").strip()
    if configured_name:
        return configured_name
    return os.environ.get("USERNAME", "").strip()


def _clear_auth_session() -> None:
    for key in AUTH_SESSION_KEYS:
        st.session_state.pop(key, None)


def _mark_authenticated(provider: str, principal: str = "") -> None:
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


def _get_ui_auth_principal() -> str:
    principal = st.session_state.get("auth_principal", "").strip()
    if principal:
        return principal

    auth_provider = st.session_state.get("auth_provider", "dev")
    if auth_provider == "dev":
        return _get_dev_display_name()
    return ""


def _expire_auth_session_if_needed(now: float | None = None) -> None:
    if not st.session_state.get("authenticated"):
        return

    timeout_seconds = _get_positive_int_env(
        "APP_AUTH_SESSION_TIMEOUT_SECONDS", 1800)
    last_verified_at = float(st.session_state.get(
        "auth_last_verified_at", 0.0) or 0.0)
    if not last_verified_at:
        st.session_state["auth_last_verified_at"] = now or time.time()
        return

    current_time = now or time.time()
    if current_time - last_verified_at > timeout_seconds:
        _clear_auth_session()
        st.session_state["auth_error_message"] = "Session expired. Please sign in again."


def _get_password_lock_state(
    session_state: MutableMapping[str, Any], now: float | None = None
) -> tuple[bool, str]:
    locked_until = float(session_state.get(
        "password_locked_until", 0.0) or 0.0)
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


def _record_failed_password_attempt(
    session_state: MutableMapping[str, Any], now: float | None = None
) -> str:
    max_attempts = _get_positive_int_env("APP_PASSWORD_MAX_ATTEMPTS", 5)
    lockout_seconds = _get_positive_int_env("APP_PASSWORD_LOCKOUT_SECONDS", 60)

    attempts = int(session_state.get("password_attempt_count", 0) or 0) + 1
    session_state["password_attempt_count"] = attempts
    if attempts >= max_attempts:
        current_time = now or time.time()
        session_state["password_locked_until"] = current_time + lockout_seconds
        return (
            f"Too many incorrect password attempts. Try again in {lockout_seconds} second(s)."
        )
    return "Incorrect password. Please try again."


def _validate_trusted_header_auth_config(app_env: str) -> str:
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


def _check_trusted_header_auth(headers: Mapping[str, str]) -> tuple[bool, str]:
    trusted_header = os.environ.get("APP_TRUSTED_AUTH_HEADER", "").strip()
    if not trusted_header:
        return False, ""

    header_value = _get_header_value(headers, trusted_header)
    if not header_value:
        return False, ""

    expected_value = os.environ.get("APP_TRUSTED_AUTH_VALUE", "").strip()
    if expected_value and header_value != expected_value:
        return False, ""

    user_header = os.environ.get("APP_TRUSTED_USER_HEADER", "").strip()
    if user_header:
        principal = _get_header_value(headers, user_header)
    elif expected_value:
        principal = trusted_header
    else:
        principal = header_value

    return True, principal or header_value


def _check_password() -> bool:
    """Return True if the user has supplied the correct password (or if no
    password is configured, skip the gate entirely)."""
    load_environment()
    app_env = os.environ.get("APP_ENV", "dev").lower()
    _expire_auth_session_if_needed()

    trusted_auth_config_error = _validate_trusted_header_auth_config(app_env)
    if trusted_auth_config_error:
        st.set_page_config(
            page_title="Earthquake Agent – Configuration Error", page_icon="🔒"
        )
        st.title("🔒 Authentication configuration error")
        st.error(trusted_auth_config_error)
        st.stop()
        return False

    trusted_auth, principal = _check_trusted_header_auth(
        dict(st.context.headers))
    if trusted_auth:
        _mark_authenticated("trusted-header", principal)
        return True

    required_password = os.environ.get("APP_PASSWORD", "")
    if not required_password:
        if app_env == "dev" and _is_anonymous_dev_auth_allowed():
            return True

        st.set_page_config(
            page_title="Earthquake Agent – Configuration Error", page_icon="🔒"
        )
        st.title("🔒 Password required")
        st.error(
            "Configure APP_PASSWORD or a trusted auth header. Anonymous access is only allowed when APP_ALLOW_ANONYMOUS_DEV_AUTH=true in dev."
        )
        st.stop()
        return False

    def _submit() -> None:
        locked, message = _get_password_lock_state(st.session_state)
        if locked:
            st.session_state["auth_error_message"] = message
            return

        entered = st.session_state.get("login_password", "")
        entered_name = st.session_state.get("login_name", "").strip()
        if hmac.compare_digest(entered, required_password):
            _mark_authenticated("password", entered_name)
        else:
            st.session_state["auth_error_message"] = _record_failed_password_attempt(
                st.session_state
            )

    if st.session_state.get("authenticated"):
        st.session_state["auth_last_verified_at"] = time.time()
        return True

    st.set_page_config(page_title="Earthquake Agent – Login", page_icon="🔒")
    st.title("🔒 Login required")
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
    return False  # never reached; st.stop() halts execution


def _render_sign_out_button() -> None:
    if st.button("Sign out", use_container_width=True):
        _clear_auth_session()
        st.rerun()


def is_chart_request(question: str) -> bool:
    normalized = question.lower()
    has_chart_intent = any(
        token in normalized for token in ["graph", "chart", "plot", "visualize"]
    )
    has_earthquake_context = any(
        token in normalized for token in ["earthquake", "earthquakes"]
    )
    return has_chart_intent and has_earthquake_context


def get_app() -> SqlAgentApp:
    if "agent_app" not in st.session_state:
        st.session_state.agent_app = SqlAgentApp()
    return st.session_state.agent_app


def run_chat_turn(app: SqlAgentApp, question: str) -> dict[str, str]:
    normalized = question.lower()

    if normalized.startswith("export csv "):
        sql_query = question[len("export csv "):].strip()
        return {
            "role": "assistant",
            "content": app.export_query_to_csv(sql_query),
        }

    if is_chart_request(question):
        if "pie" in normalized:
            path = app.generate_earthquake_pie_chart()
            return {
                "role": "assistant",
                "content": f"Pie chart generated: {path}",
                "image_path": path,
            }

        path = app.generate_earthquake_bar_chart()
        return {
            "role": "assistant",
            "content": f"Bar chart generated: {path}",
            "image_path": path,
        }

    answer = app.ask(question)
    return {"role": "assistant", "content": answer}


def _submit_prompt(app: SqlAgentApp, prompt: str) -> None:
    st.session_state.messages.append({"role": "user", "content": prompt})
    try:
        response_message = run_chat_turn(app, prompt)
        st.session_state.messages.append(response_message)
    except Exception as e:
        error_text = f"Error: {e}"
        st.session_state.messages.append(
            {"role": "assistant", "content": error_text})


def _queue_prompt(prompt: str) -> None:
    st.session_state.pending_prompt = prompt
    st.session_state.awaiting_response = True
    st.session_state.pending_prompt_ready = False


def _process_pending_prompt(app: SqlAgentApp) -> None:
    prompt = st.session_state.get("pending_prompt", "").strip()
    if not prompt:
        st.session_state.awaiting_response = False
        st.session_state.pending_prompt_ready = False
        return

    _submit_prompt(app, prompt)

    st.session_state.pending_prompt = ""
    st.session_state.awaiting_response = False
    st.session_state.pending_prompt_ready = False
    st.rerun()


def _extract_export_path(message: str) -> str:
    marker = " to: "
    if marker not in message:
        return ""
    return message.split(marker, 1)[-1].strip()


def _parse_markdown_table(table_lines: list[str]) -> list[dict[str, str]]:
    if len(table_lines) < 3:
        return []

    def _cells(line: str) -> list[str]:
        # Split only on real table delimiters, not escaped pipes inside values.
        parts = [part.strip() for part in re.split(r"(?<!\\)\|", line)]

        normalized: list[str] = []
        for part in parts:
            if not part:
                continue

            cell = part.replace(r"\|", "|").strip()

            # If a model returns escaped wrapper pipes in a cell, unwrap them.
            if cell.startswith("|") and cell.endswith("|") and len(cell) > 1:
                cell = cell[1:-1].strip()

            if cell:
                normalized.append(cell)

        return normalized

    headers = _cells(table_lines[0])
    if not headers:
        return []

    rows: list[dict[str, str]] = []
    for row_line in table_lines[2:]:
        values = _cells(row_line)
        if not values:
            continue
        normalized_values = values + [""] * max(0, len(headers) - len(values))
        row = {headers[idx]: normalized_values[idx]
               for idx in range(len(headers))}
        rows.append(row)
    return rows


def _split_markdown_content(text: str) -> list[tuple[str, str | list[dict[str, str]]]]:
    """Split content into text and table segments; supports multiple tables."""
    lines = text.splitlines()
    segments: list[tuple[str, str | list[dict[str, str]]]] = []
    text_buffer: list[str] = []
    i = 0

    while i < len(lines):
        current = lines[i].strip()
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""

        is_table_header = (
            current.startswith("|")
            and next_line.startswith("|")
            and re.search(r"-", next_line)
        )
        if not is_table_header:
            text_buffer.append(lines[i])
            i += 1
            continue

        if text_buffer:
            text_segment = "\n".join(text_buffer).strip()
            if text_segment:
                segments.append(("text", text_segment))
            text_buffer = []

        table_lines: list[str] = [lines[i].strip(), lines[i + 1].strip()]
        i += 2
        while i < len(lines):
            row_line = lines[i].strip()
            if row_line.startswith("|"):
                table_lines.append(row_line)
                i += 1
                continue
            if not row_line:
                i += 1
                continue
            break

        rows = _parse_markdown_table(table_lines)
        if rows:
            segments.append(("table", rows))
        else:
            segments.append(("text", "\n".join(table_lines)))

    if text_buffer:
        text_segment = "\n".join(text_buffer).strip()
        if text_segment:
            segments.append(("text", text_segment))

    if not segments:
        return [("text", text)]
    return segments


def _render_message_content(content: str) -> None:
    segments = _split_markdown_content(content)
    for kind, payload in segments:
        if kind == "table":
            st.table(payload)
        else:
            st.markdown(payload)


def _inject_chat_ui_styles() -> None:
    stylesheet = CHATGPT_STYLE_PATH.read_text(encoding="utf-8")
    st.markdown(f"<style>{stylesheet}</style>", unsafe_allow_html=True)


def _render_chat_shell() -> None:
    st.markdown(
        """
        <div class="chat-shell">
            <h1>Earthquake Data Agent</h1>
            <p>
                Ask questions about earthquake data, request quick charts, or export a safe SQL result set.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_empty_state() -> None:
    st.markdown(
        """
        <div class="welcome-card">
            <strong>Start with a prompt</strong>
            <p>Try: “Show the top countries by earthquake count”, “Generate a pie chart”, or “export csv SELECT TOP 10 * FROM earthquake_events_gold”.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_starter_prompts(app: SqlAgentApp) -> None:
    st.markdown("#### Try one of these")
    st.markdown('<div class="starter-prompts">', unsafe_allow_html=True)
    columns = st.columns(3)
    suggestions = [
        "Show the top countries by earthquake count",
        "Generate a pie chart of earthquakes by country",
        "export csv SELECT TOP 10 * FROM earthquake_events_gold",
    ]

    for idx, suggestion in enumerate(suggestions):
        if columns[idx].button(
            suggestion, key=f"starter_prompt_{idx}", use_container_width=True
        ):
            _submit_prompt(app, suggestion)
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def _render_centered_prompt_form(*, show_loading: bool = False) -> str | None:
    outer_left, prompt_area, outer_right = st.columns([1.3, 6.7, 1])
    with prompt_area:
        if show_loading:
            _render_loading_status(compact=True)

        st.markdown('<div class="centered-prompt-shell">',
                    unsafe_allow_html=True)
        with st.form("center_prompt_form", clear_on_submit=True, border=False):
            prompt = st.text_input(
                "Ask me about your data or even general questions",
                placeholder="Ask me about your data or even general questions",
                key="center_prompt_text",
                label_visibility="collapsed",
            )
            submitted = st.form_submit_button(
                "Send",
                use_container_width=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

    if submitted and prompt.strip():
        return prompt.strip()
    return None


def _render_loading_status(*, floating: bool = False, compact: bool = False) -> None:
    class_names = ["floating-answer-status"]
    if floating:
        class_names.append("floating-answer-status--fixed")
    if compact:
        class_names.append("floating-answer-status--compact")

    st.markdown(
        f"""
        <div class="{' '.join(class_names)}" aria-live="polite">
            <span class="floating-answer-status__spinner" aria-hidden="true"></span>
            <span class="floating-answer-status__label">Searching for an answer...</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _has_assistant_messages() -> bool:
    return any(
        message.get("role") == "assistant" for message in st.session_state.messages
    )


def _render_export_expander(app: SqlAgentApp) -> None:
    st.markdown('<div class="export-expander">', unsafe_allow_html=True)
    with st.expander("Export data", expanded=False):
        st.caption(
            f"Single-statement SELECT TOP (n) only. Maximum export size: TOP ({app.config.max_export_rows})."
        )
        export_query = st.text_area(
            "SQL SELECT query",
            value="SELECT TOP 10 * FROM earthquake_events_gold",
            height=140,
            key="export_sql_query",
            help=f"Only single-statement SELECT TOP (n) queries are allowed. Maximum export size: TOP ({app.config.max_export_rows}).",
        )

        if st.button(
            "Export Query to CSV", key="main_export_button", use_container_width=True
        ):
            result = app.export_query_to_csv(export_query.strip())
            st.session_state.messages.append(
                {"role": "assistant", "content": result})
            export_path = _extract_export_path(result)
            if export_path:
                st.session_state["last_export_path"] = export_path
            st.rerun()

        last_export_path = st.session_state.get("last_export_path", "")
        if last_export_path and Path(last_export_path).exists():
            with open(last_export_path, "rb") as export_file:
                st.download_button(
                    "Download Latest CSV",
                    data=export_file.read(),
                    file_name=Path(last_export_path).name,
                    mime="text/csv",
                    use_container_width=True,
                )

        st.caption(
            f"You can also type: export csv SELECT TOP 10 * FROM earthquake_events_gold. Maximum export size: TOP ({app.config.max_export_rows})."
        )
    st.markdown("</div>", unsafe_allow_html=True)


def main() -> None:
    _check_password()  # blocks and stops if unauthenticated

    st.set_page_config(
        page_title="Earthquake Agent",
        page_icon="🌍",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    _inject_chat_ui_styles()
    _render_chat_shell()

    app = get_app()

    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "pending_prompt" not in st.session_state:
        st.session_state.pending_prompt = ""
    if "awaiting_response" not in st.session_state:
        st.session_state.awaiting_response = False
    if "pending_prompt_ready" not in st.session_state:
        st.session_state.pending_prompt_ready = False

    has_messages = bool(st.session_state.messages)
    has_pending_prompt = bool(st.session_state.pending_prompt)

    if not has_messages:
        first_prompt = _render_centered_prompt_form(
            show_loading=has_pending_prompt and st.session_state.pending_prompt_ready
        )
        if first_prompt:
            _queue_prompt(first_prompt)
            st.rerun()

        if has_pending_prompt:
            if st.session_state.pending_prompt_ready:
                _process_pending_prompt(app)
            else:
                st.session_state.pending_prompt_ready = True
                st.rerun()

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            _render_message_content(message["content"])
            image_path = message.get("image_path", "")
            if image_path and Path(image_path).exists():
                st.image(image_path, use_column_width=True)

    with st.sidebar:
        st.markdown("### Workspace")
        st.caption("Chat, charts, context, and export tools.")
        auth_provider = st.session_state.get("auth_provider", "dev")
        auth_principal = _get_ui_auth_principal()
        if auth_principal:
            st.caption(f"Authenticated via {auth_provider}: {auth_principal}")
        elif auth_provider != "dev":
            st.caption(f"Authenticated via {auth_provider}")
        if st.session_state.get("authenticated"):
            _render_sign_out_button()

        st.divider()
        st.markdown("#### Actions")

        if st.button("Generate Bar Chart by Country", use_container_width=True):
            chart_path = app.generate_earthquake_bar_chart()
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": f"Bar chart generated: {chart_path}",
                    "image_path": chart_path,
                }
            )

        if st.button("Generate Pie Chart by Country", use_container_width=True):
            chart_path = app.generate_earthquake_pie_chart()
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": f"Pie chart generated: {chart_path}",
                    "image_path": chart_path,
                }
            )

        if st.button("Show Context", use_container_width=True):
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": app._format_context_history(),
                }
            )

        if st.button("Reset Context", use_container_width=True):
            app.chat_history.clear()
            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": "Context cleared.",
                }
            )

        if st.button("Clear Chat Window", use_container_width=True):
            st.session_state.messages = []

        st.divider()
        if not _has_assistant_messages():
            st.markdown("#### Suggestions")
            _render_empty_state()
            _render_starter_prompts(app)

        st.divider()
        st.markdown("#### Export")
        _render_export_expander(app)

    if has_messages:
        if has_pending_prompt and st.session_state.pending_prompt_ready:
            _render_loading_status(floating=True)

        prompt = st.chat_input(
            "Ask me about your data or even general questions")
        if prompt:
            _queue_prompt(prompt)
            st.rerun()

        if has_pending_prompt:
            if st.session_state.pending_prompt_ready:
                _process_pending_prompt(app)
            else:
                st.session_state.pending_prompt_ready = True
                st.rerun()


if __name__ == "__main__":
    main()
