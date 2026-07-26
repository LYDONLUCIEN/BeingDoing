'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { Bug, Lightbulb, Loader2, Mail, RefreshCw } from 'lucide-react';
import {
  fetchAdminFeedbacks,
  type AdminFeedbackItem,
  type AdminFeedbackStatus,
  type AdminFeedbackType,
} from '@/lib/api/admin';
import { formatLocalDateTime, toDate } from '@/lib/utils/formatTime';

const STATUS_LABEL: Record<AdminFeedbackStatus, string> = {
  received: '待处理',
  in_progress: '处理中',
  done: '已完结',
};

const STATUS_COLOR: Record<AdminFeedbackStatus, string> = {
  received: '#f59e0b',
  in_progress: '#3b82f6',
  done: '#10b981',
};

const TYPE_LABEL: Record<AdminFeedbackType, string> = {
  bug: '问题反馈',
  idea: '意见建议',
};

/** 已过承诺时限且未完结 */
function isOverdue(item: AdminFeedbackItem): boolean {
  if (!item.due_at || item.status === 'done') return false;
  const due = toDate(item.due_at);
  return !!due && due.getTime() < Date.now();
}

export default function AdminFeedbacksPage() {
  const [items, setItems] = useState<AdminFeedbackItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<AdminFeedbackType | ''>('');
  const [filterStatus, setFilterStatus] = useState<AdminFeedbackStatus | ''>('');
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAdminFeedbacks({
        type: filterType || undefined,
        status: filterStatus || undefined,
        page,
        page_size: pageSize,
      });
      setItems(res.items || []);
      setTotal(res.total || 0);
    } catch (e: any) {
      setError(e?.response?.data?.detail || e?.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterType, filterStatus, page]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold" style={{ color: 'var(--bd-fg)' }}>
            用户反馈
          </h1>
          <p className="text-xs mt-1" style={{ color: 'var(--bd-fg-muted)' }}>
            查看用户提交的问题反馈和意见建议。点击详情查看用户邮箱，通过邮件回复用户。
          </p>
        </div>
        <button
          onClick={load}
          className="px-3 py-1.5 rounded-lg text-xs flex items-center gap-1 border border-bd-border hover:bg-bd-overlay-md"
          style={{ color: 'var(--bd-fg-muted)' }}
        >
          <RefreshCw className="w-3 h-3" />
          刷新
        </button>
      </div>

      {/* 筛选 */}
      <div className="flex items-center gap-3 flex-wrap">
        <FilterGroup
          label="类型"
          value={filterType}
          onChange={(v) => {
            setFilterType(v as any);
            setPage(1);
          }}
          options={[
            { value: '', label: '全部' },
            { value: 'bug', label: '问题反馈' },
            { value: 'idea', label: '意见建议' },
          ]}
        />
        <FilterGroup
          label="状态"
          value={filterStatus}
          onChange={(v) => {
            setFilterStatus(v as any);
            setPage(1);
          }}
          options={[
            { value: '', label: '全部' },
            { value: 'received', label: '待处理' },
            { value: 'in_progress', label: '处理中' },
            { value: 'done', label: '已完结' },
          ]}
        />
        <span className="text-xs text-bd-subtle">共 {total} 条</span>
      </div>

      {/* 错误 */}
      {error && (
        <div className="px-4 py-3 rounded-xl bg-red-50 text-red-700 text-sm">{error}</div>
      )}

      {/* 列表 */}
      {loading ? (
        <div className="py-16 flex items-center justify-center">
          <Loader2 className="w-5 h-5 animate-spin text-bd-muted" />
        </div>
      ) : items.length === 0 ? (
        <div className="py-16 text-center text-sm text-bd-muted">暂无反馈</div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <Link
              key={item.id}
              href={`/admin/feedbacks/${item.id}`}
              className="block px-4 py-3 rounded-xl border border-bd-border hover:bg-bd-overlay-md transition-colors"
            >
              <div className="flex items-start gap-3">
                {/* 类型图标 */}
                <div className="flex-shrink-0 mt-0.5">
                  {item.type === 'bug' ? (
                    <Bug className="w-4 h-4 text-red-500" />
                  ) : (
                    <Lightbulb className="w-4 h-4 text-amber-500" />
                  )}
                </div>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                      style={{
                        background: `${STATUS_COLOR[item.status]}20`,
                        color: STATUS_COLOR[item.status],
                      }}
                    >
                      {STATUS_LABEL[item.status]}
                    </span>
                    {isOverdue(item) && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full font-medium bg-red-100 text-red-600">
                        已超时
                      </span>
                    )}
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-bd-overlay-md text-bd-muted">
                      {TYPE_LABEL[item.type]}
                    </span>
                    <span
                      className="text-[11px] flex items-center gap-1"
                      style={{ color: 'var(--bd-fg-muted)' }}
                    >
                      <Mail className="w-3 h-3" />
                      {item.user_email}
                    </span>
                    <span className="text-[10px] text-bd-subtle">
                      {formatLocalDateTime(item.created_at)}
                    </span>
                    <span className="text-[10px] text-bd-subtle">
                      处理人：{item.assignee_email || '未指派'}
                    </span>
                    <span
                      className="text-[10px]"
                      style={{
                        color: isOverdue(item)
                          ? '#dc2626'
                          : 'var(--bd-fg-muted)',
                      }}
                    >
                      截止：{item.due_at ? formatLocalDateTime(item.due_at) : '—'}
                    </span>
                  </div>
                  <p
                    className="text-sm line-clamp-2"
                    style={{ color: 'var(--bd-fg)' }}
                  >
                    {item.content}
                  </p>
                </div>
              </div>
            </Link>
          ))}

          {/* 分页 */}
          {total > pageSize && (
            <div className="flex justify-center gap-2 pt-4">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-3 py-1 rounded-lg text-xs border border-bd-border disabled:opacity-50"
              >
                上一页
              </button>
              <span className="text-xs px-3 py-1 text-bd-muted">
                第 {page} / {Math.ceil(total / pageSize)} 页
              </span>
              <button
                disabled={page * pageSize >= total}
                onClick={() => setPage((p) => p + 1)}
                className="px-3 py-1 rounded-lg text-xs border border-bd-border disabled:opacity-50"
              >
                下一页
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function FilterGroup({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <div className="flex items-center gap-1">
      <span className="text-xs text-bd-muted mr-1">{label}:</span>
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          className="px-2.5 py-1 rounded-md text-xs transition-colors"
          style={{
            background: value === opt.value ? 'var(--bd-ui-accent)' : 'transparent',
            color: value === opt.value ? '#fff' : 'var(--bd-fg-muted)',
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
