'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronLeft, ChevronRight, Sparkles, Star } from 'lucide-react';
import { useLocale } from '@/hooks/useLocale';
// ── 用户故事（9 条，3x3 平铺，头像占位 assets/user_story/）──────────────────────────
const TESTIMONIALS: Array<{
  quote: string;
  name: string;
  role: string;
  avatar: string; // 占位，后续在 public/assets/user_story/ 放入图片后改为 /assets/user_story/1.jpg 等
  color: string;
}> = [
  { quote: '我第一次意识到，我一直在做别人期待的事，而不是我认为重要的事。这个过程让我看清了自己。', name: '小林', role: '产品经理', avatar: '', color: '129, 140, 248' },
  { quote: '原来沟通协调这件事对我来说真的是禀赋，不是习惯。这个区分让我第一次觉得自己有竞争力。', name: 'Maggie', role: '市场运营', avatar: '', color: '251, 113, 133' },
  { quote: '帮助别人成长这件事，让我忘我。我以为那只是爱好，没想到可以成为职业核心。', name: '阿文', role: '应届生', avatar: '', color: '251, 191, 36' },
  { quote: '使命感这个词以前对我太虚了。但当我说出「我想帮普通人做出好决策」的时候，我哭了。', name: '晓敏', role: '咨询顾问', avatar: '', color: '52, 211, 153' },
  { quote: '以为自己什么都喜欢，其实是什么都没认真想过。四个维度逼着我去想清楚，很有价值。', name: '老K', role: '创业者', avatar: '', color: '34, 211, 238' },
  { quote: '第一次做完就哭了，太多东西压在心里没被看见。这是一份给自己的礼物。', name: '苏苏', role: '教师', avatar: '', color: '244, 114, 182' },
  { quote: '以前觉得职业规划是套路，但这里的对话让我真正在思考「我」是谁。', name: '浩然', role: '程序员', avatar: '', color: '129, 140, 248' },
  { quote: '热忱那一关，我写了五件小事。没想到它们可以串成一条清晰的线。', name: '小雨', role: '设计师', avatar: '', color: '251, 191, 36' },
  { quote: '和伴侣一起做完探索，才发现我们原来有这么多共振点。', name: '阿杰', role: '创业合伙人', avatar: '', color: '52, 211, 153' },
];

// ── 四个核心维度（配色：信念=蓝/禀赋=绿/热忱=红/使命=黄，文案来自 i18n）──
const DIMENSION_KEYS = ['values', 'strengths', 'interests', 'purpose'] as const;
const DIMENSION_VARS: Record<(typeof DIMENSION_KEYS)[number], { varColor: string; varBorder: string; varBg: string }> = {
  values: { varColor: 'var(--bd-phase-values)', varBorder: 'color-mix(in srgb, var(--bd-phase-values) 25%, transparent)', varBg: 'var(--bd-phase-values-dim, color-mix(in srgb, var(--bd-phase-values) 8%, transparent))' },
  strengths: { varColor: 'var(--bd-phase-strengths)', varBorder: 'color-mix(in srgb, var(--bd-phase-strengths) 25%, transparent)', varBg: 'var(--bd-phase-strengths-dim, color-mix(in srgb, var(--bd-phase-strengths) 8%, transparent))' },
  interests: { varColor: 'var(--bd-phase-interests)', varBorder: 'color-mix(in srgb, var(--bd-phase-interests) 25%, transparent)', varBg: 'var(--bd-phase-interests-dim, color-mix(in srgb, var(--bd-phase-interests) 8%, transparent))' },
  purpose: { varColor: 'var(--bd-phase-purpose)', varBorder: 'color-mix(in srgb, var(--bd-phase-purpose) 25%, transparent)', varBg: 'var(--bd-phase-purpose-dim, color-mix(in srgb, var(--bd-phase-purpose) 8%, transparent))' },
};

/* 运行时绘制连接弧线（与 new-report-finall 一致） */
function useBuildArcs(zoneRef: React.RefObject<HTMLDivElement | null>, svgRef: React.RefObject<SVGSVGElement | null>) {
  const build = useCallback(() => {
    const zone = zoneRef.current;
    const svg = svgRef.current;
    const cards = document.querySelectorAll('.bd-dimension-card');
    if (!zone || !svg || cards.length !== 4) return;

    const zoneRect = zone.getBoundingClientRect();
    if (zoneRect.height < 50) return; // 移动端隐藏连接区时跳过
    const r = 8;
    const arcH = 60;
    const centerX = zoneRect.width / 2;

    svg.innerHTML = '';
    cards.forEach((card, i) => {
      const cardRect = card.getBoundingClientRect();
      const cx = cardRect.left + cardRect.width / 2 - zoneRect.left;
      const startY = 30;
      const turnY = arcH;

      let d: string;
      if (cx < centerX) {
        const endX = Math.min(cx + 50, centerX - 10);
        d = `M ${cx} ${startY} L ${cx} ${turnY - r} A ${r} ${r} 0 0 0 ${cx + r} ${turnY} L ${endX} ${turnY}`;
      } else {
        const endX = Math.max(cx - 50, centerX + 10);
        d = `M ${cx} ${startY} L ${cx} ${turnY - r} A ${r} ${r} 0 0 1 ${cx - r} ${turnY} L ${endX} ${turnY}`;
      }

      const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      path.setAttribute('d', d);
      path.classList.add('bd-arc-path');
      const delays = [0, 0.15, 0.15, 0];
      (path as SVGPathElement).style.animationDelay = `${delays[i]}s`;
      svg.appendChild(path);
    });
  }, [zoneRef, svgRef]);

  useEffect(() => {
    build();
    window.addEventListener('resize', build);
    const t = setTimeout(build, 100);
    return () => {
      window.removeEventListener('resize', build);
      clearTimeout(t);
    };
  }, [build]);
}

function DimensionsSection({ t }: { t: (p: string) => string; locale: string }) {
  const router = useRouter();
  const zoneRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  useBuildArcs(zoneRef, svgRef);

  return (
    <section className="max-w-5xl mx-auto px-6 pt-8 pb-0 w-full">
      {/* 四卡片区（new-report 以卡片为基准，我们上方有 Hero 故加 pt-8 增加相对留白） */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        {DIMENSION_KEYS.map((key) => {
          const vars = DIMENSION_VARS[key];
          return (
            <div
              key={key}
              className={`bd-dimension-card bd-dim-${key} px-6 py-8 flex flex-col text-left min-h-[200px] lg:min-h-[220px] cursor-default`}
            >
              <p className="text-[13px] font-medium mb-3" style={{ color: '#8892a0', fontFamily: 'var(--font-sans-en)' }}>
                {t(`dimensions.${key}.step`)}
              </p>
              <h3 className="text-xl font-semibold mb-4 bd-dim-card-title">{t(`dimensions.${key}.name`)}</h3>
              <p className="bd-dim-desc text-sm leading-relaxed flex-1" style={{ color: '#606972' }}>{t(`dimensions.${key}.desc`)}</p>
            </div>
          );
        })}
      </div>

      {/* 连接区域：呼吸弧线 + 垂直白光（260px，与 new-report 一致；移动端隐藏） */}
      <div ref={zoneRef} className="bd-connection-zone w-full hidden lg:block shrink-0" aria-hidden>
        <svg ref={svgRef} className="bd-arc-svg" preserveAspectRatio="none" />
        <div className="bd-v-final" />
      </div>

      {/* 结果卡片：与 new-report-finall 内容完全一致 */}
      <section className="w-full max-w-[800px] mx-auto mt-8 lg:mt-0 mb-20 relative z-10">
        <motion.div
          initial={false}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, ease: [0.165, 0.84, 0.44, 1] }}
          className="bd-report-glass-card"
        >
          <h2 className="bd-report-title">{t('home.reportTitle')}</h2>
          <p className="bd-report-subtitle">
            {t('home.reportSubtitleLine1')}<br />
            {t('home.reportSubtitleLine2')}
          </p>
          <button
            type="button"
            onClick={() => router.push('/explore/intro')}
            className="bd-btn-start"
          >
            {t('home.reportCta')}
            <span className="bd-btn-icon-core">→</span>
          </button>
        </motion.div>
      </section>
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

function ComingSoonFlat() {
  const { t } = useLocale();

  return (
    <section className="relative z-10 max-w-4xl mx-auto px-5 py-20">
      <div className="text-center mb-16">
        <motion.div
          initial={false}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="inline-flex items-center gap-2 bg-purple-100/60 dark:bg-purple-500/20 backdrop-blur-md text-purple-700 dark:text-purple-300 px-5 py-2 rounded-full mb-6"
        >
          <Sparkles className="h-4 w-4" />
          <span className="text-sm">{t('home.comingSoonBadge')}</span>
        </motion.div>
        <motion.h2
          initial={false}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-5xl font-semibold mb-4 tracking-[0.05em]"
          style={{ color: 'var(--bd-fg)' }}
        >
          {t('home.comingSoonTitle')}
        </motion.h2>
        <motion.p
          initial={false}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-xl font-light"
          style={{ color: 'var(--bd-fg-muted)' }}
        >
          {t('home.comingSoonSubtitle')}
        </motion.p>
      </div>
      <div className="grid md:grid-cols-3 gap-6">
        {COMING_SOON_ITEMS.map((item, i) => (
          <motion.div
            key={i}
            initial={false}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.1 }}
            className="bg-white/60 dark:bg-white/10 backdrop-blur-[24px] border border-white/90 dark:border-white/20 rounded-3xl p-8 shadow-[0_20px_40px_-10px_rgba(0,0,0,0.03)] transition-all duration-500 hover:-translate-y-2 hover:shadow-[0_30px_60px_-15px_rgba(0,0,0,0.08)] hover:bg-white/85 dark:hover:bg-white/15"
          >
            <h3 className="text-xl font-medium mb-3" style={{ color: 'var(--bd-fg)' }}>{item.title}</h3>
            <p className="text-sm leading-relaxed font-light" style={{ color: 'var(--bd-fg-muted)' }}>{item.desc}</p>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

const STORIES_PER_PAGE = 3;
const TOTAL_PAGES = Math.ceil(TESTIMONIALS.length / STORIES_PER_PAGE);
const HERO_VIDEO_SRC = process.env.NEXT_PUBLIC_HOME_HERO_VIDEO_SRC ?? '';
const STORIES_VIDEO_SRC = process.env.NEXT_PUBLIC_HOME_STORIES_VIDEO_SRC ?? '';

function TestimonialGrid({ videoSrc }: { videoSrc?: string }) {
  const { t } = useLocale();
  const [page, setPage] = useState(0);

  const start = page * STORIES_PER_PAGE;
  const visible = TESTIMONIALS.slice(start, start + STORIES_PER_PAGE);
  const canPrev = page > 0;
  const canNext = page < TOTAL_PAGES - 1;

  return (
    <section className="relative z-10 w-full px-5 py-20">
      {videoSrc ? (
        <div className="absolute inset-0 -z-10 pointer-events-none overflow-hidden">
          <video
            className="w-full h-full object-cover opacity-20"
            src={videoSrc}
            autoPlay
            loop
            muted
            playsInline
            preload="metadata"
            aria-hidden
          />
        </div>
      ) : null}
      <div className="text-center mb-16 max-w-4xl mx-auto">
        <motion.h2
          initial={false}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-5xl font-semibold mb-4 tracking-[0.05em]"
          style={{ color: 'var(--bd-fg)' }}
        >
          {t('home.theirStories')}
        </motion.h2>
        <motion.p
          initial={false}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="text-xl font-light"
          style={{ color: 'var(--bd-fg-muted)' }}
        >
          {t('home.testimonialsSubtitle')}
        </motion.p>
      </div>

      <div className="relative max-w-6xl mx-auto">
        {canPrev && (
          <button
            type="button"
            onClick={() => setPage((p) => p - 1)}
            className="absolute left-0 top-1/2 -translate-y-1/2 -translate-x-4 lg:-translate-x-12 z-20 bg-white/90 dark:bg-white/10 backdrop-blur-md hover:bg-white dark:hover:bg-white/20 border border-black/10 dark:border-white/20 rounded-full p-3 shadow-lg transition-all hover:scale-110"
            style={{ color: 'var(--bd-fg)' }}
            aria-label="上一页"
          >
            <ChevronLeft className="h-6 w-6" />
          </button>
        )}

        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={page}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            transition={{ duration: 0.35, ease: [0.165, 0.84, 0.44, 1] }}
            className="grid grid-cols-1 md:grid-cols-3 gap-6 px-4"
          >
            {visible.map((item, i) => (
              <div key={start + i} className="h-full">
                <div className="bd-testimonial-card px-6 py-8 min-h-[220px] h-full">
                  {/* 顶部：头像+姓名职业 ｜ 评分 */}
                  <div className="flex items-start justify-between gap-4 mb-6">
                    <div className="flex items-center gap-3 min-w-0">
                      {item.avatar ? (
                        <img src={item.avatar} alt="" className="w-11 h-11 rounded-full object-cover flex-shrink-0" />
                      ) : (
                        <div
                          className="w-11 h-11 rounded-full flex items-center justify-center text-base font-semibold flex-shrink-0"
                          style={{ background: `rgba(${item.color}, 0.2)`, color: `rgb(${item.color})` }}
                        >
                          {item.name.slice(0, 1)}
                        </div>
                      )}
                      <div className="min-w-0">
                        <div className="font-semibold text-[15px] truncate" style={{ color: 'var(--bd-fg)' }}>{item.name}</div>
                        <div className="text-xs truncate" style={{ color: 'var(--bd-fg-muted)' }}>{item.role}</div>
                      </div>
                    </div>
                    <div className="flex gap-0.5 flex-shrink-0" aria-label="5 星">
                      {[1, 2, 3, 4, 5].map((j) => (
                        <Star key={j} className="h-4 w-4 fill-amber-400 text-amber-400" />
                      ))}
                    </div>
                  </div>
                  {/* 下方：评价正文（黑色字体） */}
                  <p className="bd-testimonial-quote text-sm leading-[1.75] font-normal">
                    {item.quote}
                  </p>
                </div>
              </div>
            ))}
          </motion.div>
        </AnimatePresence>

        {canNext && (
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            className="absolute right-0 top-1/2 -translate-y-1/2 translate-x-4 lg:translate-x-12 z-20 bg-white/90 dark:bg-white/10 backdrop-blur-md hover:bg-white dark:hover:bg-white/20 border border-black/10 dark:border-white/20 rounded-full p-3 shadow-lg transition-all hover:scale-110"
            style={{ color: 'var(--bd-fg)' }}
            aria-label="下一页"
          >
            <ChevronRight className="h-6 w-6" />
          </button>
        )}
      </div>

      <div className="flex justify-center gap-2 mt-8">
        {Array.from({ length: TOTAL_PAGES }).map((_, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => setPage(idx)}
            className={`h-2 rounded-full transition-all ${
              page === idx
                ? 'bg-neutral-800 dark:bg-neutral-300 w-8'
                : 'bg-gray-300 dark:bg-gray-600 hover:bg-gray-400 dark:hover:bg-gray-500 w-2'
            }`}
            aria-label={`第${idx + 1}页`}
          />
        ))}
      </div>
    </section>
  );
}

// ── 页脚 ──────────────────────────────────────────────────
function LandingFooter() {
  const { t } = useLocale();
  const year = new Date().getFullYear();
  const copyright = t('footer.copyright').replace('{year}', String(year));
  const links = [
    { label: t('footer.aboutUs'), href: '/about' },
    { label: t('footer.contactUs'), href: '/contact' },
    { label: t('footer.privacyPolicy'), href: '/privacy' },
    { label: t('footer.termsOfService'), href: '/terms' },
  ];

  return (
    <footer className="border-t border-black/5 dark:border-white/10 mt-8">
      <div className="max-w-5xl mx-auto px-6 py-12">
        <div className="flex flex-col md:flex-row items-center justify-between gap-8">
          <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2">
            {links.map(({ label, href }) => (
              <Link
                key={href}
                href={href}
                className="text-sm hover:underline transition-colors"
                style={{ color: 'var(--bd-fg-muted)' }}
              >
                {label}
              </Link>
            ))}
          </div>
          {/* 二维码占位：后续可替换为真实 QR 图 */}
          <div className="flex flex-col items-center gap-2">
            <div
              className="w-24 h-24 rounded-lg flex items-center justify-center text-xs"
              style={{
                background: 'linear-gradient(135deg, rgba(124,92,252,0.15), rgba(167,139,250,0.1))',
                border: '1px dashed rgba(124,92,252,0.3)',
                color: 'var(--bd-fg-subtle)',
              }}
            >
              QR
            </div>
            <span className="text-xs" style={{ color: 'var(--bd-fg-subtle)' }}>{t('footer.qrCode')}</span>
          </div>
        </div>
        <p className="text-center text-xs mt-8" style={{ color: 'var(--bd-fg-subtle)' }}>
          {copyright}
        </p>
      </div>
    </footer>
  );
}

// ── 主页面 ──────────────────────────────────────────────────
export default function LandingPage() {
  const router = useRouter();
  const { t, locale } = useLocale();

  // 首页时覆盖布局背景为 #faf9f8，与 background4 一致
  useEffect(() => {
    document.documentElement.setAttribute('data-landing', 'true');
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const lowCore = typeof navigator.hardwareConcurrency === 'number' && navigator.hardwareConcurrency <= 4;
    const lowMemory = typeof (navigator as Navigator & { deviceMemory?: number }).deviceMemory === 'number'
      && ((navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 0) <= 4;
    if (reduceMotion || lowCore || lowMemory) {
      document.documentElement.setAttribute('data-landing-lite', 'true');
    } else {
      document.documentElement.removeAttribute('data-landing-lite');
    }
    return () => {
      document.documentElement.removeAttribute('data-landing');
      document.documentElement.removeAttribute('data-landing-lite');
    };
  }, []);

  return (
    <div className="landing-mesh-wrap">
      {/* 动态背景：光谱扫射 prism（参考 background4） */}
      <div className="landing-mesh-bg">
        <div className="landing-mesh-prism" aria-hidden />
      </div>
      <div className="landing-mesh-noise" aria-hidden />
      {/* 与 background4 一致：内容层无遮罩，mesh 直接透过 */}
      <div className="landing-mesh-content min-h-screen">

      {/* ① Hero */}
      <section className="relative flex flex-col items-center justify-center text-center px-6 pt-20 md:pt-24 pb-12 md:pb-10 min-h-[52vh] md:min-h-[55vh]">
        {HERO_VIDEO_SRC ? (
          <div className="absolute inset-0 -z-10 pointer-events-none overflow-hidden">
            <video
              className="w-full h-full object-cover opacity-30"
              src={HERO_VIDEO_SRC}
              autoPlay
              loop
              muted
              playsInline
              preload="metadata"
              aria-hidden
            />
          </div>
        ) : null}
        <motion.h1
          initial={false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7 }}
          className="text-3xl sm:text-5xl md:text-7xl font-bold leading-tight mb-6 tracking-[0.05em]"
          style={{ color: 'var(--bd-fg)', fontFamily: 'var(--font-sans-cn)' }}
        >
          {t('home.heroTitle')}
        </motion.h1>

        <motion.p
          initial={false}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.1 }}
          className="bd-hero-slogan leading-relaxed mb-10"
          style={{ fontFamily: 'var(--font-sans-cn)' }}
        >
          {t('home.heroSlogan')}
        </motion.p>

        <motion.div
          initial={false}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.5 }}
        >
          <button
            type="button"
            onClick={() => router.push('/explore/intro')}
            className="bd-btn-hero px-10 py-4 rounded-[30px] font-semibold text-lg text-white inline-flex items-center gap-2"
            style={{ background: '#1d1d1f' }}
          >
            {t('common.startExplore')}
            <span className="bd-btn-hero-arrow">→</span>
          </button>
        </motion.div>
      </section>

      {/* ② 四个维度 */}
      <DimensionsSection t={t} locale={locale} />

      {/* ③ 即将上线（职业双轨 / 光谱共振 / 静室之我） */}
      <ComingSoonFlat />

      {/* ④ 他们的故事：3×3 平铺 */}
      <TestimonialGrid videoSrc={STORIES_VIDEO_SRC || undefined} />

      {/* ⑤ 页脚 */}
      <LandingFooter />
    </div>
    </div>
  );
}
