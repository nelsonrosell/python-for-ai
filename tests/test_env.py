import os
import unittest
from pathlib import Path
from unittest.mock import patch

import app.env as env_module


class TestLoadEnvironment(unittest.TestCase):
    def setUp(self) -> None:
        self._original_env_loaded = env_module._ENV_LOADED
        env_module._ENV_LOADED = False

    def tearDown(self) -> None:
        env_module._ENV_LOADED = self._original_env_loaded

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
    @patch("app.env.load_dotenv")
    @patch("pathlib.Path.exists", return_value=False)
    def test_skips_env_file_loading_when_only_process_env_is_available(
        self,
        _mock_exists,
        mock_load_dotenv,
    ) -> None:
        chosen = env_module.load_environment()

        self.assertIsNone(chosen)
        mock_load_dotenv.assert_not_called()

    @patch.dict(os.environ, {"APP_ENV": "prod"}, clear=True)
    @patch("app.env.load_dotenv")
    @patch("pathlib.Path.exists")
    def test_loads_matching_env_file_when_present(
        self,
        mock_exists,
        mock_load_dotenv,
    ) -> None:
        mock_exists.side_effect = [True]

        chosen = env_module.load_environment()

        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.name, ".env.prod")
        mock_load_dotenv.assert_called_once_with(chosen, override=False)


if __name__ == "__main__":
    unittest.main()
