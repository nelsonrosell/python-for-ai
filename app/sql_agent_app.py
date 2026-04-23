import struct
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
        self.config = config or load_config()
        self.db = self._create_db()
        self.agent = self._create_agent()
        self.general_llm = self._create_llm()
        self.visualizer = EarthquakeVisualizer()
        self.chat_history: list[dict[str, str]] = []
        self.max_history_turns = 8

    def _create_llm(self) -> AzureChatOpenAI:
        return AzureChatOpenAI(
            azure_endpoint=self.config.azure_openai_endpoint,
            api_key=self.config.azure_openai_api_key,
            api_version=self.config.azure_openai_api_version,
            azure_deployment=self.config.azure_openai_deployment,
            temperature=0,
        )

    def _is_sqlalchemy_uri(self, connection_string: str) -> bool:
        return "://" in connection_string

    def _create_token_credential(self) -> ChainedTokenCredential:
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
        token_bytes = token.encode("utf-16-le")
        return struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)

    def _build_token_ready_connection_string(self) -> str:
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

    def _create_agent(self) -> Any:
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
        normalized = question.lower().strip()
        follow_up_tokens = [
            "these",
            "those",
            "that",
            "it",
            "they",
            "them",
            "what does this",
            "what do these",
            "can you explain",
            "what does that mean",
            "what are these",
        ]
        return any(token in normalized for token in follow_up_tokens)

    def _remember_interaction(self, mode: str, question: str, answer: str) -> None:
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

    def _ask_general(self, question: str) -> str:
        response = self.general_llm.invoke(question)
        content = getattr(response, "content", "")
        return content if isinstance(content, str) else str(content)

    def _execute_select_query(self, sql_query: str) -> tuple[list[str], list[dict[str, object]]]:
        normalized = sql_query.strip().lower()
        if not normalized:
            raise ValueError("Please provide a SQL SELECT query.")
        if not normalized.startswith("select"):
            raise ValueError("Only SELECT queries can be exported.")

        engine = self.db._engine
        with engine.connect() as connection:
            result = connection.execute(text(sql_query))
            columns = list(result.keys())
            rows = [dict(row._mapping) for row in result]
        return columns, rows

    def ask(self, question: str) -> str:
        if not self._is_database_question(question):
            if self.chat_history and self._is_follow_up_question(question):
                answer = self._ask_general(
                    self._build_follow_up_prompt(question))
            else:
                answer = self._ask_general(question)
            self._remember_interaction("general", question, answer)
            return answer

        try:
            result = self.agent.invoke(question)
            answer = result["output"]
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
