from __future__ import annotations

from pathlib import Path
import sys
import unittest
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
        with patch.object(tools, "cache_reports_from_repo", return_value={"cached_count": 0}) as mocked:
            tools.cache_all_reports(years=3, limit=5)

        mocked.assert_called_once()
        self.assertEqual(mocked.call_args.kwargs["years"], 3)
        self.assertEqual(mocked.call_args.kwargs["limit"], 5)

    def test_cache_all_reports_rejects_invalid_years(self) -> None:
        with self.assertRaisesRegex(ValueError, "'years' must be greater than 0"):
            tools.cache_all_reports(years=0)


if __name__ == "__main__":
    unittest.main()
