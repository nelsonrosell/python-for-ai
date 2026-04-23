from app.sql_agent_app import SqlAgentApp
from sqlalchemy import text

app = SqlAgentApp()
engine = app.db._engine

with engine.connect() as conn:
    result = conn.execute(text(
        "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"))
    tables = result.fetchall()
    print('Available tables:')
    for table in tables:
        print(f'  - {table[0]}')
