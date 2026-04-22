from sqlalchemy import text

from app.sql_agent_app import SqlAgentApp

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
