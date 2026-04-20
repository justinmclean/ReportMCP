# Repository Guidelines

This project intentionally mirrors the lightweight Python layout used by `HealthMCP`.

## Commands

- Run tests with `python3 -m unittest discover -s tests -v`.
- Run the local stdio server with `python3 server.py`.
- Install for development with `python3 -m pip install -e .[dev]`.

## Style

- Keep modules small and stdlib-first.
- Preserve the `protocol.py`, `tools.py`, `schemas.py`, `parser.py` separation.
- Avoid adding network calls to unit tests; mock ASF repository fetches.
- Cached reports belong under `.cache/incubator-reports` unless a caller configures another cache directory.
