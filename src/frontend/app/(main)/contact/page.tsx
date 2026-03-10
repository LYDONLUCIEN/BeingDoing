'use client';

import Link from 'next/link';
import { motion } from 'framer-motion';

export default function ContactPage() {
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
          <h1 className="text-3xl md:text-4xl font-bold">联系我们</h1>
          <p className="text-bd-muted">如有任何问题或建议，欢迎与我们联系。</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="rounded-xl border border-bd-border bg-bd-card p-6 space-y-4 text-bd-muted leading-relaxed text-sm"
        >
          <p className="text-bd-subtle text-xs tracking-widest uppercase">联系方式</p>
          <p>
            邮箱：<a href="mailto:hello@zhuyin.app" className="hover:underline" style={{ color: 'var(--bd-ui-accent)' }}>hello@zhuyin.app</a>
          </p>
          <p>其他联系方式即将开放。</p>
        </motion.div>
      </div>
    </div>
  );
}
