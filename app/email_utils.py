import html
import json
import logging
import time
import base64
import csv
import io
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from azure.identity import ClientSecretCredential


GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_SENDMAIL_URL = "https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
LOGGER = logging.getLogger(__name__)


def _split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []

    values = [value.strip() for value in stripped[1:-1].split("|")]
    return [value for value in values]


def markdown_table_to_html(markdown_table: str) -> str:
    lines = [line.strip()
             for line in markdown_table.splitlines() if line.strip()]
    if len(lines) < 2:
        return ""

    headers = _split_markdown_row(lines[0])
    separators = _split_markdown_row(lines[1])
    if not headers or not separators or len(headers) != len(separators):
        return ""
    if not all(set(cell) <= {":", "-", " "} for cell in separators):
        return ""

    body_rows: list[list[str]] = []
    for line in lines[2:]:
        row = _split_markdown_row(line)
        if not row:
            continue
        padded = row + [""] * (len(headers) - len(row))
        body_rows.append(padded[: len(headers)])

    if not body_rows:
        return ""

    header_html = "".join(
        f"<th>{html.escape(header)}</th>" for header in headers)
    rows_html = []
    for row in body_rows:
        cell_html = "".join(f"<td>{html.escape(cell)}</td>" for cell in row)
        rows_html.append(f"<tr>{cell_html}</tr>")

    return (
        '<table border="1" cellspacing="0" cellpadding="6" '
        'style="border-collapse: collapse;">'
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody>"
        "</table>"
    )


def build_result_email_html(source_question: str, formatted_answer: str) -> str:
    table_html = markdown_table_to_html(formatted_answer)
    if table_html:
        content_html = table_html
    else:
        content_html = f"<pre>{html.escape(formatted_answer)}</pre>"

    escaped_question = html.escape(source_question)
    return (
        "<html><body>"
        "<p>The Earthquake Agent generated the following result.</p>"
        f"<p><strong>Source question:</strong> {escaped_question}</p>"
        f"{content_html}"
        "</body></html>"
    )


def _markdown_table_rows(markdown_table: str) -> tuple[list[str], list[list[str]]]:
    lines = [line.strip()
             for line in markdown_table.splitlines() if line.strip()]
    if len(lines) < 2:
        return [], []

    headers = _split_markdown_row(lines[0])
    separators = _split_markdown_row(lines[1])
    if not headers or not separators or len(headers) != len(separators):
        return [], []
    if not all(set(cell) <= {":", "-", " "} for cell in separators):
        return [], []

    rows: list[list[str]] = []
    for line in lines[2:]:
        row = _split_markdown_row(line)
        if not row:
            continue
        padded = row + [""] * (len(headers) - len(row))
        rows.append(padded[: len(headers)])

    return headers, rows


def build_email_attachment(formatted_answer: str) -> tuple[str, str, str]:
    headers, rows = _markdown_table_rows(formatted_answer)
    if headers and rows:
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(headers)
        writer.writerows(rows)
        encoded = base64.b64encode(
            output.getvalue().encode("utf-8")).decode("ascii")
        return ("earthquake_result.csv", "text/csv", encoded)

    encoded = base64.b64encode(
        formatted_answer.encode("utf-8")).decode("ascii")
    return ("earthquake_result.txt", "text/plain", encoded)


class GraphMailSender:
    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        sender_user_id: str,
    ) -> None:
        self.sender_user_id = sender_user_id
        self.credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret,
        )

    def send_mail(
        self,
        recipient: str,
        subject: str,
        html_body: str,
        text_body: str,
        attachment: tuple[str, str, str] | None = None,
    ) -> None:
        access_token = self.credential.get_token(GRAPH_SCOPE).token
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "HTML",
                    "content": html_body,
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": recipient,
                        }
                    }
                ],
                "replyTo": [
                    {
                        "emailAddress": {
                            "address": self.sender_user_id,
                        }
                    }
                ],
            },
            "saveToSentItems": True,
        }
        if attachment is not None:
            attachment_name, content_type, content_bytes = attachment
            payload["message"]["attachments"] = [
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "name": attachment_name,
                    "contentType": content_type,
                    "contentBytes": content_bytes,
                }
            ]
        request_body = json.dumps(payload).encode("utf-8")
        request_url = GRAPH_SENDMAIL_URL.format(
            sender=quote(self.sender_user_id, safe="")
        )
        last_error: Exception | None = None

        for attempt in range(3):
            request = Request(
                request_url,
                data=request_body,
                method="POST",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
            try:
                with urlopen(request, timeout=15) as response:
                    if response.status not in {200, 202}:
                        raise RuntimeError(
                            f"Microsoft Graph returned unexpected status {response.status}."
                        )
                    return
            except HTTPError as error:
                response_text = error.read().decode("utf-8", errors="ignore")
                if error.code in {429, 500, 502, 503, 504} and attempt < 2:
                    time.sleep(2**attempt)
                    continue
                last_error = RuntimeError(
                    f"Microsoft Graph sendMail failed with status {error.code}: {response_text or error.reason}"
                )
                break
            except URLError as error:
                if attempt < 2:
                    time.sleep(2**attempt)
                    continue
                last_error = RuntimeError(
                    f"Microsoft Graph sendMail request failed: {error.reason}"
                )
                break

        if last_error is not None:
            LOGGER.error("Microsoft Graph sendMail failed",
                         exc_info=last_error)
            raise last_error

        raise RuntimeError(
            "Microsoft Graph sendMail failed for an unknown reason.")
