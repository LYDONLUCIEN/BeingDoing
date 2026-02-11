'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { Heart, Star, Compass, ArrowRight } from 'lucide-react';

const sections = [
  {
    icon: Heart,
    title: '喜欢的事（热情）',
    color: 'text-rose-400',
    border: 'border-rose-500/30',
    content: [
      '热情是驱动你行动的内在力量。当你做自己真正喜欢的事时，你会感到充满活力、忘记时间的流逝。',
      '在这一环节中，我们会通过一系列问题帮助你识别那些让你兴奋、让你充满好奇心的领域。',
    ],
  },
  {
    icon: Star,
    title: '擅长的事（才能）',
    color: 'text-amber-400',
    border: 'border-amber-500/30',
    content: [
      '才能是你天生就比别人做得好的事情。它们可能是你毫不费力就能表现出色的能力，也可能是你通过长期练习发展出的深厚技能。',
      '我们将帮你发现那些你可能习以为常、但实际上是你独特优势的能力。',
    ],
  },
  {
    icon: Compass,
    title: '重要的事（价值观）',
    color: 'text-blue-400',
    border: 'border-blue-500/30',
    content: [
      '价值观是你内心深处认为最重要的原则和信念。它们决定了什么样的工作和生活方式能让你感到满足和有意义。',
      '通过探索价值观，你将了解哪些因素是你在做人生选择时最不能妥协的。',
    ],
  },
];

export default function TheoryPage() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-900 to-slate-800 text-white">
      <div className="max-w-3xl mx-auto px-4 py-16 space-y-12">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center space-y-4"
        >
          <h1 className="text-3xl md:text-4xl font-bold">理论介绍</h1>
          <p className="text-white/60 text-lg">
            我们的方法基于一个简单而有力的公式
          </p>
          <div className="inline-block px-6 py-3 rounded-xl bg-white/5 border border-white/10">
            <p className="text-xl font-semibold">
              <span className="text-rose-400">喜欢</span>
              {' × '}
              <span className="text-amber-400">擅长</span>
              {' × '}
              <span className="text-blue-400">价值观</span>
              {' = '}
              <span className="text-emerald-400">天命</span>
            </p>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="rounded-xl border border-white/10 bg-white/5 p-6 text-white/80 leading-relaxed space-y-3"
        >
          <p>
            当你找到了自己<strong className="text-rose-400">热爱</strong>的事，同时又是你<strong className="text-amber-400">擅长</strong>做的事，并且这件事还符合你的<strong className="text-blue-400">核心价值观</strong>时，三者的交集就是你的<strong className="text-emerald-400">天命</strong>。
          </p>
          <p>
            三个要素缺一不可。只有热爱没有能力会力不从心；只有能力没有热爱会倦怠空虚；缺少价值观的支撑则会感到迷茫和无意义。
          </p>
        </motion.div>

        {sections.map((sec, i) => (
          <motion.div
            key={sec.title}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 + i * 0.1 }}
            className={`rounded-xl border ${sec.border} bg-white/5 p-6 space-y-3`}
          >
            <div className="flex items-center gap-3">
              <sec.icon className={`w-6 h-6 ${sec.color}`} />
              <h2 className={`text-xl font-semibold ${sec.color}`}>{sec.title}</h2>
            </div>
            {sec.content.map((p, j) => (
              <p key={j} className="text-white/70 leading-relaxed">{p}</p>
            ))}
          </motion.div>
        ))}

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.7 }}
          className="text-center pt-4"
        >
          <Link
            href="/explore"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-primary-500 hover:bg-primary-400 text-white font-semibold transition-colors"
          >
            开始探索 <ArrowRight size={18} />
          </Link>
        </motion.div>
      </div>
    </div>
  );
}
