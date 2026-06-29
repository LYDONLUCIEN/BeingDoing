'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  sendNotificationEmail,
  getNotificationStatus,
  listNotificationTasks,
  type NotificationUserFilter,
  type NotificationTaskStatus,
  type NotificationTaskListItem,
} from '@/lib/api/admin';
import { formatUTC } from '@/lib/utils/formatTime';

type ActiveFilter = 'all' | 'active' | 'inactive';
type ProfileFilter = 'all' | 'completed' | 'incomplete';

const POLL_INTERVAL_MS = 2000;

export default function AdminNotificationsPage() {
  const router = useRouter();

  // 筛选条件
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>('all');
  const [profileFilter, setProfileFilter] = useState<ProfileFilter>('all');
  const [createdAfter, setCreatedAfter] = useState('');

  // 邮件内容
  const [subject, setSubject] = useState('');
  const [body, setBody] = useState('');

  // 当前任务进度
  const [currentTask, setCurrentTask] = useState<NotificationTaskStatus | null>(null);
  const [polling, setPolling] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 历史列表
  const [history, setHistory] = useState<NotificationTaskListItem[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyPageSize] = useState(10);

  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const buildFilter = (): NotificationUserFilter => {
    const f: NotificationUserFilter = {};
    if (activeFilter !== 'all') f.is_active = activeFilter === 'active';
    if (profileFilter !== 'all') f.profile_completed = profileFilter === 'completed';
    if (createdAfter) f.created_after = createdAfter;
    return f;
  };

  const handleSend = async () => {
    if (!subject.trim() || !body.trim()) {
      setError('主题和正文不能为空');
      return;
    }
    setError(null);
    setInfo(null);
    setSending(true);
    try {
      const res = await sendNotificationEmail({
        subject: subject.trim(),
        body: body.trim(),
        user_filter: buildFilter(),
      });
      setInfo(`任务已创建：${res.task_id}，正在后台发送...`);
      // 立即开始轮询
      setCurrentTask(null);
      setPolling(true);
      pollTask(res.task_id);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '创建任务失败';
      setError(msg);
    } finally {
      setSending(false);
    }
  };

  const pollTask = useCallback(async (taskId: string) => {
    try {
      const status = await getNotificationStatus(taskId);
      setCurrentTask(status);
      if (status.status === 'running' || status.status === 'pending') {
        pollTimer.current = setTimeout(() => pollTask(taskId), POLL_INTERVAL_MS);
      } else {
        // 完成/中断/失败，停止轮询并刷新历史
        setPolling(false);
        loadHistory(historyPage);
      }
    } catch (e: unknown) {
      setPolling(false);
      const msg = e instanceof Error ? e.message : '查询进度失败';
      setError(msg);
    }
  }, [historyPage]);

  useEffect(() => {
    return () => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
    };
  }, []);

  const loadHistory = useCallback(async (page: number) => {
    try {
      const res = await listNotificationTasks({ page, page_size: historyPageSize });
      setHistory(res.items);
      setHistoryTotal(res.total);
      setHistoryPage(page);
    } catch (e: unknown) {
      // 静默失败，不打断用户
    }
  }, [historyPageSize]);

  useEffect(() => {
    loadHistory(1);
  }, [loadHistory]);

  // 查看历史任务进度
  const viewHistoryTask = async (taskId: string) => {
    setPolling(false);
    if (pollTimer.current) clearTimeout(pollTimer.current);
    try {
      const status = await getNotificationStatus(taskId);
      setCurrentTask(status);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : '查询失败';
      setError(msg);
    }
  };

  const progressPct = currentTask && currentTask.total > 0
    ? Math.round(((currentTask.sent + currentTask.failed) / currentTask.total) * 100)
    : 0;

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="mx-auto max-w-5xl space-y-6">
        <header className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-gray-900">通知邮件群发</h1>
          <button
            onClick={() => router.push('/admin')}
            className="rounded border border-gray-300 px-3 py-1 text-sm text-gray-600 hover:bg-gray-100"
          >
            返回
          </button>
        </header>

        {/* 创建任务区 */}
        <section className="rounded-lg bg-white p-6 shadow-sm">
          <h2 className="mb-4 text-lg font-semibold text-gray-800">新建群发任务</h2>

          {/* 收件人筛选 */}
          <div className="mb-4 grid grid-cols-1 gap-4 md:grid-cols-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">用户状态</label>
              <select
                value={activeFilter}
                onChange={(e) => setActiveFilter(e.target.value as ActiveFilter)}
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="all">全部用户</option>
                <option value="active">仅活跃用户</option>
                <option value="inactive">仅禁用用户</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">资料完成度</label>
              <select
                value={profileFilter}
                onChange={(e) => setProfileFilter(e.target.value as ProfileFilter)}
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              >
                <option value="all">不限</option>
                <option value="completed">已完成资料</option>
                <option value="incomplete">未完成资料</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">注册时间晚于</label>
              <input
                type="date"
                value={createdAfter}
                onChange={(e) => setCreatedAfter(e.target.value)}
                className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
              />
            </div>
          </div>

          {/* 邮件内容 */}
          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-gray-700">邮件主题</label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              maxLength={255}
              placeholder="例如：系统维护通知"
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
          </div>
          <div className="mb-4">
            <label className="mb-1 block text-sm font-medium text-gray-700">邮件正文（纯文本）</label>
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={6}
              placeholder="例如：尊敬的用户，系统将于今晚 22:00 进行维护升级..."
              className="w-full rounded border border-gray-300 px-3 py-2 text-sm"
            />
          </div>

          {error && <div className="mb-3 rounded bg-red-50 p-2 text-sm text-red-700">{error}</div>}
          {info && <div className="mb-3 rounded bg-green-50 p-2 text-sm text-green-700">{info}</div>}

          <button
            onClick={handleSend}
            disabled={sending}
            className="rounded bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {sending ? '创建中...' : '发送'}
          </button>
        </section>

        {/* 当前任务进度 */}
        {currentTask && (
          <section className="rounded-lg bg-white p-6 shadow-sm">
            <h2 className="mb-4 text-lg font-semibold text-gray-800">任务进度</h2>
            <div className="mb-3 flex flex-wrap items-center gap-4 text-sm text-gray-700">
              <span>任务ID：{currentTask.task_id.slice(0, 8)}...</span>
              <span>主题：{currentTask.subject}</span>
              <span>
                状态：
                <StatusBadge status={currentTask.status} />
              </span>
            </div>
            <div className="mb-2 flex items-center gap-4 text-sm">
              <span>总计 {currentTask.total}</span>
              <span className="text-green-600">成功 {currentTask.sent}</span>
              <span className="text-red-600">失败 {currentTask.failed}</span>
              {polling && <span className="text-indigo-600">发送中...</span>}
            </div>
            {/* 进度条 */}
            <div className="mb-4 h-3 w-full overflow-hidden rounded-full bg-gray-200">
              <div
                className="h-full bg-indigo-600 transition-all"
                style={{ width: `${progressPct}%` }}
              />
            </div>
            {/* 收件人明细（最多显示前 50 条） */}
            {currentTask.recipients.length > 0 && (
              <details className="text-sm">
                <summary className="cursor-pointer text-gray-600">
                  收件人明细（{currentTask.recipients.length} 条）
                </summary>
                <table className="mt-2 w-full text-left text-xs">
                  <thead className="text-gray-500">
                    <tr>
                      <th className="py-1">邮箱</th>
                      <th className="py-1">状态</th>
                      <th className="py-1">错误</th>
                    </tr>
                  </thead>
                  <tbody>
                    {currentTask.recipients.slice(0, 50).map((r, i) => (
                      <tr key={i} className="border-t border-gray-100">
                        <td className="py-1 break-all">{r.email}</td>
                        <td className="py-1">{r.status}</td>
                        <td className="py-1 break-all text-red-500">{r.error_msg ?? ''}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {currentTask.recipients.length > 50 && (
                  <div className="mt-1 text-gray-400">仅显示前 50 条...</div>
                )}
              </details>
            )}
          </section>
        )}

        {/* 历史任务列表 */}
        <section className="rounded-lg bg-white p-6 shadow-sm">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-800">历史任务</h2>
            <button
              onClick={() => loadHistory(historyPage)}
              className="rounded border border-gray-300 px-3 py-1 text-xs text-gray-600 hover:bg-gray-100"
            >
              刷新
            </button>
          </div>
          {history.length === 0 ? (
            <div className="py-6 text-center text-sm text-gray-400">暂无历史任务</div>
          ) : (
            <table className="w-full text-left text-sm">
              <thead className="text-gray-500">
                <tr>
                  <th className="py-2">主题</th>
                  <th className="py-2">总数</th>
                  <th className="py-2">成功</th>
                  <th className="py-2">失败</th>
                  <th className="py-2">状态</th>
                  <th className="py-2">创建时间</th>
                  <th className="py-2">操作</th>
                </tr>
              </thead>
              <tbody>
                {history.map((t) => (
                  <tr key={t.task_id} className="border-t border-gray-100">
                    <td className="py-2">{t.subject}</td>
                    <td className="py-2">{t.total}</td>
                    <td className="py-2 text-green-600">{t.sent}</td>
                    <td className="py-2 text-red-600">{t.failed}</td>
                    <td className="py-2"><StatusBadge status={t.status} /></td>
                    <td className="py-2 text-xs text-gray-500">
                      {t.created_at ? formatUTC(t.created_at) : '-'}
                    </td>
                    <td className="py-2">
                      <button
                        onClick={() => viewHistoryTask(t.task_id)}
                        className="text-xs text-indigo-600 hover:underline"
                      >
                        查看
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {/* 简单分页 */}
          {historyTotal > historyPageSize && (
            <div className="mt-4 flex items-center justify-center gap-4 text-sm">
              <button
                onClick={() => loadHistory(historyPage - 1)}
                disabled={historyPage <= 1}
                className="rounded border px-3 py-1 disabled:opacity-50"
              >
                上一页
              </button>
              <span>
                第 {historyPage} 页 / 共 {Math.ceil(historyTotal / historyPageSize)} 页
              </span>
              <button
                onClick={() => loadHistory(historyPage + 1)}
                disabled={historyPage * historyPageSize >= historyTotal}
                className="rounded border px-3 py-1 disabled:opacity-50"
              >
                下一页
              </button>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    pending: 'bg-gray-100 text-gray-700',
    running: 'bg-blue-100 text-blue-700',
    completed: 'bg-green-100 text-green-700',
    interrupted: 'bg-yellow-100 text-yellow-700',
    failed: 'bg-red-100 text-red-700',
  };
  const cls = colorMap[status] ?? 'bg-gray-100 text-gray-700';
  return (
    <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${cls}`}>
      {status}
    </span>
  );
}
