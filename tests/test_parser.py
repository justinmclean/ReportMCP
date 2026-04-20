from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apache_incubator_reports_mcp import parser
from tests.fixtures import SAMPLE_REPORT, report_dir


class ParserTests(unittest.TestCase):
    def test_parse_report_text_extracts_podling_sections(self) -> None:
        report = parser.parse_report_text(SAMPLE_REPORT, "2026-04", "/tmp/2026-04.txt")

        self.assertEqual(report.title, "Incubator Report April 2026")
        self.assertEqual(report.report_period, "2026-04")
        self.assertEqual([item.podling for item in report.podling_reports], ["Alpha", "Bravo"])
        self.assertEqual(report.podling_reports[0].mentor_signoff_count, 1)
        self.assertEqual(report.podling_reports[0].mentor_entry_count, 2)
        serialized = report.podling_reports[0].to_dict()
        self.assertFalse(serialized["mentor_signoff_interpretation"]["is_completion_fraction"])
        self.assertEqual(serialized["mentor_signoff_interpretation"]["color_treatment"], "neutral")
        self.assertEqual(report.podling_reports[0].last_release, "2026-03-15")
        self.assertEqual(report.podling_reports[0].issues[0], "Grow the committer base.")

    def test_load_reports_and_overview(self) -> None:
        with report_dir() as base:
            overview = parser.reports_overview(base)

        self.assertEqual(overview["report_count"], 1)
        self.assertEqual(overview["podling_count"], 2)
        self.assertEqual(overview["report_periods"], ["2026-04"])
        self.assertEqual(overview["podlings"], ["Alpha", "Bravo"])

    def test_cache_report_url_writes_payload_and_metadata(self) -> None:
        class Response:
            headers = {"content-type": "text/plain"}

            def __enter__(self) -> "Response":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

            def read(self) -> bytes:
                return SAMPLE_REPORT.encode("utf-8")

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("urllib.request.urlopen", return_value=Response()):
                result = parser.cache_report_url(
                    "https://whimsy.apache.org/board/minutes/Incubator.html",
                    cache_dir=temp_dir,
                    report_id="report202604",
                )

            self.assertTrue(Path(result["path"]).exists())
            self.assertTrue(Path(result["metadata_path"]).exists())
            self.assertEqual(result["report"]["report_id"], "report202604")
            self.assertEqual(result["report"]["podling_count"], 2)
            self.assertFalse(
                result["report"]["visualization_hints"]["observed_mentor_signoff_count"][
                    "is_completion_fraction"
                ]
            )


if __name__ == "__main__":
    unittest.main()
