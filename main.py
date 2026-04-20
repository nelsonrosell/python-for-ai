from dotenv import load_dotenv
import os
from langchain_openai import AzureChatOpenAI
from langchain_community.agent_toolkits import create_sql_agent
from langchain_community.utilities import SQLDatabase

load_dotenv()


def create_agent():
    db = SQLDatabase.from_uri(os.getenv("SQL_CONNECTION_STRING"))

    llm = AzureChatOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        azure_deployment=os.getenv("AZURE_OPENAI_DEPLOYMENT"),
        temperature=0,
    )

    agent = create_sql_agent(llm=llm, db=db, verbose=True)
    return agent


def main():
    print("SQL Agent is ready. Type 'exit' to quit.\n")
    agent = create_agent()

    while True:
        question = input("Ask a question about your database: ").strip()
        if question.lower() == "exit":
            print("Goodbye!")
            break
        if not question:
            continue
        try:
            result = agent.invoke(question)
            print(f"\nAnswer: {result['output']}\n")
        except Exception as e:
            print(f"Error: {e}\n")


if __name__ == "__main__":
    main()
