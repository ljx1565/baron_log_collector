## 폴더를 opt 폴더에 넣어주세요.


# 필요 패키지 설치
pip install -r /opt/log_client/requirements.txt
config.yaml 에서 hostname / api_url / api_token / 각 log_path·conf_path 수정

# auditd 감사 로그 규칙 규정
sudo cp /opt/log_client/audit.rules.example /etc/audit/rules.d/soc.rules
sudo augenrules --load


# client 서비스 등록
cat < eof>  /etc/systemd/system/log-client.service
[Unit]
Description=SOC Log Collector
After=network.target log-server.service
Wants=log-server.service

[Service]
ExecStart=/usr/bin/python3 /opt/collector/main.py
WorkingDirectory=/opt/collector
Restart=always
User=root

[Install]
WantedBy=multi-user.target


sudo systemctl daemon-reload
sudo systemctl enable --now log-client





## 구조

```
opt/
├── db/
│   └── schema.sql          # MariaDB 스키마 (hosts/log_sources/events/alert_rules/alerts + VIEW)
├── collector/               # 각 서버(Rocky/Ubuntu)에 배포하는 수집기
│   ├── config.yaml          # 이 서버가 수집할 로그 소스 정의 (경로/conf 파일 등 환경에 맞게 수정)
│   ├── tailer.py            # 로그 로테이션에 안전한 파일 tail
│   ├── severity.py          # 소스별 값 -> syslog 0~7 severity 매핑 규칙
│   ├── normalizer.py        # 파싱 결과 -> 공통 이벤트 스키마 변환
│   ├── sender.py            # 중앙 API로 즉시 전송 (재시도 포함)
│   ├── main.py              # 진입점 (소스별 스레드 실행)
│   └── parsers/
│       ├── conf_format.py   # Apache/Nginx LogFormat을 conf에서 읽어 동적 파싱
│       ├── json_parser.py   # Suricata eve.json 등 JSON 라인 로그
│       ├── journal_parser.py# systemd journal(syslog+cron) JSON 스트리밍
│       ├── samba_parser.py
│       ├── mariadb_parser.py
│       └── dns_parser.py
└── server/                  # 중앙 API + DB 저장 + 웹소켓 push + 관제 대시보드
    ├── db.py                # DB insert/upsert/조회 헬퍼 (PyMySQL)
    ├── app.py               # Flask + Flask-SocketIO API + 대시보드 라우트
    ├── templates/
    │   └── dashboard.html   # 관제 대시보드 페이지 (실시간 이벤트 스트림 + 알림 + 심각도 필터)
    └── requirements.txt
```










## 나머지

- `alert_rules` 테이블에 실제 규칙 데이터 삽입 (예: SSH 실패 임계치 등 팀에서 정의)
- 대시보드 인증/접근 제어 (지금은 누구나 `/`에 접속 가능)

## 추가 로그 소스 설정 (dnf/php_error/audit/tallylog/btmp/wtmp/firewalld/chrony)


**firewalld** — 차단된 패킷은 기본적으로 로그에 안 남는다.
```bash
sudo firewall-cmd --set-log-denied=all
sudo firewall-cmd --reload
```
규칙 변경 이력은 별도 설정 없이 journal로 바로 잡힌다.

**tallylog/btmp/wtmp** — 바이너리 로그라 tail이 불가능해서, `faillock`/`lastb`/`last` 명령을 30초 간격으로 실행해 이전 결과와 비교(diff)하는 방식으로 동작한다 (`opt/log_client/main.py`의 `run_polling_source`).



