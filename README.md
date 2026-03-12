# Pi Cam Live Stream 🎥

A live streaming website built with **Next.js 14** and deployed on **Vercel**, receiving an MJPEG video stream from a **Raspberry Pi Camera Module 3** over a **Cloudflare Tunnel**.

## Architecture

```
Pi Camera Module 3
    ↓ (picamera2)
Python MJPEG Server (port 8080)
    ↓ (Cloudflare Quick Tunnel — free)
https://xxxx.trycloudflare.com/stream.mjpg
    ↓
Next.js Website on Vercel
    ↓
Viewer's browser
```

---

## 1 · Set Up the Raspberry Pi

See **[pi/README.md](./pi/README.md)** for full instructions.

**Quick version:**

```bash
# On your Raspberry Pi
git clone <your-repo-url>
cd pi
bash install.sh
```

Then get your public URL:
```bash
sudo journalctl -u cloudflare-tunnel -f
# Look for: https://xxxx.trycloudflare.com
```

Your stream URL is: `https://xxxx.trycloudflare.com/stream.mjpg`

---

## 2 · Deploy to Vercel via GitHub

### 2a. Push to GitHub

```bash
# From the project root
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

### 2b. Import in Vercel

1. Go to [vercel.com/new](https://vercel.com/new)
2. Click **"Import Git Repository"** → select your repo
3. Set **Root Directory** to `livestream-web`
4. Add **Environment Variable**:
   - Key: `NEXT_PUBLIC_STREAM_URL`
   - Value: `https://xxxx.trycloudflare.com/stream.mjpg`
5. Click **Deploy** ✅

---

## 3 · Run Locally (Dev)

```bash
cd livestream-web
cp .env.example .env.local
# Edit .env.local and set NEXT_PUBLIC_STREAM_URL

npm install
npm run dev
# Open http://localhost:3000
```

---

## Project Structure

```
/
├── pi/
│   ├── stream_server.py    ← MJPEG server for Raspberry Pi
│   ├── install.sh          ← Pi setup & systemd installer
│   └── README.md           ← Pi-side setup guide
│
└── livestream-web/         ← Next.js website (deploy this to Vercel)
    ├── app/
    │   ├── page.tsx            ← Main homepage
    │   ├── layout.tsx          ← Root layout
    │   ├── globals.css         ← Global styles & animations
    │   ├── components/
    │   │   └── StreamPlayer.tsx ← MJPEG player w/ auto-reconnect
    │   └── api/health/
    │       └── route.ts        ← Health check endpoint
    ├── vercel.json
    └── .env.example
```

---

## Environment Variables

| Variable | Description | Example |
|---|---|---|
| `NEXT_PUBLIC_STREAM_URL` | Full URL to the Pi's MJPEG stream | `https://xxxx.trycloudflare.com/stream.mjpg` |
| `NEXT_PUBLIC_SITE_TITLE` | Browser tab title *(optional)* | `My Pi Cam` |

---

## Troubleshooting

| Problem | Solution |
|---|---|
| White/blank stream box | Stream URL not set or tunnel not running |
| "Stream Unavailable" | Pi stream_server.py is not running — check `systemctl status picam-stream` |
| Tunnel URL expired | `trycloudflare.com` URLs reset on restart. Update the env var and redeploy. |
| Choppy video | Reduce `WIDTH`/`HEIGHT` in `stream_server.py` (try 640×480) |
