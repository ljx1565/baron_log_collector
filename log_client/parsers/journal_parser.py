"""
syslog 대신 systemd journal을 사용한다 (`journalctl -f -o json`).
journal은 이미 구조화된 JSON을 주기 때문에 별도 정규식 파싱이 필요 없고,
PRIORITY 필드가 RFC 5424 0~7 값 그대로라 severity 매핑도 공짜로 얻는다.

하나의 journal 스트림 안에 섞여 있는 이벤트를, 전통적으로 별도 파일로
나뉘던 카테고리(cron/secure(auth)+pam/messages/rsyslog)에 맞춰 재분류한다.
"""

import json
import subprocess

_CRON_IDENTIFIERS = {"CRON", "cron", "anacron"}
_RSYSLOG_IDENTIFIERS = {"rsyslogd"}
_FIREWALLD_IDENTIFIERS = {"firewalld"}
_CHRONY_IDENTIFIERS = {"chronyd"}
# LOG_AUTH=4, LOG_AUTHPRIV=10 (secure/auth 로그가 쓰는 syslog facility)
_AUTH_FACILITIES = {"4", "10"}
# facility 필드가 없는 경우를 대비한 identifier 기반 보조 판별 (pam은 여기 다 포함시켜 secure/auth로 합침)
_AUTH_IDENTIFIERS = {
    "sshd", "sudo", "su", "login", "systemd-logind",
    "polkit", "unix_chkpwd", "gdm-password", "sssd_pam",
}


class JournalParser:
    """journalctl -f -o json 프로세스를 실행하고 줄 단위로 JSON을 넘겨준다."""

    def __init__(self):
        self._proc = subprocess.Popen(
            ["journalctl", "-f", "-o", "json", "--no-pager"],
            stdout=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

    def follow(self):
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

    @staticmethod
    def classify(fields: dict) -> str:
        """journal 엔트리를 cron / auth / rsyslog / firewalld / chrony / messages 중 하나로 분류."""
        identifier = fields.get("SYSLOG_IDENTIFIER", "")
        message = fields.get("MESSAGE", "")
        if not isinstance(message, str):
            message = ""  # 바이너리(비-UTF8) 메시지는 journal이 정수 배열로 주는데, 여기선 무시

        if identifier in _CRON_IDENTIFIERS:
            return "cron"
        if identifier in _RSYSLOG_IDENTIFIERS:
            return "rsyslog"
        if identifier in _FIREWALLD_IDENTIFIERS:
            return "firewalld"  # 규칙 변경/reload 등
        if identifier in _CHRONY_IDENTIFIERS:
            return "chrony"
        # LogDenied=all 설정 시 커널이 남기는 차단 패킷 로그 (netfilter LOG 포맷)
        if "IN=" in message and "OUT=" in message and "PROTO=" in message:
            return "firewalld"

        facility = str(fields.get("SYSLOG_FACILITY", ""))
        if facility in _AUTH_FACILITIES or identifier in _AUTH_IDENTIFIERS or "pam" in identifier.lower():
            return "auth"  # secure/auth + pam 통합

        return "messages"  # 그 외 일반 시스템 메시지 (/var/log/messages 격)
