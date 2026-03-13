#!/bin/bash
# ============================================================
# Nurture Baby Monitor — Full Auto-Start Setup
# Run once: sudo bash install_sensors.sh
# Creates 4 services that auto-start on every boot:
#   1. sensor_server  (port 5000 — sensor JSON API)
#   2. stream_server  (port 8080 — MJPEG camera)
#   3. nurture-sensor-tunnel (Cloudflare → port 5000)
#   4. nurture-stream-tunnel (Cloudflare → port 8080)
# ============================================================
set -e

# Detect actual username (works whether run as root or pi/saikishore)
ACTUAL_USER=${SUDO_USER:-$(logname 2>/dev/null || echo $USER)}
HOME_DIR=$(eval echo "~$ACTUAL_USER")
PI_DIR="$HOME_DIR/livestreaming/pi"
PYTHON=/usr/bin/python3

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Nurture Baby Monitor — Auto-Start Setup            ║"
echo "║   User: $ACTUAL_USER                                 "
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
echo "▶ Installing system packages..."
apt-get update -q
apt-get install -y -q \
    python3-pip i2c-tools python3-smbus python3-serial \
    libcamera-apps git curl

# ── 2. Python sensor libraries ────────────────────────────────────────────────
echo "▶ Installing Python sensor libraries..."
pip3 install --break-system-packages \
    adafruit-blinka \
    adafruit-circuitpython-bme680 \
    adafruit-circuitpython-ads1x15 \
    adafruit-circuitpython-mlx90614 \
    mh-z19 \
    flask

# ── 3. Install cloudflared ────────────────────────────────────────────────────
if ! command -v cloudflared &>/dev/null; then
    echo "▶ Installing cloudflared..."
    ARCH=$(uname -m)
    if [ "$ARCH" = "aarch64" ]; then
        CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
    else
        CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-armhf"
    fi
    curl -L "$CF_URL" -o /usr/local/bin/cloudflared
    chmod +x /usr/local/bin/cloudflared
    echo "   ✓ cloudflared installed"
else
    echo "   ✓ cloudflared already installed"
fi

# ── 4. Sensor Server service ──────────────────────────────────────────────────
echo "▶ Creating nurture-sensor service (port 5000)..."
cat > /etc/systemd/system/nurture-sensor.service << EOF
[Unit]
Description=Nurture Sensor API Server
After=network.target
StartLimitIntervalSec=0

[Service]
ExecStart=$PYTHON $PI_DIR/sensor_server.py --port 5000 --start-active
WorkingDirectory=$PI_DIR
Restart=always
RestartSec=5
User=$ACTUAL_USER
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── 5. Stream Server service ──────────────────────────────────────────────────
echo "▶ Creating nurture-stream service (port 8080)..."
cat > /etc/systemd/system/nurture-stream.service << EOF
[Unit]
Description=Nurture MJPEG Camera Stream
After=network.target
StartLimitIntervalSec=0

[Service]
ExecStart=$PYTHON $PI_DIR/stream_server.py --port 8080 --camera usb
WorkingDirectory=$PI_DIR
Restart=always
RestartSec=5
User=$ACTUAL_USER
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── 6. Cloudflare Tunnel — Sensor (port 5000) ─────────────────────────────────
echo "▶ Creating cloudflare tunnel service for sensor API..."
cat > /etc/systemd/system/nurture-sensor-tunnel.service << EOF
[Unit]
Description=Cloudflare Tunnel — Nurture Sensor API (port 5000)
After=network.target nurture-sensor.service
StartLimitIntervalSec=0

[Service]
ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:5000 --loglevel info
Restart=always
RestartSec=10
User=$ACTUAL_USER
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── 7. Cloudflare Tunnel — Stream (port 8080) ─────────────────────────────────
echo "▶ Creating cloudflare tunnel service for camera stream..."
cat > /etc/systemd/system/nurture-stream-tunnel.service << EOF
[Unit]
Description=Cloudflare Tunnel — Nurture Camera Stream (port 8080)
After=network.target nurture-stream.service
StartLimitIntervalSec=0

[Service]
ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:8080 --loglevel info
Restart=always
RestartSec=10
User=$ACTUAL_USER
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── 8. Enable and start all services ─────────────────────────────────────────
echo "▶ Enabling and starting all services..."
systemctl daemon-reload

for svc in nurture-sensor nurture-stream nurture-sensor-tunnel nurture-stream-tunnel; do
    systemctl enable "$svc.service"
    systemctl restart "$svc.service"
    echo "   ✓ $svc started"
done

sleep 5

# ── 9. Print the tunnel URLs ──────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✅  Setup Complete! Services auto-start on boot.   ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Fetching Cloudflare tunnel URLs...                  ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "📡 Sensor API URL:"
journalctl -u nurture-sensor-tunnel --no-pager -n 50 2>/dev/null \
    | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1 \
    || echo "   (still starting — run: sudo journalctl -u nurture-sensor-tunnel -f)"

echo ""
echo "📷 Camera Stream URL:"
journalctl -u nurture-stream-tunnel --no-pager -n 50 2>/dev/null \
    | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1 \
    || echo "   (still starting — run: sudo journalctl -u nurture-stream-tunnel -f)"

echo ""
echo "After boot, get URLs anytime with:"
echo "  sudo bash ~/livestreaming/pi/get_urls.sh"
echo ""
