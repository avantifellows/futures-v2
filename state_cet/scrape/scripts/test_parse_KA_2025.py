from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse_KA_2025 as parser


class _Page:
    def __init__(self, number: int, text: str, tables: list[list[list[str | None]]]):
        self.page_number = number
        self._text = text
        self._tables = tables

    def extract_text(self) -> str:
        return self._text

    def extract_tables(self):
        return self._tables

    def close(self) -> None:
        pass


class _Pdf:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class ParserTests(unittest.TestCase):
    def test_wrapped_fractional_rank(self):
        self.assertEqual(parser._parse_rank("124589.\n5"), 124589.5)
        self.assertEqual(parser._parse_rank("14631.87\n5"), 14631.875)

    def test_degree_prefix_is_program_identity(self):
        self.assertEqual(
            parser._normalize_course_name("B TECH IN COMPUTER SCIENCE"),
            "B TECH IN COMPUTER SCIENCE",
        )
        self.assertNotEqual(
            parser._normalize_course_name("B TECH IN COMPUTER SCIENCE"),
            parser._normalize_course_name("COMPUTER SCIENCE"),
        )

    def test_header_only_page_applies_to_next_page_table(self):
        pages = [
            _Page(1, "College: E237 Presidency University", []),
            _Page(2, "", [[['Course Name', 'GM'], ['COMPUTER\nSCIENCE', '5020']]]),
        ]
        with patch.object(parser.pdfplumber, "open", return_value=_Pdf(pages)):
            rows = parser.parse_pdf(Path("unused.pdf"), ["GM"], "GEN")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["college_code"], "E237")
        self.assertEqual(rows[0]["college_name"], "Presidency University")
        self.assertEqual(rows[0]["closing_rank"], 5020.0)


if __name__ == "__main__":
    unittest.main()
