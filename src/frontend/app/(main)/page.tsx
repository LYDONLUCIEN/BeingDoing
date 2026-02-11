'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { useAuthStore } from '@/stores/authStore';
import { Heart, Star, Compass } from 'lucide-react';

const cards = [
  {
    icon: Heart,
    title: '喜欢的事（热情）',
    description: '探索你内心真正感兴趣的事物，找到让你充满活力的方向。',
    color: 'from-rose-500/20 to-rose-600/10',
    borderColor: 'border-rose-500/30',
    iconColor: 'text-rose-400',
  },
  {
    icon: Star,
    title: '擅长的事（才能）',
    description: '发现你的天赋优势和核心能力，了解你能在哪些方面出类拔萃。',
    color: 'from-amber-500/20 to-amber-600/10',
    borderColor: 'border-amber-500/30',
    iconColor: 'text-amber-400',
  },
  {
    icon: Compass,
    title: '重要的事（价值观）',
    description: '明确你最看重的价值观，找到让你感到有意义的人生方向。',
    color: 'from-blue-500/20 to-blue-600/10',
    borderColor: 'border-blue-500/30',
    iconColor: 'text-blue-400',
  },
];

export default function LandingPage() {
  const router = useRouter();
  const { isAuthenticated } = useAuthStore();

  const handleStart = () => {
    if (isAuthenticated) {
      router.push('/explore');
    } else {
      router.push('/auth/login?redirect=/explore');
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800 text-white">
      {/* Hero */}
      <section className="flex flex-col items-center justify-center text-center px-4 pt-24 pb-16">
        <motion.h1
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="text-4xl md:text-5xl font-bold mb-4"
        >
          找到想做的事
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.15 }}
          className="text-lg md:text-xl text-white/60 mb-6 max-w-xl"
        >
          一个沉浸式的智能引导系统，帮助你发现真正的天命
        </motion.p>

        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.3 }}
          className="mb-10 px-6 py-3 rounded-xl bg-white/5 border border-white/10"
        >
          <p className="text-xl md:text-2xl font-semibold">
            <span className="text-rose-400">喜欢</span>
            {' × '}
            <span className="text-amber-400">擅长</span>
            {' × '}
            <span className="text-blue-400">价值观</span>
            {' = '}
            <span className="text-emerald-400">天命</span>
          </p>
        </motion.div>

        <motion.button
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.45 }}
          type="button"
          onClick={handleStart}
          className="px-8 py-3 rounded-xl bg-primary-500 hover:bg-primary-400 text-white font-semibold text-lg transition-colors"
        >
          开始测试
        </motion.button>
      </section>

      {/* Three cards */}
      <section className="max-w-5xl mx-auto px-4 pb-24">
        <div className="grid md:grid-cols-3 gap-6">
          {cards.map((card, i) => (
            <motion.div
              key={card.title}
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.5, delay: 0.6 + i * 0.12 }}
              className={`rounded-xl border ${card.borderColor} bg-gradient-to-b ${card.color} p-6 space-y-3`}
            >
              <card.icon className={`w-8 h-8 ${card.iconColor}`} />
              <h3 className="text-lg font-semibold">{card.title}</h3>
              <p className="text-sm text-white/70 leading-relaxed">{card.description}</p>
            </motion.div>
          ))}
        </div>
      </section>

      {/* Footer hint */}
      <section className="text-center pb-12">
        <Link href="/theory" className="text-sm text-white/50 hover:text-white/80 transition-colors underline underline-offset-4">
          了解理论背景 →
        </Link>
      </section>
    </div>
  );
}
