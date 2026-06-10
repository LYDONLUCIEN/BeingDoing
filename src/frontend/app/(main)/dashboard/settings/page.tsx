'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import { useLocale } from '@/hooks/useLocale';
import { getLastActivationCode } from '@/lib/explore/session';
import { surveyApi } from '@/lib/api/survey';
import { apiClient, getApiErrorMessage } from '@/lib/api/client';
import { authApi } from '@/lib/api/auth';
import SurveyFormBd from '@/components/survey/SurveyFormBd';
import type { SurveyData } from '@/lib/survey/schema';

export default function DashboardSettingsPage() {
  const { t } = useLocale();
  const router = useRouter();
  const { user, setUser, isAuthenticated } = useAuthStore();
  const [nickname, setNickname] = useState(user?.username || user?.email || '');
  const [avatarPreview, setAvatarPreview] = useState<string | null>(user?.avatar_url || null);
  const [introData, setIntroData] = useState<Partial<SurveyData>>({});
  const [introLoading, setIntroLoading] = useState(false);
  const [introSaving, setIntroSaving] = useState(false);
  const [introError, setIntroError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);
  const [activationCode, setActivationCode] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Email verification state
  const [verifySending, setVerifySending] = useState(false);
  const [verifyCooldown, setVerifyCooldown] = useState(0);
  const verifyCooldownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 2500);
    return () => clearTimeout(t);
  }, [toast]);

  useEffect(() => {
    setNickname(user?.username || user?.email || '');
    setAvatarPreview(user?.avatar_url || null);
  }, [user]);

  // 从后端同步 email_verified 等字段到本地 store（修复旧登录会话缺失字段的问题）
  useEffect(() => {
    if (!isAuthenticated) return;
    authApi.getCurrentUser().then((me) => {
      const d = me?.data;
      if (d) {
        setUser({
          user_id: d.user_id ?? user?.user_id,
          email: d.email ?? user?.email,
          phone: d.phone ?? user?.phone,
          username: d.username ?? user?.username,
          is_super_admin: d.is_super_admin ?? user?.is_super_admin,
          email_verified: d.email_verified,
        });
      }
    }).catch(() => {});
  }, [isAuthenticated]);

  useEffect(() => {
    const code = getLastActivationCode();
    setActivationCode(code);
    // 始终按用户维度加载问卷数据（不依赖激活码）
    setIntroLoading(true);
    surveyApi
      .getUserSurveyStatus()
      .then((r) => setIntroData(r.data?.survey_data || {}))
      .catch(() => setIntroData({}))
      .finally(() => setIntroLoading(false));
  }, []);

  // Cooldown timer for email verification
  useEffect(() => {
    if (verifyCooldown <= 0) {
      if (verifyCooldownRef.current) clearInterval(verifyCooldownRef.current);
      return;
    }
    verifyCooldownRef.current = setInterval(() => {
      setVerifyCooldown((prev) => {
        if (prev <= 1) {
          if (verifyCooldownRef.current) clearInterval(verifyCooldownRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (verifyCooldownRef.current) clearInterval(verifyCooldownRef.current);
    };
  }, [verifyCooldown]);

  const handleSendVerifyEmail = useCallback(async () => {
    if (!user?.email || verifySending || verifyCooldown > 0) return;
    setVerifySending(true);
    try {
      await apiClient.post('/auth/email-verify/request', { email: user.email });
      setToast({ type: 'success', msg: t('auth.verifyEmailSent') });
      setVerifyCooldown(300); // 5 minutes
    } catch (err: unknown) {
      setToast({ type: 'error', msg: getApiErrorMessage(err, t('auth.verifyFailed')) });
    } finally {
      setVerifySending(false);
    }
  }, [user?.email, verifySending, verifyCooldown, t]);

  const handleAvatarClick = () => {
    fileInputRef.current?.click();
  };

  const handleAvatarChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !file.type.startsWith('image/')) return;
    const url = URL.createObjectURL(file);
    setAvatarPreview(url);
    setUser(user ? { ...user, avatar_url: url } : null);
  };

  const handleNicknameSave = () => {
    if (user) setUser({ ...user, username: nickname || undefined });
  };

  const handleIntroSubmit = async (data: SurveyData) => {
    setIntroSaving(true);
    setIntroError(null);
    try {
      if (activationCode) {
        await surveyApi.saveForActivation(activationCode, data);
      } else {
        await surveyApi.saveForUser(data);
      }
      setIntroData(data);
      setToast({ type: 'success', msg: '保存成功' });
    } catch (e: any) {
      const msg = e?.message || '保存失败';
      setIntroError(msg);
      setToast({ type: 'error', msg });
    } finally {
      setIntroSaving(false);
    }
  };

  const displayName = user?.username || user?.email || t('common.user');
  const initials = (displayName || 'U').slice(0, 2).toUpperCase();

  return (
    <div className="max-w-3xl space-y-10">
      <h1 className="text-2xl font-semibold text-bd-fg">{t('dashboard.setting')}</h1>

      {/* 基本信息修改 */}
      <section className="rounded-2xl border border-bd-border bg-bd-card/80 backdrop-blur-lg p-8 shadow-sm">
        <h2 className="text-lg font-medium text-bd-fg mb-1">{t('dashboard.basicInfo')}</h2>
        <p className="text-sm text-bd-muted mb-6">{t('dashboard.basicInfoDesc')}</p>
        <div className="flex flex-col sm:flex-row items-start gap-8">
          <div className="flex flex-col items-center gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleAvatarChange}
            />
            <button
              type="button"
              onClick={handleAvatarClick}
              className="w-24 h-24 rounded-full flex items-center justify-center text-white text-2xl font-semibold transition-all overflow-hidden ring-2 ring-black/30 ring-offset-2 ring-offset-bd-card shadow-[inset_0_1px_0_rgba(255,255,255,0.12),0_4px_12px_rgba(0,0,0,0.25)] hover:ring-black/45"
              style={{
                background: avatarPreview
                  ? `url(${avatarPreview}) center/cover`
                  : 'linear-gradient(135deg, var(--bd-phase-values), var(--bd-phase-strengths))',
              }}
              title={t('dashboard.clickAvatarToUpload')}
            >
              {!avatarPreview && initials}
            </button>
            <span className="text-xs text-bd-subtle">{t('dashboard.clickAvatarToUpload')}</span>
          </div>
          <div className="flex-1 min-w-0 space-y-4">
            <div>
              <label className="block text-sm font-medium text-bd-muted mb-1.5">{t('dashboard.nickname')}</label>
              <input
                type="text"
                value={nickname}
                onChange={(e) => setNickname(e.target.value)}
                onBlur={handleNicknameSave}
                placeholder={t('common.user')}
                className="w-full rounded-xl border border-bd-border bg-bd-overlay px-4 py-2.5 text-bd-fg placeholder:text-bd-subtle focus:border-bd-ui-accent focus:ring-2 focus:ring-bd-ui-accent/20 outline-none transition-colors"
              />
            </div>
          </div>
        </div>
      </section>

      {/* 邮箱验证 */}
      {user?.email && (
        <section className="rounded-2xl border border-bd-border bg-bd-card/80 backdrop-blur-lg p-8 shadow-sm">
          <h2 className="text-lg font-medium text-bd-fg mb-1">{t('auth.emailVerify')}</h2>
          <p className="text-sm text-bd-muted mb-6">{t('auth.verifyEmailDesc')}</p>
          <div className="flex items-center gap-4">
            <div className="flex-1 min-w-0">
              <p className="text-sm text-bd-fg">{user.email}</p>
              <p className="text-xs mt-1" style={{ color: 'var(--bd-fg-muted)' }}>
                {t('dashboard.setting')}
              </p>
            </div>
            {user.email_verified ? (
              <span
                className="inline-block px-3 py-1 rounded-full text-xs font-medium"
                style={{ background: 'rgba(34,197,94,0.12)', color: '#16a34a' }}
              >
                {t('auth.emailVerified')}
              </span>
            ) : (
              <div className="flex items-center gap-3">
                <span
                  className="inline-block px-3 py-1 rounded-full text-xs font-medium"
                  style={{ background: 'rgba(239,68,68,0.12)', color: '#dc2626' }}
                >
                  {t('auth.emailNotVerified')}
                </span>
                <button
                  type="button"
                  onClick={handleSendVerifyEmail}
                  disabled={verifySending || verifyCooldown > 0}
                  className="px-4 py-2 rounded-xl text-sm font-medium text-white transition-all bd-btn-black disabled:opacity-50"
                >
                  {verifyCooldown > 0
                    ? `${Math.floor(verifyCooldown / 60)}:${String(verifyCooldown % 60).padStart(2, '0')}`
                    : verifySending
                      ? '...'
                      : t('auth.sendVerifyEmail')}
                </button>
              </div>
            )}
          </div>
        </section>
      )}

      {/* 个人简介信息 */}
      <section className="rounded-2xl border border-bd-border bg-bd-card/80 backdrop-blur-lg p-8 shadow-sm">
        <h2 className="text-lg font-medium text-bd-fg mb-1">{t('dashboard.personalIntro')}</h2>
        <p className="text-sm text-bd-muted mb-6">{t('dashboard.personalIntroDesc')}</p>
        {introError && <p className="text-sm text-bd-err mb-4">{introError}</p>}
        <SurveyFormBd
          initialData={introData}
          loading={introLoading}
          saving={introSaving}
          submitLabel="保存修改"
          showSkip={false}
          onSubmit={handleIntroSubmit}
        />
      </section>

      {/* Toast */}
      {toast && (
        <div
          role="alert"
          className={`fixed bottom-8 left-1/2 -translate-x-1/2 px-5 py-3 rounded-xl text-sm font-medium shadow-lg z-[100] ${
            toast.type === 'success'
              ? 'bg-emerald-600/95 text-white'
              : 'bg-red-600/95 text-white'
          }`}
          style={{ animation: 'toast-in 0.25s ease-out' }}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}
