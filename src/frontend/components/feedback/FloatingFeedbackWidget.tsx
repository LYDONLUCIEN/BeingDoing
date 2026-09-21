'use client';

import { useEffect, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { useNotificationStore } from '@/stores/notificationStore';
import { useAuthStore } from '@/stores/authStore';
import NotificationList from './NotificationList';
import FeedbackForm from './FeedbackForm';
import { Bell, X, Search } from 'lucide-react';

type View = 'notifications' | 'feedback';

// 悬浮球自定义位置（2026-09-21 起支持拖拽）：left/top 视口坐标（px），持久化到 localStorage；
// 未拖过时为 null，走 CSS 默认定位（右下角，chat 页上浮避让）
const LAUNCHER_POS_KEY = 'ol-msg-launcher-pos';

type LauncherPos = { x: number; y: number };

// 水平方向允许最多露出半边（左右各半），垂直方向不出屏
function clampPos(x: number, y: number, w: number, h: number): LauncherPos {
  return {
    x: Math.min(Math.max(x, -w / 2), window.innerWidth - w / 2),
    y: Math.min(Math.max(y, 4), Math.max(4, window.innerHeight - h - 4)),
  };
}

// 松手吸附：越过右边界 → 只露左半边贴右缘；越过左边界 → 只露右半边贴左缘；未越界保持原位
function snapToEdge(p: LauncherPos, w: number, h: number): LauncherPos {
  const c = clampPos(p.x, p.y, w, h);
  if (c.x + w > window.innerWidth) return { x: window.innerWidth - w / 2, y: c.y };
  if (c.x < 0) return { x: -w / 2, y: c.y };
  return c;
}

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
  // 拖拽：pos 非 null 时以内联 left/top 覆盖 CSS 默认 right/bottom 定位
  const [pos, setPos] = useState<LauncherPos | null>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const dragRef = useRef<{ startX: number; startY: number; baseX: number; baseY: number; moved: boolean } | null>(null);
  const posRef = useRef<LauncherPos | null>(null); // 拖拽中的最新位置（pointerup 时取它吸附，避开 state 闭包旧值）
  // 拖拽结束的 pointerup 后浏览器仍会补发 click，用它抑制「拖拽误触发打开抽屉」
  const suppressClickRef = useRef(false);

  useEffect(() => {
    setMounted(true);
    try {
      const raw = localStorage.getItem(LAUNCHER_POS_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as LauncherPos;
        if (typeof saved?.x === 'number' && typeof saved?.y === 'number') {
          posRef.current = saved;
          setPos(saved); // 元素未挂载无法量尺寸，越界钳制交给 resize 效应与下次拖拽
        }
      }
    } catch {
      // 解析失败视为无自定义位置
    }
  }, []);

  // 窗口尺寸变化时把已拖过的悬浮球钳回可视区
  useEffect(() => {
    if (!pos) return;
    const onResize = () => {
      const el = launcherRef.current;
      if (!el) return;
      setPos((p) => (p ? clampPos(p.x, p.y, el.offsetWidth, el.offsetHeight) : p));
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [pos != null]); // eslint-disable-line react-hooks/exhaustive-deps

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
    if (suppressClickRef.current) {
      suppressClickRef.current = false;
      return;
    }
    if (isOpen) {
      closeWidget();
    } else {
      setView('notifications');
      void openWidget();
    }
  };

  // 拖拽：pointerdown 记起点，移动超过 6px 阈值才判定为拖拽（保留单击打开抽屉）
  const handlePointerDown = (e: React.PointerEvent<HTMLButtonElement>) => {
    const el = launcherRef.current;
    if (!el || e.pointerType === 'mouse' && e.button !== 0) return;
    const rect = el.getBoundingClientRect();
    dragRef.current = { startX: e.clientX, startY: e.clientY, baseX: rect.left, baseY: rect.top, moved: false };
    el.setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLButtonElement>) => {
    const d = dragRef.current;
    const el = launcherRef.current;
    if (!d || !el) return;
    const dx = e.clientX - d.startX;
    const dy = e.clientY - d.startY;
    if (!d.moved && Math.hypot(dx, dy) < 6) return;
    d.moved = true;
    const next = clampPos(d.baseX + dx, d.baseY + dy, el.offsetWidth, el.offsetHeight);
    posRef.current = next;
    setPos(next);
  };

  const handlePointerUp = () => {
    const d = dragRef.current;
    dragRef.current = null;
    if (!d?.moved) return;
    suppressClickRef.current = true;
    const el = launcherRef.current;
    const latest = posRef.current;
    if (!el || !latest) return;
    const snapped = snapToEdge(latest, el.offsetWidth, el.offsetHeight);
    posRef.current = snapped;
    setPos(snapped);
    try { localStorage.setItem(LAUNCHER_POS_KEY, JSON.stringify(snapped)); } catch { /* 存储失败不影响拖拽 */ }
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
          ref={launcherRef}
          className={launcherClass}
          onClick={handleToggle}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerCancel={handlePointerUp}
          style={pos ? { left: pos.x, top: pos.y, right: 'auto', bottom: 'auto' } : undefined}
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
