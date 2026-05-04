import unittest
from unittest.mock import patch

from app.sql_agent_app import SqlAgentApp


class TestEmailDelivery(unittest.TestCase):
    def _build_app(self) -> SqlAgentApp:
        app = object.__new__(SqlAgentApp)
        app.config = type(
            "Config",
            (),
            {
                "graph_mail_tenant_id": "tenant-id",
                "graph_mail_client_id": "client-id",
                "graph_mail_client_secret": "client-secret",
                "graph_mail_sender": "sender@example.com",
                "auto_email_duplicate_alerts": False,
                "duplicate_alert_recipient": None,
                "sql_allowed_tables": (),
                "max_export_rows": 500,
            },
        )()
        app.chat_history = []
        app._last_db_run_result = ""
        app.max_history_turns = 8
        return app

    def test_send_email_requires_previous_result(self) -> None:
        app = self._build_app()

        self.assertEqual(
            app.ask("send this to alice@example.com"),
            "There is no previous result to email yet.",
        )

    def test_send_email_requires_graph_configuration(self) -> None:
        app = self._build_app()
        app.config.graph_mail_client_secret = None
        app.chat_history = [
            {
                "mode": "database",
                "question": "Show the latest Australian earthquakes",
                "answer": "- quake 1\n- quake 2",
            }
        ]

        self.assertEqual(
            app.ask("send this to alice@example.com"),
            "Email sending is not configured. Missing: GRAPH_MAIL_CLIENT_SECRET.",
        )

    @patch("app.sql_agent_app.GraphMailSender")
    def test_send_email_uses_latest_non_email_answer(self, graph_mail_sender) -> None:
        sender = graph_mail_sender.return_value
        app = self._build_app()
        app.chat_history = [
            {
                "mode": "database",
                "question": "Show the latest Australian earthquakes in table format",
                "answer": "- quake 1\n- quake 2",
            },
            {
                "mode": "email",
                "question": "send this to previous@example.com",
                "answer": "Sent the latest result to previous@example.com.",
            },
        ]

        result = app.ask("send this to alice@example.com")

        self.assertEqual(
            result, "Sent the latest result to alice@example.com.")
        graph_mail_sender.assert_called_once_with(
            tenant_id="tenant-id",
            client_id="client-id",
            client_secret="client-secret",
            sender_user_id="sender@example.com",
        )
        sender.send_mail.assert_called_once()
        _, kwargs = sender.send_mail.call_args
        self.assertEqual(kwargs["recipient"], "alice@example.com")
        self.assertIn("<table", kwargs["html_body"])
        self.assertIn("quake 1", kwargs["html_body"])
        self.assertIsNone(kwargs["attachment"])

    @patch("app.sql_agent_app.GraphMailSender")
    def test_send_email_with_attachment_phrase_requests_attachment(self, graph_mail_sender) -> None:
        sender = graph_mail_sender.return_value
        app = self._build_app()
        app.chat_history = [
            {
                "mode": "database",
                "question": "Show the latest Australian earthquakes in table format",
                "answer": "| Name | Magnitude |\n| --- | --- |\n| Quake 1 | 5.4 |",
            }
        ]

        result = app.ask("email this to alice@example.com as attachment")

        self.assertEqual(
            result,
            "Sent the latest result to alice@example.com with an attachment.",
        )
        sender.send_mail.assert_called_once()
        _, kwargs = sender.send_mail.call_args
        self.assertEqual(kwargs["recipient"], "alice@example.com")
        self.assertIsNotNone(kwargs["attachment"])
        attachment_name, content_type, content_bytes = kwargs["attachment"]
        self.assertEqual(attachment_name, "earthquake_result.csv")
        self.assertEqual(content_type, "text/csv")
        self.assertTrue(content_bytes)

    @patch("app.sql_agent_app.GraphMailSender")
    def test_send_email_with_explicit_csv_request_forces_csv_attachment(self, graph_mail_sender) -> None:
        sender = graph_mail_sender.return_value
        app = self._build_app()
        app.chat_history = [
            {
                "mode": "database",
                "question": "Show the latest Australian earthquakes",
                "answer": "Latest results:\nquake 1\nquake 2",
            }
        ]

        result = app.ask(
            "email it to alice@example.com the .csv file as attachment")

        self.assertEqual(
            result,
            "Sent the latest result to alice@example.com with an attachment.",
        )
        sender.send_mail.assert_called_once()
        _, kwargs = sender.send_mail.call_args
        attachment_name, content_type, content_bytes = kwargs["attachment"]
        self.assertEqual(attachment_name, "earthquake_result.csv")
        self.assertEqual(content_type, "text/csv")
        self.assertTrue(content_bytes)

    @patch("app.sql_agent_app.GraphMailSender")
    def test_database_answer_with_duplicate_raw_rows_triggers_alert_email(self, graph_mail_sender) -> None:
        sender = graph_mail_sender.return_value
        app = self._build_app()
        app.config.auto_email_duplicate_alerts = True
        app.config.duplicate_alert_recipient = "alerts@example.com"

        class FakeAgent:
            def invoke(self, _question: str) -> dict[str, str]:
                app._last_db_run_result = "[(1, 'Quake A'), (1, 'Quake A'), (2, 'Quake B')]"
                return {"output": "Here are the latest earthquakes in Australia."}

        app.agent = FakeAgent()

        result = app.ask("show latest earthquakes")

        self.assertEqual(
            result, "Here are the latest earthquakes in Australia.")
        sender.send_mail.assert_called_once()
        _, kwargs = sender.send_mail.call_args
        self.assertEqual(kwargs["recipient"], "alerts@example.com")
        self.assertIsNotNone(kwargs["attachment"])
        attachment_name, content_type, content_bytes = kwargs["attachment"]
        self.assertEqual(attachment_name, "earthquake_result.csv")
        self.assertEqual(content_type, "text/csv")
        self.assertTrue(content_bytes)

    @patch("app.sql_agent_app.GraphMailSender")
    def test_database_answer_with_duplicate_rows_triggers_alert_email(self, graph_mail_sender) -> None:
        sender = graph_mail_sender.return_value
        app = self._build_app()
        app.config.auto_email_duplicate_alerts = True
        app.config.duplicate_alert_recipient = "alerts@example.com"
        app.agent = type(
            "Agent",
            (),
            {
                "invoke": lambda self, _: {
                    "output": "| ID | Title |\n| --- | --- |\n| 1 | Quake A |\n| 1 | Quake A |\n| 2 | Quake B |"
                }
            },
        )()

        result = app.ask("show latest earthquakes in table format")

        self.assertIn("| ID | Title |", result)
        sender.send_mail.assert_called_once()
        _, kwargs = sender.send_mail.call_args
        self.assertEqual(kwargs["recipient"], "alerts@example.com")
        self.assertIsNotNone(kwargs["attachment"])
        attachment_name, content_type, content_bytes = kwargs["attachment"]
        self.assertEqual(attachment_name, "earthquake_result.csv")
        self.assertEqual(content_type, "text/csv")
        self.assertTrue(content_bytes)


if __name__ == "__main__":
    unittest.main()
