import os
import hmac
import re
from pathlib import Path
from typing import Mapping

import streamlit as st

from app import SqlAgentApp
from app.env import load_environment


CHATGPT_STYLE_PATH = Path(__file__).with_name("streamlit_app.css")

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


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
    load_environment()
    app_env = os.environ.get("APP_ENV", "dev").lower()
    trusted_auth, principal = _check_trusted_header_auth(
        dict(st.context.headers))
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

    with st.spinner("Searching for an answer..."):
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


def _render_centered_prompt_form() -> str | None:
    outer_left, prompt_area, outer_right = st.columns([1.3, 6.7, 1])
    with prompt_area:
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
        if has_pending_prompt:
            if st.session_state.pending_prompt_ready:
                _process_pending_prompt(app)
            else:
                st.session_state.pending_prompt_ready = True
                st.rerun()

        first_prompt = _render_centered_prompt_form()
        if first_prompt:
            _queue_prompt(first_prompt)
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

    if has_messages:
        if has_pending_prompt:
            if st.session_state.pending_prompt_ready:
                _process_pending_prompt(app)
            else:
                st.session_state.pending_prompt_ready = True
                st.rerun()

        prompt = st.chat_input(
            "Ask me about your data or even general questions")
        if prompt:
            _queue_prompt(prompt)
            st.rerun()


if __name__ == "__main__":
    main()
