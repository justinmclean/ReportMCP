from __future__ import annotations

from typing import Any

REPORTS_DIR_PROPERTY = {
    "type": "string",
    "description": "Optional local path to cached ASF Incubator report files",
}
CACHE_DIR_PROPERTY = {
    "type": "string",
    "description": "Optional local cache directory for ASF Incubator report files",
}
REPO_URL_PROPERTY = {
    "type": "string",
    "description": "Optional ASF Incubator reports source URL",
}
REPORT_ID_PROPERTY = {"type": "string", "description": "Incubator report id, usually the cached file stem"}
PODLING_PROPERTY = {"type": "string", "description": "Podling name"}
QUERY_PROPERTY = {"type": "string", "description": "Case-insensitive report or podling search text"}
URL_PROPERTY = {"type": "string", "description": "Incubator report URL to cache"}
LIMIT_PROPERTY = {"type": "integer", "description": "Optional maximum number of results"}
YEARS_PROPERTY = {
    "type": ["integer", "null"],
    "description": "Optional number of years of report history to cache; null means full history",
}
BOOLEAN_PROPERTY = {"type": "boolean", "description": "Optional boolean flag"}


def input_schema(
    properties: dict[str, Any], *, required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


def tool_definition(
    *,
    description: str,
    handler: Any,
    properties: dict[str, Any],
    required: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "description": description,
        "inputSchema": input_schema(properties, required=required),
        "handler": handler,
    }


def base_properties() -> dict[str, Any]:
    return {
        "reports_dir": REPORTS_DIR_PROPERTY,
        "cache_dir": CACHE_DIR_PROPERTY,
        "refresh": BOOLEAN_PROPERTY,
    }


def repo_cache_properties() -> dict[str, Any]:
    return {
        "repo_url": REPO_URL_PROPERTY,
        "cache_dir": CACHE_DIR_PROPERTY,
        "years": YEARS_PROPERTY,
        "limit": LIMIT_PROPERTY,
    }


def url_cache_properties() -> dict[str, Any]:
    return {
        "url": URL_PROPERTY,
        "cache_dir": CACHE_DIR_PROPERTY,
        "report_id": REPORT_ID_PROPERTY,
    }


def report_properties() -> dict[str, Any]:
    return {
        **base_properties(),
        "report_id": REPORT_ID_PROPERTY,
    }


def podling_properties() -> dict[str, Any]:
    return {
        **base_properties(),
        "podling": PODLING_PROPERTY,
    }


def search_properties() -> dict[str, Any]:
    return {
        **base_properties(),
        "query": QUERY_PROPERTY,
        "limit": LIMIT_PROPERTY,
    }
