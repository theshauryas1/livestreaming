#!/bin/bash
# Run anytime after boot to get the current Cloudflare tunnel URLs
echo ""
echo "📡 Sensor API URL:"
journalctl -u nurture-sensor-tunnel --no-pager -n 100 2>/dev/null \
    | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1 \
    || echo "   Service not running. Start with: sudo systemctl start nurture-sensor-tunnel"

echo ""
echo "📷 Camera Stream URL (add /stream.mjpg at the end):"
journalctl -u nurture-stream-tunnel --no-pager -n 100 2>/dev/null \
    | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1 \
    || echo "   Service not running. Start with: sudo systemctl start nurture-stream-tunnel"

echo ""
echo "Status:"
systemctl is-active nurture-sensor       && echo "  ✅ sensor_server   running" || echo "  ❌ sensor_server   stopped"
systemctl is-active nurture-stream       && echo "  ✅ stream_server   running" || echo "  ❌ stream_server   stopped"
systemctl is-active nurture-sensor-tunnel && echo "  ✅ sensor tunnel   running" || echo "  ❌ sensor tunnel   stopped"
systemctl is-active nurture-stream-tunnel && echo "  ✅ stream tunnel   running" || echo "  ❌ stream tunnel   stopped"
echo ""
