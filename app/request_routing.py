import re


_EMAIL_ADDRESS_PATTERN = re.compile(
    r"(?P<recipient>[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
    re.IGNORECASE,
)

_DB_TERMS = [
    "database",
    "sql",
    "table",
    "query",
    "schema",
    "column",
    "row",
    "count",
    "earthquake",
    "country",
    "state",
    "county",
    "filter",
    "group by",
    "order by",
    "top",
    "average",
    "sum",
    "max",
    "min",
]

_FOLLOW_UP_PHRASES = [
    "what does this",
    "what do these",
    "what does that mean",
    "what are these",
    "can you explain",
    "same query",
    "same result",
    "same as above",
    "previous result",
    "above result",
    "the list",
    "this list",
    "that list",
    "these results",
    "those results",
    "how about",
    "what about",
    "and in",
    "and for",
    "what about",
    "more about",
    "tell me more",
    "go on",
    "and what",
    "also in",
    "also for",
]

_TABLE_FORMAT_PHRASES = [
    "table format",
    "in table",
    "as a table",
    "show in table",
    "format this",
    "format it",
    "show me the list in table",
    "display in table",
    "tabular format",
]


def is_database_question(question: str) -> bool:
    normalized = question.lower()
    return any(term in normalized for term in _DB_TERMS)


def is_follow_up_question(question: str, has_chat_history: bool) -> bool:
    normalized = question.lower().strip()
    if any(phrase in normalized for phrase in _FOLLOW_UP_PHRASES):
        return True

    if bool(re.search(r"\b(this|that|these|those|it|they|them)\b", normalized)):
        return True

    if has_chat_history and len(normalized.split()) <= 6:
        return True

    return False


def is_table_format_follow_up(question: str) -> bool:
    normalized = question.lower().strip()
    return any(phrase in normalized for phrase in _TABLE_FORMAT_PHRASES)


def parse_email_request(question: str) -> tuple[str, bool, str | None]:
    normalized = question.strip().lower()
    if not normalized:
        return "", False, None
    if "email" not in normalized and "send" not in normalized:
        return "", False, None
    match = _EMAIL_ADDRESS_PATTERN.search(question)
    if not match:
        return "", False, None
    wants_attachment = bool(
        re.search(
            r"\b(?:as|with)\s+attachment\b|\battached\b|\battach(?:ment)?\b",
            normalized,
        )
    )
    attachment_format = None
    if wants_attachment and re.search(r"(?:\.csv\b|\bcsv\s+file\b|\bcsv\b)", normalized):
        attachment_format = "csv"
    return match.group("recipient").strip(), wants_attachment, attachment_format
