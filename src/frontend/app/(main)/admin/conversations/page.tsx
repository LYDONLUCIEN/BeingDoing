'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  fetchAdminConversations,
  fetchAdminConversationDetail,
  cloneConversation,
  jumpToRumination,
  getMockInfo,
  initMock,
  applyMockToActivation,
  saveAsMock,
  type AdminConversationItem,
} from '@/lib/api/admin';
import { formatLocalDateTime } from '@/lib/utils/formatTime';
import { fetchAdminActivations } from '@/lib/api/admin';
import MessageContent from '@/components/explore/MessageContent';
import RuminationTablesView from '@/components/admin/RuminationTablesView';
import { loadSession, saveSession, setLastActivationCode, type PhaseKey } from '@/lib/explore/session';

export default function AdminConversationsPage() {
  const router = useRouter();
  const [items, setItems] = useState<AdminConversationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [stepId, setStepId] = useState('all');
  const [detail, setDetail] = useState<any>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailSessionId, setDetailSessionId] = useState<string>('');
  const [detailReportId, setDetailReportId] = useState<string>('');
  const [detailStepId, setDetailStepId] = useState<string>('');
  const [detailActivationCode, setDetailActivationCode] = useState<string>('');
  const [detailOpen, setDetailOpen] = useState(false);
  const [cloneOpen, setCloneOpen] = useState(false);
  const [jumpOpen, setJumpOpen] = useState(false);
  const [jumpSection, setJumpSection] = useState('opening');
  const [jumpFilterStep, setJumpFilterStep] = useState(0);
  const [jumpLoading, setJumpLoading] = useState(false);
  const [jumpError, setJumpError] = useState<string | null>(null);
  const [cloneTargetCode, setCloneTargetCode] = useState('');
  const [cloneTargetPhase, setCloneTargetPhase] = useState('values');
  const [cloneTargetThreadId, setCloneTargetThreadId] = useState('');
  const [cloneLoading, setCloneLoading] = useState(false);
  const [cloneError, setCloneError] = useState<string | null>(null);
  const [activationCodes, setActivationCodes] = useState<string[]>([]);
  const [mockInfo, setMockInfo] = useState<{ exists: boolean; prior_files: string[] } | null>(null);
  const [mockApplyCode, setMockApplyCode] = useState('');
  const [mockSaveSource, setMockSaveSource] = useState('');
  const [mockLoading, setMockLoading] = useState(false);
  const [mockMsg, setMockMsg] = useState<string | null>(null);
  const [mockOpen, setMockOpen] = useState(false);

  const loadMockInfo = async () => {
    try {
      const info = await getMockInfo();
      setMockInfo(info);
    } catch {
      setMockInfo(null);
    }
  };

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
      interests: '热爱',
      purpose: '使命',
      rumination: '沉淀',
    }),
    [],
  );

  const openDetail = async (sid: string, rid?: string, step?: string, ac?: string) => {
    setDetailOpen(true);
    setDetailSessionId(sid);
    setDetailReportId(rid ?? '');
    setDetailStepId(step ?? '');
    setDetailActivationCode(ac ?? '');
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

  const handleOpenClone = async () => {
    setCloneOpen(true);
    setCloneError(null);
    setCloneTargetCode('');
    setCloneTargetPhase(detailStepId || 'values');
    setCloneTargetThreadId('');
    try {
      const list = await fetchAdminActivations({ status: 'active' });
      setActivationCodes(list.map((a) => a.activation_code));
    } catch {
      setActivationCodes([]);
    }
  };

  const handleClone = async () => {
    if (!cloneTargetCode.trim()) {
      setCloneError('请填写目标激活码');
      return;
    }
    setCloneLoading(true);
    setCloneError(null);
    try {
      await cloneConversation({
        source_report_id: detailReportId,
        source_phase: detailStepId,
        source_thread_id: detailSessionId,
        target_activation_code: cloneTargetCode.trim().toUpperCase(),
        target_phase: cloneTargetPhase,
        target_thread_id: cloneTargetThreadId.trim() || undefined,
      });
      setCloneOpen(false);
      loadList();
    } catch (e: any) {
      setCloneError(e?.response?.data?.detail || e?.message || '克隆失败');
    } finally {
      setCloneLoading(false);
    }
  };

  const [jumpActivationCode, setJumpActivationCode] = useState('');

  const handleJumpToRumination = async () => {
    const code = (jumpActivationCode || detailActivationCode)?.trim();
    if (!code) return;
    setJumpLoading(true);
    try {
      await jumpToRumination({
        activation_code: code.toUpperCase(),
        target_section: jumpSection,
        target_filter_step: jumpFilterStep || undefined,
      });
      setLastActivationCode(code.toUpperCase());
      const s = loadSession(code.toUpperCase());
      const phases = s?.unlockedPhases ?? ['values'];
      if (!phases.includes('rumination')) {
        saveSession({
          ...s,
          activationCode: code.toUpperCase(),
          unlockedPhases: [...new Set([...phases, 'rumination' as PhaseKey])] as PhaseKey[],
          currentPhase: 'rumination',
        });
      }
      setJumpOpen(false);
      router.push('/explore/chat/rumination');
    } catch (e: any) {
      setJumpError(e?.response?.data?.detail || e?.message || '跳步失败');
    } finally {
      setJumpLoading(false);
    }
  };

  const renderConversationDetail = () => {
    const payload = detail?.conversation ?? detail;
    const source = detail?.source || payload?.source;
    const messages = Array.isArray(payload?.messages) ? payload.messages : [];

    // rumination：优先渲染表格区块（step 表格 + step 对话切片），再附原始对话
    if (detail?.rumination_tables) {
      return (
        <div className="space-y-4">
          <RuminationTablesView
            tables={detail.rumination_tables}
            conversationByStep={detail.conversation_by_step}
          />
        </div>
      );
    }

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
                <p className="text-[11px] text-bd-subtle">{msg?.created_at ? formatLocalDateTime(msg.created_at) : ''}</p>
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
        <button
          type="button"
          onClick={() => {
            setMockOpen(true);
            setMockMsg(null);
            loadMockInfo();
          }}
          className="px-3 py-2 rounded-lg border border-bd-border hover:bg-bd-overlay-md"
        >
          Mock 数据管理
        </button>
      </section>

      {mockOpen && (
        <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-4 shadow-sm">
          <h3 className="text-sm font-medium mb-3" style={{ color: 'var(--bd-fg)' }}>
            Mock 数据管理
          </h3>
          <p className="text-xs text-bd-subtle mb-3">
            常态化 mock 数据存于 data/admin_mock/，用于调试 rumination。先点击「初始化 Mock」生成默认数据，再「应用」到激活码，或通过 Admin 跳步。
          </p>
          <div className="flex flex-wrap gap-4 items-end">
            <div>
              <label className="block text-bd-subtle mb-1 text-xs">初始化默认 Mock</label>
              <button
                type="button"
                onClick={async () => {
                  setMockLoading(true);
                  setMockMsg(null);
                  try {
                    const info = await initMock();
                    setMockInfo(info);
                    setMockMsg('已初始化 mock 数据');
                  } catch (e: any) {
                    setMockMsg(e?.response?.data?.detail || e?.message || '失败');
                  } finally {
                    setMockLoading(false);
                  }
                }}
                disabled={mockLoading}
                className="px-3 py-2 rounded-lg border border-bd-border hover:bg-bd-overlay-md text-xs disabled:opacity-50"
              >
                初始化 Mock
              </button>
            </div>
            <div>
              <label className="block text-bd-subtle mb-1 text-xs">应用 Mock 到激活码</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={mockApplyCode}
                  onChange={(e) => setMockApplyCode(e.target.value.toUpperCase())}
                  placeholder="激活码"
                  className="rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs w-32"
                />
                <button
                  type="button"
                  onClick={async () => {
                    if (!mockApplyCode.trim()) return;
                    setMockLoading(true);
                    setMockMsg(null);
                    try {
                      await applyMockToActivation(mockApplyCode);
                      setMockMsg('应用成功');
                    } catch (e: any) {
                      setMockMsg(e?.response?.data?.detail || e?.message || '失败');
                    } finally {
                      setMockLoading(false);
                    }
                  }}
                  disabled={mockLoading}
                  className="px-3 py-2 rounded-lg bg-bd-ui-accent text-bd-ui-accent-fg text-xs disabled:opacity-50"
                >
                  应用
                </button>
              </div>
            </div>
            <div>
              <label className="block text-bd-subtle mb-1 text-xs">用历史数据替换 Mock</label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={mockSaveSource}
                  onChange={(e) => setMockSaveSource(e.target.value.toUpperCase())}
                  placeholder="激活码 或 report_id"
                  className="rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs w-40"
                />
                <button
                  type="button"
                  onClick={async () => {
                    if (!mockSaveSource.trim()) return;
                    setMockLoading(true);
                    setMockMsg(null);
                    try {
                      const isReportId = mockSaveSource.includes('-') || mockSaveSource.length > 12;
                      await saveAsMock(
                        isReportId
                          ? { report_id: mockSaveSource }
                          : { activation_code: mockSaveSource }
                      );
                      setMockMsg('已保存为 mock');
                      loadMockInfo();
                    } catch (e: any) {
                      setMockMsg(e?.response?.data?.detail || e?.message || '失败');
                    } finally {
                      setMockLoading(false);
                    }
                  }}
                  disabled={mockLoading}
                  className="px-3 py-2 rounded-lg border border-bd-border hover:bg-bd-overlay-md text-xs disabled:opacity-50"
                >
                  保存为 Mock
                </button>
              </div>
            </div>
          </div>
          {mockInfo && (
            <p className="text-[11px] text-bd-subtle mt-2">
              prior 文件: {mockInfo.prior_files?.join(', ') || '无'}
            </p>
          )}
          {mockMsg && (
            <p className={`text-xs mt-2 ${mockMsg.includes('成功') || mockMsg.includes('已保存') ? 'text-green-600' : 'text-red-600'}`}>
              {mockMsg}
            </p>
          )}
          <button
            type="button"
            onClick={() => setMockOpen(false)}
            className="mt-3 px-2 py-1 text-xs rounded border border-bd-border hover:bg-bd-overlay-md"
          >
            收起
          </button>
        </section>
      )}

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
                        onClick={() =>
                          openDetail(item.session_id, item.report_id, item.step_id, item.activation_code)
                        }
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
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    setJumpActivationCode(detailActivationCode);
                    setJumpError(null);
                    setJumpOpen(true);
                  }}
                  className="px-2 py-1 text-xs rounded border border-bd-border hover:bg-bd-overlay-md whitespace-nowrap"
                >
                  跳步到 Rumination
                </button>
                <button
                  type="button"
                  onClick={handleOpenClone}
                  className="px-2 py-1 text-xs rounded border border-bd-border hover:bg-bd-overlay-md whitespace-nowrap"
                >
                  克隆到…
                </button>
                <button
                  type="button"
                  onClick={() => setDetailOpen(false)}
                  className="px-2 py-1 text-xs rounded border border-bd-border hover:bg-bd-overlay-md whitespace-nowrap"
                >
                  关闭
                </button>
              </div>
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

      {jumpOpen && (
        <div
          className="fixed inset-0 z-[130] bg-black/40 backdrop-blur-[1px] flex items-center justify-center p-4"
          onClick={() => !jumpLoading && setJumpOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-bd-card border border-bd-border shadow-2xl p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-sm font-medium mb-4" style={{ color: 'var(--bd-fg)' }}>
              跳步到 Rumination
            </h3>
            <p className="text-xs text-bd-subtle mb-3 leading-relaxed">
              调试功能：可将指定激活码直接跳到 Rumination 阶段。跳步时会自动应用 data/admin_mock/ 中的 mock 数据（含 prior_context），满足进入 rumination 的前置要求。可在「Mock 数据管理」中用历史数据替换 mock。
            </p>
            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-bd-subtle mb-1">激活码</label>
                <input
                  type="text"
                  value={jumpActivationCode}
                  onChange={(e) => setJumpActivationCode(e.target.value.toUpperCase())}
                  placeholder="输入激活码"
                  className="w-full rounded-lg border border-bd-border bg-bd-overlay px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-bd-subtle mb-1">目标 section</label>
                <select
                  value={jumpSection}
                  onChange={(e) => setJumpSection(e.target.value)}
                  className="w-full rounded-lg border border-bd-border bg-bd-overlay px-3 py-2"
                >
                  <option value="opening">opening</option>
                  <option value="review">review</option>
                  <option value="filter">filter</option>
                  <option value="final_choice">final_choice</option>
                  <option value="recommend">recommend</option>
                  <option value="end">end</option>
                </select>
              </div>
              <div>
                <label className="block text-bd-subtle mb-1">筛选步骤 (0=未进入)</label>
                <input
                  type="number"
                  min={0}
                  max={7}
                  value={jumpFilterStep}
                  onChange={(e) => setJumpFilterStep(parseInt(e.target.value, 10) || 0)}
                  className="w-full rounded-lg border border-bd-border bg-bd-overlay px-3 py-2"
                />
              </div>
              {jumpError && <p className="text-red-600 text-xs">{jumpError}</p>}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => !jumpLoading && setJumpOpen(false)}
                className="px-3 py-1.5 text-xs rounded border border-bd-border hover:bg-bd-overlay-md"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleJumpToRumination}
                disabled={jumpLoading}
                className="px-3 py-1.5 text-xs rounded bg-bd-ui-accent text-bd-ui-accent-fg disabled:opacity-50"
              >
                {jumpLoading ? '跳步中…' : '确认并跳转'}
              </button>
            </div>
          </div>
        </div>
      )}

      {cloneOpen && (
        <div
          className="fixed inset-0 z-[130] bg-black/40 backdrop-blur-[1px] flex items-center justify-center p-4"
          onClick={() => !cloneLoading && setCloneOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-2xl bg-bd-card border border-bd-border shadow-2xl p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-sm font-medium mb-4" style={{ color: 'var(--bd-fg)' }}>
              克隆会话到目标
            </h3>
            <div className="space-y-3 text-xs">
              <div>
                <label className="block text-bd-subtle mb-1">目标激活码</label>
                <input
                  type="text"
                  value={cloneTargetCode}
                  onChange={(e) => setCloneTargetCode(e.target.value.toUpperCase())}
                  placeholder="输入激活码"
                  className="w-full rounded-lg border border-bd-border bg-bd-overlay px-3 py-2"
                />
              </div>
              <div>
                <label className="block text-bd-subtle mb-1">目标阶段</label>
                <select
                  value={cloneTargetPhase}
                  onChange={(e) => setCloneTargetPhase(e.target.value)}
                  className="w-full rounded-lg border border-bd-border bg-bd-overlay px-3 py-2"
                >
                  <option value="values">values</option>
                  <option value="strengths">strengths</option>
                  <option value="interests">interests</option>
                  <option value="purpose">purpose</option>
                  <option value="rumination">rumination</option>
                </select>
              </div>
              <div>
                <label className="block text-bd-subtle mb-1">目标 thread_id（可选，不填则新建）</label>
                <input
                  type="text"
                  value={cloneTargetThreadId}
                  onChange={(e) => setCloneTargetThreadId(e.target.value)}
                  placeholder="留空自动生成"
                  className="w-full rounded-lg border border-bd-border bg-bd-overlay px-3 py-2"
                />
              </div>
              {cloneError && (
                <p className="text-red-600 text-xs">{cloneError}</p>
              )}
            </div>
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => !cloneLoading && setCloneOpen(false)}
                className="px-3 py-1.5 text-xs rounded border border-bd-border hover:bg-bd-overlay-md"
              >
                取消
              </button>
              <button
                type="button"
                onClick={handleClone}
                disabled={cloneLoading}
                className="px-3 py-1.5 text-xs rounded bg-bd-ui-accent text-bd-ui-accent-fg disabled:opacity-50"
              >
                {cloneLoading ? '克隆中…' : '确认克隆'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

