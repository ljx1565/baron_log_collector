"""auditd의 audit.log 파서.

일반적인 라인 형식:
type=SYSCALL msg=audit(1690000000.123:456): arch=c000003e syscall=59
  success=yes exit=0 ... comm="bash" exe="/usr/bin/bash" key="exec_watch"

type=/msg=audit(epoch:id) 헤더를 먼저 뜯어내고, 나머지는 key=value 쌍을
전부 딕셔너리로 풀어낸다 (auditd 필드는 종류가 많고 계속 늘어날 수 있어서
화이트리스트 없이 전부 담아 details로 보낸다).
"""

from __future__ import annotations

import re

_HEADER_RE = re.compile(r"^type=(?P<type>\S+)\s+msg=audit\((?P<epoch>\d+\.\d+):(?P<audit_id>\d+)\):\s*(?P<rest>.*)$")
_KV_RE = re.compile(r'(\w+)=("[^"]*"|\S+)')


class AuditParser:
    def parse(self, line: str) -> dict | None:
        m = _HEADER_RE.match(line.strip())
        if not m:
            return None
        fields = {"type": m.group("type"), "epoch": m.group("epoch"), "audit_id": m.group("audit_id")}
        for key, value in _KV_RE.findall(m.group("rest")):
            if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
                value = value[1:-1]
            fields[key] = value
        return fields
