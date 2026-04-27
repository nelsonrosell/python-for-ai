import struct
import re
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
from .export import export_rows_to_csv
from .visualization import EarthquakeVisualizer


SQL_ACCESS_TOKEN_ATTRIBUTE = 1256
SQL_ACCESS_TOKEN_SCOPE = "https://database.windows.net/.default"
SQL_AGENT_PREFIX = """
You are an agent designed to interact with a Microsoft SQL Server-compatible database (Microsoft Fabric SQL endpoint).

CRITICAL: Always keep result sets small and manageable:
- Use TOP (n) with n <= 5 for data exploration queries.
- For COUNT or aggregation queries, GROUP BY with limited results.
- Never return raw table dumps; always aggregate or limit results.
- If results are too large, use LIMIT or TOP to reduce output.

When writing SQL:
- Use SQL Server syntax.
- Use TOP (n) instead of LIMIT.
- Prefer explicit column lists over SELECT *.
- Use square brackets for identifiers only when needed.
- Never run INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, CREATE, or EXEC.
- If a query fails due to syntax, correct it for SQL Server and retry.
- ALWAYS use TOP (5) for safety unless aggregating results.
""".strip()


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
        """
        credentials = []

        if self.config.sql_entra_login_hint:
            credentials.append(
                InteractiveBrowserCredential(
                    login_hint=self.config.sql_entra_login_hint,
                    response_mode="form_post",
                )
            )

        credentials.append(AzureCliCredential())

        if not self.config.sql_entra_login_hint:
            credentials.append(InteractiveBrowserCredential(
                response_mode="form_post"))

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

            return SQLDatabase(engine)

        if self._is_sqlalchemy_uri(self.config.sql_connection_string):
            return SQLDatabase.from_uri(self.config.sql_connection_string)

        odbc_connect = quote_plus(self.config.sql_connection_string)
        engine = create_engine(f"mssql+pyodbc:///?odbc_connect={odbc_connect}")
        return SQLDatabase(engine)

    _BLOCKED_SQL_COMMANDS = re.compile(
        r"\b(DELETE|UPDATE|INSERT|MERGE|DROP|ALTER|CREATE|TRUNCATE|EXEC(UTE)?)\b",
        re.IGNORECASE,
    )

    @classmethod
    def _validate_sql(cls, query: str) -> str | None:
        """Return an error string if the query contains a blocked command, else None."""
        match = cls._BLOCKED_SQL_COMMANDS.search(query)
        if match:
            return f"Blocked: '{match.group().upper()}' statements are not permitted."
        return None

    def _patch_db_with_guard(self) -> None:
        """Patch self.db.run() so the keyword guard applies to every execution path,
        including toolkit tools and any future code that calls db.run() directly."""
        original_run = self.db.run

        def guarded_run(command: str, *args: Any, **kwargs: Any) -> str:
            error = self._validate_sql(command)
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
            verbose=True,
            agent_type="tool-calling",
            prefix=SQL_AGENT_PREFIX,
            top_k=3,
            max_iterations=5,
            agent_executor_kwargs={"handle_parsing_errors": True},
        )

    def _is_database_question(self, question: str) -> bool:
        """Return True if the question appears to be about the database.
        Uses a keyword heuristic (earthquake domain terms, SQL keywords, etc.)
        to decide whether to route through the SQL agent or the general LLM.
        """
        normalized = question.lower()
        db_terms = [
            "database",
            "sql",
            "table",
            "query",
            "schema",
            "column",
            "row",
            "count",
            "earthquake",
            "country",
            "state",
            "county",
            "filter",
            "group by",
            "order by",
            "top",
            "average",
            "sum",
            "max",
            "min",
        ]
        return any(term in normalized for term in db_terms)

    def _is_follow_up_question(self, question: str) -> bool:
        """Return True if the question is a follow-up to a previous turn.
        Detects follow-ups via known phrases ('what does this mean', 'how about'),
        anaphoric pronouns ('this', 'they', 'them'), or short questions (≤ 6 words)
        when chat history is non-empty.
        """
        normalized = question.lower().strip()
        follow_up_phrases = [
            "what does this",
            "what do these",
            "what does that mean",
            "what are these",
            "can you explain",
            "same query",
            "same result",
            "same as above",
            "previous result",
            "above result",
            "the list",
            "this list",
            "that list",
            "these results",
            "those results",
            "how about",
            "what about",
            "and in",
            "and for",
            "what about",
            "more about",
            "tell me more",
            "go on",
            "and what",
            "also in",
            "also for",
        ]
        if any(phrase in normalized for phrase in follow_up_phrases):
            return True

        # Use word boundaries to avoid false positives like matching "it" in "list".
        if bool(re.search(r"\b(this|that|these|those|it|they|them)\b", normalized)):
            return True

        # Very short questions (≤6 words) when there is prior history are almost always follow-ups.
        if self.chat_history and len(normalized.split()) <= 6:
            return True

        return False

    def _is_table_format_follow_up(self, question: str) -> bool:
        """Return True if the user is asking to reformat the previous answer as a table
        (e.g. 'show in table format', 'display as a table').
        """
        normalized = question.lower().strip()
        format_phrases = [
            "table format",
            "in table",
            "as a table",
            "show in table",
            "format this",
            "format it",
            "show me the list in table",
            "display in table",
            "tabular format",
        ]
        return any(phrase in normalized for phrase in format_phrases)

    def _get_last_database_answer(self) -> str:
        """Return the most recent answer that came from a database query,
        or an empty string if no database turn exists in the history.
        Used to reformat previous results without re-querying the database.
        """
        for turn in reversed(self.chat_history):
            if turn.get("mode") == "database":
                return turn.get("answer", "")
        return ""

    def _convert_text_list_to_markdown_table(self, text: str) -> str:
        """Convert simple line/bullet/number lists into a markdown table."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""

        items: list[str] = []
        bullet_pattern = re.compile(r"^(?:[-*•]|\d+\.)\s+(.+)$")

        # Case 1: explicit bullet or numbered list.
        for line in lines:
            match = bullet_pattern.match(line)
            if match:
                items.append(match.group(1).strip())

        # Case 2: header line followed by plain list items.
        if not items and len(lines) > 1 and lines[0].endswith(":"):
            trailing = [line for line in lines[1:] if not line.endswith(":")]
            if trailing:
                items.extend(trailing)

        if not items:
            return ""

        table_lines = ["| Value |", "| --- |"]
        for item in items:
            safe_item = item.replace("|", "\\|")
            table_lines.append(f"| {safe_item} |")
        return "\n".join(table_lines)

    def _looks_like_markdown_table(self, text: str) -> bool:
        """Return True if the text already contains a markdown table
        (a header row followed by a separator row beginning with '|' and '-').
        """
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) < 2:
            return False
        for i in range(len(lines) - 1):
            header = lines[i]
            separator = lines[i + 1]
            if header.startswith("|") and separator.startswith("|") and "-" in separator:
                return True
        return False

    def _convert_pipe_rows_to_markdown_table(self, text: str) -> str:
        """Convert raw pipe-delimited rows into a markdown table with generic columns."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""

        row_values: list[list[str]] = []
        for line in lines:
            if not (line.startswith("|") and line.endswith("|")):
                continue
            if line.count("|") < 3:
                continue
            cells = [cell.strip() for cell in line[1:-1].split("|")]
            cells = [cell for cell in cells if cell]
            if len(cells) < 2:
                continue
            row_values.append(cells)

        if not row_values:
            return ""

        column_count = max(len(row) for row in row_values)
        headers = [f"Column {idx + 1}" for idx in range(column_count)]
        table_lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * column_count) + " |",
        ]

        for row in row_values:
            padded = row + [""] * (column_count - len(row))
            escaped = [value.replace("|", "\\|") for value in padded]
            table_lines.append("| " + " | ".join(escaped) + " |")

        return "\n".join(table_lines)

    def _convert_key_value_lines_to_markdown_table(self, text: str) -> str:
        """Convert "Field: Value" lines into a two-column markdown table."""
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""

        rows: list[tuple[str, str]] = []
        for line in lines:
            # Skip markdown-table-like rows; these should be handled separately.
            if "|" in line:
                continue
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if not key or not value:
                continue
            rows.append((key, value))

        # Require multiple rows to avoid turning incidental single-colon text into Field/Value tables.
        if len(rows) < 2:
            return ""

        table_lines = ["| Field | Value |", "| --- | --- |"]
        for key, value in rows:
            safe_key = key.replace("|", "\\|")
            safe_value = value.replace("|", "\\|")
            table_lines.append(f"| {safe_key} | {safe_value} |")
        return "\n".join(table_lines)

    def _to_markdown_table(self, text: str) -> str:
        """Try converting text to a markdown table using known patterns."""
        if self._looks_like_markdown_table(text):
            return text

        pipe_rows_table = self._convert_pipe_rows_to_markdown_table(text)
        if pipe_rows_table:
            return pipe_rows_table

        key_value_table = self._convert_key_value_lines_to_markdown_table(text)
        if key_value_table:
            return key_value_table
        return self._convert_text_list_to_markdown_table(text)

    def _build_table_format_prompt(self, question: str, last_answer: str) -> str:
        """Build an LLM prompt that instructs the model to convert a previous
        database answer into a clean markdown table without re-running any query.
        """
        return (
            "You are formatting the assistant's PREVIOUS database answer. "
            "Do not run a new query and do not list database tables or schema. "
            "Convert the previous answer into a clean markdown table. "
            "If the previous answer has no structured rows, preserve the values as faithfully as possible and "
            "still present them in a table. Keep it concise.\n\n"
            f"User follow-up request: {question}\n\n"
            f"Previous database answer:\n{last_answer}"
        )

    def _remember_interaction(self, mode: str, question: str, answer: str) -> None:
        """Append a completed question/answer turn to chat_history.
        mode is either 'database' or 'general' and is used later to locate
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

    def _ask_general(self, question: str) -> str:
        """Send a question directly to the general-purpose LLM (bypassing the
        SQL agent) and return the response content as a plain string.
        Used for non-database questions and follow-ups that don't need new data.
        """
        response = self.general_llm.invoke(question)
        content = getattr(response, "content", "")
        return content if isinstance(content, str) else str(content)

    def _execute_select_query(self, sql_query: str) -> tuple[list[str], list[dict[str, object]]]:
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
        error = self._validate_sql(sql_query)
        if error:
            raise ValueError(error)

        engine = self.db._engine
        with engine.connect() as connection:
            result = connection.execute(text(sql_query))
            columns = list(result.keys())
            rows = [dict(row._mapping) for row in result]
        return columns, rows

    def ask(self, question: str) -> str:
        """Main entry point for a single user question.
        Routing logic (in order):
        1. Table-format follow-up → reformat the last database answer without re-querying.
        2. Non-database question → answer via the general LLM (with context if follow-up).
        3. Database question → route through the LangChain SQL agent.
        Stores every turn in chat_history and handles the 'result too large' error gracefully.
        """
        if self.chat_history and self._is_table_format_follow_up(question):
            last_db_answer = self._get_last_database_answer()
            if last_db_answer:
                converted = self._to_markdown_table(last_db_answer)
                if converted:
                    answer = converted
                else:
                    answer = self._ask_general(
                        self._build_table_format_prompt(
                            question, last_db_answer)
                    )
                self._remember_interaction("general", question, answer)
                return answer

        if not self._is_database_question(question):
            if self.chat_history and self._is_follow_up_question(question):
                answer = self._ask_general(
                    self._build_follow_up_prompt(question))
            else:
                answer = self._ask_general(question)
            self._remember_interaction("general", question, answer)
            return answer

        try:
            # For database follow-up questions, include conversation context
            question_to_ask = question
            if self.chat_history and self._is_follow_up_question(question):
                question_to_ask = self._build_database_follow_up_prompt(
                    question)

            result = self.agent.invoke(question_to_ask)
            answer = result["output"]

            # If user explicitly asked for table format, normalize the answer into markdown table.
            if self._is_table_format_follow_up(question):
                converted_answer = self._to_markdown_table(answer)
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
            print(f"Error querying earthquake data: {e}")
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
            return f"Export failed: {e}"

    def run(self) -> None:
        """Run the app as an interactive CLI REPL.
        Supports special commands: 'exit', 'show context', 'reset context',
        'remember N', 'export csv <SQL>', 'graph bar', 'graph pie', and
        natural-language chart requests (e.g. 'plot earthquake counts').
        All other input is forwarded to ask().
        """
        print("SQL Agent is ready. Type 'exit' to quit.")
        print("Special commands: 'graph bar' or 'graph pie' to visualize earthquakes by country.\n")
        print("Context commands: 'show context', 'reset context', 'remember N'.\n")
        print("Export command: export csv SELECT TOP 10 * FROM your_table\n")

        while True:
            question = input("Ask a question (database or general): ").strip()
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
                            "\nPlease provide a positive number, for example: remember 8\n")
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
            ) and any(
                token in normalized for token in ["earthquake", "earthquakes"]
            )

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
                            f"\nGenerated bar chart (default) saved to: {path}\n"
                        )
                except Exception as e:
                    print(f"Error generating graph: {e}\n")
                continue

            # Regular agent query
            try:
                answer = self.ask(question)
                print(f"\nAnswer: {answer}\n")
            except Exception as e:
                print(f"Error: {e}\n")
