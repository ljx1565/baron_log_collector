"""
각 로그 소스의 고유한 심각도 표현을 syslog 표준(RFC 5424, 0~7)으로 변환한다.
0=Emergency 1=Alert 2=Critical 3=Error 4=Warning 5=Notice 6=Informational 7=Debug
※ 숫자가 낮을수록 심각도가 높다.
"""

EMERGENCY, ALERT, CRITICAL, ERROR, WARNING, NOTICE, INFO, DEBUG = range(8)


def http_status(fields: dict) -> int:
    try:
        status = int(fields.get("status", 200))
    except (TypeError, ValueError):
        return INFO
    if status >= 500:
        return CRITICAL
    if status in (401, 403):
        return ERROR
    if status >= 400:
        return WARNING
    return INFO


def suricata(fields: dict) -> int:
    # Suricata alert.severity: 1(높음)~3(낮음)
    try:
        prio = int(fields.get("alert", {}).get("severity", 3))
    except (AttributeError, TypeError, ValueError):
        return NOTICE
    return {1: ALERT, 2: WARNING, 3: NOTICE}.get(prio, NOTICE)


def syslog_priority(fields: dict) -> int:
    # journalctl -o json 의 PRIORITY 필드는 이미 0~7 RFC5424 값
    try:
        return int(fields.get("PRIORITY", INFO))
    except (TypeError, ValueError):
        return INFO


def samba(fields: dict) -> int:
    msg = (fields.get("message") or "").lower()
    if any(k in msg for k in ("denied", "failed", "error")):
        return ERROR
    return INFO


def mariadb(fields: dict) -> int:
    level = (fields.get("level") or "").lower()
    return {
        "error": ERROR,
        "warning": WARNING,
        "note": INFO,
    }.get(level, DEBUG)


def dns(fields: dict) -> int:
    qtype = (fields.get("query_type") or "").upper()
    if qtype in ("AXFR", "IXFR"):
        return WARNING  # 존 트랜스퍼 시도는 눈여겨봐야 함
    return DEBUG


def dnf(fields: dict) -> int:
    level = (fields.get("level") or "").upper()
    return {"ERROR": ERROR, "CRITICAL": CRITICAL, "WARNING": WARNING}.get(level, DEBUG)


def php_error(fields: dict) -> int:
    level = (fields.get("level") or "").lower()
    if "fatal" in level or "parse" in level:
        return ERROR
    if "warning" in level:
        return WARNING
    return NOTICE


def audit(fields: dict) -> int:
    # 웹 서버 계정이 직접 명령어를 실행한 경우 - 평소엔 안 걸리는 게 정상이라 웹쉘/RCE 의심 신호
    if fields.get("key") == "web_attack_check":
        return ERROR
    # 실패한 syscall(예: 권한 없는 파일 접근 시도)은 눈여겨봐야 함
    if fields.get("success") == "no":
        return WARNING
    # 우리가 직접 건 감시 키(webshell_watch/auth_watch)에 걸린 접근은 주목
    if fields.get("key") in ("webshell_watch", "auth_watch"):
        return WARNING
    return INFO  # 단순 execve 기록 등은 참고용


def failed_login(fields: dict) -> int:
    # btmp(lastb), faillock(tallylog 대체) - 실패한 로그인은 항상 주목할 필요
    return WARNING


def last_login(fields: dict) -> int:
    # wtmp(last) - 정상 로그인 세션 기록, 참고용
    return INFO


RULES = {
    "http_status": http_status,
    "suricata": suricata,
    "syslog_priority": syslog_priority,
    "samba": samba,
    "mariadb": mariadb,
    "dns": dns,
    "dnf": dnf,
    "php_error": php_error,
    "audit": audit,
    "failed_login": failed_login,
    "last_login": last_login,
}


def resolve(rule_name: str, fields: dict) -> int:
    fn = RULES.get(rule_name)
    if fn is None:
        return NOTICE
    try:
        return fn(fields)
    except Exception:
        return NOTICE
