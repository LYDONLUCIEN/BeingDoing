'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  fetchAdminLlmTurnDetail,
  fetchAdminLlmTurns,
  fetchAdminLlmUsageCalls,
  fetchAdminLlmUsageSummary,
  fetchAdminLlmUsageUsers,
  type AdminLlmTurnLogDetail,
  type AdminLlmTurnLogItem,
  type AdminLlmUsageCall,
  type AdminLlmUsageSummary,
  type AdminLlmUsageUser,
} from '@/lib/api/admin';
import { formatLocalDateTime } from '@/lib/utils/formatTime';

type TabKey = 'overview' | 'users' | 'calls' | 'turns';

const TABS: Array<{ key: TabKey; label: string }> = [
  { key: 'overview', label: '总览与趋势' },
  { key: 'users', label: '按用户' },
  { key: 'calls', label: '调用明细' },
  { key: 'turns', label: '轮次诊断' },
];

/** 轮次诊断 outcome 口径（与后端 llm_turn_log_service 一致） */
const TURN_OUTCOMES: Array<{ value: string; label: string }> = [
  { value: 'ok', label: '正常' },
  { value: 'length', label: '截断(length)' },
  { value: 'empty_content_retried_ok', label: '空回复·重试成功' },
  { value: 'empty_content_failed', label: '空回复·重试失败' },
  { value: 'partial', label: '半截回复' },
  { value: 'error', label: '错误' },
  { value: 'disconnected', label: '客户端断开' },
];

function turnOutcomeLabel(outcome?: string | null): string {
  return TURN_OUTCOMES.find((o) => o.value === outcome)?.label || outcome || '—';
}

function turnOutcomeClass(outcome?: string | null): string {
  if (outcome === 'ok') return 'text-emerald-700 bg-emerald-50 border-emerald-200';
  if (outcome === 'empty_content_failed' || outcome === 'error')
    return 'text-red-700 bg-red-50 border-red-200';
  return 'text-amber-700 bg-amber-50 border-amber-200';
}

function fmtTokens(n?: number | null): string {
  const v = Number(n || 0);
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}K`;
  return String(v);
}

function fmtCost(cost?: number | null, known?: boolean): string {
  if (cost === null || cost === undefined) return '—';
  if (!known && !cost) return '—';
  return `¥${cost.toFixed(4)}`;
}

function todayStr(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate(),
  ).padStart(2, '0')}`;
}

function daysAgoStr(n: number): string {
  const d = new Date(Date.now() - n * 86400000);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate(),
  ).padStart(2, '0')}`;
}

export default function LlmUsagePanel() {
  const [tab, setTab] = useState<TabKey>('overview');
  const [start, setStart] = useState(daysAgoStr(29));
  const [end, setEnd] = useState(todayStr());
  const [error, setError] = useState<string | null>(null);

  const [summary, setSummary] = useState<AdminLlmUsageSummary | null>(null);
  const [loadingSummary, setLoadingSummary] = useState(false);

  const [users, setUsers] = useState<AdminLlmUsageUser[]>([]);
  const [usersTotal, setUsersTotal] = useState(0);
  const [usersPage, setUsersPage] = useState(1);
  const [userQuery, setUserQuery] = useState('');
  const [loadingUsers, setLoadingUsers] = useState(false);

  const [calls, setCalls] = useState<AdminLlmUsageCall[]>([]);
  const [callsTotal, setCallsTotal] = useState(0);
  const [callsPage, setCallsPage] = useState(1);
  const [callScene, setCallScene] = useState('');
  const [callUserId, setCallUserId] = useState('');
  const [loadingCalls, setLoadingCalls] = useState(false);

  const [turns, setTurns] = useState<AdminLlmTurnLogItem[]>([]);
  const [turnsTotal, setTurnsTotal] = useState(0);
  const [turnsPage, setTurnsPage] = useState(1);
  const [turnOutcome, setTurnOutcome] = useState('');
  const [turnCode, setTurnCode] = useState('');
  const [turnSession, setTurnSession] = useState('');
  const [loadingTurns, setLoadingTurns] = useState(false);
  const [turnDetail, setTurnDetail] = useState<AdminLlmTurnLogDetail | null>(null);
  const [loadingTurnDetail, setLoadingTurnDetail] = useState(false);

  const pageSize = 50;

  const loadSummary = useCallback(async () => {
    setLoadingSummary(true);
    setError(null);
    try {
      setSummary(await fetchAdminLlmUsageSummary({ start, end }));
    } catch (e: any) {
      setError(e?.message || '加载用量总览失败');
    } finally {
      setLoadingSummary(false);
    }
  }, [start, end]);

  const loadUsers = useCallback(
    async (page = 1) => {
      setLoadingUsers(true);
      setError(null);
      try {
        const res = await fetchAdminLlmUsageUsers({
          start,
          end,
          page,
          page_size: pageSize,
          q: userQuery || undefined,
        });
        setUsers(res.records || []);
        setUsersTotal(Number(res.total || 0));
        setUsersPage(Number(res.page || page));
      } catch (e: any) {
        setError(e?.message || '加载用户用量失败');
      } finally {
        setLoadingUsers(false);
      }
    },
    [start, end, userQuery],
  );

  const loadCalls = useCallback(
    async (page = 1) => {
      setLoadingCalls(true);
      setError(null);
      try {
        const res = await fetchAdminLlmUsageCalls({
          start,
          end,
          page,
          page_size: pageSize,
          scene: callScene || undefined,
          user_id: callUserId || undefined,
        });
        setCalls(res.records || []);
        setCallsTotal(Number(res.total || 0));
        setCallsPage(Number(res.page || page));
      } catch (e: any) {
        setError(e?.message || '加载调用明细失败');
      } finally {
        setLoadingCalls(false);
      }
    },
    [start, end, callScene, callUserId],
  );

  const loadTurns = useCallback(
    async (page = 1) => {
      setLoadingTurns(true);
      setError(null);
      try {
        const res = await fetchAdminLlmTurns({
          start,
          end,
          page,
          page_size: pageSize,
          outcome: turnOutcome || undefined,
          activation_code: turnCode || undefined,
          session_id: turnSession || undefined,
        });
        setTurns(res.records || []);
        setTurnsTotal(Number(res.total || 0));
        setTurnsPage(Number(res.page || page));
      } catch (e: any) {
        setError(e?.message || '加载轮次日志失败');
      } finally {
        setLoadingTurns(false);
      }
    },
    [start, end, turnOutcome, turnCode, turnSession],
  );

  const openTurnDetail = useCallback(async (logId: string) => {
    setLoadingTurnDetail(true);
    try {
      setTurnDetail(await fetchAdminLlmTurnDetail(logId));
    } catch (e: any) {
      setError(e?.message || '加载日志详情失败');
    } finally {
      setLoadingTurnDetail(false);
    }
  }, []);

  useEffect(() => {
    if (tab === 'overview') loadSummary();
    if (tab === 'users') loadUsers(1);
    if (tab === 'calls') loadCalls(1);
    if (tab === 'turns') loadTurns(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab]);

  const aggCards = (agg?: AdminLlmUsageSummary['total'], prefix = '') =>
    agg ? (
      <>
        {[
          { label: `${prefix}调用次数`, value: String(agg.calls) },
          { label: `${prefix}输入 Token`, value: fmtTokens(agg.prompt_tokens) },
          {
            label: `${prefix}缓存命中率`,
            value:
              agg.cache_hit_rate === null || agg.cache_hit_rate === undefined
                ? '—'
                : `${(agg.cache_hit_rate * 100).toFixed(1)}%`,
          },
          { label: `${prefix}输出 Token`, value: fmtTokens(agg.completion_tokens) },
          { label: `${prefix}预估费用`, value: fmtCost(agg.cost_yuan, agg.cost_known) },
        ].map((c) => (
          <div
            key={c.label}
            className="rounded-xl border border-bd-border bg-bd-overlay-md px-3 py-2"
          >
            <p className="text-[11px] text-bd-subtle">{c.label}</p>
            <p className="text-base font-semibold">{c.value}</p>
          </div>
        ))}
      </>
    ) : null;

  return (
    <section className="rounded-2xl bg-bd-card border border-bd-border px-6 py-5 shadow-sm">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
        <div>
          <h2 className="text-sm font-medium">LLM Token 消耗统计</h2>
          <p className="text-[11px] text-bd-subtle mt-1">
            调用粒度统计（llm_usage_logs），费用为落库时按当时费率表（含峰谷时段）计算的预估值，以
            DeepSeek 账单为准；数据自功能上线起累积，不含历史回填。
          </p>
        </div>
        <div className="flex items-end gap-2">
          <div className="space-y-1">
            <p className="text-[11px] text-bd-subtle">开始</p>
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-1.5 text-xs"
            />
          </div>
          <div className="space-y-1">
            <p className="text-[11px] text-bd-subtle">结束</p>
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-1.5 text-xs"
            />
          </div>
          <button
            type="button"
            onClick={() => {
              if (tab === 'overview') loadSummary();
              if (tab === 'users') loadUsers(1);
              if (tab === 'calls') loadCalls(1);
              if (tab === 'turns') loadTurns(1);
            }}
            className="px-3 py-2 rounded-lg bg-bd-ui-accent text-bd-ui-accent-fg text-xs"
          >
            查询
          </button>
        </div>
      </div>

      <div className="flex items-center gap-2 mb-4 border-b border-bd-border">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`px-3 py-2 text-xs border-b-2 -mb-px ${
              tab === t.key
                ? 'border-bd-ui-accent font-medium'
                : 'border-transparent text-bd-subtle hover:text-bd-fg'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-xs mb-4">
          {error}
        </div>
      )}

      {tab === 'overview' && (
        <div className="space-y-5">
          {loadingSummary ? (
            <p className="text-xs text-bd-subtle">加载中...</p>
          ) : !summary ? (
            <p className="text-xs text-bd-subtle">暂无数据。</p>
          ) : (
            <>
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">{aggCards(summary.total)}</div>

              <div>
                <h3 className="text-xs font-medium mb-2">峰谷时段拆分（高峰：北京时间 9-12 / 14-18）</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div className="rounded-xl border border-bd-border px-4 py-3">
                    <p className="text-[11px] text-bd-subtle mb-2">高峰时段</p>
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <span>调用 {summary.peak.calls}</span>
                      <span>Token {fmtTokens(summary.peak.prompt_tokens + summary.peak.completion_tokens)}</span>
                      <span>{fmtCost(summary.peak.cost_yuan, summary.peak.cost_known)}</span>
                    </div>
                  </div>
                  <div className="rounded-xl border border-bd-border px-4 py-3">
                    <p className="text-[11px] text-bd-subtle mb-2">空闲时段</p>
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <span>调用 {summary.off_peak.calls}</span>
                      <span>
                        Token {fmtTokens(summary.off_peak.prompt_tokens + summary.off_peak.completion_tokens)}
                      </span>
                      <span>{fmtCost(summary.off_peak.cost_yuan, summary.off_peak.cost_known)}</span>
                    </div>
                  </div>
                </div>
              </div>

              <div>
                <h3 className="text-xs font-medium mb-2">分场景</h3>
                <table className="w-full text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-bd-border text-[11px] text-bd-subtle">
                      <th className="px-2 py-2 text-left font-medium">场景</th>
                      <th className="px-2 py-2 text-left font-medium">调用</th>
                      <th className="px-2 py-2 text-left font-medium">输入</th>
                      <th className="px-2 py-2 text-left font-medium">缓存命中</th>
                      <th className="px-2 py-2 text-left font-medium">输出</th>
                      <th className="px-2 py-2 text-left font-medium">预估费用</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summary.by_scene.map((s) => (
                      <tr key={s.scene} className="border-b border-bd-border/60 last:border-0">
                        <td className="px-2 py-2">{s.scene}</td>
                        <td className="px-2 py-2">{s.calls}</td>
                        <td className="px-2 py-2">{fmtTokens(s.prompt_tokens)}</td>
                        <td className="px-2 py-2">{fmtTokens(s.cache_hit_tokens)}</td>
                        <td className="px-2 py-2">{fmtTokens(s.completion_tokens)}</td>
                        <td className="px-2 py-2">{fmtCost(s.cost_yuan, s.cost_known)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div>
                <h3 className="text-xs font-medium mb-2">按天趋势</h3>
                <div className="overflow-x-auto -mx-2 pb-1">
                  <table className="min-w-[720px] w-full text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-bd-border text-[11px] text-bd-subtle">
                        <th className="px-2 py-2 text-left font-medium">日期</th>
                        <th className="px-2 py-2 text-left font-medium">调用</th>
                        <th className="px-2 py-2 text-left font-medium">输入</th>
                        <th className="px-2 py-2 text-left font-medium">输出</th>
                        <th className="px-2 py-2 text-left font-medium">命中率</th>
                        <th className="px-2 py-2 text-left font-medium">预估费用</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...summary.by_day].reverse().map((d) => (
                        <tr key={d.date} className="border-b border-bd-border/60 last:border-0">
                          <td className="px-2 py-2 font-mono text-[11px]">{d.date}</td>
                          <td className="px-2 py-2">{d.calls}</td>
                          <td className="px-2 py-2">{fmtTokens(d.prompt_tokens)}</td>
                          <td className="px-2 py-2">{fmtTokens(d.completion_tokens)}</td>
                          <td className="px-2 py-2">
                            {d.cache_hit_rate === null || d.cache_hit_rate === undefined
                              ? '—'
                              : `${(d.cache_hit_rate * 100).toFixed(0)}%`}
                          </td>
                          <td className="px-2 py-2">{fmtCost(d.cost_yuan, d.cost_known)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {tab === 'users' && (
        <div className="space-y-3">
          <div className="flex items-end gap-2">
            <input
              value={userQuery}
              onChange={(e) => setUserQuery(e.target.value)}
              placeholder="用户名 / 邮箱 / user_id / 激活码"
              className="w-[280px] rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs"
            />
            <button
              type="button"
              onClick={() => loadUsers(1)}
              className="px-3 py-2 rounded-lg border border-bd-border text-xs hover:bg-bd-overlay-md"
            >
              搜索
            </button>
          </div>
          {loadingUsers ? (
            <p className="text-xs text-bd-subtle">加载中...</p>
          ) : users.length === 0 ? (
            <p className="text-xs text-bd-subtle">暂无记录。</p>
          ) : (
            <div className="overflow-x-auto -mx-2 pb-1">
              <table className="min-w-[1080px] w-full text-xs border-collapse">
                <thead>
                  <tr className="border-b border-bd-border text-[11px] text-bd-subtle">
                    <th className="px-2 py-2 text-left font-medium">用户</th>
                    <th className="px-2 py-2 text-left font-medium">激活码</th>
                    <th className="px-2 py-2 text-left font-medium">调用</th>
                    <th className="px-2 py-2 text-left font-medium">输入</th>
                    <th className="px-2 py-2 text-left font-medium">缓存命中</th>
                    <th className="px-2 py-2 text-left font-medium">输出</th>
                    <th className="px-2 py-2 text-left font-medium">场景</th>
                    <th className="px-2 py-2 text-left font-medium">预估费用</th>
                    <th className="px-2 py-2 text-left font-medium">最近活跃</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u, i) => (
                    <tr
                      key={u.user_id || u.activation_code || `unknown-${i}`}
                      className="border-b border-bd-border/60 last:border-0"
                    >
                      <td className="px-2 py-2">
                        <div>{u.username || '—'}</div>
                        <div className="text-[10px] text-bd-subtle font-mono">
                          {u.email || u.user_id || '（未关联用户）'}
                        </div>
                      </td>
                      <td className="px-2 py-2 font-mono text-[11px]">{u.activation_code || '—'}</td>
                      <td className="px-2 py-2">{u.calls}</td>
                      <td className="px-2 py-2">{fmtTokens(u.prompt_tokens)}</td>
                      <td className="px-2 py-2">{fmtTokens(u.cache_hit_tokens)}</td>
                      <td className="px-2 py-2">{fmtTokens(u.completion_tokens)}</td>
                      <td className="px-2 py-2">{(u.scenes || []).join(', ')}</td>
                      <td className="px-2 py-2">{fmtCost(u.cost_yuan)}</td>
                      <td className="px-2 py-2 whitespace-nowrap">
                        {u.last_active_at ? formatLocalDateTime(u.last_active_at) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pager
            page={usersPage}
            total={usersTotal}
            pageSize={pageSize}
            onPage={(p) => loadUsers(p)}
          />
        </div>
      )}

      {tab === 'calls' && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-end gap-2">
            <select
              value={callScene}
              onChange={(e) => setCallScene(e.target.value)}
              className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-2 text-xs"
            >
              <option value="">全部场景</option>
              {['chat', 'report', 'rumination', 'team_analysis', 'unknown'].map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
            <input
              value={callUserId}
              onChange={(e) => setCallUserId(e.target.value)}
              placeholder="user_id 过滤（可选）"
              className="w-[240px] rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs"
            />
            <button
              type="button"
              onClick={() => loadCalls(1)}
              className="px-3 py-2 rounded-lg border border-bd-border text-xs hover:bg-bd-overlay-md"
            >
              查询
            </button>
          </div>
          {loadingCalls ? (
            <p className="text-xs text-bd-subtle">加载中...</p>
          ) : calls.length === 0 ? (
            <p className="text-xs text-bd-subtle">暂无记录。</p>
          ) : (
            <div className="overflow-x-auto -mx-2 pb-1">
              <table className="min-w-[1280px] w-full text-xs border-collapse">
                <thead>
                  <tr className="border-b border-bd-border text-[11px] text-bd-subtle">
                    <th className="px-2 py-2 text-left font-medium">时间</th>
                    <th className="px-2 py-2 text-left font-medium">场景</th>
                    <th className="px-2 py-2 text-left font-medium">模型</th>
                    <th className="px-2 py-2 text-left font-medium">user_id</th>
                    <th className="px-2 py-2 text-left font-medium">激活码</th>
                    <th className="px-2 py-2 text-left font-medium">输入</th>
                    <th className="px-2 py-2 text-left font-medium">命中/未命中</th>
                    <th className="px-2 py-2 text-left font-medium">输出</th>
                    <th className="px-2 py-2 text-left font-medium">峰/谷</th>
                    <th className="px-2 py-2 text-left font-medium">预估费用</th>
                  </tr>
                </thead>
                <tbody>
                  {calls.map((c) => (
                    <tr key={c.id} className="border-b border-bd-border/60 last:border-0">
                      <td className="px-2 py-2 whitespace-nowrap">
                        {c.created_at ? formatLocalDateTime(c.created_at) : ''}
                      </td>
                      <td className="px-2 py-2">{c.scene}</td>
                      <td className="px-2 py-2 font-mono text-[11px]">{c.model || '—'}</td>
                      <td className="px-2 py-2 font-mono text-[11px]">{c.user_id || '—'}</td>
                      <td className="px-2 py-2 font-mono text-[11px]">{c.activation_code || '—'}</td>
                      <td className="px-2 py-2">{fmtTokens(c.prompt_tokens)}</td>
                      <td className="px-2 py-2">
                        {fmtTokens(c.cache_hit_tokens)}/{fmtTokens(c.cache_miss_tokens)}
                      </td>
                      <td className="px-2 py-2">{fmtTokens(c.completion_tokens)}</td>
                      <td className="px-2 py-2">{c.is_peak ? '峰' : '谷'}</td>
                      <td className="px-2 py-2">{fmtCost(c.cost_yuan)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pager
            page={callsPage}
            total={callsTotal}
            pageSize={pageSize}
            onPage={(p) => loadCalls(p)}
          />
        </div>
      )}

      {tab === 'turns' && (
        <div className="space-y-3">
          <p className="text-[11px] text-bd-subtle">
            每轮 LLM 调用的结构化诊断（含空回复/半截/断连分类；详情可查看思维链与正文全文，仅
            super_admin）。数据自 2026-09-21 功能上线起累积，按保留期自动清理。
          </p>
          <div className="flex flex-wrap items-end gap-2">
            <select
              value={turnOutcome}
              onChange={(e) => setTurnOutcome(e.target.value)}
              className="rounded-lg border border-bd-border bg-bd-overlay px-2 py-2 text-xs"
            >
              <option value="">全部结果</option>
              {TURN_OUTCOMES.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
            <input
              value={turnCode}
              onChange={(e) => setTurnCode(e.target.value)}
              placeholder="激活码过滤（可选）"
              className="w-[180px] rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs"
            />
            <input
              value={turnSession}
              onChange={(e) => setTurnSession(e.target.value)}
              placeholder="session / thread 过滤（可选）"
              className="w-[220px] rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-xs"
            />
            <button
              type="button"
              onClick={() => loadTurns(1)}
              className="px-3 py-2 rounded-lg border border-bd-border text-xs hover:bg-bd-overlay-md"
            >
              查询
            </button>
          </div>
          {loadingTurns ? (
            <p className="text-xs text-bd-subtle">加载中...</p>
          ) : turns.length === 0 ? (
            <p className="text-xs text-bd-subtle">暂无记录。</p>
          ) : (
            <div className="overflow-x-auto -mx-2 pb-1">
              <table className="min-w-[1280px] w-full text-xs border-collapse">
                <thead>
                  <tr className="border-b border-bd-border text-[11px] text-bd-subtle">
                    <th className="px-2 py-2 text-left font-medium">时间</th>
                    <th className="px-2 py-2 text-left font-medium">结果</th>
                    <th className="px-2 py-2 text-left font-medium">模型</th>
                    <th className="px-2 py-2 text-left font-medium">场景/阶段</th>
                    <th className="px-2 py-2 text-left font-medium">激活码</th>
                    <th className="px-2 py-2 text-left font-medium">会话</th>
                    <th className="px-2 py-2 text-left font-medium">finish</th>
                    <th className="px-2 py-2 text-left font-medium">重试</th>
                    <th className="px-2 py-2 text-left font-medium">思维链/正文字符</th>
                    <th className="px-2 py-2 text-left font-medium">正文预览</th>
                    <th className="px-2 py-2 text-left font-medium">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {turns.map((t) => (
                    <tr key={t.id} className="border-b border-bd-border/60 last:border-0">
                      <td className="px-2 py-2 whitespace-nowrap">
                        {t.ts ? formatLocalDateTime(t.ts) : '—'}
                      </td>
                      <td className="px-2 py-2">
                        <span
                          className={`inline-block rounded-full border px-2 py-0.5 text-[11px] ${turnOutcomeClass(
                            t.outcome,
                          )}`}
                        >
                          {turnOutcomeLabel(t.outcome)}
                        </span>
                      </td>
                      <td className="px-2 py-2 font-mono text-[11px]">{t.model || '—'}</td>
                      <td className="px-2 py-2">
                        {t.scene || '—'}
                        {t.phase ? ` / ${t.phase}` : ''}
                      </td>
                      <td className="px-2 py-2 font-mono text-[11px]">{t.activation_code || '—'}</td>
                      <td className="px-2 py-2 font-mono text-[11px]" title={t.thread_id || ''}>
                        {(t.thread_id || t.session_id || '—').slice(0, 12)}
                      </td>
                      <td className="px-2 py-2">{t.finish_reason || '—'}</td>
                      <td className="px-2 py-2">{t.retry_count || 0}</td>
                      <td className="px-2 py-2">
                        {t.reasoning_chars ?? 0}/{t.content_chars ?? 0}
                      </td>
                      <td
                        className="px-2 py-2 max-w-[220px] truncate text-bd-subtle"
                        title={t.content_preview || ''}
                      >
                        {t.content_preview || '—'}
                      </td>
                      <td className="px-2 py-2">
                        <button
                          type="button"
                          disabled={loadingTurnDetail}
                          onClick={() => openTurnDetail(t.id)}
                          className="px-2 py-1 rounded-lg border border-bd-border text-[11px] hover:bg-bd-overlay-md disabled:opacity-50"
                        >
                          详情
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Pager
            page={turnsPage}
            total={turnsTotal}
            pageSize={pageSize}
            onPage={(p) => loadTurns(p)}
          />
        </div>
      )}

      {turnDetail && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onClick={() => setTurnDetail(null)}
        >
          <div
            className="max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-bd-card border border-bd-border p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between gap-3 mb-3">
              <div>
                <span
                  className={`inline-block rounded-full border px-2 py-0.5 text-[11px] ${turnOutcomeClass(
                    turnDetail.outcome,
                  )}`}
                >
                  {turnOutcomeLabel(turnDetail.outcome)}
                </span>
                <p className="text-[11px] text-bd-subtle mt-2 font-mono">
                  {turnDetail.ts ? formatLocalDateTime(turnDetail.ts) : ''} · {turnDetail.model || '—'} ·
                  finish={turnDetail.finish_reason || '—'} · 重试 {turnDetail.retry_count || 0} 次 ·
                  耗时 {turnDetail.duration_ms ?? '—'}ms
                </p>
                <p className="text-[11px] text-bd-subtle mt-1 font-mono">
                  激活码 {turnDetail.activation_code || '—'} · session {turnDetail.session_id || '—'} ·
                  thread {turnDetail.thread_id || '—'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setTurnDetail(null)}
                className="px-2 py-1 rounded-lg border border-bd-border text-xs hover:bg-bd-overlay-md"
              >
                关闭
              </button>
            </div>
            {turnDetail.error && (
              <div className="rounded-xl border border-red-200 bg-red-50 text-red-700 px-3 py-2 text-xs mb-3">
                {turnDetail.error}
              </div>
            )}
            <h4 className="text-xs font-medium mb-1">思维链全文（reasoning_content，敏感）</h4>
            <pre className="whitespace-pre-wrap break-words rounded-xl border border-bd-border bg-bd-overlay px-3 py-2 text-[11px] max-h-56 overflow-y-auto mb-3">
              {turnDetail.reasoning_content || '（无）'}
            </pre>
            <h4 className="text-xs font-medium mb-1">正文全文（content，未剥离协议块）</h4>
            <pre className="whitespace-pre-wrap break-words rounded-xl border border-bd-border bg-bd-overlay px-3 py-2 text-[11px] max-h-56 overflow-y-auto mb-3">
              {turnDetail.content || '（空）'}
            </pre>
            {turnDetail.usage && (
              <>
                <h4 className="text-xs font-medium mb-1">用量（合并）</h4>
                <pre className="whitespace-pre-wrap break-words rounded-xl border border-bd-border bg-bd-overlay px-3 py-2 text-[11px] mb-3">
                  {JSON.stringify(turnDetail.usage, null, 2)}
                </pre>
              </>
            )}
            {turnDetail.attempts && turnDetail.attempts.length > 0 && (
              <>
                <h4 className="text-xs font-medium mb-1">各次尝试</h4>
                <pre className="whitespace-pre-wrap break-words rounded-xl border border-bd-border bg-bd-overlay px-3 py-2 text-[11px] max-h-56 overflow-y-auto">
                  {JSON.stringify(turnDetail.attempts, null, 2)}
                </pre>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function Pager({
  page,
  total,
  pageSize,
  onPage,
}: {
  page: number;
  total: number;
  pageSize: number;
  onPage: (p: number) => void;
}) {
  const maxPage = Math.max(1, Math.ceil(total / pageSize));
  return (
    <div className="flex items-center justify-between text-xs">
      <p className="text-bd-subtle">
        第 {page}/{maxPage} 页 · 共 {total} 条
      </p>
      <div className="flex items-center gap-2">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
          className="px-3 py-1.5 rounded-lg border border-bd-border disabled:opacity-50"
        >
          上一页
        </button>
        <button
          type="button"
          disabled={page >= maxPage}
          onClick={() => onPage(page + 1)}
          className="px-3 py-1.5 rounded-lg border border-bd-border disabled:opacity-50"
        >
          下一页
        </button>
      </div>
    </div>
  );
}
