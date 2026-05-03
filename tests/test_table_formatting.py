import unittest

from app.table_formatting import (
    build_table_format_prompt,
    convert_key_value_lines_to_markdown_table,
    convert_pipe_rows_to_markdown_table,
    convert_text_list_to_markdown_table,
    looks_like_markdown_table,
    to_markdown_table,
)


class TestTableFormatting(unittest.TestCase):
    def test_convert_text_list_to_markdown_table(self) -> None:
        table = convert_text_list_to_markdown_table("- quake 1\n- quake 2")
        self.assertIn("| Value |", table)
        self.assertIn("| quake 1 |", table)

    def test_looks_like_markdown_table(self) -> None:
        self.assertTrue(looks_like_markdown_table("| A |\n| --- |\n| 1 |"))
        self.assertFalse(looks_like_markdown_table("not a table"))

    def test_convert_pipe_rows_to_markdown_table(self) -> None:
        table = convert_pipe_rows_to_markdown_table("| quake 1 | 5.4 |")
        self.assertIn("| Column 1 | Column 2 |", table)
        self.assertIn("| quake 1 | 5.4 |", table)

    def test_convert_key_value_lines_to_markdown_table(self) -> None:
        table = convert_key_value_lines_to_markdown_table(
            "Name: Quake 1\nMagnitude: 5.4")
        self.assertIn("| Field | Value |", table)
        self.assertIn("| Name | Quake 1 |", table)

    def test_to_markdown_table_prefers_existing_table(self) -> None:
        source = "| Name | Magnitude |\n| --- | --- |\n| Quake 1 | 5.4 |"
        self.assertEqual(to_markdown_table(source), source)

    def test_build_table_format_prompt_contains_context(self) -> None:
        prompt = build_table_format_prompt(
            "show this in table format", "quake 1")
        self.assertIn(
            "User follow-up request: show this in table format", prompt)
        self.assertIn("Previous database answer:\nquake 1", prompt)


if __name__ == "__main__":
    unittest.main()
