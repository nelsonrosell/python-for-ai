import re


DEFAULT_MAX_EXPORT_ROWS = 500
_TABLE_REFERENCE_PATTERN = re.compile(
    r'\b(?:FROM|JOIN|APPLY|CROSS\s+APPLY|OUTER\s+APPLY)\s+([A-Za-z0-9_\.\[\]"]+)',
    re.IGNORECASE,
)
_CTE_PATTERN = re.compile(r"\bWITH\s+([A-Za-z0-9_]+)\s+AS\b", re.IGNORECASE)
_BLOCKED_SQL_COMMANDS = re.compile(
    r"\b(DELETE|UPDATE|INSERT|MERGE|DROP|ALTER|CREATE|TRUNCATE|EXEC(UTE)?)\b",
    re.IGNORECASE,
)
_SELECT_INTO_PATTERN = re.compile(r"\bSELECT\b[\s\S]*\bINTO\b", re.IGNORECASE)
_EXPORT_TOP_PATTERN = re.compile(
    r"^\s*SELECT\s+(?:DISTINCT\s+)?TOP\s*(?:\(\s*(\d+)\s*\)|(\d+))(?=\s|$)",
    re.IGNORECASE,
)


def validate_sql(query: str) -> str | None:
    normalized = query.strip()
    if not normalized:
        return "Blocked: empty SQL statements are not permitted."

    if any(token in normalized for token in ("--", "/*", "*/")):
        return "Blocked: SQL comments are not permitted."

    if ";" in normalized.rstrip().rstrip(";"):
        return "Blocked: multiple SQL statements are not permitted."

    match = _BLOCKED_SQL_COMMANDS.search(query)
    if match:
        return f"Blocked: '{match.group().upper()}' statements are not permitted."

    if _SELECT_INTO_PATTERN.search(query):
        return "Blocked: 'SELECT INTO' statements are not permitted."

    return None


def normalize_table_identifier(identifier: str) -> str:
    cleaned = identifier.strip().strip(",")
    parts = [part.strip('[]"') for part in cleaned.split(".") if part.strip()]
    if not parts:
        return ""
    return parts[-1].lower()


def validate_allowed_tables(
    sql_query: str,
    allowed_table_names: tuple[str, ...],
) -> str | None:
    if not allowed_table_names:
        return None

    allowed_tables = {
        normalize_table_identifier(table)
        for table in allowed_table_names
    }
    cte_names = {
        normalize_table_identifier(match.group(1))
        for match in _CTE_PATTERN.finditer(sql_query)
    }
    referenced_tables = {
        normalize_table_identifier(match.group(1))
        for match in _TABLE_REFERENCE_PATTERN.finditer(sql_query)
    }
    referenced_tables = {table for table in referenced_tables if table}
    disallowed_tables = sorted(
        table
        for table in referenced_tables
        if table not in allowed_tables and table not in cte_names
    )
    if disallowed_tables:
        formatted = ", ".join(disallowed_tables)
        return f"Blocked: query references non-allowlisted tables: {formatted}."
    return None


def validate_query(sql_query: str, allowed_table_names: tuple[str, ...]) -> str | None:
    error = validate_sql(sql_query)
    if error:
        return error
    return validate_allowed_tables(sql_query, allowed_table_names)


def validate_export_query(sql_query: str, max_export_rows: int = DEFAULT_MAX_EXPORT_ROWS) -> None:
    top_match = _EXPORT_TOP_PATTERN.match(sql_query)
    if not top_match:
        raise ValueError(
            f"Export queries must begin with SELECT TOP (n), where n <= {max_export_rows}."
        )

    row_limit = int(top_match.group(1) or top_match.group(2))
    if row_limit > max_export_rows:
        raise ValueError(
            f"Export queries are limited to TOP ({max_export_rows}) rows."
        )
