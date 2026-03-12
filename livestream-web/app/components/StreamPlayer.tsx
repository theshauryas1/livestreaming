'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import {
    Maximize2, Minimize2, RefreshCw, Wifi, WifiOff, Camera
} from 'lucide-react';

interface StreamPlayerProps {
    streamUrl: string;
    title?: string;
}

type Status = 'connecting' | 'live' | 'offline' | 'reconnecting';

export default function StreamPlayer({ streamUrl, title = 'Live Stream' }: StreamPlayerProps) {
    const [status, setStatus] = useState<Status>('connecting');
    const [fullscreen, setFullscreen] = useState(false);
    const [retryCount, setRetryCount] = useState(0);
    const [imgKey, setImgKey] = useState(0);           // forces img reload
    const [showControls, setShowControls] = useState(true);

    const imgRef = useRef<HTMLImageElement>(null);
    const wrapRef = useRef<HTMLDivElement>(null);
    const retryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const hideTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
    const MAX_RETRIES = 10;
    const RETRY_DELAY = 4000; // ms

    // ── Stream event handlers ───────────────────────────────────────────────
    const onLoad = useCallback(() => {
        setStatus('live');
        setRetryCount(0);
    }, []);

    const onError = useCallback(() => {
        if (retryTimer.current) clearTimeout(retryTimer.current);
        setRetryCount(prev => {
            const next = prev + 1;
            if (next >= MAX_RETRIES) {
                setStatus('offline');
            } else {
                setStatus('reconnecting');
                retryTimer.current = setTimeout(() => {
                    setImgKey(k => k + 1);
                }, RETRY_DELAY);
            }
            return next;
        });
    }, []);

    const manualRetry = () => {
        setStatus('connecting');
        setRetryCount(0);
        setImgKey(k => k + 1);
    };

    // ── Fullscreen ──────────────────────────────────────────────────────────
    const toggleFullscreen = useCallback(async () => {
        if (!wrapRef.current) return;
        if (!document.fullscreenElement) {
            await wrapRef.current.requestFullscreen();
            setFullscreen(true);
        } else {
            await document.exitFullscreen();
            setFullscreen(false);
        }
    }, []);

    useEffect(() => {
        const onFsChange = () => setFullscreen(!!document.fullscreenElement);
        document.addEventListener('fullscreenchange', onFsChange);
        return () => document.removeEventListener('fullscreenchange', onFsChange);
    }, []);

    // ── Auto-hide controls ──────────────────────────────────────────────────
    const resetHideTimer = useCallback(() => {
        setShowControls(true);
        if (hideTimer.current) clearTimeout(hideTimer.current);
        if (status === 'live') {
            hideTimer.current = setTimeout(() => setShowControls(false), 3000);
        }
    }, [status]);

    useEffect(() => {
        resetHideTimer();
        return () => { if (hideTimer.current) clearTimeout(hideTimer.current); };
    }, [status, resetHideTimer]);

    // ── Cleanup timers ──────────────────────────────────────────────────────
    useEffect(() => () => {
        if (retryTimer.current) clearTimeout(retryTimer.current);
        if (hideTimer.current) clearTimeout(hideTimer.current);
    }, []);

    // ── Derived UI ──────────────────────────────────────────────────────────
    const statusConfig = {
        connecting: { color: 'text-yellow-400', dot: 'bg-yellow-400', label: 'Connecting…' },
        live: { color: 'text-green-400', dot: 'bg-green-400', label: 'LIVE' },
        offline: { color: 'text-red-400', dot: 'bg-red-400', label: 'Offline' },
        reconnecting: { color: 'text-yellow-400', dot: 'bg-yellow-400', label: `Reconnecting (${retryCount}/${MAX_RETRIES})` },
    }[status];

    return (
        <div
            ref={wrapRef}
            className="stream-frame w-full aspect-video select-none"
            onMouseMove={resetHideTimer}
            onTouchStart={resetHideTimer}
            style={{ background: '#000' }}
        >
            {/* Corner decorators */}
            <div className="corner-tl" /><div className="corner-tr" />
            <div className="corner-bl" /><div className="corner-br" />

            {/* ── MJPEG image ── */}
            {status !== 'offline' && (
                <img
                    ref={imgRef}
                    key={imgKey}
                    src={`${streamUrl}?t=${imgKey}`}
                    alt="Pi Camera Live Stream"
                    onLoad={onLoad}
                    onError={onError}
                    className="w-full h-full object-contain"
                    style={{ display: status === 'live' ? 'block' : 'none' }}
                />
            )}

            {/* ── Loading skeleton ── */}
            {(status === 'connecting' || status === 'reconnecting') && (
                <div className="shimmer absolute inset-0 flex flex-col items-center justify-center gap-4">
                    <div className="relative">
                        <Camera size={48} className="text-sky-400 opacity-60" />
                        <div className="absolute -inset-2 border border-sky-400/30 rounded-full animate-ping" />
                    </div>
                    <p className="font-mono text-sm text-sky-400/80">{statusConfig.label}</p>
                </div>
            )}

            {/* ── Offline state ── */}
            {status === 'offline' && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-5 bg-black/80">
                    <WifiOff size={52} className="text-red-400" />
                    <div className="text-center">
                        <p className="text-red-400 font-semibold text-lg">Stream Unavailable</p>
                        <p className="text-slate-500 text-sm mt-1">Check that the Pi is running and the tunnel is active.</p>
                    </div>
                    <button
                        onClick={manualRetry}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg border border-sky-500/40 text-sky-400
                       hover:bg-sky-500/10 transition-all duration-200 text-sm font-medium"
                    >
                        <RefreshCw size={14} /> Try again
                    </button>
                </div>
            )}

            {/* ── HUD overlay ── */}
            <div
                className={`absolute inset-0 transition-opacity duration-500 pointer-events-none
                    ${showControls || status !== 'live' ? 'opacity-100' : 'opacity-0'}`}
            >
                {/* Top bar */}
                <div className="absolute top-0 left-0 right-0 px-4 py-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <span className={`pulse-dot ${statusConfig.dot}`} style={{ color: statusConfig.dot.replace('bg-', '') }} />
                        <span className={`text-xs font-mono font-bold tracking-widest ${statusConfig.color}`}>
                            {statusConfig.label}
                        </span>
                    </div>
                    <div className="text-xs font-mono text-slate-400">
                        {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>
                </div>

                {/* Title badge */}
                <div className="absolute top-3 left-1/2 -translate-x-1/2">
                    <span className="text-xs text-slate-300 font-medium bg-black/40 px-3 py-1 rounded-full backdrop-blur-sm">
                        {title}
                    </span>
                </div>

                {/* Bottom-right controls */}
                <div className="absolute bottom-3 right-3 flex items-center gap-2 pointer-events-auto">
                    {status !== 'offline' && (
                        <button
                            onClick={manualRetry}
                            title="Refresh stream"
                            className="p-2 rounded-lg bg-black/40 backdrop-blur-sm border border-white/10
                         text-slate-300 hover:text-white hover:bg-black/60 transition-all duration-150"
                        >
                            <RefreshCw size={14} />
                        </button>
                    )}
                    <button
                        onClick={toggleFullscreen}
                        title={fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
                        className="p-2 rounded-lg bg-black/40 backdrop-blur-sm border border-white/10
                       text-slate-300 hover:text-white hover:bg-black/60 transition-all duration-150"
                    >
                        {fullscreen ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
                    </button>
                </div>

                {/* Bottom-left wifi icon */}
                <div className="absolute bottom-3 left-3">
                    {status === 'live'
                        ? <Wifi size={16} className="text-green-400 opacity-70" />
                        : <WifiOff size={16} className="text-red-400 opacity-70" />
                    }
                </div>
            </div>
        </div>
    );
}
