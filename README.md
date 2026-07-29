## 구조

```
opt/
├── log_client/               # 각 서버(Rocky/Ubuntu)에 배포하는 수집기
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
└── log_server/                  # 중앙 API + DB 저장 + 웹소켓 push + 관제 대시보드
    ├── schema.sql          # MariaDB 스키마 (hosts/log_sources/events/alert_rules/alerts + VIEW)
    ├── db.py                # DB insert/upsert/조회 헬퍼 (PyMySQL)
    ├── app.py               # Flask + Flask-SocketIO API + 대시보드 라우트
    ├── templates/
    │   └── dashboard.html   # 관제 대시보드 페이지 (실시간 이벤트 스트림 + 알림 + 심각도 필터)
    └── requirements.txt
```



## 기타 사항

- `alert_rules` 테이블에 실제 규칙 데이터 삽입
- 대시보드 인증/접근 제어 (지금은 누구나 `/`에 접속 가능)

## 추가 로그 소스 설정 (dnf/php_error/audit/tallylog/btmp/wtmp/firewalld/chrony)

## firewalld 차단 패킷 로깅 설정
sudo firewall-cmd --set-log-denied=all
sudo firewall-cmd --reload

**tallylog/btmp/wtmp** — tail 명령어가 안 막히는 바이너리 로그는 faillock / lastb / last 명령을 30초 간격으로 실행해 이전 결과와 비교(diff)하는 방식으로 동작 (opt/log_client/main.py의 run_polling_source)