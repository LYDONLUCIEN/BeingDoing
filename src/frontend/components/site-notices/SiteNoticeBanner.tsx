'use client';

import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Info, ShieldAlert, X } from 'lucide-react';
import { fetchActiveNotice, type SiteNoticeItem } from '@/lib/api/siteNotices';
import SiteNoticeModal from './SiteNoticeModal';

/** localStorage dismiss key：记录已关闭 notice 的 id + updated_at */
const DISMISS_KEY = 'bd-site-notice-dismissed';

type DismissedMap = Record<string, string>; // { noticeId: updated_at }

function readDismissed(): DismissedMap {
  if (typeof window === 'undefined') return {};
  try {
    return JSON.parse(localStorage.getItem(DISMISS_KEY) || '{}') as DismissedMap;
  } catch {
    return {};
  }
}

function writeDismissed(map: DismissedMap) {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(DISMISS_KEY, JSON.stringify(map));
  } catch {
    /* 忽略配额错误 */
  }
}

/** severity -> 样式 */
function severityStyle(sev: string) {
  switch (sev) {
    case 'urgent':
      return { bg: 'bg-red-50', text: 'text-red-800', icon: ShieldAlert };
    case 'warn':
      return { bg: 'bg-amber-50', text: 'text-amber-800', icon: AlertTriangle };
    case 'info':
    default:
      return { bg: 'bg-sky-50', text: 'text-sky-800', icon: Info };
  }
}

export default function SiteNoticeBanner() {
  const [notice, setNotice] = useState<SiteNoticeItem | null>(null);
  const [dismissed, setDismissed] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);

  const load = useCallback(async () => {
    const n = await fetchActiveNotice('banner');
    console.log('[SiteNoticeBanner] fetched:', n);
    if (!n) {
      setNotice(null);
      return;
    }
    setNotice(n);
    // 判断是否被 dismiss 过(同 id 且 updated_at 未变)
    const map = readDismissed();
    const dismissed = map[n.id] === (n.updated_at ?? n.created_at ?? '');
    console.log('[SiteNoticeBanner] dismissed=', dismissed, 'map=', map);
    setDismissed(dismissed);
  }, []);

  useEffect(() => {
    load();
    // 每 5 分钟刷一次（运行期间 banner 进入/退出窗口自动生效）
    const t = setInterval(load, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, [load]);

  if (!notice || dismissed) return null;
  const style = severityStyle(notice.severity);
  const Icon = style.icon;
  const hasMore = !!notice.content_md || (notice.channels?.length ?? 0) > 0;

  const onDismiss = () => {
    const map = readDismissed();
    map[notice.id] = notice.updated_at ?? notice.created_at ?? '';
    writeDismissed(map);
    setDismissed(true);
  };

  return (
    <>
      <div
        className={`${style.bg} ${style.text} sticky top-14 z-40 w-full px-4 py-2 flex items-center gap-3 text-sm border-b`}
        role="status"
        aria-live="polite"
      >
        <Icon className="w-4 h-4 flex-shrink-0" />
        <span className="flex-1 truncate">{notice.title}</span>
        {hasMore && (
          <button
            onClick={() => setModalOpen(true)}
            className="underline underline-offset-2 hover:opacity-80 flex-shrink-0"
          >
            了解更多
          </button>
        )}
        {notice.dismissible && (
          <button
            onClick={onDismiss}
            className="hover:opacity-70 flex-shrink-0"
            aria-label="关闭通知"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {modalOpen && (
        <SiteNoticeModal notice={notice} onClose={() => setModalOpen(false)} />
      )}
    </>
  );
}
