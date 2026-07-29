"""
Apache/Nginx의 로그 포맷 설정을 conf 파일에서 읽어,
그 형식지정자에 맞는 정규식을 '동적으로' 만들어내는 파서.

conf 파일의 LogFormat 문자열이 바뀌어도, 코드를 고치지 않고
새 포맷에 맞는 필드를 그대로 뽑아낼 수 있는 게 핵심이다.
"""

from __future__ import annotations

import re

# Apache 형식지정자 -> (필드명, 캡처 정규식)
_APACHE_DIRECTIVES = {
    "%h": ("remote_addr", r"\S+"),
    "%l": ("ident", r"\S+"),
    "%u": ("user", r"\S+"),
    "%t": ("time_local", r"\[[^\]]+\]"),
    "%r": ("request", r'[^"]*'),   # 앞뒤 큰따옴표는 포맷 문자열의 리터럴 토큰이 이미 처리함
    "%>s": ("status", r"\d+"),
    "%s": ("status", r"\d+"),
    "%b": ("bytes", r"\S+"),
    "%O": ("bytes", r"\S+"),
}
# %{HeaderName}i 같은 헤더 참조 형식지정자
_APACHE_HEADER_RE = re.compile(r"%\{([A-Za-z-]+)\}i")

_NAME_FOR_HEADER = {
    "Referer": "referer",
    "User-Agent": "user_agent",
}


def extract_apache_log_format(conf_path: str, format_name: str = "combined") -> str:
    """httpd.conf 등에서 `LogFormat "..." name` 지시자를 찾아 포맷 문자열을 반환.

    실제 httpd.conf에는 %r, %{Referer}i 등을 감싸는 큰따옴표가
    `\\"` 형태로 이스케이프되어 있으므로, 이를 고려한 정규식을 사용한다.
    """
    with open(conf_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    # 큰따옴표 문자열 안에서 \" (이스케이프된 따옴표)는 그대로 두고, 진짜 닫는 따옴표에서만 멈춘다
    pattern = re.compile(r'LogFormat\s+"((?:\\.|[^"\\])*)"\s+' + re.escape(format_name))
    m = pattern.search(content)
    if not m:
        raise ValueError(f"LogFormat '{format_name}' 을(를) {conf_path} 에서 찾지 못함")
    # \" -> ", \\ -> \ 로 언이스케이프
    return m.group(1).replace('\\"', '"').replace("\\\\", "\\")


def extract_nginx_log_format(conf_path: str, format_name: str = "combined") -> str:
    """nginx.conf 등에서 `log_format name '...'` 지시자를 찾아 포맷 문자열을 반환."""
    with open(conf_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    pattern = re.compile(
        r"log_format\s+" + re.escape(format_name) + r"\s+'([^']+)'", re.DOTALL
    )
    m = pattern.search(content)
    if not m:
        raise ValueError(f"log_format '{format_name}' 을(를) {conf_path} 에서 찾지 못함")
    return m.group(1)


def build_apache_regex(format_string: str):
    """Apache 포맷 문자열 -> (컴파일된 정규식, 필드명 리스트)."""
    tokens = re.split(r"(%\{[A-Za-z-]+\}i|%>?s|%[a-zA-Z])", format_string)
    regex_parts = []
    for token in tokens:
        if not token:
            continue
        header_match = _APACHE_HEADER_RE.fullmatch(token)
        if header_match:
            header_name = header_match.group(1)
            field_name = _NAME_FOR_HEADER.get(header_name, header_name.lower().replace("-", "_"))
            regex_parts.append(f'(?P<{field_name}>[^"]*)')
        elif token in _APACHE_DIRECTIVES:
            field_name, pat = _APACHE_DIRECTIVES[token]
            regex_parts.append(f"(?P<{field_name}>{pat})")
        else:
            regex_parts.append(re.escape(token))
    regex = re.compile("".join(regex_parts))
    return regex


def build_nginx_regex(format_string: str):
    """nginx 포맷 문자열($variable 방식) -> (컴파일된 정규식)."""
    tokens = re.split(r"(\$[a-zA-Z_]+)", format_string)
    regex_parts = []
    for token in tokens:
        if not token:
            continue
        if token.startswith("$"):
            field_name = token[1:]
            # 값에 공백/따옴표가 포함될 수 있는 필드는 넓게, 아니면 \S+
            wide_fields = {"request", "http_referer", "http_user_agent"}
            pat = r'[^"]*' if field_name in wide_fields else r"\S+"
            regex_parts.append(f"(?P<{field_name}>{pat})")
        else:
            regex_parts.append(re.escape(token))
    return re.compile("".join(regex_parts))


_REQUEST_LINE_RE = re.compile(r"^(?P<method>\S+)\s+(?P<uri>\S+)\s+HTTP/(?P<http_version>[\d.]+)$")


class ConfFormatParser:
    """conf 파일에서 로그 포맷을 읽어 라인을 파싱하는 파서."""

    def __init__(self, conf_path: str, style: str, format_name: str = "combined"):
        if style == "apache":
            fmt = extract_apache_log_format(conf_path, format_name)
            self._regex = build_apache_regex(fmt)
        elif style == "nginx":
            fmt = extract_nginx_log_format(conf_path, format_name)
            self._regex = build_nginx_regex(fmt)
        else:
            raise ValueError(f"지원하지 않는 conf_style: {style}")

    def parse(self, line: str) -> dict | None:
        m = self._regex.match(line)
        if not m:
            return None
        fields = m.groupdict()
        # %t 는 대괄호를 포함해서 캡처되므로 여기서만 벗겨낸다
        for k, v in fields.items():
            if v and len(v) >= 2 and v[0] == "[" and v[-1] == "]":
                fields[k] = v[1:-1]
        # request("GET /path HTTP/1.1")를 method/uri로 다시 쪼갠다 (LogFormat 변경 없이 가능)
        request = fields.get("request")
        if request:
            m2 = _REQUEST_LINE_RE.match(request)
            if m2:
                fields.update(m2.groupdict())
        return fields
