#!/bin/bash
# ============================================================
# Nurture Baby Monitor — Sensor Library Installer for Pi 5
# Run this script ONCE on your Raspberry Pi 5
# Usage:  sudo bash install_sensors.sh
# ============================================================
set -e

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   Nurture Baby Monitor — Pi 5 Sensor Setup           ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# ── 1. System packages ────────────────────────────────────────────────────────
echo "▶ Installing system packages..."
apt-get update -q
apt-get install -y -q \
    python3-pip \
    python3-smbus \
    i2c-tools \
    python3-serial \
    libcamera-dev \
    python3-opencv \
    git \
    curl

# ── 2. Enable I²C and UART interfaces ────────────────────────────────────────
echo "▶ Enabling I²C interface..."
raspi-config nonint do_i2c 0

echo "▶ Enabling UART (for MH-Z19B CO₂ sensor)..."
raspi-config nonint do_serial_hw 0   # enable UART hardware
raspi-config nonint do_serial_cons 1 # disable serial console (free port for sensor)

# ── 3. Python sensor libraries ────────────────────────────────────────────────
echo "▶ Installing Python sensor libraries..."
pip3 install --break-system-packages \
    adafruit-blinka \
    adafruit-circuitpython-mlx90614 \
    adafruit-circuitpython-bme680 \
    adafruit-circuitpython-ads1x15 \
    mh-z19 \
    RPi.GPIO \
    opencv-python-headless

# ── 4. Project folder ─────────────────────────────────────────────────────────
echo "▶ Setting up project folder at /home/pi/nurture..."
mkdir -p /home/pi/nurture
if [ -d /root/livestreaming/pi ]; then
    cp /root/livestreaming/pi/*.py /home/pi/nurture/
    echo "   ✓ Copied Pi scripts"
elif [ -d /home/pi/livestreaming/pi ]; then
    cp /home/pi/livestreaming/pi/*.py /home/pi/nurture/
    echo "   ✓ Copied Pi scripts"
else
    echo "   ⚠ Could not find pi/ folder — copy sensor_server.py, sensor_reader.py, stream_server.py manually"
fi
chown -R pi:pi /home/pi/nurture

# ── 5. Install sensor server systemd service ──────────────────────────────────
echo "▶ Installing sensor server systemd service (port 5000)..."
cat > /etc/systemd/system/nurture-sensor.service << 'EOF'
[Unit]
Description=Nurture Baby Monitor — Sensor Server
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/nurture/sensor_server.py --port 5000 --camera-index 0
WorkingDirectory=/home/pi/nurture
Restart=always
RestartSec=5
User=pi

[Install]
WantedBy=multi-user.target
EOF

# ── 6. Install stream server systemd service ──────────────────────────────────
echo "▶ Installing stream server systemd service (port 8080)..."
cat > /etc/systemd/system/nurture-stream.service << 'EOF'
[Unit]
Description=Nurture Baby Monitor — MJPEG Live Stream
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/nurture/stream_server.py --camera usb --port 8080
WorkingDirectory=/home/pi/nurture
Restart=always
RestartSec=5
User=pi

[Install]
WantedBy=multi-user.target
EOF

# ── 7. Install Cloudflare Tunnel ──────────────────────────────────────────────
echo "▶ Installing cloudflared..."
ARCH=$(uname -m)
if [ "$ARCH" = "aarch64" ]; then
    CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64"
else
    CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-armhf"
fi
curl -L "$CF_URL" -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# Cloudflare tunnel service — tunnels BOTH port 5000 (sensor) and 8080 (stream)
echo "▶ Installing Cloudflare tunnel service for port 5000 (sensor API)..."
cat > /etc/systemd/system/nurture-tunnel.service << 'EOF'
[Unit]
Description=Nurture Cloudflare Tunnel (Sensor API)
After=network.target nurture-sensor.service

[Service]
ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:5000
Restart=always
RestartSec=10
User=pi

[Install]
WantedBy=multi-user.target
EOF

# ── 8. Enable and start all services ─────────────────────────────────────────
echo "▶ Enabling services to start on boot..."
systemctl daemon-reload
systemctl enable nurture-sensor.service
systemctl enable nurture-stream.service
systemctl enable nurture-tunnel.service
systemctl start nurture-sensor.service
systemctl start nurture-stream.service
systemctl start nurture-tunnel.service

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✅  Setup Complete!                                 ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  Services running:                                    ║"
echo "║    sensor_server  → http://localhost:5000             ║"
echo "║    stream_server  → http://localhost:8080/stream      ║"
echo "║    cloudflared    → (get URL below)                   ║"
echo "╠══════════════════════════════════════════════════════╣"
echo "║  NEXT STEP: Get your public Cloudflare tunnel URL:   ║"
echo "║    sudo journalctl -u nurture-tunnel -f              ║"
echo "║                                                       ║"
echo "║  Then activate sensors:                               ║"
echo "║    curl -X POST http://localhost:5000/api/activate \  ║"
echo "║         -d '{\"active\":true}'                         ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "⚠  REBOOT REQUIRED for UART (MH-Z19B) to work:"
echo "   sudo reboot"
echo ""
