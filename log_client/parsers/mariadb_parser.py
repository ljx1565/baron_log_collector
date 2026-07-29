"""MariaDB 에러 로그(mariadb.log) 파서.

일반적인 라인 형식: 2026-07-28 10:00:00 0 [Note] ...
또는:               2026-07-28T10:00:00.000000Z 0 [Warning] ...
"""

from __future__ import annotations

import re

_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?)\s+"
    r"(?P<thread_id>\d+)\s+"
    r"\[(?P<level>Note|Warning|Error)\]\s+"
    r"(?P<message>.*)$"
)


class MariaDBParser:
    def parse(self, line: str) -> dict | None:
        m = _LINE_RE.match(line.strip())
        if not m:
            return None
        return m.groupdict()
