'use client';

import { useEffect, useState } from 'react';
import { usePathname } from 'next/navigation';
import { useNotificationStore } from '@/stores/notificationStore';
import { useAuthStore } from '@/stores/authStore';
import NotificationList from './NotificationList';
import FeedbackForm from './FeedbackForm';
import { Bell, X, Search } from 'lucide-react';

type View = 'notifications' | 'feedback';

/**
 * 站内信 · 反馈入口（对齐 HTML 设计稿 .support-*）：
 * 右下固定毛玻璃 pill（铃铛 + 未读 badge）→ 右侧 456px 抽屉，
 * 双 tab「站内信 / 提交反馈」。数据层不变（notificationStore + 真实后端接口）。
 */
export default function FloatingFeedbackWidget() {
  const { isAuthenticated } = useAuthStore();
  const {
    isOpen,
    unreadCount,
    refreshUnreadCount,
    openWidget,
    closeWidget,
    fetchFirstPage,
  } = useNotificationStore();
  const pathname = usePathname();

  const [view, setView] = useState<View>('notifications');
  const [mounted, setMounted] = useState(false);
  const [query, setQuery] = useState('');
  const [unreadOnly, setUnreadOnly] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  // 已登录 + 页面可见时，刷新未读数
  useEffect(() => {
    if (!mounted || !isAuthenticated) return;
    refreshUnreadCount();

    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        refreshUnreadCount();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [mounted, isAuthenticated, refreshUnreadCount]);

  // Esc 关闭抽屉
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeWidget();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, closeWidget]);

  // 未登录不显示（auth 页 / admin 页不经过 main layout）
  if (!mounted || !isAuthenticated) return null;

  const handleToggle = () => {
    if (isOpen) {
      closeWidget();
    } else {
      setView('notifications');
      void openWidget();
    }
  };

  // chat 页底部有输入区，悬浮球上浮避让
  const launcherClass = `ol-msg-launcher${pathname?.includes('/explore/chat') ? ' ol-msg-launcher--chat' : ''}`;

  return (
    <>
      {isOpen && (
        <>
          <div className="ol-msg-scrim" onClick={closeWidget} aria-hidden />
          <aside className="ol-msg-drawer" role="dialog" aria-label="站内信与反馈">
            <header className="ol-msg-drawer-head">
              <span className="ol-msg-drawer-icon">
                <Bell className="w-4 h-4" aria-hidden />
              </span>
              <h3>站内信</h3>
              {unreadCount > 0 && (
                <span className="ol-msg-launcher-badge">
                  {unreadCount > 99 ? '99+' : unreadCount}
                </span>
              )}
              <button type="button" className="ol-msg-close" onClick={closeWidget} aria-label="关闭">
                <X className="w-3.5 h-3.5" aria-hidden />
              </button>
            </header>

            <div className="ol-msg-tabs" role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={view === 'notifications'}
                onClick={() => setView('notifications')}
              >
                站内信
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={view === 'feedback'}
                onClick={() => setView('feedback')}
              >
                提交反馈
              </button>
            </div>

            {view === 'notifications' ? (
              <>
                <div className="ol-msg-toolbar">
                  <label className="ol-msg-search">
                    <Search className="w-3.5 h-3.5" aria-hidden />
                    <span className="sr-only">搜索站内信</span>
                    <input
                      type="search"
                      value={query}
                      onChange={(e) => setQuery(e.target.value)}
                      placeholder="搜索标题或内容"
                    />
                  </label>
                  <div className="ol-msg-seg" role="group" aria-label="站内信筛选">
                    <button
                      type="button"
                      aria-pressed={!unreadOnly}
                      onClick={() => setUnreadOnly(false)}
                    >
                      全部
                    </button>
                    <button
                      type="button"
                      aria-pressed={unreadOnly}
                      onClick={() => setUnreadOnly(true)}
                    >
                      未读
                    </button>
                  </div>
                </div>
                <NotificationList query={query} unreadOnly={unreadOnly} />
              </>
            ) : (
              <div className="ol-msg-feedback">
                <FeedbackForm
                  onSubmitted={() => {
                    setView('notifications');
                    // 刷新列表，让用户立即看到 auto_ack 回执通知
                    void fetchFirstPage();
                  }}
                />
              </div>
            )}
          </aside>
        </>
      )}

      {!isOpen && (
        <button
          type="button"
          className={launcherClass}
          onClick={handleToggle}
          aria-label="打开站内信与反馈"
        >
          <Bell className="w-4 h-4" aria-hidden />
          站内信 · 反馈
          {unreadCount > 0 && (
            <span className="ol-msg-launcher-badge">
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </button>
      )}
    </>
  );
}
