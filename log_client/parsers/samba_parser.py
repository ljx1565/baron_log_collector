"""
smbd 로그 파서.

Samba 로그는 로그 레벨/설정에 따라 형식이 꽤 유동적이라 완벽한 정규화보다는,
타임스탬프 + IP + 공유명/사용자명을 최대한 뽑아내고 나머지는 message로 남기는
느슨한(best-effort) 방식으로 구현했다. 실제 배포 환경의 log level에 맞춰
정규식은 조정이 필요할 수 있다.
"""

from __future__ import annotations

import re

# 예: [2026/07/28 10:00:00.123456,  1] ../../source3/smbd/service.c:225(fn)
_TS_RE = re.compile(r"^\[(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2})(?:\.\d+)?,\s*\d+\]")
_IP_RE = re.compile(r"(?P<ip>\d{1,3}(?:\.\d{1,3}){3})")
_SHARE_RE = re.compile(r"connect to service (?P<share>\S+)")
_USER_RE = re.compile(r"^\s*(?P<user>[\w.\-]+)\s*\(")


class SambaParser:
    def parse(self, line: str) -> dict | None:
        ts_match = _TS_RE.match(line)
        if not ts_match:
            return None  # 타임스탬프로 시작하지 않는 줄(스택트레이스 등)은 건너뜀

        fields = {"timestamp": ts_match.group("ts"), "message": line.strip()}

        ip_match = _IP_RE.search(line)
        if ip_match:
            fields["src_ip"] = ip_match.group("ip")

        share_match = _SHARE_RE.search(line)
        if share_match:
            fields["share"] = share_match.group("share")

        user_match = _USER_RE.search(line[ts_match.end():])
        if user_match:
            fields["smb_user"] = user_match.group("user")

        return fields
