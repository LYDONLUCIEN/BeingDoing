'use client';

/**
 * 根布局错误边界，捕获 layout 或更上层的错误。
 * 必须渲染自己的 html/body。
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="zh-CN">
      <body style={{ margin: 0, fontFamily: 'system-ui', minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#f8fafc' }}>
        <div style={{ maxWidth: 400, padding: 24, textAlign: 'center' }}>
          <h1 style={{ fontSize: 18, marginBottom: 8 }}>应用出错了</h1>
          <p style={{ fontSize: 14, color: '#64748b', marginBottom: 16 }}>{error.message}</p>
          <button
            type="button"
            onClick={() => reset()}
            style={{ padding: '8px 16px', borderRadius: 8, background: '#0f172a', color: '#fff', border: 'none', cursor: 'pointer' }}
          >
            重试
          </button>
        </div>
      </body>
    </html>
  );
}
