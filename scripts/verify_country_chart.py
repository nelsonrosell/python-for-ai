from app.sql_agent_app import SqlAgentApp
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


app = SqlAgentApp()
data = app.get_earthquake_counts_by_county()

print("Top 10 categories used for chart:")
for idx, (country, count) in enumerate(data.items()):
    if idx >= 10:
        break
    print(f"{country}: {count}")

path = app.generate_earthquake_bar_chart()
print(f"Generated chart: {path}")
