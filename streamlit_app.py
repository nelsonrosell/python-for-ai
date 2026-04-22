import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from app import SqlAgentApp

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


def _check_password() -> bool:
    """Return True if the user has supplied the correct password (or if no
    password is configured, skip the gate entirely)."""
    _load_env()
    required_password = os.environ.get("APP_PASSWORD", "")
    if not required_password:
        # No password configured → open access
        return True

    def _submit() -> None:
        if st.session_state.get("login_password") == required_password:
            st.session_state["authenticated"] = True
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


def _extract_export_path(message: str) -> str:
    marker = " to: "
    if marker not in message:
        return ""
    return message.split(marker, 1)[-1].strip()


def main() -> None:
    _check_password()  # blocks and stops if unauthenticated

    st.set_page_config(page_title="Earthquake Agent",
                       page_icon="🌍", layout="wide")
    st.title("Earthquake Data Agent")
    st.caption(
        "Ask database questions, general questions, request earthquake charts, or run 'export csv SELECT ...'.")

    app = get_app()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    with st.sidebar:
        st.subheader("Quick Actions")

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
        st.subheader("Export Query")
        export_query = st.text_area(
            "SQL SELECT query",
            value="SELECT TOP 10 * FROM earthquake_events_gold",
            height=140,
            key="export_sql_query",
            help="Only SELECT queries are allowed.",
        )

        if st.button("Export Query to CSV", use_container_width=True):
            result = app.export_query_to_csv(export_query.strip())
            st.session_state.messages.append(
                {"role": "assistant", "content": result}
            )
            export_path = _extract_export_path(result)
            if export_path:
                st.session_state["last_export_path"] = export_path

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
            "You can also type: export csv SELECT TOP 10 * FROM earthquake_events_gold")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            image_path = message.get("image_path", "")
            if image_path and Path(image_path).exists():
                st.image(image_path, use_column_width=True)

    prompt = st.chat_input("Ask a question")
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            response_message = run_chat_turn(app, prompt)
            st.markdown(response_message["content"])
            image_path = response_message.get("image_path", "")
            if image_path and Path(image_path).exists():
                st.image(image_path, use_column_width=True)
            st.session_state.messages.append(response_message)
        except Exception as e:
            error_text = f"Error: {e}"
            st.markdown(error_text)
            st.session_state.messages.append(
                {"role": "assistant", "content": error_text}
            )


if __name__ == "__main__":
    main()
