'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';

export default function AdminPage() {
  const router = useRouter();
  const { user, isAuthenticated } = useAuthStore();

  useEffect(() => {
    if (!isAuthenticated) {
      router.replace('/auth/login?redirect=/admin');
    }
  }, [isAuthenticated, router]);

  if (!isAuthenticated) {
    return null;
  }

  if (!user?.is_super_admin) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900 text-white">
        <div className="rounded-xl border border-white/10 bg-slate-800/70 px-6 py-4 text-center space-y-2">
          <p className="text-base font-semibold">无权限访问管理视图</p>
          <p className="text-sm text-white/70">
            只有在 <code className="px-1 py-0.5 bg-slate-900/70 rounded border border-white/10">.env</code>{' '}
            中配置为超级管理员的账号才能访问此页面。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-900 text-white flex flex-col">
      <div className="border-b border-white/10 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold">Admin 管理视图</h1>
          <p className="text-sm text-white/70">仅超级管理员可见，用于调试与后台查看。</p>
        </div>
      </div>

      <div className="flex-1 max-w-4xl mx-auto w-full px-6 py-6 space-y-6">
        <section className="rounded-xl border border-white/10 bg-slate-800/60 px-5 py-4">
          <h2 className="text-sm font-semibold mb-2">当前登录管理员</h2>
          <div className="text-sm space-y-1">
            <p>
              <span className="text-white/60">User ID：</span>
              <span className="font-mono">{user.user_id}</span>
            </p>
            {user.email && (
              <p>
                <span className="text-white/60">Email：</span>
                <span>{user.email}</span>
              </p>
            )}
          </div>
          <p className="mt-3 text-xs text-white/60">
            提示：后台原始运行日志会写入
            <code className="mx-1 px-1 py-0.5 rounded bg-slate-900/80 border border-white/10">
              logs/{user.user_id}/&#123;session_id&#125;/runs.jsonl
            </code>
            ，你可以用任意文本工具查看。
          </p>
        </section>
      </div>
    </div>
  );
}
