0. dnf install httpd -y
   dnf install Mariadb -y
   dnf install pip -y
   dnf install python3 -y

1. mysql -u root -p < /opt/log_server/schema.sql

2. pip install -r /opt/log_server/requirements.txt


# server 서비스 등록
cat /etc/systemd/system/log-server.service
[Unit]
Description=API service
After=network.target mariadb.service
Requires=mariadb.service

[Service]
ExecStart=/usr/bin/python3 /opt/log_server/app.py
WorkingDirectory=/opt/server
Restart=always
User=root
Environment=SOC_DB_HOST=localhost
Environment=SOC_DB_USER=root
Environment=SOC_DB_PASSWORD='asd123!@'
Environment=SOC_DB_NAME=soc
Environment=SOC_API_TOKEN=asd123

[Install]
WantedBy=multi-user.target

sudo systemctl daemon-reload
sudo systemctl enable --now log-server