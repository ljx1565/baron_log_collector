"""PHP 에러 로그 파서.

일반적인 라인 형식:
[28-Jul-2026 20:10:15 Asia/Seoul] PHP Warning:  message in /var/www/html/x.php on line 12
"""

from __future__ import annotations

import re

_LINE_RE = re.compile(r"^\[(?P<timestamp>[^\]]+)\]\s+(?P<message>.*)$")
_LEVEL_RE = re.compile(r"^(?P<level>PHP (?:Fatal error|Parse error|Warning|Notice|Deprecated)):\s*(?P<detail>.*)$")


class PhpErrorParser:
    def parse(self, line: str) -> dict | None:
        m = _LINE_RE.match(line.strip())
        if not m:
            return None
        fields = m.groupdict()
        level_match = _LEVEL_RE.match(fields["message"])
        if level_match:
            fields.update(level_match.groupdict())
        else:
            fields["level"] = "PHP"
            fields["detail"] = fields["message"]
        return fields
