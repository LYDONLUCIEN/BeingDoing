'use client';

import { useNotificationStore } from '@/stores/notificationStore';
import { timeAgo } from '@/lib/utils/timeAgo';
import { CheckCheck, Inbox } from 'lucide-react';
import type { Notification } from '@/lib/api/feedback';

export default function NotificationList() {
  const { items, isLoading, total, markRead, markAllRead, unreadCount } = useNotificationStore();

  if (isLoading && items.length === 0) {
    return (
      <div className="h-full flex items-center justify-center text-sm text-bd-muted">
        加载中…
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="h-full flex flex-col items-center justify-center px-6 text-center gap-2">
        <Inbox className="w-10 h-10 text-bd-subtle" />
        <p className="text-sm" style={{ color: 'var(--bd-fg-muted)' }}>
          暂无通知
        </p>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      {/* 顶部操作栏 */}
      {unreadCount > 0 && (
        <div className="px-5 py-2 flex justify-end">
          <button
            onClick={() => markAllRead()}
            className="text-[11px] flex items-center gap-1 hover:underline"
            style={{ color: 'var(--bd-ui-accent)' }}
          >
            <CheckCheck className="w-3 h-3" />
            全部已读
          </button>
        </div>
      )}

      {/* 列表 */}
      <div className="flex-1 overflow-y-auto px-3 pb-2 space-y-1">
        {items.map((n) => (
          <NotificationItem key={n.id} notification={n} onClick={() => markRead(n.id)} />
        ))}
        {items.length < total && (
          <div className="text-center text-[11px] py-2 text-bd-subtle">
            共 {total} 条，仅显示最近 {items.length} 条
          </div>
        )}
      </div>
    </div>
  );
}

function NotificationItem({
  notification,
  onClick,
}: {
  notification: Notification;
  onClick: () => void;
}) {
  const isUnread = notification.read_at === null;

  return (
    <button
      onClick={onClick}
      className="w-full text-left px-3 py-2.5 rounded-xl hover:bg-bd-overlay-md transition-colors border border-transparent"
      style={isUnread ? { background: 'rgba(124, 58, 237, 0.06)' } : undefined}
    >
      <div className="flex items-start gap-2">
        {isUnread && (
          <span
            className="mt-1.5 w-2 h-2 rounded-full flex-shrink-0"
            style={{ background: 'var(--bd-ui-accent)' }}
          />
        )}
        <div className="flex-1 min-w-0">
          <p
            className="text-xs font-semibold mb-0.5 truncate"
            style={{ color: 'var(--bd-fg)' }}
          >
            {notification.title}
          </p>
          <p
            className="text-[11px] line-clamp-3 mb-1"
            style={{ color: 'var(--bd-fg-muted)' }}
          >
            {notification.content}
          </p>
          <p className="text-[10px] text-bd-subtle">{timeAgo(notification.created_at)}</p>
        </div>
      </div>
    </button>
  );
}
