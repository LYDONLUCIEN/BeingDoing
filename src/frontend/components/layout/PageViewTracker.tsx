'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';

/**
 * 页面浏览埋点（ADR-0013）：
 * - SPA 路由切换也计 PV（usePathname 监听）
 * - visitor_id：匿名访客 cookie（1 年），兼算 UV
 * - 排除 /admin 前缀（避免管理员自身访问污染看板）
 * - sendBeacon 优先，fetch keepalive 兜底；失败静默，不影响页面
 */

const VISITOR_COOKIE = 'bd_visitor_id';
const COOKIE_MAX_AGE = 365 * 24 * 60 * 60; // 1 年

function getVisitorId(): string {
  const match = document.cookie.match(new RegExp(`(?:^|; )${VISITOR_COOKIE}=([^;]*)`));
  if (match && match[1]) return decodeURIComponent(match[1]);
  const id =
    typeof crypto !== 'undefined' && 'randomUUID' in crypto
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
  document.cookie = `${VISITOR_COOKIE}=${encodeURIComponent(id)}; max-age=${COOKIE_MAX_AGE}; path=/; samesite=lax`;
  return id;
}

export default function PageViewTracker() {
  const pathname = usePathname();

  useEffect(() => {
    if (!pathname || pathname.startsWith('/admin')) return;
    try {
      const visitorId = getVisitorId();
      const payload = JSON.stringify({
        event_type: 'page_view',
        visitor_id: visitorId,
        path: pathname.slice(0, 255),
      });
      const url = '/api/v1/analytics/event';
      const blob = new Blob([payload], { type: 'application/json' });
      if (typeof navigator !== 'undefined' && navigator.sendBeacon && navigator.sendBeacon(url, blob)) {
        return;
      }
      fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
        keepalive: true,
      }).catch(() => {});
    } catch {
      // 埋点失败静默
    }
  }, [pathname]);

  return null;
}
