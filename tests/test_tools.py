from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from apache_incubator_reports_mcp import tools
from tests.fixtures import report_dir


class ToolsTests(unittest.TestCase):
    def test_get_podling_reports(self) -> None:
        with report_dir() as base:
            result = tools.get_podling_reports("Alpha", reports_dir=str(base))

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["reports"][0]["observed_mentor_signoff_count"], 1)
        self.assertEqual(result["reports"][0]["mentor_signoff_color"], "neutral")
        self.assertFalse(result["reports"][0]["mentor_signoff_interpretation"]["is_missing_or_risk_metric"])

    def test_search_reports_limits_results(self) -> None:
        with report_dir() as base:
            result = tools.search_reports("release", reports_dir=str(base), limit=1)

        self.assertGreaterEqual(result["count"], 1)
        self.assertEqual(len(result["results"]), 1)

    def test_tools_registered_with_schemas(self) -> None:
        self.assertIn("cache_all_reports", tools.TOOLS)
        self.assertEqual(
            tools.TOOLS["cache_all_reports"]["inputSchema"]["properties"]["repo_url"]["type"],
            "string",
        )
        self.assertEqual(
            tools.TOOLS["cache_all_reports"]["inputSchema"]["properties"]["years"]["type"],
            ["integer", "null"],
        )

    def test_cache_all_reports_passes_years_and_limit(self) -> None:
        with patch.object(
            tools,
            "cache_reports_from_repo",
            return_value={"cached_count": 0},
        ) as mocked:
            tools.cache_all_reports(years=3, limit=5)

        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.kwargs["years"], 3)
        self.assertEqual(mocked.call_args.kwargs["limit"], 5)

    def test_cache_all_reports_rejects_invalid_years(self) -> None:
        with self.assertRaisesRegex(ValueError, "'years' must be greater than 0"):
            tools.cache_all_reports(years=0)

    def test_get_report_due_dates(self) -> None:
        result = tools.get_report_due_dates(year=2026, month=5, count=2)

        self.assertEqual(result["count"], 2)
        self.assertEqual(
            result["schedule_basis"]["podling_reports_due"],
            "Two weeks before the ASF Board meeting",
        )
        self.assertEqual(
            result["due_dates"][0],
            {
                "report_period": "2026-05",
                "podling_reports_due": "2026-05-06",
                "mentor_signoff_due": "2026-05-13",
                "board_meeting": "2026-05-20",
            },
        )
        self.assertEqual(result["due_dates"][1]["report_period"], "2026-06")
        self.assertEqual(result["due_dates"][1]["board_meeting"], "2026-06-17")

    def test_get_report_due_dates_defaults_year_to_january(self) -> None:
        result = tools.get_report_due_dates(year=2026, count=1)

        self.assertEqual(result["due_dates"][0]["report_period"], "2026-01")
        self.assertEqual(result["due_dates"][0]["board_meeting"], "2026-01-21")

    def test_get_report_due_dates_rejects_invalid_month(self) -> None:
        with self.assertRaisesRegex(ValueError, "'month' must be between 1 and 12"):
            tools.get_report_due_dates(year=2026, month=13)

    def test_get_report_due_dates_ical(self) -> None:
        result = tools.get_report_due_dates_ical(year=2026, month=5, count=1)
        calendar = result["calendar"]

        self.assertEqual(result["filename"], "apache-incubator-report-due-dates-2026-05.ics")
        self.assertEqual(result["content_type"], "text/calendar")
        self.assertEqual(result["event_count"], 3)
        self.assertTrue(calendar.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertIn("VERSION:2.0\r\n", calendar)
        self.assertIn("SUMMARY:ASF Incubator podling reports due (2026-05)\r\n", calendar)
        self.assertIn("SUMMARY:ASF Incubator mentor sign-off due (2026-05)\r\n", calendar)
        self.assertIn("SUMMARY:ASF Board meeting (2026-05)\r\n", calendar)
        self.assertIn("DTSTART;VALUE=DATE:20260506\r\n", calendar)
        self.assertIn("DTSTART;VALUE=DATE:20260513\r\n", calendar)
        self.assertIn("DTSTART;VALUE=DATE:20260520\r\n", calendar)
        self.assertEqual(calendar.count("BEGIN:VEVENT"), 3)
        self.assertTrue(calendar.endswith("END:VCALENDAR\r\n"))


if __name__ == "__main__":
    unittest.main()
