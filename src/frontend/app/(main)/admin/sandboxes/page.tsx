'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  deleteAdminSandbox,
  ensureAdminWorkspace,
  fetchAdminSandboxes,
  forkAdminSandbox,
  purgeExpiredAdminSandboxes,
  type AdminSandboxItem,
} from '@/lib/api/admin';
import { FlaskConical, ExternalLink, Trash2, Copy, RefreshCw } from 'lucide-react';

export default function AdminSandboxesPage() {
  const [items, setItems] = useState<AdminSandboxItem[]>([]);
  const [retentionDays, setRetentionDays] = useState(15);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sourceCode, setSourceCode] = useState('');
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAdminSandboxes();
      setItems(res.items ?? []);
      setRetentionDays(res.retention_days ?? 15);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '加载失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const formatTime = (iso?: string | null) => {
    if (!iso) return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
      d.getDate(),
    ).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(
      d.getMinutes(),
    ).padStart(2, '0')}`;
  };

  const copyText = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setNotice('已复制到剪贴板');
      setTimeout(() => setNotice(null), 2000);
    } catch {
      setNotice('复制失败');
    }
  };

  const handleFork = async () => {
    const c = sourceCode.trim().toUpperCase();
    if (!c) return;
    setWorking(true);
    setError(null);
    try {
      const data = await forkAdminSandbox(c);
      setNotice(`已创建沙箱激活码：${data.sandbox_activation_code}`);
      setSourceCode('');
      await load();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Fork 失败');
    } finally {
      setWorking(false);
    }
  };

  const handleEnterResidentWorkspace = async () => {
    setWorking(true);
    setError(null);
    try {
      const data = await ensureAdminWorkspace();
      setNotice(
        data.created
          ? `已创建常驻调试工作区：${data.activation_code}`
          : `已进入常驻调试工作区：${data.activation_code}`
      );
      window.location.href = `/explore/activate?code=${encodeURIComponent(data.activation_code)}`;
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '进入常驻工作区失败');
    } finally {
      setWorking(false);
    }
  };

  const handleDelete = async (code: string) => {
    if (!confirm(`确定删除沙箱 ${code}？磁盘目录与激活记录将一并移除。`)) return;
    setWorking(true);
    setError(null);
    try {
      await deleteAdminSandbox(code);
      await load();
      setNotice('已删除');
      setTimeout(() => setNotice(null), 2000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '删除失败');
    } finally {
      setWorking(false);
    }
  };

  const handlePurge = async () => {
    if (!confirm('清理所有已超过保留期限的沙箱？')) return;
    setWorking(true);
    setError(null);
    try {
      const { removed } = await purgeExpiredAdminSandboxes();
      await load();
      setNotice(`已清理 ${removed} 个过期沙箱`);
      setTimeout(() => setNotice(null), 3000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : '清理失败');
    } finally {
      setWorking(false);
    }
  };

  return (
    <div className="max-w-6xl">
      <div className="flex items-start gap-3 mb-8">
        <div
          className="p-3 rounded-2xl bg-violet-500/15 text-violet-600 dark:text-violet-300"
          aria-hidden
        >
          <FlaskConical className="w-7 h-7" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold text-bd-fg">调试沙箱 Fork</h1>
          <p className="text-sm text-bd-muted mt-1 max-w-2xl">
            从正式激活码复制报告与问卷到独立目录 <code className="text-xs bg-bd-overlay-md px-1 rounded">data/simple/sandboxes/</code>
            ，生成 <code className="text-xs bg-bd-overlay-md px-1 rounded">SBX</code> 前缀新码，便于以管理员身份继续对话测试。默认保留{' '}
            {retentionDays} 天，可手动删除；禁止从沙箱再次 Fork。
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 dark:bg-rose-950/30 dark:border-rose-800 px-4 py-3 text-sm text-rose-800 dark:text-rose-200">
          {error}
        </div>
      )}
      {notice && (
        <div className="mb-4 rounded-xl border border-emerald-200 bg-emerald-50 dark:bg-emerald-950/30 dark:border-emerald-800 px-4 py-3 text-sm text-emerald-800 dark:text-emerald-200">
          {notice}
        </div>
      )}

      <section className="rounded-2xl border border-bd-border bg-bd-card/60 p-6 mb-8">
        <h2 className="text-sm font-medium text-bd-fg mb-4">新建 Fork</h2>
        <div className="flex flex-wrap gap-3 items-end">
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs text-bd-muted mb-1">源激活码（正式用户）</label>
            <input
              className="w-full rounded-xl border border-bd-border bg-bd-bg px-3 py-2 text-sm text-bd-fg"
              placeholder="例如 ABCD123456"
              value={sourceCode}
              onChange={(e) => setSourceCode(e.target.value)}
              disabled={working}
            />
          </div>
          <button
            type="button"
            disabled={working || !sourceCode.trim()}
            onClick={() => void handleFork()}
            className="rounded-xl px-4 py-2 text-sm font-medium bg-violet-600 text-white hover:bg-violet-500 disabled:opacity-50"
          >
            {working ? '处理中…' : 'Fork 沙箱'}
          </button>
          <button
            type="button"
            onClick={() => void handleEnterResidentWorkspace()}
            disabled={working}
            className="rounded-xl px-4 py-2 text-sm font-medium bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-50"
          >
            进入我的常驻调试工作区
          </button>
          <button
            type="button"
            onClick={() => void load()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-xl border border-bd-border px-4 py-2 text-sm text-bd-fg hover:bg-bd-overlay-md disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            刷新列表
          </button>
          <button
            type="button"
            onClick={() => void handlePurge()}
            disabled={working}
            className="rounded-xl border border-amber-200 dark:border-amber-800 px-4 py-2 text-sm text-amber-800 dark:text-amber-200 hover:bg-amber-50 dark:hover:bg-amber-950/30"
          >
            清理过期沙箱
          </button>
        </div>
        <p className="text-xs text-bd-subtle mt-3">
          审计日志：<code>sandbox_fork_audit.jsonl</code>（项目 data/simple 下）
        </p>
      </section>

      <section className="rounded-2xl border border-bd-border bg-bd-card/60 overflow-hidden">
        <div className="px-6 py-4 border-b border-bd-border flex items-center justify-between">
          <h2 className="text-sm font-medium text-bd-fg">沙箱列表</h2>
          <span className="text-xs text-bd-muted">{items.length} 条</span>
        </div>
        {loading && !items.length ? (
          <div className="p-8 text-center text-bd-muted text-sm">加载中…</div>
        ) : items.length === 0 ? (
          <div className="p-8 text-center text-bd-muted text-sm">暂无沙箱，请在上方输入正式激活码创建。</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-bd-muted border-b border-bd-border">
                  <th className="px-4 py-3 font-medium">沙箱激活码</th>
                  <th className="px-4 py-3 font-medium">来源激活码</th>
                  <th className="px-4 py-3 font-medium">过期时间</th>
                  <th className="px-4 py-3 font-medium">状态</th>
                  <th className="px-4 py-3 font-medium text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.activation_code} className="border-b border-bd-border/80 hover:bg-bd-overlay-sm">
                    <td className="px-4 py-3 font-mono text-xs">
                      <div className="flex items-center gap-2 flex-wrap">
                        {row.activation_code}
                        <button
                          type="button"
                          className="p-1 rounded text-bd-muted hover:text-bd-fg"
                          title="复制"
                          onClick={() => void copyText(row.activation_code)}
                        >
                          <Copy className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-bd-muted">
                      {row.forked_from_code || '—'}
                    </td>
                    <td className="px-4 py-3 text-xs text-bd-muted">
                      {formatTime(row.sandbox_expires_at)}
                      {row.expired && (
                        <span className="ml-2 text-amber-600 dark:text-amber-400">已过期</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs">{row.status}</td>
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex items-center gap-1">
                        <Link
                          href={`/explore/activate?code=${encodeURIComponent(row.activation_code)}`}
                          className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-violet-600 dark:text-violet-300 hover:bg-violet-500/10"
                        >
                          <ExternalLink className="w-3.5 h-3.5" />
                          进入探索
                        </Link>
                        <button
                          type="button"
                          disabled={working}
                          className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-rose-600 dark:text-rose-400 hover:bg-rose-500/10 disabled:opacity-50"
                          onClick={() => void handleDelete(row.activation_code)}
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
