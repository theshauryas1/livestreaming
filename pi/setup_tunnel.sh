#!/bin/bash
# ============================================================
# Nurture Baby Monitor — Permanent Cloudflare Tunnel Setup
# Run this ONCE on your Pi after logging into Cloudflare
# ============================================================

set -e

echo "================================================"
echo "  Nurture Pi — Permanent Cloudflare Tunnel Setup"
echo "================================================"

# ── Step 1: Login to Cloudflare (opens browser on Pi) ────────────────────────
echo ""
echo "[1/5] Login to Cloudflare..."
echo "      A browser will open (or copy the URL to your laptop browser)"
cloudflared tunnel login

# ── Step 2: Create the named tunnel ──────────────────────────────────────────
echo ""
echo "[2/5] Creating tunnel 'nurture-pi'..."
cloudflared tunnel create nurture-pi

# ── Step 3: Write config.yml ──────────────────────────────────────────────────
echo ""
echo "[3/5] Writing tunnel config..."

# Get the tunnel ID from the JSON credential file
CRED_FILE=$(ls ~/.cloudflared/*.json 2>/dev/null | grep -v cert | head -1)
TUNNEL_ID=$(basename "$CRED_FILE" .json)
echo "      Tunnel ID: $TUNNEL_ID"

cat > ~/.cloudflared/config.yml << EOF
tunnel: $TUNNEL_ID
credentials-file: $CRED_FILE

ingress:
  - hostname: sensor.REPLACE_WITH_YOUR_DOMAIN.com
    service: http://localhost:5000
  - hostname: stream.REPLACE_WITH_YOUR_DOMAIN.com
    service: http://localhost:8080
  - service: http_status:404
EOF

echo ""
echo "⚠️  EDIT the hostnames in ~/.cloudflared/config.yml"
echo "   Replace 'REPLACE_WITH_YOUR_DOMAIN.com' with your actual domain"
echo ""
read -p "Press Enter after editing config.yml to continue..."

# ── Step 4: Create DNS routes ─────────────────────────────────────────────────
echo ""
echo "[4/5] Creating DNS routes (your domain must be on Cloudflare)..."
cloudflared tunnel route dns nurture-pi sensor.$(grep "sensor\." ~/.cloudflared/config.yml | awk '{print $2}')
cloudflared tunnel route dns nurture-pi stream.$(grep "stream\." ~/.cloudflared/config.yml | awk '{print $2}')

# ── Step 5: Install as systemd service ────────────────────────────────────────
echo ""
echo "[5/5] Installing cloudflared as a system service..."
sudo cloudflared service install

echo ""
echo "✅ Done! Tunnel is now a system service."
echo "   It will auto-start on every Pi boot."
echo ""
echo "Your permanent URLs:"
echo "   Sensor API:  https://sensor.YOUR_DOMAIN.com"
echo "   Camera:      https://stream.YOUR_DOMAIN.com/stream.mjpg"
echo ""
echo "Update these in:"
echo "   Vercel → NEXT_PUBLIC_PI_API_URL  = https://sensor.YOUR_DOMAIN.com"
echo "   Vercel → NEXT_PUBLIC_STREAM_URL  = https://stream.YOUR_DOMAIN.com/stream.mjpg"
echo "   App Settings → Pi Server URL     = https://sensor.YOUR_DOMAIN.com"
echo "   App Settings → Camera Stream URL = https://stream.YOUR_DOMAIN.com/stream.mjpg"
