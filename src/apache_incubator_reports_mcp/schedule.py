from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any


def current_year_month() -> tuple[int, int]:
    today = datetime.now(UTC).date()
    return today.year, today.month


def add_months(year: int, month: int, offset: int) -> tuple[int, int]:
    zero_based = (year * 12) + (month - 1) + offset
    return zero_based // 12, (zero_based % 12) + 1


def third_wednesday(year: int, month: int) -> date:
    first = date(year, month, 1)
    days_until_wednesday = (2 - first.weekday()) % 7
    return first + timedelta(days=days_until_wednesday + 14)


def report_due_dates(year: int, month: int) -> dict[str, Any]:
    board_meeting = third_wednesday(year, month)
    podling_due = board_meeting - timedelta(days=14)
    mentor_due = board_meeting - timedelta(days=7)
    return {
        "report_period": f"{year:04d}-{month:02d}",
        "podling_reports_due": podling_due.isoformat(),
        "mentor_signoff_due": mentor_due.isoformat(),
        "board_meeting": board_meeting.isoformat(),
    }


def report_due_date_schedule(year: int, month: int, count: int) -> list[dict[str, Any]]:
    return [
        report_due_dates(*add_months(year, month, offset))
        for offset in range(count)
    ]


def _escape_ical_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
    )


def _ical_date(value: str) -> date:
    return date.fromisoformat(value)


def _add_all_day_event(
    lines: list[str],
    *,
    uid: str,
    summary: str,
    event_date: date,
    timestamp: str,
    description: str,
) -> None:
    lines.extend(
        [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{timestamp}",
            f"DTSTART;VALUE=DATE:{event_date:%Y%m%d}",
            f"DTEND;VALUE=DATE:{event_date + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape_ical_text(summary)}",
            f"DESCRIPTION:{_escape_ical_text(description)}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    )


def report_due_dates_ical(schedule: list[dict[str, Any]]) -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Apache Incubator Reports MCP//Report Due Dates//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Apache Incubator Report Due Dates",
    ]

    event_specs = [
        (
            "podling_reports_due",
            "ASF Incubator podling reports due",
            "Podling reports are due two weeks before the ASF Board meeting.",
        ),
        (
            "mentor_signoff_due",
            "ASF Incubator mentor sign-off due",
            "Mentor sign-off is due one week before the ASF Board meeting.",
        ),
        (
            "board_meeting",
            "ASF Board meeting",
            "ASF Board meeting, typically held on the third Wednesday of the month.",
        ),
    ]
    for row in schedule:
        period = str(row["report_period"])
        for key, summary, description in event_specs:
            _add_all_day_event(
                lines,
                uid=f"apache-incubator-{period}-{key}@apache-incubator-reports-mcp",
                summary=f"{summary} ({period})",
                event_date=_ical_date(str(row[key])),
                timestamp=timestamp,
                description=description,
            )

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
