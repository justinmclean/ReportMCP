from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from textwrap import dedent
from typing import Iterator

SAMPLE_REPORT = dedent(
    """\
    # Incubator Report April 2026

    ## Table of Contents
    [Alpha](#alpha)
    [Bravo](#bravo)

    ## Alpha

    Alpha has been incubating since 2025-01-01.

    Three most important unfinished issues to address before graduating:

    1. Grow the committer base.
    2. Make another Apache release.

    How has the community developed since the last report?

    More contributors joined.

    Date of last release: 2026-03-15

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

    ## Shepherd Assignments

    Not a podling section.
    """
)


@contextmanager
def report_dir() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as temp_dir:
        base = Path(temp_dir)
        (base / "2026-04.txt").write_text(SAMPLE_REPORT, encoding="utf-8")
        yield base
