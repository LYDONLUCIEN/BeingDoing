'use client';

/**
 * 沉淀（rumination）阶段入口：无条件走 v4（2026-09 v3 前端已删除）。
 *
 * 自 chat 页（page.tsx）抽出的原 v4 分支逻辑：
 * - activationCode 获取口径与 chat 页一致：URL ?code= 优先（并写入 last），否则 localStorage last；
 * - 「完成并继续」：unlockNextPhase + 跳 /explore/transition?from=rumination（isNavigatingRef 防连点）；
 * - LegacyBrowserNotice 旧内核提示；外层 chat-shell-h 容器。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import dynamic from 'next/dynamic';
import LegacyBrowserNotice from '@/components/layout/LegacyBrowserNotice';
import { useAuthStore } from '@/stores/authStore';
import {
  loadSession,
  unlockNextPhase,
  getLastActivationCode,
  setLastActivationCode,
  getUserSurveyCompleted,
  type ExploreSession,
} from '@/lib/explore/session';

const RuminationV4Page = dynamic(
  () => import('@/components/explore/ruminationV4/RuminationV4Page'),
  { ssr: false },
);

export default function RuminationV4Entry() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuthStore();
  const [session, setSession] = useState<ExploreSession | null>(null);
  const [activationCode, setActivationCode] = useState<string | null>(null);
  const [chatError, setChatError] = useState<string | null>(null);
  /** 防止「完成并继续」连点 / 多处导航竞态：导航中置 true，跳转完成后置 false */
  const isNavigatingRef = useRef(false);

  // 邮箱未验证：禁止进入探索对话（后端写端点统一 403 email_not_verified），回问卷页做验证引导
  useEffect(() => {
    if (user?.email && user.email_verified === false) {
      router.replace('/explore/survey');
    }
  }, [user, router]);

  // activationCode 获取口径与 chat 页 Auth & redirect 一致：?code= 优先并持久化，否则取 last
  useEffect(() => {
    const forcedCode = searchParams.get('code')?.trim() || null;
    if (forcedCode) {
      setLastActivationCode(forcedCode);
    }
    const code = forcedCode || getLastActivationCode();
    if (!code) {
      router.replace('/explore/activate');
      return;
    }
    setActivationCode(code);
    const s = loadSession(code);
    setSession(s);
    // 用户维度 + 激活码维度双检查，防止清缓存后误跳问卷（与 chat 页同口径）
    if (!s?.surveyCompleted && !getUserSurveyCompleted()) {
      router.replace('/explore/survey');
    }
  }, [router, searchParams]);

  /** v4 顶栏「完成并继续」：解锁下一阶段并进过渡页（不依赖 v3 线程 completed 门控） */
  const handleV4CompleteAndContinue = useCallback(() => {
    if (!activationCode) {
      setChatError('激活码上下文丢失，请返回激活页重新进入');
      return;
    }
    let sessionSnapshot = session;
    if (!sessionSnapshot) {
      // 防止极端情况下 session state 丢失导致"按钮可点但点击无响应"
      try {
        sessionSnapshot = loadSession(activationCode);
        setSession(sessionSnapshot);
      } catch {
        setChatError('会话状态读取失败，请刷新页面后重试');
        return;
      }
    }
    // 防连点：上一轮导航尚未完成时忽略
    if (isNavigatingRef.current) return;
    // 去重保护：session 已前进则不再重复 push
    if (sessionSnapshot.currentPhase !== 'rumination') {
      router.push(`/explore/chat/${sessionSnapshot.currentPhase}`);
      return;
    }
    isNavigatingRef.current = true;
    try {
      // unlockNextPhase 内部会 saveSession
      const updated = unlockNextPhase({ ...sessionSnapshot, currentPhase: 'rumination' });
      setSession(updated);
      router.push('/explore/transition?from=rumination');
      // App Router push 为异步且无 Promise，防止偶发未跳转时导航锁卡死。
      window.setTimeout(() => {
        isNavigatingRef.current = false;
      }, 1800);
    } catch (err) {
      console.error('[V4 CompleteAndContinue] 导航异常', err);
      isNavigatingRef.current = false;
      setChatError('跳转失败，请刷新页面后重试');
    }
  }, [activationCode, session, router]);

  return (
    <div className="chat-shell-h flex min-h-0 flex-col overflow-hidden">
      {/* 旧内核浏览器提示（ADR-0020）：「不再提示」前每个 phase 页都弹 */}
      <LegacyBrowserNotice />
      {chatError && (
        <div
          className="mx-4 mt-3 shrink-0 rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700"
          role="alert"
        >
          {chatError}
        </div>
      )}
      {activationCode ? (
        <RuminationV4Page
          activationCode={activationCode}
          onCompleteAndContinue={handleV4CompleteAndContinue}
        />
      ) : (
        <div className="flex flex-1 items-center justify-center text-sm text-gray-400">
          加载中…
        </div>
      )}
    </div>
  );
}
