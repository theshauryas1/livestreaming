'use client';
import { useEffect, useState, useCallback } from 'react';

interface SensorData {
    active: boolean;
    body_temp: number;
    ambient_temp: number;
    room_temp: number;
    humidity: number;
    pressure: number;
    co2_ppm: number;
    gas_index: number;
    cry_detected: boolean;
}

interface HistoryPoint { t: number; value: number; }

const PI_API_URL = process.env.NEXT_PUBLIC_PI_API_URL ?? '';
const MAX_HISTORY = 40;

function clamp(v: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, v)); }

function sparkPath(pts: number[], w: number, h: number): string {
    if (pts.length < 2) return '';
    const lo = Math.min(...pts);
    const hi = Math.max(...pts);
    const range = (hi - lo) || 1;
    const xs = pts.map((_, i) => (i / (pts.length - 1)) * w);
    const ys = pts.map(v => h - ((v - lo) / range) * h * 0.85 - h * 0.075);
    return xs.map((x, i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${ys[i].toFixed(1)}`).join(' ');
}

function SparkLine({ pts, color }: { pts: number[]; color: string }) {
    const w = 120; const h = 36;
    const d = sparkPath(pts, w, h);
    return (
        <svg width={w} height={h} className="opacity-70">
            {d && <path d={d} fill="none" stroke={color} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />}
        </svg>
    );
}

type AlertLevel = 'ok' | 'warn' | 'crit';
function alertColor(level: AlertLevel) {
    return level === 'crit' ? '#ef4444' : level === 'warn' ? '#f59e0b' : '#22d3ee';
}

function SensorCard({
    label, value, unit, pts, color, sub
}: { label: string; value: string; unit: string; pts: number[]; color: string; sub?: string }) {
    return (
        <div className="glass px-4 py-3 flex flex-col gap-1" style={{ borderRadius: 16 }}>
            <span className="text-xs text-slate-500 font-medium uppercase tracking-wider">{label}</span>
            <div className="flex items-end justify-between gap-2">
                <div>
                    <span className="text-slate-100 font-bold text-xl">{value}</span>
                    <span className="text-slate-400 text-xs ml-1">{unit}</span>
                    {sub && <p className="text-slate-600 text-xs mt-0.5">{sub}</p>}
                </div>
                <SparkLine pts={pts} color={color} />
            </div>
        </div>
    );
}

export default function SensorDashboard() {
    const [data, setData] = useState<SensorData | null>(null);
    const [error, setError] = useState('');
    const [history, setHistory] = useState<Record<string, HistoryPoint[]>>({});

    const fetchData = useCallback(async () => {
        if (!PI_API_URL) return;
        try {
            const res = await fetch(`${PI_API_URL}/api/status`, { cache: 'no-store' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const json: SensorData = await res.json();
            setData(json);
            setError('');

            if (json.active) {
                const now = Date.now();
                setHistory(prev => {
                    const add = (key: string, val: number) => {
                        const arr = [...(prev[key] ?? []), { t: now, value: val }];
                        return arr.slice(-MAX_HISTORY);
                    };
                    return {
                        body_temp: add('body_temp', json.body_temp),
                        ambient_temp: add('ambient_temp', json.ambient_temp),
                        room_temp: add('room_temp', json.room_temp),
                        humidity: add('humidity', json.humidity),
                        pressure: add('pressure', json.pressure),
                        co2_ppm: add('co2_ppm', json.co2_ppm),
                        gas_index: add('gas_index', json.gas_index),
                    };
                });
            }
        } catch (e: unknown) {
            setError(e instanceof Error ? e.message : 'Failed to reach Pi');
        }
    }, []);

    useEffect(() => {
        fetchData();
        const id = setInterval(fetchData, 2000);
        return () => clearInterval(id);
    }, [fetchData]);

    const pts = (key: string) => (history[key] ?? []).map(p => p.value);
    const co2Alert: AlertLevel = (data?.co2_ppm ?? 0) > 1500 ? 'crit' : (data?.co2_ppm ?? 0) > 1000 ? 'warn' : 'ok';
    const gasAlert: AlertLevel = (data?.gas_index ?? 0) >= 200000 ? 'crit' : 'ok';
    const bodyAlert: AlertLevel = (data?.body_temp ?? 0) > 38.5 ? 'crit' : (data?.body_temp ?? 0) > 38 ? 'warn' : 'ok';

    if (!PI_API_URL) {
        return (
            <div className="mt-6 glass p-5 border-amber-500/20 text-center" style={{ borderRadius: 16 }}>
                <p className="text-amber-400 font-semibold text-sm">Sensor API not configured</p>
                <p className="text-slate-500 text-xs mt-1">
                    Set <code className="text-sky-400 bg-sky-400/10 px-1 py-0.5 rounded">NEXT_PUBLIC_PI_API_URL</code> to your Cloudflare tunnel URL in Vercel.
                </p>
            </div>
        );
    }

    if (!data) {
        return (
            <div className="mt-6 glass p-5 text-center" style={{ borderRadius: 16 }}>
                <p className="text-slate-400 text-sm animate-pulse">
                    {error ? `⚠ ${error}` : 'Connecting to Raspberry Pi…'}
                </p>
            </div>
        );
    }

    if (!data.active) {
        return (
            <div className="mt-6 glass p-5 border-slate-700/50 text-center" style={{ borderRadius: 16 }}>
                <div className="flex items-center justify-center gap-2 mb-2">
                    <span className="w-2 h-2 rounded-full bg-slate-600 inline-block" />
                    <p className="text-slate-400 font-semibold text-sm">Sensor server is DORMANT</p>
                </div>
                <p className="text-slate-600 text-xs">
                    To activate: <code className="text-sky-400">curl -X POST {PI_API_URL}/api/activate -d '{`{"active":true}`}'</code>
                </p>
            </div>
        );
    }

    return (
        <section className="mt-6 fade-in" style={{ animationDelay: '200ms' }}>
            {/* Header row */}
            <div className="flex items-center justify-between mb-3">
                <h2 className="text-slate-300 font-semibold text-sm uppercase tracking-wider">Live Sensor Readings</h2>
                <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                    <span className="text-emerald-400 text-xs font-medium">ACTIVE</span>
                </div>
            </div>

            {/* Cry / alert banner */}
            {data.cry_detected && (
                <div className="mb-3 glass border-red-500/40 px-4 py-3 flex items-center gap-3" style={{ borderRadius: 12 }}>
                    <span className="text-2xl">🍼</span>
                    <div>
                        <p className="text-red-400 font-bold text-sm">Baby Crying Detected!</p>
                        <p className="text-slate-400 text-xs">MAX9814 microphone via ADS1115 A1</p>
                    </div>
                </div>
            )}

            {/* Sensor grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
                <SensorCard
                    label="Body Temp"
                    value={data.body_temp.toFixed(1)}
                    unit="°C"
                    pts={pts('body_temp')}
                    color={alertColor(bodyAlert)}
                    sub="MLX90614"
                />
                <SensorCard
                    label="Ambient Temp"
                    value={data.ambient_temp.toFixed(1)}
                    unit="°C"
                    pts={pts('ambient_temp')}
                    color="#22d3ee"
                    sub="MLX90614"
                />
                <SensorCard
                    label="Room Temp"
                    value={data.room_temp.toFixed(1)}
                    unit="°C"
                    pts={pts('room_temp')}
                    color="#22d3ee"
                    sub="BME680"
                />
                <SensorCard
                    label="Humidity"
                    value={data.humidity.toString()}
                    unit="%"
                    pts={pts('humidity')}
                    color="#818cf8"
                    sub="BME680"
                />
                <SensorCard
                    label="Pressure"
                    value={data.pressure.toFixed(0)}
                    unit="hPa"
                    pts={pts('pressure')}
                    color="#818cf8"
                    sub="BME680"
                />
                <SensorCard
                    label="CO₂ Level"
                    value={data.co2_ppm.toString()}
                    unit="ppm"
                    pts={pts('co2_ppm')}
                    color={alertColor(co2Alert)}
                    sub="MH-Z19B · alert >1000"
                />
                <SensorCard
                    label="Gas Index"
                    value={data.gas_index > 999 ? `${(data.gas_index / 1000).toFixed(0)}k` : data.gas_index.toString()}
                    unit={data.gas_index > 999 ? '×1k' : ''}
                    pts={pts('gas_index')}
                    color={alertColor(gasAlert)}
                    sub="MQ135 · safe <200k"
                />
                <div className="glass px-4 py-3 flex flex-col gap-1" style={{ borderRadius: 16 }}>
                    <span className="text-xs text-slate-500 font-medium uppercase tracking-wider">Cry Detection</span>
                    <div className="flex flex-col gap-1 mt-1">
                        <span
                            className="font-bold text-xl"
                            style={{ color: data.cry_detected ? '#ef4444' : '#22d3ee' }}
                        >
                            {data.cry_detected ? 'YES' : 'NO'}
                        </span>
                        <span className="text-slate-600 text-xs">MAX9814 · ADS1115 A1</span>
                    </div>
                </div>
            </div>
        </section>
    );
}
