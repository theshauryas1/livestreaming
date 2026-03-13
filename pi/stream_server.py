#!/usr/bin/env python3
"""
Raspberry Pi MJPEG Stream Server
Supports three camera backends:
  --camera pi       Raspberry Pi Camera Module 3  (default, uses picamera2)
  --camera pi5      Raspberry Pi 5 Camera Module  (uses picamera2 with Pi 5 tuning)
  --camera usb      USB webcam                    (uses OpenCV / v4l2)

Stream URL: http://<pi-ip>:8080/stream.mjpg
"""

import io
import sys
import time
import logging
import argparse
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

# ─── Configuration ────────────────────────────────────────────────────────────
PORT        = 8080
WIDTH       = 1280
HEIGHT      = 720
FRAMERATE   = 30
STREAM_PATH = "/stream.mjpg"
# ──────────────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


# ─── Shared frame buffer ───────────────────────────────────────────────────────
class StreamingOutput(io.BufferedIOBase):
    """Thread-safe buffer that holds the latest MJPEG frame."""

    def __init__(self):
        self.frame = None
        self.condition = threading.Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


# ─── HTTP handler ──────────────────────────────────────────────────────────────
class StreamingHandler(BaseHTTPRequestHandler):
    """Serves the MJPEG stream and a simple health endpoint."""

    def log_message(self, format, *args):
        if args and str(args[1]) not in ("200",):
            log.info(f"{self.client_address[0]} - {format % args}")

    def do_GET(self):
        # Strip query parameters for routing
        path_only = self.path.split("?", 1)[0]

        if path_only == "/":
            self.send_response(301)
            self.send_header("Location", STREAM_PATH)
            self._cors_headers()
            self.end_headers()

        elif path_only == "/health":
            payload = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self._cors_headers()
            self.end_headers()
            self.wfile.write(payload)

        elif path_only == STREAM_PATH:
            self.send_response(200)
            self.send_header("Age", "0")
            self.send_header("Cache-Control", "no-cache, private")
            self.send_header("Pragma", "no-cache")
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
            self._cors_headers()
            self.end_headers()
            try:
                while True:
                    with output.condition:
                        output.condition.wait()
                        frame = output.frame
                    self.wfile.write(b"--FRAME\r\n")
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(frame)))
                    self.end_headers()
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
            except Exception as e:
                log.debug(f"Client disconnected: {self.client_address} — {e}")
        else:
            self.send_error(404)
            self.end_headers()

    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")


class StreamingServer(HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


# ─── Camera backends ───────────────────────────────────────────────────────────

def start_usb_libcamera(camera_index: int = 1):
    """
    Stream USB webcam using libcamera-vid subprocess (MJPEG passthrough).
    No OpenCV or picamera2 encoder needed — reads raw MJPEG bytes from stdout.
    camera_index: 0 = Pi Camera Module, 1 = first USB camera (libcamera ordering)
    """
    import subprocess, threading, shutil

    log.info(f"Starting USB camera via libcamera-vid (camera index {camera_index}) …")

    # Bookworm uses rpicam-vid; Bullseye uses libcamera-vid
    cmd_name = "rpicam-vid" if shutil.which("rpicam-vid") else "libcamera-vid"

    cmd = [
        cmd_name,
        "--camera", str(camera_index),
        "-t", "0",
        "--width",  str(WIDTH),
        "--height", str(HEIGHT),
        "--framerate", str(FRAMERATE),
        "--codec", "mjpeg",
        "--inline",
        "-o", "-",
        "--nopreview",
    ]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    log.info(f"USB Camera stream started — {WIDTH}x{HEIGHT} @ {FRAMERATE} fps")

    def _pipe_frames():
        buf = b""
        SOI = b"\xff\xd8"   # JPEG start marker
        EOI = b"\xff\xd9"   # JPEG end marker
        while True:
            chunk = proc.stdout.read(65536)
            if not chunk:
                break
            buf += chunk
            while True:
                start = buf.find(SOI)
                end   = buf.find(EOI, start + 2) if start != -1 else -1
                if start == -1 or end == -1:
                    break
                jpeg = buf[start : end + 2]
                output.write(jpeg)
                buf = buf[end + 2:]

    t = threading.Thread(target=_pipe_frames, daemon=True)
    t.start()
    return proc


def start_picamera2(pi5_mode: bool = False):
    """Start streaming using picamera2 (Pi Camera Module 2/3)."""
    from picamera2 import Picamera2
    from picamera2.encoders import MJPEGEncoder
    from picamera2.outputs import FileOutput

    label = "Pi 5 Camera" if pi5_mode else "Camera Module 3"
    log.info(f"Initialising {label} via picamera2 …")

    picam2 = Picamera2()
    controls = {"FrameRate": FRAMERATE}
    controls.update({"AfMode": 2, "AfSpeed": 1})

    video_config = picam2.create_video_configuration(
        main={"size": (WIDTH, HEIGHT), "format": "RGB888"},
        controls=controls,
    )
    # Strip unsupported controls
    supported = set(picam2.camera_controls.keys())
    video_config["controls"] = {
        k: v for k, v in video_config.get("controls", {}).items()
        if k in supported
    }
    picam2.configure(video_config)
    picam2.start_recording(MJPEGEncoder(), FileOutput(output))
    log.info(f"{label} started — {WIDTH}x{HEIGHT} @ {FRAMERATE} fps")
    return picam2


    """Start streaming from a USB webcam using OpenCV in a background thread."""
    try:
        import cv2
    except ImportError:
        log.error("OpenCV not found. Install it: sudo apt-get install -y python3-opencv")
        sys.exit(1)

    cap = cv2.VideoCapture(device_index)
    if not cap.isOpened():
        log.error(f"Cannot open USB camera at /dev/video{device_index}. "
                  "Check the device is connected and try --usb-index <N>.")
        sys.exit(1)

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, HEIGHT)
    cap.set(cv2.CAP_PROP_FPS, FRAMERATE)

    actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    actual_fps = cap.get(cv2.CAP_PROP_FPS)
    log.info(f"USB camera opened — {actual_w}x{actual_h} @ {actual_fps:.0f} fps "
             f"(device /dev/video{device_index})")

    encode_params = [cv2.IMWRITE_JPEG_QUALITY, 85]

    def capture_loop():
        while True:
            ret, frame = cap.read()
            if not ret:
                log.warning("USB camera frame capture failed — retrying …")
                time.sleep(0.1)
                continue
            ok, buf = cv2.imencode(".jpg", frame, encode_params)
            if ok:
                output.write(buf.tobytes())

    t = threading.Thread(target=capture_loop, daemon=True)
    t.start()
    log.info("USB camera capture thread running.")
    return cap


# ─── Entry point ───────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(
        description="Raspberry Pi MJPEG Stream Server"
    )
    parser.add_argument(
        "--camera",
        choices=["pi", "pi5", "usb"],
        default="pi",
        help=(
            "Camera backend to use: "
            "'pi' = Camera Module 3 (default), "
            "'pi5' = Raspberry Pi 5 Camera Module, "
            "'usb' = USB webcam via OpenCV"
        ),
    )
    parser.add_argument(
        "--usb-index",
        type=int,
        default=0,
        metavar="N",
        help="USB camera device index (default: 0 → /dev/video0). Only used with --camera usb.",
    )
    parser.add_argument(
        "--width",  type=int, default=WIDTH,     help=f"Frame width  (default: {WIDTH})")
    parser.add_argument(
        "--height", type=int, default=HEIGHT,    help=f"Frame height (default: {HEIGHT})")
    parser.add_argument(
        "--fps",    type=int, default=FRAMERATE, help=f"Frame rate   (default: {FRAMERATE})")
    parser.add_argument(
        "--port",   type=int, default=PORT,      help=f"HTTP port    (default: {PORT})")
    return parser.parse_args()


def main():
    global output, WIDTH, HEIGHT, FRAMERATE, PORT, STREAM_PATH

    args = parse_args()
    WIDTH     = args.width
    HEIGHT    = args.height
    FRAMERATE = args.fps
    PORT      = args.port

    output = StreamingOutput()

    camera_resource = None

    if args.camera == "usb":
        # USB UVC webcam — libcamera-vid native MJPEG passthrough (no OpenCV needed)
        camera_resource = start_usb_libcamera(camera_index=args.usb_index + 1)
    elif args.camera == "pi5":
        camera_resource = start_picamera2(pi5_mode=True)
    else:
        camera_resource = start_picamera2(pi5_mode=False)

    try:
        address = ("", PORT)
        httpd = StreamingServer(address, StreamingHandler)
        log.info(f"Stream live at http://0.0.0.0:{PORT}{STREAM_PATH}")
        log.info(f"Camera mode : --camera {args.camera}")
        log.info("Press Ctrl+C to stop.")
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("Shutting down …")
    finally:
        try:
            if hasattr(camera_resource, "stop_recording"):
                camera_resource.stop_recording()
                camera_resource.close()
            elif hasattr(camera_resource, "terminate"):
                camera_resource.terminate()
            elif hasattr(camera_resource, "release"):
                camera_resource.release()
        except Exception:
            pass
        log.info("Camera closed.")


if __name__ == "__main__":
    main()
