# Raspberry Pi Camera — Setup Guide

## Supported Camera Inputs

| Mode | Flag | Hardware |
|------|------|----------|
| `pi`  | `--camera pi`  | Raspberry Pi Camera Module 3 (CSI) |
| `pi5` | `--camera pi5` | Raspberry Pi 5 Camera Module (CSI) |
| `usb` | `--camera usb` | Any USB webcam (Logitech, etc.)    |

---

## Requirements

- Raspberry Pi 3B+ / 4 / **5**
- One of the supported cameras above
- Raspberry Pi OS (Bookworm recommended, 64-bit)
- Internet connection on the Pi

---

## Step 1 — Enable the Camera (CSI cameras only)

> **Skip this step if you are using a USB webcam.**

```bash
sudo raspi-config
# Interface Options → Camera → Enable
# Reboot when prompted
sudo reboot
```

After reboot, verify the camera is detected:
```bash
libcamera-hello --list-cameras
# Should show: Camera Module 3  (or Pi 5 Camera)
```

---

## Step 2 — Run the Installer

Copy the `pi/` folder to your Raspberry Pi, then:

```bash
chmod +x install.sh
bash install.sh
```

The installer will **ask you to choose your camera type** (1 = Module 3, 2 = Pi 5, 3 = USB) and then:

- Install only the required packages (`picamera2` OR `python3-opencv`)
- Install `cloudflared`
- Create two systemd services that start on boot:
  - `picam-stream` — MJPEG HTTP server on port 8080
  - `cloudflare-tunnel` — exposes port 8080 to the internet

---

## Manual / CLI Usage

You can also run the server directly without the installer:

```bash
# Raspberry Pi Camera Module 3
python3 stream_server.py --camera pi

# Raspberry Pi 5 Camera Module
python3 stream_server.py --camera pi5

# USB Webcam (first device)
python3 stream_server.py --camera usb

# USB Webcam on /dev/video1
python3 stream_server.py --camera usb --usb-index 1

# Custom resolution / framerate
python3 stream_server.py --camera usb --width 1920 --height 1080 --fps 30

# Change the HTTP port
python3 stream_server.py --camera pi --port 9090
```

All options:

| Option | Default | Description |
|--------|---------|-------------|
| `--camera` | `pi` | `pi`, `pi5`, or `usb` |
| `--usb-index` | `0` | USB device index (`/dev/videoN`) |
| `--width` | `1280` | Frame width in pixels |
| `--height` | `720` | Frame height in pixels |
| `--fps` | `30` | Target frame rate |
| `--port` | `8080` | HTTP server port |

---

## Step 3 — Get Your Public Tunnel URL

```bash
sudo journalctl -u cloudflare-tunnel -f
```

Look for a line like:
```
https://abc-def-ghi-jkl.trycloudflare.com
```

Your **stream URL** is:
```
https://abc-def-ghi-jkl.trycloudflare.com/stream.mjpg
```

> ⚠️ **Note**: Free `trycloudflare.com` URLs change every tunnel restart. Create a free Cloudflare account and use a Named Tunnel for a permanent URL.

---

## Step 4 — Configure Vercel

In your Vercel dashboard, set these environment variables:

| Variable | Example value |
|----------|--------------|
| `NEXT_PUBLIC_STREAM_URL` | `https://xxxx.trycloudflare.com/stream.mjpg` |
| `NEXT_PUBLIC_CAMERA_TYPE` | `pi` \| `pi5` \| `usb` |

Then **redeploy** the frontend. The website will display the correct camera label automatically.

---

## Step 5 — Test the Stream Locally

On any device on the same Wi-Fi:
```
http://<pi-ip-address>:8080/stream.mjpg
```

---

## Service Commands

```bash
# Check status
sudo systemctl status picam-stream
sudo systemctl status cloudflare-tunnel

# View logs
sudo journalctl -u picam-stream -f
sudo journalctl -u cloudflare-tunnel -f

# Restart
sudo systemctl restart picam-stream
sudo systemctl restart cloudflare-tunnel
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| CSI camera not found | Run `sudo raspi-config` → enable camera; reboot |
| USB camera not found | Check `ls /dev/video*`; try `--usb-index 1` |
| `No module named cv2` | `sudo apt-get install python3-opencv` |
| Port 8080 busy | Pass `--port 9090` and update the cloudflare service |
| Low framerate | Reduce `--width` / `--height`, or lower `--fps` |
| Tunnel URL keeps changing | Use a Cloudflare Named Tunnel for a permanent URL |
