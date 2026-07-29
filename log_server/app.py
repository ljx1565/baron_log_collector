"""
중앙 관제 API 서버.

각 서버(collector)가 로그를 생성 즉시 POST /api/events 로 전송하면:
  1) hosts / log_sources 를 upsert
  2) events 테이블에 저장
  3) alert_rules 조건을 만족하는지 확인해서 만족하면 alerts 테이블에 기록
  4) 웹소켓으로 대시보드에 실시간 push (새 이벤트 / 새 알림 모두 대시보드 내부 알림으로만 처리)
"""

import os

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO

import db

API_TOKEN = os.environ.get("SOC_API_TOKEN", "CHANGE_ME")

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True
socketio = SocketIO(app, cors_allowed_origins="*")


def _check_auth(req) -> bool:
    auth = req.headers.get("Authorization", "")
    return auth == f"Bearer {API_TOKEN}"


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/events", methods=["POST"])
def receive_event():
    if not _check_auth(request):
        return jsonify({"error": "unauthorized"}), 401

    event = request.get_json(silent=True)
    if not event:
        return jsonify({"error": "invalid json"}), 400

    hostname = event.get("hostname")
    source_name = event.get("source_name")
    if not hostname or not source_name:
        return jsonify({"error": "hostname/source_name required"}), 400

    try:
        conn = db.get_conn()
    except Exception:
        app.logger.exception("DB 연결 실패 (SOC_DB_HOST/USER/PASSWORD/NAME 환경변수를 확인하세요)")
        return jsonify({"error": "db connection failed"}), 500

    try:
        host_id = db.get_or_create_host(conn, hostname, event.get("host_ip"))
        source_id = db.get_or_create_source(conn, source_name)
        event_id = db.insert_event(conn, host_id, source_id, event)

        # 웹소켓으로 대시보드에 새 이벤트 push
        socketio.emit("new_event", {
            "event_id": event_id,
            "hostname": hostname,
            "source_name": source_name,
            "event_time": event["event_time"],
            "severity": event["severity"],
            "summary": event.get("summary"),
            "src_ip": event.get("src_ip"),
            "details": event.get("details") or {},
        })

        _check_and_raise_alerts(conn, source_id, event, event_id, hostname)
    except Exception:
        app.logger.exception("이벤트 처리 중 오류 (payload: %s)", event)
        return jsonify({"error": "internal error, check server logs"}), 500
    finally:
        conn.close()

    return jsonify({"status": "ok", "event_id": event_id}), 200


def _check_and_raise_alerts(conn, source_id, event, event_id, hostname):
    """이 이벤트 severity 기준으로 걸리는 규칙들을 확인하고, 임계치를 넘으면 알림 생성."""
    rules = db.matching_alert_rules(conn, source_id, event["severity"])
    for rule in rules:
        count = db.count_recent_events(
            conn, source_id, rule["min_severity"], rule["time_window_sec"]
        )
        if count >= rule["threshold_count"]:
            message = (
                f'[{hostname}] "{rule["name"]}" 규칙 발동 '
                f'({rule["time_window_sec"]}초 내 {count}건)'
            )
            db.insert_alert(conn, rule["rule_id"], event_id, message)
            # 대시보드 내부 알림만 사용하기로 했으므로 웹소켓으로만 push
            socketio.emit("new_alert", {
                "rule_name": rule["name"],
                "message": message,
                "event_id": event_id,
            })


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/events", methods=["GET"])
def list_events():
    limit = min(int(request.args.get("limit", 100)), 500)
    host = request.args.get("host") or None
    source = request.args.get("source") or None
    max_severity = request.args.get("max_severity")
    max_severity = int(max_severity) if max_severity is not None else None

    conn = db.get_conn()
    try:
        rows = db.fetch_events(conn, limit=limit, host=host, source=source, max_severity=max_severity)
    finally:
        conn.close()
    return jsonify(rows)


@app.route("/api/alerts", methods=["GET"])
def list_alerts():
    unread_only = request.args.get("unread_only") == "1"
    conn = db.get_conn()
    try:
        rows = db.fetch_alerts(conn, unread_only=unread_only)
    finally:
        conn.close()
    return jsonify(rows)


@app.route("/api/alerts/<int:alert_id>/read", methods=["POST"])
def read_alert(alert_id):
    conn = db.get_conn()
    try:
        db.mark_alert_read(conn, alert_id)
    finally:
        conn.close()
    return jsonify({"status": "ok"})


@app.route("/api/meta", methods=["GET"])
def meta():
    conn = db.get_conn()
    try:
        hosts = db.list_hosts(conn)
        sources = db.list_sources(conn)
    finally:
        conn.close()
    return jsonify({"hosts": hosts, "sources": sources})


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=5000)
