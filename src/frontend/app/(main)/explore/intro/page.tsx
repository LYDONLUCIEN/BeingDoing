'use client';

import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';

const PARAGRAPHS = [
  '请寻找一个安静的空间和不被打扰的时间段，在「导师」的指引下，写下你内心浮现的答案。不必追求完美，只需捕捉当下最真实的情感流动与思维轨迹。',
  '你需要完成 4 个主题的探索，可以分次完成，退出后可从历史记录恢复对话。',
  '现在，就请开启独属于你的心灵之旅吧。',
];

export default function ExploreIntroPage() {
  const router = useRouter();

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center px-6 py-12"
      style={{ background: 'linear-gradient(to bottom, var(--bd-bg), var(--bd-bg-mid), var(--bd-bg-end))' }}
    >
      <div className="w-full max-w-xl space-y-8">
        {/* 返回 */}
        <button
          type="button"
          onClick={() => router.push('/')}
          className="text-sm text-bd-subtle hover:text-bd-muted transition-colors self-start"
        >
          ← 返回首页
        </button>

        {/* 逐段渐现的文案 */}
        <div className="space-y-8 min-h-[280px]">
          {PARAGRAPHS.map((text, i) => (
            <motion.p
              key={i}
              initial={{ opacity: 0, y: 24 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: 1,
                delay: 0.8 + i * 1.2,
                ease: [0.22, 1, 0.36, 1],
              }}
              className="text-base md:text-lg leading-relaxed"
              style={{ color: 'var(--bd-fg)' }}
            >
              {text}
            </motion.p>
          ))}
        </div>

        {/* 点亮开始 — 在文案全部浮现后出现 */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 4.2, ease: 'easeOut' }}
          className="flex flex-col items-center pt-6"
        >
          <p className="text-sm text-bd-subtle mb-4">点击下方，开启旅程</p>
          <motion.button
            type="button"
            onClick={() => router.push('/explore/activate')}
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6, delay: 4.5 }}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.98 }}
            className="px-12 py-4 rounded-xl font-semibold text-lg shadow-lg transition-shadow hover:shadow-xl"
            style={{
              background: 'linear-gradient(135deg, var(--bd-primary), var(--bd-primary-alt))',
              color: 'var(--bd-primary-fg)',
              boxShadow: '0 8px 24px var(--bd-primary-dim)',
            }}
          >
            点亮开始
          </motion.button>
        </motion.div>
      </div>
    </div>
  );
}
