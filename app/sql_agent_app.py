import struct
import logging
import warnings
from urllib.parse import quote_plus
from typing import Any

from azure.identity import (
    AzureCliCredential,
    ChainedTokenCredential,
    InteractiveBrowserCredential,
)
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.utilities import SQLDatabase
from langchain_openai import AzureChatOpenAI
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url

from .config import AppConfig, load_config
from .email_rules import (
    build_email_payload,
    build_email_subject,
    get_email_configuration_error,
    get_last_shareable_answer,
)
from .email_utils import GraphMailSender
from .export import export_rows_to_csv
from .request_routing import (
    is_database_question,
    is_follow_up_question,
    is_table_format_follow_up,
    parse_email_request,
)
from .sql_agent_prompt import build_agent_prefix
from .sql_guardrails import (
    DEFAULT_MAX_EXPORT_ROWS,
    validate_allowed_tables,
    validate_export_query,
    validate_query,
    validate_sql,
)
from .table_formatting import (
    build_table_format_prompt,
    to_markdown_table,
)
from .visualization import EarthquakeVisualizer


SQL_ACCESS_TOKEN_ATTRIBUTE = 1256
SQL_ACCESS_TOKEN_SCOPE = "https://database.windows.net/.default"
DEFAULT_MAX_EXPORT_ROWS = 500
LOGGER = logging.getLogger(__name__)
warnings.filterwarnings(
    "ignore",
    message=r"response_mode='form_post' is recommended for better security\..*",
    category=UserWarning,
    module=r"msal\.oauth2cli\.oauth2",
)


class SqlAgentApp:
    def __init__(self, config: AppConfig | None = None) -> None:
        """Initialise the app: connect to the database, apply the SQL guard,
        create the LLM, the visualizer, and the LangChain agent.
        Accepts an optional pre-built AppConfig; otherwise loads one from env.
        """
        self.config = config or load_config()
        self.db = self._create_db()
        # guard applied at db.run() so all execution paths are covered
        self._patch_db_with_guard()
        self.general_llm = self._create_llm()
        self.visualizer = EarthquakeVisualizer()
        self.chat_history: list[dict[str, str]] = []
        self.max_history_turns = 8
        self.agent = self._create_agent()

    def _create_llm(self) -> AzureChatOpenAI:
        """Instantiate and return an AzureChatOpenAI client using credentials
        from the app config. Temperature is fixed at 0 for deterministic SQL generation.
        """
        return AzureChatOpenAI(
            azure_endpoint=self.config.azure_openai_endpoint,
            api_key=self.config.azure_openai_api_key,
            api_version=self.config.azure_openai_api_version,
            azure_deployment=self.config.azure_openai_deployment,
            temperature=0,
        )

    def _is_sqlalchemy_uri(self, connection_string: str) -> bool:
        """Return True if the connection string is a SQLAlchemy URI (contains '://'),
        as opposed to a raw ODBC connection string.
        """
        return "://" in connection_string

    def _create_token_credential(self) -> ChainedTokenCredential:
        """Build a ChainedTokenCredential that tries, in order:
        1. InteractiveBrowserCredential with a login hint (if configured).
        2. AzureCliCredential (works when the developer is already logged in via 'az login').
        3. InteractiveBrowserCredential without a hint (fallback pop-up).

        When a login hint is configured, prefer the interactive credential first
        so the app authenticates with that intended Entra user instead of any
        unrelated Azure CLI session already present on the machine.
        """
        credentials = []

        if self.config.sql_entra_login_hint:
            credentials.append(
                InteractiveBrowserCredential(
                    login_hint=self.config.sql_entra_login_hint,
                )
            )

        credentials.append(AzureCliCredential())

        if not self.config.sql_entra_login_hint:
            credentials.append(InteractiveBrowserCredential())

        return ChainedTokenCredential(*credentials)

    def _build_access_token_struct(self, token: str) -> bytes:
        """Encode a bearer token string into the binary struct expected by the
        ODBC SQL_ACCESS_TOKEN connection attribute (SQL_COPT_SS_ACCESS_TOKEN).
        The format is a 4-byte little-endian length prefix followed by the
        token encoded as UTF-16 LE.
        """
        token_bytes = token.encode("utf-16-le")
        return struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)

    def _build_token_ready_connection_string(self) -> str:
        """Produce a clean ODBC connection string suitable for token-based auth.
        Strips credentials fields (UID, PWD, Authentication, Trusted_Connection)
        from both SQLAlchemy URIs and raw ODBC strings so the token injected
        via the do_connect event is the sole auth mechanism.
        """
        if self._is_sqlalchemy_uri(self.config.sql_connection_string):
            url = make_url(self.config.sql_connection_string)
            parts = []

            driver = url.query.get("driver")
            if driver:
                parts.append(f"Driver={{{driver}}}")

            server = url.host or ""
            if url.port:
                parts.append(f"Server=tcp:{server},{url.port}")
            else:
                parts.append(f"Server=tcp:{server}")

            if url.database:
                parts.append(f"Database={url.database}")

            for key, value in url.query.items():
                if key.lower() in {
                    "driver",
                    "authentication",
                    "uid",
                    "pwd",
                    "user",
                    "username",
                }:
                    continue
                parts.append(f"{key}={value}")

            return ";".join(parts) + ";"

        filtered_parts = []
        for part in self.config.sql_connection_string.split(";"):
            if not part.strip():
                continue
            key, separator, value = part.partition("=")
            if not separator:
                continue
            if key.strip().lower() in {
                "authentication",
                "uid",
                "pwd",
                "trusted_connection",
            }:
                continue
            filtered_parts.append(f"{key}={value}")

        return ";".join(filtered_parts) + ";"

    def _create_db(self) -> SQLDatabase:
        """Create and return a LangChain SQLDatabase wrapper.
        Supports three connection modes in order of priority:
        1. Entra ID access-token auth: injects a fresh OAuth token on every
           connection via a SQLAlchemy 'do_connect' event.
        2. SQLAlchemy URI: passed directly to SQLDatabase.from_uri().
        3. Raw ODBC string: URL-encoded and wrapped in an mssql+pyodbc engine.
        """
        include_tables = list(self.config.sql_allowed_tables) or None

        if self.config.sql_use_access_token_auth:
            odbc_connect = quote_plus(
                self._build_token_ready_connection_string())
            engine = create_engine(
                f"mssql+pyodbc:///?odbc_connect={odbc_connect}")
            credential = self._create_token_credential()

            @event.listens_for(engine, "do_connect")
            def provide_token(
                dialect: Any, conn_rec: Any, cargs: Any, cparams: Any
            ) -> None:
                token = credential.get_token(SQL_ACCESS_TOKEN_SCOPE)
                attrs_before = dict(cparams.get("attrs_before", {}))
                attrs_before[SQL_ACCESS_TOKEN_ATTRIBUTE] = (
                    self._build_access_token_struct(token.token)
                )
                cparams["attrs_before"] = attrs_before

            return SQLDatabase(engine, include_tables=include_tables)

        if self._is_sqlalchemy_uri(self.config.sql_connection_string):
            return SQLDatabase.from_uri(
                self.config.sql_connection_string,
                include_tables=include_tables,
            )

        odbc_connect = quote_plus(self.config.sql_connection_string)
        engine = create_engine(f"mssql+pyodbc:///?odbc_connect={odbc_connect}")
        return SQLDatabase(engine, include_tables=include_tables)

    def _get_max_export_rows(self) -> int:
        return getattr(self.config, "max_export_rows", DEFAULT_MAX_EXPORT_ROWS)

    def _patch_db_with_guard(self) -> None:
        """Patch self.db.run() so the keyword guard applies to every execution path,
        including toolkit tools and any future code that calls db.run() directly."""
        original_run = self.db.run

        def guarded_run(command: str, *args: Any, **kwargs: Any) -> str:
            query_text = command if isinstance(command, str) else str(command)
            error = validate_query(query_text, self.config.sql_allowed_tables)
            if error:
                return error
            return original_run(command, *args, **kwargs)

        self.db.run = guarded_run  # type: ignore[method-assign]

    def _create_agent(self) -> Any:
        """Create the LangChain SQL Agent."""
        llm = self._create_llm()
        return create_sql_agent(
            llm=llm,
            db=self.db,
            verbose=self.config.agent_verbose_logging,
            agent_type="tool-calling",
            prefix=build_agent_prefix(self.config.sql_allowed_tables),
            top_k=3,
            max_iterations=5,
            agent_executor_kwargs={"handle_parsing_errors": True},
        )

    def _get_last_database_answer(self) -> str:
        """Return the most recent answer that came from a database query,
        or an empty string if no database turn exists in the history.
        Used to reformat previous results without re-querying the database.
        """
        for turn in reversed(self.chat_history):
            if turn.get("mode") == "database":
                return turn.get("answer", "")
        return ""

    def _remember_interaction(self, mode: str, question: str, answer: str) -> None:
        """Append a completed question/answer turn to chat_history.
        mode is either 'database', 'general', or 'email' and is used later to locate
        the last database answer for table-format follow-ups.
        Trims the history to max_history_turns to prevent unbounded memory growth.
        """
        self.chat_history.append(
            {
                "mode": mode,
                "question": question,
                "answer": answer,
            }
        )
        # Keep only recent turns to avoid unbounded context growth.
        if len(self.chat_history) > self.max_history_turns:
            self.chat_history = self.chat_history[-self.max_history_turns:]

    def _format_context_history(self) -> str:
        """Return a human-readable summary of the current chat history,
        used by the 'show context' CLI command. Each turn is truncated to
        120 characters for readability.
        """
        if not self.chat_history:
            return "Context is empty."

        lines = [
            f"Stored turns: {len(self.chat_history)} (max {self.max_history_turns})"
        ]
        for i, turn in enumerate(self.chat_history, start=1):
            question = turn["question"].replace("\n", " ").strip()
            answer = turn["answer"].replace("\n", " ").strip()
            if len(question) > 120:
                question = question[:117] + "..."
            if len(answer) > 120:
                answer = answer[:117] + "..."
            lines.append(f"{i}. [{turn['mode']}] Q: {question}")
            lines.append(f"   A: {answer}")

        return "\n".join(lines)

    def _build_follow_up_prompt(self, question: str) -> str:
        """Build a general-purpose follow-up prompt that embeds the last 3
        conversation turns so the LLM can resolve pronouns and references
        without querying the database.
        """
        recent_turns = self.chat_history[-3:]
        context_lines = []
        for turn in recent_turns:
            context_lines.append(f"User: {turn['question']}")
            context_lines.append(f"Assistant: {turn['answer']}")

        context_block = "\n".join(context_lines)
        return (
            "You are assisting with follow-up questions. Use the conversation context below "
            "to resolve references like 'these values' and give a concise, clear answer.\n\n"
            f"Conversation context:\n{context_block}\n\n"
            f"Current follow-up question: {question}"
        )

    def _build_database_follow_up_prompt(self, question: str) -> str:
        """Build a context-aware prompt for database follow-up questions."""
        recent_turns = self.chat_history[-3:]
        context_lines = ["Previous conversation context:"]
        for turn in recent_turns:
            context_lines.append(f"User: {turn['question']}")
            context_lines.append(f"Assistant: {turn['answer']}")

        context_block = "\n".join(context_lines)
        return (
            f"{context_block}\n\n"
            "Use this context to understand what the current question refers to. "
            "Only query database objects when necessary to answer the follow-up. "
            f"Current question: {question}"
        )

    def _send_last_answer_to_email(
        self,
        recipient: str,
        wants_attachment: bool = False,
        attachment_format: str | None = None,
    ) -> str:
        source_question, source_answer = get_last_shareable_answer(
            self.chat_history)
        if not source_answer:
            return "There is no previous result to email yet."

        configuration_error = get_email_configuration_error(self.config)
        if configuration_error:
            return configuration_error

        email_payload = build_email_payload(
            source_question,
            source_answer,
            wants_attachment,
            attachment_format,
        )
        sender = GraphMailSender(
            tenant_id=self.config.graph_mail_tenant_id or "",
            client_id=self.config.graph_mail_client_id or "",
            client_secret=self.config.graph_mail_client_secret or "",
            sender_user_id=self.config.graph_mail_sender or "",
        )

        try:
            sender.send_mail(
                recipient=recipient,
                subject=build_email_subject(source_question),
                html_body=str(email_payload["html_body"]),
                text_body=str(email_payload["text_body"]),
                attachment=email_payload["attachment"],
            )
        except RuntimeError as error:
            LOGGER.exception("Email delivery failed")
            return f"Email delivery failed: {error}"

        confirmation = f"Sent the latest result to {recipient}."
        if wants_attachment:
            confirmation = f"Sent the latest result to {recipient} with an attachment."
        self._remember_interaction(
            "email", f"send this to {recipient}", confirmation)
        return confirmation

    def _ask_general(self, question: str) -> str:
        """Send a question directly to the general-purpose LLM (bypassing the
        SQL agent) and return the response content as a plain string.
        Used for non-database questions and follow-ups that don't need new data.
        """
        response = self.general_llm.invoke(question)
        content = getattr(response, "content", "")
        return content if isinstance(content, str) else str(content)

    def _execute_select_query(
        self, sql_query: str
    ) -> tuple[list[str], list[dict[str, object]]]:
        """Execute a raw SELECT query directly against the database engine and
        return (column_names, rows). Raises ValueError if the query is empty,
        does not start with SELECT, or contains a blocked SQL command.
        Used by export_query_to_csv; bypasses the agent but still enforces
        the keyword guard via _validate_sql.
        """
        normalized = sql_query.strip().lower()
        if not normalized:
            raise ValueError("Please provide a SQL SELECT query.")
        if not normalized.startswith("select"):
            raise ValueError("Only SELECT queries can be exported.")
        error = validate_sql(sql_query)
        if error:
            raise ValueError(error)
        allowed_tables_error = validate_allowed_tables(
            sql_query,
            self.config.sql_allowed_tables,
        )
        if allowed_tables_error:
            raise ValueError(allowed_tables_error)
        validate_export_query(sql_query, self._get_max_export_rows())

        engine = self.db._engine
        with engine.connect() as connection:
            result = connection.execute(text(sql_query))
            columns = list(result.keys())
            rows = [dict(row._mapping) for row in result]
        return columns, rows

    def ask(self, question: str) -> str:
        """Main entry point for a single user question.
        Routing logic (in order):
        1. Email command → send the last shareable answer to the requested recipient.
        2. Table-format follow-up → reformat the last database answer without re-querying.
        3. Non-database question → answer via the general LLM (with context if follow-up).
        4. Database question → route through the LangChain SQL agent.
        Stores every turn in chat_history and handles the 'result too large' error gracefully.
        """
        recipient, wants_attachment, attachment_format = parse_email_request(
            question)
        if recipient:
            return self._send_last_answer_to_email(
                recipient,
                wants_attachment,
                attachment_format,
            )

        if self.chat_history and is_table_format_follow_up(question):
            last_db_answer = self._get_last_database_answer()
            if last_db_answer:
                converted = to_markdown_table(last_db_answer)
                if converted:
                    answer = converted
                else:
                    answer = self._ask_general(
                        build_table_format_prompt(question, last_db_answer))
                self._remember_interaction("general", question, answer)
                return answer

        if not is_database_question(question):
            if self.chat_history and is_follow_up_question(question, bool(self.chat_history)):
                answer = self._ask_general(
                    self._build_follow_up_prompt(question))
            else:
                answer = self._ask_general(question)
            self._remember_interaction("general", question, answer)
            return answer

        try:
            # For database follow-up questions, include conversation context
            question_to_ask = question
            if self.chat_history and is_follow_up_question(question, bool(self.chat_history)):
                question_to_ask = self._build_database_follow_up_prompt(
                    question)

            result = self.agent.invoke(question_to_ask)
            answer = result["output"]

            # If user explicitly asked for table format, normalize the answer into markdown table.
            if is_table_format_follow_up(question):
                converted_answer = to_markdown_table(answer)
                if converted_answer:
                    answer = converted_answer

            self._remember_interaction("database", question, answer)
            return answer
        except Exception as e:
            error_msg = str(e)
            if "string too long" in error_msg or "string_above_max_length" in error_msg:
                answer = "Query result too large for processing. Try being more specific or use 'graph bar'/'graph pie' commands for earthquake visualization."
                self._remember_interaction("database", question, answer)
                return answer
            raise

    def get_earthquake_counts_by_county(self) -> dict[str, int]:
        """Query earthquake counts aggregated by country."""
        try:
            engine = self.db._engine
            with engine.connect() as connection:
                query = text("""
                    SELECT TOP 50
                        COALESCE(NULLIF(country_code, ''), 'Unknown') AS country,
                        COUNT(*) as count
                    FROM earthquake_events_gold
                    GROUP BY COALESCE(NULLIF(country_code, ''), 'Unknown')
                    ORDER BY count DESC
                """)
                result = connection.execute(query)
                return {row[0]: row[1] for row in result}
        except Exception as e:
            LOGGER.exception("Error querying earthquake data")
            return {}

    def generate_earthquake_bar_chart(self) -> str:
        """Generate a bar chart of earthquake counts by country."""
        data = self.get_earthquake_counts_by_county()
        if not data:
            return "No earthquake data available."
        return self.visualizer.generate_bar_chart(
            data,
            title="Earthquake Count by Country",
            category_label="Country",
        )

    def generate_earthquake_pie_chart(self) -> str:
        """Generate a pie chart of earthquake distribution by country."""
        data = self.get_earthquake_counts_by_county()
        if not data:
            return "No earthquake data available."
        return self.visualizer.generate_pie_chart(
            data,
            title="Earthquake Distribution by Country",
            category_label="Country",
        )

    def export_query_to_csv(self, sql_query: str) -> str:
        """Run a SELECT query and export the result rows to CSV."""
        try:
            columns, rows = self._execute_select_query(sql_query)
            path = export_rows_to_csv(columns, rows, label="export")
            return f"Exported {len(rows)} row(s) to: {path}"
        except ValueError as e:
            return str(e)
        except Exception as e:
            LOGGER.exception("Export query failed")
            return "Export failed. Please try again later."

    def run(self) -> None:
        """Run the app as an interactive CLI REPL.
        Supports special commands: 'exit', 'show context', 'reset context',
        'remember N', 'export csv <SQL>', 'graph bar', 'graph pie', and
        natural-language chart requests (e.g. 'plot earthquake counts').
        All other input is forwarded to ask().
        """
        print("SQL Agent is ready. Type 'exit' to quit.")
        print(
            "Special commands: 'graph bar' or 'graph pie' to visualize earthquakes by country.\n"
        )
        print("Context commands: 'show context', 'reset context', 'remember N'.\n")
        print("Export command: export csv SELECT TOP 10 * FROM your_table\n")

        while True:
            try:
                question = input(
                    "Ask a question (database or general): ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\nGoodbye!")
                break

            if question.lower() == "exit":
                print("Goodbye!")
                break
            if not question:
                continue

            normalized = question.lower()

            # Context management commands.
            if normalized == "show context":
                print(f"\n{self._format_context_history()}\n")
                continue

            if normalized == "reset context":
                self.chat_history.clear()
                print("\nContext cleared.\n")
                continue

            if normalized.startswith("export csv "):
                sql_query = question[len("export csv "):].strip()
                print(f"\n{self.export_query_to_csv(sql_query)}\n")
                continue

            if normalized.startswith("remember "):
                try:
                    max_turns = int(normalized.split()[1])
                    if max_turns <= 0:
                        print(
                            "\nPlease provide a positive number, for example: remember 8\n"
                        )
                        continue
                    self.max_history_turns = max_turns
                    if len(self.chat_history) > self.max_history_turns:
                        self.chat_history = self.chat_history[-self.max_history_turns:]
                    print(
                        f"\nContext memory size set to {self.max_history_turns} turns.\n"
                    )
                except (IndexError, ValueError):
                    print("\nUsage: remember N (example: remember 8)\n")
                continue

            # Handle special graph commands and natural-language chart requests.
            # Example: "Generate a pie chart of earthquake counts by country"
            is_chart_request = any(
                token in normalized for token in ["graph", "chart", "plot", "visualize"]
            ) and any(token in normalized for token in ["earthquake", "earthquakes"])

            if normalized.startswith("graph") or is_chart_request:
                try:
                    if "pie" in normalized:
                        path = self.generate_earthquake_pie_chart()
                        print(f"\nPie chart saved to: {path}\n")
                    elif "bar" in normalized:
                        path = self.generate_earthquake_bar_chart()
                        print(f"\nBar chart saved to: {path}\n")
                    elif normalized.startswith("graph"):
                        print("Usage: 'graph bar' or 'graph pie'\n")
                    else:
                        # Default to bar chart for generic chart requests.
                        path = self.generate_earthquake_bar_chart()
                        print(
                            f"\nGenerated bar chart (default) saved to: {path}\n")
                except Exception as e:
                    print(f"Error generating graph: {e}\n")
                continue

            # Regular agent query
            try:
                answer = self.ask(question)
                print(f"\nAnswer: {answer}\n")
            except Exception as e:
                print(f"Error: {e}\n")
