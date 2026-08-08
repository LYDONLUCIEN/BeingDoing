'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AxiosError } from 'axios';
import { authApi } from '@/lib/api/auth';
import { getApiErrorMessage } from '@/lib/api/client';
import { useAuthStore } from '@/stores/authStore';
import { useAuthModalStore } from '@/stores/authModalStore';

/** 邮箱打码：a***@b.com */
function maskEmail(email?: string): string {
  if (!email) return '你的注册邮箱';
  const [local, domain] = email.split('@');
  if (!domain) return email;
  const head = local ? local[0] : '*';
  return `${head}***@${domain}`;
}

function isUnauthorized(err: unknown): boolean {
  return (err as AxiosError)?.response?.status === 401;
}

export default function AccountRecoveryPage() {
  const router = useRouter();
  const { user, token, isAuthenticated, _hasHydrated, setUser, setToken, setRecoveryMode, logout } =
    useAuthStore();
  const openAuthModal = useAuthModalStore((s) => s.openAuthModal);

  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [sending, setSending] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const cooldownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const autoSentRef = useRef(false);

  // 无受限 token（未登录/登录态已失效）→ 回首页（与其他页面的未登录行为一致）
  useEffect(() => {
    if (_hasHydrated && !token) {
      router.replace('/');
    }
  }, [_hasHydrated, token, router]);

  // 发送验证码冷却倒计时（沿用设置页邮箱验证的 cooldown 实现）
  useEffect(() => {
    if (cooldown <= 0) {
      if (cooldownRef.current) clearInterval(cooldownRef.current);
      return;
    }
    cooldownRef.current = setInterval(() => {
      setCooldown((prev) => {
        if (prev <= 1) {
          if (cooldownRef.current) clearInterval(cooldownRef.current);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => {
      if (cooldownRef.current) clearInterval(cooldownRef.current);
    };
  }, [cooldown]);

  const handleUnauthorized = () => {
    // 受限 token 过期/失效：清登录态回首页并弹出登录框，引导重新登录
    logout();
    router.replace('/');
    openAuthModal('/');
  };

  const handleSendCode = async () => {
    if (sending || cooldown > 0) return;
    setError('');
    setSuccessMsg('');
    setSending(true);
    try {
      await authApi.sendAccountRecoveryCode();
      setSuccessMsg(`验证码已发送至 ${maskEmail(user?.email)}，请查收`);
      setCooldown(60);
    } catch (err: unknown) {
      if (isUnauthorized(err)) {
        handleUnauthorized();
        return;
      }
      setError(getApiErrorMessage(err, '发送失败，请稍后重试'));
    } finally {
      setSending(false);
    }
  };

  // 进入恢复页自动发送一次验证码（登录跳转而来时用户无需再手动点击）
  useEffect(() => {
    if (!_hasHydrated || !token || autoSentRef.current) return;
    autoSentRef.current = true;
    void handleSendCode();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [_hasHydrated, token]);

  const handleConfirmRecovery = async () => {
    if (confirming || code.length !== 6) return;
    setError('');
    setSuccessMsg('');
    setConfirming(true);
    try {
      const response = await authApi.confirmAccountRecovery(code);
      const resData = response?.data;
      if (response?.code === 200 && resData?.token) {
        // 恢复成功：退出恢复会话，写入正式 token，再拉取完整用户信息
        setRecoveryMode(false);
        setToken(resData.token);
        try {
          const me = await authApi.getCurrentUser();
          const userData = me.data || resData;
          setUser({
            user_id: userData.user_id,
            email: userData.email,
            phone: userData.phone,
            username: userData.username,
            is_super_admin: userData.is_super_admin,
            email_verified: userData.email_verified,
          });
        } catch {
          setUser({
            user_id: resData.user_id,
            email: resData.email,
            phone: resData.phone,
            username: resData.username,
          });
        }
        router.push('/dashboard');
      } else {
        setError('恢复失败，请重试');
      }
    } catch (err: unknown) {
      if (isUnauthorized(err)) {
        handleUnauthorized();
        return;
      }
      setError(getApiErrorMessage(err, '验证码错误或已过期'));
    } finally {
      setConfirming(false);
    }
  };

  const handleLogout = () => {
    logout();
    router.push('/');
  };

  // 等待 localStorage 恢复完成，避免闪屏/误跳转
  if (!_hasHydrated || !isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100">
      <div className="w-full max-w-md p-8 bg-white rounded-lg shadow-lg">
        <h1 className="text-2xl font-bold text-center mb-4 text-primary-700">
          恢复你的账户
        </h1>
        <p className="text-sm text-center text-gray-600 mb-8">
          你的账户已注销，数据保留期内可恢复。验证码将发送到你的邮箱{' '}
          <span className="font-medium text-gray-800">{maskEmail(user?.email)}</span>
          。
        </p>

        {error && (
          <div className="mb-4 p-3 bg-red-100 border border-red-400 text-red-700 rounded">
            {error}
          </div>
        )}
        {successMsg && (
          <div className="mb-4 p-3 bg-green-100 border border-green-400 text-green-700 rounded">
            {successMsg}
          </div>
        )}

        <div className="space-y-4">
          <div>
            <label htmlFor="recovery-code" className="block text-sm font-medium text-gray-700 mb-1">
              邮箱验证码
            </label>
            <div className="flex gap-2">
              <input
                id="recovery-code"
                type="text"
                inputMode="numeric"
                maxLength={6}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500 tracking-widest"
                placeholder="6 位验证码"
              />
              <button
                type="button"
                onClick={() => void handleSendCode()}
                disabled={sending || cooldown > 0}
                className="shrink-0 px-4 py-2 border border-primary-600 text-primary-600 rounded-md hover:bg-primary-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {cooldown > 0 ? `${cooldown}s 后重发` : sending ? '发送中...' : '发送验证码'}
              </button>
            </div>
          </div>

          <button
            type="button"
            onClick={() => void handleConfirmRecovery()}
            disabled={confirming || code.length !== 6}
            className="w-full py-2 px-4 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {confirming ? '恢复中...' : '恢复账户'}
          </button>

          <div className="text-center">
            <button
              type="button"
              onClick={handleLogout}
              className="text-sm text-gray-500 hover:text-gray-700 underline"
            >
              退出登录
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
