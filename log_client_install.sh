#!/usr/bin/env bash
#
# log_client(collector) 설치 스크립트
#
# 사용법: 이 서버에서 root 권한으로 실행
#   sudo bash log_client_install.sh
#
set -euo pipefail

# 다운로드 링크 및 토큰값
SOURCE_URL="https://github.com/ljx1565/baron_log_collector"   # TODO: 실제 다운로드 주소로 교체
API_TOKEN="asd123"                                            # 서버와 동일한 토큰 (하드코딩)
# --------------------------------------------------------------------------

INSTALL_DIR="/opt/log_client"
SERVICE_NAME="log-client"

if [ "$(id -u)" -ne 0 ]; then
    echo "root 권한으로 실행하세요: sudo bash log_client_install.sh" >&2
    exit 1
fi

echo "=== log_client(collector) 설치 ==="
echo "먼저 이 서버에 맞는 값을 입력받습니다. 입력이 끝나야 실제 설치가 시작되며,"
echo "설치 도중 네트워크가 끊겨도 여기까지는 아무 변경도 일어나지 않습니다."
echo

read -rp "이 서버의 hostname (DB에 기록될 식별자, 예: server01) : " INPUT_HOSTNAME
while [ -z "$INPUT_HOSTNAME" ]; do
    read -rp "값을 입력하세요 (빈 값 불가) hostname: " INPUT_HOSTNAME
done

read -rp "중앙 API 주소 [기본값: http://localhost:5000/api/events] : " INPUT_API_URL
INPUT_API_URL="${INPUT_API_URL:-http://localhost:5000/api/events}"

echo
echo "입력값 확인"
echo "  hostname = $INPUT_HOSTNAME"
echo "  api_url  = $INPUT_API_URL"
echo "  api_token = (하드코딩된 값 사용)"
read -rp "이대로 설치를 진행할까요? [Y/n] " CONFIRM
CONFIRM="${CONFIRM:-Y}"
if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "설치를 취소했습니다. 아무것도 변경되지 않았습니다."
    exit 0
fi

echo
echo ">>> 여기서부터는 입력 없이 자동으로 진행됩니다 <<<"
echo

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "[1/6] 소스 다운로드..."
wget -qO "$TMP_DIR/log_client.tar.gz" "$SOURCE_URL"
tar -xzf "$TMP_DIR/log_client.tar.gz" -C "$TMP_DIR"
SRC_DIR="$(find "$TMP_DIR" -mindepth 1 -maxdepth 1 -type d | head -n1)"
if [ -z "$SRC_DIR" ]; then
    echo "다운로드한 압축 파일에서 소스 디렉터리를 찾지 못했습니다." >&2
    exit 1
fi

echo "[2/6] 설치 디렉터리에 복사: $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
cp -r "$SRC_DIR"/* "$INSTALL_DIR"/

echo "[3/6] config.yaml에 입력값 반영..."
python3 - "$INSTALL_DIR/config.yaml" "$INPUT_HOSTNAME" "$INPUT_API_URL" "$API_TOKEN" <<'PYEOF'
import sys

path, hostname, api_url, token = sys.argv[1:5]
with open(path, encoding="utf-8") as f:
    lines = f.readlines()

out = []
for line in lines:
    if line.startswith("hostname:"):
        out.append(f'hostname: "{hostname}"\n')
    elif line.startswith("api_url:"):
        out.append(f'api_url: "{api_url}"\n')
    elif line.startswith("api_token:"):
        out.append(f'api_token: "{token}"\n')
    else:
        out.append(line)

with open(path, "w", encoding="utf-8") as f:
    f.writelines(out)
PYEOF

echo "[4/6] 파이썬 패키지 설치..."
pip3 install --quiet -r "$INSTALL_DIR/requirements.txt" --break-system-packages 2>/dev/null \
    || pip3 install --quiet -r "$INSTALL_DIR/requirements.txt"

echo "[5/6] auditd 규칙 적용..."
if [ -f "$INSTALL_DIR/audit.rules.example" ]; then
    cp "$INSTALL_DIR/audit.rules.example" /etc/audit/rules.d/soc.rules
    augenrules --load 2>/dev/null || echo "  (augenrules 적용 실패 - auditd가 설치되어 있는지 확인하세요)"
fi

echo "[6/6] systemd 서비스 등록..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=SOC Log Collector
After=network.target log-server.service
Wants=log-server.service

[Service]
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/main.py
WorkingDirectory=${INSTALL_DIR}
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

echo
echo "설치 완료."
echo "상태 확인 : systemctl status ${SERVICE_NAME}"
echo "로그 확인 : journalctl -u ${SERVICE_NAME} -f"
