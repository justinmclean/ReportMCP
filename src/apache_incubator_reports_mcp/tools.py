from __future__ import annotations

from pathlib import Path
from typing import Any

from apache_incubator_reports_mcp import schemas
from apache_incubator_reports_mcp.parser import (
    ASF_REPORTS_REPO_URL,
    DEFAULT_CACHE_DIR,
    cache_report_url,
    cache_reports_from_repo,
    find_report,
    load_reports,
    podling_reports,
    report_summary,
    reports_overview,
)
from apache_incubator_reports_mcp.parser import (
    list_podlings as parser_list_podlings,
)
from apache_incubator_reports_mcp.parser import (
    search_reports as parser_search_reports,
)
from apache_incubator_reports_mcp.schedule import (
    current_year_month,
    report_due_date_schedule,
    report_due_dates_ical,
)

_CONFIGURED_CACHE_DIR: str | None = None
_CONFIGURED_REPO_URL: str | None = None


def configure_defaults(
    cache_dir: str | None = None,
    repo_url: str | None = None,
) -> None:
    global _CONFIGURED_CACHE_DIR, _CONFIGURED_REPO_URL
    if cache_dir:
        _CONFIGURED_CACHE_DIR = cache_dir
    if repo_url:
        _CONFIGURED_REPO_URL = repo_url


def require_non_empty_string(value: Any, key: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"'{key}' must be a string")
    stripped = value.strip()
    if not stripped:
        raise ValueError(f"'{key}' must be a non-empty string")
    return stripped


def optional_string(value: Any, key: str) -> str | None:
    if value is None:
        return None
    return require_non_empty_string(value, key)


def require_limit(value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("'limit' must be an integer")
    if value <= 0:
        raise ValueError("'limit' must be greater than 0")
    return value


def require_years(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("'years' must be an integer or null")
    if value <= 0:
        raise ValueError("'years' must be greater than 0")
    return value


def require_year(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("'year' must be an integer or null")
    if value < 2000 or value > 2099:
        raise ValueError("'year' must be between 2000 and 2099")
    return value


def require_month(value: Any) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError("'month' must be an integer or null")
    if value < 1 or value > 12:
        raise ValueError("'month' must be between 1 and 12")
    return value


def resolve_cache_dir(value: str | None = None) -> str:
    return optional_string(value, "cache_dir") or _CONFIGURED_CACHE_DIR or DEFAULT_CACHE_DIR


def resolve_repo_url(value: str | None = None) -> str:
    return optional_string(value, "repo_url") or _CONFIGURED_REPO_URL or ASF_REPORTS_REPO_URL


def resolve_reports_dir(
    reports_dir: str | None = None,
    cache_dir: str | None = None,
    refresh: bool = False,
) -> str:
    return _resolve_reports_dir(reports_dir, cache_dir, refresh)[0]


def _resolve_reports_dir(
    reports_dir: str | None,
    cache_dir: str | None,
    refresh: bool,
) -> tuple[str, str | None]:
    """Return the reports directory and a warning if a refresh failed.

    A refresh that fails part way, for example when apache.org is slow or
    returns an error, falls back to the existing cache rather than failing
    the read.
    """
    if reports_dir is not None:
        return require_non_empty_string(reports_dir, "reports_dir"), None
    resolved_cache_dir = resolve_cache_dir(cache_dir)
    if not Path(resolved_cache_dir).expanduser().exists():
        cache_all_reports(cache_dir=resolved_cache_dir)
    elif refresh:
        try:
            cache_all_reports(cache_dir=resolved_cache_dir, skip_cached=True)
        except (OSError, ValueError) as error:
            return resolved_cache_dir, (
                f"Refresh failed ({error or type(error).__name__}), so cached reports were used."
            )
    return resolved_cache_dir, None


def _with_warning(payload: dict[str, Any], warning: str | None) -> dict[str, Any]:
    if warning:
        payload["refresh_warning"] = warning
    return payload


def incubator_reports_overview(
    reports_dir: str | None = None,
    cache_dir: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Return a high-level summary of cached ASF Incubator reports."""
    resolved, warning = _resolve_reports_dir(reports_dir, cache_dir, refresh)
    return _with_warning(reports_overview(resolved), warning)


def cache_all_reports(
    repo_url: str | None = None,
    cache_dir: str | None = None,
    years: int | None = 2,
    limit: int | None = None,
    skip_cached: bool = False,
) -> dict[str, Any]:
    """Download approved ASF Incubator reports into the local cache."""
    resolved_years = require_years(years)
    resolved_limit = require_limit(limit) if limit is not None else None
    return cache_reports_from_repo(
        repo_url=resolve_repo_url(repo_url),
        cache_dir=resolve_cache_dir(cache_dir),
        years=resolved_years,
        limit=resolved_limit,
        skip_cached=skip_cached,
    )


def cache_report(
    url: str,
    cache_dir: str | None = None,
    report_id: str | None = None,
) -> dict[str, Any]:
    """Download one Incubator report URL into the local cache."""
    return cache_report_url(
        require_non_empty_string(url, "url"),
        cache_dir=resolve_cache_dir(cache_dir),
        report_id=optional_string(report_id, "report_id"),
    )


def list_reports(
    reports_dir: str | None = None,
    cache_dir: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """List cached Incubator report documents."""
    resolved, warning = _resolve_reports_dir(reports_dir, cache_dir, refresh)
    reports = load_reports(resolved)
    payload = {
        "count": len(reports),
        "reports": [
            {
                "report_id": report.report_id,
                "title": report.title,
                "report_period": report.report_period,
                "source_status": report.source_status,
                "source_status_note": report.source_status_note,
                "podling_count": len(report.podling_reports),
                "path": report.path,
                "source_url": report.source_url,
                "cached_at": report.cached_at,
            }
            for report in reports
        ],
    }
    return _with_warning(payload, warning)


def list_podlings(
    reports_dir: str | None = None,
    cache_dir: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """List podlings that appear in cached Incubator reports."""
    resolved, warning = _resolve_reports_dir(reports_dir, cache_dir, refresh)
    return _with_warning(
        {"reports_dir": resolved, "podlings": parser_list_podlings(resolved)}, warning
    )


def search_reports(
    query: str,
    reports_dir: str | None = None,
    cache_dir: str | None = None,
    refresh: bool = False,
    limit: int = 20,
) -> dict[str, Any]:
    """Search cached Incubator reports by text or podling name."""
    resolved_limit = require_limit(limit)
    resolved, warning = _resolve_reports_dir(reports_dir, cache_dir, refresh)
    rows = parser_search_reports(resolved, require_non_empty_string(query, "query"))
    return _with_warning(
        {"query": query, "count": len(rows), "results": rows[:resolved_limit]}, warning
    )


def get_report_summary(
    report_id: str,
    reports_dir: str | None = None,
    cache_dir: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Return parsed summary details for one cached Incubator report."""
    resolved, warning = _resolve_reports_dir(reports_dir, cache_dir, refresh)
    report = find_report(resolved, require_non_empty_string(report_id, "report_id"))
    return _with_warning(report_summary(report), warning)


def get_report_markdown(
    report_id: str,
    reports_dir: str | None = None,
    cache_dir: str | None = None,
    refresh: bool = False,
) -> str:
    """Return the raw text for one cached Incubator report."""
    report = find_report(
        resolve_reports_dir(reports_dir, cache_dir, refresh),
        require_non_empty_string(report_id, "report_id"),
    )
    return report.raw_text


def get_podling_reports(
    podling: str,
    reports_dir: str | None = None,
    cache_dir: str | None = None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Return all cached report entries for one podling."""
    resolved_podling = require_non_empty_string(podling, "podling")
    resolved, warning = _resolve_reports_dir(reports_dir, cache_dir, refresh)
    rows = podling_reports(resolved, resolved_podling)
    return _with_warning(
        {"podling": resolved_podling, "count": len(rows), "reports": rows}, warning
    )


def get_report_due_dates(
    year: int | None = None,
    month: int | None = None,
    count: int = 12,
) -> dict[str, Any]:
    """Return Incubator report due dates based on ASF Board meeting dates."""
    schedule = _report_due_date_schedule_from_args(year, month, count)
    return {
        "schedule_basis": {
            "board_meeting": "Typically the third Wednesday of each month",
            "podling_reports_due": "Two weeks before the ASF Board meeting",
            "mentor_signoff_due": "One week before the ASF Board meeting",
        },
        "count": len(schedule),
        "due_dates": schedule,
    }


def _report_due_date_schedule_from_args(
    year: int | None,
    month: int | None,
    count: int,
) -> list[dict[str, Any]]:
    resolved_year = require_year(year)
    resolved_month = require_month(month)
    resolved_count = require_limit(count)
    if resolved_year is None and resolved_month is None:
        current_year, current_month = current_year_month()
        resolved_year = current_year
        resolved_month = current_month
    elif resolved_year is None:
        resolved_year = current_year_month()[0]
    elif resolved_month is None:
        resolved_month = 1
    assert resolved_year is not None
    assert resolved_month is not None
    return report_due_date_schedule(resolved_year, resolved_month, resolved_count)


def get_report_due_dates_ical(
    year: int | None = None,
    month: int | None = None,
    count: int = 12,
) -> dict[str, Any]:
    """Return an importable iCalendar file for Incubator report due dates."""
    schedule = _report_due_date_schedule_from_args(year, month, count)
    first_period = schedule[0]["report_period"]
    filename = f"apache-incubator-report-due-dates-{first_period}.ics"
    return {
        "filename": filename,
        "content_type": "text/calendar",
        "count": len(schedule),
        "event_count": len(schedule) * 3,
        "calendar": report_due_dates_ical(schedule),
    }


TOOLS: dict[str, dict[str, Any]] = {
    "incubator_reports_overview": schemas.tool_definition(
        description="Return a high-level summary of cached ASF Incubator reports.",
        handler=incubator_reports_overview,
        properties=schemas.base_properties(),
    ),
    "cache_all_reports": schemas.tool_definition(
        description="Download approved ASF Incubator reports into the local cache.",
        handler=cache_all_reports,
        properties=schemas.repo_cache_properties(),
    ),
    "cache_report": schemas.tool_definition(
        description="Download one Incubator report URL into the local cache.",
        handler=cache_report,
        properties=schemas.url_cache_properties(),
        required=["url"],
    ),
    "list_reports": schemas.tool_definition(
        description="List cached Incubator report documents.",
        handler=list_reports,
        properties=schemas.base_properties(),
    ),
    "list_podlings": schemas.tool_definition(
        description="List podlings that appear in cached Incubator reports.",
        handler=list_podlings,
        properties=schemas.base_properties(),
    ),
    "search_reports": schemas.tool_definition(
        description="Search cached Incubator reports by text or podling name.",
        handler=search_reports,
        properties=schemas.search_properties(),
        required=["query"],
    ),
    "get_report_summary": schemas.tool_definition(
        description="Return parsed summary details for one cached Incubator report.",
        handler=get_report_summary,
        properties=schemas.report_properties(),
        required=["report_id"],
    ),
    "get_report_markdown": schemas.tool_definition(
        description="Return the raw text for one cached Incubator report.",
        handler=get_report_markdown,
        properties=schemas.report_properties(),
        required=["report_id"],
    ),
    "get_podling_reports": schemas.tool_definition(
        description="Return all cached report entries for one podling.",
        handler=get_podling_reports,
        properties=schemas.podling_properties(),
        required=["podling"],
    ),
    "get_report_due_dates": schemas.tool_definition(
        description="Return Incubator report due dates based on ASF Board meeting dates.",
        handler=get_report_due_dates,
        properties=schemas.report_due_date_properties(),
    ),
    "get_report_due_dates_ical": schemas.tool_definition(
        description="Return an importable iCalendar file for Incubator report due dates.",
        handler=get_report_due_dates_ical,
        properties=schemas.report_due_date_properties(),
    ),
}
