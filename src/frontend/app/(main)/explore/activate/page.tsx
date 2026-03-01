'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { apiClient } from '@/lib/api/client';
import { loadSession, saveSession, setLastActivationCode, getLastActivationCode } from '@/lib/explore/session';
import { surveyApi } from '@/lib/api/survey';

export default function ActivatePage() {
  const router = useRouter();
  const [code, setCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const last = getLastActivationCode();
    if (last) setCode(last);
  }, []);

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
    <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 text-white flex items-center justify-center px-4">
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
          className="text-sm text-white/40 hover:text-white/70 transition-colors"
        >
          ← 返回首页
        </button>

        {/* Header */}
        <div className="space-y-2">
          <p className="text-xs tracking-widest uppercase text-primary-400">Step 0</p>
          <h1 className="text-3xl font-bold">输入激活码</h1>
          <p className="text-white/50 text-sm leading-relaxed">
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
            className="w-full rounded-xl border border-white/15 bg-white/5 px-4 py-3.5 text-base outline-none focus:border-primary-400 transition-colors placeholder:text-white/25"
          />
          {error && <p className="text-sm text-rose-400">{error}</p>}
          <button
            type="button"
            onClick={handleActivate}
            disabled={loading || !code.trim()}
            className="w-full rounded-xl bg-primary-500 hover:bg-primary-400 disabled:bg-primary-500/40 px-4 py-3.5 text-base font-semibold transition-all"
          >
            {loading ? '验证中…' : '开始探索 →'}
          </button>
        </div>

        {/* Steps preview */}
        <div className="border-t border-white/10 pt-6 space-y-3">
          <p className="text-xs text-white/30 uppercase tracking-widest">探索路径</p>
          {[
            { num: '01', label: '信念', desc: '你最在意什么？', color: 'text-blue-400' },
            { num: '02', label: '禀赋', desc: '你天生擅长什么？', color: 'text-amber-400' },
            { num: '03', label: '热忱', desc: '什么让你忘我投入？', color: 'text-rose-400' },
            { num: '04', label: '使命', desc: '你想为谁而做？', color: 'text-emerald-400' },
          ].map((s) => (
            <div key={s.num} className="flex items-center gap-3">
              <span className="text-xs font-mono text-white/20">{s.num}</span>
              <span className={`text-sm font-semibold ${s.color}`}>{s.label}</span>
              <span className="text-xs text-white/40">{s.desc}</span>
            </div>
          ))}
        </div>
      </motion.div>
    </div>
  );
}
