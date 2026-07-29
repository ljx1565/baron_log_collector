## sh 실행 시 아래가 실행됩니다.

```
dnf install httpd -y
dnf install Mariadb -y
dnf install pip -y
dnf install python3 -y

mysql -u root -p < /opt/log_server/schema.sql
pip install -r /opt/log_server/requirements.txt

# server 서비스 등록
cat << 'EOF' | sudo tee /etc/systemd/system/log-server.service
[Unit]
Description=API service
After=network.target mariadb.service
Requires=mariadb.service

[Service]
ExecStart=/usr/bin/python3 /opt/log_server/app.py
WorkingDirectory=/opt/log_server
Restart=always
User=root
Environment=SOC_DB_HOST=localhost
Environment=SOC_DB_USER=root
Environment=SOC_DB_PASSWORD='asd123!@'
Environment=SOC_DB_NAME=soc
Environment=SOC_API_TOKEN=asd123

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now log-server
```
