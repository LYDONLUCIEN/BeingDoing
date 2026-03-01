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
          className="rounded-xl border border-white/10 bg-white/5 p-6 space-y-4 text-white/70 leading-relaxed text-sm"
        >
          <p className="text-white/40 text-xs tracking-widest uppercase">内容即将更新</p>
        </motion.div>
      </div>
    </div>
  );
}
