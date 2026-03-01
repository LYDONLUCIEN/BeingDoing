'use client';

import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';
import { PHASES } from '@/lib/explore/session';

export default function ReportPage() {
  const router = useRouter();

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-950 via-slate-900 to-slate-950 text-white flex items-center justify-center px-4">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.6 }}
        className="max-w-lg w-full text-center space-y-8"
      >
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary-500/20 border border-primary-500/40">
          <Sparkles className="w-7 h-7 text-primary-400" />
        </div>

        <div className="space-y-3">
          <p className="text-xs tracking-widest uppercase text-white/30">探索完成</p>
          <h1 className="text-3xl font-bold">四力共鸣</h1>
          <p className="text-white/50 leading-relaxed">
            你已完成信念、禀赋、热忱与使命的全部探索。<br />
            综合报告功能正在开发中，敬请期待。
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          {PHASES.map((p) => (
            <button
              key={p.key}
              type="button"
              onClick={() => router.push(`/explore/chat/${p.key}`)}
              className="rounded-xl border border-white/10 bg-white/5 hover:bg-white/10 px-4 py-3 text-sm transition-colors text-left"
            >
              <span className="text-xs font-mono text-white/20 block mb-0.5">{p.num}</span>
              <span className="font-medium text-white/80">{p.label}</span>
              <span className="text-xs text-white/30 block mt-0.5">回顾对话</span>
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={() => router.push('/')}
          className="text-sm text-white/40 hover:text-white/70 transition-colors underline underline-offset-4"
        >
          返回首页
        </button>
      </motion.div>
    </div>
  );
}
