# Apache Incubator Reports MCP

A small stdio MCP server for reading ASF Incubator reports.

By default, it uses the public Whimsy page for approved ASF Board minutes extracts:

```text
https://whimsy.apache.org/board/minutes/Incubator.html
```

Reports are cached locally before being parsed. The default cache is `.cache/incubator-reports`.

## Install

```bash
python3 -m pip install .
```

For development:

```bash
python3 -m pip install -e .[dev]
```

## Run

```bash
incubator-reports-mcp --cache-dir /path/to/cache
```

For local development without installing:

```bash
python3 server.py --cache-dir /path/to/cache
```

The server uses `stdio`, so it is intended to be launched by an MCP client.

## Example MCP Client Config

```json
{
  "mcpServers": {
    "incubator-reports": {
      "command": "incubator-reports-mcp",
      "args": [
        "--cache-dir",
        "/path/to/cache"
      ]
    }
  }
}
```

## Tools

- `cache_all_reports`: downloads approved Incubator reports into the local cache, defaulting to the last 2 years unless `years` is set to `null`
- `cache_report`: downloads one report URL into the local cache
- `incubator_reports_overview`: summarizes cached report documents
- `list_reports`: lists cached report documents
- `list_podlings`: lists podlings found in cached reports
- `search_reports`: searches report text and podling entries
- `get_report_summary`: returns parsed summary details for a report
- `get_report_markdown`: returns raw report text
- `get_podling_reports`: returns all cached entries for one podling

## Test

```bash
python3 -m unittest discover -s tests -v
```
