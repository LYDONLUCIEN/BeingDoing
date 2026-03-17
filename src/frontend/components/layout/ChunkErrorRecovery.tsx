'use client';

import { useEffect } from 'react';

const RELOAD_GUARD_KEY = 'bd-chunk-reload-ts';
const RELOAD_GUARD_MS = 30_000;

function isChunkLoadFailure(message: string): boolean {
  if (!message) return false;
  return (
    message.includes('ChunkLoadError') ||
    message.includes('Loading chunk') ||
    message.includes('Failed to fetch dynamically imported module') ||
    (message.includes('/_next/static/chunks') && message.includes('failed'))
  );
}

function reloadOnceForChunkFailure() {
  try {
    const now = Date.now();
    const previous = Number(sessionStorage.getItem(RELOAD_GUARD_KEY) || '0');
    if (now - previous < RELOAD_GUARD_MS) return;

    sessionStorage.setItem(RELOAD_GUARD_KEY, String(now));
    const url = new URL(window.location.href);
    url.searchParams.set('_r', String(now));
    window.location.replace(url.toString());
  } catch {
    window.location.reload();
  }
}

export default function ChunkErrorRecovery() {
  useEffect(() => {
    const onError = (event: ErrorEvent) => {
      const message = String(event?.message || event?.error?.message || '');
      if (isChunkLoadFailure(message)) {
        reloadOnceForChunkFailure();
      }
    };

    const onUnhandledRejection = (event: PromiseRejectionEvent) => {
      const reason = event?.reason;
      const message = String(reason?.message || reason || '');
      if (isChunkLoadFailure(message)) {
        reloadOnceForChunkFailure();
      }
    };

    window.addEventListener('error', onError);
    window.addEventListener('unhandledrejection', onUnhandledRejection);
    return () => {
      window.removeEventListener('error', onError);
      window.removeEventListener('unhandledrejection', onUnhandledRejection);
    };
  }, []);

  return null;
}
