#!/usr/bin/env python3
"""
Nurture Baby Monitor — Sensor Server
======================================
When run on Raspberry Pi 5 with real sensors:
  → Imports sensor_reader.py to get live hardware readings

When run without sensors (simulation / development):
  → Generates realistic random values within safe thresholds

Endpoints:
  GET  /api/status   → sensor data (JSON)
  GET  /api/image    → JPEG snapshot from USB camera
  POST /api/activate → {"active": true/false} toggle
  GET  /api/info     → server info

Usage on Raspberry Pi 5:
  python3 sensor_server.py --port 5000 --camera-index 0

Usage for simulation only:
  python3 sensor_server.py --port 5000 --simulate
"""

import argparse
import json
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

# ── Try importing real sensor reader (only works on Pi with sensors attached) ─
try:
    import sensor_reader
    REAL_SENSORS = True
    print("[boot] ✓ Real sensors loaded via sensor_reader.py")
except ImportError:
    REAL_SENSORS = False
    print("[boot] ⚠ sensor_reader.py not found — using simulation mode")
except Exception as e:
    REAL_SENSORS = False
    print(f"[boot] ⚠ sensor_reader.py error ({e}) — falling back to simulation")

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# ─── Thresholds / realistic ranges ───────────────────────────────────────────
NORMAL = {
    "body_temp":    (36.1, 37.5),   # MLX90614 object — normal 36.1-37.5°C
    "ambient_temp": (22.0, 26.0),   # MLX90614 ambient
    "room_temp":    (20.0, 28.0),   # BME680
    "humidity":     (40,   65),     # BME680  %
    "pressure":     (1005, 1020),   # BME680  hPa
    "co2_ppm":      (400,  900),    # MH-Z19B  normal (alert > 1000)
    "gas_index":    (50000, 180000),# MQ135 via ADS1115 — safe < 200000
}

ALERT_THRESHOLDS = {
    "body_temp": 38.0,
    "co2_ppm":   1000,
    "gas_index": 200000,
}

# ─── Shared state ─────────────────────────────────────────────────────────────
_state_lock   = threading.Lock()
_active       = False          # ← dormant by default
_last_data    = {}             # most recent sensor snapshot
_camera_index = 0              # USB camera device index


# ─── Camera helpers ──────────────────────────────────────────────────────────

# 1×1 grey JPEG fallback used when OpenCV isn't available
_PLACEHOLDER_JPEG = bytes([
    0xFF,0xD8,0xFF,0xE0,0x00,0x10,0x4A,0x46,0x49,0x46,0x00,0x01,0x01,0x00,0x00,0x01,
    0x00,0x01,0x00,0x00,0xFF,0xDB,0x00,0x43,0x00,0x08,0x06,0x06,0x07,0x06,0x05,0x08,
    0x07,0x07,0x07,0x09,0x09,0x08,0x0A,0x0C,0x14,0x0D,0x0C,0x0B,0x0B,0x0C,0x19,0x12,
    0x13,0x0F,0x14,0x1D,0x1A,0x1F,0x1E,0x1D,0x1A,0x1C,0x1C,0x20,0x24,0x2E,0x27,0x20,
    0x22,0x2C,0x23,0x1C,0x1C,0x28,0x37,0x29,0x2C,0x30,0x31,0x34,0x34,0x34,0x1F,0x27,
    0x39,0x3D,0x38,0x32,0x3C,0x2E,0x33,0x34,0x32,0xFF,0xC0,0x00,0x0B,0x08,0x00,0x01,
    0x00,0x01,0x01,0x01,0x11,0x00,0xFF,0xC4,0x00,0x1F,0x00,0x00,0x01,0x05,0x01,0x01,
    0x01,0x01,0x01,0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x01,0x02,0x03,0x04,
    0x05,0x06,0x07,0x08,0x09,0x0A,0x0B,0xFF,0xDA,0x00,0x08,0x01,0x01,0x00,0x00,0x3F,
    0x00,0xFB,0x00,0xFF,0xD9
])


def capture_frame_jpeg():
    """Capture one frame from the USB camera and return as JPEG bytes.
    Falls back to _PLACEHOLDER_JPEG if capture fails or OpenCV is missing."""
    if not CV2_AVAILABLE:
        return _PLACEHOLDER_JPEG

    cap = cv2.VideoCapture(_camera_index)
    if not cap.isOpened():
        print(f"[camera] Cannot open /dev/video{_camera_index} — using placeholder")
        return _PLACEHOLDER_JPEG

    try:
        ret, frame = cap.read()
        if not ret or frame is None:
            return _PLACEHOLDER_JPEG
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return bytes(buf) if ok else _PLACEHOLDER_JPEG
    except Exception as e:
        print(f"[camera] Frame capture error: {e}")
        return _PLACEHOLDER_JPEG
    finally:
        cap.release()


# ─── Sensor data helpers ─────────────────────────────────────────────────────

def _dormant_data():
    """Returns safe all-zero payload when server is dormant."""
    return {
        "active":       False,
        "body_temp":    0.0,
        "ambient_temp": 0.0,
        "room_temp":    0.0,
        "humidity":     0,
        "pressure":     0.0,
        "co2_ppm":      0,
        "gas_index":    0,
        "mq135_raw":    0,
        "cry_detected": False,
    }


def _generate_reading():
    """Generates one realistic sensor snapshot within safe thresholds.
    Small random chance of elevated values to trigger app alerts."""
    def rf(lo, hi): return round(random.uniform(lo, hi), 2)
    def ri(lo, hi): return random.randint(lo, hi)

    # ~3% chance of cry event  (MAX9814 / ADS1115 A1)
    cry = random.random() < 0.03

    # ~5% chance of elevated CO₂ → triggers alert  (MH-Z19B)
    co2 = ri(1010, 1200) if random.random() < 0.05 else ri(*NORMAL["co2_ppm"])

    # ~2% chance of fever reading  (MLX90614)
    body_temp = rf(38.1, 38.8) if random.random() < 0.02 else rf(*NORMAL["body_temp"])

    gas = ri(*NORMAL["gas_index"])

    return {
        "active":       True,
        "body_temp":    body_temp,
        "ambient_temp": rf(*NORMAL["ambient_temp"]),
        "room_temp":    rf(*NORMAL["room_temp"]),
        "humidity":     ri(*NORMAL["humidity"]),
        "pressure":     rf(*NORMAL["pressure"]),
        "co2_ppm":      co2,
        "gas_index":    gas,
        "mq135_raw":    gas,
        "cry_detected": cry,
    }


def _sensor_loop():
    """Background thread: reads real sensors (or simulates) every 2 seconds when active."""
    global _last_data
    while True:
        with _state_lock:
            is_active = _active
        if is_active:
            if REAL_SENSORS:
                # ── Real hardware readings ───────────────────────────────
                try:
                    data = sensor_reader.read_all()
                except Exception as e:
                    print(f"[sensor] read_all() error: {e}")
                    data = _dormant_data()
                    data["active"] = True
            else:
                # ── Simulation fallback ──────────────────────────────────
                data = _generate_reading()

            with _state_lock:
                _last_data = data

            # ── Auto-buzzer on real Pi: beep on alerts ───────────────
            if REAL_SENSORS:
                try:
                    if (data.get("cry_detected") or
                        data.get("body_temp", 0) > ALERT_THRESHOLDS["body_temp"] or
                        data.get("co2_ppm", 0) > ALERT_THRESHOLDS["co2_ppm"] or
                        data.get("gas_index", 0) >= ALERT_THRESHOLDS["gas_index"]):
                        sensor_reader.buzz(300)
                except Exception:
                    pass

        time.sleep(2)



# ─── HTTP handler ─────────────────────────────────────────────────────────────

class SensorHandler(BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        print(f"[{self.address_string()}] {fmt % args}")

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    # ── GET /api/status ───────────────────────────────────────────────────────
    def _handle_status(self):
        with _state_lock:
            data = dict(_last_data) if _active and _last_data else _dormant_data()
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    # ── GET /api/image — real USB camera frame ────────────────────────────────
    def _handle_image(self):
        """Captures a fresh JPEG from the USB camera (same as stream_server.py).
        Returns placeholder if camera unavailable or server is dormant."""
        with _state_lock:
            is_active = _active

        jpeg = capture_frame_jpeg() if is_active else _PLACEHOLDER_JPEG

        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Content-Length", str(len(jpeg)))
        self.send_header("Cache-Control", "no-cache, no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(jpeg)

    # ── GET /api/info ─────────────────────────────────────────────────────────
    def _handle_info(self):
        with _state_lock:
            info = {
                "server":        "Nurture Sensor Simulation Server",
                "version":       "1.0",
                "active":        _active,
                "camera_index":  _camera_index,
                "camera_opencv": CV2_AVAILABLE,
                "sensors": [
                    "MLX90614 (0x5A) — body & ambient temp",
                    "BME680   (0x76) — room temp, humidity, pressure, VOC",
                    "MH-Z19B  (UART) — CO₂ ppm",
                    "MQ135   (ADS1115 A0) — gas index",
                    "MAX9814 (ADS1115 A1) — cry detection",
                    f"USB Camera /dev/video{_camera_index} — snapshots",
                    "Buzzer GPIO17 — triggered server-side",
                ],
            }
        body = json.dumps(info, indent=2).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    # ── POST /api/activate ────────────────────────────────────────────────────
    def _handle_activate(self):
        global _active, _last_data
        try:
            length   = int(self.headers.get("Content-Length", 0))
            body_raw = self.rfile.read(length)
            payload  = json.loads(body_raw) if body_raw else {}
            activate = bool(payload.get("active", True))
        except Exception:
            activate = True

        with _state_lock:
            _active = activate
            if not activate:
                _last_data = {}

        msg = f"Sensor simulation {'ACTIVATED ▶' if activate else 'DEACTIVATED ⏹'}"
        print(f"[control] {msg}")

        resp = json.dumps({"ok": True, "active": activate, "message": msg}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self._cors()
        self.end_headers()
        self.wfile.write(resp)

    # ── Router ────────────────────────────────────────────────────────────────
    def do_GET(self):
        path = self.path.split("?")[0]
        if   path == "/api/status": self._handle_status()
        elif path == "/api/image":  self._handle_image()
        elif path == "/api/info":   self._handle_info()
        elif path == "/":
            self.send_response(302)
            self.send_header("Location", "/api/info")
            self.end_headers()
        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Not found")

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/activate":
            self._handle_activate()
        else:
            self.send_response(404)
            self.end_headers()


# ─── Entry point ──────────────────────────────────────────────────────────────

def main():
    global _active, _camera_index

    parser = argparse.ArgumentParser(description="Nurture Sensor Simulation Server")
    parser.add_argument("--port",         type=int, default=5000,
                        help="HTTP port (default: 5000)")
    parser.add_argument("--camera-index", type=int, default=0,
                        help="USB camera device index (default: 0 → /dev/video0)")
    parser.add_argument("--start-active", action="store_true",
                        help="Start in ACTIVE mode instead of DORMANT")
    args = parser.parse_args()

    _camera_index = args.camera_index

    if args.start_active:
        _active = True
        print("[boot] ▶  Starting in ACTIVE mode (--start-active flag)")
    else:
        print("[boot] ⏹  Starting in DORMANT mode")
        print("[boot]    To activate:  curl -X POST http://localhost:{}/api/activate -d '{{\"active\":true}}'".format(args.port))

    if CV2_AVAILABLE:
        print(f"[boot] 📷  OpenCV found — /api/image uses USB camera /dev/video{_camera_index}")
    else:
        print("[boot] ⚠️  OpenCV not found — /api/image will return placeholder JPEG")
        print("[boot]    Install with:  pip3 install opencv-python")

    # Start background sensor generation loop
    threading.Thread(target=_sensor_loop, daemon=True).start()

    server = HTTPServer(("0.0.0.0", args.port), SensorHandler)
    print(f"\n[boot] Sensor server → http://0.0.0.0:{args.port}")
    print(f"         GET  /api/status    sensor readings (JSON)")
    print(f"         GET  /api/image     USB camera snapshot (JPEG)")
    print(f"         GET  /api/info      server info")
    print(f"         POST /api/activate  {{\"active\": true|false}}\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[boot] Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
