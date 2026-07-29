"""Suricata eve.json처럼 한 줄에 JSON 객체 하나씩 들어있는 로그용 파서."""

from __future__ import annotations

import json


class JsonLineParser:
    def parse(self, line: str) -> dict | None:
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None
