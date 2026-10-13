'use client';

import { Suspense, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { authApi } from '@/lib/api/auth';
import { useAuthStore } from '@/stores/authStore';
import { useRegisterVerification } from '@/hooks/useRegisterVerification';
import LegalDocLink from '@/components/legal/LegalDocLink';
import { useLegalConsentPersistence } from '@/hooks/useLegalConsent';
import Link from 'next/link';

// 2026-10-13 起（ADR-0026）：邮箱验证前置——先验证邮箱拿到 ticket，再设密码完成注册；
// 落库即已验证，登录只需邮箱+密码。手机号不收集（等短信通道上线）。
const passwordSchema = z.object({
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

type PasswordFormData = z.infer<typeof passwordSchema>;

const inputClass =
  'w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500';
const primaryBtnClass =
  'w-full py-2 px-4 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed';

function RegisterForm() {
  const router = useRouter();
  const { setUser, setToken } = useAuthStore();
  const verify = useRegisterVerification();
  const [emailInput, setEmailInput] = useState('');
  const [codeInput, setCodeInput] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<PasswordFormData>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { agreeTerms: false } as Partial<PasswordFormData>,
  });

  // 勾选状态记忆：上次勾过则自动预勾选，变更时实时记忆
  useLegalConsentPersistence(watch, setValue);

  const onSendCode = async () => {
    await verify.sendCode(emailInput);
  };

  const onVerifyCode = async () => {
    if (codeInput.trim().length !== 6) {
      verify.setError('请输入 6 位验证码');
      return;
    }
    await verify.verifyCode(codeInput);
  };

  const onRegisterSubmit = async (data: PasswordFormData) => {
    verify.setError('');
    setSubmitting(true);
    try {
      const response = await authApi.register({
        email: verify.email,
        username: data.username || undefined,
        password: data.password,
        ticket: verify.ticket,
      });

      if (response.code === 200 && response.data) {
        setUser({
          user_id: response.data.user_id,
          email: response.data.email,
          phone: response.data.phone,
          username: response.data.username,
          avatar_url: response.data.avatar_url,
          email_verified: true,
        });
        setToken(response.data.token);
        // 邮箱已前置验证：无需引导验证，直接进入探索（试用码已随注册发放）
        router.push('/explore');
      }
    } catch (err: any) {
      verify.setError(err.response?.data?.detail || '注册失败，请重试');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100">
      <div className="w-full max-w-md p-8 bg-white rounded-lg shadow-lg">
        <h1 className="text-3xl font-bold text-center mb-6 text-primary-700">
          找到想做的事
        </h1>
        <h2 className="text-xl font-semibold text-center mb-8 text-gray-700">
          注册
        </h2>

        {verify.error && (
          <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
            {verify.error}
          </div>
        )}
        {verify.notice && (
          <div className="mb-4 p-3 bg-green-50 border border-green-300 text-green-700 rounded text-sm">
            {verify.notice}
          </div>
        )}

        {/* 第一步：输入邮箱，发送验证码 */}
        {verify.step === 'email' && (
          <div className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-1">
                邮箱
              </label>
              <input
                type="email"
                id="email"
                autoComplete="email"
                value={emailInput}
                onChange={(e) => setEmailInput(e.target.value)}
                className={inputClass}
                placeholder="your@email.com"
              />
              <p className="mt-1 text-xs text-gray-500">
                注册前需要先验证邮箱，验证通过后即可完成注册
              </p>
            </div>
            <button
              type="button"
              onClick={() => void onSendCode()}
              disabled={verify.sending || !emailInput.trim()}
              className={primaryBtnClass}
            >
              {verify.sending ? '发送中...' : '发送验证码'}
            </button>
            {verify.alreadyRegistered && (
              <p className="text-sm text-center text-gray-600">
                该邮箱已有账号，{' '}
                <Link href="/auth/login" className="text-primary-600 hover:text-primary-700">
                  直接登录
                </Link>
              </p>
            )}
          </div>
        )}

        {/* 第二步：输入验证码（或在任意设备点邮件链接，本页自动推进） */}
        {verify.step === 'code' && (
          <div className="space-y-4">
            <p className="text-sm text-gray-600">
              验证码已发送至 <span className="font-medium text-gray-900">{verify.email}</span>
              ，有效期 10 分钟。点击邮件中的链接也可完成验证，本页会自动继续。
            </p>
            <div>
              <label htmlFor="code" className="block text-sm font-medium text-gray-700 mb-1">
                邮箱验证码
              </label>
              <input
                type="text"
                id="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={codeInput}
                onChange={(e) => setCodeInput(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className={`${inputClass} tracking-widest`}
                placeholder="6 位验证码"
              />
            </div>
            <button
              type="button"
              onClick={() => void onVerifyCode()}
              disabled={verify.verifying || codeInput.length !== 6}
              className={primaryBtnClass}
            >
              {verify.verifying ? '验证中...' : '验证并继续'}
            </button>
            <div className="flex items-center justify-between text-sm">
              <button
                type="button"
                onClick={verify.backToEmail}
                className="text-gray-500 hover:text-gray-700"
              >
                更换邮箱
              </button>
              <button
                type="button"
                onClick={() => void verify.sendCode(verify.email)}
                disabled={verify.sending || verify.cooldown > 0}
                className="text-primary-600 hover:text-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {verify.cooldown > 0 ? `${verify.cooldown}s 后可重发` : verify.sending ? '发送中...' : '重新发送'}
              </button>
            </div>
          </div>
        )}

        {/* 第三步：设置密码，完成注册 */}
        {verify.step === 'password' && (
          <form onSubmit={handleSubmit(onRegisterSubmit)} className="space-y-4">
            <p className="text-sm text-gray-600">
              邮箱 <span className="font-medium text-gray-900">{verify.email}</span> 已验证 ✓
            </p>

            <div>
              <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-1">
                用户名（可选）
              </label>
              <input
                {...register('username')}
                type="text"
                id="username"
                className={inputClass}
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
                autoComplete="new-password"
                className={inputClass}
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
                autoComplete="new-password"
                className={inputClass}
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

            <button type="submit" disabled={submitting} className={primaryBtnClass}>
              {submitting ? '注册中...' : '完成注册'}
            </button>
          </form>
        )}

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
