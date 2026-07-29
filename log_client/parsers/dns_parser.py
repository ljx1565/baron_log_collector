"""BIND named query.log 파서.

일반적인 라인 형식:
28-Jul-2026 10:00:00.000 queries: info: client @0x7f... 1.2.3.4#53
  (example.com): query: example.com IN A + (5.6.7.8)
"""

from __future__ import annotations

import re

_LINE_RE = re.compile(
    r"^(?P<timestamp>\d{2}-\w{3}-\d{4} \d{2}:\d{2}:\d{2}\.\d+)\s+"
    r"queries:\s+\w+:\s+client\s+\S+\s+"
    r"(?P<src_ip>[\d.]+)#\d+\s+"
    r"\([^)]+\):\s+query:\s+"
    r"(?P<query_name>\S+)\s+IN\s+(?P<query_type>\S+)"
)


class DnsParser:
    def parse(self, line: str) -> dict | None:
        m = _LINE_RE.search(line.strip())
        if not m:
            return None
        return m.groupdict()
