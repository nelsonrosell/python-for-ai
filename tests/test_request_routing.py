import unittest

from app.request_routing import (
    is_database_question,
    is_follow_up_question,
    is_table_format_follow_up,
    parse_email_request,
)


class TestRequestRouting(unittest.TestCase):
    def test_detects_database_question(self) -> None:
        self.assertTrue(is_database_question(
            "show the top earthquake countries"))
        self.assertFalse(is_database_question("write me a poem"))

    def test_detects_follow_up_question_from_phrase(self) -> None:
        self.assertTrue(is_follow_up_question("what about Australia?", False))

    def test_detects_follow_up_question_from_short_message(self) -> None:
        self.assertTrue(is_follow_up_question("and Australia?", True))
        self.assertFalse(is_follow_up_question("and Australia?", False))

    def test_detects_table_format_follow_up(self) -> None:
        self.assertTrue(is_table_format_follow_up("show this in table format"))
        self.assertFalse(is_table_format_follow_up("email this result"))

    def test_parses_email_request_and_attachment_flag(self) -> None:
        recipient, wants_attachment, attachment_format = parse_email_request(
            "email this to alice@example.com as attachment"
        )
        self.assertEqual(recipient, "alice@example.com")
        self.assertTrue(wants_attachment)
        self.assertIsNone(attachment_format)

    def test_parses_email_request_with_explicit_csv_attachment(self) -> None:
        recipient, wants_attachment, attachment_format = parse_email_request(
            "email it to alice@example.com the .csv file as attachment"
        )
        self.assertEqual(recipient, "alice@example.com")
        self.assertTrue(wants_attachment)
        self.assertEqual(attachment_format, "csv")

    def test_ignores_non_email_requests(self) -> None:
        recipient, wants_attachment, attachment_format = parse_email_request(
            "show earthquakes in Australia")
        self.assertEqual(recipient, "")
        self.assertFalse(wants_attachment)
        self.assertIsNone(attachment_format)


if __name__ == "__main__":
    unittest.main()
