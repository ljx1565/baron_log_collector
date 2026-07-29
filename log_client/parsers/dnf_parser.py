"""dnf.log 파서.

일반적인 라인 형식: 2026-07-28T20:10:15+0900 INFO --- logging initialized ---
"""

from __future__ import annotations

import re

_LINE_RE = re.compile(
    r"^(?P<timestamp>\S+)\s+(?P<level>DEBUG|DDEBUG|SUBDEBUG|INFO|WARNING|ERROR|CRITICAL)\s+(?P<message>.*)$"
)


class DnfParser:
    def parse(self, line: str) -> dict | None:
        m = _LINE_RE.match(line.strip())
        if not m:
            return None
        return m.groupdict()
