'use client';

import { useCallback, useEffect, useState } from 'react';
import { Plus, Pencil, Trash2, Power, X } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import {
  adminListSiteNotices,
  adminCreateSiteNotice,
  adminUpdateSiteNotice,
  adminDeleteSiteNotice,
  adminToggleSiteNotice,
  getMaintenanceStatus,
  setMaintenanceMode,
  type SiteNoticeItem,
  type SiteNoticePayload,
  type SiteNoticeChannel,
} from '@/lib/api/siteNotices';
import { getApiErrorMessage } from '@/lib/api/client';

const SEVERITY_LABEL: Record<string, string> = {
  info: '信息',
  warn: '提醒',
  urgent: '紧急',
};

const SEVERITY_CLASS: Record<string, string> = {
  info: 'bg-sky-100 text-sky-700',
  warn: 'bg-amber-100 text-amber-700',
  urgent: 'bg-red-100 text-red-700',
};

function fmtTime(s: string | null): string {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString('zh-CN', { hour12: false });
  } catch {
    return s;
  }
}

export default function AdminSiteNoticesPage() {
  const { user, isAuthenticated } = useAuthStore();

  const [items, setItems] = useState<SiteNoticeItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 维护模式（false = 不在维护；null 仅在初次加载时短暂存在，但按钮仍可点）
  const [maintOn, setMaintOn] = useState<boolean>(false);
  const [maintLoading, setMaintLoading] = useState(false);
  const [maintReason, setMaintReason] = useState('例行升级');
  const [maintEnd, setMaintEnd] = useState('');
  // 表单弹层
  const [editing, setEditing] = useState<SiteNoticeItem | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await adminListSiteNotices({ page, page_size: pageSize });
      setItems(res.items);
      setTotal(res.total);
    } catch (e: any) {
      setError(getApiErrorMessage(e, '加载失败'));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize]);

  useEffect(() => {
    if (!isAuthenticated || !user?.is_super_admin) return;
    loadList();
    // 加载维护模式状态（失败不阻塞按钮，默认显示「正常运行」）
    getMaintenanceStatus()
      .then((s) => setMaintOn(!!s.is_on))
      .catch((e) => console.warn('[maint] status fetch failed:', e));
  }, [loadList, isAuthenticated, user]);

  const onMaintToggle = async () => {
    console.log('[maint-toggle] clicked, current state=', maintOn);
    setMaintLoading(true);
    setError(null);
    try {
      const action: 'on' | 'off' = maintOn ? 'off' : 'on';
      const payload: { action: 'on' | 'off'; end_at?: string; reason?: string } = { action };
      if (action === 'on') {
        payload.reason = maintReason || '例行升级';
        if (maintEnd) payload.end_at = maintEnd;
      }
      const res = await setMaintenanceMode(payload);
      console.log('[maint-toggle] response:', res);
      // 切换成功 → 直接更新本地状态（不依赖后续 status 查询）
      setMaintOn(action === 'on');
      if (action === 'on') {
        alert(
          '✅ 已进入维护模式\n\n用户访问站点会看到维护页。\n本浏览器已自动设置绕过 cookie，可走 HTTPS 正常验证。\n\n验证用户视角：用无痕窗口访问站点。'
        );
      } else {
        alert('✅ 已退出维护模式\n\n用户恢复访问。');
      }
    } catch (e: any) {
      console.error('[maint-toggle] failed:', e);
      setError(getApiErrorMessage(e, '维护模式切换失败'));
    } finally {
      setMaintLoading(false);
    }
  };

  const openCreate = () => {
    setEditing(null);
    setFormOpen(true);
  };

  const openEdit = (n: SiteNoticeItem) => {
    setEditing(n);
    setFormOpen(true);
  };

  const onToggle = async (n: SiteNoticeItem) => {
    try {
      await adminToggleSiteNotice(n.id);
      await loadList();
    } catch (e: any) {
      setError(getApiErrorMessage(e, '切换失败'));
    }
  };

  const onDelete = async (n: SiteNoticeItem) => {
    if (!confirm(`确认删除公告「${n.title}」？此操作不可撤销。`)) return;
    try {
      await adminDeleteSiteNotice(n.id);
      await loadList();
    } catch (e: any) {
      setError(getApiErrorMessage(e, '删除失败'));
    }
  };

  // 鉴权占位(与现有 admin 页一致)
  if (!isAuthenticated || !user?.is_super_admin) {
    return <div className="p-6 text-sm text-bd-muted">需要超级管理员权限</div>;
  }

  return (
    <div className="p-6 space-y-4">
      {/* 头部 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 600, margin: 0 }}>站内公告</h1>
          <p style={{ fontSize: 12, opacity: 0.6, marginTop: 4 }}>
            维护通知 / 公告 banner,显示在所有页面顶部。共 {total} 条
          </p>
        </div>
        <button
          onClick={openCreate}
          style={{
            backgroundColor: '#2563eb',
            color: '#fff',
            padding: '8px 16px',
            borderRadius: 6,
            fontSize: 14,
            fontWeight: 500,
            border: 'none',
            cursor: 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <Plus size={16} /> 新建公告
        </button>
      </div>

      {error && <div className="p-3 bg-red-50 text-red-700 text-sm rounded">{error}</div>}

      {/* 维护模式卡片 */}
      <div
        style={{
          padding: 16,
          borderRadius: 8,
          border: '1px solid',
          borderColor: maintOn ? '#fca5a5' : '#e5e7eb',
          background: maintOn ? '#fef2f2' : '#f9fafb',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ fontWeight: 600, fontSize: 14 }}>维护模式</div>
          <span
            style={{
              padding: '2px 10px',
              borderRadius: 12,
              fontSize: 12,
              background: maintOn ? '#dc2626' : '#10b981',
              color: '#fff',
            }}
          >
            {maintOn ? '维护中' : '正常运行'}
          </span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            {!maintOn && (
              <>
                <input
                  type="text"
                  placeholder="原因（如：数据库升级）"
                  value={maintReason}
                  onChange={(e) => setMaintReason(e.target.value)}
                  style={{
                    padding: '6px 10px',
                    fontSize: 13,
                    border: '1px solid #ccc',
                    borderRadius: 4,
                    width: 180,
                  }}
                />
                <input
                  type="text"
                  placeholder="恢复时间（如：04:00）"
                  value={maintEnd}
                  onChange={(e) => setMaintEnd(e.target.value)}
                  style={{
                    padding: '6px 10px',
                    fontSize: 13,
                    border: '1px solid #ccc',
                    borderRadius: 4,
                    width: 140,
                  }}
                />
              </>
            )}
            <button
              onClick={onMaintToggle}
              disabled={maintLoading}
              style={{
                padding: '6px 16px',
                fontSize: 13,
                fontWeight: 500,
                border: 'none',
                borderRadius: 6,
                cursor: maintLoading ? 'not-allowed' : 'pointer',
                opacity: maintLoading ? 0.5 : 1,
                backgroundColor: maintOn ? '#10b981' : '#dc2626',
                color: '#fff',
              }}
            >
              {maintLoading ? '切换中…' : maintOn ? '退出维护模式' : '进入维护模式'}
            </button>
          </div>
        </div>
        <p style={{ fontSize: 12, color: '#6b7280', marginTop: 8 }}>
          进入维护模式后，用户访问站点会看到静态维护页（nginx 拦截）。
          你的浏览器会自动设置绕过 cookie，可走 HTTPS 正常验证。
        </p>
      </div>

      {/* 列表 */}
      <div className="bg-bd-surface rounded-lg border border-bd-border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-bd-surface-2 text-xs text-bd-muted">
            <tr>
              <th className="text-left p-3">标题</th>
              <th className="text-left p-3">类型</th>
              <th className="text-left p-3">级别</th>
              <th className="text-left p-3">生效窗口</th>
              <th className="text-left p-3">状态</th>
              <th className="text-right p-3">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={6} className="p-6 text-center text-bd-muted">
                  加载中…
                </td>
              </tr>
            )}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={6} className="p-6 text-center text-bd-muted">
                  暂无公告
                </td>
              </tr>
            )}
            {!loading &&
              items.map((n) => (
                <tr key={n.id} className="border-t border-bd-border hover:bg-bd-surface-2">
                  <td className="p-3 font-medium">{n.title}</td>
                  <td className="p-3 text-bd-muted">{n.type}</td>
                  <td className="p-3">
                    <span className={`px-2 py-0.5 rounded text-xs ${SEVERITY_CLASS[n.severity]}`}>
                      {SEVERITY_LABEL[n.severity] ?? n.severity}
                    </span>
                  </td>
                  <td className="p-3 text-xs text-bd-muted">
                    <div>{fmtTime(n.start_at)}</div>
                    <div>~ {fmtTime(n.end_at)}</div>
                  </td>
                  <td className="p-3">
                    <span
                      className={`px-2 py-0.5 rounded text-xs ${
                        n.is_active ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-600'
                      }`}
                    >
                      {n.is_active ? '启用' : '停用'}
                    </span>
                  </td>
                  <td className="p-3 text-right">
                    <div className="inline-flex items-center gap-1">
                      <button
                        onClick={() => openEdit(n)}
                        className="p-1.5 rounded hover:bg-bd-surface-3"
                        title="编辑"
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => onToggle(n)}
                        className="p-1.5 rounded hover:bg-bd-surface-3"
                        title={n.is_active ? '停用' : '启用'}
                      >
                        <Power className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => onDelete(n)}
                        className="p-1.5 rounded hover:bg-red-50 text-red-600"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      {/* 分页 */}
      {total > pageSize && (
        <div className="flex items-center justify-center gap-2 text-sm">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="px-3 py-1 rounded border disabled:opacity-40"
          >
            上一页
          </button>
          <span className="text-bd-muted">
            {page} / {Math.ceil(total / pageSize)}
          </span>
          <button
            disabled={page * pageSize >= total}
            onClick={() => setPage((p) => p + 1)}
            className="px-3 py-1 rounded border disabled:opacity-40"
          >
            下一页
          </button>
        </div>
      )}

      {/* 表单弹层 */}
      {formOpen && (
        <NoticeForm
          editing={editing}
          onClose={() => setFormOpen(false)}
          onSaved={async () => {
            setFormOpen(false);
            await loadList();
          }}
        />
      )}
    </div>
  );
}

// ── 表单弹层 ────────────────────────────────────────────
function NoticeForm({
  editing,
  onClose,
  onSaved,
}: {
  editing: SiteNoticeItem | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(editing?.title ?? '');
  const [contentMd, setContentMd] = useState(editing?.content_md ?? '');
  const [severity, setSeverity] = useState<'info' | 'warn' | 'urgent'>(editing?.severity ?? 'info');
  const [startAt, setStartAt] = useState(toLocalInput(editing?.start_at));
  const [endAt, setEndAt] = useState(toLocalInput(editing?.end_at));
  const [dismissible, setDismissible] = useState(editing?.dismissible ?? true);
  const [isActive, setIsActive] = useState(editing?.is_active ?? true);
  const [channels, setChannels] = useState<SiteNoticeChannel[]>(editing?.channels ?? []);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    console.log('[site-notice] submit clicked, title=', title);
    if (!title.trim()) {
      setError('请输入标题');
      return;
    }
    setSaving(true);
    setError(null);
    const payload: SiteNoticePayload = {
      title: title.trim(),
      content_md: contentMd.trim() || undefined,
      severity,
      start_at: startAt ? new Date(startAt).toISOString() : undefined,
      end_at: endAt ? new Date(endAt).toISOString() : undefined,
      dismissible,
      is_active: isActive,
      channels: channels.filter((c) => c.url || c.qr_url),
    };
    console.log('[site-notice] payload=', payload);
    try {
      if (editing) {
        await adminUpdateSiteNotice(editing.id, payload);
      } else {
        await adminCreateSiteNotice(payload);
      }
      console.log('[site-notice] saved ok');
      onSaved();
    } catch (e: any) {
      console.error('[site-notice] save failed:', e);
      setError(getApiErrorMessage(e, '保存失败'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[100] bg-black/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-bd-surface rounded-xl shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between p-5 border-b border-bd-border sticky top-0 bg-bd-surface">
          <h2 className="text-lg font-semibold">{editing ? '编辑公告' : '新建公告'}</h2>
          <button onClick={onClose} className="p-1 rounded hover:bg-bd-surface-2">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-4">
          {error && <div className="p-3 bg-red-50 text-red-700 text-sm rounded">{error}</div>}

          <Field label="标题（顶部窄条显示一行）">
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={120}
              className="w-full px-3 py-2 rounded border bg-transparent text-sm"
              placeholder="例:7月5日 02:00–04:00 系统升级维护"
            />
          </Field>

          <Field label="正文（点击「了解更多」后弹 Modal 显示）">
            <textarea
              value={contentMd}
              onChange={(e) => setContentMd(e.target.value)}
              rows={5}
              className="w-full px-3 py-2 rounded border bg-transparent text-sm"
              placeholder="详细说明维护内容、影响范围等"
            />
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <Field label="级别">
              <select
                value={severity}
                onChange={(e) => setSeverity(e.target.value as any)}
                className="w-full px-3 py-2 rounded border bg-transparent text-sm"
              >
                <option value="info">信息（天蓝）</option>
                <option value="warn">提醒（琥珀）</option>
                <option value="urgent">紧急（红橙）</option>
              </select>
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <Field label="生效时间（留空=立即）">
              <input
                type="datetime-local"
                value={startAt}
                onChange={(e) => setStartAt(e.target.value)}
                className="w-full px-3 py-2 rounded border bg-transparent text-sm"
              />
            </Field>
            <Field label="结束时间（留空=永久）">
              <input
                type="datetime-local"
                value={endAt}
                onChange={(e) => setEndAt(e.target.value)}
                className="w-full px-3 py-2 rounded border bg-transparent text-sm"
              />
            </Field>
          </div>

          <div className="flex gap-6">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={dismissible}
                onChange={(e) => setDismissible(e.target.checked)}
              />
              允许用户关闭
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={isActive}
                onChange={(e) => setIsActive(e.target.checked)}
              />
              立即启用
            </label>
          </div>

          {/* 渠道入口 */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-medium">渠道入口（Modal 底部展示）</label>
              <button
                onClick={() =>
                  setChannels([...channels, { type: 'blog', url: '', label: '' }])
                }
                className="text-xs flex items-center gap-1 text-bd-accent"
              >
                <Plus className="w-3 h-3" /> 添加渠道
              </button>
            </div>
            <div className="space-y-2">
              {channels.length === 0 && (
                <p className="text-xs text-bd-muted">暂无渠道入口</p>
              )}
              {channels.map((ch, i) => (
                <div key={i} className="flex gap-2 items-center">
                  <select
                    value={ch.type}
                    onChange={(e) => updateChannel(channels, setChannels, i, { type: e.target.value })}
                    className="px-2 py-1 rounded border bg-transparent text-xs"
                  >
                    <option value="wechat">微信群(图)</option>
                    <option value="blog">博客</option>
                    <option value="xiaohongshu">小红书</option>
                    <option value="other">其他</option>
                  </select>
                  <input
                    type="text"
                    value={ch.label ?? ''}
                    onChange={(e) => updateChannel(channels, setChannels, i, { label: e.target.value })}
                    placeholder="名称(可选)"
                    className="px-2 py-1 rounded border bg-transparent text-xs w-24"
                  />
                  {ch.type === 'wechat' ? (
                    <input
                      type="text"
                      value={ch.qr_url ?? ''}
                      onChange={(e) => updateChannel(channels, setChannels, i, { qr_url: e.target.value })}
                      placeholder="二维码图片 URL"
                      className="flex-1 px-2 py-1 rounded border bg-transparent text-xs"
                    />
                  ) : (
                    <input
                      type="text"
                      value={ch.url ?? ''}
                      onChange={(e) => updateChannel(channels, setChannels, i, { url: e.target.value })}
                      placeholder="链接 URL"
                      className="flex-1 px-2 py-1 rounded border bg-transparent text-xs"
                    />
                  )}
                  <button
                    onClick={() => setChannels(channels.filter((_, idx) => idx !== i))}
                    className="text-red-500 p-1"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, padding: 16, borderTop: '1px solid rgba(0,0,0,0.08)', position: 'sticky', bottom: 0, background: 'var(--bd-surface, #fff)', zIndex: 10 }}>
          <button
            onClick={onClose}
            style={{ padding: '8px 16px', borderRadius: 6, border: '1px solid #ccc', background: 'transparent', fontSize: 14, cursor: 'pointer' }}
          >
            取消
          </button>
          <button
            onClick={submit}
            disabled={saving}
            style={{ padding: '8px 16px', borderRadius: 6, border: 'none', backgroundColor: '#2563eb', color: '#fff', fontSize: 14, cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.5 : 1 }}
          >
            {saving ? '保存中…' : '保存'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium mb-1">{label}</label>
      {children}
    </div>
  );
}

function updateChannel(
  list: SiteNoticeChannel[],
  setter: (v: SiteNoticeChannel[]) => void,
  idx: number,
  patch: Partial<SiteNoticeChannel>
) {
  const next = list.map((c, i) => (i === idx ? { ...c, ...patch } : c));
  setter(next);
}

/** ISO -> datetime-local input value（本地时区） */
function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return '';
  }
}
