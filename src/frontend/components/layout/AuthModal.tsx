'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { X } from 'lucide-react';
import { authApi } from '@/lib/api/auth';
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

export default function AuthModal({ isOpen, onClose, redirectTo = '/explore' }: AuthModalProps) {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const { setUser, setToken } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();

  const loginForm = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });

  const registerForm = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
  });

  const handleSuccess = (targetPath: string) => {
    onClose();
    // 始终跳转到目标页面（如果不在该页面）
    if (pathname !== targetPath) {
      router.push(targetPath);
    } else {
      // 已经在目标页面，刷新当前路由触发重新渲染
      router.refresh();
    }
  };

  const onLoginSubmit = async (data: LoginFormData) => {
    setError('');
    setLoading(true);

    try {
      const response = await authApi.login({
        email: data.email || undefined,
        phone: data.phone || undefined,
        password: data.password,
      });

      if (response.code === 200 && response.data) {
        try {
          const me = await authApi.getCurrentUser();
          const userData = me.data || response.data;
          setUser({
            user_id: userData.user_id,
            email: userData.email,
            phone: userData.phone,
            username: userData.username,
            is_super_admin: userData.is_super_admin,
          });
        } catch {
          setUser({
            user_id: response.data.user_id,
            email: response.data.email,
            phone: response.data.phone,
            username: response.data.username,
          });
        }
        setToken(response.data.token);
        handleSuccess(redirectTo);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || '登录失败，请检查您的凭据');
    } finally {
      setLoading(false);
    }
  };

  const onRegisterSubmit = async (data: RegisterFormData) => {
    setError('');
    setLoading(true);

    try {
      const response = await authApi.register({
        email: data.email || undefined,
        phone: data.phone || undefined,
        username: data.username || undefined,
        password: data.password,
      });

      if (response.code === 200 && response.data) {
        setUser({
          user_id: response.data.user_id,
          email: response.data.email,
          phone: response.data.phone,
          username: response.data.username,
        });
        setToken(response.data.token);
        handleSuccess('/profile/setup');
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || '注册失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  const switchMode = () => {
    setError('');
    loginForm.reset();
    registerForm.reset();
    setMode(mode === 'login' ? 'register' : 'login');
  };

  if (!isOpen) return null;

  const inputClass =
    'w-full px-3 py-2.5 bg-white/5 border border-white/10 rounded-lg text-white placeholder-white/30 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-colors';
  const labelClass = 'block text-sm font-medium text-white/70 mb-1.5';
  const errorClass = 'mt-1 text-xs text-red-400';

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      {/* Backdrop with blur */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-md"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-md max-h-[90vh] bg-slate-800/95 border border-white/10 rounded-2xl shadow-2xl shadow-black/50 overflow-y-auto animate-in fade-in zoom-in-95 duration-200">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 z-10 p-1 rounded-lg text-white/40 hover:text-white hover:bg-white/10 transition-colors"
        >
          <X size={18} />
        </button>

        <div className="px-6 pt-8 pb-6">
          {/* Title */}
          <div className="text-center mb-6">
            <h2 className="text-2xl font-bold text-white">
              找到想做的事
            </h2>
            <p className="text-white/50 mt-1 text-sm">
              {mode === 'login' ? '欢迎回来' : '开始你的探索之旅'}
            </p>
          </div>

          {/* Tab switcher */}
          <div className="flex bg-white/5 rounded-lg p-1 mb-6">
            <button
              type="button"
              onClick={() => { if (mode !== 'login') switchMode(); }}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
                mode === 'login'
                  ? 'bg-primary-500 text-white shadow-sm'
                  : 'text-white/50 hover:text-white/70'
              }`}
            >
              登录
            </button>
            <button
              type="button"
              onClick={() => { if (mode !== 'register') switchMode(); }}
              className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
                mode === 'register'
                  ? 'bg-primary-500 text-white shadow-sm'
                  : 'text-white/50 hover:text-white/70'
              }`}
            >
              注册
            </button>
          </div>

          {/* Error message */}
          {error && (
            <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 text-red-300 rounded-lg text-sm">
              {error}
            </div>
          )}

          {/* Login Form */}
          {mode === 'login' ? (
            <form onSubmit={loginForm.handleSubmit(onLoginSubmit)} className="space-y-4">
              <div>
                <label htmlFor="login-email" className={labelClass}>邮箱</label>
                <input
                  {...loginForm.register('email')}
                  type="email"
                  id="login-email"
                  className={inputClass}
                  placeholder="your@email.com"
                />
                {loginForm.formState.errors.email && (
                  <p className={errorClass}>{loginForm.formState.errors.email.message}</p>
                )}
              </div>

              <div>
                <label htmlFor="login-phone" className={labelClass}>手机号（可选）</label>
                <input
                  {...loginForm.register('phone')}
                  type="tel"
                  id="login-phone"
                  className={inputClass}
                  placeholder="13800138000"
                />
              </div>

              <div>
                <label htmlFor="login-password" className={labelClass}>密码</label>
                <input
                  {...loginForm.register('password')}
                  type="password"
                  id="login-password"
                  className={inputClass}
                  placeholder="至少6位"
                />
                {loginForm.formState.errors.password && (
                  <p className={errorClass}>{loginForm.formState.errors.password.message}</p>
                )}
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 bg-primary-500 text-white rounded-lg font-medium hover:bg-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:ring-offset-2 focus:ring-offset-slate-800 disabled:opacity-50 disabled:cursor-not-allowed text-sm transition-colors"
              >
                {loading ? '登录中...' : '登录'}
              </button>
            </form>
          ) : (
            /* Register Form */
            <form onSubmit={registerForm.handleSubmit(onRegisterSubmit)} className="space-y-3.5">
              <div>
                <label htmlFor="register-email" className={labelClass}>邮箱</label>
                <input
                  {...registerForm.register('email')}
                  type="email"
                  id="register-email"
                  className={inputClass}
                  placeholder="your@email.com"
                />
                {registerForm.formState.errors.email && (
                  <p className={errorClass}>{registerForm.formState.errors.email.message}</p>
                )}
              </div>

              <div>
                <label htmlFor="register-phone" className={labelClass}>手机号（可选）</label>
                <input
                  {...registerForm.register('phone')}
                  type="tel"
                  id="register-phone"
                  className={inputClass}
                  placeholder="13800138000"
                />
              </div>

              <div>
                <label htmlFor="register-username" className={labelClass}>用户名（可选）</label>
                <input
                  {...registerForm.register('username')}
                  type="text"
                  id="register-username"
                  className={inputClass}
                  placeholder="你的昵称"
                />
              </div>

              <div>
                <label htmlFor="register-password" className={labelClass}>密码</label>
                <input
                  {...registerForm.register('password')}
                  type="password"
                  id="register-password"
                  className={inputClass}
                  placeholder="至少6位"
                />
                {registerForm.formState.errors.password && (
                  <p className={errorClass}>{registerForm.formState.errors.password.message}</p>
                )}
              </div>

              <div>
                <label htmlFor="register-confirmPassword" className={labelClass}>确认密码</label>
                <input
                  {...registerForm.register('confirmPassword')}
                  type="password"
                  id="register-confirmPassword"
                  className={inputClass}
                  placeholder="再次输入密码"
                />
                {registerForm.formState.errors.confirmPassword && (
                  <p className={errorClass}>{registerForm.formState.errors.confirmPassword.message}</p>
                )}
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 bg-primary-500 text-white rounded-lg font-medium hover:bg-primary-400 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:ring-offset-2 focus:ring-offset-slate-800 disabled:opacity-50 disabled:cursor-not-allowed text-sm transition-colors"
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
