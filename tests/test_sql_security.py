import unittest
from unittest.mock import patch

from app.sql_agent_app import SqlAgentApp


class TestSqlSecurity(unittest.TestCase):
    def test_validate_sql_allows_simple_select(self) -> None:
        self.assertIsNone(
            SqlAgentApp._validate_sql("SELECT TOP 5 * FROM earthquake_events_gold")
        )

    def test_validate_sql_blocks_stacked_statements(self) -> None:
        error = SqlAgentApp._validate_sql("SELECT 1; DROP TABLE dangerous")
        self.assertEqual(error, "Blocked: multiple SQL statements are not permitted.")

    def test_validate_sql_blocks_select_into(self) -> None:
        error = SqlAgentApp._validate_sql(
            "SELECT * INTO audit_copy FROM earthquake_events_gold"
        )
        self.assertEqual(error, "Blocked: 'SELECT INTO' statements are not permitted.")

    def test_validate_allowed_tables_blocks_non_allowlisted_reference(self) -> None:
        app = object.__new__(SqlAgentApp)
        app.config = type(
            "Config",
            (),
            {"sql_allowed_tables": ("earthquake_events_gold",), "max_export_rows": 500},
        )()

        error = app._validate_allowed_tables("SELECT TOP 5 * FROM dbo.secret_table")
        self.assertEqual(
            error,
            "Blocked: query references non-allowlisted tables: secret_table.",
        )

    def test_validate_allowed_tables_allows_allowlisted_reference(self) -> None:
        app = object.__new__(SqlAgentApp)
        app.config = type(
            "Config",
            (),
            {"sql_allowed_tables": ("earthquake_events_gold",), "max_export_rows": 500},
        )()

        self.assertIsNone(
            app._validate_allowed_tables(
                "SELECT TOP 5 * FROM dbo.earthquake_events_gold"
            )
        )

    def test_validate_export_query_requires_top_clause(self) -> None:
        app = object.__new__(SqlAgentApp)
        app.config = type("Config", (), {"max_export_rows": 500})()

        with self.assertRaises(ValueError) as ctx:
            app._validate_export_query("SELECT * FROM earthquake_events_gold")

        self.assertEqual(
            str(ctx.exception),
            "Export queries must begin with SELECT TOP (n), where n <= 500.",
        )

    def test_validate_export_query_enforces_max_rows(self) -> None:
        app = object.__new__(SqlAgentApp)
        app.config = type("Config", (), {"max_export_rows": 25})()

        with self.assertRaises(ValueError) as ctx:
            app._validate_export_query("SELECT TOP 50 * FROM earthquake_events_gold")

        self.assertEqual(
            str(ctx.exception),
            "Export queries are limited to TOP (25) rows.",
        )

    @patch("app.sql_agent_app.InteractiveBrowserCredential")
    @patch("app.sql_agent_app.AzureCliCredential")
    @patch("app.sql_agent_app.ChainedTokenCredential")
    def test_create_token_credential_prefers_login_hint_interactive_credential(
        self,
        chained_token_credential,
        azure_cli_credential,
        interactive_browser_credential,
    ) -> None:
        interactive_browser_credential.return_value = "interactive"
        azure_cli_credential.return_value = "cli"

        app = object.__new__(SqlAgentApp)
        app.config = type(
            "Config",
            (),
            {
                "sql_entra_login_hint": "user@example.com",
                "sql_allowed_tables": (),
                "max_export_rows": 500,
            },
        )()

        app._create_token_credential()

        interactive_browser_credential.assert_called_once_with(
            login_hint="user@example.com",
            response_mode="form_post",
        )
        azure_cli_credential.assert_called_once_with()
        chained_token_credential.assert_called_once_with("interactive", "cli")


if __name__ == "__main__":
    unittest.main()
