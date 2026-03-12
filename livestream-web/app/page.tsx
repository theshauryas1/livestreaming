import StreamPlayer from './components/StreamPlayer';
import { Radio, Github, ExternalLink, Cpu, Wifi } from 'lucide-react';

const STREAM_URL = process.env.NEXT_PUBLIC_STREAM_URL ?? '';
const SITE_TITLE = process.env.NEXT_PUBLIC_SITE_TITLE ?? 'Pi Live Stream';
const CAMERA_TYPE = process.env.NEXT_PUBLIC_CAMERA_TYPE ?? 'pi';

const CAMERA_LABELS: Record<string, string> = {
  pi: 'Camera Module 3',
  pi5: 'Pi 5 Camera',
  usb: 'USB Webcam',
};

export default function Home() {
  return (
    <main className="relative min-h-screen bg-grid overflow-x-hidden z-10">

      {/* ── Radial glow behind stream ─────────────────────────────── */}
      <div
        aria-hidden
        className="pointer-events-none absolute top-0 left-1/2 -translate-x-1/2 w-[900px] h-[500px]
                   rounded-full opacity-20 blur-3xl"
        style={{ background: 'radial-gradient(ellipse, #38bdf8 0%, #818cf8 50%, transparent 75%)' }}
      />

      <div className="relative z-10 max-w-6xl mx-auto px-4 sm:px-6 py-8">

        {/* ══ HEADER ═══════════════════════════════════════════════════════ */}
        <header className="flex items-center justify-between mb-8 fade-in">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl glass glow-accent">
              <Radio size={22} className="text-sky-400" />
            </div>
            <div>
              <h1 className="gradient-text text-xl font-bold leading-tight">
                {SITE_TITLE}
              </h1>
              <p className="text-slate-500 text-xs">Raspberry Pi · {CAMERA_LABELS[CAMERA_TYPE] ?? CAMERA_TYPE}</p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <a
              href="https://github.com"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 transition-colors
                         px-3 py-1.5 rounded-lg glass hover:border-sky-500/30"
            >
              <Github size={13} /> GitHub
            </a>
          </div>
        </header>

        {/* ══ STREAM PLAYER ════════════════════════════════════════════════ */}
        <section className="fade-in" style={{ animationDelay: '100ms' }}>
          <div className="glass p-3 sm:p-4 glow-accent"
            style={{ borderRadius: '20px' }}>
            {STREAM_URL ? (
              <StreamPlayer streamUrl={STREAM_URL} title={SITE_TITLE} />
            ) : (
              <div className="aspect-video flex flex-col items-center justify-center gap-4 rounded-xl bg-black/50">
                <Cpu size={48} className="text-sky-400/40" />
                <div className="text-center">
                  <p className="text-slate-400 font-medium">Stream URL not configured</p>
                  <p className="text-slate-600 text-sm mt-1">
                    Set <code className="text-sky-400 bg-sky-400/10 px-1.5 py-0.5 rounded text-xs">
                      NEXT_PUBLIC_STREAM_URL
                    </code> in your Vercel environment variables.
                  </p>
                </div>
              </div>
            )}
          </div>
        </section>

        {/* ══ INFO CARDS ═══════════════════════════════════════════════════ */}
        <section
          className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-6 fade-in"
          style={{ animationDelay: '200ms' }}
        >
          {[
            { label: 'Camera', value: CAMERA_LABELS[CAMERA_TYPE] ?? CAMERA_TYPE, icon: '📷' },
            { label: 'Protocol', value: 'MJPEG / HTTP', icon: '📡' },
            { label: 'Tunnel', value: 'Cloudflare', icon: '☁️' },
            { label: 'Host', value: 'Vercel', icon: '▲' },
          ].map((item) => (
            <div key={item.label} className="glass px-4 py-3 flex flex-col gap-1">
              <span className="text-lg">{item.icon}</span>
              <span className="text-xs text-slate-500 font-medium uppercase tracking-wider">
                {item.label}
              </span>
              <span className="text-slate-200 font-semibold text-sm">{item.value}</span>
            </div>
          ))}
        </section>

        {/* ══ SETUP CALLOUT ════════════════════════════════════════════════ */}
        {!STREAM_URL && (
          <section className="mt-6 glass p-5 border-sky-500/20 fade-in"
            style={{ animationDelay: '300ms' }}>
            <h2 className="text-sky-400 font-semibold mb-3 flex items-center gap-2">
              <Wifi size={16} /> Quick Setup
            </h2>
            <ol className="space-y-2 text-sm text-slate-400 list-decimal list-inside">
              <li>Copy the <code className="text-slate-300">pi/</code> folder to your Raspberry Pi</li>
              <li>Run <code className="text-sky-400">bash install.sh</code> on the Pi</li>
              <li>
                Get the tunnel URL from{' '}
                <code className="text-slate-300">sudo journalctl -u cloudflare-tunnel -f</code>
              </li>
              <li>
                Add <code className="text-sky-400">NEXT_PUBLIC_STREAM_URL</code> in your{' '}
                <a
                  href="https://vercel.com/dashboard"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-sky-400 hover:text-sky-300 underline underline-offset-2 inline-flex items-center gap-0.5"
                >
                  Vercel dashboard <ExternalLink size={10} />
                </a>{' '}
                and redeploy.
              </li>
            </ol>
          </section>
        )}

        {/* ══ FOOTER ═══════════════════════════════════════════════════════ */}
        <footer className="mt-8 text-center text-slate-600 text-xs fade-in"
          style={{ animationDelay: '400ms' }}>
          Built with ♥ on Raspberry Pi · Deployed on{' '}
          <a
            href="https://vercel.com"
            className="text-slate-500 hover:text-slate-300 transition-colors"
            target="_blank"
            rel="noopener noreferrer"
          >
            Vercel
          </a>
        </footer>

      </div>
    </main>
  );
}
