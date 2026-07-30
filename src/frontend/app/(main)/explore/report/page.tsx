'use client';

import { Suspense, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { getLastActivationCode, loadSession, saveSession, setLastActivationCode } from '@/lib/explore/session';
import { recordReportGenerated } from '@/lib/api/analytics';
import { getMyReportInfo } from '@/lib/api/report';

/**
 * 报告准备页（状态检查与跳转中枢，不再有假进度条）。
 *
 * 报告内容在审核期已后台预生成，本页只做一件事：查状态 → 直接跳 view 页。
 * - approved：标记 reportReady + 上报 analytics，然后跳 view（可看报告）
 * - not_started / pending_review / 404 / 查询失败：直接跳 view（由 view 页渲染对应占位/引导）
 */
function ReportPrepContent() {
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    let cancelled = false;
    const codeParam = searchParams.get('code')?.trim() ?? '';
    const code = codeParam || getLastActivationCode();
    if (codeParam) setLastActivationCode(codeParam);

    const viewUrl = code
      ? `/explore/report/view?code=${encodeURIComponent(code)}`
      : '/explore/report/view';

    const gotoView = () => {
      if (!cancelled) router.replace(viewUrl);
    };

    if (!code) {
      gotoView();
      return;
    }

    getMyReportInfo(code)
      .then((info) => {
        if (cancelled) return;
        if (info.review_status === 'approved') {
          // 保留原有副作用：标记报告就绪 + 上报「报告已生成」
          const s = loadSession(code);
          saveSession({ ...s, reportReady: true });
          if (s.sessionId) {
            recordReportGenerated({ session_id: s.sessionId, activation_code: code }).catch(() => {});
          }
        }
        gotoView();
      })
      .catch(() => {
        // 404（无报告）与其它查询失败：统一交给 view 页处理对应分支
        gotoView();
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="min-h-screen bg-bd-gradient text-bd-fg flex items-center justify-center px-4">
      <Loader2 size={24} className="animate-spin text-bd-subtle" />
    </div>
  );
}

export default function ReportPrepPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-bd-gradient text-bd-fg flex items-center justify-center px-4">
          <Loader2 size={24} className="animate-spin text-bd-subtle" />
        </div>
      }
    >
      <ReportPrepContent />
    </Suspense>
  );
}
