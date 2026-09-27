'use client';

import { Suspense, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { authApi } from '@/lib/api/auth';
import { apiClient } from '@/lib/api/client';
import { useAuthStore } from '@/stores/authStore';
import LegalDocLink from '@/components/legal/LegalDocLink';
import { useLegalConsentPersistence } from '@/hooks/useLegalConsent';
import Link from 'next/link';

// 2026-09-27 起：注册强制邮箱验证——邮箱改为必填，手机号注册通道关闭
// （手机验证码为假实现，且纯手机注册会绕过邮箱验证门控）。
const registerSchema = z.object({
  email: z.string().min(1, '请输入邮箱').email('请输入有效邮箱'),
  username: z.string().optional(),
  password: z.string().min(6, '密码至少6位'),
  confirmPassword: z.string(),
  agreeTerms: z.boolean(),
}).refine((data) => data.password === data.confirmPassword, {
  message: '两次输入的密码不一致',
  path: ['confirmPassword'],
}).refine((data) => data.agreeTerms === true, {
  message: '请阅读并同意协议后继续',
  path: ['agreeTerms'],
});

type RegisterFormData = z.infer<typeof registerSchema>;

interface RegisteredState {
  email: string;
  emailSent: boolean;
}

function RegisterForm() {
  const { setUser, setToken } = useAuthStore();
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [registered, setRegistered] = useState<RegisteredState | null>(null);
  const [resendState, setResendState] = useState<{ loading: boolean; message: string; isError: boolean }>({
    loading: false,
    message: '',
    isError: false,
  });

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<RegisterFormData>({
    resolver: zodResolver(registerSchema),
    defaultValues: { agreeTerms: false } as Partial<RegisterFormData>,
  });

  // 勾选状态记忆：上次勾过则自动预勾选，变更时实时记忆
  useLegalConsentPersistence(watch, setValue);

  const onSubmit = async (data: RegisterFormData) => {
    setError('');
    setLoading(true);

    try {
      const response = await authApi.register({
        email: data.email,
        username: data.username || undefined,
        password: data.password,
      });

      if (response.code === 200 && response.data) {
        setUser({
          user_id: response.data.user_id,
          email: response.data.email,
          phone: response.data.phone,
          username: response.data.username,
          avatar_url: response.data.avatar_url,
        });
        setToken(response.data.token);
        // 不再直接跳走：先引导完成邮箱验证（验证通过才会发放试用激活码）
        setRegistered({
          email: data.email,
          emailSent: response.data.verification_email_sent !== false,
        });
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || '注册失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  const onResend = async () => {
    if (!registered || resendState.loading) return;
    setResendState({ loading: true, message: '', isError: false });
    try {
      await apiClient.post('/auth/email-verify/request', { email: registered.email });
      setResendState({ loading: false, message: '验证邮件已重新发送，请查收', isError: false });
    } catch (err: any) {
      setResendState({
        loading: false,
        message: err.response?.data?.detail || '发送失败，请稍后重试',
        isError: true,
      });
    }
  };

  // 注册成功：展示验证引导卡（未验证用户可登录浏览，探索功能验证后解锁）
  if (registered) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100">
        <div className="w-full max-w-md p-8 bg-white rounded-lg shadow-lg">
          <h1 className="text-2xl font-bold text-center mb-6 text-primary-700">
            {registered.emailSent ? '验证邮件已发送' : '注册成功'}
          </h1>

          <div className="space-y-4 text-sm text-gray-700">
            {registered.emailSent ? (
              <p>
                我们已向 <span className="font-medium text-gray-900">{registered.email}</span>{' '}
                发送了验证邮件，请点击邮件中的链接完成验证（24 小时内有效）。
              </p>
            ) : (
              <p className="text-amber-700">
                验证邮件发送失败，请点击下方按钮重试；若多次失败请联系管理员协助。
              </p>
            )}
            <p className="text-gray-500">
              收不到邮件？请检查垃圾邮件/订阅邮件文件夹。
              验证通过后即可开始探索（试用激活码将在验证通过后自动发放）。
            </p>
          </div>

          {resendState.message && (
            <div
              className={`mt-4 p-3 rounded text-sm ${
                resendState.isError
                  ? 'bg-red-100 border border-red-400 text-red-700'
                  : 'bg-green-50 border border-green-300 text-green-700'
              }`}
            >
              {resendState.message}
            </div>
          )}

          <button
            onClick={onResend}
            disabled={resendState.loading}
            className="mt-6 w-full py-2 px-4 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {resendState.loading ? '发送中...' : '重发验证邮件'}
          </button>

          <div className="mt-4 text-center">
            <Link href="/" className="text-sm text-primary-600 hover:text-primary-700">
              先去随便逛逛（探索功能验证后解锁）
            </Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100">
      <div className="w-full max-w-md p-8 bg-white rounded-lg shadow-lg">
        <h1 className="text-3xl font-bold text-center mb-6 text-primary-700">
          找到想做的事
        </h1>
        <h2 className="text-xl font-semibold text-center mb-8 text-gray-700">
          注册
        </h2>

        {error && (
          <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
              邮箱
            </label>
            <input
              {...register('email')}
              type="email"
              id="email"
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              placeholder="your@email.com"
            />
            {errors.email && (
              <p className="mt-1 text-sm text-red-600">{errors.email.message}</p>
            )}
            <p className="mt-1 text-xs text-gray-500">
              注册后需点击验证邮件中的链接完成邮箱验证
            </p>
          </div>

          <div>
            <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-1">
              用户名（可选）
            </label>
            <input
              {...register('username')}
              type="text"
              id="username"
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              placeholder="your_username"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">
              密码
            </label>
            <input
              {...register('password')}
              type="password"
              id="password"
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              placeholder="••••••"
            />
            {errors.password && (
              <p className="mt-1 text-sm text-red-600">{errors.password.message}</p>
            )}
          </div>

          <div>
            <label htmlFor="confirmPassword" className="block text-sm font-medium text-gray-700 mb-1">
              确认密码
            </label>
            <input
              {...register('confirmPassword')}
              type="password"
              id="confirmPassword"
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
              placeholder="••••••"
            />
            {errors.confirmPassword && (
              <p className="mt-1 text-sm text-red-600">{errors.confirmPassword.message}</p>
            )}
          </div>

          {/* 隐私政策 & 服务条款勾选 */}
          <div>
            <label className="flex items-start gap-2 text-sm text-gray-700 cursor-pointer">
              <input
                type="checkbox"
                {...register('agreeTerms')}
                className="mt-0.5 h-4 w-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500"
              />
              <span>
                我已阅读并同意
                <LegalDocLink
                  type="privacy"
                  className="text-primary-600 hover:text-primary-700 hover:underline mx-1 align-baseline"
                />
                和
                <LegalDocLink
                  type="terms"
                  className="text-primary-600 hover:text-primary-700 hover:underline ml-1 align-baseline"
                />
              </span>
            </label>
            {errors.agreeTerms && (
              <p className="mt-1 text-sm text-red-600">{errors.agreeTerms.message}</p>
            )}
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2 px-4 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? '注册中...' : '注册'}
          </button>
        </form>

        <div className="mt-6 text-center">
          <p className="text-sm text-gray-600">
            已有账号？{' '}
            <Link href="/auth/login" className="text-primary-600 hover:text-primary-700">
              立即登录
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}

export default function RegisterPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
      </div>
    }>
      <RegisterForm />
    </Suspense>
  );
}
