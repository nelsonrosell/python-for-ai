from app.sql_agent_app import SqlAgentApp
from sqlalchemy import text
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


app = SqlAgentApp()
engine = app.db._engine

for table_name in ["earthquake_events_gold", "earthquake_events_silver"]:
    print(f"\nColumns in {table_name}:")
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT TOP 1 * FROM {table_name}"))
        for col in result.keys():
            print(f"  - {col}")
