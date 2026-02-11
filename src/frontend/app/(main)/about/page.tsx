'use client';

import { motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800 text-white">
      <div className="max-w-3xl mx-auto px-4 py-16 space-y-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center space-y-4"
        >
          <Sparkles className="w-12 h-12 text-primary-400 mx-auto" />
          <h1 className="text-3xl md:text-4xl font-bold">关于我们</h1>
          <p className="text-white/60 text-lg">
            帮助每个人找到真正想做的事
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="rounded-xl border border-white/10 bg-white/5 p-6 space-y-4 text-white/80 leading-relaxed"
        >
          <p>
            「找到想做的事」是一个智能引导系统，基于{' '}
            <strong className="text-white">喜欢 × 擅长 × 价值观 = 天命</strong>{' '}
            的核心理论，通过 AI 驱动的对话式探索，帮助用户发现自己的热情、才能和价值观，进而找到人生的方向。
          </p>
          <p>
            我们相信每个人都有独特的天命。通过结构化的探索流程和智能化的引导，我们希望让这个发现过程变得更加清晰和高效。
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="rounded-xl border border-white/10 bg-white/5 p-6 space-y-4"
        >
          <h2 className="text-lg font-semibold">技术架构</h2>
          <ul className="space-y-2 text-white/70 text-sm">
            <li>前端：Next.js 14 + Tailwind CSS + Zustand</li>
            <li>后端：FastAPI + LangGraph Agent + SQLAlchemy</li>
            <li>AI：基于 ReAct 思维链的智能引导系统</li>
            <li>探索流程：价值观 → 才能 → 热情 → 组合分析 → 精炼结果</li>
          </ul>
        </motion.div>
      </div>
    </div>
  );
}
