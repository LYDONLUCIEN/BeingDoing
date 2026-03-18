'use client';

export default function AdminConversationsPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <header>
        <h1 className="text-xl font-semibold mb-2" style={{ color: 'var(--bd-fg)' }}>
          对话与阶段
        </h1>
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          这里可以按 activation_code / session_id / 阶段（信念 / 禀赋 / 热忱 / 使命）查看 simple-chat 的历史对话，并跳转到某个会话详情。
        </p>
      </header>

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm">
        <p className="text-xs text-bd-subtle">
          占位说明：后续可调用 <code className="px-1 py-0.5 rounded bg-bd-overlay-md">/api/v1/admin/analytics/chat-records</code>{' '}
          与 <code className="px-1 py-0.5 rounded bg-bd-overlay-md">/api/v1/admin/analytics/session-detail</code> 来构建列表与详情视图。
        </p>
      </section>
    </div>
  );
}

