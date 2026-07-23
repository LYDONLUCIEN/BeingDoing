'use client';

import { useEffect, useRef, useState } from 'react';
import { useNotificationStore } from '@/stores/notificationStore';
import { useAuthStore } from '@/stores/authStore';
import NotificationList from './NotificationList';
import FeedbackForm from './FeedbackForm';
import { MessageCircle, X, Bell, Send } from 'lucide-react';

type View = 'notifications' | 'feedback';
type Side = 'left' | 'right';

const STORAGE_KEY = 'feedback-widget-pos';
const TAB_W = 30; // 收起态书签宽度（比原来的 8px 细条好选中得多）
const TAB_H = 46; // 书签/抽拉条高度（矮一些）
const FULL_W = 190; // 悬停抽拉展开后的宽度（长一些，容纳图标+功能描述文字）
const EDGE_GAP = 24; // 浮窗面板距屏幕边缘的距离（原 right-6）
const DEFAULT_BOTTOM = 24;
const DRAG_THRESHOLD = 5; // 超过该位移视为拖拽而非点击

function clampBottom(b: number): number {
  if (typeof window === 'undefined') return b;
  return Math.min(Math.max(b, 12), window.innerHeight - TAB_H - 12);
}

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

  const [view, setView] = useState<View>('notifications');
  const [mounted, setMounted] = useState(false);
  const [isTouch, setIsTouch] = useState(false);
  const [side, setSide] = useState<Side>('right');
  const [bottom, setBottom] = useState(DEFAULT_BOTTOM);
  const [hovered, setHovered] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [dismissed, setDismissed] = useState(false);

  const dragRef = useRef<{
    startY: number;
    startX: number;
    startBottom: number;
    moved: boolean;
  } | null>(null);
  const suppressClickRef = useRef(false);
  // 供 pointerup 回调读取最新位置（避免闭包过期）
  const posRef = useRef<{ side: Side; bottom: number }>({ side: 'right', bottom: DEFAULT_BOTTOM });
  posRef.current = { side, bottom };

  // SSR/CSR 一致性：首帧占位；挂载后恢复 localStorage 位置 + 触屏检测
  useEffect(() => {
    setMounted(true);
    setIsTouch(window.matchMedia('(pointer: coarse)').matches);
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const p = JSON.parse(saved);
        if (p.side === 'left' || p.side === 'right') setSide(p.side);
        if (typeof p.bottom === 'number') setBottom(clampBottom(p.bottom));
      }
    } catch {
      // localStorage 不可用则忽略
    }
  }, []);

  // 窗口缩放时重新钳制位置，避免按钮跑出屏幕
  useEffect(() => {
    const onResize = () => setBottom((b) => clampBottom(b));
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
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
  // 点小×后：本次页面会话内隐藏（SPA 跳转不恢复，整页刷新后重新出现）
  if (dismissed) return null;

  // ---------- 交互 ----------

  const handleToggle = async () => {
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    if (isOpen) {
      closeWidget();
    } else {
      setView('notifications');
      await openWidget();
    }
  };

  const handleDismiss = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isOpen) closeWidget();
    setDismissed(true);
  };

  // ---------- 拖拽（pointer events，桌面/触屏通用） ----------

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    dragRef.current = {
      startY: e.clientY,
      startX: e.clientX,
      startBottom: posRef.current.bottom,
      moved: false,
    };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = dragRef.current;
    if (!d) return;
    const dy = d.startY - e.clientY; // 向上拖 → bottom 增大
    if (
      !d.moved &&
      Math.abs(dy) < DRAG_THRESHOLD &&
      Math.abs(e.clientX - d.startX) < DRAG_THRESHOLD
    ) {
      return;
    }
    d.moved = true;
    setDragging(true);
    setBottom(clampBottom(d.startBottom + dy));
  };

  const onPointerUp = (e: React.PointerEvent<HTMLDivElement>) => {
    const d = dragRef.current;
    dragRef.current = null;
    setDragging(false);
    if (!d?.moved) return;
    suppressClickRef.current = true; // 阻止拖拽后的 click 触发开合
    // 松手吸附：按指针在屏幕左/右半决定贴哪条边
    const newSide: Side = e.clientX < window.innerWidth / 2 ? 'left' : 'right';
    setSide(newSide);
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ side: newSide, bottom: posRef.current.bottom })
      );
    } catch {
      // 忽略持久化失败
    }
  };

  // ---------- 布局计算 ----------

  // 触屏始终展开；桌面端悬停/面板打开/拖拽中展开，否则收起为边缘书签
  const expanded = isTouch || hovered || isOpen || dragging;
  const wrapperW = expanded ? FULL_W : TAB_W;

  const vh = typeof window !== 'undefined' ? window.innerHeight : 800;
  const panelHeight = Math.min(480, vh - 128);
  const panelBottom = Math.min(bottom + TAB_H + 8, Math.max(16, vh - panelHeight - 16));

  return (
    <>
      {/* 浮窗面板（跟随按钮所在侧边与上下位置） */}
      {isOpen && (
        <div
          className="fixed z-50 w-[360px] max-w-[calc(100vw-2rem)] bg-bd-card/95 backdrop-blur-xl border border-bd-border rounded-3xl shadow-[0_22px_60px_rgba(15,23,42,0.28)] flex flex-col overflow-hidden animate-[fadeInScale_180ms_ease-out]"
          style={{
            animationName: 'fadeInScale',
            bottom: panelBottom,
            [side]: EDGE_GAP,
            height: 480,
            maxHeight: 'calc(100vh - 8rem)',
          }}
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
              <FeedbackForm
                onSubmitted={() => {
                  setView('notifications');
                  // 刷新通知列表，让用户立即看到 auto_ack 确认通知
                  fetchFirstPage();
                }}
              />
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

      {/* 悬浮书签容器：收起时是屏幕边缘小书签，悬停/触屏时抽拉展开为带文字描述的长条 */}
      <div
        className="fixed z-50 select-none touch-none"
        style={{
          bottom,
          [side]: 0,
          width: wrapperW,
          height: TAB_H,
          transition: dragging ? 'none' : 'width 180ms ease-out',
        }}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => {
          if (!isOpen && !dragging) setHovered(false);
        }}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onClick={handleToggle}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleToggle();
          }
        }}
        aria-label={isOpen ? '关闭站内信与反馈浮窗' : '打开站内信与反馈浮窗'}
      >
        {/* 收起态：圆角矩形小标笾（贴边一侧直边、内侧圆角） */}
        <div
          className="absolute inset-y-0 flex items-center justify-center"
          style={{
            [side]: 0,
            width: TAB_W,
            background: 'linear-gradient(145deg, var(--bd-ui-accent), var(--bd-primary))',
            borderRadius: side === 'right' ? '10px 0 0 10px' : '0 10px 10px 0',
            boxShadow: '0 6px 18px rgba(15,23,42,0.22)',
            opacity: expanded ? 0 : 1,
            transition: 'opacity 150ms ease-out',
            cursor: 'grab',
          }}
        >
          <MessageCircle className="w-3.5 h-3.5 text-white" aria-hidden />
          {!isOpen && unreadCount > 0 && (
            <span
              className="absolute top-1.5 w-1.5 h-1.5 rounded-full bg-white"
              style={{ [side === 'right' ? 'left' : 'right']: 4 }}
            />
          )}
        </div>

        {/* 展开态：抽拉长条（图标 + 功能文字描述，overflow-hidden 随宽度抽出逐渐显露） */}
        <div
          className="absolute inset-y-0 overflow-hidden flex items-center"
          style={{
            [side]: 0,
            width: FULL_W,
            background: 'linear-gradient(145deg, var(--bd-ui-accent), var(--bd-primary))',
            borderRadius: side === 'right' ? '12px 0 0 12px' : '0 12px 12px 0',
            boxShadow: '0 10px 30px rgba(15,23,42,0.28)',
            opacity: expanded ? 1 : 0,
            pointerEvents: expanded ? 'auto' : 'none',
            transition: dragging ? 'none' : 'opacity 150ms ease-out',
            cursor: dragging ? 'grabbing' : 'grab',
          }}
        >
          <div
            className="flex items-center gap-2.5 whitespace-nowrap"
            style={{ paddingInline: 12 }}
          >
            {isOpen ? (
              <X className="w-5 h-5 text-white shrink-0" aria-hidden />
            ) : (
              <MessageCircle className="w-5 h-5 text-white shrink-0" aria-hidden />
            )}
            <div className="flex flex-col leading-tight">
              <span className="text-[13px] font-semibold text-white">站内信 · 反馈</span>
              <span className="text-[10px] text-white/75">查看通知 / 提交问题与想法</span>
            </div>
          </div>
          {!isOpen && unreadCount > 0 && (
            <span
              className="absolute top-1 min-w-[18px] h-[18px] px-1 rounded-full bg-red-500 text-white text-[10px] font-semibold flex items-center justify-center ring-2 ring-white/60"
              style={{ [side === 'right' ? 'right' : 'left']: 6 }}
            >
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </div>

        {/* 小×：隐藏按钮（本次页面会话内不再出现，刷新后恢复）；放容器层避免被抽拉条 overflow 裁切 */}
        {expanded && (
          <button
            onClick={handleDismiss}
            onPointerDown={(e) => e.stopPropagation()}
            className="absolute w-5 h-5 rounded-full bg-bd-card border border-bd-border shadow-sm flex items-center justify-center hover:bg-bd-overlay-md transition-colors"
            style={{ top: -8, [side === 'right' ? 'left' : 'right']: -8 }}
            aria-label="隐藏反馈按钮（刷新页面后恢复）"
            title="隐藏按钮，刷新页面后恢复"
          >
            <X className="w-3 h-3" style={{ color: 'var(--bd-fg-muted)' }} />
          </button>
        )}
      </div>

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
