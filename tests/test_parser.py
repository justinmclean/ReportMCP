from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
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

    def test_parse_report_text_without_table_of_contents_returns_no_podling_sections(self) -> None:
        report = parser.parse_report_text(
            """# Incubator Report April 2026

## Alpha

Alpha has been incubating since 2025-01-01.

Three most important unfinished issues to address before graduating:

1. Grow the committer base.

Signed-off-by:

  [x] (alpha) Mentor One
""",
            "2026-04",
            "/tmp/2026-04.txt",
        )

        self.assertEqual(report.podling_reports, [])

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

    def test_cache_reports_from_repo_filters_to_recent_years(self) -> None:
        now = datetime.now(UTC)
        recent_url = f"https://example.invalid/reports/report{now.year}{now.month:02d}.txt"
        old_url = f"https://example.invalid/reports/report{now.year - 3}{now.month:02d}.txt"

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(parser, "discover_report_urls", return_value=[recent_url, old_url]),
                patch.object(
                    parser,
                    "cache_report_url",
                    side_effect=lambda url, cache_dir: {"url": url, "cache_dir": cache_dir},
                ),
            ):
                result = parser.cache_reports_from_repo(
                    repo_url="https://example.invalid/reports/",
                    cache_dir=temp_dir,
                    years=2,
                )

        self.assertEqual(result["discovered_count"], 2)
        self.assertEqual(result["cached_count"], 1)
        self.assertEqual(result["cached_reports"][0]["url"], recent_url)

    def test_cache_reports_from_repo_allows_full_history_when_years_is_none(self) -> None:
        now = datetime.now(UTC)
        recent_url = f"https://example.invalid/reports/report{now.year}{now.month:02d}.txt"
        old_url = f"https://example.invalid/reports/report{now.year - 3}{now.month:02d}.txt"

        with tempfile.TemporaryDirectory() as temp_dir:
            with (
                patch.object(parser, "discover_report_urls", return_value=[recent_url, old_url]),
                patch.object(
                    parser,
                    "cache_report_url",
                    side_effect=lambda url, cache_dir: {"url": url, "cache_dir": cache_dir},
                ),
            ):
                result = parser.cache_reports_from_repo(
                    repo_url="https://example.invalid/reports/",
                    cache_dir=temp_dir,
                    years=None,
                )

        self.assertEqual(result["cached_count"], 2)

    def test_cache_reports_from_repo_skip_cached_fetches_only_new_minutes(self) -> None:
        year = datetime.now(UTC).year
        base = "https://example.invalid/foundation/records/minutes"
        cached_url = f"{base}/{year}/board_minutes_{year}_01_21.txt"
        new_url = f"{base}/{year}/board_minutes_{year}_02_18.txt"
        special_url = f"{base}/{year}/board_minutes_{year}_02_25.txt"
        old_url = f"{base}/board_minutes_1999_04_13.txt"
        fetched: list[str] = []

        def fake_cache(url: str, cache_dir: str) -> dict[str, str]:
            fetched.append(url)
            if url == special_url:
                raise ValueError(f"{parser.NO_INCUBATOR_REPORT_ERROR}: {url}")
            return {"url": url}

        with tempfile.TemporaryDirectory() as temp_dir:
            Path(temp_dir, f"board-minutes-{year}-01-21.txt").write_text("cached", encoding="utf-8")
            urls = [cached_url, new_url, special_url, old_url]
            with (
                patch.object(parser, "discover_report_urls", return_value=urls),
                patch.object(parser, "cache_report_url", side_effect=fake_cache),
            ):
                first = parser.cache_reports_from_repo(cache_dir=temp_dir, skip_cached=True)
                fetched.clear()
                parser.cache_reports_from_repo(cache_dir=temp_dir, skip_cached=True)

        self.assertEqual(first["skipped_cached_count"], 1)
        self.assertEqual(first["cached_count"], 1)
        # The 1999 minutes are outside the window, and the special meeting is
        # remembered, so a second refresh only retries the new report.
        self.assertEqual(fetched, [new_url])

    def test_within_years_window_uses_calendar_years(self) -> None:
        now = datetime(2026, 4, 25, tzinfo=UTC)

        self.assertTrue(parser._within_years_window("2026-01", 2, now=now))
        self.assertTrue(parser._within_years_window("2025-12", 2, now=now))
        self.assertFalse(parser._within_years_window("2024-12", 2, now=now))

    def test_report_period_from_board_minutes_filename(self) -> None:
        self.assertEqual(
            parser.report_period_from_text(
                "https://apache.org/foundation/records/minutes/2015/board_minutes_2015_06_17.txt"
            ),
            "2015-06",
        )

    def test_extract_issues_merges_wrapped_bullet_lines(self) -> None:
        body = """Three most important unfinished issues to address before graduating:

- Grow the community(attracting more committers, contributors, and
  users).
- Improve docs.

Date of last release: 2025-01-01
"""

        self.assertEqual(
            parser._extract_issues(body),
            [
                "Grow the community(attracting more committers, contributors, and users).",
                "Improve docs.",
            ],
        )

    def test_extract_issues_drops_empty_numbered_placeholders(self) -> None:
        body = """Three most important unfinished issues to address before graduating:

  1. Grow the community (committers, contributors, users)
  2. Create releases
  3.

### Are there any issues that the IPMC or ASF Board need to be aware of?

  None
"""

        self.assertEqual(
            parser._extract_issues(body),
            ["Grow the community (committers, contributors, users)", "Create releases"],
        )

    def test_extract_issues_splits_numbers_without_a_space(self) -> None:
        body = """Three most important unfinished issues to address before graduating:

  1.Keep growing the community, attract more contributors and committers
  2.Release Apache standard releases regularly
  3.Continuously improve system performance

### Are there any issues that the IPMC or ASF Board need to be aware of?
"""

        self.assertEqual(
            parser._extract_issues(body),
            [
                "Keep growing the community, attract more contributors and committers",
                "Release Apache standard releases regularly",
                "Continuously improve system performance",
            ],
        )

    def test_extract_issues_drops_na_and_keeps_sub_bullets_with_their_item(self) -> None:
        body = """Three most important unfinished issues to address before graduating:

  1. Successfully make releases without WIP disclaimer.
     - ONGOING.
  2. N/A
  3. N/A

### Are there any issues that the IPMC or ASF Board need to be aware of?
"""

        self.assertEqual(
            parser._extract_issues(body),
            ["Successfully make releases without WIP disclaimer. ONGOING."],
        )

    def test_extract_issues_reads_past_1200_characters(self) -> None:
        long_item = "Grow the community " * 80
        body = f"""Three most important unfinished issues to address before graduating:

  1. {long_item.strip()}
  2. Make another release.

Date of last release: none
"""

        issues = parser._extract_issues(body)
        self.assertEqual(len(issues), 2)
        self.assertEqual(issues[1], "Make another release.")

    def test_parse_report_text_marks_no_report_submitted_source_status(self) -> None:
        report = parser.parse_report_text(
            "# Incubator PMC report 2024-07-17\n\nNo report was submitted.\n",
            "report202407",
            "/tmp/report202407.txt",
        )

        self.assertEqual(report.source_status, "no_report_submitted")
        self.assertEqual(report.source_status_note, "No report was submitted.")
        self.assertEqual(report.podling_reports, [])

    def test_discover_report_urls_recurses_year_directories(self) -> None:
        root_listing = """
        <html><body>
        <a href="2024/">2024/</a>
        <a href="2025/">2025/</a>
        </body></html>
        """
        year_2024 = """
        <html><body>
        <a href="board_minutes_2024_04_17.txt">Apr 2024</a>
        <a href="board_minutes_2024_05_15.txt">May 2024</a>
        </body></html>
        """
        year_2025 = """
        <html><body>
        <a href="board_minutes_2025_02_19.txt">Feb 2025</a>
        </body></html>
        """

        def fake_download(url: str) -> tuple[bytes, str]:
            pages = {
                "https://apache.org/foundation/records/minutes/": root_listing,
                "https://apache.org/foundation/records/minutes/2024/": year_2024,
                "https://apache.org/foundation/records/minutes/2025/": year_2025,
            }
            return pages[url].encode("utf-8"), "text/html"

        with patch.object(parser, "_download", side_effect=fake_download):
            urls = parser.discover_report_urls("https://apache.org/foundation/records/minutes/")

        self.assertEqual(
            urls,
            [
                "https://apache.org/foundation/records/minutes/2024/board_minutes_2024_04_17.txt",
                "https://apache.org/foundation/records/minutes/2024/board_minutes_2024_05_15.txt",
                "https://apache.org/foundation/records/minutes/2025/board_minutes_2025_02_19.txt",
            ],
        )

    def test_parse_report_text_keeps_report_present_without_inventing_content_scope(self) -> None:
        report = parser.parse_report_text(
            """# Incubator PMC report for March 2025

## Community

## Table of Contents
[Gravitino](#gravitino)
""",
            "report202503",
            "/tmp/report202503.txt",
        )

        self.assertEqual(report.source_status, "report_present")
        self.assertEqual(report.podling_reports, [])

    def test_parse_report_text_uses_table_of_contents_names_for_podlings(self) -> None:
        report = parser.parse_report_text(
            """# Incubator PMC report for March 2025

## Table of Contents
[Gravitino](#gravitino)
[Wayang](#wayang)

## Gravitino

Project notes without the older stock prompts.

## Wayang

More project notes without the older stock prompts.

## Releases

- Something else
""",
            "report202503",
            "/tmp/report202503.txt",
        )

        self.assertEqual([item.podling for item in report.podling_reports], ["Gravitino", "Wayang"])

    def test_load_reports_includes_board_minutes_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            (base / "report202604.txt").write_text(SAMPLE_REPORT, encoding="utf-8")
            (base / "board-minutes-2025-06-18.txt").write_text(
                "No report was submitted.\n",
                encoding="utf-8",
            )

            reports = parser.load_reports(base)

        self.assertEqual(len(reports), 2)
        self.assertEqual(
            [report.report_id for report in reports],
            ["board-minutes-2025-06-18", "report202604"],
        )

    def test_template_heading_is_not_treated_as_podling(self) -> None:
        report = parser.parse_report_text(
            """# Incubator Report April 2026

## Table of Contents
[Alpha](#alpha)

## Alpha

Alpha has been incubating since 2025-01-01.

### Three most important unfinished issues to address before graduating:

How has the project developed since the last report?

Steady progress.

### Signed-off-by:

[x] Mentor One
""",
            "report202604",
            "/tmp/report202604.txt",
        )

        self.assertEqual([item.podling for item in report.podling_reports], ["Alpha"])

    def test_date_of_last_release_heading_is_not_treated_as_podling(self) -> None:
        report = parser.parse_report_text(
            """# Incubator Report May 2022

## Table of Contents
[AGE](#age)

## AGE

AGE has been incubating since 2020-04-29.

### Date of last release:

2022-04-21

### Signed-off-by:

- [x] Felix Cheung
""",
            "report202205",
            "/tmp/report202205.txt",
        )

        self.assertEqual([item.podling for item in report.podling_reports], ["AGE"])

    def test_template_questions_as_same_level_headings_stay_in_the_report(self) -> None:
        text = """# Incubator PMC report for May 2026

## Table of Contents
[Alpha](#alpha)
[Bravo](#bravo)

## Alpha

Alpha has been incubating since 2025-04-12.

## Three most important unfinished issues to address before graduating:

1. Grow the committer base.
2. Make another release.

## Date of last release:

2026-04-25

## Signed-off-by:

- [X] (alpha) Mentor One

--------------------
## Bravo

Bravo has been incubating since 2024-07-01.

### Three most important unfinished issues to address before graduating:

1. Improve release cadence.

--------------------
## Charlie

Charlie is new and missing from the table of contents.
"""
        report = parser.parse_report_text(text, "board-minutes-2026-05-20", "/tmp/r.txt")
        alpha, bravo = report.podling_reports

        self.assertEqual(alpha.issues, ["Grow the committer base.", "Make another release."])
        self.assertEqual(alpha.last_release, "2026-04-25")
        self.assertEqual(alpha.mentor_signoff_count, 1)
        self.assertNotIn("Charlie", bravo.body)

    def test_report_ends_at_the_next_heading_even_if_not_in_the_contents(self) -> None:
        text = """# Incubator PMC report for May 2025

## Table of Contents
[Alpha](#alpha)

## Alpha

### Three most important unfinished issues to address before graduating:

1. Grow the committer base.

## Bravo

### Signed-off-by:

- [X] (bravo) Mentor Two
"""
        report = parser.parse_report_text(text, "board-minutes-2025-05-21", "/tmp/r.txt")

        self.assertNotIn("Mentor Two", report.podling_reports[0].body)

    def test_appended_previous_month_report_is_dropped(self) -> None:
        text = """# Incubator PMC report for June 2025

## Table of Contents
[Alpha](#alpha)

## Alpha

Alpha June text.

# Incubator PMC report for May 2025

## Table of Contents
[Alpha](#alpha)

## Alpha

Alpha May text.
"""
        report = parser.parse_report_text(text, "board-minutes-2025-06-18", "/tmp/r.txt")

        self.assertEqual(len(report.podling_reports), 1)
        self.assertIn("June", report.podling_reports[0].body)

    def test_last_release_reads_a_wrapped_answer(self) -> None:
        body = """### Date of last release:

2025-06-04 (0.3.0-incubating). rc1 for 0.4.0-incubating was cancelled on
2026-07-27; rc2 is in preparation

### When were the last committers or PPMC members elected?
"""
        self.assertEqual(
            parser._extract_first(parser.LAST_RELEASE_RE, body),
            "2025-06-04 (0.3.0-incubating). rc1 for 0.4.0-incubating was cancelled on "
            "2026-07-27; rc2 is in preparation",
        )

    def test_cache_report_url_accepts_direct_board_minutes_urls(self) -> None:
        incubator_report = """# Incubator PMC report for June 2025

## Table of Contents
[Alpha](#alpha)
[Bravo](#bravo)

## Alpha

Alpha has been incubating since 2025-01-01.

Three most important unfinished issues to address before graduating:

1. Grow the committer base.
2. Make another Apache release.

Date of last release: 2025-05-01

Signed-off-by:

  [x] (alpha) Mentor One
  [ ] (alpha) Mentor Two

## Bravo

Bravo has been incubating since 2024-07-01.

Three most important unfinished issues to address before graduating:

- Improve release cadence.

Date of last release: none yet

Signed-off-by:

  [x] (bravo) Mentor Three
"""
        board_minutes = """The Apache Software Foundation

Board of Directors Meeting Minutes

June 18, 2025

    AG. Apache Incubator Project [Justin Mclean]

       See Attachment AG

-----------------------------------------
Attachment AG: Report from the Apache Incubator Project  [Justin Mclean]

""" + incubator_report + """
-----------------------------------------
Attachment AH: Report from the Apache James Project  [Benoit Tellier]
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("urllib.request.urlopen", return_value=type("Response", (), {
                "headers": {"content-type": "text/plain"},
                "__enter__": lambda self: self,
                "__exit__": lambda self, *_args: None,
                "read": lambda self: board_minutes.encode("utf-8"),
            })()):
                result = parser.cache_report_url(
                    "https://apache.org/foundation/records/minutes/2025/board_minutes_2025_06_18.txt",
                    cache_dir=temp_dir,
                )

        self.assertEqual(result["report"]["podling_count"], 2)

    def test_cache_report_url_extracts_incubator_attachment_from_board_minutes(self) -> None:
        board_minutes = """The Apache Software Foundation

Board of Directors Meeting Minutes

February 19, 2025

  6. Committee Reports

    AG. Apache Incubator Project [Justin Mclean]

       See Attachment AG

-----------------------------------------
Attachment AG: Report from the Apache Incubator Project  [Justin Mclean]

# Incubator PMC report for February 2025

## Table of Contents
[Alpha](#alpha)

## Alpha

Alpha has been incubating since 2024-01-01.

### Signed-off-by:

- [x] Mentor One

-----------------------------------------
Attachment AH: Report from the Apache James Project  [Benoit Tellier]
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("urllib.request.urlopen", return_value=type("Response", (), {
                "headers": {"content-type": "text/plain"},
                "__enter__": lambda self: self,
                "__exit__": lambda self, *_args: None,
                "read": lambda self: board_minutes.encode("utf-8"),
            })()):
                result = parser.cache_report_url(
                    "https://apache.org/foundation/records/minutes/2025/board_minutes_2025_02_19.txt",
                    cache_dir=temp_dir,
                )

        self.assertEqual(result["report"]["title"], "Incubator PMC report for February 2025")
        self.assertEqual(result["report"]["source_status"], "report_present")
        self.assertEqual(result["report"]["podling_count"], 1)

    def test_cache_report_url_marks_no_report_submitted_from_board_minutes_entry(self) -> None:
        board_minutes = """The Apache Software Foundation

Board of Directors Meeting Minutes

July 17, 2024

    AH. Apache Incubator Project [Justin Mclean]

       No report was submitted.
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("urllib.request.urlopen", return_value=type("Response", (), {
                "headers": {"content-type": "text/plain"},
                "__enter__": lambda self: self,
                "__exit__": lambda self, *_args: None,
                "read": lambda self: board_minutes.encode("utf-8"),
            })()):
                result = parser.cache_report_url(
                    "https://apache.org/foundation/records/minutes/2024/board_minutes_2024_07_17.txt",
                    cache_dir=temp_dir,
                )

        self.assertEqual(result["report"]["source_status"], "no_report_submitted")
        self.assertEqual(result["report"]["podling_count"], 0)

    def test_cache_report_url_keeps_report_present_even_if_body_mentions_phrase(self) -> None:
        board_minutes = """The Apache Software Foundation

Board of Directors Meeting Minutes

February 19, 2025

    AG. Apache Incubator Project [Justin Mclean]

       See Attachment AG

-----------------------------------------
Attachment AG: Report from the Apache Incubator Project  [Justin Mclean]

# Incubator PMC report for February 2025

The incubator has not reported for several months. No report was submitted
for some earlier months, but this month the report is present.

## Table of Contents
[Alpha](#alpha)

## Alpha

Alpha has been incubating since 2024-01-01.

### Signed-off-by:

- [x] Mentor One

-----------------------------------------
Attachment AH: Report from the Apache James Project  [Benoit Tellier]
"""

        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("urllib.request.urlopen", return_value=type("Response", (), {
                "headers": {"content-type": "text/plain"},
                "__enter__": lambda self: self,
                "__exit__": lambda self, *_args: None,
                "read": lambda self: board_minutes.encode("utf-8"),
            })()):
                result = parser.cache_report_url(
                    "https://apache.org/foundation/records/minutes/2025/board_minutes_2025_02_19.txt",
                    cache_dir=temp_dir,
                )

        self.assertEqual(result["report"]["source_status"], "report_present")
        self.assertEqual(result["report"]["podling_count"], 1)


if __name__ == "__main__":
    unittest.main()
