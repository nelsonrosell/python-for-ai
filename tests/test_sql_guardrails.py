import unittest

from app.sql_guardrails import (
    normalize_table_identifier,
    validate_allowed_tables,
    validate_export_query,
    validate_query,
    validate_sql,
)


class TestSqlGuardrails(unittest.TestCase):
    def test_validate_sql_blocks_comments(self) -> None:
        self.assertEqual(
            validate_sql("SELECT * FROM earthquake_events_gold -- comment"),
            "Blocked: SQL comments are not permitted.",
        )

    def test_normalize_table_identifier_returns_last_segment(self) -> None:
        self.assertEqual(
            normalize_table_identifier('[dbo].[earthquake_events_gold]'),
            "earthquake_events_gold",
        )

    def test_validate_allowed_tables_allows_cte_names(self) -> None:
        self.assertIsNone(
            validate_allowed_tables(
                "WITH recent AS (SELECT TOP 5 * FROM dbo.earthquake_events_gold) SELECT * FROM recent",
                ("earthquake_events_gold",),
            )
        )

    def test_validate_query_combines_sql_and_allowlist_checks(self) -> None:
        self.assertEqual(
            validate_query(
                "SELECT TOP 5 * FROM dbo.secret_table",
                ("earthquake_events_gold",),
            ),
            "Blocked: query references non-allowlisted tables: secret_table.",
        )

    def test_validate_export_query_accepts_parenthesized_top(self) -> None:
        validate_export_query(
            "SELECT TOP (10) id FROM earthquake_events_gold ORDER BY id DESC",
            500,
        )


if __name__ == "__main__":
    unittest.main()
