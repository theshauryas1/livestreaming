#!/bin/bash
echo ""
echo "=== Your Nurture App URLs ==="
echo ""

# 1. Get Cloudflare Sensor URL (Port 5000)
CF_SENSOR_URL=$(sudo journalctl -u nurture-sensor-tunnel -n 50 --no-pager | grep -o 'https://[a-zA-Z0-9-]*\.trycloudflare\.com' | tail -n 1)

if [ -n "$CF_SENSOR_URL" ]; then
    echo "🌡️ Sensor API URL:"
    echo "   $CF_SENSOR_URL"
else
    echo "🌡️ Sensor API URL: [Not Found or Still Starting - Run script again in 5s]"
fi

echo ""

# 2. Get Ngrok Camera URL (Port 8080)
# Ngrok provides a local API on port 4040 to get the active public URL
NGROK_STREAM_URL=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | grep -o '"public_url":"https://[^"]*"' | cut -d'"' -f4)

if [ -n "$NGROK_STREAM_URL" ]; then
    echo "📷 Camera Stream URL (paste into Vercel exact as shown below):"
    echo "   $NGROK_STREAM_URL/stream.mjpg"
else
    echo "📷 Camera Stream URL: [Not Found or Ngrok Offline]"
    echo "   Check status with 'sudo systemctl status nurture-stream-ngrok'"
fi
echo ""
echo "============================="
echo ""
