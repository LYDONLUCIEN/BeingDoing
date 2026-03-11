'use client';

import { useState, useEffect } from 'react';
import { getChatRecords, getSessionDetail, type ChatRecord, type SessionDetailRuns, type SessionDetailSimple } from '@/lib/api/admin';
import { Loader2, ChevronLeft, ChevronRight, FileText, X, Copy } from 'lucide-react';
import FlowAiMessage from '@/components/explore/FlowAiMessage';
import { copyToClipboard } from '@/lib/utils/clipboard';

const JSON_PREVIEW_STYLE = { background: '#f8fafc', color: '#1e293b', border: '1px solid #e2e8f0' };

function dimToPhase(dim: string): 'values' | 'strength' | 'interest' | 'purpose' {
  if (dim.includes('values')) return 'values';
  if (dim.includes('strengths')) return 'strength';
  if (dim.includes('interests')) return 'interest';
  return 'purpose';
}

function extractResponseFromLogs(logs: unknown): string {
  if (!Array.isArray(logs) || logs.length === 0) return '';
  const lastDone = [...logs].reverse().find((e: unknown) => (e as Record<string, unknown>)?.done === true);
  return (lastDone as Record<string, unknown>)?.message as string || '';
}

const DIMENSION_LABELS: { [k: string]: string } = {
  values_exploration: '信念',
  strengths_exploration: '禀赋',
  interests_exploration: '热忱',
  combination: '组合',
  refinement: '精炼',
  values: '信念',
  strengths: '禀赋',
  interests: '热忱',
  purpose: '使命',
};

export default function ChatRecordsTable() {
  const [records, setRecords] = useState<ChatRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(30);
  const [loading, setLoading] = useState(false);
  const [detailSessionId, setDetailSessionId] = useState<string | null>(null);
  const [detailRecord, setDetailRecord] = useState<ChatRecord | null>(null);
  const [detailData, setDetailData] = useState<SessionDetailRuns | SessionDetailSimple | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [dimensionFilter, setDimensionFilter] = useState('');
  const [sessionIdFilter, setSessionIdFilter] = useState('');

  const loadRecords = async (p?: number) => {
    setLoading(true);
    try {
      const res = await getChatRecords({
        page: p !== undefined ? p : page,
        page_size: pageSize,
        dimension: dimensionFilter || undefined,
        session_id: sessionIdFilter || undefined,
      });
      if (res.data) {
        setRecords(res.data.records);
        setTotal(res.data.total);
        setPage(res.data.page);
      }
    } catch (err: unknown) {
      if ((err as { response?: { status?: number } })?.response?.status === 401) {
        setRecords([]);
        setTotal(0);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    setPage(1);
    loadRecords(1);
  }, [dimensionFilter, sessionIdFilter]);

  const handlePageChange = (p: number) => {
    if (p < 1 || p > Math.ceil(total / pageSize)) return;
    loadRecords(p);
  };

  const handleOpenDetail = async (r: ChatRecord) => {
    setDetailSessionId(r.session_id);
    setDetailRecord(r);
    setDetailData(null);
    setDetailLoading(true);
    try {
      const res = await getSessionDetail(r.session_id);
      if (res.data) setDetailData(res.data);
    } finally {
      setDetailLoading(false);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="rounded-2xl border-0 shadow-lg overflow-hidden" style={{ background: 'var(--bd-card)', boxShadow: '0 4px 24px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.04)' }}>
      <div className="px-6 py-5 border-b" style={{ borderColor: 'var(--bd-border)' }}>
        <div className="flex items-center justify-between flex-wrap gap-4">
          <h3 className="text-base font-semibold flex items-center gap-2" style={{ color: 'var(--bd-fg)' }}>
            <FileText size={20} className="opacity-80" />
            对话明细
          </h3>
          <div className="flex items-center gap-2 flex-wrap">
            <input
              type="text"
              placeholder="Session ID / 激活码"
              value={sessionIdFilter}
              onChange={(e) => setSessionIdFilter(e.target.value)}
              className="rounded-xl border px-3 py-2 text-sm w-44 transition-colors focus:outline-none focus:ring-2"
              style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-bg-overlay)' }}
            />
            <select
              value={dimensionFilter}
              onChange={(e) => setDimensionFilter(e.target.value)}
              className="rounded-xl border px-3 py-2 text-sm"
              style={{ borderColor: 'var(--bd-border)', background: 'var(--bd-bg-overlay)' }}
            >
              <option value="">全部维度</option>
              <option value="values">信念</option>
              <option value="strengths">禀赋</option>
              <option value="interests">热忱</option>
              <option value="purpose">使命</option>
              <option value="values_exploration">信念(探索)</option>
              <option value="strengths_exploration">禀赋(探索)</option>
              <option value="interests_exploration">热忱(探索)</option>
              <option value="combination">组合</option>
              <option value="refinement">精炼</option>
            </select>
          </div>
        </div>
      </div>

      <div className="px-6">
        <div className="overflow-x-auto rounded-xl border" style={{ maxHeight: '420px', borderColor: 'var(--bd-border)' }}>
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10" style={{ background: 'var(--bd-bg-overlay)' }}>
              <tr className="border-b" style={{ borderColor: 'var(--bd-border)' }}>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider" style={{ color: 'var(--bd-fg-muted)' }}>Session / 用户</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: 'var(--bd-fg-muted)' }}>维度</th>
                <th className="px-4 py-3 text-right text-xs font-semibold" style={{ color: 'var(--bd-fg-muted)' }}>字数</th>
                <th className="px-4 py-3 text-right text-xs font-semibold" style={{ color: 'var(--bd-fg-muted)' }}>Token 入</th>
                <th className="px-4 py-3 text-right text-xs font-semibold" style={{ color: 'var(--bd-fg-muted)' }}>Token 出</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: 'var(--bd-fg-muted)' }}>时间</th>
                <th className="px-4 py-3 text-left text-xs font-semibold" style={{ color: 'var(--bd-fg-muted)' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={7} className="px-3 py-8 text-center">
                    <Loader2 className="w-6 h-6 animate-spin mx-auto" style={{ color: 'var(--bd-primary)' }} />
                  </td>
                </tr>
              ) : records.length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-3 py-8 text-center" style={{ color: 'var(--bd-fg-muted)' }}>
                    暂无记录，可先点击「从历史同步」
                  </td>
                </tr>
              ) : (
                records.map((r) => (
                  <tr
                    key={r.id}
                    className="border-b cursor-pointer transition-colors"
                    style={{ borderColor: 'var(--bd-border)' }}
                    onClick={() => handleOpenDetail(r)}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bd-bg-overlay)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = '')}
                  >
                    <td className="px-4 py-2.5" style={{ color: 'var(--bd-fg)' }}>
                      <div className="flex flex-col gap-0.5">
                        <span className="font-mono text-xs truncate max-w-[160px]" title={r.session_id}>
                          {r.session_id.slice(0, 10)}…
                        </span>
                        {(r.username || r.user_id || r.activation_code) && (
                          <span className="text-xs flex flex-wrap gap-x-2 gap-y-0.5" style={{ color: 'var(--bd-fg-muted)' }}>
                            {r.username && <span title="用户名">{r.username}</span>}
                            {r.user_id && <span className="font-mono" title="用户ID">{r.user_id.slice(0, 8)}…</span>}
                            {r.activation_code && <span className="font-mono" title="激活码">{r.activation_code}</span>}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-2.5" style={{ color: 'var(--bd-fg)' }}>{DIMENSION_LABELS[r.dimension] || r.dimension}</td>
                    <td className="px-4 py-2.5 text-right font-mono" style={{ color: 'var(--bd-fg-muted)' }}>{r.user_input_chars}</td>
                    <td className="px-4 py-2.5 text-right font-mono" style={{ color: 'var(--bd-fg-muted)' }}>{r.llm_input_tokens}</td>
                    <td className="px-4 py-2.5 text-right font-mono" style={{ color: 'var(--bd-fg-muted)' }}>{r.llm_output_tokens}</td>
                    <td className="px-4 py-2.5 text-xs" style={{ color: 'var(--bd-fg-muted)' }}>
                      {r.created_at ? new Date(r.created_at).toLocaleString('zh-CN') : '-'}
                    </td>
                    <td className="px-4 py-2.5">
                      <button
                        type="button"
                        onClick={(e) => (e.stopPropagation(), handleOpenDetail(r))}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors"
                        style={{ color: 'var(--bd-primary)', background: 'var(--bd-primary-dim)' }}
                      >
                        <FileText size={12} /> 详情
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {total > 0 && (
        <div className="px-6 pb-5 flex items-center justify-between text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          <span>共 {total} 条</span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => handlePageChange(page - 1)}
              disabled={page <= 1}
              className="p-1 rounded disabled:opacity-40 hover:bg-bd-overlay"
            >
              <ChevronLeft size={18} />
            </button>
            <span>{page} / {totalPages}</span>
            <button
              type="button"
              onClick={() => handlePageChange(page + 1)}
              disabled={page >= totalPages}
              className="p-1 rounded disabled:opacity-40 hover:bg-bd-overlay"
            >
              <ChevronRight size={18} />
            </button>
          </div>
        </div>
      )}

      {detailSessionId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
          style={{ background: 'rgba(0,0,0,0.4)' }}
          onClick={() => setDetailSessionId(null)}
        >
          <div
            className="rounded-2xl overflow-hidden flex flex-col max-w-4xl w-full max-h-[88vh] shadow-2xl"
            style={{ background: '#ffffff', border: '1px solid #e2e8f0' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-[#e2e8f0] bg-[#f8fafc]">
              <div>
                <h3 className="font-semibold text-lg text-[#1e293b]">
                  会话详情 · {detailSessionId}
                </h3>
                {detailRecord && (detailRecord.username || detailRecord.user_id || detailRecord.activation_code) && (
                  <div className="flex flex-wrap gap-3 mt-1.5 text-sm text-[#64748b]">
                    {detailRecord.username && <span>用户：{detailRecord.username}</span>}
                    {detailRecord.user_id && <span className="font-mono">ID：{detailRecord.user_id}</span>}
                    {detailRecord.activation_code && <span className="font-mono">激活码：{detailRecord.activation_code}</span>}
                  </div>
                )}
              </div>
              <button
                type="button"
                onClick={() => setDetailSessionId(null)}
                className="p-2 rounded-xl transition-colors hover:opacity-80 bg-[#f1f5f9] hover:bg-[#e2e8f0]"
              >
                <X size={20} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto min-h-0 bg-[#F7F4EE]">
              {detailLoading ? (
                <div className="py-16 text-center bg-white">
                  <Loader2 className="w-10 h-10 animate-spin mx-auto" style={{ color: 'var(--bd-primary)' }} />
                </div>
              ) : detailData?.source === 'runs' ? (
                <div className="flow-light bg-[#F7F4EE]" data-phase="values" style={{ background: '#F7F4EE' }}>
                  <div className="flow-chat-body p-5 bg-[#F7F4EE]" style={{ minHeight: '200px', background: '#F7F4EE' }}>
                    {detailData.turns.map((t, i) => {
                      const e = t.entry as Record<string, unknown>;
                      const userInput = (e?.user_input as string) || '';
                      const response = (e?.response_preview as string) || extractResponseFromLogs(e?.logs);
                      const phase = dimToPhase((e?.context_keys as string[])?.[0] || 'values');
                      const hasContent = userInput || response;
                      return (
                        <div key={i} className="space-y-4">
                          <div className="flow-dimension-label py-2">
                            <span className="flow-dimension-dot" />
                            第 {t.log_index + 1} 轮
                          </div>
                          {!hasContent && (
                            <pre className="p-4 text-xs rounded-lg whitespace-pre-wrap break-words" style={{ ...JSON_PREVIEW_STYLE }}>
                              {JSON.stringify(e, null, 2)}
                            </pre>
                          )}
                          {userInput && (
                            <div className="flow-msg-user">
                              <div className="flow-msg-user-wrap">
                                <div className="flow-msg-user-content">
                                  <span className="flow-msg-user-text">{userInput}</span>
                                </div>
                                <div className="flow-msg-user-toolbar">
                                  <button type="button" className="flow-toolbar-btn" title="复制" onClick={() => copyToClipboard(userInput)}>
                                    <Copy size={14} strokeWidth={1.6} />
                                  </button>
                                </div>
                              </div>
                            </div>
                          )}
                          {response && (
                            <FlowAiMessage content={response} phase={phase} />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : detailData?.source === 'simple' ? (
                <div className="flow-light bg-[#F7F4EE]" data-phase="values" style={{ background: '#F7F4EE' }}>
                  {Object.entries(detailData.conversations).map(([dim, msgs]) => (
                    <div key={dim} className="border-b last:border-b-0 border-[#e2e8f0] bg-[#F7F4EE]">
                      <div className="px-5 pt-4 pb-2 bg-[#F7F4EE]">
                        <h4 className="flow-dimension-label text-sm font-semibold">
                          <span className="flow-dimension-dot" />
                          {DIMENSION_LABELS[dim] || dim}
                        </h4>
                      </div>
                      <div className="flow-chat-body px-5 pb-4 pt-1 bg-[#F7F4EE]" data-phase={dimToPhase(dim)} style={{ background: '#F7F4EE' }}>
                        {msgs.map((m, j) => (
                          m.role === 'user' ? (
                            <div key={j} className="flow-msg-user">
                              <div className="flow-msg-user-wrap">
                                <div className="flow-msg-user-content">
                                  <span className="flow-msg-user-text">{m.content || '-'}</span>
                                </div>
                                <div className="flow-msg-user-toolbar">
                                  <button type="button" className="flow-toolbar-btn" title="复制" onClick={() => copyToClipboard(m.content || '')}>
                                    <Copy size={14} strokeWidth={1.6} />
                                  </button>
                                </div>
                              </div>
                            </div>
                          ) : (
                            <FlowAiMessage key={j} content={m.content || '-'} phase={dimToPhase(dim)} />
                          )
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="p-5 bg-white">
                  <p className="text-[#64748b]">未找到对话内容</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
