"""
`faillock` (인자 없이 실행하면 모든 계정) 명령 출력을 파싱한다.

Rocky 8/9는 기본적으로 pam_tally2 대신 pam_faillock을 쓰기 때문에
/var/log/tallylog 파일이 아예 없는 경우가 많다. 대신 faillock 명령의
텍스트 출력을 파싱해서 "계정 잠김/실패 시도" 이벤트를 만든다.

출력 형식 예:
    root:
    When                Type   Source                                          Valid
    2026-07-28 20:10:15 RHOST  192.168.1.50                                    V
"""

import re

_ATTEMPT_RE = re.compile(
    r"^(?P<when>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+(?P<type>\S+)\s+(?P<source>\S+)\s+(?P<valid>\S+)$"
)


def parse_faillock_output(output: str):
    """반환값: (식별키, 필드딕셔너리) 튜플 리스트.
    식별키는 (계정명, 시도시각, 출처) 조합 - 같은 시도가 다시 안 보이면 새 이벤트로 취급."""
    entries = []
    current_user = None
    for line in output.splitlines():
        line = line.rstrip()
        if not line:
            continue
        # 계정명 헤더 줄 (예: "root:") - 들여쓰기 없이 콜론으로 끝남
        if not line.startswith(" ") and line.endswith(":"):
            current_user = line[:-1].strip()
            continue
        m = _ATTEMPT_RE.match(line.strip())
        if not m or current_user is None:
            continue
        fields = m.groupdict()
        fields["user"] = current_user
        key = (current_user, fields["when"], fields["source"])
        entries.append((key, fields))
    return entries
