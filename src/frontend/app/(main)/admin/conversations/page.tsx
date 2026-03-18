'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  fetchAdminConversations,
  fetchAdminConversationDetail,
  type AdminConversationItem,
} from '@/lib/api/admin';
import MessageContent from '@/components/explore/MessageContent';

export default function AdminConversationsPage() {
  const [items, setItems] = useState<AdminConversationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [stepId, setStepId] = useState('all');
  const [detail, setDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailSessionId, setDetailSessionId] = useState<string>('');
  const [detailOpen, setDetailOpen] = useState(false);

  const loadList = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAdminConversations({
        q: query || undefined,
        step_id: stepId === 'all' ? undefined : stepId,
        page: 1,
        page_size: 200,
      });
      setItems(res.items || []);
    } catch (e: any) {
      setError(e?.message || '加载会话列表失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepId]);

  const stepLabel: Record<string, string> = useMemo(
    () => ({
      values: '价值观',
      strengths: '优势',
      interests: '热忱',
      purpose: '使命',
      rumination: '沉淀',
    }),
    [],
  );

  const openDetail = async (sid: string, rid?: string, step?: string) => {
    setDetailOpen(true);
    setDetailSessionId(sid);
    setDetailLoading(true);
    setDetail(null);
    try {
      const res = await fetchAdminConversationDetail(sid, {
        report_id: rid,
        step_id: step,
      });
      setDetail(res);
    } catch (e: any) {
      // 兜底：接口偶发 404 时不打断页面，保持可继续查看其他会话
      if (e?.response?.status === 404) {
        setDetail({ conversation: { messages: [], metadata: {} } });
        return;
      }
      setError(e?.message || '加载会话详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

  const renderConversationDetail = () => {
    const payload = detail?.conversation ?? detail;
    const source = detail?.source || payload?.source;
    const messages = Array.isArray(payload?.messages) ? payload.messages : [];

    if (source === 'runs' && Array.isArray(payload?.turns)) {
      return (
        <div className="space-y-3">
          {(payload.turns || []).map((turn: any, idx: number) => (
            <div key={`${turn?.log_index ?? idx}`} className="rounded-xl border border-bd-border bg-bd-overlay-md p-3">
              <p className="text-[11px] text-bd-subtle mb-2">log_index: {turn?.log_index ?? idx}</p>
              <pre className="text-[11px] whitespace-pre overflow-x-auto">
                {JSON.stringify(turn?.entry ?? {}, null, 2)}
              </pre>
            </div>
          ))}
        </div>
      );
    }

    if (messages.length === 0) {
      return (
        <pre className="text-[11px] whitespace-pre overflow-x-auto bg-bd-overlay-md rounded-xl p-3 border border-bd-border">
          {JSON.stringify(payload ?? {}, null, 2)}
        </pre>
      );
    }

    return (
      <div className="space-y-3">
        {messages.map((msg: any, idx: number) => {
          const role = String(msg?.role || 'assistant');
          const key = String(msg?.message_id || msg?.id || idx);
          const isUser = role === 'user';
          const title = isUser ? '用户' : role;
          let content = String(msg?.content || '');
          if ((role === 'conclusion_card' || role === 'table') && !content.trim() && msg?.card_payload) {
            content = JSON.stringify(msg.card_payload, null, 2);
          }
          return (
            <div
              key={key}
              className={`rounded-xl border p-3 ${isUser ? 'bg-blue-50 border-blue-200' : 'bg-bd-overlay-md border-bd-border'}`}
            >
              <div className="flex items-center justify-between mb-2">
                <p className="text-[11px] font-medium uppercase tracking-wide">{title}</p>
                <p className="text-[11px] text-bd-subtle">{msg?.created_at || ''}</p>
              </div>
              <MessageContent content={content} markdown className="text-[13px]" colorMode="light" />
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <header>
        <h1 className="text-xl font-semibold mb-2" style={{ color: 'var(--bd-fg)' }}>
          会话记录
        </h1>
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          按 report_id / step_id / session_id / activation_code 筛选并查看会话详情，支撑排查 report → step → session 链路。
        </p>
      </header>

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-4 shadow-sm flex flex-wrap items-center gap-3 text-xs">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="搜索 report_id / session_id / activation_code / user_id"
          className="min-w-[280px] rounded-lg border border-bd-border bg-bd-overlay px-3 py-2"
        />
        <select
          value={stepId}
          onChange={(e) => setStepId(e.target.value)}
          className="rounded-lg border border-bd-border bg-bd-overlay px-3 py-2"
        >
          <option value="all">全部阶段</option>
          <option value="values">values</option>
          <option value="strengths">strengths</option>
          <option value="interests">interests</option>
          <option value="purpose">purpose</option>
          <option value="rumination">rumination</option>
        </select>
        <button
          type="button"
          onClick={loadList}
          className="px-3 py-2 rounded-lg bg-bd-ui-accent text-bd-ui-accent-fg"
        >
          搜索
        </button>
      </section>

      {error && (
        <section className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-xs">
          {error}
        </section>
      )}

      <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm">
        {loading ? (
          <p className="text-xs text-bd-subtle">加载中...</p>
        ) : items.length === 0 ? (
          <p className="text-xs text-bd-subtle">暂无匹配会话。</p>
        ) : (
          <div className="overflow-x-auto -mx-2 pb-1">
            <table className="min-w-[1100px] w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-bd-border text-[11px] text-bd-subtle">
                  <th className="px-2 py-2 text-left font-medium">report_id</th>
                  <th className="px-2 py-2 text-left font-medium">step</th>
                  <th className="px-2 py-2 text-left font-medium">session_id</th>
                  <th className="px-2 py-2 text-left font-medium">activation_code</th>
                  <th className="px-2 py-2 text-left font-medium">user_id</th>
                  <th className="px-2 py-2 text-left font-medium">messages</th>
                  <th className="px-2 py-2 text-left font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => (
                  <tr key={`${item.report_id}-${item.step_id}-${item.session_id}`} className="border-b border-bd-border/60 last:border-0">
                    <td className="px-2 py-2 font-mono text-[11px]">{item.report_id}</td>
                    <td className="px-2 py-2 whitespace-nowrap">
                      <span className="px-2 py-0.5 rounded-full border border-bd-border bg-bd-overlay-md whitespace-nowrap inline-flex items-center">
                        {stepLabel[item.step_id] || item.step_id}
                      </span>
                    </td>
                    <td className="px-2 py-2 font-mono text-[11px]">{item.session_id}</td>
                    <td className="px-2 py-2 font-mono text-[11px]">{item.activation_code}</td>
                    <td className="px-2 py-2 font-mono text-[11px]">{item.user_id}</td>
                    <td className="px-2 py-2">{item.message_count}</td>
                    <td className="px-2 py-2 whitespace-nowrap">
                      <button
                        type="button"
                        onClick={() => openDetail(item.session_id, item.report_id, item.step_id)}
                        className="px-2 py-1 rounded border border-bd-border hover:bg-bd-overlay-md whitespace-nowrap"
                      >
                        查看详情
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {detailOpen && (
        <div
          className="fixed inset-0 z-[120] bg-black/40 backdrop-blur-[1px] flex items-center justify-center p-4"
          onClick={() => setDetailOpen(false)}
        >
          <div
            className="w-full max-w-5xl max-h-[85vh] rounded-2xl bg-bd-card border border-bd-border shadow-2xl flex flex-col overflow-hidden"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="px-5 py-3 border-b border-bd-border flex items-center justify-between">
              <h2 className="text-sm font-medium" style={{ color: 'var(--bd-fg)' }}>
                会话详情 {detailSessionId ? `(${detailSessionId})` : ''}
              </h2>
              <button
                type="button"
                onClick={() => setDetailOpen(false)}
                className="px-2 py-1 text-xs rounded border border-bd-border hover:bg-bd-overlay-md whitespace-nowrap"
              >
                关闭
              </button>
            </div>
            <div className="p-5 overflow-y-auto overflow-x-auto">
              {detailLoading ? (
                <p className="text-xs text-bd-subtle">加载详情中...</p>
              ) : detail ? (
                renderConversationDetail()
              ) : (
                <p className="text-xs text-bd-subtle">请选择一条会话查看详情。</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

