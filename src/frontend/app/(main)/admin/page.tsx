'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/stores/authStore';
import { useThemeStore } from '@/stores/themeStore';
import { useDebugStore } from '@/stores/debugStore';
import { apiClient } from '@/lib/api/client';
import { loadSession, saveSession, setLastActivationCode, type PhaseKey } from '@/lib/explore/session';
import Link from 'next/link';
import { CheckCircle2, Bug, Loader2, Palette } from 'lucide-react';

const ALL_PHASES = ['values', 'strengths', 'interests', 'purpose'] as const;

function DebugSection() {
  const router = useRouter();
  const { debugMode, isDebugAdmin, loaded, loadStatus } = useDebugStore();
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const handleLoad = async (redirectTo: 'chat' | 'report') => {
    const trimmed = code.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.post('/simple-auth/activate', { code: trimmed });
      const activationCode: string = res.data.activation_code;
      setLastActivationCode(activationCode);
      const session = loadSession(activationCode);
      const debugSession = {
        ...session,
        activationCode,
        unlockedPhases: [...ALL_PHASES],
        currentPhase: (redirectTo === 'report' ? 'purpose' : 'values') as PhaseKey,
        surveyCompleted: true,
      };
      saveSession(debugSession);
      router.push(redirectTo === 'report' ? '/explore/report' : '/explore/chat/values');
    } catch (err: any) {
      const detail = err?.response?.data?.detail || err?.response?.data?.message || '激活码无效或不存在';
      setError(String(detail));
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="rounded-xl border border-bd-border bg-bd-card px-5 py-5 space-y-5">
      <div className="flex items-center gap-2">
        <Bug size={18} className="text-bd-primary" />
        <h2 className="text-sm font-semibold text-bd-fg">Debug 模式</h2>
      </div>
      {!loaded ? (
        <p className="text-sm text-bd-muted">加载中…</p>
      ) : isDebugAdmin ? (
        <div className="space-y-4">
          <p className="text-xs text-bd-muted">
            Debug 模式已开启。你可以载入任意激活码（包括已过期）并解锁全部阶段，用于调试历史数据。
          </p>
          <div className="flex flex-col sm:flex-row gap-3">
            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="输入激活码"
              className="flex-1 rounded-lg border border-bd-border bg-bd-overlay px-3 py-2 text-sm text-bd-fg outline-none focus:border-bd-primary"
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => handleLoad('chat')}
                disabled={loading || !code.trim()}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-bd-primary text-bd-primary-fg hover:opacity-90 disabled:opacity-40 flex items-center gap-1.5"
              >
                {loading ? <Loader2 size={14} className="animate-spin" /> : null}
                载入并解锁全部
              </button>
              <button
                type="button"
                onClick={() => handleLoad('report')}
                disabled={loading || !code.trim()}
                className="px-4 py-2 rounded-lg text-sm font-medium border border-bd-border text-bd-muted hover:text-bd-fg hover:bg-bd-overlay-md disabled:opacity-40 flex items-center gap-1.5"
              >
                直接查看报告
              </button>
            </div>
          </div>
          {error && <p className="text-xs text-bd-err">{error}</p>}
        </div>
      ) : (
        <p className="text-sm text-bd-muted">
          {debugMode
            ? '当前账号不在超级管理员列表中，请在 .env 的 SUPER_ADMIN_EMAILS 中添加你的邮箱。'
            : 'Debug 模式未开启。在 .env 中设置 DEBUG_MODE=true 后，超级管理员即可使用调试功能。'}
        </p>
      )}
    </section>
  );
}

function ThemeSwitcher() {
  const { colorScheme } = useThemeStore();

  return (
    <section className="bd-eff-card rounded-xl border border-bd-border bg-bd-card px-5 py-5 space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-bd-fg">界面主题</h2>
        <p className="text-xs text-bd-muted mt-0.5">黑白各一套。顶部导航栏 ☀️/🌙 切换日/夜间模式。配色在下方入口配置。</p>
      </div>
      <p className="text-xs text-bd-subtle">
        当前：<code className="text-bd-primary font-mono">{colorScheme === 'dark' ? '夜间' : '日间'}</code>
      </p>
      <div className="flex flex-wrap gap-2">
        <Link
          href="/settings/colors"
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors border"
          style={{
            borderColor: 'var(--bd-border)',
            color: 'var(--bd-fg)',
            background: 'var(--bd-overlay)',
          }}
        >
          <Palette size={16} /> 配色（背景 / 四维 / 导引色）
        </Link>
        <Link
          href="/settings/style-lab"
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors border"
          style={{
            borderColor: 'var(--bd-border)',
            color: 'var(--bd-fg-muted)',
            background: 'var(--bd-overlay)',
          }}
        >
          效果实验室
        </Link>
      </div>
    </section>
  );
}

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
      <div className="min-h-screen flex items-center justify-center bg-bd-bg text-bd-fg">
        <div className="rounded-xl border border-bd-border bg-bd-card px-6 py-4 text-center space-y-2">
          <p className="text-base font-semibold">无权限访问管理视图</p>
          <p className="text-sm text-bd-muted">
            只有在 <code className="px-1 py-0.5 bg-bd-overlay rounded border border-bd-border">.env</code>{' '}
            中配置为超级管理员的账号才能访问此页面。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-bd-gradient text-bd-fg flex flex-col">
      <div className="border-b border-bd-border px-6 py-4 flex items-center justify-between" style={{ backgroundColor: 'var(--bd-nav-bg)' }}>
        <div>
          <h1 className="text-xl font-semibold text-bd-fg">Admin 管理视图</h1>
          <p className="text-sm text-bd-muted">仅超级管理员可见，用于调试与后台查看。</p>
        </div>
      </div>

      <div className="flex-1 max-w-4xl mx-auto w-full px-6 py-6 space-y-6">

        {/* Theme switcher */}
        <ThemeSwitcher />

        {/* Debug 模式 */}
        <DebugSection />

        {/* Account info */}
        <section className="bd-eff-card rounded-xl border border-bd-border bg-bd-card px-5 py-4">
          <h2 className="text-sm font-semibold mb-2 text-bd-fg">当前登录管理员</h2>
          <div className="text-sm space-y-1">
            <p>
              <span className="text-bd-muted">User ID：</span>
              <span className="font-mono text-bd-fg">{user.user_id}</span>
            </p>
            {user.email && (
              <p>
                <span className="text-bd-muted">Email：</span>
                <span className="text-bd-fg">{user.email}</span>
              </p>
            )}
          </div>
          <p className="mt-3 text-xs text-bd-muted">
            提示：后台原始运行日志会写入
            <code className="mx-1 px-1 py-0.5 rounded bg-bd-overlay border border-bd-border">
              logs/{user.user_id}/&#123;session_id&#125;/runs.jsonl
            </code>
            ，你可以用任意文本工具查看。
          </p>
        </section>

      </div>
    </div>
  );
}
