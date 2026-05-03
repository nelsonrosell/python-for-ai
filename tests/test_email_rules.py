import unittest

from app.email_rules import (
    build_email_payload,
    build_email_subject,
    get_email_configuration_error,
    get_formatted_email_answer,
    get_last_shareable_answer,
)


class TestEmailRules(unittest.TestCase):
    def test_get_last_shareable_answer_skips_email_turns(self) -> None:
        question, answer = get_last_shareable_answer(
            [
                {"mode": "database", "question": "show quakes", "answer": "- quake 1"},
                {"mode": "email", "question": "send this", "answer": "sent"},
            ]
        )
        self.assertEqual(question, "show quakes")
        self.assertEqual(answer, "- quake 1")

    def test_get_formatted_email_answer_converts_lists(self) -> None:
        formatted = get_formatted_email_answer("- quake 1\n- quake 2")
        self.assertIn("| Value |", formatted)

    def test_get_email_configuration_error_lists_missing_settings(self) -> None:
        config = type(
            "Config",
            (),
            {
                "graph_mail_tenant_id": "tenant-id",
                "graph_mail_client_id": None,
                "graph_mail_client_secret": None,
                "graph_mail_sender": "sender@example.com",
            },
        )()
        self.assertEqual(
            get_email_configuration_error(config),
            "Email sending is not configured. Missing: GRAPH_MAIL_CLIENT_ID, GRAPH_MAIL_CLIENT_SECRET.",
        )

    def test_build_email_subject_truncates_long_questions(self) -> None:
        subject = build_email_subject(
            "show me the list of earthquake events in australia ordered by magnitude descending and include everything")
        self.assertTrue(subject.startswith("Earthquake Agent result: "))
        self.assertLessEqual(len(subject), len(
            "Earthquake Agent result: ") + 70)

    def test_build_email_payload_attaches_csv_for_tables(self) -> None:
        payload = build_email_payload(
            "show quakes",
            "| Name | Magnitude |\n| --- | --- |\n| Quake 1 | 5.4 |",
            True,
        )
        self.assertIn("<table", str(payload["html_body"]))
        attachment = payload["attachment"]
        self.assertIsNotNone(attachment)
        # type: ignore[misc]
        attachment_name, content_type, content_bytes = attachment
        self.assertEqual(attachment_name, "earthquake_result.csv")
        self.assertEqual(content_type, "text/csv")
        self.assertTrue(content_bytes)

    def test_build_email_payload_forces_csv_attachment_when_requested(self) -> None:
        payload = build_email_payload(
            "show quakes",
            "Latest results:\nquake 1\nquake 2",
            True,
            "csv",
        )
        attachment = payload["attachment"]
        self.assertIsNotNone(attachment)
        # type: ignore[misc]
        attachment_name, content_type, content_bytes = attachment
        self.assertEqual(attachment_name, "earthquake_result.csv")
        self.assertEqual(content_type, "text/csv")
        self.assertTrue(content_bytes)

    def test_build_email_payload_extracts_table_from_mixed_content_for_csv(self) -> None:
        payload = build_email_payload(
            "show quakes",
            "Here are the latest earthquakes in Australia:\n"
            "| ID | Title | Magnitude |\n"
            "| --- | --- | --- |\n"
            "| us6000qj0l | M 5.5 | 5.5 |\n"
            "| us6000qj0h | M 5.9 | 5.9 |\n"
            "It seems there are duplicate entries.",
            True,
            "csv",
        )
        attachment = payload["attachment"]
        self.assertIsNotNone(attachment)
        attachment_name, content_type, content_bytes = attachment  # type: ignore[misc]
        self.assertEqual(attachment_name, "earthquake_result.csv")
        self.assertEqual(content_type, "text/csv")
        self.assertIn("SUQsVGl0bGUsTWFnbml0dWRl", content_bytes)


if __name__ == "__main__":
    unittest.main()
