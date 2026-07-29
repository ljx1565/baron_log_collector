"""
수집기(collector) 진입점.

config.yaml에 정의된 모든 로그 소스에 대해 스레드를 하나씩 띄워서,
각 스레드가 '읽기 -> 파싱 -> 정규화 -> 전송'을 반복한다.
서비스 하나가 죽어도 다른 소스 수집에 영향 없도록 스레드 단위로 격리한다.
"""

from __future__ import annotations

import logging
import subprocess
import threading
import time

import yaml

from normalizer import normalize
from sender import EventSender
from tailer import RotationSafeTailer
from parsers.conf_format import ConfFormatParser
from parsers.json_parser import JsonLineParser
from parsers.journal_parser import JournalParser
from parsers.samba_parser import SambaParser
from parsers.mariadb_parser import MariaDBParser
from parsers.dns_parser import DnsParser
from parsers.dnf_parser import DnfParser
from parsers.php_error_parser import PhpErrorParser
from parsers.audit_parser import AuditParser
from parsers.last_parser import parse_last_output
from parsers.faillock_parser import parse_faillock_output

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")


def _build_parser(source_cfg: dict):
    stype = source_cfg["type"]
    if stype == "json":
        return JsonLineParser()
    if stype == "conf_format":
        return ConfFormatParser(
            conf_path=source_cfg["conf_path"],
            style=source_cfg["conf_style"],
            format_name=source_cfg.get("format_name", "combined"),
        )
    if stype == "samba":
        return SambaParser()
    if stype == "mariadb":
        return MariaDBParser()
    if stype == "dns":
        return DnsParser()
    if stype == "dnf":
        return DnfParser()
    if stype == "php_error":
        return PhpErrorParser()
    if stype == "audit":
        return AuditParser()
    raise ValueError(f"알 수 없는 소스 타입: {stype}")


def run_file_source(source_cfg: dict, sender: EventSender):
    """일반 파일(tail) 기반 소스: json / conf_format / samba / mariadb / dns 공통 처리."""
    name = source_cfg["name"]
    parser = _build_parser(source_cfg)
    tailer = RotationSafeTailer(source_cfg["log_path"])

    logger.info("[%s] 수집 시작: %s", name, source_cfg["log_path"])
    parse_fail_count = 0
    for line in tailer.follow():
        raw_fields = parser.parse(line)
        if raw_fields is None:
            parse_fail_count += 1
            # 조용히 무시하지 않고, 처음 몇 건은 원본 라인을 보여준다 (형식이 안 맞는지 바로 확인 가능하도록)
            if parse_fail_count <= 5:
                logger.warning("[%s] 파싱 실패(%d번째), 형식을 확인하세요: %s",
                               name, parse_fail_count, line[:200])
            continue
        event = normalize(name, raw_fields, source_cfg)
        sender.send(event)


def run_polling_source(source_cfg: dict, sender: EventSender):
    """명령어를 주기적으로 실행해서 이전 결과와 비교(diff)하는 방식.
    wtmp/btmp/faillock처럼 바이너리라 tail이 불가능한 소스에 사용한다.
    새 라이브러리 없이 subprocess + 표준 명령(last/lastb/faillock)만 사용."""
    name = source_cfg["name"]
    command = source_cfg["command"]
    interval = source_cfg.get("interval_sec", 30)
    parser_type = source_cfg["parser"]  # "last_line" | "faillock"

    logger.info("[%s] 폴링 수집 시작 (%d초 간격): %s", name, interval, " ".join(command))
    seen_keys = set()
    first_run = True

    while True:
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=15)
            output = result.stdout
        except Exception as exc:
            logger.warning("[%s] 명령 실행 실패: %s", name, exc)
            time.sleep(interval)
            continue

        if parser_type == "last_line":
            entries = parse_last_output(output)
        elif parser_type == "faillock":
            entries = parse_faillock_output(output)
        else:
            entries = []

        current_keys = {key for key, _ in entries}
        if first_run:
            # 최초 실행에서는 기존 내역을 전부 새 이벤트로 보내지 않고 기준선으로만 저장
            seen_keys = current_keys
            first_run = False
        else:
            for key, fields in entries:
                if key in seen_keys:
                    continue
                event = normalize(name, fields, source_cfg)
                sender.send(event)
            seen_keys = current_keys

        time.sleep(interval)


def run_journal_source(sender: EventSender):
    """systemd journal 기반 소스: cron/auth/rsyslog/messages 로 분류해서 처리."""
    jp = JournalParser()
    logger.info("[journal] 수집 시작 (cron/auth/rsyslog/messages로 분류)")
    for raw_fields in jp.follow():
        category = jp.classify(raw_fields)  # 'cron' | 'auth' | 'rsyslog' | 'messages'
        event = normalize(category, raw_fields, {})
        sender.send(event)


def main():
    with open("config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    sender = EventSender(
        api_url=config["api_url"],
        api_token=config["api_token"],
        hostname=config["hostname"],
    )

    sources = {s["name"]: s for s in config["sources"]}
    threads = []

    for name, source_cfg in sources.items():
        if source_cfg["type"] == "journal":
            t = threading.Thread(target=run_journal_source, args=(sender,), daemon=True)
        elif source_cfg["type"] == "polling":
            t = threading.Thread(target=run_polling_source, args=(source_cfg, sender), daemon=True)
        else:
            t = threading.Thread(target=run_file_source, args=(source_cfg, sender), daemon=True)
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()


if __name__ == "__main__":
    main()
