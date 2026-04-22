from app.sql_agent_app import SqlAgentApp
from sqlalchemy import text, inspect

app = SqlAgentApp()
engine = app.db._engine

for table_name in ['earthquake_events_gold', 'earthquake_events_silver']:
    print(f'\nColumns in {table_name}:')
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT TOP 1 * FROM {table_name}"))
        # Get column names
        columns = result.keys()
        for col in columns:
            print(f'  - {col}')
