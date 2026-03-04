'use client';

import { motion } from 'framer-motion';
import { Users, MessageCircle } from 'lucide-react';

export default function CommunityPage() {
  return (
    <div className="min-h-screen bg-bd-gradient text-bd-fg">
      <div className="max-w-3xl mx-auto px-4 py-16 space-y-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center space-y-4"
        >
          <Users className="w-12 h-12 text-bd-primary mx-auto" />
          <h1 className="text-3xl md:text-4xl font-bold">社区</h1>
          <p className="text-bd-muted text-lg">与志同道合的探索者交流心得，分享你的发现</p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="rounded-xl border border-bd-border bg-bd-card p-8 text-center space-y-4"
        >
          <MessageCircle className="w-10 h-10 text-bd-subtle mx-auto" />
          <p className="text-bd-muted">社区功能正在开发中，敬请期待</p>
          <p className="text-sm text-bd-subtle">
            我们正在打造一个安全、温暖的社区空间，让每位探索者都能找到共鸣和支持。
          </p>
        </motion.div>
      </div>
    </div>
  );
}
