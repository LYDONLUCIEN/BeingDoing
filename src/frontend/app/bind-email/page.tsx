'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { AxiosError } from 'axios';
import { authApi } from '@/lib/api/auth';
import { getApiErrorMessage } from '@/lib/api/client';
import { useAuthStore } from '@/stores/authStore';
import { useAuthModalStore } from '@/stores/authModalStore';

function isUnauthorized(err: unknown): boolean {
  return (err as AxiosError)?.response?.status === 401;
}

/**
 * 强制绑定邮箱页（2026-10-13 起，ADR-0026）：
 * 纯手机老账号登录后持有 email_binding_required 受限 token，硬门禁——
 * 只能在本页完成邮箱绑定（输入邮箱 → 收验证码 → 确认），绑定后换发正式 token。
 */
export default function BindEmailPage() {
  const router = useRouter();
  const { token, isAuthenticated, _hasHydrated, setUser, setToken, setBindingMode, logout } =
    useAuthStore();
  const openAuthModal = useAuthModalStore((s) => s.openAuthModal);

  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [codeSent, setCodeSent] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');
  const [sending, setSending] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [cooldown, setCooldown] = useState(0);
  const cooldownRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 无受限 token（未登录/登录态已失效）→ 回首页（与其他页面的未登录行为一致）
  useEffect(() => {
    if (_hasHydrated && !token) {
      router.replace('/');
    }
  }, [_hasHydrated, token, router]);

  // 发送验证码冷却倒计时
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
    const normalized = email.trim().toLowerCase();
    if (!normalized) {
      setError('请输入邮箱');
      return;
    }
    if (sending || cooldown > 0) return;
    setError('');
    setSuccessMsg('');
    setSending(true);
    try {
      await authApi.requestBindEmailCode({ email: normalized });
      setCodeSent(true);
      setSuccessMsg(`验证码已发送至 ${normalized}，请查收（10 分钟内有效）`);
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

  const handleConfirm = async () => {
    const normalized = email.trim().toLowerCase();
    if (confirming || !normalized || code.length !== 6) return;
    setError('');
    setSuccessMsg('');
    setConfirming(true);
    try {
      const response = await authApi.confirmBindEmail({ email: normalized, code });
      const resData = response?.data;
      if (response?.code === 200 && resData?.token) {
        // 绑定成功：退出绑定会话，写入正式 token，再拉取完整用户信息
        setBindingMode(false);
        setToken(resData.token);
        try {
          const me = await authApi.getCurrentUser();
          const userData = me.data || resData;
          setUser({
            user_id: userData.user_id,
            email: userData.email,
            phone: userData.phone,
            username: userData.username,
            avatar_url: userData.avatar_url,
            is_super_admin: userData.is_super_admin,
            email_verified: userData.email_verified,
          });
        } catch {
          setUser({
            user_id: resData.user_id,
            email: resData.email,
            phone: resData.phone,
            username: resData.username,
            avatar_url: resData.avatar_url,
            email_verified: true,
          });
        }
        router.push('/explore');
      } else {
        setError('绑定失败，请重试');
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
          绑定你的邮箱
        </h1>
        <p className="text-sm text-center text-gray-600 mb-8">
          为了账号安全，手机号账号需要先绑定并验证邮箱，之后使用邮箱 + 密码即可登录。
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
            <label htmlFor="bind-email" className="block text-sm font-medium text-gray-700 mb-1">
              邮箱
            </label>
            <div className="flex gap-2">
              <input
                id="bind-email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500"
                placeholder="your@email.com"
              />
              <button
                type="button"
                onClick={() => void handleSendCode()}
                disabled={sending || cooldown > 0 || !email.trim()}
                className="shrink-0 px-4 py-2 border border-primary-600 text-primary-600 rounded-md hover:bg-primary-50 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {cooldown > 0 ? `${cooldown}s 后重发` : sending ? '发送中...' : codeSent ? '重新发送' : '发送验证码'}
              </button>
            </div>
          </div>

          <div>
            <label htmlFor="bind-code" className="block text-sm font-medium text-gray-700 mb-1">
              邮箱验证码
            </label>
            <input
              id="bind-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
              className="w-full px-4 py-2 border border-gray-300 rounded-md focus:ring-primary-500 focus:border-primary-500 tracking-widest"
              placeholder="6 位验证码"
            />
          </div>

          <button
            type="button"
            onClick={() => void handleConfirm()}
            disabled={confirming || !codeSent || code.length !== 6}
            className="w-full py-2 px-4 bg-primary-600 text-white rounded-md hover:bg-primary-700 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {confirming ? '绑定中...' : '完成绑定'}
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
