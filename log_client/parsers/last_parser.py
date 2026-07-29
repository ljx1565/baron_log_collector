"""
`last -F` (wtmp) / `lastb -F` (btmp) 명령 출력을 파싱한다.

wtmp/btmp는 바이너리라 tail이 불가능하므로, 표준 명령어 출력을 주기적으로
받아와 이전 실행과 비교(diff)하는 방식으로 처리한다. 새 라이브러리 없이
subprocess + 정규식만 사용한다.

세션 하나의 정확한 시작 시각까지 완벽하게 파싱하기보다는(상대적 날짜 표기,
연도 생략 등으로 파싱이 깨지기 쉬움), 같은 줄이 다시 나타나지 않으면
"새 세션"으로 간주하는 정도로 단순화했다. event_time은 감지된 시각(now)을 쓴다.
"""

import re

_LINE_RE = re.compile(r"^(?P<user>\S+)\s+(?P<tty>\S+)\s+(?P<src_ip>\S+)\s+(?P<detail>.+)$")
_IGNORE_PREFIXES = ("wtmp begins", "btmp begins", "reboot")


def parse_last_output(output: str):
    """반환값: (식별키, 필드딕셔너리) 튜플 리스트. 식별키는 원본 줄 전체."""
    entries = []
    for line in output.splitlines():
        line = line.rstrip()
        if not line or line.startswith(_IGNORE_PREFIXES):
            continue
        m = _LINE_RE.match(line)
        if not m:
            continue
        entries.append((line, m.groupdict()))
    return entries
