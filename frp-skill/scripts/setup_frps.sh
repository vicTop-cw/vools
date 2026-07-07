#!/bin/bash
# frp 服务端 (frps) Linux 一键部署脚本
# 用法：bash setup_frps.sh [版本号] [公网端口]
# 示例：bash setup_frps.sh 0.67.0 12345
set -e

VERSION="${1:-0.67.0}"
REMOTE_PORT="${2:-12345}"
BIND_PORT=7000

echo "[1/5] 正在下载 frp v${VERSION} ..."
wget -q "https://github.com/fatedier/frp/releases/download/v${VERSION}/frp_${VERSION}_linux_amd64.tar.gz" -O /tmp/frp.tar.gz
tar -xzf /tmp/frp.tar.gz -C /tmp
sudo cp "/tmp/frp_${VERSION}_linux_amd64/frps" /usr/local/bin/
rm -rf /tmp/frp.tar.gz "/tmp/frp_${VERSION}_linux_amd64"
echo "  OK - frps 已安装到 /usr/local/bin/frps"

echo "[2/5] 正在创建配置文件 /etc/frp/frps.toml ..."
sudo mkdir -p /etc/frp
sudo tee /etc/frp/frps.toml > /dev/null <<EOF
bindPort = ${BIND_PORT}
EOF
echo "  OK"

echo "[3/5] 正在配置防火墙 ..."
if command -v firewall-cmd &> /dev/null; then
    sudo firewall-cmd --add-port=${BIND_PORT}/tcp --permanent 2>/dev/null || true
    sudo firewall-cmd --add-port=${REMOTE_PORT}/tcp --permanent 2>/dev/null || true
    sudo firewall-cmd --reload 2>/dev/null || true
    echo "  OK - firewalld 规则已添加。"
elif command -v ufw &> /dev/null; then
    sudo ufw allow ${BIND_PORT}/tcp 2>/dev/null || true
    sudo ufw allow ${REMOTE_PORT}/tcp 2>/dev/null || true
    echo "  OK - ufw 规则已添加。"
else
    echo "  警告 - 未检测到防火墙工具，请手动开放端口 ${BIND_PORT} 和 ${REMOTE_PORT}。"
fi

echo "[4/5] 正在创建 systemd 服务 ..."
sudo tee /etc/systemd/system/frps.service > /dev/null <<EOF
[Unit]
Description=frps service
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/frps -c /etc/frp/frps.toml
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable frps
echo "  OK - frps.service 已创建并设为开机自启。"

echo "[5/5] 正在启动 frps ..."
sudo systemctl start frps
sleep 1
if sudo systemctl is-active --quiet frps; then
    echo "  OK - frps 正在运行。"
    echo ""
    echo "=== 部署完成 ==="
    echo "  通信端口  : ${BIND_PORT}"
    echo "  转发端口  : ${REMOTE_PORT}"
    echo ""
    echo "管理命令: sudo systemctl {status|restart|stop} frps"
    echo "查看日志: journalctl -u frps -f"
else
    echo "  失败 - frps 未能启动，请检查: journalctl -u frps -e"
    exit 1
fi
