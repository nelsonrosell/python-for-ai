import os
import unittest
from unittest.mock import patch

from app.config import REQUIRED_KEYS, load_config


class TestLoadConfig(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_raises_when_required_keys_missing(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            load_config()

        message = str(ctx.exception)
        for key in REQUIRED_KEYS:
            self.assertIn(key, message)

    @patch.dict(
        os.environ,
        {
            "SQL_CONNECTION_STRING": "mssql+pyodbc://user:pass@server/db?driver=ODBC+Driver+18+for+SQL+Server",
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
            "AZURE_OPENAI_API_KEY": "fake-key",
            "AZURE_OPENAI_API_VERSION": "2024-02-01",
            "AZURE_OPENAI_DEPLOYMENT": "gpt-4o",
        },
        clear=True,
    )
    def test_loads_config_when_keys_present(self) -> None:
        config = load_config()
        self.assertEqual(config.azure_openai_deployment, "gpt-4o")
        self.assertEqual(config.app_env, "dev")
        self.assertTrue(config.sql_connection_string.startswith("mssql+pyodbc://"))
        self.assertEqual(config.sql_allowed_tables, ())
        self.assertFalse(config.sql_use_access_token_auth)
        self.assertIsNone(config.sql_entra_login_hint)
        self.assertFalse(config.agent_verbose_logging)
        self.assertEqual(config.max_export_rows, 500)

    @patch.dict(
        os.environ,
        {
            "SQL_CONNECTION_STRING": "Driver={ODBC Driver 18 for SQL Server};Server=tcp:workspace.datawarehouse.fabric.microsoft.com,1433;Database=mydb;Encrypt=yes;TrustServerCertificate=no;",
            "SQL_USE_ACCESS_TOKEN_AUTH": "true",
            "SQL_ENTRA_LOGIN_HINT": "user@example.com",
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
            "AZURE_OPENAI_API_KEY": "fake-key",
            "AZURE_OPENAI_API_VERSION": "2024-02-01",
            "AZURE_OPENAI_DEPLOYMENT": "gpt-4o",
        },
        clear=True,
    )
    def test_loads_optional_sql_token_auth_settings(self) -> None:
        config = load_config()
        self.assertTrue(config.sql_use_access_token_auth)
        self.assertEqual(config.sql_entra_login_hint, "user@example.com")

    @patch.dict(
        os.environ,
        {
            "APP_ENV": "prod",
            "APP_ENABLE_VERBOSE_AGENT_LOGS": "true",
            "APP_MAX_EXPORT_ROWS": "250",
            "SQL_ALLOWED_TABLES": "earthquake_events_gold, reporting_view ",
            "SQL_CONNECTION_STRING": "Driver={ODBC Driver 18 for SQL Server};Server=tcp:workspace.datawarehouse.fabric.microsoft.com,1433;Database=mydb;Encrypt=yes;TrustServerCertificate=no;",
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
            "AZURE_OPENAI_API_KEY": "fake-key",
            "AZURE_OPENAI_API_VERSION": "2024-02-01",
            "AZURE_OPENAI_DEPLOYMENT": "gpt-4o",
        },
        clear=True,
    )
    def test_loads_security_related_optional_settings(self) -> None:
        config = load_config()
        self.assertEqual(config.app_env, "prod")
        self.assertTrue(config.agent_verbose_logging)
        self.assertEqual(config.max_export_rows, 250)
        self.assertEqual(
            config.sql_allowed_tables,
            ("earthquake_events_gold", "reporting_view"),
        )

    @patch.dict(
        os.environ,
        {
            "APP_ENV": "prod",
            "SQL_CONNECTION_STRING": "Driver={ODBC Driver 18 for SQL Server};Server=tcp:workspace.datawarehouse.fabric.microsoft.com,1433;Database=mydb;Encrypt=yes;TrustServerCertificate=no;",
            "AZURE_OPENAI_ENDPOINT": "https://example.openai.azure.com/",
            "AZURE_OPENAI_API_KEY": "fake-key",
            "AZURE_OPENAI_API_VERSION": "2024-02-01",
            "AZURE_OPENAI_DEPLOYMENT": "gpt-4o",
        },
        clear=True,
    )
    def test_requires_sql_allowed_tables_outside_dev(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            load_config()

        self.assertEqual(
            str(ctx.exception),
            "SQL_ALLOWED_TABLES must be configured when APP_ENV is not 'dev'.",
        )


if __name__ == "__main__":
    unittest.main()
