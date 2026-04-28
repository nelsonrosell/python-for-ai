import os
import hmac
import re
from pathlib import Path
from typing import Mapping

import streamlit as st
from dotenv import load_dotenv

from app import SqlAgentApp


CHATGPT_STYLE = """
<style>
    :root {
        --surface: var(--background-color);
        --surface-alt: var(--secondary-background-color);
        --border: color-mix(in srgb, var(--text-color) 12%, transparent);
        --text: var(--text-color);
        --text-muted: color-mix(in srgb, var(--text-color) 62%, transparent);
        --accent: var(--primary-color);
    }

    [data-testid="stSidebar"] {
        border-right: 1px solid var(--border);
    }

    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"],
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span {
        color: var(--text);
    }

    [data-testid="stSidebar"] .stButton > button,
    [data-testid="stSidebar"] .stDownloadButton > button {
        border-radius: 0.9rem;
        border: 1px solid var(--border);
        background: var(--surface-alt);
        color: var(--text);
    }

    [data-testid="stSidebar"] textarea {
        border-radius: 0.85rem;
    }

    .stButton > button {
        border-radius: 999px;
        border: 1px solid color-mix(in srgb, var(--accent) 26%, transparent);
        color: var(--text);
        padding: 0.38rem 0.85rem;
        min-height: 0;
    }

    .stButton > button p {
        font-size: 0.86rem;
    }

    [data-testid="stMainBlockContainer"] {
        max-width: 980px;
        padding-top: 1.5rem;
        padding-bottom: 6rem;
    }

    .chat-shell {
        margin: 0 auto 1.4rem auto;
        padding: 1.2rem 1.35rem;
        border: 1px solid var(--border);
        border-radius: 1.2rem;
        backdrop-filter: blur(18px);
    }

    .chat-shell h1 {
        margin: 0;
        color: var(--text);
        font-size: 1.9rem;
        font-weight: 650;
        letter-spacing: -0.02em;
    }

    .chat-shell p {
        margin: 0.45rem 0 0 0;
        color: var(--text-muted);
        line-height: 1.55;
    }

    .chat-shell .pill-row {
        display: flex;
        gap: 0.55rem;
        flex-wrap: wrap;
        margin-top: 0.95rem;
    }

    .chat-shell .pill {
        padding: 0.36rem 0.7rem;
        border-radius: 999px;
        border: 1px solid color-mix(in srgb, var(--accent) 26%, transparent);
        color: var(--text);
        font-size: 0.84rem;
    }

    .welcome-card {
        margin: 1.2rem auto 1.6rem auto;
        max-width: 720px;
        padding: 1.1rem 1.2rem;
        border: 1px solid var(--border);
        border-radius: 1rem;
    }

    .welcome-card strong {
        color: var(--text);
    }

    .welcome-card p {
        margin: 0.2rem 0 0 0;
        color: var(--text-muted);
    }

    [data-testid="stChatMessage"] {
        margin-bottom: 1rem;
        padding: 1rem 1.15rem;
        border: 1px solid var(--border);
        border-radius: 1.15rem;
        max-width: 86%;
    }

    [data-testid="stChatMessage"]:last-of-type {
        margin-bottom: 0.3rem;
    }

    [aria-label="Chat message from user"] {
        border-color: color-mix(in srgb, var(--accent) 30%, transparent);
        margin-left: auto;
        margin-right: 0;
        max-width: 72%;
    }

    [aria-label="Chat message from assistant"] {
        border-color: var(--border);
        margin-left: 0;
        margin-right: auto;
    }

    [aria-label="Chat message from user"] [data-testid="stMarkdownContainer"] p,
    [aria-label="Chat message from user"] [data-testid="stMarkdownContainer"] li,
    [aria-label="Chat message from user"] [data-testid="stMarkdownContainer"] span {
        color: var(--text);
    }

    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] span {
        color: var(--text);
        line-height: 1.65;
    }

    .export-expander {
        margin: 0 auto 1.4rem auto;
        border: 1px solid var(--border);
        border-radius: 1rem;
        overflow: hidden;
    }

    .export-expander [data-testid="stExpander"] {
        border: none;
        background: transparent;
    }

    .export-expander [data-testid="stExpander"] details {
        background: transparent;
    }

    .export-expander [data-testid="stExpander"] summary {
        color: var(--text);
        font-weight: 600;
    }

    .export-expander [data-testid="stExpanderDetails"] {
        background: transparent;
    }

    .starter-prompts {
        margin-top: 0.7rem;
    }

    .assistant-loading {
        display: inline-flex;
        align-items: center;
        gap: 0.55rem;
        padding: 0.15rem 0;
        color: var(--text-muted);
        font-size: 0.95rem;
    }

    .assistant-loading .dot {
        width: 0.42rem;
        height: 0.42rem;
        border-radius: 999px;
        background: var(--accent);
        box-shadow: 0 0 0 0 rgba(25, 195, 125, 0.6);
        animation: pulseDot 1.2s infinite ease-in-out;
    }

    @keyframes pulseDot {
        0% { transform: scale(0.88); opacity: 0.65; }
        50% { transform: scale(1.15); opacity: 1; }
        100% { transform: scale(0.88); opacity: 0.65; }
    }

    [data-testid="stChatInput"] {
        max-width: 980px;
        padding-left: 1.8rem;
        padding-right: 1.8rem;
        margin-left: auto;
        margin-right: auto;
        width: 100%;
        box-sizing: border-box;
    }

    .block-container {
        padding-left: 1.8rem;
        padding-right: 1.8rem;
    }

    @media (max-width: 900px) {
        .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }

        [data-testid="stChatInput"] {
            padding-left: 1rem;
            padding-right: 1rem;
        }

        .chat-shell h1 {
            font-size: 1.55rem;
        }
    }
</style>
"""

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

_ENV_LOADED = False


def _load_env() -> None:
    global _ENV_LOADED
    if not _ENV_LOADED:
        app_env = os.environ.get("APP_ENV", "dev")
        env_file = Path(f".env.{app_env}")
        if not env_file.exists():
            env_file = Path(".env")
        load_dotenv(env_file, override=False)
        _ENV_LOADED = True


def _get_header_value(headers: Mapping[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
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
    _load_env()
    app_env = os.environ.get("APP_ENV", "dev").lower()
    trusted_auth, principal = _check_trusted_header_auth(dict(st.context.headers))
    if trusted_auth:
        st.session_state["authenticated"] = True
        st.session_state["auth_provider"] = "trusted-header"
        st.session_state["auth_principal"] = principal
        return True

    required_password = os.environ.get("APP_PASSWORD", "")
    if not required_password:
        if app_env == "dev":
            return True

        st.set_page_config(
            page_title="Earthquake Agent – Configuration Error", page_icon="🔒"
        )
        st.title("🔒 Password required")
        st.error(
            "Configure APP_PASSWORD or a trusted auth header when APP_ENV is not 'dev'."
        )
        st.stop()
        return False

    def _submit() -> None:
        entered = st.session_state.get("login_password", "")
        if hmac.compare_digest(entered, required_password):
            st.session_state["authenticated"] = True
            st.session_state["auth_provider"] = "password"
        else:
            st.session_state["auth_error"] = True

    if st.session_state.get("authenticated"):
        return True

    st.set_page_config(page_title="Earthquake Agent – Login", page_icon="🔒")
    st.title("🔒 Login required")
    st.text_input(
        "Password",
        type="password",
        key="login_password",
        on_change=_submit,
    )
    if st.button("Sign in"):
        _submit()
    if st.session_state.get("auth_error"):
        st.error("Incorrect password. Please try again.")
        st.session_state["auth_error"] = False
    st.stop()
    return False  # never reached; st.stop() halts execution


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
        sql_query = question[len("export csv ") :].strip()
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
        st.session_state.messages.append({"role": "assistant", "content": error_text})


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
        row = {headers[idx]: normalized_values[idx] for idx in range(len(headers))}
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
    st.markdown(CHATGPT_STYLE, unsafe_allow_html=True)


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


def _render_centered_prompt_form() -> str | None:
    with st.form("center_prompt_form", clear_on_submit=True, border=False):
        prompt_col, button_col = st.columns([10.5, 1.1])
        with prompt_col:
            prompt = st.text_input(
                "Ask me about your data or even general questions",
                placeholder="Ask me about your data or even general questions",
                key="center_prompt_text",
                label_visibility="collapsed",
            )
        with button_col:
            submitted = st.form_submit_button(
                "Send",
                use_container_width=True,
            )

    if submitted and prompt.strip():
        return prompt.strip()
    return None


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
            st.session_state.messages.append({"role": "assistant", "content": result})
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

    with st.sidebar:
        st.markdown("### Workspace")
        st.caption("Chat, charts, context, and export tools.")
        auth_provider = st.session_state.get("auth_provider", "dev")
        auth_principal = st.session_state.get("auth_principal", "")
        if auth_principal:
            st.caption(f"Authenticated via {auth_provider}: {auth_principal}")
        elif auth_provider != "dev":
            st.caption(f"Authenticated via {auth_provider}")

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

    prompt = st.chat_input("Ask me about your data or even general questions")
    if prompt:
        _submit_prompt(app, prompt)

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            _render_message_content(message["content"])
            image_path = message.get("image_path", "")
            if image_path and Path(image_path).exists():
                st.image(image_path, use_column_width=True)


if __name__ == "__main__":
    main()
