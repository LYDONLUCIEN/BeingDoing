'use client';

import { useState } from 'react';
import { useNotificationStore } from '@/stores/notificationStore';
import { timeAgo } from '@/lib/utils/timeAgo';
import { Inbox } from 'lucide-react';
import type { Notification } from '@/lib/api/feedback';

interface NotificationListProps {
  query?: string;
  unreadOnly?: boolean;
}

/** 通知类型 → 卡片左上角 kind 标签（对齐 HTML 的 kind 字段；未知类型兜底「通知」） */
const KIND_LABELS: Record<string, string> = {
  feedback_auto_ack: '反馈回执',
  feedback_new: '新反馈',
  feedback_status_changed: '反馈进度',
  feedback_overdue: '反馈超时',
  llm_balance_low: '系统告警',
  announcement: '公告',
  team_analysis_notice: '团队分析',
  activation_expired: '续期提醒',
  report_recheck_done: '报告复核',
  report_recheck_rejected: '报告复核',
  password_changed: '账户安全',
};

function kindLabel(type: string): string {
  return KIND_LABELS[type] ?? '通知';
}

export default function NotificationList({ query = '', unreadOnly = false }: NotificationListProps) {
  const { items, isLoading, total, markRead, markAllRead, unreadCount } = useNotificationStore();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const normalizedQuery = query.trim().toLocaleLowerCase();
  const visibleItems = items.filter((item) => {
    if (unreadOnly && item.read_at !== null) return false;
    if (!normalizedQuery) return true;
    return `${item.title}\n${item.content}`.toLocaleLowerCase().includes(normalizedQuery);
  });

  const selected = items.find((n) => n.id === selectedId) ?? null;

  if (isLoading && items.length === 0) {
    return <div className="ol-msg-empty">加载中…</div>;
  }

  /* ── 详情视图（对齐 HTML：返回 + kind pill + 标题 + 时间 + 正文） ── */
  if (selected) {
    return (
      <div className="ol-msg-detail">
        <button type="button" className="ol-msg-back" onClick={() => setSelectedId(null)}>
          ← 返回列表
        </button>
        <span className="ol-msg-kind" style={{ alignSelf: 'flex-start' }}>
          {kindLabel(selected.type)}
        </span>
        <h4 className="ol-msg-detail-title">{selected.title}</h4>
        <span className="ol-msg-detail-time">{timeAgo(selected.created_at)}</span>
        <p className="ol-msg-detail-body">{selected.content}</p>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="ol-msg-empty">
        <Inbox className="w-10 h-10" aria-hidden />
        <p>暂无通知</p>
      </div>
    );
  }

  if (visibleItems.length === 0) {
    return (
      <div className="ol-msg-empty">
        <Inbox className="w-10 h-10" aria-hidden />
        <p>没有找到符合条件的站内信</p>
      </div>
    );
  }

  return (
    <>
      <div className="ol-msg-list">
        {visibleItems.map((n) => (
          <NotificationCard
            key={n.id}
            notification={n}
            onOpen={() => {
              if (n.read_at === null) void markRead(n.id);
              setSelectedId(n.id);
            }}
          />
        ))}
        {items.length < total && (
          <div style={{ textAlign: 'center', fontSize: 11, padding: '6px 0', color: '#99a3af' }}>
            共 {total} 条，仅显示最近 {items.length} 条
          </div>
        )}
      </div>
      <div className="ol-msg-footer">
        <span>共 {total} 条消息</span>
        <button type="button" onClick={() => markAllRead()} disabled={unreadCount === 0}>
          全部标为已读
        </button>
      </div>
    </>
  );
}

function NotificationCard({
  notification,
  onOpen,
}: {
  notification: Notification;
  onOpen: () => void;
}) {
  const isUnread = notification.read_at === null;

  return (
    <button
      type="button"
      onClick={onOpen}
      className={`ol-msg-card${isUnread ? ' is-unread' : ''}`}
    >
      <span className="ol-msg-card-top">
        <span className="ol-msg-kind">{kindLabel(notification.type)}</span>
        {isUnread && <span className="ol-msg-unread-dot">未读</span>}
      </span>
      <span className="ol-msg-time">{timeAgo(notification.created_at)}</span>
      <strong className="ol-msg-card-title">{notification.title}</strong>
      <p className="ol-msg-card-preview">{notification.content}</p>
    </button>
  );
}
