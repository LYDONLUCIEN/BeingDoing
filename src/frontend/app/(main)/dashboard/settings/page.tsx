'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import type { AxiosError } from 'axios';
import { useAuthStore } from '@/stores/authStore';
import { useLocale } from '@/hooks/useLocale';
import { getLastActivationCode } from '@/lib/explore/session';
import { surveyApi } from '@/lib/api/survey';
import { apiClient, getApiErrorMessage, isRequestCanceled } from '@/lib/api/client';
import { authApi } from '@/lib/api/auth';
import { usersApi } from '@/lib/api/users';
import type { SurveyData } from '@/lib/survey/schema';
import { computeSurveyCompletion } from '@/lib/survey/completion';
import DashboardPageHeader from '@/components/dashboard/DashboardPageHeader';
import { LockKeyhole, Mail, X } from 'lucide-react';

export default function DashboardSettingsPage() {
  const { t } = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user, setUser, isAuthenticated, logout } = useAuthStore();
  const isLocalUiPreview =
    process.env.NODE_ENV === 'development' && searchParams.get('ui_preview') === '1';
  const [nickname, setNickname] = useState(user?.username || user?.email || '');
  const [avatarPreview, setAvatarPreview] = useState<string | null>(user?.avatar_url || null);
  const [introData, setIntroData] = useState<Partial<SurveyData>>({});
  const [toast, setToast] = useState<{ type: 'success' | 'error'; msg: string } | null>(null);
  const [activationCode, setActivationCode] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Email verification state
  const [verifySending, setVerifySending] = useState(false);
  const [verifyCooldown, setVerifyCooldown] = useState(0);
  const verifyCooldownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 账户注销 state
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [deleteConfirmText, setDeleteConfirmText] = useState('');
  const [deleteWorking, setDeleteWorking] = useState(false);
  const DELETE_CONFIRM_PHRASE = '注销我的账户';

  // 修改密码 state
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [pwdSaving, setPwdSaving] = useState(false);
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false);
  // 防爆破锁定倒计时（秒，后端 423 login_locked 下发）
  const [pwdLockSeconds, setPwdLockSeconds] = useState(0);
  const pwdLockRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
    const code = getLastActivationCode();
    setActivationCode(code);
    if (isLocalUiPreview) {
      setIntroData({});
      return;
    }
    // 始终按用户维度加载问卷数据（不依赖激活码）
    surveyApi
      .getUserSurveyStatus()
      .then((r) => setIntroData(r.data?.survey_data || {}))
      .catch(() => setIntroData({}));
  }, [isLocalUiPreview]);

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

  // 修改密码锁定倒计时
  useEffect(() => {
    if (pwdLockSeconds <= 0) {
      if (pwdLockRef.current) clearInterval(pwdLockRef.current);
      return;
    }
    pwdLockRef.current = setInterval(() => {
      setPwdLockSeconds((prev) => {
        if (prev <= 1) {
          if (pwdLockRef.current) clearInterval(pwdLockRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (pwdLockRef.current) clearInterval(pwdLockRef.current);
    };
  }, [pwdLockSeconds]);

  const handleChangePassword = async () => {
    if (pwdSaving || pwdLockSeconds > 0) return;
    if (!oldPassword || !newPassword || !confirmNewPassword) {
      setToast({ type: 'error', msg: '请完整填写旧密码和两次新密码' });
      return;
    }
    if (newPassword.length < 6) {
      setToast({ type: 'error', msg: '新密码至少 6 位' });
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setToast({ type: 'error', msg: '两次输入的新密码不一致' });
      return;
    }
    if (newPassword === oldPassword) {
      setToast({ type: 'error', msg: '新密码不能与旧密码相同' });
      return;
    }
    setPwdSaving(true);
    try {
      await authApi.changePassword({ old_password: oldPassword, new_password: newPassword });
      // 后端已撤销全部会话（含当前），本地登出并引导重新登录
      setToast({ type: 'success', msg: '密码修改成功，请使用新密码重新登录' });
      setTimeout(() => {
        logout();
        router.push('/');
      }, 1200);
    } catch (err: unknown) {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      if (axiosErr?.response?.status === 423) {
        // 防爆破锁定：解析 retry_after_seconds 并启动倒计时（与 AuthModal 登录锁定同口径）
        let seconds = 15 * 60;
        try {
          const parsed = JSON.parse(axiosErr.response?.data?.detail || '{}');
          if (parsed?.type === 'login_locked' && Number(parsed?.retry_after_seconds) > 0) {
            seconds = Number(parsed.retry_after_seconds);
          }
        } catch { /* 解析失败用默认锁定时长 */ }
        setPwdLockSeconds(seconds);
        setToast({ type: 'error', msg: '尝试次数过多，账号已临时锁定，请稍后再试' });
      } else if (!isRequestCanceled(err)) {
        setToast({ type: 'error', msg: getApiErrorMessage(err, '修改密码失败，请稍后重试') });
      }
    } finally {
      setPwdSaving(false);
    }
  };

  const closePasswordDialog = () => {
    if (pwdSaving) return;
    setPasswordDialogOpen(false);
    setOldPassword('');
    setNewPassword('');
    setConfirmNewPassword('');
  };

  const openDeleteDialog = () => {
    setDeleteConfirmText('');
    setDeleteDialogOpen(true);
  };

  const handleDeleteAccount = async () => {
    if (deleteWorking || deleteConfirmText !== DELETE_CONFIRM_PHRASE) return;
    setDeleteWorking(true);
    try {
      await authApi.deleteAccount(deleteConfirmText);
      setDeleteDialogOpen(false);
      setToast({ type: 'success', msg: '账户已注销，数据将保留 30 天，期间登录可恢复' });
      // 短暂展示提示后清除登录态并跳转
      setTimeout(() => {
        logout();
        router.push('/');
      }, 800);
    } catch (err: unknown) {
      setToast({ type: 'error', msg: getApiErrorMessage(err, '注销失败，请稍后重试') });
    } finally {
      setDeleteWorking(false);
    }
  };

  const handleAvatarClick = () => {
    fileInputRef.current?.click();
  };

  const [avatarUploading, setAvatarUploading] = useState(false);

  const handleAvatarChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // 允许重复选择同一文件
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setToast({ type: 'error', msg: '仅支持图片文件' });
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setToast({ type: 'error', msg: '图片大小不能超过 5MB' });
      return;
    }
    // 本地即时预览（blob 仅当前会话有效，仅作预览；上传成功后被服务器 URL 替换）
    const previewUrl = URL.createObjectURL(file);
    setAvatarPreview(previewUrl);
    setAvatarUploading(true);
    try {
      const res = await usersApi.uploadAvatar(file);
      const url = res.data?.avatar_url;
      if (url) {
        setAvatarPreview(url);
        const u = useAuthStore.getState().user;
        setUser(u ? { ...u, avatar_url: url } : null);
        setToast({ type: 'success', msg: '头像已更新' });
      }
    } catch (err: unknown) {
      if (!isRequestCanceled(err)) {
        // 失败回退预览到已保存的头像
        setAvatarPreview(useAuthStore.getState().user?.avatar_url || null);
        setToast({ type: 'error', msg: getApiErrorMessage(err, '头像上传失败，请稍后重试') });
      }
    } finally {
      setAvatarUploading(false);
    }
  };

  const handleNicknameSave = async () => {
    const u = useAuthStore.getState().user;
    if (!u) return;
    const name = nickname.trim();
    if (name === (u.username || '')) return; // 无改动不请求
    if (!name) {
      setNickname(u.username || u.email || ''); // 空白不保存，回退显示
      return;
    }
    try {
      await usersApi.updateMe({ username: name });
      setUser({ ...u, username: name });
      setToast({ type: 'success', msg: '昵称已保存' });
    } catch (err: unknown) {
      if (!isRequestCanceled(err)) {
        setNickname(u.username || u.email || '');
        setToast({ type: 'error', msg: getApiErrorMessage(err, '昵称保存失败，请稍后重试') });
      }
    }
  };

  // 资料完成度（卡片展示用，编辑在 /dashboard/profile/edit 独立页）
  const introCompletion = computeSurveyCompletion(introData as SurveyData);

  const displayName = user?.username || user?.email || t('common.user');
  const initials = (displayName || 'U').slice(0, 2).toUpperCase();
  const accountEmail = user?.email || (isLocalUiPreview ? 'preview@openlife.cn' : null);
  const emailVerified = user?.email_verified ?? isLocalUiPreview;

  return (
    <div className="ol-profile-content ol-settings-page space-y-10">
      <DashboardPageHeader
        kicker="ACCOUNT & PROFILE"
        title={t('dashboard.setting')}
        description="管理个人资料、探索背景与账户安全设置。"
      />

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
              disabled={avatarUploading}
              className="w-24 h-24 rounded-full flex items-center justify-center text-white text-2xl font-semibold transition-all overflow-hidden ring-2 ring-black/30 ring-offset-2 ring-offset-bd-card shadow-[inset_0_1px_0_rgba(255,255,255,0.12),0_4px_12px_rgba(0,0,0,0.25)] hover:ring-black/45 disabled:opacity-60 disabled:cursor-wait"
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

      {/* 账号安全：保留原邮箱验证与修改密码接口，仅重排交互入口 */}
      <section className="ol-settings-security-section rounded-2xl border border-bd-border bg-bd-card/80 backdrop-blur-lg p-8 shadow-sm">
        <div className="ol-settings-section-heading">
          <div>
            <span>SECURITY</span>
            <h2>账号安全</h2>
          </div>
          <p>集中管理登录凭证与安全通知，不改变现有验证流程。</p>
        </div>
        <div className="ol-account-security-grid">
          {accountEmail && (
            <article className="ol-account-security-card">
              <header className="ol-account-security-head">
                <div className="ol-account-security-title">
                  <span className="ol-account-security-icon" aria-hidden><Mail /></span>
                  <div>
                    <h3>{t('auth.emailVerify')}</h3>
                    <p>用于账户安全提醒、密码找回与重要服务通知。</p>
                  </div>
                </div>
                <span className={`ol-account-security-status ${emailVerified ? 'is-verified' : ''}`}>
                  {emailVerified ? t('auth.emailVerified') : t('auth.emailNotVerified')}
                </span>
              </header>
              <div className="ol-account-security-body">
                <div className="ol-account-security-value">
                  <small>账户邮箱</small>
                  <strong title={accountEmail}>{accountEmail}</strong>
                  <p>{emailVerified ? '该邮箱已完成验证，可用于安全通知与密码找回。' : '验证邮件只会发送到当前账户邮箱。'}</p>
                </div>
                {!emailVerified && (
                  <button
                    type="button"
                    onClick={handleSendVerifyEmail}
                    disabled={verifySending || verifyCooldown > 0}
                    className="ol-account-security-action"
                  >
                    {verifyCooldown > 0
                      ? `${Math.floor(verifyCooldown / 60)}:${String(verifyCooldown % 60).padStart(2, '0')}`
                      : verifySending
                        ? '发送中…'
                        : t('auth.sendVerifyEmail')}
                  </button>
                )}
              </div>
            </article>
          )}

          <article className="ol-account-security-card">
            <header className="ol-account-security-head">
              <div className="ol-account-security-title">
                <span className="ol-account-security-icon" aria-hidden><LockKeyhole /></span>
                <div>
                  <h3>登录密码</h3>
                  <p>定期更新密码，避免与其他产品使用相同的登录凭证。</p>
                </div>
              </div>
              <span className="ol-account-security-status is-verified">已设置</span>
            </header>
            <div className="ol-account-security-body">
              <div className="ol-account-security-value">
                <small>密码安全</small>
                <strong aria-label="密码已隐藏">••••••••••••</strong>
                <p>修改成功后，所有设备都需要使用新密码重新登录。</p>
              </div>
              <button
                type="button"
                onClick={() => setPasswordDialogOpen(true)}
                disabled={pwdSaving}
                className="ol-account-security-action"
              >
                修改密码
              </button>
            </div>
          </article>
        </div>
      </section>

      {/* 个人简介信息：不在此摊开表单，点开进入独立编辑页（含填写进度） */}
      <section className="rounded-2xl border border-bd-border bg-bd-card/80 backdrop-blur-lg p-8 shadow-sm">
        <h2 className="text-lg font-medium text-bd-fg mb-1">{t('dashboard.personalIntro')}</h2>
        <p className="text-sm text-bd-muted mb-6">{t('dashboard.personalIntroDesc')}</p>
        <div className="mb-5">
          <div className="ol-profile-progress-meta">
            <span>资料完成度</span>
            <strong>
              {introCompletion.filled}/{introCompletion.total} · {introCompletion.percent}%
            </strong>
          </div>
          <div
            className="ol-profile-progress-track"
            role="progressbar"
            aria-valuenow={introCompletion.percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="资料完成度"
          >
            <div className="ol-profile-progress-fill" style={{ width: `${introCompletion.percent}%` }} />
          </div>
        </div>
        <button
          type="button"
          onClick={() => router.push('/dashboard/profile/edit')}
          className="inline-flex items-center gap-2 rounded-full bg-[#222b35] px-5 py-2.5 text-sm font-medium text-white transition-all hover:bg-[#303b46] hover:-translate-y-px"
        >
          编辑个人资料 →
        </button>
      </section>

      {/* 危险区：注销账户 */}
      <section className="rounded-2xl border border-rose-300/60 bg-bd-card/80 backdrop-blur-lg p-8 shadow-sm">
        <h2 className="text-lg font-medium text-rose-600 mb-1">危险区</h2>
        <p className="text-sm text-bd-muted mb-6">
          注销后将无法使用任何功能；数据保留 30 天，期间登录可恢复；到期后数据永久删除，无法找回。
        </p>
        <button
          type="button"
          onClick={openDeleteDialog}
          className="px-4 py-2 rounded-xl text-sm font-medium text-white bg-rose-600 hover:bg-rose-700 transition-colors"
        >
          注销账户
        </button>
      </section>

      {/* 修改密码弹窗：提交仍复用原 handleChangePassword 与安全锁定逻辑 */}
      {passwordDialogOpen && (
        <div className="ol-settings-dialog-shell">
          <button
            type="button"
            className="ol-settings-dialog-backdrop"
            aria-label="关闭修改密码弹窗"
            onClick={closePasswordDialog}
          />
          <form
            role="dialog"
            aria-modal="true"
            aria-labelledby="password-dialog-title"
            className="ol-settings-dialog"
            onSubmit={(event) => {
              event.preventDefault();
              void handleChangePassword();
            }}
          >
            <header>
              <div>
                <span>SECURITY</span>
                <h3 id="password-dialog-title">修改登录密码</h3>
              </div>
              <button type="button" aria-label="关闭" onClick={closePasswordDialog} disabled={pwdSaving}>
                <X />
              </button>
            </header>
            <p className="ol-settings-dialog-description">
              修改成功后所有设备将退出登录；忘记旧密码可通过登录弹窗的「忘记密码」重置。
            </p>
            <div className="ol-settings-password-fields">
              <label>
                <span>旧密码</span>
                <input
                  type="password"
                  value={oldPassword}
                  onChange={(event) => setOldPassword(event.target.value)}
                  placeholder="请输入当前密码"
                  autoComplete="current-password"
                  disabled={pwdSaving || pwdLockSeconds > 0}
                  autoFocus
                />
              </label>
              <label>
                <span>新密码</span>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  placeholder="至少 6 位"
                  autoComplete="new-password"
                  disabled={pwdSaving || pwdLockSeconds > 0}
                />
              </label>
              <label>
                <span>确认新密码</span>
                <input
                  type="password"
                  value={confirmNewPassword}
                  onChange={(event) => setConfirmNewPassword(event.target.value)}
                  placeholder="再次输入新密码"
                  autoComplete="new-password"
                  disabled={pwdSaving || pwdLockSeconds > 0}
                />
              </label>
            </div>
            {pwdLockSeconds > 0 && (
              <p className="ol-settings-lock-note">
                尝试次数过多，账号已临时锁定 {Math.floor(pwdLockSeconds / 60)}:{String(pwdLockSeconds % 60).padStart(2, '0')}
              </p>
            )}
            <footer>
              <button type="button" onClick={closePasswordDialog} disabled={pwdSaving}>取消</button>
              <button type="submit" disabled={pwdSaving || pwdLockSeconds > 0}>
                {pwdSaving ? '提交中…' : '确认修改'}
              </button>
            </footer>
          </form>
        </div>
      )}

      {/* 注销账户二次确认弹窗 */}
      {deleteDialogOpen && (
        <div className="fixed inset-0 z-[110] flex items-center justify-center px-5">
          <button
            type="button"
            className="absolute inset-0 bg-stone-900/25 backdrop-blur-[2px]"
            aria-label="关闭"
            onClick={() => !deleteWorking && setDeleteDialogOpen(false)}
          />
          <div
            role="dialog"
            aria-modal
            className="relative w-full max-w-sm rounded-2xl border border-bd-border bg-bd-card px-6 py-5 shadow-xl space-y-4"
          >
            <h3 className="text-sm font-semibold text-rose-600">确认注销账户</h3>
            <div className="space-y-1.5 text-xs text-bd-muted">
              <p>注销后你将无法使用任何功能：</p>
              <p>· 数据保留 30 天，期间登录可恢复账户；</p>
              <p>· 到期后数据将被永久删除，无法找回。</p>
            </div>
            <div className="space-y-1.5">
              <p className="text-xs text-bd-subtle">
                请输入「{DELETE_CONFIRM_PHRASE}」以确认注销：
              </p>
              <input
                type="text"
                value={deleteConfirmText}
                onChange={(e) => setDeleteConfirmText(e.target.value)}
                placeholder={DELETE_CONFIRM_PHRASE}
                disabled={deleteWorking}
                className="w-full rounded-xl border border-bd-border bg-bd-overlay px-4 py-2.5 text-sm text-bd-fg placeholder:text-bd-subtle focus:border-rose-500 focus:ring-2 focus:ring-rose-500/20 outline-none transition-colors"
              />
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setDeleteDialogOpen(false)}
                disabled={deleteWorking}
                className="px-3 py-1.5 rounded-lg border border-bd-border text-bd-muted hover:text-bd-fg hover:bg-bd-overlay-md text-xs"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void handleDeleteAccount()}
                disabled={deleteWorking || deleteConfirmText !== DELETE_CONFIRM_PHRASE}
                className="px-3 py-1.5 rounded-lg bg-rose-600 text-white text-xs font-medium disabled:opacity-50"
              >
                {deleteWorking ? '注销中…' : '确认注销'}
              </button>
            </div>
          </div>
        </div>
      )}

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
