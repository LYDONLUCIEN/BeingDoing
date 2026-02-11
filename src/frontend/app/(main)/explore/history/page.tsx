'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useAuthStore } from '@/stores/authStore';
import { useSessionStore } from '@/stores/sessionStore';
import { sessionsApi, type Session } from '@/lib/api/sessions';
import { FLOW_STEPS } from '@/lib/constants';
import { ArrowLeft, Play, Trash2 } from 'lucide-react';

export default function HistoryPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();
  const { setCurrentSession } = useSessionStore();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/auth/login?redirect=/explore/history');
      return;
    }
    loadSessions();
  }, [isAuthenticated, router]);

  const loadSessions = async () => {
    setLoading(true);
    try {
      const res = await sessionsApi.list();
      setSessions(res.data?.sessions || []);
    } catch (err: any) {
      setError('加载历史记录失败');
    } finally {
      setLoading(false);
    }
  };

  const handleContinue = (session: Session) => {
    setCurrentSession(session);
    router.push('/explore/flow');
  };

  const handleDelete = async (sessionId: string) => {
    if (!confirm('确定要删除这条探索记录吗？')) return;
    try {
      await sessionsApi.delete(sessionId);
      setSessions((prev) => prev.filter((s) => s.session_id !== sessionId));
    } catch (err: any) {
      setError(err.response?.data?.detail || '删除失败');
    }
  };

  const getStepName = (stepId: string) => {
    return FLOW_STEPS.find((s) => s.id === stepId)?.name || stepId;
  };

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="animate-spin rounded-full h-12 w-12 border-2 border-primary-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800 text-white">
      <div className="max-w-3xl mx-auto px-4 py-10 space-y-6">
        <div className="flex items-center gap-3">
          <Link
            href="/explore"
            className="flex items-center gap-1 text-sm text-white/60 hover:text-white transition-colors"
          >
            <ArrowLeft size={16} /> 返回
          </Link>
          <h1 className="text-2xl font-bold">历史探索</h1>
        </div>

        {error && (
          <div className="p-3 rounded-lg bg-red-500/20 border border-red-400/40 text-red-200 text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="animate-spin rounded-full h-8 w-8 border-2 border-primary-500 border-t-transparent" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-20 space-y-3">
            <p className="text-white/60">暂无探索记录</p>
            <Link
              href="/explore"
              className="inline-block px-5 py-2 rounded-lg bg-primary-500 hover:bg-primary-400 text-white text-sm font-medium transition-colors"
            >
              开始新的探索
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {sessions.map((session) => (
              <div
                key={session.session_id}
                className="rounded-xl border border-white/10 bg-white/5 p-4 flex items-center gap-4"
              >
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">
                    {getStepName(session.current_step)}
                  </p>
                  <p className="text-xs text-white/50 mt-1">
                    {new Date(session.last_activity_at || session.created_at).toLocaleDateString('zh-CN', {
                      year: 'numeric',
                      month: 'long',
                      day: 'numeric',
                      hour: '2-digit',
                      minute: '2-digit',
                    })}
                    <span className="ml-2 px-1.5 py-0.5 rounded bg-white/10 text-white/60">
                      {session.status === 'completed' ? '已完成' : '进行中'}
                    </span>
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => handleContinue(session)}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-primary-500/20 text-primary-300 hover:bg-primary-500/30 text-sm transition-colors"
                  >
                    <Play size={14} /> 继续
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDelete(session.session_id)}
                    className="p-1.5 rounded-lg text-red-400/60 hover:text-red-400 hover:bg-red-500/20 transition-colors"
                    title="删除"
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
