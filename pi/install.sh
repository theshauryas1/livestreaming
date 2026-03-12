#!/usr/bin/env bash
# ============================================================
#  Pi Camera Live Stream — Installer
#  Supports:
#    pi   → Raspberry Pi Camera Module 3  (picamera2)
#    pi5  → Raspberry Pi 5 Camera Module  (picamera2)
#    usb  → USB webcam                    (OpenCV / v4l2)
#
#  Run on your Raspberry Pi:  bash install.sh
# ============================================================
set -e

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Pi Cam Live Stream — Setup Script"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 0. Choose camera type ────────────────────────────────────
echo ""
echo "Select your camera type:"
echo "  1) Raspberry Pi Camera Module 3    [--camera pi]"
echo "  2) Raspberry Pi 5 Camera Module    [--camera pi5]"
echo "  3) USB Webcam (e.g. Logitech)      [--camera usb]"
echo ""
read -rp "Enter choice [1/2/3] (default: 1): " CAM_CHOICE

case "$CAM_CHOICE" in
    2) CAMERA_FLAG="pi5" ;;
    3) CAMERA_FLAG="usb" ;;
    *) CAMERA_FLAG="pi"  ;;
esac

USB_INDEX=0
if [ "$CAMERA_FLAG" = "usb" ]; then
    read -rp "USB device index (default: 0 → /dev/video0): " USB_IDX_INPUT
    USB_INDEX="${USB_IDX_INPUT:-0}"
fi

echo ""
echo "→ Using camera mode: --camera $CAMERA_FLAG"
[ "$CAMERA_FLAG" = "usb" ] && echo "→ USB device index : $USB_INDEX"
echo ""

# ── 1. System deps ──────────────────────────────────────────
echo "[1/5] Updating package list …"
sudo apt-get update -y

echo "[2/5] Installing base dependencies …"
sudo apt-get install -y \
    python3-pip \
    curl

if [ "$CAMERA_FLAG" = "usb" ]; then
    echo "      → USB mode: installing OpenCV (python3-opencv) …"
    sudo apt-get install -y python3-opencv
else
    echo "      → Pi Camera mode: installing picamera2 and libcamera …"
    sudo apt-get install -y \
        python3-picamera2 \
        python3-libcamera \
        python3-kms++
fi

# ── 2. cloudflared ─────────────────────────────────────────
echo "[3/5] Installing cloudflared …"
ARCH=$(dpkg --print-architecture)

if [ "$ARCH" = "arm64" ]; then
    CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb"
else
    CF_URL="https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-armhf.deb"
fi

curl -L "$CF_URL" -o /tmp/cloudflared.deb
sudo dpkg -i /tmp/cloudflared.deb
rm /tmp/cloudflared.deb
echo "cloudflared installed: $(cloudflared --version)"

# ── 3. Copy stream server ──────────────────────────────────
echo "[4/5] Setting up stream server …"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
mkdir -p /opt/picam-stream
cp "$SCRIPT_DIR/stream_server.py" /opt/picam-stream/stream_server.py
chmod +x /opt/picam-stream/stream_server.py

# Build the ExecStart command based on camera choice
if [ "$CAMERA_FLAG" = "usb" ]; then
    EXEC_START="/usr/bin/python3 /opt/picam-stream/stream_server.py --camera usb --usb-index ${USB_INDEX}"
else
    EXEC_START="/usr/bin/python3 /opt/picam-stream/stream_server.py --camera ${CAMERA_FLAG}"
fi

# ── 4. systemd — stream server ─────────────────────────────
echo "[5/5] Creating systemd services …"

sudo tee /etc/systemd/system/picam-stream.service > /dev/null <<EOF
[Unit]
Description=Pi Camera MJPEG Stream Server
After=network.target

[Service]
ExecStart=${EXEC_START}
Restart=always
RestartSec=3
User=pi
Group=pi
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

# ── 5. systemd — cloudflare tunnel ────────────────────────
sudo tee /etc/systemd/system/cloudflare-tunnel.service > /dev/null <<'EOF'
[Unit]
Description=Cloudflare Quick Tunnel for Pi Cam
After=network.target picam-stream.service

[Service]
ExecStart=/usr/local/bin/cloudflared tunnel --url http://localhost:8080
Restart=always
RestartSec=5
User=pi
Group=pi

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable picam-stream.service
sudo systemctl enable cloudflare-tunnel.service
sudo systemctl start picam-stream.service
sudo systemctl start cloudflare-tunnel.service

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅  Setup complete!"
echo ""
echo "  Camera mode : --camera $CAMERA_FLAG"
[ "$CAMERA_FLAG" = "usb" ] && echo "  USB index   : $USB_INDEX  (/dev/video${USB_INDEX})"
echo ""
echo "  Get your tunnel URL by running:"
echo "    sudo journalctl -u cloudflare-tunnel -f"
echo ""
echo "  Look for a line like:"
echo "    https://xxxx-xxxx-xxxx.trycloudflare.com"
echo ""
echo "  Use that URL as NEXT_PUBLIC_STREAM_URL in Vercel."
echo "  Append /stream.mjpg to it."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
