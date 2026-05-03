import re


def convert_text_list_to_markdown_table(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    items: list[str] = []
    bullet_pattern = re.compile(r"^(?:[-*•]|\d+\.)\s+(.+)$")

    for line in lines:
        match = bullet_pattern.match(line)
        if match:
            items.append(match.group(1).strip())

    if not items and len(lines) > 1 and lines[0].endswith(":"):
        trailing = [line for line in lines[1:] if not line.endswith(":")]
        if trailing:
            items.extend(trailing)

    if not items:
        return ""

    table_lines = ["| Value |", "| --- |"]
    for item in items:
        safe_item = item.replace("|", "\\|")
        table_lines.append(f"| {safe_item} |")
    return "\n".join(table_lines)


def looks_like_markdown_table(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    for i in range(len(lines) - 1):
        header = lines[i]
        separator = lines[i + 1]
        if header.startswith("|") and separator.startswith("|") and "-" in separator:
            return True
    return False


def convert_pipe_rows_to_markdown_table(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    row_values: list[list[str]] = []
    for line in lines:
        if not (line.startswith("|") and line.endswith("|")):
            continue
        if line.count("|") < 3:
            continue
        cells = [cell.strip() for cell in line[1:-1].split("|")]
        cells = [cell for cell in cells if cell]
        if len(cells) < 2:
            continue
        row_values.append(cells)

    if not row_values:
        return ""

    column_count = max(len(row) for row in row_values)
    headers = [f"Column {idx + 1}" for idx in range(column_count)]
    table_lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * column_count) + " |",
    ]

    for row in row_values:
        padded = row + [""] * (column_count - len(row))
        escaped = [value.replace("|", "\\|") for value in padded]
        table_lines.append("| " + " | ".join(escaped) + " |")

    return "\n".join(table_lines)


def convert_key_value_lines_to_markdown_table(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""

    rows: list[tuple[str, str]] = []
    for line in lines:
        if "|" in line:
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            continue
        rows.append((key, value))

    if len(rows) < 2:
        return ""

    table_lines = ["| Field | Value |", "| --- | --- |"]
    for key, value in rows:
        safe_key = key.replace("|", "\\|")
        safe_value = value.replace("|", "\\|")
        table_lines.append(f"| {safe_key} | {safe_value} |")
    return "\n".join(table_lines)


def to_markdown_table(text: str) -> str:
    if looks_like_markdown_table(text):
        return text

    pipe_rows_table = convert_pipe_rows_to_markdown_table(text)
    if pipe_rows_table:
        return pipe_rows_table

    key_value_table = convert_key_value_lines_to_markdown_table(text)
    if key_value_table:
        return key_value_table

    return convert_text_list_to_markdown_table(text)


def build_table_format_prompt(question: str, last_answer: str) -> str:
    return (
        "You are formatting the assistant's PREVIOUS database answer. "
        "Do not run a new query and do not list database tables or schema. "
        "Convert the previous answer into a clean markdown table. "
        "If the previous answer has no structured rows, preserve the values as faithfully as possible and "
        "still present them in a table. Keep it concise.\n\n"
        f"User follow-up request: {question}\n\n"
        f"Previous database answer:\n{last_answer}"
    )
