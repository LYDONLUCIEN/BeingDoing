'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import SurveyFormBd from '@/components/survey/SurveyFormBd';
import { surveyApi } from '@/lib/api/survey';
import { loadSession, saveSession, getLastActivationCode } from '@/lib/explore/session';
import type { SurveyData } from '@/lib/survey/schema';

export default function SurveyPage() {
  const router = useRouter();
  const [activationCode, setActivationCode] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = getLastActivationCode();
    if (!code) {
      router.replace('/explore/activate');
      return;
    }
    setActivationCode(code);
  }, [router]);

  const handleSubmit = async (data: SurveyData) => {
    if (!activationCode) return;
    setLoading(true);
    setError(null);
    try {
      await surveyApi.saveForActivation(activationCode, data);
      const session = loadSession(activationCode);
      saveSession({ ...session, surveyCompleted: true });
      router.push(`/explore/chat/values`);
    } catch (e: any) {
      setError(e?.message || '保存失败，请重试');
    } finally {
      setLoading(false);
    }
  };

  const handleSkip = async () => {
    if (!activationCode) return;
    setLoading(true);
    try {
      await surveyApi.saveForActivation(activationCode, {});
      const session = loadSession(activationCode);
      saveSession({ ...session, surveyCompleted: true });
    } catch {}
    setLoading(false);
    router.push(`/explore/chat/values`);
  };

  if (!activationCode) return null;

  return (
    <div className="min-h-screen bg-bd-gradient text-bd-fg">
      <div className="max-w-2xl mx-auto px-4 pt-24 pb-20">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="space-y-8"
        >
          <button
            type="button"
            onClick={() => router.push('/explore/activate')}
            className="text-sm text-bd-subtle hover:text-bd-fg transition-colors flex items-center gap-1"
          >
            <span aria-hidden>←</span> 返回
          </button>

          <header className="space-y-3">
            <p className="text-xs tracking-[0.25em] uppercase text-bd-primary font-medium">在正式开始之前</p>
            <h1 className="text-3xl sm:text-4xl font-semibold text-bd-fg tracking-tight">了解你</h1>
            <p className="text-bd-muted text-sm sm:text-base leading-relaxed max-w-lg">
              这份问卷帮助我们更了解你的背景，让对话更有针对性。所有问题均为选填，你也可以直接跳过开始探索。
            </p>
          </header>

          {error && (
            <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          )}

          <div className="rounded-2xl border border-bd-border bg-bd-card/80 backdrop-blur-lg p-6 sm:p-8 shadow-[0_4px_24px_rgba(0,0,0,0.06)]">
            <SurveyFormBd
              initialData={{}}
              loading={loading}
              saving={loading}
              submitLabel="提交并开始第一步 →"
              showSkip
              onSubmit={handleSubmit}
              onSkip={handleSkip}
            />
          </div>
        </motion.div>
      </div>
    </div>
  );
}
