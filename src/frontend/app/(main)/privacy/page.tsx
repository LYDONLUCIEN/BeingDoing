'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';

export default function PrivacyPage() {
  return (
    <div className="min-h-screen bg-bd-gradient text-bd-fg">
      <div className="max-w-3xl mx-auto px-4 py-16 space-y-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="space-y-4"
        >
          <Link href="/" className="text-sm hover:underline" style={{ color: 'var(--bd-fg-muted)' }}>
            ← 返回首页
          </Link>
          <h1 className="text-3xl md:text-4xl font-bold">隐私政策</h1>
          <p className="text-bd-muted">我们重视并保护您的隐私。本政策说明我们如何收集、使用和保护您的个人信息。</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="rounded-xl border border-bd-border bg-bd-card p-6 space-y-4 text-bd-muted leading-relaxed text-sm"
        >
          <p className="text-bd-subtle text-xs tracking-widest uppercase">内容即将更新</p>
          <p>完整的隐私政策正在完善中，敬请期待。</p>
        </motion.div>
      </div>
    </div>
  );
}
