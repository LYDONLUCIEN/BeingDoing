'use client';

import { useEffect } from 'react';
import Link from 'next/link';

export default function MainError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Main layout error:', error);
  }, [error]);

  return (
    <div className="min-h-[60vh] flex flex-col items-center justify-center p-6">
      <div className="max-w-md w-full rounded-xl border border-slate-200 bg-white p-8 text-center space-y-4 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-800">页面出错了</h1>
        <p className="text-sm text-slate-600">{error.message}</p>
        <div className="flex gap-3 justify-center">
          <button
            type="button"
            onClick={() => reset()}
            className="px-4 py-2 rounded-lg bg-slate-800 text-white text-sm font-medium hover:opacity-90"
          >
            重试
          </button>
          <Link
            href="/"
            className="px-4 py-2 rounded-lg border border-slate-300 text-slate-700 text-sm font-medium hover:bg-slate-100"
          >
            返回首页
          </Link>
        </div>
      </div>
    </div>
  );
}
