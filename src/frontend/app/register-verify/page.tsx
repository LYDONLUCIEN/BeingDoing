'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { apiClient } from '@/lib/api/client';

type VerifyState = 'verifying' | 'success' | 'error';

/**
 * 注册前置验证的链接落地页（2026-10-13 起，ADR-0026）：
 * 邮件链接在任何设备点开都只完成服务端验证，不携带 ticket——
 * 原注册页通过轮询领到 ticket 后继续设置密码（跨设备不断进度）。
 */
function RegisterVerifyContent() {
  const searchParams = useSearchParams();
  const [state, setState] = useState<VerifyState>('verifying');
  const [message, setMessage] = useState('');

  useEffect(() => {
    const token = searchParams.get('token');
    if (!token) {
      setState('error');
      setMessage('验证链接缺少参数');
      return;
    }
    (async () => {
      try {
        await apiClient.get('/auth/register/verify-link', { params: { token } });
        setState('success');
      } catch (err: any) {
        setState('error');
        setMessage(err.response?.data?.detail || '验证链接无效或已过期');
      }
    })();
  }, [searchParams]);

  return (
    <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100">
      <div className="w-full max-w-md p-8 bg-white rounded-lg shadow-lg text-center">
        {state === 'verifying' && (
          <>
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600 mx-auto mb-4" />
            <p className="text-gray-600">正在验证邮箱...</p>
          </>
        )}
        {state === 'success' && (
          <>
            <div className="text-5xl mb-4">✅</div>
            <h1 className="text-2xl font-bold text-primary-700 mb-4">邮箱验证成功</h1>
            <p className="text-sm text-gray-600">
              请回到你刚才的注册页面继续设置密码（页面会自动继续）。
              本标签页可以关闭了。
            </p>
          </>
        )}
        {state === 'error' && (
          <>
            <div className="text-5xl mb-4">⚠️</div>
            <h1 className="text-2xl font-bold text-red-600 mb-4">验证失败</h1>
            <p className="text-sm text-gray-600">
              {message}，请回到注册页重新发送验证码。
            </p>
          </>
        )}
      </div>
    </div>
  );
}

export default function RegisterVerifyPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center bg-gradient-to-br from-primary-50 to-primary-100">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-primary-600" />
      </div>
    }>
      <RegisterVerifyContent />
    </Suspense>
  );
}
