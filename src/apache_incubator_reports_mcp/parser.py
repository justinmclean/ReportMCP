from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_REPORTS_DIR = "reports"
DEFAULT_CACHE_DIR = ".cache/incubator-reports"
ASF_REPORTS_REPO_URL = "https://whimsy.apache.org/board/minutes/Incubator.html"
SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".html", ".htm"}
GENERIC_HEADINGS = {
    "abstract",
    "board motion",
    "community",
    "content",
    "incubator",
    "incubator report",
    "incubator reports",
    "legal / trademarks",
    "legal/trademarks",
    "new podlings",
    "not yet ready to graduate",
    "are there any issues that the ipmc or asf board need to be aware of?",
    "have your mentors been helpful and responsive?",
    "how has the community developed since the last report?",
    "how has the project developed since the last report?",
    "how would you assess the podling's maturity?",
    "ipmc/shepherd notes:",
    "is the ppmc managing the podling's brand / trademarks?",
    "when were the last committers or ppmc members elected?",
    "podlings",
    "podlings that failed to report",
    "ready to graduate",
    "report",
    "shepherd assignments",
    "signed-off-by",
    "status",
}
DATE_PATTERNS = [
    re.compile(r"\b(20\d{2})[-_/ ](0?[1-9]|1[0-2])\b"),
    re.compile(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(?!\d)"),
    re.compile(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(20\d{2})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(20\d{2})\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\b",
        re.IGNORECASE,
    ),
]
MONTHS = {
    "january": "01",
    "february": "02",
    "march": "03",
    "april": "04",
    "may": "05",
    "june": "06",
    "july": "07",
    "august": "08",
    "september": "09",
    "october": "10",
    "november": "11",
    "december": "12",
}
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
HTML_HEADING_RE = re.compile(r"<h([1-6])[^>]*>(.*?)</h\1>", re.IGNORECASE | re.DOTALL)
HTML_BLOCK_RE = re.compile(r"</(?:p|div|li|tr|h[1-6])>", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
SIGNED_OFF_RE = re.compile(r"signed[- ]off[- ]by\s*:?", re.IGNORECASE)
CHECKBOX_RE = re.compile(r"\[\s*([xX ]?)\s*\]\s*(?:\(([^)]*)\))?\s*([^\n\r]+)")
LAST_RELEASE_RE = re.compile(r"date of (?:last )?release\s*:?\s*([^\n\r]+)", re.IGNORECASE)
INCUBATING_SINCE_RE = re.compile(r"incubat(?:ing|ion).*?since\s*:?\s*([^\n\r.]+)", re.IGNORECASE)

MENTOR_SIGNOFF_INTERPRETATION = {
    "metric": "observed_mentor_signoff_count",
    "meaning": "count of mentors who checked a sign-off box in the report text",
    "full_signoff_required": False,
    "is_completion_fraction": False,
    "is_missing_or_risk_metric": False,
    "color_treatment": "neutral",
    "client_guidance": (
        "Do not divide observed_mentor_signoff_count by mentor count, do not render it as red/orange/green "
        "completion, and do not treat partial sign-off as a problem."
    ),
}


@dataclass
class MentorSignoff:
    mentor: str
    checked: bool
    podling: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PodlingReport:
    podling: str
    heading: str
    body: str
    issues: list[str] = field(default_factory=list)
    signoffs: list[MentorSignoff] = field(default_factory=list)
    incubating_since: str | None = None
    last_release: str | None = None

    @property
    def mentor_signoff_count(self) -> int:
        return sum(1 for signoff in self.signoffs if signoff.checked)

    @property
    def mentor_entry_count(self) -> int:
        return len(self.signoffs)

    def to_dict(self, include_body: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "podling": self.podling,
            "heading": self.heading,
            "issues": self.issues,
            "mentor_signoff_note": "Full mentor sign-off is not required; these are observed checked sign-offs only.",
            "full_mentor_signoff_required": False,
            "mentor_signoff_status": "informational",
            "mentor_signoff_color": "neutral",
            "mentor_signoff_interpretation": MENTOR_SIGNOFF_INTERPRETATION,
            "observed_mentor_signoff_count": self.mentor_signoff_count,
            "signed_off_by": [signoff.mentor for signoff in self.signoffs if signoff.checked],
            "mentor_signoff_entries": [signoff.to_dict() for signoff in self.signoffs],
            "incubating_since": self.incubating_since,
            "last_release": self.last_release,
        }
        if include_body:
            data["body"] = self.body
        return data


@dataclass
class ParsedReport:
    report_id: str
    title: str
    path: str
    report_period: str | None
    generated_on: str | None
    podling_reports: list[PodlingReport]
    raw_text: str
    source_url: str | None = None
    cached_at: str | None = None

    def to_dict(self, include_raw: bool = False, include_bodies: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "report_id": self.report_id,
            "title": self.title,
            "path": self.path,
            "report_period": self.report_period,
            "generated_on": self.generated_on,
            "source_url": self.source_url,
            "cached_at": self.cached_at,
            "podling_count": len(self.podling_reports),
            "podlings": [item.to_dict(include_body=include_bodies) for item in self.podling_reports],
        }
        if include_raw:
            data["raw_text"] = self.raw_text
        return data


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "report"


def _strip_markdown(value: str) -> str:
    cleaned = re.sub(r"[*_`]+", "", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _html_to_markdownish(text: str) -> str:
    text = HTML_HEADING_RE.sub(lambda m: "\n" + "#" * int(m.group(1)) + " " + _strip_tags(m.group(2)) + "\n", text)
    text = HTML_BLOCK_RE.sub("\n", text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    return html.unescape(_strip_tags(text))


def _strip_tags(value: str) -> str:
    return TAG_RE.sub("", value)


def normalize_text(text: str, suffix: str = "") -> str:
    if suffix.lower() in {".html", ".htm"} or re.search(r"<html|<h[1-6]|<body", text, re.IGNORECASE):
        return _html_to_markdownish(text)
    return text


def report_period_from_text(*values: str) -> str | None:
    haystack = " ".join(value for value in values if value)
    for pattern in DATE_PATTERNS:
        match = pattern.search(haystack)
        if not match:
            continue
        if pattern is DATE_PATTERNS[0]:
            return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"
        if pattern is DATE_PATTERNS[1]:
            return f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"
        if pattern is DATE_PATTERNS[2]:
            return f"{int(match.group(2)):04d}-{MONTHS[match.group(1).casefold()]}"
        return f"{int(match.group(1)):04d}-{MONTHS[match.group(2).casefold()]}"
    return None


def _report_period_key(period: str) -> tuple[int, int] | None:
    match = re.fullmatch(r"(20\d{2})-(0[1-9]|1[0-2])", period)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _within_years_window(
    report_period: str | None,
    years: int | None,
    *,
    now: datetime | None = None,
) -> bool:
    if years is None or report_period is None:
        return True

    period_key = _report_period_key(report_period)
    if period_key is None:
        return True

    current = now or datetime.now(UTC)
    current_index = current.year * 12 + current.month
    report_index = period_key[0] * 12 + period_key[1]
    return report_index >= current_index - (years * 12)


def _title_from_text(text: str, fallback: str) -> str:
    match = HEADING_RE.search(text)
    if match:
        return _strip_markdown(match.group(2))
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return _strip_markdown(first_line) if first_line else fallback


def _sections(text: str) -> list[tuple[int, str, str]]:
    matches = list(HEADING_RE.finditer(text))
    sections: list[tuple[int, str, str]] = []
    for index, match in enumerate(matches):
        level = len(match.group(1))
        start = match.end()
        end = len(text)
        for next_match in matches[index + 1 :]:
            if len(next_match.group(1)) <= level:
                end = next_match.start()
                break
        sections.append((level, _strip_markdown(match.group(2)), text[start:end].strip()))
    return sections


def _looks_like_podling_section(heading: str, body: str) -> bool:
    normalized = heading.casefold().strip()
    if not normalized or normalized in GENERIC_HEADINGS:
        return False
    if "incubator pmc report" in normalized:
        return False
    if normalized.endswith("?"):
        return False
    if len(heading) > 80:
        return False
    body_fold = body.casefold()
    signals = [
        "incubat",
        "signed-off-by",
        "signed off by",
        "date of last release",
        "three most important",
        "community developed",
        "project developed",
    ]
    return any(signal in body_fold for signal in signals)


def _clean_podling_name(heading: str) -> str:
    name = re.sub(r"^apache\s+", "", heading.strip(), flags=re.IGNORECASE)
    name = re.sub(r"\s*\(incubat(?:ing|or|ed).*?\)\s*$", "", name, flags=re.IGNORECASE)
    return name.strip()


def _extract_issues(body: str) -> list[str]:
    lower = body.casefold()
    marker = "three most important"
    start = lower.find(marker)
    if start < 0:
        return []
    block = body[start : start + 1200]
    lines = []
    for raw_line in block.splitlines()[1:]:
        stripped = raw_line.strip()
        if not stripped:
            if lines:
                break
            continue
        if re.match(r"^(how|date of|when were|signed[- ]off|shepherd)", stripped, re.IGNORECASE):
            break
        item = re.sub(r"^[-*]\s+", "", stripped)
        item = re.sub(r"^\d+[.)]\s+", "", item)
        if item and not item.endswith(":"):
            lines.append(_strip_markdown(item))
    return lines[:5]


def _extract_signoffs(body: str) -> list[MentorSignoff]:
    signoffs: list[MentorSignoff] = []
    match = SIGNED_OFF_RE.search(body)
    source = body[match.end() :] if match else body
    for checkbox in CHECKBOX_RE.finditer(source):
        checked = checkbox.group(1).casefold() == "x"
        podling = checkbox.group(2).strip() if checkbox.group(2) else None
        mentor = _strip_markdown(checkbox.group(3))
        if mentor:
            signoffs.append(MentorSignoff(mentor=mentor, checked=checked, podling=podling))
    return signoffs


def _extract_first(pattern: re.Pattern[str], body: str) -> str | None:
    match = pattern.search(body)
    if not match:
        return None
    value = _strip_markdown(match.group(1))
    return value or None


def parse_report_text(
    text: str,
    report_id: str,
    path: str,
    *,
    source_url: str | None = None,
    cached_at: str | None = None,
    suffix: str = "",
) -> ParsedReport:
    normalized = normalize_text(text, suffix)
    title = _title_from_text(normalized, report_id)
    report_period = report_period_from_text(title, report_id, path)
    podling_reports: list[PodlingReport] = []

    for level, heading, body in _sections(normalized):
        if level == 1 or level > 4 or not _looks_like_podling_section(heading, body):
            continue
        podling_reports.append(
            PodlingReport(
                podling=_clean_podling_name(heading),
                heading=heading,
                body=body,
                issues=_extract_issues(body),
                signoffs=_extract_signoffs(body),
                incubating_since=_extract_first(INCUBATING_SINCE_RE, body),
                last_release=_extract_first(LAST_RELEASE_RE, body),
            )
        )

    return ParsedReport(
        report_id=report_id,
        title=title,
        path=path,
        report_period=report_period,
        generated_on=None,
        podling_reports=podling_reports,
        raw_text=normalized,
        source_url=source_url,
        cached_at=cached_at,
    )


def _metadata_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".json")


def _read_metadata(path: Path) -> dict[str, Any]:
    meta_path = _metadata_path(path)
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def is_report_file(path: Path) -> bool:
    if path.name.endswith(".json"):
        return False
    return path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES


def load_reports(reports_dir: str | Path = DEFAULT_REPORTS_DIR) -> list[ParsedReport]:
    base = Path(reports_dir).expanduser().resolve()
    if not base.exists():
        raise FileNotFoundError(f"Reports directory does not exist: {base}")
    if not base.is_dir():
        raise NotADirectoryError(f"Reports path is not a directory: {base}")

    reports: list[ParsedReport] = []
    for path in sorted(item for item in base.iterdir() if is_report_file(item)):
        metadata = _read_metadata(path)
        text = path.read_text(encoding="utf-8", errors="replace")
        reports.append(
            parse_report_text(
                text=text,
                report_id=metadata.get("report_id") or path.stem,
                path=str(path),
                source_url=metadata.get("source_url"),
                cached_at=metadata.get("cached_at"),
                suffix=path.suffix,
            )
        )
    return reports


def find_report(reports_dir: str | Path, report_id: str) -> ParsedReport:
    normalized = report_id.casefold()
    for report in load_reports(reports_dir):
        if report.report_id.casefold() == normalized or Path(report.path).stem.casefold() == normalized:
            return report
    raise KeyError(f"No Incubator report found for report_id: {report_id}")


def list_podlings(reports_dir: str | Path) -> list[str]:
    names = {
        podling.podling
        for report in load_reports(reports_dir)
        for podling in report.podling_reports
    }
    return sorted(names, key=str.casefold)


def report_summary(report: ParsedReport) -> dict[str, Any]:
    return {
        "report_id": report.report_id,
        "title": report.title,
        "path": report.path,
        "report_period": report.report_period,
        "source_url": report.source_url,
        "cached_at": report.cached_at,
        "visualization_hints": {
            "observed_mentor_signoff_count": MENTOR_SIGNOFF_INTERPRETATION,
        },
        "podling_count": len(report.podling_reports),
        "podlings": [
            {
                "podling": item.podling,
                "mentor_signoff_note": (
                    "Full mentor sign-off is not required; these are observed checked sign-offs only."
                ),
                "full_mentor_signoff_required": False,
                "mentor_signoff_status": "informational",
                "mentor_signoff_color": "neutral",
                "mentor_signoff_interpretation": MENTOR_SIGNOFF_INTERPRETATION,
                "observed_mentor_signoff_count": item.mentor_signoff_count,
                "signed_off_by": [signoff.mentor for signoff in item.signoffs if signoff.checked],
                "last_release": item.last_release,
                "incubating_since": item.incubating_since,
                "issue_count": len(item.issues),
            }
            for item in report.podling_reports
        ],
    }


def reports_overview(reports_dir: str | Path) -> dict[str, Any]:
    reports = load_reports(reports_dir)
    return {
        "reports_dir": str(Path(reports_dir).expanduser().resolve()),
        "report_count": len(reports),
        "podling_count": len({item.podling for report in reports for item in report.podling_reports}),
        "report_ids": [report.report_id for report in reports],
        "report_periods": sorted({report.report_period for report in reports if report.report_period}),
        "podlings": list_podlings(reports_dir),
    }


def podling_reports(reports_dir: str | Path, podling: str) -> list[dict[str, Any]]:
    normalized = podling.casefold()
    matches: list[dict[str, Any]] = []
    for report in load_reports(reports_dir):
        for item in report.podling_reports:
            if item.podling.casefold() == normalized:
                data = item.to_dict(include_body=True)
                data.update(
                    {
                        "report_id": report.report_id,
                        "report_period": report.report_period,
                        "title": report.title,
                        "path": report.path,
                    }
                )
                matches.append(data)
    return sorted(matches, key=lambda row: row.get("report_period") or "")


def search_reports(reports_dir: str | Path, query: str) -> list[dict[str, Any]]:
    normalized = query.casefold()
    rows: list[dict[str, Any]] = []
    for report in load_reports(reports_dir):
        report_match = normalized in report.title.casefold() or normalized in report.raw_text.casefold()
        podling_matches = [
            item.podling
            for item in report.podling_reports
            if normalized in item.podling.casefold() or normalized in item.body.casefold()
        ]
        if report_match or podling_matches:
            rows.append(
                {
                    "report_id": report.report_id,
                    "title": report.title,
                    "report_period": report.report_period,
                    "path": report.path,
                    "matching_podlings": sorted(set(podling_matches), key=str.casefold),
                }
            )
    return rows


def _download(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "apache-incubator-reports-mcp/0.1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read(), response.headers.get("content-type", "")


def _filename_from_url(url: str, content_type: str) -> str:
    parsed = urllib.parse.urlparse(url)
    name = Path(urllib.parse.unquote(parsed.path)).name
    if name and Path(name).suffix.lower() in SUPPORTED_SUFFIXES:
        return name
    suffix = ".html" if "html" in content_type.casefold() else ".txt"
    return f"{_slug(Path(parsed.path).stem or hashlib.sha256(url.encode('utf-8')).hexdigest()[:12])}{suffix}"


def cache_report_url(url: str, cache_dir: str | Path = DEFAULT_CACHE_DIR, report_id: str | None = None) -> dict[str, Any]:
    target_dir = Path(cache_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)
    payload, content_type = _download(url)
    filename = _filename_from_url(url, content_type)
    suffix = Path(filename).suffix or ".txt"
    resolved_id = report_id or _slug(Path(filename).stem)
    target = target_dir / f"{resolved_id}{suffix}"
    target.write_bytes(payload)
    metadata = {
        "report_id": resolved_id,
        "source_url": url,
        "cached_at": _now_iso(),
        "content_type": content_type,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }
    _metadata_path(target).write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    parsed = parse_report_text(
        payload.decode("utf-8", errors="replace"),
        report_id=resolved_id,
        path=str(target),
        source_url=url,
        cached_at=metadata["cached_at"],
        suffix=suffix,
    )
    return {
        "cached": True,
        "path": str(target),
        "metadata_path": str(_metadata_path(target)),
        "report": report_summary(parsed),
    }


def _whimsy_report_blocks(html_text: str) -> list[tuple[str, str]]:
    # Kept for tests and fallback parsing of the summary page. The summary page
    # may omit detailed podling sections, so production caching follows minutes
    # text links and extracts the full Incubator attachment.
    blocks: list[tuple[str, str]] = []
    pattern = re.compile(
        r'<h2\s+id="(?P<date>\d{4}-\d{2}-\d{2})".*?</h2>\s*'
        r'<pre\s+class="report">(?P<report>.*?)</pre>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in pattern.finditer(html_text):
        period = match.group("date")[:7]
        text = html.unescape(match.group("report")).strip() + "\n"
        if "# Incubator PMC report" in text:
            blocks.append((f"report{period.replace('-', '')}", text))
    return blocks


def _whimsy_minutes_urls(html_text: str, source_url: str) -> list[tuple[str, str]]:
    matches = re.findall(
        r'href=["\'](?P<url>[^"\']*board_minutes_(?P<year>\d{4})_(?P<month>\d{2})_\d{2}\.txt)["\']',
        html_text,
        flags=re.IGNORECASE,
    )
    seen: set[str] = set()
    urls: list[tuple[str, str]] = []
    for url, year, month in matches:
        report_id = f"report{year}{month}"
        if report_id in seen:
            continue
        seen.add(report_id)
        urls.append((report_id, urllib.parse.urljoin(source_url, url)))
    return urls


def _extract_incubator_attachment(minutes_text: str) -> str | None:
    start = minutes_text.find("# Incubator PMC report")
    if start < 0:
        return None
    end = minutes_text.find("\n-----------------------------------------", start)
    if end < 0:
        end = len(minutes_text)
    text = minutes_text[start:end].strip()
    return html.unescape(_strip_tags(text)) + "\n"


def cache_reports_from_whimsy(
    source_url: str = ASF_REPORTS_REPO_URL,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    years: int | None = 2,
    limit: int | None = None,
) -> dict[str, Any]:
    payload, content_type = _download(source_url)
    html_text = payload.decode("utf-8", errors="replace")
    minutes_urls = _whimsy_minutes_urls(html_text, source_url)
    target_dir = Path(cache_dir).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    cached: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    for report_id, minutes_url in minutes_urls:
        report_period = report_period_from_text(report_id, minutes_url)
        if not _within_years_window(report_period, years):
            continue
        if limit is not None and len(cached) >= limit:
            break
        try:
            minutes_payload, _minutes_content_type = _download(minutes_url)
            minutes_text = minutes_payload.decode("utf-8", errors="replace")
            text = _extract_incubator_attachment(minutes_text)
            if text is None:
                skipped.append({"report_id": report_id, "reason": "no_incubator_attachment"})
                continue
            parsed = parse_report_text(
                text,
                report_id=report_id,
                path=minutes_url,
                source_url=minutes_url,
                suffix=".txt",
            )
            if not parsed.podling_reports:
                skipped.append({"report_id": report_id, "reason": "no_podling_reports"})
                continue
            target = target_dir / f"{report_id}.txt"
            target.write_text(text, encoding="utf-8")
            metadata = {
                "report_id": report_id,
                "source_url": minutes_url,
                "cached_at": _now_iso(),
                "content_type": content_type,
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            }
            _metadata_path(target).write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            parsed.path = str(target)
            parsed.cached_at = metadata["cached_at"]
            cached.append(
                {
                    "cached": True,
                    "path": str(target),
                    "metadata_path": str(_metadata_path(target)),
                    "report": report_summary(parsed),
                }
            )
        except Exception as exc:
            errors.append({"report_id": report_id, "error": str(exc)})

    return {
        "source_url": source_url,
        "cache_dir": str(target_dir),
        "discovered_count": len(minutes_urls),
        "cached_count": len(cached),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "cached_reports": cached,
        "skipped": skipped,
        "errors": errors,
    }


def discover_report_urls(repo_url: str = ASF_REPORTS_REPO_URL) -> list[str]:
    payload, _content_type = _download(repo_url)
    listing = payload.decode("utf-8", errors="replace")
    urls: list[str] = []
    for href in re.findall(r'href=["\']([^"\']+)["\']', listing, flags=re.IGNORECASE):
        if href.startswith("?") or href.startswith("#") or href in {"../", "./"}:
            continue
        resolved = urllib.parse.urljoin(repo_url, href)
        path = urllib.parse.urlparse(resolved).path
        if Path(path).suffix.lower() in SUPPORTED_SUFFIXES:
            urls.append(resolved)
    return sorted(set(urls))


def cache_reports_from_repo(
    repo_url: str = ASF_REPORTS_REPO_URL,
    cache_dir: str | Path = DEFAULT_CACHE_DIR,
    years: int | None = 2,
    limit: int | None = None,
) -> dict[str, Any]:
    if "whimsy.apache.org/board/minutes/Incubator.html" in repo_url:
        return cache_reports_from_whimsy(repo_url, cache_dir=cache_dir, years=years, limit=limit)

    urls = discover_report_urls(repo_url)
    selected = [
        url
        for url in urls
        if _within_years_window(report_period_from_text(url), years)
    ]
    if limit is not None:
        selected = selected[:limit]
    cached: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for url in selected:
        try:
            cached.append(cache_report_url(url, cache_dir=cache_dir))
        except Exception as exc:
            errors.append({"url": url, "error": str(exc)})
    return {
        "repo_url": repo_url,
        "cache_dir": str(Path(cache_dir).expanduser().resolve()),
        "discovered_count": len(urls),
        "cached_count": len(cached),
        "error_count": len(errors),
        "cached_reports": cached,
        "errors": errors,
    }
