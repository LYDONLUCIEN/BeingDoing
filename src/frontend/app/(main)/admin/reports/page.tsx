'use client';

export default function AdminReportsPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <header>
        <h1 className="text-xl font-semibold mb-2" style={{ color: 'var(--bd-fg)' }}>
          报告概览
        </h1>
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          统计与查看已生成的「四维共鸣」报告，例如报告生成时间、是否被查看、以及按维度拆分的摘要。
        </p>
      </header>

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm">
        <p className="text-xs text-bd-subtle">
          占位说明：后续可以在这里展示报告列表、按激活码或邮箱筛选，并支持预览与导出报告内容。
        </p>
      </section>
    </div>
  );
}

