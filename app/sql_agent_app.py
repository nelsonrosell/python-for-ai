from typing import Any

from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.utilities import SQLDatabase
from langchain_openai import AzureChatOpenAI

from .config import AppConfig, load_config


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

    def _create_db(self) -> SQLDatabase:
        return SQLDatabase.from_uri(self.config.sql_connection_string)

    def _create_agent(self) -> Any:
        llm = self._create_llm()
        db = self._create_db()
        return create_sql_agent(llm=llm, db=db, verbose=True)

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
