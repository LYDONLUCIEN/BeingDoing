'use client';

export default function AdminDashboardPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-8">
      <header>
        <p className="text-xs uppercase tracking-[0.2em] text-bd-subtle mb-2">Admin</p>
        <h1 className="text-2xl font-semibold mb-2" style={{ color: 'var(--bd-fg)' }}>
          总览 Dashboard
        </h1>
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          一眼查看激活码、探索进度、报告生成与 Token 消耗的核心数据。后续可以在这里接入图表与趋势分析。
        </p>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-2xl bg-bd-card border border-bd-border px-5 py-4 shadow-sm">
          <p className="text-xs text-bd-subtle mb-1">今日新激活码</p>
          <p className="text-2xl font-semibold" style={{ color: 'var(--bd-fg)' }}>—</p>
        </div>
        <div className="rounded-2xl bg-bd-card border border-bd-border px-5 py-4 shadow-sm">
          <p className="text-xs text-bd-subtle mb-1">完成全部四维探索</p>
          <p className="text-2xl font-semibold" style={{ color: 'var(--bd-fg)' }}>—</p>
        </div>
        <div className="rounded-2xl bg-bd-card border border-bd-border px-5 py-4 shadow-sm">
          <p className="text-xs text-bd-subtle mb-1">已生成报告数</p>
          <p className="text-2xl font-semibold" style={{ color: 'var(--bd-fg)' }}>—</p>
        </div>
        <div className="rounded-2xl bg-bd-card border border-bd-border px-5 py-4 shadow-sm">
          <p className="text-xs text-bd-subtle mb-1">近 7 日 Token</p>
          <p className="text-2xl font-semibold" style={{ color: 'var(--bd-fg)' }}>—</p>
        </div>
      </section>

      <section className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm">
          <h2 className="text-sm font-medium mb-2" style={{ color: 'var(--bd-fg)' }}>
            探索阶段完成率（占位）
          </h2>
          <p className="text-xs text-bd-subtle">
            这里可以接入各阶段（信念 / 禀赋 / 热忱 / 使命）的完成率、漏斗等图表。
          </p>
        </div>
        <div className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm">
          <h2 className="text-sm font-medium mb-2" style={{ color: 'var(--bd-fg)' }}>
            使用趋势（占位）
          </h2>
          <p className="text-xs text-bd-subtle">
            这里可以展示按天的激活数、活跃会话数与报告生成趋势。
          </p>
        </div>
      </section>
    </div>
  );
}

