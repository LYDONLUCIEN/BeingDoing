'use client';

export default function AdminAnalyticsPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <header>
        <h1 className="text-xl font-semibold mb-2" style={{ color: 'var(--bd-fg)' }}>
          埋点与 Token 统计
        </h1>
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          这里将聚合 simple-chat 与报告生成过程中的关键埋点数据，用于分析 Token 消耗、调用次数与性能表现。
        </p>
      </header>

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm">
        <p className="text-xs text-bd-subtle">
          占位说明：后续可调用 <code className="px-1 py-0.5 rounded bg-bd-overlay-md">/api/v1/admin/analytics</code> 等接口，绘制 Token / 调用量 / 错误率趋势图。
        </p>
      </section>
    </div>
  );
}

