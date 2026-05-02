'use client';

export default function ChatError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex min-h-[70vh] items-center justify-center p-6">
      <div className="flex flex-col items-center gap-4 text-center">
        <div className="text-4xl">出了点问题</div>
        <p className="max-w-md text-sm text-white/60">
          {error.message || '对话加载遇到了意外错误，请重试。'}
        </p>
        <button
          onClick={reset}
          className="rounded-lg bg-primary-500 px-6 py-2 text-sm font-medium text-white transition hover:bg-primary-600"
        >
          重试
        </button>
      </div>
    </div>
  );
}
