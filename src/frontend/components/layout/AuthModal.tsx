'use client';

import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { X } from 'lucide-react';
import { authApi } from '@/lib/api/auth';
import { getApiErrorMessage } from '@/lib/api/client';
import { useAuthStore } from '@/stores/authStore';
import { useRouter, usePathname } from 'next/navigation';

const loginSchema = z.object({
  email: z.string().email().optional().or(z.literal('')),
  phone: z.string().optional(),
  password: z.string().min(6, '密码至少6位'),
}).refine((data) => data.email || data.phone, {
  message: '邮箱或手机号至少提供一个',
  path: ['email'],
});

const registerSchema = z.object({
  email: z.string().email().optional().or(z.literal('')),
  phone: z.string().optional(),
  username: z.string().optional(),
  password: z.string().min(6, '密码至少6位'),
  confirmPassword: z.string(),
}).refine((data) => data.email || data.phone, {
  message: '邮箱或手机号至少提供一个',
  path: ['email'],
}).refine((data) => data.password === data.confirmPassword, {
  message: '两次输入的密码不一致',
  path: ['confirmPassword'],
});

type LoginFormData = z.infer<typeof loginSchema>;
type RegisterFormData = z.infer<typeof registerSchema>;

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  redirectTo?: string;
}

export default function AuthModal({ isOpen, onClose, redirectTo = '/' }: AuthModalProps) {
  const [mode, setMode] = useState<'login' | 'register' | 'forgot'>('login');
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [resetEmail, setResetEmail] = useState('');
  const [resetCode, setResetCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmNewPassword, setConfirmNewPassword] = useState('');
  const [resetCooldown, setResetCooldown] = useState(0);
  const { setUser, setToken } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();

  const loginForm = useForm<LoginFormData>({ resolver: zodResolver(loginSchema) });
  const registerForm = useForm<RegisterFormData>({ resolver: zodResolver(registerSchema) });

  const [successMsg, setSuccessMsg] = useState('');
  useEffect(() => {
    if (mode !== 'forgot' || resetCooldown <= 0) return;
    const timer = window.setInterval(() => {
      setResetCooldown((prev) => {
        if (prev <= 1) {
          window.clearInterval(timer);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [mode, resetCooldown]);

  const handleSuccess = (targetPath: string) => {
    setSuccessMsg('');
    onClose();
    if (pathname !== targetPath) router.push(targetPath);
    else router.refresh();
  };

  const normalizeEmail = (email?: string) => {
    const normalized = (email || '').trim().toLowerCase();
    return normalized || undefined;
  };

  const onLoginSubmit = async (data: LoginFormData) => {
    setError('');
    setSuccessMsg('');
    setLoading(true);
    try {
      const response = await authApi.login({
        email: normalizeEmail(data.email),
        phone: data.phone?.trim() || undefined,
        password: data.password,
      });
      const resData = response?.data;
      if (response?.code === 200 && resData?.token) {
        try {
          const me = await authApi.getCurrentUser();
          const userData = me?.data || resData;
          setUser({
            user_id: userData?.user_id ?? resData.user_id,
            email: userData?.email ?? resData.email,
            phone: userData?.phone ?? resData.phone,
            username: userData?.username ?? resData.username,
            is_super_admin: userData?.is_super_admin,
            email_verified: userData?.email_verified ?? resData.email_verified,
          });
        } catch {
          setUser({
            user_id: resData.user_id,
            email: resData.email,
            phone: resData.phone,
            username: resData.username,
            is_super_admin: false,
            email_verified: resData.email_verified,
          });
        }
        setToken(resData.token);
        setSuccessMsg('登录成功！');
        // 短暂展示成功提示后关闭并跳转，确保 UI 更新
        setTimeout(() => {
          setLoading(false);
          handleSuccess(redirectTo);
        }, 400);
      } else {
        setLoading(false);
      }
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, '登录失败，请检查邮箱/手机号和密码'));
    } finally {
      setLoading(false);
    }
  };

  const onRegisterSubmit = async (data: RegisterFormData) => {
    setError('');
    setSuccessMsg('');
    setLoading(true);
    try {
      const response = await authApi.register({
        email: normalizeEmail(data.email),
        phone: data.phone?.trim() || undefined,
        username: data.username?.trim() || undefined,
        password: data.password,
      });
      const resData = response?.data;
      if (response?.code === 200 && resData?.token) {
        setToken(resData.token);
        try {
          const me = await authApi.getCurrentUser();
          const userData = me?.data || resData;
          setUser({
            user_id: userData?.user_id ?? resData.user_id,
            email: userData?.email ?? resData.email,
            phone: userData?.phone ?? resData.phone,
            username: userData?.username ?? resData.username,
            is_super_admin: userData?.is_super_admin,
            email_verified: userData?.email_verified ?? resData.email_verified,
          });
        } catch {
          setUser({
            user_id: resData.user_id,
            email: resData.email,
            phone: resData.phone,
            username: resData.username,
            is_super_admin: false,
            email_verified: resData.email_verified,
          });
        }
        setSuccessMsg('注册成功！');
        setTimeout(() => {
          setLoading(false);
          handleSuccess(redirectTo);
        }, 400);
      }
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, '注册失败，请重试'));
    } finally {
      setLoading(false);
    }
  };

  const sendResetCode = async () => {
    const normalizedEmail = normalizeEmail(resetEmail);
    if (!normalizedEmail) {
      setError('请输入邮箱');
      return;
    }
    if (resetCooldown > 0) {
      setError(`请 ${resetCooldown}s 后再发送`);
      return;
    }
    setError('');
    setSuccessMsg('');
    setLoading(true);
    try {
      await authApi.requestPasswordResetCode({ email: normalizedEmail });
      setSuccessMsg('验证码已发送到该账号的注册邮箱（5分钟有效）');
      setResetCooldown(60);
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, '发送验证码失败，请稍后重试'));
    } finally {
      setLoading(false);
    }
  };

  const confirmReset = async () => {
    const normalizedEmail = normalizeEmail(resetEmail);
    if (!normalizedEmail || !resetCode || !newPassword || !confirmNewPassword) {
      setError('请完整填写邮箱、验证码和两次新密码');
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setError('两次输入的新密码不一致');
      return;
    }
    setError('');
    setSuccessMsg('');
    setLoading(true);
    try {
      await authApi.confirmPasswordReset({
        email: normalizedEmail,
        code: resetCode.trim(),
        new_password: newPassword,
      });
      setSuccessMsg('密码重置成功，请使用新密码登录');
      setMode('login');
    } catch (err: unknown) {
      setError(getApiErrorMessage(err, '重置密码失败，请检查验证码是否正确'));
    } finally {
      setLoading(false);
    }
  };

  const switchMode = (target: 'login' | 'register') => {
    setError('');
    loginForm.reset();
    registerForm.reset();
    setMode(target);
  };

  if (!isOpen) return null;

  const inputClass =
    'w-full px-3 py-2.5 rounded-lg text-sm outline-none transition-colors bg-bd-overlay border border-bd-border text-bd-fg placeholder:text-bd-subtle focus:border-bd-primary focus:ring-2 focus:ring-bd-primary-dim';
  const labelClass = 'block text-sm font-medium text-bd-muted mb-1.5';
  const errorClass = 'mt-1 text-xs text-bd-err';

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 backdrop-blur-md"
        style={{ background: 'rgba(0,0,0,0.55)' }}
        onClick={onClose}
      />

      {/* Modal */}
      <div
        className="relative w-full max-w-md max-h-[90vh] rounded-2xl overflow-y-auto animate-in fade-in zoom-in-95 duration-200 shadow-bd-lg"
        style={{
          backgroundColor: 'var(--bd-bg-surface)',
          border: '1px solid var(--bd-border)',
        }}
      >
        {/* Close */}
        <button
          type="button"
          onClick={onClose}
          className="absolute top-4 right-4 z-10 p-1 rounded-lg text-bd-subtle hover:text-bd-fg hover:bg-bd-overlay-md transition-colors"
        >
          <X size={18} />
        </button>

        <div className="px-6 pt-8 pb-6">
          {/* Title */}
          <div className="text-center mb-6">
            <h2 className="text-2xl font-bold text-bd-fg">Being · Doing</h2>
            <p className="text-bd-muted mt-1 text-sm">
              {mode === 'login' ? '欢迎回来' : mode === 'register' ? '开始你的探索之旅' : '通过账号注册邮箱重置密码'}
            </p>
          </div>

          {/* Tab switcher */}
          <div className="flex bg-bd-overlay rounded-lg p-1 mb-6">
            {(['login', 'register'] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => { if (mode !== m) switchMode(m); }}
                className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
                  mode === m
                    ? 'bg-bd-primary text-bd-primary-fg shadow-sm'
                    : 'text-bd-muted hover:text-bd-fg'
                }`}
              >
                {m === 'login' ? '登录' : '注册'}
              </button>
            ))}
          </div>

          {/* Error */}
          {error && (
            <div className="mb-4 p-3 rounded-lg text-sm bg-bd-error-dim border border-bd-err text-bd-err">
              {error}
            </div>
          )}
          {/* Success */}
          {successMsg && (
            <div className="mb-4 p-3 rounded-lg text-sm bg-green-500/15 border border-green-500/50 text-green-700 dark:text-green-400">
              {successMsg}
            </div>
          )}

          {/* Login form */}
          {mode === 'login' ? (
            <form onSubmit={loginForm.handleSubmit(onLoginSubmit)} className="space-y-4">
              <div>
                <label htmlFor="login-email" className={labelClass}>邮箱</label>
                <input {...loginForm.register('email')} type="email" id="login-email" className={inputClass} placeholder="your@email.com" />
                {loginForm.formState.errors.email && <p className={errorClass}>{loginForm.formState.errors.email.message}</p>}
              </div>
              <div>
                <label htmlFor="login-phone" className={labelClass}>手机号（可选）</label>
                <input {...loginForm.register('phone')} type="tel" id="login-phone" className={inputClass} placeholder="13800138000" />
              </div>
              <div>
                <label htmlFor="login-password" className={labelClass}>密码</label>
                <input {...loginForm.register('password')} type="password" id="login-password" className={inputClass} placeholder="至少6位" />
                {loginForm.formState.errors.password && <p className={errorClass}>{loginForm.formState.errors.password.message}</p>}
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 rounded-lg font-medium text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-bd-primary-fg"
                style={{ background: 'var(--bd-primary)' }}
                onMouseEnter={(e) => !loading && (e.currentTarget.style.background = 'var(--bd-primary-alt)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--bd-primary)')}
              >
                {loading ? '登录中...' : '登录'}
              </button>
              <div className="text-right">
                <button
                  type="button"
                  className="text-sm text-bd-primary hover:underline"
                  onClick={() => {
                    setError('');
                    setSuccessMsg('');
                    setMode('forgot');
                  }}
                >
                  忘记密码？
                </button>
              </div>
            </form>
          ) : mode === 'forgot' ? (
            <div className="space-y-3.5">
              <div>
                <label className={labelClass}>邮箱</label>
                <input
                  type="email"
                  className={inputClass}
                  placeholder="请输入账号注册时绑定的邮箱"
                  value={resetEmail}
                  onChange={(e) => setResetEmail(e.target.value)}
                />
              </div>
              <button
                type="button"
                disabled={loading || resetCooldown > 0}
                onClick={sendResetCode}
                className="w-full py-2.5 px-4 rounded-lg font-medium text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-bd-primary-fg"
                style={{ background: 'var(--bd-primary)' }}
              >
                {loading ? '发送中...' : resetCooldown > 0 ? `${resetCooldown}s 后可重发` : '发送验证码'}
              </button>

              <div>
                <label className={labelClass}>验证码</label>
                <input
                  type="text"
                  className={inputClass}
                  placeholder="请输入邮箱验证码"
                  value={resetCode}
                  onChange={(e) => setResetCode(e.target.value)}
                />
              </div>
              <div>
                <label className={labelClass}>新密码</label>
                <input
                  type="password"
                  className={inputClass}
                  placeholder="至少6位"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
              </div>
              <div>
                <label className={labelClass}>确认新密码</label>
                <input
                  type="password"
                  className={inputClass}
                  placeholder="请再次输入新密码"
                  value={confirmNewPassword}
                  onChange={(e) => setConfirmNewPassword(e.target.value)}
                />
              </div>
              <button
                type="button"
                disabled={loading}
                onClick={confirmReset}
                className="w-full py-2.5 px-4 rounded-lg font-medium text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-bd-primary-fg"
                style={{ background: 'var(--bd-primary)' }}
              >
                {loading ? '提交中...' : '重置密码'}
              </button>
              <div className="text-right">
                <button
                  type="button"
                  className="text-sm text-bd-primary hover:underline"
                  onClick={() => setMode('login')}
                >
                  返回登录
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={registerForm.handleSubmit(onRegisterSubmit)} className="space-y-3.5">
              <div>
                <label htmlFor="register-email" className={labelClass}>邮箱</label>
                <input {...registerForm.register('email')} type="email" id="register-email" className={inputClass} placeholder="your@email.com" />
                {registerForm.formState.errors.email && <p className={errorClass}>{registerForm.formState.errors.email.message}</p>}
              </div>
              <div>
                <label htmlFor="register-phone" className={labelClass}>手机号（可选）</label>
                <input {...registerForm.register('phone')} type="tel" id="register-phone" className={inputClass} placeholder="13800138000" />
              </div>
              <div>
                <label htmlFor="register-username" className={labelClass}>用户名（可选）</label>
                <input {...registerForm.register('username')} type="text" id="register-username" className={inputClass} placeholder="你的昵称" />
              </div>
              <div>
                <label htmlFor="register-password" className={labelClass}>密码</label>
                <input {...registerForm.register('password')} type="password" id="register-password" className={inputClass} placeholder="至少6位" />
                {registerForm.formState.errors.password && <p className={errorClass}>{registerForm.formState.errors.password.message}</p>}
              </div>
              <div>
                <label htmlFor="register-confirmPassword" className={labelClass}>确认密码</label>
                <input {...registerForm.register('confirmPassword')} type="password" id="register-confirmPassword" className={inputClass} placeholder="再次输入密码" />
                {registerForm.formState.errors.confirmPassword && <p className={errorClass}>{registerForm.formState.errors.confirmPassword.message}</p>}
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 rounded-lg font-medium text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-bd-primary-fg"
                style={{ background: 'var(--bd-primary)' }}
                onMouseEnter={(e) => !loading && (e.currentTarget.style.background = 'var(--bd-primary-alt)')}
                onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--bd-primary)')}
              >
                {loading ? '注册中...' : '注册'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
