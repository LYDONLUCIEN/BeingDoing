'use client';

import { Suspense, useState, useEffect, type CSSProperties } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { motion } from 'framer-motion';
import { apiClient, getApiErrorMessage } from '@/lib/api/client';
import {
  loadSession,
  saveSession,
  setLastActivationCode,
  getLastActivationCode,
  hasReportAvailable,
  applyExploreResumeToSession,
  setUserSurveyCompleted,
  getUserSurveyCompleted,
  type ExploreSession,
} from '@/lib/explore/session';
import { clearThreadCache } from '@/lib/explore/threads';
import { fetchExploreResumeFromJourneys } from '@/lib/explore/journeyResume';
import { surveyApi } from '@/lib/api/survey';
import { useAuthStore } from '@/stores/authStore';
import { fetchAdminSystemSettings } from '@/lib/api/admin';
import { useLocale } from '@/hooks/useLocale';
import { authApi } from '@/lib/api/auth';
import { listMyCodes } from '@/lib/api/activation';
import PurchaseModal from '@/components/payment/PurchaseModal';

function useActivateBg() {
  useEffect(() => {
    document.documentElement.setAttribute('data-activate-page', 'true');
    return () => document.documentElement.removeAttribute('data-activate-page');
  }, []);
}

type TransitionBackground = 'mist' | 'botanical' | 'paper' | 'path';

const TRANSITION_BACKGROUNDS: Array<{ key: TransitionBackground; label: string }> = [
  { key: 'mist', label: '柔雾留白' },
  { key: 'botanical', label: '细线生长' },
  { key: 'paper', label: '半透明纸层' },
  { key: 'path', label: '路径坐标' },
];

const TRANSITION_APPEARANCE_KEY = 'openlife-transition-appearance-v2';

function ActivatePageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { t } = useLocale();
  useActivateBg();
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showReport, setShowReport] = useState(false);
  const [purchaseOpen, setPurchaseOpen] = useState(false);
  const [transitionBg, setTransitionBg] = useState<TransitionBackground>('paper');
  const [transitionBlur, setTransitionBlur] = useState(6);
  const { user, setUser, isAuthenticated } = useAuthStore();

  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(TRANSITION_APPEARANCE_KEY) || '{}') as {
        background?: TransitionBackground;
        blur?: number;
      };
      if (TRANSITION_BACKGROUNDS.some((item) => item.key === saved.background)) {
        setTransitionBg(saved.background as TransitionBackground);
      }
      if (Number.isFinite(saved.blur)) {
        setTransitionBlur(Math.max(0, Math.min(24, Number(saved.blur))));
      }
    } catch {
      // 外观偏好损坏时回退到推荐组合。
    }
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(
        TRANSITION_APPEARANCE_KEY,
        JSON.stringify({ background: transitionBg, blur: transitionBlur })
      );
    } catch {
      // 隐私模式可能禁止 localStorage；不影响激活流程。
    }
  }, [transitionBg, transitionBlur]);

  // 从后端同步 email_verified 到本地 store
  // 注意：必须以 getState() 取最新 user 并保留 avatar_url，否则会抹掉已上传的头像
  useEffect(() => {
    if (!isAuthenticated) return;
    authApi.getCurrentUser().then((me) => {
      const d = me?.data;
      if (!d) return;
      const u = useAuthStore.getState().user;
      // blob: URL 只在生成它的页面会话内有效，后端 avatar_url 为准，本地残留 blob 一律丢弃
      const localAvatar = u?.avatar_url?.startsWith('blob:') ? null : u?.avatar_url;
      setUser({
        ...u,
        user_id: d.user_id ?? u?.user_id,
        email: d.email ?? u?.email,
        phone: d.phone ?? u?.phone,
        username: d.username ?? u?.username,
        is_super_admin: d.is_super_admin ?? u?.is_super_admin,
        email_verified: d.email_verified,
        avatar_url: d.avatar_url ?? localAvatar ?? undefined,
      });
    }).catch(() => {});
  }, [isAuthenticated]);

  useEffect(() => {
    const fromUrl = searchParams.get('code')?.trim();
    if (fromUrl) {
      setCode(fromUrl);
      return;
    }
    const last = getLastActivationCode();
    if (last) {
      setCode(last);
      return;
    }
    // 新注册用户：若名下已有激活码，自动预填。
    // 只预填「已绑定可用」（status=active）的码——绝不预填未绑定/未激活码；
    // 优先完整码（用户主身份），其次试用码
    if (!isAuthenticated) return;
    let cancelled = false;
    listMyCodes()
      .then((items) => {
        if (cancelled) return;
        const active = items.filter((it) => it.status === 'active');
        const preferred = active.find((it) => it.code_type === 'full') ?? active[0];
        if (preferred?.code) {
          // 不覆盖用户已手动输入的内容
          setCode((prev) => (prev.trim() ? prev : preferred.code));
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [searchParams, isAuthenticated]);

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
      const sessionId: string | undefined = res.data.activation_session_id;
      const workspaceKind = String(res.data.workspace_kind || '').toLowerCase();
      const activationStatus = String(res.data.status || '').toLowerCase();
      const isWorkspaceActivation =
        workspaceKind === 'resident' ||
        workspaceKind === 'fork' ||
        String(activationCode || '').toUpperCase().startsWith('ADM') ||
        String(activationCode || '').toUpperCase().startsWith('SBX');
      setLastActivationCode(activationCode);

      // Load existing session state (preserves unlocked phases on revisit)
      const session = loadSession(activationCode);

      // ── 问卷完成判定：用户维度优先 ──
      // 优先级：用户维度 localStorage > 后端用户维度 API > 激活码维度兜底
      const currentUserId = user?.user_id;
      let surveyDone = getUserSurveyCompleted(currentUserId) || session.surveyCompleted;
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
      if (activationStatus === 'expired' && !adminBypass) {
        setError(t('explore.activate.expiredGuide'));
        return;
      }

      // 用户维度：向后端查询当前用户 basic_info（不依赖激活码）
      if (!surveyDone && user) {
        try {
          const statusRes = await surveyApi.getUserSurveyStatus();
          if (statusRes.data?.completed) {
            surveyDone = true;
            if (currentUserId) setUserSurveyCompleted(currentUserId, true);
          }
        } catch {}
      }

      // 兜底：若用户维度仍无法判定，回退到激活码维度查询（兼容旧数据）
      if (!surveyDone) {
        try {
          const sv = await surveyApi.getForActivation(activationCode);
          const data = sv.data?.survey_data ?? {};
          const hasData = Object.keys(data).some((k) => {
            const v = (data as Record<string, unknown>)[k];
            return v !== undefined && v !== null && v !== '' && (Array.isArray(v) ? v.length > 0 : true);
          });
          if (hasData) {
            surveyDone = true;
            if (currentUserId) setUserSurveyCompleted(currentUserId, true);
          }
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

      // 清除线程缓存，确保进入聊天页时从后端拉取最新数据（跨设备一致性）
      clearThreadCache(activationCode);

      if (surveyDone || adminBypass) {
        router.push(`/explore/chat/${nextSession.currentPhase}`);
      } else {
        router.push('/explore/survey');
      }
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, '激活失败，请检查激活码是否正确'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <main
      className="ol-transition-app"
      data-transition-bg={transitionBg}
      style={{
        '--transition-blur': `${transitionBlur}px`,
        '--transition-veil': String(0.045 + transitionBlur * 0.0045),
      } as CSSProperties}
    >
      <div className="ol-transition-background" aria-hidden="true">
        <span className="ol-transition-image" />
        <span className="ol-transition-filter" />
        <span className="ol-transition-noise" />
      </div>

      <details className="ol-transition-appearance">
        <summary>页面质感</summary>
        <div className="ol-transition-panel">
          <div className="ol-transition-panel-head">
            <strong>选择背景</strong>
            <small>自动记住选择</small>
          </div>
          <div className="ol-transition-options" aria-label="承接页背景">
            {TRANSITION_BACKGROUNDS.map((item) => (
              <button
                key={item.key}
                className="ol-transition-option"
                type="button"
                data-transition-bg-option={item.key}
                aria-pressed={transitionBg === item.key}
                onClick={() => setTransitionBg(item.key)}
              >
                <span>{item.label}</span>
              </button>
            ))}
          </div>
          <div className="ol-transition-blur-control">
            <label className="ol-transition-blur-label" htmlFor="transition-blur">
              <span>背景毛玻璃</span>
              <output htmlFor="transition-blur">{transitionBlur}px</output>
            </label>
            <input
              id="transition-blur"
              type="range"
              min="0"
              max="24"
              step="1"
              value={transitionBlur}
              onChange={(event) => setTransitionBlur(Number(event.target.value))}
              aria-valuetext={`${transitionBlur} 像素`}
            />
            <p>只柔化背景，不影响文字和输入内容。</p>
          </div>
        </div>
      </details>

      <motion.section
        className="ol-transition-stage"
        aria-labelledby="activation-title"
        initial={{ opacity: 0, y: 18 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.58, ease: [0.22, 1, 0.36, 1] }}
      >
        <button type="button" onClick={() => router.push('/')} className="ol-transition-back">
          <span>←</span> {t('explore.intro.back')}
        </button>

        <div className="ol-transition-card">
          <p className="ol-transition-kicker">STEP 0 · OPENLIFE ACCESS</p>
          <h1 id="activation-title">{t('explore.activate.title')}</h1>
          <p className="ol-transition-intro">{t('explore.activate.desc')}</p>

          {user && !user.email_verified && (
            <div className="ol-transition-verify">
              <p>{t('auth.needVerifyFirst')}</p>
              <button type="button" onClick={() => router.push('/dashboard/settings')}>
                {t('auth.goToVerify')}
              </button>
            </div>
          )}

          {(!user || user.email_verified !== false) && (
            <div className="ol-transition-form">
              <div className="ol-transition-field">
                <label htmlFor="activation-code">激活码</label>
                <input
                  id="activation-code"
                  type="text"
                  value={code}
                  onChange={(event) => setCode(event.target.value.toUpperCase())}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' && !loading) void handleActivate();
                  }}
                  placeholder={t('explore.activate.placeholder')}
                  autoComplete="one-time-code"
                  autoCapitalize="characters"
                  spellCheck={false}
                  aria-invalid={Boolean(error)}
                  aria-describedby="activation-help activation-status"
                />
              </div>
              <p className="ol-transition-help" id="activation-help">
                {t('explore.activate.findCodeHint')}
              </p>
              <button
                type="button"
                onClick={() => void handleActivate()}
                disabled={loading || !code.trim()}
                aria-busy={loading}
                className="ol-transition-submit"
              >
                <span>{loading ? t('explore.activate.validating') : t('explore.activate.submit')}</span>
              </button>
              <p
                className={`ol-transition-status${error ? ' is-error' : ''}`}
                id="activation-status"
                role="status"
                aria-live="polite"
              >
                {error || ''}
              </p>
              {showReport && (
                <button
                  type="button"
                  onClick={() => router.push('/explore/report/view')}
                  className="ol-transition-report"
                >
                  {t('common.viewReport')} →
                </button>
              )}
            </div>
          )}

          <div className="ol-transition-links">
            <button type="button" onClick={() => setPurchaseOpen(true)}>
              {t('explore.activate.buyCta')}
            </button>
            <span aria-hidden="true">·</span>
            <button type="button" onClick={() => router.push('/dashboard/codes')}>
              {t('explore.activate.viewAllCodes')}
            </button>
          </div>
        </div>
      </motion.section>

      <PurchaseModal
        open={purchaseOpen}
        onClose={() => setPurchaseOpen(false)}
        onSuccess={(newCode) => setCode(newCode)}
      />
    </main>
  );
}

export default function ActivatePage() {
  return (
    <Suspense fallback={null}>
      <ActivatePageContent />
    </Suspense>
  );
}
