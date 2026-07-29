## sh 실행 시 아래가 실행됩니다.

```
# 필요 패키지 설치
pip install -r /opt/log_client/requirements.txt
config.yaml 에서 hostname / api_url / api_token / 각 log_path·conf_path 수정

# auditd 감사 로그 규칙 규정
sudo cp /opt/log_client/audit.rules.example /etc/audit/rules.d/soc.rules
sudo augenrules --load


# client 서비스 등록
cat << 'EOF' | sudo tee /etc/systemd/system/log-client.service[Unit]
Description=SOC Log Collector
After=network.target log-server.service
Wants=log-server.service

[Service]
ExecStart=/usr/bin/python3 /opt/log_client/main.py
WorkingDirectory=/opt/log_client
Restart=always
User=root

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now log-client
```
