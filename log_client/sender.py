"""로그가 생성되는 즉시 중앙 API(/api/events)로 전송한다.

DB 연결 정보는 collector가 직접 알 필요 없이, API 서버 쪽에서만 갖도록 해서
각 서버가 뚫려도 DB 자격증명이 노출되지 않게 한다.
"""

from __future__ import annotations

import logging
import socket
import time

import requests

logger = logging.getLogger("sender")


def _detect_local_ip() -> str | None:
    """이 서버의 주 IP를 감지한다 (실제 패킷은 안 보내고 라우팅 테이블만 조회).
    새 라이브러리 없이 표준 socket 모듈만 사용. 1차 방법이 안 되면 2차로 폴백."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        finally:
            s.close()
    except OSError:
        pass

    # 폴백: 인터넷 라우팅 자체가 안 되는 격리망일 때, hostname으로 조회
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass

    logger.warning("이 서버의 IP를 감지하지 못했습니다. hosts.ip_address는 비어 있게 됩니다.")
    return None


class EventSender:
    def __init__(self, api_url: str, api_token: str, hostname: str, timeout=3, max_retries=3):
        self.api_url = api_url
        self.hostname = hostname
        self.host_ip = _detect_local_ip()
        logger.info("이 서버의 감지된 IP: %s", self.host_ip)
        self.timeout = timeout
        self.max_retries = max_retries
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        })

    def send(self, event: dict) -> bool:
        payload = {**event, "hostname": self.hostname, "host_ip": self.host_ip}
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = self._session.post(self.api_url, json=payload, timeout=self.timeout)
                if resp.status_code == 200:
                    return True
                logger.warning("API 응답 오류(%s): %s", resp.status_code, resp.text[:200])
            except requests.RequestException as exc:
                logger.warning("전송 실패(%d/%d): %s", attempt, self.max_retries, exc)
            time.sleep(min(2 ** attempt, 10))  # 지수 백오프
        logger.error("이벤트 전송 최종 실패, 유실됨: %s", payload.get("summary"))
        return False
