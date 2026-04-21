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
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url

from .config import AppConfig, load_config


SQL_ACCESS_TOKEN_ATTRIBUTE = 1256
SQL_ACCESS_TOKEN_SCOPE = "https://database.windows.net/.default"


class SqlAgentApp:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or load_config()
        self.agent = self._create_agent()

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
            odbc_connect = quote_plus(self._build_token_ready_connection_string())
            engine = create_engine(f"mssql+pyodbc:///?odbc_connect={odbc_connect}")
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
        db = self._create_db()
        return create_sql_agent(
            llm=llm,
            db=db,
            verbose=True,
            agent_executor_kwargs={"handle_parsing_errors": True},
        )

    def ask(self, question: str) -> str:
        result = self.agent.invoke(question)
        return result["output"]

    def run(self) -> None:
        print("SQL Agent is ready. Type 'exit' to quit.\n")

        while True:
            question = input("Ask a question about your database: ").strip()
            if question.lower() == "exit":
                print("Goodbye!")
                break
            if not question:
                continue
            try:
                answer = self.ask(question)
                print(f"\nAnswer: {answer}\n")
            except Exception as e:
                print(f"Error: {e}\n")
