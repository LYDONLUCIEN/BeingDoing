'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { apiClient } from '@/lib/api/client';
import { loadSession, saveSession, setLastActivationCode, getLastActivationCode, hasReportAvailable } from '@/lib/explore/session';
import { surveyApi } from '@/lib/api/survey';

export default function ActivatePage() {
  const router = useRouter();
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
      const detail =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        '激活失败，请检查激活码是否正确';
      setError(String(detail));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-bd-gradient text-bd-fg flex items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="w-full max-w-md space-y-8"
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
          <p className="text-xs tracking-widest uppercase" style={{ color: 'var(--bd-ui-accent)' }}>Step 0</p>
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
            className="w-full rounded-xl border bg-bd-overlay px-4 py-3.5 text-base outline-none transition-colors focus:border-[var(--bd-ui-accent)] focus:ring-2 focus:ring-[var(--bd-ui-accent)] focus:ring-opacity-25"
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
            className="w-full rounded-xl px-4 py-3.5 text-base font-semibold text-bd-ui-accent-fg transition-all disabled:opacity-40 hover:opacity-90"
            style={{ background: 'var(--bd-ui-accent)' }}
          >
            {loading ? '验证中…' : '开始探索 →'}
          </button>
          {showReport && (
            <button
              type="button"
              onClick={() => router.push('/explore/report/view')}
              className="w-full rounded-xl px-4 py-3 text-base font-medium border-2 transition-all hover:opacity-90 flex items-center justify-center gap-2"
              style={{ borderColor: 'var(--bd-ui-accent)', color: 'var(--bd-ui-accent)' }}
            >
              查看报告
            </button>
          )}
        </div>

        {/* Steps preview */}
        <div className="border-t border-bd-border pt-6 space-y-3">
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
