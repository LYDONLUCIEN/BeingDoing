'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { apiClient } from '@/lib/api/client';
import { loadSession, saveSession, setLastActivationCode, getLastActivationCode, hasReportAvailable } from '@/lib/explore/session';
import { surveyApi } from '@/lib/api/survey';

function useActivateBg() {
  useEffect(() => {
    document.documentElement.setAttribute('data-activate-page', 'true');
    return () => document.documentElement.removeAttribute('data-activate-page');
  }, []);
}

export default function ActivatePage() {
  const router = useRouter();
  useActivateBg();
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showReport, setShowReport] = useState(false);

  useEffect(() => {
    const last = getLastActivationCode();
    if (last) setCode(last);
  }, []);

  useEffect(() => {
    const trimmed = code.trim();
    if (!trimmed) {
      setShowReport(false);
      return;
    }
    try {
      const session = loadSession(trimmed);
      setShowReport(hasReportAvailable(session));
    } catch {
      setShowReport(false);
    }
  }, [code]);

  const handleActivate = async () => {
    const trimmed = code.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.post('/simple-auth/activate', { code: trimmed });
      const activationCode: string = res.data.activation_code;
      setLastActivationCode(activationCode);

      // Load existing session state (preserves unlocked phases on revisit)
      const session = loadSession(activationCode);

      // Check if survey already completed
      let surveyDone = session.surveyCompleted;
      if (!surveyDone) {
        try {
          const sv = await surveyApi.getForActivation(activationCode);
          const data = sv.data?.survey_data ?? {};
          const hasData = Object.keys(data).some((k) => {
            const v = (data as Record<string, unknown>)[k];
            return v !== undefined && v !== null && v !== '' && (Array.isArray(v) ? v.length > 0 : true);
          });
          surveyDone = hasData;
        } catch {}
      }

      saveSession({ ...session, activationCode, surveyCompleted: surveyDone });

      if (surveyDone) {
        router.push(`/explore/chat/${session.currentPhase}`);
      } else {
        router.push('/explore/survey');
      }
    } catch (err: any) {
      const raw =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message;
      const detail = Array.isArray(raw) ? raw[0] : raw;
      const fallback = err?.response
        ? '激活失败，请检查激活码是否正确'
        : '网络错误或服务器未响应，请检查后端是否启动、NEXT_PUBLIC_API_URL 是否正确';
      setError(detail || fallback);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="activate-page-wrap relative min-h-screen text-bd-fg flex items-center justify-center px-4">
      {/* 首页 mesh 背景 */}
      <div className="landing-mesh-bg fixed inset-0 z-0" aria-hidden>
        <div className="landing-mesh-blob landing-mesh-blob-1" />
        <div className="landing-mesh-blob landing-mesh-blob-2" />
        <div className="landing-mesh-blob landing-mesh-blob-3" />
        <div className="landing-mesh-blob landing-mesh-blob-4" />
      </div>
      <div className="landing-mesh-noise fixed inset-0 z-[1]" aria-hidden />
      <motion.div
        className="relative z-[2] w-full max-w-md space-y-8"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
      >
        {/* Back */}
        <button
          type="button"
          onClick={() => router.push('/')}
          className="text-sm text-bd-subtle hover:text-bd-muted transition-colors"
        >
          ← 返回首页
        </button>

        {/* Header */}
        <div className="space-y-2">
          <p className="text-xs tracking-widest uppercase text-neutral-600">Step 0</p>
          <h1 className="text-3xl font-bold text-bd-fg">输入激活码</h1>
          <p className="text-bd-muted text-sm leading-relaxed">
            激活码是你专属的探索通行证。整个探索过程中，所有对话记录都会自动保存，可随时回来继续。
          </p>
        </div>

        {/* Input */}
        <div className="space-y-3">
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !loading) handleActivate(); }}
            placeholder="请输入你的激活码"
            className="w-full rounded-xl border bg-bd-overlay px-4 py-3.5 text-base outline-none transition-colors focus:border-neutral-400 focus:ring-2 focus:ring-neutral-300 focus:ring-opacity-50"
            style={{
              color: 'var(--bd-fg)',
              borderColor: 'var(--bd-border)',
            }}
          />
          {error && <p className="text-sm text-bd-err">{error}</p>}
          <button
            type="button"
            onClick={handleActivate}
            disabled={loading || !code.trim()}
            className="bd-btn-black w-full rounded-xl px-4 py-3.5 text-base font-semibold text-white transition-all disabled:opacity-40"
          >
            {loading ? '验证中…' : '开始探索 →'}
          </button>
          {showReport && (
            <button
              type="button"
              onClick={() => router.push('/explore/report/view')}
              className="bd-btn-report w-full rounded-xl px-4 py-3 text-base font-medium flex items-center justify-center gap-2"
            >
              查看报告
            </button>
          )}
        </div>

        {/* Steps preview - 独立背景避免 mesh 影响文字可读性 */}
        <div className="bd-activate-steps-preview rounded-xl p-4 space-y-3">
          <p className="text-xs text-bd-subtle uppercase tracking-widest">探索路径</p>
          {[
            { num: '01', label: '信念', desc: '你最在意什么？', varColor: 'var(--bd-phase-values)' },
            { num: '02', label: '禀赋', desc: '你天生擅长什么？', varColor: 'var(--bd-phase-strengths)' },
            { num: '03', label: '热忱', desc: '什么让你忘我投入？', varColor: 'var(--bd-phase-interests)' },
            { num: '04', label: '使命', desc: '你想为谁而做？', varColor: 'var(--bd-phase-purpose)' },
          ].map((s) => (
            <div key={s.num} className="flex items-center gap-3">
              <span className="text-xs font-mono" style={{ color: s.varColor }}>{s.num}</span>
              <span className="text-sm font-semibold" style={{ color: s.varColor }}>{s.label}</span>
              <span className="text-xs text-bd-subtle">{s.desc}</span>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
