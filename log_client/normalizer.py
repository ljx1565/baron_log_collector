"""
소스별 파서가 만들어낸 '제각각 생긴' 필드 딕셔너리를,
events 테이블에 그대로 들어갈 수 있는 공통 스키마로 변환한다.

파싱(parser)은 소스마다 다르게 두고, 정규화(normalizer)에서만
공통 형식을 맞춘다는 게 이 파이프라인의 핵심 아이디어.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import severity as severity_mod

# journal(journalctl -o json)에서 분류되어 나오는 카테고리들.
# 모두 __REALTIME_TIMESTAMP를 쓰고, severity도 전부 PRIORITY 필드를 그대로 쓴다.
JOURNAL_CATEGORIES = {"cron", "auth", "rsyslog", "messages", "firewalld", "chrony"}

# 폴링(diff) 기반 소스 - wtmp/btmp/faillock. 바이너리 로그라 tail 불가능.
POLLING_CATEGORIES = {"wtmp", "btmp", "tallylog"}

# 소스별 event_time 파싱 시도 순서 (형식이 여러 개일 수 있어 순서대로 시도)
_TIME_FORMATS = {
    "web_access": ["%d/%b/%Y:%H:%M:%S %z"],
    "samba": ["%Y/%m/%d %H:%M:%S"],
    "mariadb": ["%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ"],
    "dns": ["%d-%b-%Y %H:%M:%S.%f"],
    "dnf": ["%Y-%m-%dT%H:%M:%S%z"],
    "tallylog": ["%Y-%m-%d %H:%M:%S"],
}

_PHP_TS_RE = re.compile(r"^(\d{2}-\w{3}-\d{4} \d{2}:\d{2}:\d{2})\s+(\S+)$")


def _parse_php_timestamp(raw: str) -> datetime | None:
    """예: '28-Jul-2026 20:10:15 Asia/Seoul' -> aware datetime.
    IANA 존 이름까지 오므로 stdlib zoneinfo(3.9+)로 정확히 변환한다."""
    m = _PHP_TS_RE.match(raw)
    if not m:
        return None
    date_part, zone_name = m.groups()
    try:
        dt = datetime.strptime(date_part, "%d-%b-%Y %H:%M:%S")
        return dt.replace(tzinfo=ZoneInfo(zone_name))
    except Exception:
        return None


def _parse_event_time(source_name: str, raw_fields: dict, time_field: str | None) -> datetime:
    # journal 계열은 __REALTIME_TIMESTAMP(마이크로초 epoch)를 그대로 사용
    if source_name in JOURNAL_CATEGORIES:
        try:
            micros = int(raw_fields["__REALTIME_TIMESTAMP"])
            return datetime.fromtimestamp(micros / 1_000_000, tz=timezone.utc)
        except (KeyError, ValueError):
            return datetime.now(timezone.utc)

    # suricata(JSON)는 ISO8601 형식
    if source_name == "suricata_hids":
        raw = raw_fields.get("timestamp")
        if raw:
            try:
                return datetime.fromisoformat(raw)
            except ValueError:
                pass
        return datetime.now(timezone.utc)

    # audit(auditd)는 msg=audit(epoch:id) 의 epoch(초 단위, 소수점 포함)를 그대로 사용
    if source_name == "audit":
        raw = raw_fields.get("epoch")
        if raw:
            try:
                return datetime.fromtimestamp(float(raw), tz=timezone.utc)
            except (TypeError, ValueError):
                pass
        return datetime.now(timezone.utc)

    # php_error는 대괄호 안에 IANA 존 이름까지 있어서 별도 파서 사용
    if source_name == "php_error":
        raw = raw_fields.get("timestamp")
        if raw:
            parsed = _parse_php_timestamp(raw)
            if parsed:
                return parsed
        return datetime.now(timezone.utc)

    # wtmp/btmp(last/lastb)는 상대적 날짜 표기 등으로 파싱이 깨지기 쉬워 감지 시각을 사용
    if source_name in ("wtmp", "btmp"):
        return datetime.now(timezone.utc)

    raw = raw_fields.get(time_field) if time_field else None
    if raw:
        for fmt in _TIME_FORMATS.get(source_name, []):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue

    return datetime.now(timezone.utc)


def _to_mysql_datetime(dt: datetime) -> str:
    """MariaDB DATETIME(3) 컬럼이 받아들일 수 있는, 타임존 표시가 없는 문자열로 변환.

    dt가 타임존 정보를 갖고 있으면(UTC 등) 먼저 UTC로 맞춘 뒤 tzinfo를 제거한다.
    isoformat()을 그대로 쓰면 '+00:00' 같은 타임존 표시가 붙어 MariaDB가 거부한다.
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # 마이크로초 6자리 -> 밀리초 3자리


def _build_summary(source_name: str, raw_fields: dict) -> str:
    if source_name == "suricata_hids":
        return raw_fields.get("alert", {}).get("signature", "suricata alert")
    if source_name in JOURNAL_CATEGORIES:
        return (raw_fields.get("MESSAGE") or "")[:255]
    if source_name == "web_access":
        method = raw_fields.get("method")
        uri = raw_fields.get("uri")
        if method and uri:
            summary = f'{method} {uri} -> {raw_fields.get("status", "")}'
            bytes_val = raw_fields.get("bytes")
            if bytes_val and bytes_val != "-":
                summary += f' ({bytes_val}B)'
            referer = raw_fields.get("referer")
            if referer and referer != "-":
                summary += f' | ref: {referer}'
            return summary
        return f'{raw_fields.get("request", "")} -> {raw_fields.get("status", "")}'
    if source_name == "samba":
        return raw_fields.get("message", "")[:255]
    if source_name == "mariadb":
        return raw_fields.get("message", "")[:255]
    if source_name == "dns":
        return f'query {raw_fields.get("query_name", "")} {raw_fields.get("query_type", "")}'
    if source_name == "dnf":
        return raw_fields.get("message", "")[:255]
    if source_name == "php_error":
        return f'{raw_fields.get("level", "PHP")}: {raw_fields.get("detail", "")}'[:255]
    if source_name == "audit":
        parts = f'{raw_fields.get("type", "")} key={raw_fields.get("key", "-")}'
        comm = raw_fields.get("comm")
        exe = raw_fields.get("exe")
        user = raw_fields.get("UID") or raw_fields.get("AUID")
        if user:
            parts += f' user={user}'
        if comm:
            parts += f' comm={comm}'
        if exe:
            parts += f' exe={exe}'
        parts += f' success={raw_fields.get("success", "-")}'
        return parts
    if source_name == "tallylog":
        return f'로그인 실패: user={raw_fields.get("user", "")} source={raw_fields.get("source", "")}'
    if source_name in ("wtmp", "btmp"):
        return f'{raw_fields.get("user", "")}@{raw_fields.get("src_ip", "")} {raw_fields.get("detail", "")}'[:255]
    return ""


def normalize(source_name: str, raw_fields: dict, config_entry: dict) -> dict:
    """
    source_name   : config.yaml 의 sources[].name, 혹은 journal 분류 결과
                     (cron / auth / rsyslog / messages)
    raw_fields    : 각 파서(parse)가 반환한 원본 필드 딕셔너리
    config_entry  : config.yaml 에서 이 소스에 해당하는 설정(dict). journal 계열은 {}
    """
    if source_name in JOURNAL_CATEGORIES:
        severity_rule = "syslog_priority"  # journal은 PRIORITY 필드를 그대로 씀
        category = source_name             # cron/auth/rsyslog/messages 그대로 category로
    else:
        severity_rule = config_entry.get("severity_rule")
        category = config_entry.get("category")

    event_time = _parse_event_time(source_name, raw_fields, config_entry.get("event_time_field"))

    src_ip_field = config_entry.get("src_ip_field")
    dst_ip_field = config_entry.get("dst_ip_field")
    src_ip = raw_fields.get(src_ip_field) if src_ip_field else raw_fields.get("src_ip")
    dst_ip = raw_fields.get(dst_ip_field) if dst_ip_field else None

    return {
        "source_name": source_name,
        "event_time": _to_mysql_datetime(event_time),
        "severity": severity_mod.resolve(severity_rule, raw_fields),
        "category": category,
        "src_ip": src_ip,
        "dst_ip": dst_ip,
        "summary": _build_summary(source_name, raw_fields)[:255],
        "details": raw_fields,
    }
