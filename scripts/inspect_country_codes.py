from app.sql_agent_app import SqlAgentApp
from sqlalchemy import text
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


app = SqlAgentApp()
engine = app.db._engine

query = text(
    """
    SELECT TOP 20 COALESCE(NULLIF(country_code, ''), 'Unknown') AS country, COUNT(*) AS cnt
    FROM earthquake_events_gold
    GROUP BY COALESCE(NULLIF(country_code, ''), 'Unknown')
    ORDER BY cnt DESC
    """
)

with engine.connect() as conn:
    rows = conn.execute(query).fetchall()

print("country_code distribution:")
for country, count in rows:
    print(f"{country}: {count}")
