'use client';

import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';
import { Sparkles, BookOpen } from 'lucide-react';

export default function ExploreIntroPage() {
  const router = useRouter();

  return (
    <div
      className="min-h-screen flex flex-col items-center justify-center px-6 py-16"
      style={{ background: 'linear-gradient(to bottom, var(--bd-bg), var(--bd-bg-mid), var(--bd-bg-end))' }}
    >
      <div className="w-full max-w-2xl">
        {/* 返回 */}
        <motion.button
          type="button"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          onClick={() => router.push('/')}
          className="text-sm text-bd-subtle hover:text-bd-fg transition-colors self-start mb-12"
        >
          ← 返回首页
        </motion.button>

        {/* 引导卡片 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.8, delay: 0.5 }}
          className="relative rounded-3xl p-8 md:p-12 overflow-hidden"
          style={{
            background: 'var(--bd-bg-card)',
            border: '1px solid var(--bd-border-soft)',
            boxShadow: '0 4px 24px var(--bd-shadow, rgba(0,0,0,0.06)), 0 1px 3px rgba(0,0,0,0.03)',
          }}
        >
          {/* 左上角装饰 */}
          <div
            className="absolute top-0 left-0 w-24 h-24 rounded-br-full opacity-30"
            style={{ background: 'linear-gradient(135deg, var(--bd-ui-accent), transparent)' }}
          />
          <div
            className="absolute top-6 left-6 w-2 h-2 rounded-full opacity-60"
            style={{ background: 'var(--bd-phase-values)' }}
          />
          <div
            className="absolute top-10 left-10 w-1.5 h-1.5 rounded-full opacity-50"
            style={{ background: 'var(--bd-phase-strengths)' }}
          />

          <div className="relative space-y-6">
            {/* 开篇 — 渐显 */}
            <motion.p
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 0.8 }}
              className="text-base leading-[1.9]"
              style={{ color: 'var(--bd-fg-muted)' }}
            >
              请寻找一个安静的空间和不被打扰的时间段，在
              <span
                className="px-2 py-0.5 rounded-md mx-1 font-semibold"
                style={{
                  background: 'var(--bd-ui-accent-dim)',
                  color: 'var(--bd-ui-accent)',
                }}
              >
                「导师」
              </span>
              的指引下，写下你内心浮现的答案。
            </motion.p>

            <motion.p
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 1.4 }}
              className="text-base leading-[1.9]"
              style={{ color: 'var(--bd-fg-muted)' }}
            >
              不必追求完美，只需捕捉当下最真实的情感流动与思维轨迹。
            </motion.p>

            {/* 分隔 */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ duration: 0.5, delay: 2 }}
              className="flex items-center gap-3 py-2"
            >
              <div className="flex-1 h-px" style={{ background: 'var(--bd-border-soft)' }} />
              <BookOpen size={16} style={{ color: 'var(--bd-fg-subtle)' }} />
              <div className="flex-1 h-px" style={{ background: 'var(--bd-border-soft)' }} />
            </motion.div>

            {/* 说明 */}
            <motion.p
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 2.3 }}
              className="text-base leading-[1.85]"
              style={{ color: 'var(--bd-fg-muted)' }}
            >
              你需要完成
              <span className="font-semibold mx-1" style={{ color: 'var(--bd-fg)' }}>4 个主题</span>
              的探索，可以分次完成，退出后可从历史记录恢复对话。
            </motion.p>

            {/* 收尾句 */}
            <motion.p
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.8, delay: 2.9 }}
              className="text-base leading-relaxed text-center pt-4"
              style={{ color: 'var(--bd-fg)' }}
            >
              现在，就请开启独属于你的
              <span
                className="inline-block mx-1 font-semibold"
                style={{
                  background: 'linear-gradient(135deg, var(--bd-phase-values), var(--bd-phase-interests))',
                  backgroundClip: 'text',
                  WebkitBackgroundClip: 'text',
                  color: 'transparent',
                }}
              >
                心灵之旅
              </span>
              吧。
            </motion.p>
          </div>
        </motion.div>

        {/* 点亮开始 — 在卡片下方 */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.8, delay: 3.5, ease: 'easeOut' }}
          className="flex flex-col items-center pt-12"
        >
          <p className="text-sm text-bd-subtle mb-5 flex items-center gap-2">
            <Sparkles size={14} style={{ color: 'var(--bd-ui-accent)' }} />
            点击下方，开启旅程
          </p>
          <motion.button
            type="button"
            onClick={() => router.push('/explore/activate')}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.6, delay: 3.7 }}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.98 }}
            className="px-14 py-4 rounded-2xl font-semibold text-lg shadow-lg transition-all hover:shadow-xl"
            style={{
              background: 'var(--bd-ui-accent)',
              color: 'var(--bd-ui-accent-fg)',
              boxShadow: '0 8px 32px var(--bd-ui-accent-dim)',
            }}
          >
            点亮开始
          </motion.button>
        </motion.div>
      </div>
    </div>
  );
}
