'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  Bug,
  Lightbulb,
  Loader2,
  Mail,
  Send,
} from 'lucide-react';
import {
  fetchAdminFeedbackDetail,
  updateAdminFeedbackStatus,
  type AdminFeedbackDetail,
  type AdminFeedbackStatus,
} from '@/lib/api/admin';
import { formatLocalDateTime } from '@/lib/utils/formatTime';
import { getApiErrorMessage } from '@/lib/api/client';

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

export default function AdminFeedbackDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [detail, setDetail] = useState<AdminFeedbackDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAdminFeedbackDetail(id);
      setDetail(data);
    } catch (e: any) {
      setError(getApiErrorMessage(e, '加载失败'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const handleStatusChange = async (newStatus: AdminFeedbackStatus) => {
    if (!detail || detail.status === newStatus) return;
    setUpdating(true);
    try {
      const updated = await updateAdminFeedbackStatus(id, newStatus);
      setDetail(updated);
    } catch (e) {
      alert(getApiErrorMessage(e, '状态更新失败'));
    } finally {
      setUpdating(false);
    }
  };

  if (loading) {
    return (
      <div className="py-16 flex items-center justify-center">
        <Loader2 className="w-5 h-5 animate-spin text-bd-muted" />
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="py-16 text-center">
        <p className="text-sm text-red-600 mb-4">{error || '反馈不存在'}</p>
        <Link
          href="/admin/feedbacks"
          className="text-xs px-3 py-1.5 rounded-lg border border-bd-border"
        >
          ← 返回列表
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6 max-w-3xl">
      {/* 返回 */}
      <button
        onClick={() => router.push('/admin/feedbacks')}
        className="text-xs flex items-center gap-1 hover:underline"
        style={{ color: 'var(--bd-fg-muted)' }}
      >
        <ArrowLeft className="w-3 h-3" />
        返回反馈列表
      </button>

      {/* 头部 */}
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 mt-1">
          {detail.type === 'bug' ? (
            <Bug className="w-5 h-5 text-red-500" />
          ) : (
            <Lightbulb className="w-5 h-5 text-amber-500" />
          )}
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span
              className="text-[10px] px-2 py-0.5 rounded-full font-medium"
              style={{
                background: `${STATUS_COLOR[detail.status]}20`,
                color: STATUS_COLOR[detail.status],
              }}
            >
              {STATUS_LABEL[detail.status]}
            </span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-bd-overlay-md text-bd-muted">
              {detail.type === 'bug' ? 'Bug' : '产品想法'}
            </span>
          </div>
          <p className="text-xs text-bd-subtle">
            提交时间：{formatLocalDateTime(detail.created_at)}
            {detail.updated_at !== detail.created_at && (
              <> · 更新：{formatLocalDateTime(detail.updated_at)}</>
            )}
          </p>
        </div>
      </div>

      {/* 用户信息 */}
      <div className="px-4 py-3 rounded-xl border border-bd-border bg-bd-card/60">
        <p className="text-[10px] uppercase tracking-wide text-bd-subtle mb-1">提交用户</p>
        <div className="flex items-center gap-2">
          <Mail className="w-4 h-4 text-bd-ui-accent" />
          <a
            href={`mailto:${detail.user_email}`}
            className="text-sm font-medium hover:underline"
            style={{ color: 'var(--bd-ui-accent)' }}
          >
            {detail.user_email}
          </a>
        </div>
        <p className="text-[11px] mt-1 text-bd-subtle">
          点击邮箱地址打开邮件客户端回复用户（用户将通过邮件收到您的回复）
        </p>
      </div>

      {/* 反馈内容 */}
      <div className="px-4 py-3 rounded-xl border border-bd-border bg-bd-card/60">
        <p className="text-[10px] uppercase tracking-wide text-bd-subtle mb-2">反馈内容</p>
        <p
          className="text-sm whitespace-pre-wrap break-words"
          style={{ color: 'var(--bd-fg)' }}
        >
          {detail.content}
        </p>
      </div>

      {/* 截图 */}
      {detail.attachments.length > 0 && (
        <div className="px-4 py-3 rounded-xl border border-bd-border bg-bd-card/60">
          <p className="text-[10px] uppercase tracking-wide text-bd-subtle mb-2">
            截图（{detail.attachments.length}）· 签名 URL 1 小时有效
          </p>
          <div className="flex flex-wrap gap-2">
            {detail.attachments.map((att) => (
              <a
                key={att.id}
                href={att.signed_url}
                target="_blank"
                rel="noopener noreferrer"
                className="block w-24 h-24 rounded-lg overflow-hidden border border-bd-border hover:scale-105 transition-transform"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={att.signed_url}
                  alt="反馈截图"
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.background = '#f3f4f6';
                    (e.target as HTMLImageElement).style.padding = '20px';
                  }}
                />
              </a>
            ))}
          </div>
        </div>
      )}

      {/* 状态切换 */}
      <div className="px-4 py-3 rounded-xl border border-bd-border bg-bd-card/60">
        <p className="text-[10px] uppercase tracking-wide text-bd-subtle mb-2">变更状态</p>
        <div className="flex items-center gap-2">
          {(['received', 'in_progress', 'done'] as AdminFeedbackStatus[]).map((s) => (
            <button
              key={s}
              onClick={() => handleStatusChange(s)}
              disabled={updating || detail.status === s}
              className="px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
              style={{
                background: detail.status === s ? STATUS_COLOR[s] : 'transparent',
                color: detail.status === s ? '#fff' : STATUS_COLOR[s],
                border: `1px solid ${STATUS_COLOR[s]}`,
                opacity: updating ? 0.5 : 1,
              }}
            >
              {STATUS_LABEL[s]}
            </button>
          ))}
          {updating && <Loader2 className="w-3 h-3 animate-spin text-bd-muted" />}
        </div>
        <p className="text-[11px] mt-2 text-bd-subtle">
          改为「处理中」或「已完结」会自动发站内信通知用户。
        </p>
      </div>

      {/* 邮件回复入口 */}
      <div className="px-4 py-3 rounded-xl border border-bd-border bg-bd-card/60">
        <p className="text-[10px] uppercase tracking-wide text-bd-subtle mb-2">通过邮件回复</p>
        <a
          href={`mailto:${detail.user_email}?subject=${encodeURIComponent(
            `【留言反馈】关于您的${detail.type === 'bug' ? 'Bug 报告' : '产品想法'}`
          )}`}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm text-white transition-transform active:scale-[0.98]"
          style={{
            background:
              'linear-gradient(145deg, var(--bd-ui-accent), var(--bd-primary))',
          }}
        >
          <Send className="w-4 h-4" />
          打开邮件客户端回复
        </a>
        <p className="text-[11px] mt-2 text-bd-subtle">
          点击后将打开您系统的默认邮件客户端，收件人已自动填好。
          后续邮件往来不归档到本系统。
        </p>
      </div>
    </div>
  );
}
