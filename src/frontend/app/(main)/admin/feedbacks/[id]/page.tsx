'use client';

import { useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  ArrowLeft,
  Bug,
  CheckCircle2,
  Lightbulb,
  Loader2,
  Mail,
  Send,
} from 'lucide-react';
import {
  fetchAdminFeedbackDetail,
  replyAdminFeedback,
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
  const [replyContent, setReplyContent] = useState('');
  const [sendingReply, setSendingReply] = useState(false);
  const [replyMsg, setReplyMsg] = useState<{ ok: boolean; text: string } | null>(null);

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
      setDetail((prev) => (prev ? { ...prev, ...updated, attachments: prev.attachments } : updated));
    } catch (e) {
      alert(getApiErrorMessage(e, '状态更新失败'));
    } finally {
      setUpdating(false);
    }
  };

  const handleSendReply = async () => {
    const content = replyContent.trim();
    if (!content) {
      setReplyMsg({ ok: false, text: '请输入回复内容' });
      return;
    }
    setSendingReply(true);
    setReplyMsg(null);
    try {
      await replyAdminFeedback(id, content);
      setReplyContent('');
      setReplyMsg({ ok: true, text: '回复邮件已发送，确认无误后可点击下方「标记已完成」结案' });
    } catch (e) {
      setReplyMsg({ ok: false, text: getApiErrorMessage(e, '发送失败，请稍后重试') });
    } finally {
      setSendingReply(false);
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
          <span className="text-sm font-medium" style={{ color: 'var(--bd-fg)' }}>
            {detail.user_email}
          </span>
        </div>
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

      {/* 标记完成 */}
      <div className="px-4 py-3 rounded-xl border border-bd-border bg-bd-card/60">
        <p className="text-[10px] uppercase tracking-wide text-bd-subtle mb-2">处理状态</p>
        {detail.status === 'done' ? (
          <p className="text-xs flex items-center gap-1.5" style={{ color: STATUS_COLOR.done }}>
            <CheckCircle2 className="w-4 h-4" />
            已完结
          </p>
        ) : (
          <button
            onClick={() => handleStatusChange('done')}
            disabled={updating}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium text-white transition-transform active:scale-[0.98] disabled:opacity-50"
            style={{ background: STATUS_COLOR.done }}
          >
            {updating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <CheckCircle2 className="w-4 h-4" />
            )}
            标记已完成
          </button>
        )}
        <p className="text-[11px] mt-2 text-bd-subtle">
          查看详情后反馈自动变为「处理中」；回复邮件并确认处理完毕后，点击「标记已完成」结案（会发站内信通知用户）。
        </p>
      </div>

      {/* 站内回复邮件 */}
      <div className="px-4 py-3 rounded-xl border border-bd-border bg-bd-card/60">
        <p className="text-[10px] uppercase tracking-wide text-bd-subtle mb-2">邮件回复用户</p>
        <textarea
          value={replyContent}
          onChange={(e) => setReplyContent(e.target.value)}
          placeholder={`将通过站内邮件服务发送至 ${detail.user_email}`}
          rows={5}
          maxLength={5000}
          className="w-full text-sm px-3 py-2.5 rounded-xl border border-bd-border bg-bd-bg/60 resize-none focus:outline-none focus:ring-2 focus:ring-bd-ui-accent/40"
          style={{ color: 'var(--bd-fg)' }}
        />
        <div className="flex items-center justify-between mt-2">
          <span className="text-[10px] text-bd-subtle">
            主题自动生成（含用户原始反馈摘要）
          </span>
          <button
            onClick={handleSendReply}
            disabled={sendingReply}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm text-white transition-transform active:scale-[0.98] disabled:opacity-50"
            style={{
              background:
                'linear-gradient(145deg, var(--bd-ui-accent), var(--bd-primary))',
            }}
          >
            {sendingReply ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Send className="w-4 h-4" />
            )}
            发送回复邮件
          </button>
        </div>
        {replyMsg && (
          <p
            className={`text-xs mt-2 px-3 py-2 rounded-lg ${
              replyMsg.ok ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-700'
            }`}
          >
            {replyMsg.text}
          </p>
        )}
      </div>
    </div>
  );
}
