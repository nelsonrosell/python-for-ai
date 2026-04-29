from app.sql_agent_app import SqlAgentApp
from sqlalchemy import text
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


app = SqlAgentApp()
engine = app.db._engine

with engine.connect() as conn:
    result = conn.execute(
        text(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE'"
        )
    )
    tables = result.fetchall()
    print("Available tables:")
    for table in tables:
        print(f"  - {table[0]}")
