#!/bin/bash
set -e

# Setup Ngrok for Camera Stream (Port 8080)
# This replaces Cloudflare for the camera stream specifically.

# Check running as root
if [ "$EUID" -ne 0 ]; then
  echo "Please run this script with sudo:"
  echo "sudo bash setup_ngrok.sh \"YOUR_AUTH_TOKEN\""
  exit 1
fi

AUTH_TOKEN=$1

if [ -z "$AUTH_TOKEN" ]; then
    echo "ERROR: You forgot your auth token!"
    echo "Usage: sudo bash setup_ngrok.sh \"YOUR_AUTH_TOKEN\""
    echo "Get it from: https://dashboard.ngrok.com/get-started/your-authtoken"
    exit 1
fi

# Detect actual user
ACTUAL_USER=$SUDO_USER
if [ -z "$ACTUAL_USER" ]; then
    ACTUAL_USER=$(logname || echo $USER)
fi

echo "▶ Installing Ngrok..."
# Download and install ngrok
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list >/dev/null
sudo apt update
sudo apt install ngrok

echo "▶ Authenticating Ngrok..."
sudo -u $ACTUAL_USER ngrok config add-authtoken $AUTH_TOKEN

echo "▶ Creating background service for Ngrok (Camera Stream)..."

# Stop existing cloudflare camera tunnel to prevent conflicts (sensor tunnel keeps running)
systemctl stop nurture-stream-tunnel || true
systemctl disable nurture-stream-tunnel || true

# Get path to config
CONFIG_FILE=$(sudo -u $ACTUAL_USER -i eval 'echo $HOME/.config/ngrok/ngrok.yml')

# Create the service pointing to localhost:8080 (the camera port)
cat > /etc/systemd/system/nurture-stream-ngrok.service << EOF
[Unit]
Description=Ngrok Tunnel - Nurture Camera Stream
After=network.target nurture-stream.service

[Service]
ExecStart=/usr/bin/ngrok http 8080 --log=stdout
Restart=always
RestartSec=10
User=$ACTUAL_USER
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable nurture-stream-ngrok
systemctl restart nurture-stream-ngrok

echo ""
echo "✅ Ngrok is successfully installed and running!"
echo "--------------------------------------------------------"
echo "To get your camera stream URL, run this command:"
echo "curl -s localhost:4040/api/tunnels | grep -o 'https://[^"]*'"
echo "(Make sure to add /stream.mjpg to the end in Vercel!)"
echo "--------------------------------------------------------"
