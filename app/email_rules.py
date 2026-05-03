from .email_utils import build_email_attachment, build_result_email_html
from .table_formatting import looks_like_markdown_table, to_markdown_table


def get_last_shareable_answer(chat_history: list[dict[str, str]]) -> tuple[str, str]:
    for turn in reversed(chat_history):
        if turn.get("mode") in {"database", "general"}:
            return turn.get("question", ""), turn.get("answer", "")
    return "", ""


def get_formatted_email_answer(answer: str) -> str:
    if looks_like_markdown_table(answer):
        return answer

    converted = to_markdown_table(answer)
    return converted or answer


def get_email_configuration_error(config: object) -> str:
    required_settings = {
        "GRAPH_MAIL_TENANT_ID": getattr(config, "graph_mail_tenant_id", None),
        "GRAPH_MAIL_CLIENT_ID": getattr(config, "graph_mail_client_id", None),
        "GRAPH_MAIL_CLIENT_SECRET": getattr(config, "graph_mail_client_secret", None),
        "GRAPH_MAIL_SENDER": getattr(config, "graph_mail_sender", None),
    }
    missing_settings = [
        setting_name
        for setting_name, setting_value in required_settings.items()
        if not setting_value
    ]
    if not missing_settings:
        return ""
    return "Email sending is not configured. Missing: " + ", ".join(missing_settings) + "."


def build_email_subject(source_question: str) -> str:
    normalized = " ".join(source_question.split()).strip()
    if not normalized:
        return "Earthquake Agent result"
    if len(normalized) > 70:
        normalized = normalized[:67] + "..."
    return f"Earthquake Agent result: {normalized}"


def build_email_payload(
    source_question: str,
    source_answer: str,
    wants_attachment: bool,
    attachment_format: str | None = None,
) -> dict[str, object]:
    formatted_answer = get_formatted_email_answer(source_answer)
    text_body = f"Source question: {source_question}\n\n{formatted_answer}"
    html_body = build_result_email_html(source_question, formatted_answer)
    attachment = build_email_attachment(
        formatted_answer,
        attachment_format,
    ) if wants_attachment else None
    return {
        "formatted_answer": formatted_answer,
        "text_body": text_body,
        "html_body": html_body,
        "attachment": attachment,
    }
