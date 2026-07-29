-- ============================================================
-- 서버 관제 로그 DB 스키마 (MariaDB)
-- 모든 로그 소스를 하나의 events 테이블에 정규화하여 저장하고,
-- 소스별 특수 필드는 details(JSON)에 보관한다.
-- severity는 Linux syslog 표준(RFC 5424, 0~7)을 그대로 사용한다.
--   0 Emergency  1 Alert  2 Critical  3 Error
--   4 Warning    5 Notice 6 Informational  7 Debug
--   ※ 숫자가 낮을수록 심각도가 높다 (0이 가장 심각)
-- ============================================================

CREATE DATABASE IF NOT EXISTS soc CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE soc;

CREATE TABLE IF NOT EXISTS hosts (
    host_id     INT AUTO_INCREMENT PRIMARY KEY,
    hostname    VARCHAR(100) NOT NULL UNIQUE,
    ip_address  VARCHAR(45),
    os          VARCHAR(50),
    role        VARCHAR(50),           -- 'server' 등
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS log_sources (
    source_id   INT AUTO_INCREMENT PRIMARY KEY,
    source_name VARCHAR(50) NOT NULL UNIQUE
    -- 예: suricata_hids, web_access, syslog, cron, mariadb, samba, dns
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO log_sources (source_name) VALUES
    ('suricata_hids'), ('web_access'), ('cron'), ('auth'), ('rsyslog'), ('messages'),
    ('mariadb'), ('samba'), ('dns'),
    ('dnf'), ('php_error'), ('audit'), ('tallylog'), ('btmp'), ('wtmp'),
    ('firewalld'), ('chrony');

CREATE TABLE IF NOT EXISTS events (
    event_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
    host_id      INT NOT NULL,
    source_id    INT NOT NULL,
    event_time   DATETIME(3) NOT NULL,       -- 로그 자체 발생 시각
    received_at  DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3), -- DB 적재 시각
    severity     TINYINT NOT NULL,           -- 0~7 (RFC 5424)
    category     VARCHAR(50),                -- 예: web_access, auth_fail, dns_query
    src_ip       VARCHAR(45),
    dst_ip       VARCHAR(45),
    summary      VARCHAR(255),               -- 사람이 읽는 한 줄 요약
    details      JSON,                       -- 소스별 원본/부가 필드 전부
    FOREIGN KEY (host_id) REFERENCES hosts(host_id),
    FOREIGN KEY (source_id) REFERENCES log_sources(source_id),
    INDEX idx_event_time (event_time),
    INDEX idx_host_time (host_id, event_time),
    INDEX idx_source_time (source_id, event_time),
    INDEX idx_src_ip (src_ip),
    INDEX idx_severity (severity)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id         INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    source_id       INT NULL,               -- NULL이면 전체 소스에 적용
    min_severity    TINYINT NOT NULL,       -- 이 값 "이하"(=더 심각)일 때만 대상
    threshold_count INT NOT NULL DEFAULT 1, -- time_window_sec 내 발생 횟수
    time_window_sec INT NOT NULL DEFAULT 60,
    enabled         BOOLEAN DEFAULT TRUE,
    FOREIGN KEY (source_id) REFERENCES log_sources(source_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS alerts (
    alert_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
    rule_id      INT NOT NULL,
    event_id     BIGINT NOT NULL,
    triggered_at DATETIME(3) DEFAULT CURRENT_TIMESTAMP(3),
    message      VARCHAR(255),
    is_read      BOOLEAN DEFAULT FALSE,     -- 대시보드 내부 알림 읽음 여부
    FOREIGN KEY (rule_id) REFERENCES alert_rules(rule_id),
    FOREIGN KEY (event_id) REFERENCES events(event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ------------------------------------------------------------
-- 소스별 조회 뷰 예시 (필요할 때마다 이런 식으로 추가)
-- ------------------------------------------------------------
CREATE OR REPLACE VIEW v_web_access_events AS
SELECT event_id, host_id, event_time, severity, src_ip,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.method')) AS method,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.uri')) AS uri,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.status')) AS http_status,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.bytes')) AS body_bytes,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.referer')) AS referer,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.user_agent')) AS user_agent
FROM events
WHERE source_id = (SELECT source_id FROM log_sources WHERE source_name = 'web_access');

CREATE OR REPLACE VIEW v_samba_events AS
SELECT event_id, host_id, event_time, severity, src_ip,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.share')) AS share_name,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.smb_user')) AS smb_user
FROM events
WHERE source_id = (SELECT source_id FROM log_sources WHERE source_name = 'samba');

CREATE OR REPLACE VIEW v_dns_events AS
SELECT event_id, host_id, event_time, severity, src_ip,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.query_name')) AS query_name,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.query_type')) AS query_type
FROM events
WHERE source_id = (SELECT source_id FROM log_sources WHERE source_name = 'dns');

CREATE OR REPLACE VIEW v_mariadb_events AS
SELECT event_id, host_id, event_time, severity,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.level')) AS log_level,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.message')) AS message
FROM events
WHERE source_id = (SELECT source_id FROM log_sources WHERE source_name = 'mariadb');

CREATE OR REPLACE VIEW v_auth_events AS
SELECT event_id, host_id, event_time, severity,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.SYSLOG_IDENTIFIER')) AS identifier,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.MESSAGE')) AS message
FROM events
WHERE source_id = (SELECT source_id FROM log_sources WHERE source_name = 'auth');

CREATE OR REPLACE VIEW v_suricata_events AS
SELECT event_id, host_id, event_time, severity, src_ip, dst_ip,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.signature')) AS signature,
       JSON_UNQUOTE(JSON_EXTRACT(details, '$.category')) AS alert_category
FROM events
WHERE source_id = (SELECT source_id FROM log_sources WHERE source_name = 'suricata_hids');
