'use client';

import { motion } from 'framer-motion';
import { Users, MessageCircle } from 'lucide-react';

export default function CommunityPage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800 text-white">
      <div className="max-w-3xl mx-auto px-4 py-16 space-y-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center space-y-4"
        >
          <Users className="w-12 h-12 text-primary-400 mx-auto" />
          <h1 className="text-3xl md:text-4xl font-bold">社区</h1>
          <p className="text-white/60 text-lg">
            与志同道合的探索者交流心得，分享你的发现
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="rounded-xl border border-white/10 bg-white/5 p-8 text-center space-y-4"
        >
          <MessageCircle className="w-10 h-10 text-white/30 mx-auto" />
          <p className="text-white/60">社区功能正在开发中，敬请期待</p>
          <p className="text-sm text-white/40">
            我们正在打造一个安全、温暖的社区空间，让每位探索者都能找到共鸣和支持。
          </p>
        </motion.div>
      </div>
    </div>
  );
}
