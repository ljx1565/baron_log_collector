#!/usr/bin/env bash
#
# log_server(중앙 API + 대시보드) 설치 스크립트
#
# 사용법: 중앙 서버에서 root 권한으로 실행
#   sudo bash log_server_install.sh
#
# DB/토큰 값은 편의상 아래에 하드코딩되어 있으므로 사용자 입력 없이 자동 진행됩니다.
# MariaDB의 root 비밀번호가 이미 DB_PASSWORD 값으로 설정되어 있어야 합니다
# (mysql_secure_installation 등으로 미리 맞춰둘 것).
#
set -euo pipefail

# ---- 배포 전에 실제 값으로 채워두세요 ------------------------------------
SOURCE_URL="https://example.com/path/to/log_server.tar.gz"   # TODO: 실제 다운로드 주소로 교체
DB_HOST="localhost"
DB_USER="root"
DB_PASSWORD="asd123!@"
DB_NAME="soc"
API_TOKEN="asd123"
# --------------------------------------------------------------------------

INSTALL_DIR="/opt/log_server"
SERVICE_NAME="log-server"

if [ "$(id -u)" -ne 0 ]; then
    echo "root 권한으로 실행하세요: sudo bash log_server_install.sh" >&2
    exit 1
fi

echo "=== log_server 설치 (하드코딩 값 사용, 입력 없이 자동 진행) ==="

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "[1/5] 소스 다운로드..."
wget -qO "$TMP_DIR/log_server.tar.gz" "$SOURCE_URL"
tar -xzf "$TMP_DIR/log_server.tar.gz" -C "$TMP_DIR"
SRC_DIR="$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n1)"
if [ -z "$SRC_DIR" ]; then
    echo "다운로드한 압축 파일에서 소스 디렉터리를 찾지 못했습니다." >&2
    exit 1
fi

echo "[2/5] 설치 디렉터리에 복사: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "$SRC_DIR"/* "$INSTALL_DIR"/

echo "[3/5] DB 스키마 적용..."
mysql -u "$DB_USER" -p"$DB_PASSWORD" < "$INSTALL_DIR/schema.sql"

echo "[4/5] 파이썬 패키지 설치..."
pip3 install --quiet -r "$INSTALL_DIR/requirements.txt" --break-system-packages 2>/dev/null \
    || pip3 install --quiet -r "$INSTALL_DIR/requirements.txt"

echo "[5/5] systemd 서비스 등록..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=SOC Central API + Dashboard
After=network.target mariadb.service
Requires=mariadb.service

[Service]
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/app.py
WorkingDirectory=${INSTALL_DIR}
Restart=always
RestartSec=3
User=root
Environment=SOC_DB_HOST=${DB_HOST}
Environment=SOC_DB_USER=${DB_USER}
Environment=SOC_DB_PASSWORD=${DB_PASSWORD}
Environment=SOC_DB_NAME=${DB_NAME}
Environment=SOC_API_TOKEN=${API_TOKEN}

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

echo
echo "설치 완료."
echo "상태 확인 : systemctl status ${SERVICE_NAME}"
echo "로그 확인 : journalctl -u ${SERVICE_NAME} -f"
