'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import SurveyForm from '@/components/survey/SurveyForm';
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
      <div className="max-w-2xl mx-auto px-4 pt-20 pb-16">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="space-y-6"
        >
          {/* Header */}
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => router.push('/explore/activate')}
              className="text-sm text-bd-subtle hover:text-bd-muted transition-colors mb-2 block"
            >
              ← 返回
            </button>
            <p className="text-xs tracking-widest uppercase text-bd-primary">在正式开始之前</p>
            <h1 className="text-3xl font-bold text-bd-fg">了解你</h1>
            <p className="text-bd-muted text-sm leading-relaxed">
              这份问卷帮助我们更了解你的背景，让对话更有针对性。所有问题均为选填，你也可以直接跳过开始探索。
            </p>
          </div>

          {error && <p className="text-sm text-bd-err">{error}</p>}

          {/* Survey form */}
          <div className="rounded-2xl border border-bd-border bg-bd-card p-6 md:p-8">
            <SurveyForm
              initialData={{}}
              loading={loading}
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
