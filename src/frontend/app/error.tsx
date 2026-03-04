'use client';

import { useEffect } from 'react';
import Link from 'next/link';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('Page error:', error);
  }, [error]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-slate-50 dark:bg-slate-900">
      <div className="max-w-md w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 p-8 text-center space-y-4">
        <h1 className="text-xl font-semibold text-slate-800 dark:text-slate-100">
          页面出错了
        </h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          {error.message}
        </p>
        <div className="flex gap-3 justify-center">
          <button
            type="button"
            onClick={() => reset()}
            className="px-4 py-2 rounded-lg bg-slate-800 dark:bg-slate-200 text-white dark:text-slate-800 text-sm font-medium hover:opacity-90"
          >
            重试
          </button>
          <Link
            href="/"
            className="px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 text-sm font-medium hover:bg-slate-100 dark:hover:bg-slate-700"
          >
            返回首页
          </Link>
        </div>
      </div>
    </div>
  );
}
