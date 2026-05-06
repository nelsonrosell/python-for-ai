import csv
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app import export


class TestCsvExport(unittest.TestCase):
    def test_export_escapes_spreadsheet_formula_prefixes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            with patch.object(export, "_EXPORTS_DIR", Path(temp_dir)):
                path = export.export_rows_to_csv(
                    ["name", "note"],
                    [
                        {"name": "=HYPERLINK(\"https://example.com\")", "note": "+1"},
                        {"name": "@hidden", "note": "-2"},
                    ],
                )

            with open(path, newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))

        self.assertEqual(rows[0]["name"], "'=HYPERLINK(\"https://example.com\")")
        self.assertEqual(rows[0]["note"], "'+1")
        self.assertEqual(rows[1]["name"], "'@hidden")
        self.assertEqual(rows[1]["note"], "'-2")


if __name__ == "__main__":
    unittest.main()
