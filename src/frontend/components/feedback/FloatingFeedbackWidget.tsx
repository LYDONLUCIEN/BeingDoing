'use client';

import { useEffect, useState } from 'react';
import { useNotificationStore } from '@/stores/notificationStore';
import { useAuthStore } from '@/stores/authStore';
import NotificationList from './NotificationList';
import FeedbackForm from './FeedbackForm';
import { MessageCircle, X, Bell, Send } from 'lucide-react';

type View = 'notifications' | 'feedback';

export default function FloatingFeedbackWidget() {
  const { user, isAuthenticated } = useAuthStore();
  const {
    isOpen,
    unreadCount,
    refreshUnreadCount,
    openWidget,
    closeWidget,
  } = useNotificationStore();

  const [view, setView] = useState<View>('notifications');
  const [mounted, setMounted] = useState(false);

  // SSR/CSR 一致性：首帧占位
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

  // 未登录不显示浮窗（auth 页 / admin 页理论上不会渲染到 main layout）
  if (!mounted || !isAuthenticated) return null;

  const handleToggle = async () => {
    if (isOpen) {
      closeWidget();
    } else {
      setView('notifications');
      await openWidget();
    }
  };

  return (
    <>
      {/* 浮窗面板 */}
      {isOpen && (
        <div
          className="fixed bottom-24 right-6 z-50 w-[360px] h-[480px] max-w-[calc(100vw-2rem)] max-h-[calc(100vh-8rem)] bg-bd-card/95 backdrop-blur-xl border border-bd-border rounded-3xl shadow-[0_22px_60px_rgba(15,23,42,0.28)] flex flex-col overflow-hidden animate-[fadeInScale_180ms_ease-out]"
          style={{ animationName: 'fadeInScale' }}
        >
          {/* 头部 */}
          <div className="flex items-center justify-between px-5 py-4 border-b border-bd-border">
            <div className="flex items-center gap-2">
              {view === 'notifications' ? (
                <>
                  <Bell className="w-4 h-4 text-bd-ui-accent" />
                  <h3 className="text-sm font-semibold" style={{ color: 'var(--bd-fg)' }}>
                    站内信
                  </h3>
                  {unreadCount > 0 && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-bd-ui-accent text-bd-ui-accent-fg">
                      {unreadCount > 99 ? '99+' : unreadCount}
                    </span>
                  )}
                </>
              ) : (
                <>
                  <Send className="w-4 h-4 text-bd-ui-accent" />
                  <h3 className="text-sm font-semibold" style={{ color: 'var(--bd-fg)' }}>
                    提交反馈
                  </h3>
                </>
              )}
            </div>
            <button
              onClick={closeWidget}
              className="p-1 rounded-lg hover:bg-bd-overlay-md transition-colors"
              aria-label="关闭"
            >
              <X className="w-4 h-4" style={{ color: 'var(--bd-fg-muted)' }} />
            </button>
          </div>

          {/* 内容区 */}
          <div className="flex-1 overflow-hidden">
            {view === 'notifications' ? (
              <NotificationList />
            ) : (
              <FeedbackForm onSubmitted={() => setView('notifications')} />
            )}
          </div>

          {/* 底部：切换到反馈 */}
          {view === 'notifications' && (
            <div className="px-5 py-3 border-t border-bd-border">
              <button
                onClick={() => setView('feedback')}
                className="w-full text-xs px-3 py-2 rounded-xl border border-bd-border hover:bg-bd-overlay-md transition-colors"
                style={{ color: 'var(--bd-fg-muted)' }}
              >
                💡 提交新反馈（Bug / 产品想法）
              </button>
            </div>
          )}
          {view === 'feedback' && (
            <div className="px-5 py-3 border-t border-bd-border">
              <button
                onClick={() => setView('notifications')}
                className="w-full text-xs px-3 py-2 rounded-xl hover:bg-bd-overlay-md transition-colors"
                style={{ color: 'var(--bd-fg-muted)' }}
              >
                ← 返回站内信
              </button>
            </div>
          )}
        </div>
      )}

      {/* 悬浮按钮 */}
      <button
        onClick={handleToggle}
        className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full shadow-[0_10px_30px_rgba(15,23,42,0.28)] hover:scale-105 active:scale-95 transition-all flex items-center justify-center"
        style={{
          background: 'linear-gradient(145deg, var(--bd-ui-accent), var(--bd-primary))',
        }}
        aria-label={isOpen ? '关闭反馈浮窗' : '打开反馈浮窗'}
      >
        {isOpen ? (
          <X className="w-6 h-6 text-white" />
        ) : (
          <MessageCircle className="w-6 h-6 text-white" />
        )}
        {!isOpen && unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[20px] h-5 px-1.5 rounded-full bg-red-500 text-white text-[10px] font-semibold flex items-center justify-center ring-2 ring-bd-card">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {/* 动画 keyframes（注入到全局） */}
      <style jsx global>{`
        @keyframes fadeInScale {
          from {
            opacity: 0;
            transform: scale(0.92) translateY(8px);
          }
          to {
            opacity: 1;
            transform: scale(1) translateY(0);
          }
        }
      `}</style>
    </>
  );
}
