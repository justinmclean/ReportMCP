# Architecture

The server follows the same small-module shape as `HealthMCP`.

## Runtime Flow

1. `server.py` places `src/` on `sys.path` for local checkout execution.
2. `apache_incubator_reports_mcp.protocol` handles stdio JSON-RPC and MCP tool calls.
3. `apache_incubator_reports_mcp.tools` validates tool arguments and resolves cache/source defaults.
4. `apache_incubator_reports_mcp.parser` downloads ASF report files, stores cache metadata, loads cached reports, and extracts podling report sections.

## Source Data

The default upstream source is the public Whimsy board-minutes extract for the Incubator:

```text
https://whimsy.apache.org/board/minutes/Incubator.html
```

`cache_all_reports` reads the approved report blocks from that page and writes them into the configured cache directory. Each cached report has a sibling JSON metadata file with the source URL, cache time, content type, and SHA-256 digest.

## Parsing Model

Reports are parsed as heading-structured text. The parser accepts Markdown-like text, plain text, and simple HTML. It identifies podling sections by looking for report-specific signals such as incubation dates, release-date fields, unfinished-issue prompts, and mentor sign-off blocks.

Parsed podling entries include:

- podling name
- unfinished issues
- mentor sign-offs
- incubation start text
- last release text
- raw section body when requested
