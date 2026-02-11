'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { useAuthStore } from '@/stores/authStore';
import { useSessionStore } from '@/stores/sessionStore';
import { sessionsApi } from '@/lib/api/sessions';
import { Plus, History } from 'lucide-react';

export default function ExploreChoicePage() {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();
  const { setCurrentSession } = useSessionStore();

  useEffect(() => {
    if (!isAuthenticated) {
      router.push('/auth/login?redirect=/explore');
    }
  }, [isAuthenticated, router]);

  const handleNewStart = async () => {
    try {
      const res = await sessionsApi.create({ current_step: 'values_exploration' });
      setCurrentSession(res.data);
      router.push('/explore/flow');
    } catch (err: any) {
      console.error('创建会话失败:', err);
    }
  };

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-900">
        <div className="animate-spin rounded-full h-12 w-12 border-2 border-primary-500 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800 text-white">
      <div className="max-w-3xl mx-auto px-4 py-16 space-y-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center space-y-4"
        >
          <h1 className="text-3xl md:text-4xl font-bold">开始探索</h1>
          <p className="text-white/60 text-lg">
            选择开启一段新的探索旅程，或继续之前的进度
          </p>
        </motion.div>

        <div className="grid md:grid-cols-2 gap-6">
          <motion.button
            type="button"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
            onClick={handleNewStart}
            className="group rounded-xl border border-emerald-500/30 bg-gradient-to-b from-emerald-500/15 to-emerald-600/5 p-8 text-left space-y-4 hover:border-emerald-500/50 hover:from-emerald-500/25 transition-all"
          >
            <Plus className="w-10 h-10 text-emerald-400 group-hover:scale-110 transition-transform" />
            <h2 className="text-xl font-semibold text-emerald-300">新的开始</h2>
            <p className="text-sm text-white/60 leading-relaxed">
              从头开始一段全新的探索旅程。我们会依次引导你探索价值观、才能和热情，最终帮你找到天命。
            </p>
          </motion.button>

          <motion.button
            type="button"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            onClick={() => router.push('/explore/history')}
            className="group rounded-xl border border-blue-500/30 bg-gradient-to-b from-blue-500/15 to-blue-600/5 p-8 text-left space-y-4 hover:border-blue-500/50 hover:from-blue-500/25 transition-all"
          >
            <History className="w-10 h-10 text-blue-400 group-hover:scale-110 transition-transform" />
            <h2 className="text-xl font-semibold text-blue-300">回顾过去</h2>
            <p className="text-sm text-white/60 leading-relaxed">
              查看你之前的探索记录，继续未完成的旅程，或回顾已完成的分析结果。
            </p>
          </motion.button>
        </div>
      </div>
    </div>
  );
}
