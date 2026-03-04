'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { Sparkles, FileText } from 'lucide-react';
import { PHASES } from '@/lib/explore/session';
import { getLastActivationCode, loadSession, saveSession } from '@/lib/explore/session';

const PROGRESS_DURATION_MS = 4200;

export default function ReportPrepPage() {
  const router = useRouter();
  const [progress, setProgress] = useState(0);
  const [status, setStatus] = useState<'loading' | 'ready'>('loading');

  useEffect(() => {
    let rafId: number;
    const start = Date.now();
    const tick = () => {
      const elapsed = Date.now() - start;
      const p = Math.min(elapsed / PROGRESS_DURATION_MS, 1);
      setProgress(p);
      if (p >= 1) {
        setStatus('ready');
        const c = getLastActivationCode();
        if (c) {
          const s = loadSession(c);
          saveSession({ ...s, reportReady: true });
        }
        return;
      }
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, []);

  return (
    <div className="min-h-screen bg-bd-gradient text-bd-fg flex items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="max-w-lg w-full text-center space-y-8"
      >
        <div
          className="inline-flex items-center justify-center w-16 h-16 rounded-full border-2 transition-colors duration-500"
          style={{
            backgroundColor: status === 'ready' ? 'rgba(124, 92, 252, 0.2)' : 'rgba(124, 92, 252, 0.1)',
            borderColor: 'var(--bd-ui-accent)',
          }}
        >
          <Sparkles
            className="w-7 h-7 transition-colors duration-500"
            style={{ color: 'var(--bd-ui-accent)' }}
          />
        </div>

        <div className="space-y-3">
          <p className="text-xs tracking-widest uppercase text-bd-subtle">探索完成</p>
          <h1 className="text-3xl font-bold">四力共鸣</h1>
          <p className="text-bd-muted leading-relaxed">
            你已完成信念、禀赋、热忱与使命的全部探索。
            <br />
            {status === 'loading' ? '正在生成综合报告…' : '报告已就绪'}
          </p>
        </div>

        <AnimatePresence mode="wait">
          {status === 'loading' ? (
            <motion.div
              key="progress"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="space-y-3"
            >
              <div className="h-2.5 rounded-full bg-bd-overlay overflow-hidden">
                <motion.div
                  className="h-full rounded-full relative overflow-hidden"
                  initial={{ width: 0 }}
                  animate={{ width: `${progress * 100}%` }}
                  transition={{ duration: 0.15 }}
                  style={{
                    background: 'linear-gradient(90deg, var(--bd-ui-accent), rgba(124, 92, 252, 0.8))',
                    boxShadow: '0 0 20px rgba(124, 92, 252, 0.5), 0 0 40px rgba(124, 92, 252, 0.3)',
                  }}
                >
                  <div
                    className="absolute inset-0 opacity-60"
                    style={{
                      background:
                        'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.4) 50%, transparent 100%)',
                      animation: 'report-shimmer 1.5s ease-in-out infinite',
                    }}
                  />
                </motion.div>
              </div>
              <p className="text-xs text-bd-subtle">
                {Math.round(progress * 100)}%
              </p>
            </motion.div>
          ) : (
            <motion.div
              key="ready"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="space-y-6"
            >
              <button
                type="button"
                onClick={() => router.push('/explore/report/view')}
                className="w-full inline-flex items-center justify-center gap-3 rounded-xl px-6 py-4 text-base font-semibold text-white transition-all hover:opacity-90 hover:scale-[1.02] active:scale-[0.98]"
                style={{
                  background: 'var(--bd-ui-accent)',
                  boxShadow: '0 4px 20px rgba(124, 92, 252, 0.4)',
                }}
              >
                <FileText className="w-5 h-5" />
                查看报告
              </button>

              <div className="grid grid-cols-2 gap-3">
                {PHASES.map((p) => (
                  <button
                    key={p.key}
                    type="button"
                    onClick={() => router.push(`/explore/chat/${p.key}`)}
                    className="rounded-xl border border-bd-border bg-bd-card hover:bg-bd-overlay-md px-4 py-3 text-sm transition-colors text-left"
                  >
                    <span className="text-xs font-mono text-bd-ghost block mb-0.5">{p.num}</span>
                    <span className="font-medium text-bd-fg">{p.label}</span>
                    <span className="text-xs text-bd-subtle block mt-0.5">回顾对话</span>
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        <button
          type="button"
          onClick={() => router.push('/')}
          className="text-sm text-bd-subtle hover:text-bd-muted transition-colors underline underline-offset-4"
        >
          返回首页
        </button>
      </motion.div>
    </div>
  );
}
