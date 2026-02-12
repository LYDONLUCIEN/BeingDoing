'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { X } from 'lucide-react';
import { authApi } from '@/lib/api/auth';
import { useAuthStore } from '@/stores/authStore';
import { useRouter } from 'next/navigation';

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

  const loginForm = useForm<LoginFormData>({
    resolver: zodResolver(loginSchema),
  });

  const registerForm = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
  });

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
        onClose();
        if (redirectTo !== '/explore') {
          router.push(redirectTo);
        }
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
        onClose();
        router.push('/profile/setup');
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6 animate-in fade-in zoom-in duration-200">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-gray-400 hover:text-gray-600"
        >
          <X size={20} />
        </button>

        {/* Title */}
        <div className="text-center mb-6">
          <h2 className="text-2xl font-bold text-primary-700">
            找到想做的事
          </h2>
          <p className="text-gray-600 mt-1">
            {mode === 'login' ? '登录' : '注册'}
          </p>
        </div>

        {/* Error message */}
        {error && (
          <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded text-sm">
            {error}
          </div>
        )}

        {/* Login Form */}
        {mode === 'login' ? (
          <form onSubmit={loginForm.handleSubmit(onLoginSubmit)} className="space-y-4">
            <div>
              <label htmlFor="login-email" className="block text-sm font-medium text-gray-700 mb-1">
                邮箱
              </label>
              <input
                {...loginForm.register('email')}
                type="email"
                id="login-email"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500 text-sm"
                placeholder="your@email.com"
              />
              {loginForm.formState.errors.email && (
                <p className="mt-1 text-sm text-red-600">{loginForm.formState.errors.email.message}</p>
              )}
            </div>

            <div>
              <label htmlFor="login-phone" className="block text-sm font-medium text-gray-700 mb-1">
                手机号（可选）
              </label>
              <input
                {...loginForm.register('phone')}
                type="tel"
                id="login-phone"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500 text-sm"
                placeholder="13800138000"
              />
            </div>

            <div>
              <label htmlFor="login-password" className="block text-sm font-medium text-gray-700 mb-1">
                密码
              </label>
              <input
                {...loginForm.register('password')}
                type="password"
                id="login-password"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500 text-sm"
                placeholder="••••••"
              />
              {loginForm.formState.errors.password && (
                <p className="mt-1 text-sm text-red-600">{loginForm.formState.errors.password.message}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2 px-4 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
            >
              {loading ? '登录中...' : '登录'}
            </button>

            <div className="text-center text-sm">
              <span className="text-gray-600">还没有账号？</span>
              <button
                type="button"
                onClick={switchMode}
                className="ml-1 text-primary-600 hover:text-primary-700"
              >
                立即注册
              </button>
            </div>
          </form>
        ) : (
          /* Register Form */
          <form onSubmit={registerForm.handleSubmit(onRegisterSubmit)} className="space-y-4">
            <div>
              <label htmlFor="register-email" className="block text-sm font-medium text-gray-700 mb-1">
                邮箱
              </label>
              <input
                {...registerForm.register('email')}
                type="email"
                id="register-email"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500 text-sm"
                placeholder="your@email.com"
              />
              {registerForm.formState.errors.email && (
                <p className="mt-1 text-sm text-red-600">{registerForm.formState.errors.email.message}</p>
              )}
            </div>

            <div>
              <label htmlFor="register-phone" className="block text-sm font-medium text-gray-700 mb-1">
                手机号（可选）
              </label>
              <input
                {...registerForm.register('phone')}
                type="tel"
                id="register-phone"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500 text-sm"
                placeholder="13800138000"
              />
            </div>

            <div>
              <label htmlFor="register-username" className="block text-sm font-medium text-gray-700 mb-1">
                用户名（可选）
              </label>
              <input
                {...registerForm.register('username')}
                type="text"
                id="register-username"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500 text-sm"
                placeholder="your_username"
              />
            </div>

            <div>
              <label htmlFor="register-password" className="block text-sm font-medium text-gray-700 mb-1">
                密码
              </label>
              <input
                {...registerForm.register('password')}
                type="password"
                id="register-password"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500 text-sm"
                placeholder="••••••"
              />
              {registerForm.formState.errors.password && (
                <p className="mt-1 text-sm text-red-600">{registerForm.formState.errors.password.message}</p>
              )}
            </div>

            <div>
              <label htmlFor="register-confirmPassword" className="block text-sm font-medium text-gray-700 mb-1">
                确认密码
              </label>
              <input
                {...registerForm.register('confirmPassword')}
                type="password"
                id="register-confirmPassword"
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500 text-sm"
                placeholder="••••••"
              />
              {registerForm.formState.errors.confirmPassword && (
                <p className="mt-1 text-sm text-red-600">{registerForm.formState.errors.confirmPassword.message}</p>
              )}
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full py-2 px-4 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed text-sm"
            >
              {loading ? '注册中...' : '注册'}
            </button>

            <div className="text-center text-sm">
              <span className="text-gray-600">已有账号？</span>
              <button
                type="button"
                onClick={switchMode}
                className="ml-1 text-primary-600 hover:text-primary-700"
              >
                立即登录
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
