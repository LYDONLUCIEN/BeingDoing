'use client';

import { motion } from 'framer-motion';
import { Sparkles } from 'lucide-react';

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-bd-gradient text-bd-fg">
      <div className="max-w-3xl mx-auto px-4 py-16 space-y-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center space-y-4"
        >
          <Sparkles className="w-12 h-12 text-bd-primary mx-auto" />
          <h1 className="text-3xl md:text-4xl font-bold">关于我们</h1>
          <p className="text-bd-muted text-lg">帮助每个人找到真正想做的事</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="rounded-xl border border-bd-border bg-bd-card p-6 space-y-4 text-bd-muted leading-relaxed text-sm"
        >
          <p className="text-bd-subtle text-xs tracking-widest uppercase">内容即将更新</p>
        </motion.div>
      </div>
    </div>
  );
}
