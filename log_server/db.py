"""DB 연결 및 insert/upsert 헬퍼.

학습용 프로젝트 규모라 요청마다 커넥션을 새로 여는 단순한 방식으로 작성했다.
트래픽이 늘어나면 커넥션 풀(DBUtils.PooledDB 등)로 바꾸는 걸 권장한다.
"""

import json
import os

import pymysql

DB_CONFIG = dict(
    host=os.environ.get("SOC_DB_HOST", "localhost"),
    user=os.environ.get("SOC_DB_USER", "soc"),
    password=os.environ.get("SOC_DB_PASSWORD", "CHANGE_ME"),
    database=os.environ.get("SOC_DB_NAME", "soc"),
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
    autocommit=True,
)


def get_conn():
    return pymysql.connect(**DB_CONFIG)


def get_or_create_host(conn, hostname: str, ip_address: str = None) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT host_id, ip_address FROM hosts WHERE hostname=%s", (hostname,))
        row = cur.fetchone()
        if row:
            if ip_address and row["ip_address"] != ip_address:
                cur.execute("UPDATE hosts SET ip_address=%s WHERE host_id=%s", (ip_address, row["host_id"]))
            return row["host_id"]
        cur.execute("INSERT INTO hosts (hostname, ip_address) VALUES (%s, %s)", (hostname, ip_address))
        return cur.lastrowid


def get_or_create_source(conn, source_name: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT source_id FROM log_sources WHERE source_name=%s", (source_name,))
        row = cur.fetchone()
        if row:
            return row["source_id"]
        cur.execute("INSERT INTO log_sources (source_name) VALUES (%s)", (source_name,))
        return cur.lastrowid


def insert_event(conn, host_id: int, source_id: int, event: dict) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO events
                (host_id, source_id, event_time, severity, category, src_ip, dst_ip, summary, details)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                host_id,
                source_id,
                event["event_time"],
                event["severity"],
                event.get("category"),
                event.get("src_ip"),
                event.get("dst_ip"),
                event.get("summary"),
                json.dumps(event.get("details") or {}, ensure_ascii=False, default=str),
            ),
        )
        return cur.lastrowid


def matching_alert_rules(conn, source_id: int, severity: int):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT * FROM alert_rules
            WHERE enabled = TRUE
              AND (source_id IS NULL OR source_id = %s)
              AND min_severity >= %s
            """,
            (source_id, severity),
        )
        return cur.fetchall()


def count_recent_events(conn, source_id: int, severity_at_most: int, window_sec: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt FROM events
            WHERE source_id = %s
              AND severity <= %s
              AND event_time >= NOW() - INTERVAL %s SECOND
            """,
            (source_id, severity_at_most, window_sec),
        )
        return cur.fetchone()["cnt"]


def insert_alert(conn, rule_id: int, event_id: int, message: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO alerts (rule_id, event_id, message) VALUES (%s, %s, %s)",
            (rule_id, event_id, message),
        )
        return cur.lastrowid


# ------------------------------------------------------------
# 대시보드 조회용
# ------------------------------------------------------------

def fetch_events(conn, limit=100, host=None, source=None, max_severity=None):
    """최근 이벤트 목록. max_severity는 '이 값 이하만'(=더 심각한 것만) 필터링.
    (severity는 낮을수록 심각하다는 점 주의)"""
    conditions = []
    params = []
    if host:
        conditions.append("h.hostname = %s")
        params.append(host)
    if source:
        conditions.append("s.source_name = %s")
        params.append(source)
    if max_severity is not None:
        conditions.append("e.severity <= %s")
        params.append(max_severity)
    where_clause = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    query = f"""
        SELECT e.event_id, h.hostname, s.source_name, e.event_time, e.severity,
               e.category, e.src_ip, e.dst_ip, e.summary, e.details
        FROM events e
        JOIN hosts h ON h.host_id = e.host_id
        JOIN log_sources s ON s.source_id = e.source_id
        {where_clause}
        ORDER BY e.event_id DESC
        LIMIT %s
    """
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
        for row in rows:
            if row.get("details"):
                try:
                    row["details"] = json.loads(row["details"])
                except (TypeError, ValueError):
                    row["details"] = {}
            else:
                row["details"] = {}
        return rows


def fetch_alerts(conn, limit=50, unread_only=False):
    where_clause = "WHERE a.is_read = FALSE" if unread_only else ""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT a.alert_id, a.message, a.triggered_at, a.is_read, a.event_id
            FROM alerts a
            {where_clause}
            ORDER BY a.alert_id DESC
            LIMIT %s
            """,
            (limit,),
        )
        return cur.fetchall()


def mark_alert_read(conn, alert_id: int):
    with conn.cursor() as cur:
        cur.execute("UPDATE alerts SET is_read = TRUE WHERE alert_id = %s", (alert_id,))


def list_hosts(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT hostname, ip_address FROM hosts ORDER BY hostname")
        return cur.fetchall()


def list_sources(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT source_name FROM log_sources ORDER BY source_name")
        return [row["source_name"] for row in cur.fetchall()]
