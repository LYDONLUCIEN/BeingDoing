'use client';

import { Suspense, useState, useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { apiClient } from '@/lib/api/client';
import {
  loadSession,
  saveSession,
  setLastActivationCode,
  getLastActivationCode,
  hasReportAvailable,
  applyExploreResumeToSession,
  type ExploreSession,
} from '@/lib/explore/session';
import { fetchExploreResumeFromJourneys } from '@/lib/explore/journeyResume';
import { surveyApi } from '@/lib/api/survey';
import { useAuthStore } from '@/stores/authStore';
import { fetchAdminSystemSettings } from '@/lib/api/admin';

function useActivateBg() {
  useEffect(() => {
    document.documentElement.setAttribute('data-activate-page', 'true');
    return () => document.documentElement.removeAttribute('data-activate-page');
  }, []);
}

function ActivatePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  useActivateBg();
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showReport, setShowReport] = useState(false);
  const { user } = useAuthStore();

  useEffect(() => {
    const fromUrl = searchParams.get('code')?.trim();
    if (fromUrl) {
      setCode(fromUrl);
      return;
    }
    const last = getLastActivationCode();
    if (last) setCode(last);
  }, [searchParams]);

  useEffect(() => {
    const trimmed = code.trim();
    if (!trimmed) {
      setShowReport(false);
      return;
    }
    try {
      const session = loadSession(trimmed);
      setShowReport(hasReportAvailable(session));
    } catch {
      setShowReport(false);
    }
  }, [code]);

  const handleActivate = async () => {
    const trimmed = code.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.post('/simple-auth/activate', { code: trimmed });
      const activationCode: string = res.data.activation_code;
      const sessionId: string | undefined = res.data.session_id;
      const workspaceKind = String(res.data.workspace_kind || '').toLowerCase();
      const isWorkspaceActivation =
        workspaceKind === 'resident' ||
        workspaceKind === 'fork' ||
        String(activationCode || '').toUpperCase().startsWith('ADM') ||
        String(activationCode || '').toUpperCase().startsWith('SBX');
      setLastActivationCode(activationCode);

      // Load existing session state (preserves unlocked phases on revisit)
      const session = loadSession(activationCode);

      // Check if survey already completed
      let surveyDone = session.surveyCompleted;
      let adminBypass = false;
      if (user?.is_super_admin && isWorkspaceActivation) {
        try {
          const sys = await fetchAdminSystemSettings();
          adminBypass =
            Boolean((sys as any)?.ADMIN_DEBUG_POLICY_ENABLED) &&
            Boolean((sys as any)?.ADMIN_DEBUG_WORKSPACE_ENABLED);
        } catch {
          adminBypass = false;
        }
      }

      if (adminBypass) {
        surveyDone = true;
      }

      if (!surveyDone) {
        try {
          const sv = await surveyApi.getForActivation(activationCode);
          const data = sv.data?.survey_data ?? {};
          const hasData = Object.keys(data).some((k) => {
            const v = (data as Record<string, unknown>)[k];
            return v !== undefined && v !== null && v !== '' && (Array.isArray(v) ? v.length > 0 : true);
          });
          surveyDone = hasData;
        } catch {}
      }

      const allPhaseKeys = ['values', 'strengths', 'interests', 'purpose', 'rumination'] as const;
      let exploreResume = res.data?.explore_resume as
        | { resume_phase?: string; unlocked_phases?: string[] }
        | undefined;
      if (!exploreResume?.resume_phase) {
        const fromJourneys = await fetchExploreResumeFromJourneys(activationCode);
        if (fromJourneys?.resume_phase) exploreResume = fromJourneys;
      }

      // 始终以后端 explore_resume 为准确定进度，localStorage 仅作兜底
      let nextSession: ExploreSession = {
        ...session,
        activationCode,
        surveyCompleted: surveyDone,
        sessionId: sessionId ?? session.sessionId,
      };

      // 后端有进度信息时优先使用
      if (exploreResume) {
        nextSession = applyExploreResumeToSession(nextSession, exploreResume);
      }

      // Admin 豁免：跳过问卷，若后端无进度则全部解锁
      if (adminBypass) {
        nextSession = {
          ...nextSession,
          surveyCompleted: true,
          ...(exploreResume
            ? {} // 后端已有进度，不覆盖
            : { unlockedPhases: [...allPhaseKeys], currentPhase: nextSession.currentPhase || 'values' }),
        };
      }

      saveSession(nextSession);

      if (surveyDone || adminBypass) {
        router.push(`/explore/chat/${nextSession.currentPhase}`);
      } else {
        router.push('/explore/survey');
      }
    } catch (err: any) {
      const raw =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message;
      const detail = Array.isArray(raw) ? raw[0] : raw;
      const fallback = err?.response
        ? '激活失败，请检查激活码是否正确'
        : '网络错误或服务器未响应，请检查后端是否启动、NEXT_PUBLIC_API_URL 是否正确';
      setError(detail || fallback);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="activate-page-wrap relative min-h-screen text-bd-fg flex items-center justify-center px-4">
      {/* 首页 mesh 背景 */}
      <div className="landing-mesh-bg fixed inset-0 z-0" aria-hidden>
        <div className="landing-mesh-blob landing-mesh-blob-1" />
        <div className="landing-mesh-blob landing-mesh-blob-2" />
        <div className="landing-mesh-blob landing-mesh-blob-3" />
        <div className="landing-mesh-blob landing-mesh-blob-4" />
      </div>
      <div className="landing-mesh-noise fixed inset-0 z-[1]" aria-hidden />
      <motion.div
        className="relative z-[2] w-full max-w-md space-y-8"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
      >
        {/* Back */}
        <button
          type="button"
          onClick={() => router.push('/')}
          className="text-sm text-bd-subtle hover:text-bd-muted transition-colors"
        >
          ← 返回首页
        </button>

        {/* Header */}
        <div className="space-y-2">
          <p className="text-xs tracking-widest uppercase text-neutral-600">Step 0</p>
          <h1 className="text-3xl font-bold text-bd-fg">输入激活码</h1>
          <p className="text-bd-muted text-sm leading-relaxed">
            激活码是你专属的探索通行证。整个探索过程中，所有对话记录都会自动保存，可随时回来继续。
          </p>
        </div>

        {/* Input */}
        <div className="space-y-3">
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !loading) handleActivate(); }}
            placeholder="请输入你的激活码"
            className="w-full rounded-xl border bg-bd-overlay px-4 py-3.5 text-base outline-none transition-colors focus:border-neutral-400 focus:ring-2 focus:ring-neutral-300 focus:ring-opacity-50"
            style={{
              color: 'var(--bd-fg)',
              borderColor: 'var(--bd-border)',
            }}
          />
          {error && <p className="text-sm text-bd-err">{error}</p>}
          <button
            type="button"
            onClick={handleActivate}
            disabled={loading || !code.trim()}
            className="bd-btn-black w-full rounded-xl px-4 py-3.5 text-base font-semibold text-white transition-all disabled:opacity-40"
          >
            {loading ? '验证中…' : '开始探索 →'}
          </button>
          {showReport && (
            <button
              type="button"
              onClick={() => router.push('/explore/report/view')}
              className="bd-btn-report w-full rounded-xl px-4 py-3 text-base font-medium flex items-center justify-center gap-2"
            >
              查看报告
            </button>
          )}
        </div>

      </motion.div>
    </div>
  );
}

export default function ActivatePage() {
  return (
    <Suspense fallback={null}>
      <ActivatePageContent />
    </Suspense>
  );
}
