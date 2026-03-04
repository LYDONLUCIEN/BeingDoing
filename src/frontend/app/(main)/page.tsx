'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useLocale } from '@/hooks/useLocale';
import { useThemeStore, DARK_THEMES } from '@/stores/themeStore';

// ── 用户留言数据（2~3 色水彩晕染撞色）──────────────────────────
const TESTIMONIALS: Array<{
  quote: string;
  name: string;
  role: string;
  colors: [string, string, string?]; // rgb 如 '129,140,248'，2~3 色撞色
  color: string; // 主色（用于背景、指示点等）
}> = [
  {
    quote: '我第一次意识到，我一直在做别人期待的事，而不是我认为重要的事。这个过程让我看清了自己。',
    name: '小林',
    role: '28岁 / 产品经理',
    colors: ['129, 140, 248', '52, 211, 153', '251, 191, 36'], // indigo + emerald + amber
    color: '129, 140, 248',
  },
  {
    quote: '原来沟通协调这件事对我来说真的是禀赋，不是习惯。这个区分让我第一次觉得自己有竞争力。',
    name: 'Maggie',
    role: '32岁 / 市场运营',
    colors: ['251, 113, 133', '244, 114, 182', '129, 140, 248'], // rose + pink + indigo
    color: '251, 113, 133',
  },
  {
    quote: '帮助别人成长这件事，让我忘我。我以为那只是爱好，没想到可以成为职业核心。',
    name: '阿文',
    role: '25岁 / 应届生',
    colors: ['251, 191, 36', '52, 211, 153'], // amber + emerald
    color: '251, 191, 36',
  },
  {
    quote: '使命感这个词以前对我太虚了。但当我说出「我想帮普通人做出好决策」的时候，我哭了。',
    name: '晓敏',
    role: '35岁 / 咨询顾问',
    colors: ['52, 211, 153', '34, 211, 238', '129, 140, 248'], // emerald + cyan + indigo
    color: '52, 211, 153',
  },
  {
    quote: '以为自己什么都喜欢，其实是什么都没认真想过。四个维度逼着我去想清楚，很有价值。',
    name: '老K',
    role: '40岁 / 创业者',
    colors: ['34, 211, 238', '129, 140, 248'], // cyan + indigo
    color: '34, 211, 238',
  },
  {
    quote: '第一次做完就哭了，太多东西压在心里没被看见。这是一份给自己的礼物。',
    name: '苏苏',
    role: '29岁 / 教师',
    colors: ['244, 114, 182', '251, 113, 133', '251, 191, 36'], // pink + rose + amber
    color: '244, 114, 182',
  },
];

// 探索你的故事：紫色系 CTA（文案来自 i18n）
const EXPLORE_CTA_COLORS = ['124, 92, 252', '167, 139, 250', '196, 181, 253'] as [string, string, string];

// ── 四个核心维度（配色：信念=蓝/禀赋=绿/热忱=红/使命=黄，文案来自 i18n）──
const DIMENSION_KEYS = ['values', 'strengths', 'interests', 'purpose'] as const;
const DIMENSION_VARS: Record<(typeof DIMENSION_KEYS)[number], { varColor: string; varBorder: string; varBg: string }> = {
  values: { varColor: 'var(--bd-phase-values)', varBorder: 'color-mix(in srgb, var(--bd-phase-values) 25%, transparent)', varBg: 'var(--bd-phase-values-dim, color-mix(in srgb, var(--bd-phase-values) 8%, transparent))' },
  strengths: { varColor: 'var(--bd-phase-strengths)', varBorder: 'color-mix(in srgb, var(--bd-phase-strengths) 25%, transparent)', varBg: 'var(--bd-phase-strengths-dim, color-mix(in srgb, var(--bd-phase-strengths) 8%, transparent))' },
  interests: { varColor: 'var(--bd-phase-interests)', varBorder: 'color-mix(in srgb, var(--bd-phase-interests) 25%, transparent)', varBg: 'var(--bd-phase-interests-dim, color-mix(in srgb, var(--bd-phase-interests) 8%, transparent))' },
  purpose: { varColor: 'var(--bd-phase-purpose)', varBorder: 'color-mix(in srgb, var(--bd-phase-purpose) 25%, transparent)', varBg: 'var(--bd-phase-purpose-dim, color-mix(in srgb, var(--bd-phase-purpose) 8%, transparent))' },
};

/* 向内寻找答案：带「规划」/「发现」动画的独立区块 */
function InwardLookingBlock({ t }: { t: (p: string) => string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      className="text-center mb-14 space-y-4"
    >
      <p className="text-xs tracking-widest uppercase" style={{ color: 'var(--bd-fg-subtle)' }}>{t('home.dimensionsTitle')}</p>
      <h2 className="text-3xl md:text-4xl font-bold" style={{ color: 'var(--bd-fg)' }}>{t('home.dimensionsHeading')}</h2>
      <p className="text-base max-w-lg mx-auto leading-relaxed" style={{ color: 'var(--bd-fg-muted)' }}>
        {t('home.dimensionsDescBefore')}
        <span className="bd-word-planned">{t('home.dimensionsDescPlanned')}</span>
        {t('home.dimensionsDescMid')}
        <span className="bd-word-discover">{t('home.dimensionsDescDiscover')}</span>
        {t('home.dimensionsDescAfter')}
      </p>
      <p className="text-base max-w-lg mx-auto leading-relaxed" style={{ color: 'var(--bd-fg-muted)' }}>
        {t('home.dimensionsDescLine2')}
      </p>
    </motion.div>
  );
}

function DimensionsSection({ t }: { t: (p: string) => string }) {
  return (
    <section className="max-w-4xl mx-auto px-6 py-20 space-y-6">
      <InwardLookingBlock t={t} />
      <div className="space-y-4">
        {DIMENSION_KEYS.map((key, i) => {
          const vars = DIMENSION_VARS[key];
          return (
            <motion.div
              key={key}
              initial={{ opacity: 0, x: i % 2 === 0 ? -24 : 24 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.5, delay: i * 0.07 }}
              className="bd-eff-card rounded-2xl p-6 md:p-8 flex flex-col md:flex-row md:items-start gap-5"
              style={{
                background: vars.varBg,
                border: `1px solid ${vars.varBorder}`,
              }}
            >
              <div className="flex-shrink-0 pt-0.5">
                <span className="text-4xl font-black" style={{ color: vars.varColor }}>{t(`dimensions.${key}.num`)}</span>
              </div>
              <div className="flex-1 space-y-2">
                <h3 className="text-xl font-bold" style={{ color: vars.varColor }}>{t(`dimensions.${key}.name`)}</h3>
                <p className="text-sm leading-relaxed" style={{ color: 'var(--bd-fg-muted)' }}>{t(`dimensions.${key}.desc`)}</p>
                <p className="text-xs italic pt-1" style={{ color: 'var(--bd-fg-subtle)' }}>「{t(`dimensions.${key}.question`)}」</p>
              </div>
            </motion.div>
          );
        })}
      </div>
    </section>
  );
}

// ── 即将上线轮播（职业双轨 / 光谱共振 / 静室之我）──
const COMING_SOON_ITEMS = [
  {
    title: '职业双轨',
    desc: '职业不是人生的全部，但可以是人生最重要的表达。我们正在构建一套工具，帮你同时规划职业成就路径与人生意义路径。',
  },
  {
    title: '光谱共振',
    desc: '匹配与你四个维度相似或互补的伙伴，在共振中看见彼此、共创可能。',
  },
  {
    title: '静室之我',
    desc: '属于你自己的读书与思考空间。可随时记录、可空闲沉淀，亦可匿名分享给有缘人。',
  },
];

function ComingSoonCarousel() {
  const [activeIndex, setActiveIndex] = useState(0);
  const item = COMING_SOON_ITEMS[activeIndex];

  return (
    <section className="max-w-4xl mx-auto px-6 py-16 pb-28">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        className="bd-eff-card rounded-3xl p-10 md:p-14 text-center space-y-5"
        style={{
          border: '1px solid var(--bd-border-soft)',
          background: 'var(--bd-bg-card-alt)',
        }}
      >
        <p className="text-xs tracking-widest uppercase" style={{ color: 'var(--bd-fg-subtle)' }}>即将上线</p>
        <AnimatePresence mode="wait">
          <motion.div
            key={activeIndex}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.35 }}
            className="space-y-4"
          >
            <h2 className="text-2xl md:text-3xl font-bold" style={{ color: 'var(--bd-fg)' }}>{item.title}</h2>
            <p className="text-sm max-w-md mx-auto leading-relaxed" style={{ color: 'var(--bd-fg-muted)' }}>
              {item.desc}
            </p>
          </motion.div>
        </AnimatePresence>
        <div
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full text-xs"
          style={{
            border: '1px solid var(--bd-border-soft)',
            color: 'var(--bd-fg-subtle)',
          }}
        >
          <span
            className="w-1.5 h-1.5 rounded-full animate-pulse"
            style={{ background: 'var(--bd-accent-3)' }}
          />
          开发中
        </div>
        <div className="flex justify-center gap-2 pt-2">
          {COMING_SOON_ITEMS.map((_, i) => (
            <button
              key={i}
              type="button"
              onClick={() => setActiveIndex(i)}
              className="w-2 h-2 rounded-full transition-all"
              style={{
                background: i === activeIndex ? 'var(--bd-ui-accent)' : 'var(--bd-fg-subtle)',
                opacity: i === activeIndex ? 1 : 0.5,
                transform: i === activeIndex ? 'scale(1.2)' : 'scale(1)',
              }}
              aria-label={`切换到${COMING_SOON_ITEMS[i].title}`}
            />
          ))}
        </div>
      </motion.div>
    </section>
  );
}

// 浅色：水彩撞色（2~3 色）
function watercolorBg(colors: [string, string, string?]) {
  const [a, b, c] = colors;
  return `
    radial-gradient(ellipse 80% 60% at 15% 85%, rgba(${a}, 0.14) 0%, transparent 55%),
    radial-gradient(ellipse 70% 50% at 85% 15%, rgba(${b}, 0.10) 0%, transparent 50%),
    ${c ? `radial-gradient(ellipse 60% 70% at 50% 50%, rgba(${c}, 0.06) 0%, transparent 60%),` : ''}
    linear-gradient(135deg, rgba(${a}, 0.08) 0%, transparent 40%),
    linear-gradient(225deg, rgba(${b}, 0.06) 0%, transparent 35%),
    linear-gradient(to bottom, rgba(255,252,248,0.96), rgba(250,248,245,0.93))
  `;
}

// 深色：流光/荧光底
function darkGlowBg(colors: [string, string, string?]) {
  const [a] = colors;
  return `
    radial-gradient(ellipse 90% 70% at 50% 100%, rgba(${a}, 0.15) 0%, transparent 55%),
    linear-gradient(180deg, rgba(15,23,42,0.6) 0%, rgba(2,8,23,0.85) 100%)
  `;
}

function TestimonialCarousel() {
  const router = useRouter();
  const { t } = useLocale();
  const { themeId } = useThemeStore();
  const isDark = DARK_THEMES.includes(themeId);
  const TOTAL = TESTIMONIALS.length + 2; // CTA左 + 6条故事 + CTA右
  const [activeIndex, setActiveIndex] = useState(0);
  const [direction, setDirection] = useState(0);
  const isCtaLeft = activeIndex === 0;
  const isCtaRight = activeIndex === TOTAL - 1;
  const isCta = isCtaLeft || isCtaRight;
  const currentColor = isCta ? '124, 92, 252' : TESTIMONIALS[activeIndex - 1]?.color ?? '124, 92, 252';
  const canPrev = activeIndex > 0;
  const canNext = activeIndex < TOTAL - 1;

  const goPrev = () => {
    if (!canPrev) return;
    setDirection(-1);
    setActiveIndex((i) => i - 1);
  };
  const goNext = () => {
    if (!canNext) return;
    setDirection(1);
    setActiveIndex((i) => i + 1);
  };

  const goToExplore = () => router.push('/explore/intro');

  return (
    <section
      className="relative min-h-[70vh] flex flex-col justify-center overflow-hidden transition-colors duration-700"
      style={{
        background: `linear-gradient(to bottom,
          color-mix(in srgb, rgba(${currentColor}, 0.06) 30%, var(--bd-bg)),
          color-mix(in srgb, rgba(${currentColor}, 0.04) 20%, var(--bd-bg-mid)),
          color-mix(in srgb, rgba(${currentColor}, 0.05) 25%, var(--bd-bg-end))
        )`,
      }}
    >
      <p
        className="absolute top-8 left-0 right-0 text-center text-xs tracking-[0.2em] uppercase transition-opacity duration-500"
        style={{ color: 'var(--bd-fg-subtle)' }}
      >
        {t('home.theirStories')}
      </p>

      {/* 换页按钮：左右两侧 */}
      {canPrev && (
        <button
          type="button"
          onClick={goPrev}
          className="absolute left-4 md:left-8 top-1/2 -translate-y-1/2 z-20 w-12 h-12 rounded-full flex items-center justify-center transition-all duration-300 hover:scale-110 opacity-70 hover:opacity-100"
          style={{
            background: isDark ? 'rgba(30,41,59,0.9)' : 'rgba(255,255,255,0.9)',
            boxShadow: isDark ? '0 4px 20px rgba(0,0,0,0.3)' : '0 4px 20px rgba(0,0,0,0.08)',
            color: `rgb(${currentColor})`,
          }}
          aria-label="上一条"
        >
          <ChevronLeft size={24} strokeWidth={2} />
        </button>
      )}
      {canNext && (
        <button
          type="button"
          onClick={goNext}
          className="absolute right-4 md:right-8 top-1/2 -translate-y-1/2 z-20 w-12 h-12 rounded-full flex items-center justify-center transition-all duration-300 hover:scale-110 opacity-70 hover:opacity-100"
          style={{
            background: isDark ? 'rgba(30,41,59,0.9)' : 'rgba(255,255,255,0.9)',
            boxShadow: isDark ? '0 4px 20px rgba(0,0,0,0.3)' : '0 4px 20px rgba(0,0,0,0.08)',
            color: `rgb(${currentColor})`,
          }}
          aria-label="下一条"
        >
          <ChevronRight size={24} strokeWidth={2} />
        </button>
      )}

      {/* 大卡片：铺满左右 */}
      <div className="w-full max-w-4xl mx-auto px-6 md:px-12 py-16">
        <AnimatePresence mode="wait">
          {isCta ? (
            <motion.button
              key={`cta-${activeIndex}`}
              type="button"
              onClick={goToExplore}
              initial={{ opacity: 0, x: direction > 0 ? 60 : -60 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: direction > 0 ? -60 : 60 }}
              transition={{ duration: 0.45, ease: [0.25, 0.1, 0.25, 1] }}
              className={`w-full rounded-2xl md:rounded-3xl p-8 md:p-12 lg:p-16 relative overflow-hidden text-left transition-transform hover:scale-[1.01] active:scale-[0.99] ${isDark ? 'testimonial-cta-dark' : ''}`}
              style={{
                background: isDark ? darkGlowBg(EXPLORE_CTA_COLORS) : watercolorBg(EXPLORE_CTA_COLORS),
                border: isDark ? '1px solid rgba(124,92,252,0.25)' : '1px solid rgba(124,92,252,0.12)',
                boxShadow: isDark ? undefined : '0 8px 40px rgba(124,92,252,0.08), 0 2px 12px rgba(0,0,0,0.03), inset 0 1px 0 rgba(255,255,255,0.7)',
              }}
            >
              <div
                className="absolute inset-0 rounded-2xl md:rounded-3xl pointer-events-none opacity-30"
                style={{
                  backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.5'/%3E%3C/svg%3E")`,
                  backgroundSize: '150px',
                }}
                aria-hidden
              />
              <div className="relative z-10">
                <h3 className="text-2xl md:text-3xl font-bold" style={{ color: 'var(--bd-ui-accent)' }}>
                  {t('home.exploreYourStory')}
                </h3>
                <p className="mt-3 text-sm md:text-base" style={{ color: 'var(--bd-fg-muted)' }}>
                  {t('home.exploreYourStorySub')}
                </p>
                <span className="inline-block mt-6 text-sm font-medium" style={{ color: 'var(--bd-ui-accent)' }}>
                  {t('home.exploreCta')}
                </span>
              </div>
            </motion.button>
          ) : (
            <motion.div
              key={activeIndex}
              initial={{ opacity: 0, x: direction > 0 ? 60 : -60 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: direction > 0 ? -60 : 60 }}
              transition={{ duration: 0.45, ease: [0.25, 0.1, 0.25, 1] }}
              className={`w-full rounded-2xl md:rounded-3xl p-8 md:p-12 lg:p-16 relative overflow-hidden ${isDark ? 'testimonial-card-dark' : ''}`}
              style={{
                background: isDark ? darkGlowBg(TESTIMONIALS[activeIndex - 1].colors) : watercolorBg(TESTIMONIALS[activeIndex - 1].colors),
                border: isDark ? '1px solid rgba(255,255,255,0.06)' : '1px solid rgba(0,0,0,0.05)',
                boxShadow: isDark ? undefined : '0 8px 40px rgba(0,0,0,0.06), 0 2px 12px rgba(0,0,0,0.03), inset 0 1px 0 rgba(255,255,255,0.7)',
                ['--tc-r' as string]: TESTIMONIALS[activeIndex - 1].color.split(',')[0]?.trim(),
                ['--tc-g' as string]: TESTIMONIALS[activeIndex - 1].color.split(',')[1]?.trim(),
                ['--tc-b' as string]: TESTIMONIALS[activeIndex - 1].color.split(',')[2]?.trim(),
              }}
            >
              <div
                className="absolute inset-0 rounded-2xl md:rounded-3xl pointer-events-none opacity-30"
                style={{
                  backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.5'/%3E%3C/svg%3E")`,
                  backgroundSize: '150px',
                }}
                aria-hidden
              />
              <blockquote className="relative z-10 text-lg md:text-xl lg:text-2xl leading-relaxed md:leading-loose font-serif" style={{ color: 'var(--bd-fg)' }}>
                「{TESTIMONIALS[activeIndex - 1].quote}」
              </blockquote>
              <div className="relative z-10 mt-8 flex items-baseline gap-3">
                <p className="text-base font-semibold" style={{ color: 'var(--bd-fg)' }}>{TESTIMONIALS[activeIndex - 1].name}</p>
                <span className="text-sm" style={{ color: 'var(--bd-fg-subtle)' }}>{TESTIMONIALS[activeIndex - 1].role}</span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* 页码指示 */}
      <div className="absolute bottom-8 left-0 right-0 flex justify-center gap-2">
        {Array.from({ length: TOTAL }).map((_, i) => (
          <button
            key={i}
            type="button"
            onClick={() => {
              setDirection(i > activeIndex ? 1 : -1);
              setActiveIndex(i);
            }}
            className="w-2 h-2 rounded-full transition-all duration-300"
            style={{
              background: i === activeIndex ? `rgb(${currentColor})` : 'var(--bd-fg-subtle)',
              opacity: i === activeIndex ? 1 : 0.4,
              transform: i === activeIndex ? 'scale(1.3)' : 'scale(1)',
            }}
            aria-label={i === 0 || i === TOTAL - 1 ? '探索你的故事' : `第${i}条`}
          />
        ))}
      </div>
    </section>
  );
}

// ── 主页面 ──────────────────────────────────────────────────
export default function LandingPage() {
  const router = useRouter();
  const { t } = useLocale();

  return (
    <div
      className="min-h-screen overflow-x-hidden"
      style={{ background: 'linear-gradient(to bottom, var(--bd-bg), var(--bd-bg-mid), var(--bd-bg-end))' }}
    >

      {/* ① Hero */}
      <section className="flex flex-col items-center justify-center text-center px-6 pt-28 pb-20 min-h-[90vh]">
        <motion.h1
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7 }}
          className="text-5xl md:text-7xl font-bold leading-tight mb-6"
          style={{ color: 'var(--bd-fg)' }}
        >
          {t('home.heroTitle')}
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="text-xl md:text-2xl lg:text-3xl leading-relaxed mb-8"
        >
          <span className="bd-hero-slogan">{t('home.heroSlogan')}</span>
        </motion.p>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="text-lg md:text-xl mb-1.5 leading-relaxed"
          style={{ color: 'var(--bd-fg-muted)' }}
        >
          {t('home.heroP1')}
        </motion.p>
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.28 }}
          className="text-lg md:text-xl mb-1.5 leading-relaxed"
          style={{ color: 'var(--bd-fg-muted)' }}
        >
          {t('home.heroP2')}
        </motion.p>
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.36 }}
          className="text-lg md:text-xl mb-10 leading-relaxed font-semibold"
          style={{ color: 'var(--bd-fg)' }}
        >
          {t('home.heroP3')}
        </motion.p>

        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.5 }}
        >
          <button
            type="button"
            onClick={() => router.push('/explore/intro')}
            className="px-10 py-4 rounded-xl font-semibold text-lg transition-all text-bd-ui-accent-fg hover:opacity-90"
            style={{ background: 'var(--bd-ui-accent)' }}
          >
            {t('common.startExploreArrow')}
          </button>
        </motion.div>
      </section>

      {/* ② 四个维度 */}
      <DimensionsSection t={t} />

      {/* ③ 即将上线（职业双轨 / 光谱共振 / 静室之我） */}
      <ComingSoonCarousel />

      {/* ④ 他们的故事：全幅沉浸式换页 */}
      <TestimonialCarousel />

    </div>
  );
}
