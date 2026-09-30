'use client';

/**
 * Admin · 滥用监控
 *
 * 数据流：GET/POST /api/v1/admin/abuse/config（阈值配置，保存即时生效）、
 * GET /api/v1/admin/abuse/users（触限用户，status=warned|frozen 分页）、
 * GET /api/v1/admin/abuse/users/{id}/events（事件流水）、
 * POST /api/v1/admin/abuse/users/{id}/unfreeze（解冻并恢复被冻激活码）。
 * 仅 super_admin 可访问（admin layout 统一拦截）。
 */

import { useCallback, useEffect, useState } from 'react';
import { Save, ShieldAlert } from 'lucide-react';
import {
  fetchAdminAbuseConfig,
  updateAdminAbuseConfig,
  fetchAdminAbuseUsers,
  fetchAdminAbuseUserEvents,
  unfreezeAdminAbuseUser,
  type AdminAbuseConfig,
  type AdminAbuseUserItem,
  type AdminAbuseEventItem,
} from '@/lib/api/admin';
import { getApiErrorMessage } from '@/lib/api/client';
import { toDate } from '@/lib/utils/formatTime';

const PAGE_SIZE = 20;
const EVENTS_PAGE_SIZE = 50;

type StatusTab = 'warned' | 'frozen';

type ThresholdField =
  | 'msg_per_minute'
  | 'msg_per_hour'
  | 'msg_per_day'
  | 'token_lifetime'
  | 'thread_delete_per_phase';

const THRESHOLD_META: { key: ThresholdField; label: string; desc: string }[] = [
  { key: 'msg_per_minute', label: '每分钟消息数', desc: '单用户每分钟发送消息上限' },
  { key: 'msg_per_hour', label: '每小时消息数', desc: '单用户每小时发送消息上限' },
  { key: 'msg_per_day', label: '每日消息数', desc: '单用户每天发送消息上限' },
  { key: 'token_lifetime', label: '累计 Token 用量', desc: '单用户全周期累计 token 上限' },
  { key: 'thread_delete_per_phase', label: '单阶段删除会话数', desc: '单用户单阶段删除对话上限' },
];

/** 规则 key → 中文标签（列表「触发规则」列） */
const RULE_LABELS: Record<string, string> = Object.fromEntries(
  THRESHOLD_META.map((m) => [m.key, m.label])
);

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '-';
  try {
    const d = toDate(iso);
    if (!d) return iso;
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export default function AdminAbusePage() {
  // ── 阈值配置 ──
  const [config, setConfig] = useState<AdminAbuseConfig | null>(null);
  const [draft, setDraft] = useState<Record<ThresholdField, string> | null>(null);
  const [enabledDraft, setEnabledDraft] = useState(true);
  const [configSaving, setConfigSaving] = useState(false);

  // ── 触限用户列表 ──
  const [statusTab, setStatusTab] = useState<StatusTab>('warned');
  const [items, setItems] = useState<AdminAbuseUserItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [unfreezingId, setUnfreezingId] = useState<string | null>(null);

  // ── 事件流水弹窗 ──
  const [eventsUser, setEventsUser] = useState<AdminAbuseUserItem | null>(null);
  const [events, setEvents] = useState<AdminAbuseEventItem[]>([]);
  const [eventsTotal, setEventsTotal] = useState(0);
  const [eventsPage, setEventsPage] = useState(1);
  const [eventsLoading, setEventsLoading] = useState(false);

  // ── 本地 toast（与支付管理页同款） ──
  const [toast, setToast] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    fetchAdminAbuseConfig()
      .then((cfg) => {
        setConfig(cfg);
        setEnabledDraft(cfg.enabled);
        setDraft({
          msg_per_minute: String(cfg.msg_per_minute),
          msg_per_hour: String(cfg.msg_per_hour),
          msg_per_day: String(cfg.msg_per_day),
          token_lifetime: String(cfg.token_lifetime),
          thread_delete_per_phase: String(cfg.thread_delete_per_phase),
        });
      })
      .catch((e: unknown) =>
        setToast({ type: 'error', msg: getApiErrorMessage(e, '加载阈值配置失败') })
      );
  }, []);

  const loadUsers = useCallback(async (status: StatusTab, p: number) => {
    setLoading(true);
    try {
      const res = await fetchAdminAbuseUsers({ status, page: p, page_size: PAGE_SIZE });
      setItems(res.items);
      setTotal(res.total);
      setPage(p);
    } catch (e: unknown) {
      setToast({ type: 'error', msg: getApiErrorMessage(e, '加载触限用户失败') });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUsers(statusTab, 1);
  }, [statusTab, loadUsers]);

  const handleSaveConfig = async () => {
    if (!config || !draft) return;
    const payload: Record<string, number | boolean> = { enabled: enabledDraft };
    for (const meta of THRESHOLD_META) {
      const n = Math.floor(Number(draft[meta.key]));
      const range = config.ranges?.[meta.key];
      const min = range?.min ?? 0;
      const max = range?.max;
      if (!Number.isFinite(n) || n < min || (max != null && n > max)) {
        setToast({
          type: 'error',
          msg: `「${meta.label}」需为 ${min}${max != null ? `-${max}` : ' 以上'} 的整数`,
        });
        return;
      }
      payload[meta.key] = n;
    }
    setConfigSaving(true);
    try {
      const saved = await updateAdminAbuseConfig(payload);
      setConfig(saved);
      setToast({ type: 'success', msg: '已保存并即时生效' });
    } catch (e: unknown) {
      setToast({ type: 'error', msg: getApiErrorMessage(e, '保存失败') });
    } finally {
      setConfigSaving(false);
    }
  };

  const handleUnfreeze = async (u: AdminAbuseUserItem) => {
    const label = u.username || u.email || u.user_id;
    if (!confirm(`确定解冻并恢复该用户（${label}）的聊天功能吗？被冻结的激活码将一并恢复。`))
      return;
    setUnfreezingId(u.user_id);
    try {
      const res = await unfreezeAdminAbuseUser(u.user_id);
      setToast({
        type: 'success',
        msg: res.restored_code
          ? `已解冻，激活码 ${res.restored_code} 已恢复`
          : '已解冻恢复',
      });
      await loadUsers(statusTab, page);
    } catch (e: unknown) {
      setToast({ type: 'error', msg: getApiErrorMessage(e, '解冻失败') });
    } finally {
      setUnfreezingId(null);
    }
  };

  const loadEvents = useCallback(async (userId: string, p: number) => {
    setEventsLoading(true);
    try {
      const res = await fetchAdminAbuseUserEvents(userId, {
        page: p,
        page_size: EVENTS_PAGE_SIZE,
      });
      setEvents(res.items);
      setEventsTotal(res.total);
      setEventsPage(p);
    } catch (e: unknown) {
      setToast({ type: 'error', msg: getApiErrorMessage(e, '加载事件流水失败') });
    } finally {
      setEventsLoading(false);
    }
  }, []);

  const openEvents = (u: AdminAbuseUserItem) => {
    setEventsUser(u);
    setEvents([]);
    setEventsTotal(0);
    setEventsPage(1);
    void loadEvents(u.user_id, 1);
  };

  const userLabel = (u: AdminAbuseUserItem) => u.username || u.email || u.user_id;

  return (
    <div className="space-y-6">
      {/* Header */}
      <header className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="grid h-10 w-10 place-items-center rounded-xl bg-[#fdf0e7] text-[#c2622a]">
            <ShieldAlert size={20} strokeWidth={2} />
          </span>
          <div>
            <h1 className="text-xl font-semibold text-bd-fg">滥用监控</h1>
            <p className="mt-0.5 text-sm text-neutral-500">
              频率 / 用量阈值配置与触限用户处置，配置保存即时生效
            </p>
          </div>
        </div>
      </header>

      {/* 阈值配置卡片 */}
      <section className="rounded-2xl bg-bd-card/80 backdrop-blur-lg border border-bd-border px-6 py-5 shadow-sm">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-sm font-semibold" style={{ color: 'var(--bd-fg)' }}>
            阈值配置
          </h2>
          <button
            type="button"
            onClick={handleSaveConfig}
            disabled={configSaving || !config || !draft}
            className="bd-btn-black inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            <Save size={14} strokeWidth={2.2} /> {configSaving ? '保存中…' : '保存配置'}
          </button>
        </div>

        <label className="mt-4 flex items-center gap-2 text-sm" style={{ color: 'var(--bd-fg)' }}>
          <input
            type="checkbox"
            checked={enabledDraft}
            onChange={(e) => setEnabledDraft(e.target.checked)}
            className="h-4 w-4 accent-bd-ui-accent"
          />
          启用滥用检测（关闭后不再触发警告 / 冻结）
        </label>

        <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {THRESHOLD_META.map((meta) => {
            const range = config?.ranges?.[meta.key];
            const def = config?.defaults?.[meta.key];
            return (
              <div key={meta.key}>
                <label
                  className="mb-1 block text-xs font-medium"
                  style={{ color: 'var(--bd-fg)' }}
                >
                  {meta.label}
                </label>
                <input
                  type="number"
                  inputMode="numeric"
                  value={draft?.[meta.key] ?? ''}
                  onChange={(e) =>
                    setDraft((prev) => (prev ? { ...prev, [meta.key]: e.target.value } : prev))
                  }
                  className="w-full px-3 py-2 rounded-lg text-sm border outline-none focus:ring-2 focus:ring-bd-ui-accent/30"
                  style={{
                    background: 'var(--bd-overlay-md, #fff)',
                    borderColor: 'var(--bd-border)',
                    color: 'var(--bd-fg)',
                  }}
                />
                <p className="mt-1 text-[11px] leading-snug text-bd-subtle">
                  {meta.desc}
                  {typeof def === 'number' ? ` · 默认 ${def}` : ''}
                  {range && (range.min != null || range.max != null)
                    ? ` · 范围 ${range.min ?? 0}~${range.max ?? '∞'}`
                    : ''}
                </p>
              </div>
            );
          })}
        </div>
      </section>

      {/* 触限用户列表 */}
      <section className="rounded-2xl bg-bd-card/80 backdrop-blur-lg border border-bd-border px-6 py-5 shadow-sm">
        <div className="mb-4 flex items-center gap-2">
          {(
            [
              { key: 'warned', label: '已警告' },
              { key: 'frozen', label: '已冻结' },
            ] as { key: StatusTab; label: string }[]
          ).map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setStatusTab(tab.key)}
              className={`rounded-full px-4 py-1.5 text-sm font-medium transition-colors ${
                statusTab === tab.key
                  ? 'bg-bd-ui-accent text-bd-ui-accent-fg'
                  : 'text-bd-muted hover:text-bd-fg hover:bg-bd-overlay-md'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {loading ? (
          <p className="text-xs text-bd-subtle">加载中…</p>
        ) : items.length === 0 ? (
          <p className="text-xs text-bd-subtle">
            {statusTab === 'warned' ? '暂无被警告的用户。' : '暂无被冻结的用户。'}
          </p>
        ) : (
          <div className="overflow-x-auto -mx-2">
            <table className="min-w-full text-xs border-collapse">
              <thead>
                <tr className="border-b border-bd-border text-[11px] text-bd-subtle">
                  <th className="px-2 py-2 text-left font-medium">用户</th>
                  <th className="px-2 py-2 text-left font-medium">状态</th>
                  <th className="px-2 py-2 text-left font-medium">触发规则</th>
                  <th className="px-2 py-2 text-left font-medium">警告时间</th>
                  <th className="px-2 py-2 text-left font-medium">冻结时间</th>
                  <th className="px-2 py-2 text-left font-medium">被冻激活码</th>
                  <th className="px-2 py-2 text-left font-medium">24h 消息数</th>
                  <th className="px-2 py-2 text-left font-medium">累计删除数</th>
                  <th className="px-2 py-2 text-left font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((u) => (
                  <tr key={u.user_id} className="border-b border-bd-border/60 last:border-0">
                    <td className="px-2 py-2">
                      <div className="font-medium" style={{ color: 'var(--bd-fg)' }}>
                        {userLabel(u)}
                      </div>
                      {u.email && u.username ? (
                        <div className="text-[11px] text-bd-subtle">{u.email}</div>
                      ) : null}
                    </td>
                    <td className="px-2 py-2">
                      {u.status === 'frozen' ? (
                        <span className="inline-flex rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-600">
                          已冻结
                        </span>
                      ) : (
                        <span className="inline-flex rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700">
                          已警告
                        </span>
                      )}
                    </td>
                    <td className="px-2 py-2" style={{ color: 'var(--bd-fg)' }}>
                      {RULE_LABELS[u.frozen_rule || u.warned_rule || ''] ||
                        u.frozen_rule ||
                        u.warned_rule ||
                        '-'}
                    </td>
                    <td className="px-2 py-2 text-bd-subtle">{fmtTime(u.warned_at)}</td>
                    <td className="px-2 py-2 text-bd-subtle">{fmtTime(u.frozen_at)}</td>
                    <td className="px-2 py-2 font-mono text-[11px]" style={{ color: 'var(--bd-fg)' }}>
                      {u.frozen_activation_code || '-'}
                    </td>
                    <td className="px-2 py-2" style={{ color: 'var(--bd-fg)' }}>
                      {u.messages_24h ?? '-'}
                    </td>
                    <td className="px-2 py-2" style={{ color: 'var(--bd-fg)' }}>
                      {u.deletes_total ?? '-'}
                    </td>
                    <td className="px-2 py-2 whitespace-nowrap">
                      <button
                        type="button"
                        onClick={() => openEvents(u)}
                        className="mr-2 rounded-lg border border-bd-border px-2.5 py-1 text-[11px] hover:bg-bd-overlay-md"
                        style={{ color: 'var(--bd-fg)' }}
                      >
                        查看事件
                      </button>
                      {u.status === 'frozen' && (
                        <button
                          type="button"
                          onClick={() => handleUnfreeze(u)}
                          disabled={unfreezingId === u.user_id}
                          className="rounded-lg bg-emerald-600 px-2.5 py-1 text-[11px] font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
                        >
                          {unfreezingId === u.user_id ? '解冻中…' : '解冻恢复'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* 分页 */}
        {total > PAGE_SIZE && (
          <div className="mt-4 flex items-center justify-center gap-4 text-xs text-bd-muted">
            <button
              type="button"
              onClick={() => loadUsers(statusTab, page - 1)}
              disabled={page <= 1 || loading}
              className="rounded-lg border border-bd-border px-3 py-1.5 disabled:opacity-50 hover:bg-bd-overlay-md"
            >
              上一页
            </button>
            <span>
              第 {page} 页 / 共 {Math.ceil(total / PAGE_SIZE)} 页（总 {total} 条）
            </span>
            <button
              type="button"
              onClick={() => loadUsers(statusTab, page + 1)}
              disabled={page * PAGE_SIZE >= total || loading}
              className="rounded-lg border border-bd-border px-3 py-1.5 disabled:opacity-50 hover:bg-bd-overlay-md"
            >
              下一页
            </button>
          </div>
        )}
      </section>

      {/* 事件流水弹窗 */}
      {eventsUser && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center px-4">
          <button
            type="button"
            className="absolute inset-0 bg-stone-900/40"
            aria-label="关闭"
            onClick={() => setEventsUser(null)}
          />
          <div className="relative flex max-h-[80vh] w-full max-w-2xl flex-col rounded-2xl border border-bd-border bg-bd-card p-6 shadow-xl">
            <div className="mb-4 flex items-center justify-between gap-4">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--bd-fg)' }}>
                事件流水 · {userLabel(eventsUser)}
              </h3>
              <button
                type="button"
                onClick={() => setEventsUser(null)}
                className="rounded-lg border border-bd-border px-3 py-1 text-xs hover:bg-bd-overlay-md"
                style={{ color: 'var(--bd-fg)' }}
              >
                关闭
              </button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto">
              {eventsLoading ? (
                <p className="text-xs text-bd-subtle">加载中…</p>
              ) : events.length === 0 ? (
                <p className="text-xs text-bd-subtle">暂无事件记录。</p>
              ) : (
                <table className="min-w-full text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-bd-border text-[11px] text-bd-subtle">
                      <th className="px-2 py-2 text-left font-medium">时间</th>
                      <th className="px-2 py-2 text-left font-medium">事件类型</th>
                      <th className="px-2 py-2 text-left font-medium">阶段</th>
                      <th className="px-2 py-2 text-left font-medium">详情</th>
                    </tr>
                  </thead>
                  <tbody>
                    {events.map((ev) => (
                      <tr key={ev.id} className="border-b border-bd-border/60 last:border-0">
                        <td className="px-2 py-2 whitespace-nowrap text-bd-subtle">
                          {fmtTime(ev.created_at)}
                        </td>
                        <td className="px-2 py-2 font-mono text-[11px]" style={{ color: 'var(--bd-fg)' }}>
                          {RULE_LABELS[ev.event_type] || ev.event_type}
                        </td>
                        <td className="px-2 py-2" style={{ color: 'var(--bd-fg)' }}>
                          {ev.phase || '-'}
                        </td>
                        <td
                          className="px-2 py-2 max-w-[280px] truncate text-bd-subtle"
                          title={ev.detail || ''}
                        >
                          {ev.detail || '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            {eventsTotal > EVENTS_PAGE_SIZE && (
              <div className="mt-4 flex items-center justify-center gap-4 text-xs text-bd-muted">
                <button
                  type="button"
                  onClick={() => loadEvents(eventsUser.user_id, eventsPage - 1)}
                  disabled={eventsPage <= 1 || eventsLoading}
                  className="rounded-lg border border-bd-border px-3 py-1.5 disabled:opacity-50 hover:bg-bd-overlay-md"
                >
                  上一页
                </button>
                <span>
                  第 {eventsPage} 页 / 共 {Math.ceil(eventsTotal / EVENTS_PAGE_SIZE)} 页
                </span>
                <button
                  type="button"
                  onClick={() => loadEvents(eventsUser.user_id, eventsPage + 1)}
                  disabled={eventsPage * EVENTS_PAGE_SIZE >= eventsTotal || eventsLoading}
                  className="rounded-lg border border-bd-border px-3 py-1.5 disabled:opacity-50 hover:bg-bd-overlay-md"
                >
                  下一页
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Toast */}
      {toast && (
        <div
          role="alert"
          className={`fixed bottom-8 left-1/2 -translate-x-1/2 px-5 py-3 rounded-xl text-sm font-medium shadow-lg z-[110] ${
            toast.type === 'success'
              ? 'bg-emerald-600/95 text-white'
              : 'bg-red-600/95 text-white'
          }`}
          style={{ animation: 'toast-in 0.25s ease-out' }}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}
