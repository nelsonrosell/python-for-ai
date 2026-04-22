from app.sql_agent_app import SqlAgentApp

app = SqlAgentApp()
data = app.get_earthquake_counts_by_county()

print("Top 10 categories used for chart:")
for idx, (country, count) in enumerate(data.items()):
    if idx >= 10:
        break
    print(f"{country}: {count}")

path = app.generate_earthquake_bar_chart()
print(f"Generated chart: {path}")
