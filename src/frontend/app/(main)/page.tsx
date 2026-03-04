'use client';

import { useRouter } from 'next/navigation';
import { motion } from 'framer-motion';

// ── 用户留言数据 ────────────────────────────────────────────
const TESTIMONIALS = [
  {
    quote: '我第一次意识到，我一直在做别人期待的事，而不是我认为重要的事。这个过程让我看清了自己。',
    name: '小林',
    role: '28岁 / 产品经理',
    accent: 'rgba(129,140,248,0.18)',
    accentBorder: 'rgba(129,140,248,0.25)',
  },
  {
    quote: '原来沟通协调这件事对我来说真的是禀赋，不是习惯。这个区分让我第一次觉得自己有竞争力。',
    name: 'Maggie',
    role: '32岁 / 市场运营',
    accent: 'rgba(251,113,133,0.15)',
    accentBorder: 'rgba(251,113,133,0.25)',
  },
  {
    quote: '帮助别人成长这件事，让我忘我。我以为那只是爱好，没想到可以成为职业核心。',
    name: '阿文',
    role: '25岁 / 应届生',
    accent: 'rgba(251,191,36,0.15)',
    accentBorder: 'rgba(251,191,36,0.25)',
  },
  {
    quote: '使命感这个词以前对我太虚了。但当我说出「我想帮普通人做出好决策」的时候，我哭了。',
    name: '晓敏',
    role: '35岁 / 咨询顾问',
    accent: 'rgba(52,211,153,0.15)',
    accentBorder: 'rgba(52,211,153,0.25)',
  },
  {
    quote: '以为自己什么都喜欢，其实是什么都没认真想过。四个维度逼着我去想清楚，很有价值。',
    name: '老K',
    role: '40岁 / 创业者',
    accent: 'rgba(34,211,238,0.15)',
    accentBorder: 'rgba(34,211,238,0.25)',
  },
  {
    quote: '第一次做完就哭了，太多东西压在心里没被看见。这是一份给自己的礼物。',
    name: '苏苏',
    role: '29岁 / 教师',
    accent: 'rgba(244,114,182,0.15)',
    accentBorder: 'rgba(244,114,182,0.25)',
  },
];

// ── 四个核心维度（与探索流程阶段配色一致：信念=蓝/禀赋=绿/热忱=红/使命=黄）──
const DIMENSIONS = [
  {
    num: '01',
    name: '信念',
    en: 'Values',
    desc: '你认为什么值得付出？哪些原则让你夜里安心、白天有力？价值观不是口号，是你做每一个选择时真正生效的标准。',
    question: '如果职业选择没有对错，你最在意什么？',
    varColor: 'var(--bd-phase-values)',
    varBorder: 'color-mix(in srgb, var(--bd-phase-values) 25%, transparent)',
    varBg: 'var(--bd-phase-values-dim, color-mix(in srgb, var(--bd-phase-values) 8%, transparent))',
  },
  {
    num: '02',
    name: '禀赋',
    en: 'Strengths',
    desc: '有些事你做起来不费力，却让别人惊叹。禀赋不只是技能，是那种「我天生就适合做这个」的自然感。',
    question: '做哪些事的时候，你觉得自己是游刃有余的？',
    varColor: 'var(--bd-phase-strengths)',
    varBorder: 'color-mix(in srgb, var(--bd-phase-strengths) 25%, transparent)',
    varBg: 'var(--bd-phase-strengths-dim, color-mix(in srgb, var(--bd-phase-strengths) 8%, transparent))',
  },
  {
    num: '03',
    name: '热忱',
    en: 'Interests',
    desc: '什么话题让你停不下来？什么场景让时间消失？热忱是驱动你在无人关注时仍然投入的内在燃料。',
    question: '你愿意在没有报酬的情况下，反复去做的事是什么？',
    varColor: 'var(--bd-phase-interests)',
    varBorder: 'color-mix(in srgb, var(--bd-phase-interests) 25%, transparent)',
    varBg: 'var(--bd-phase-interests-dim, color-mix(in srgb, var(--bd-phase-interests) 8%, transparent))',
  },
  {
    num: '04',
    name: '使命',
    en: 'Purpose',
    desc: '你想为谁而做？你希望在这个世界留下什么？使命把「我想做」变成「我必须做」，赋予职业真正的重量。',
    question: '什么事情，是你觉得如果不去做、会有遗憾的？',
    varColor: 'var(--bd-phase-purpose)',
    varBorder: 'color-mix(in srgb, var(--bd-phase-purpose) 25%, transparent)',
    varBg: 'var(--bd-phase-purpose-dim, color-mix(in srgb, var(--bd-phase-purpose) 8%, transparent))',
  },
];

// ── Marquee ─────────────────────────────────────────────────
function TestimonialMarquee() {
  const doubled = [...TESTIMONIALS, ...TESTIMONIALS];
  return (
    <div className="w-full overflow-hidden py-2 select-none">
      <motion.div
        className="flex gap-5"
        animate={{ x: ['0%', '-50%'] }}
        transition={{ duration: 44, ease: 'linear', repeat: Infinity }}
        style={{ width: 'max-content' }}
      >
        {doubled.map((t, i) => (
          <div
            key={i}
            className="w-72 flex-shrink-0 rounded-2xl p-5 space-y-3"
            style={{
              background: t.accent,
              border: `1px solid ${t.accentBorder}`,
            }}
          >
            <p className="text-sm leading-relaxed" style={{ color: 'var(--bd-fg)' }}>
              「{t.quote}」
            </p>
            <div>
              <p className="text-sm font-semibold" style={{ color: 'var(--bd-fg)' }}>{t.name}</p>
              <p className="text-xs" style={{ color: 'var(--bd-fg-subtle)' }}>{t.role}</p>
            </div>
          </div>
        ))}
      </motion.div>
    </div>
  );
}

// ── 主页面 ──────────────────────────────────────────────────
export default function LandingPage() {
  const router = useRouter();

  return (
    <div
      className="min-h-screen overflow-x-hidden"
      style={{ background: 'linear-gradient(to bottom, var(--bd-bg), var(--bd-bg-mid), var(--bd-bg-end))' }}
    >

      {/* ① Hero */}
      <section className="flex flex-col items-center justify-center text-center px-6 pt-28 pb-20 min-h-[90vh]">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7 }}
          className="mb-4 text-xs tracking-widest uppercase font-medium"
          style={{ color: 'var(--bd-primary)' }}
        >
          Being · Doing · Becoming
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.1 }}
          className="text-5xl md:text-7xl font-bold leading-tight mb-8"
          style={{ color: 'var(--bd-fg)' }}
        >
          每一种热爱，<br />
          <span
            className="text-transparent bg-clip-text"
            style={{
              backgroundImage: 'linear-gradient(to right, var(--bd-primary), var(--bd-accent-1), var(--bd-accent-2))',
            }}
          >
            都值得成为职业
          </span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="text-lg md:text-xl mb-1.5 leading-relaxed"
          style={{ color: 'var(--bd-fg-muted)' }}
        >
          人生有两条路需要走完：
        </motion.p>
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.28 }}
          className="text-lg md:text-xl mb-1.5 leading-relaxed"
          style={{ color: 'var(--bd-fg-muted)' }}
        >
          一条通向成就，一条通向意义。
        </motion.p>
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.36 }}
          className="text-lg md:text-xl mb-10 leading-relaxed font-semibold"
          style={{ color: 'var(--bd-fg)' }}
        >
          最幸运的人，走的是同一条。
        </motion.p>

        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.5 }}
        >
          <button
            type="button"
            onClick={() => router.push('/explore/intro')}
            className="px-10 py-4 rounded-xl font-semibold text-lg transition-all"
            style={{
              background: 'var(--bd-primary)',
              color: '#fff',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bd-primary-alt)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--bd-primary)')}
          >
            开始探索 →
          </button>
        </motion.div>
      </section>

      {/* ② 用户留言 */}
      <section className="py-16">
        <motion.p
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center text-xs tracking-widest uppercase mb-8"
          style={{ color: 'var(--bd-fg-subtle)' }}
        >
          他们的故事
        </motion.p>
        <TestimonialMarquee />
      </section>

      {/* ③ 四个维度 */}
      <section className="max-w-4xl mx-auto px-6 py-20 space-y-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-14 space-y-4"
        >
          <p className="text-xs tracking-widest uppercase" style={{ color: 'var(--bd-fg-subtle)' }}>探索维度</p>
          <h2 className="text-3xl md:text-4xl font-bold" style={{ color: 'var(--bd-fg)' }}>向内寻找答案</h2>
          <p className="text-base max-w-lg mx-auto leading-relaxed" style={{ color: 'var(--bd-fg-muted)' }}>
            职业方向不是被「规划」出来的，而是从你自己身上被「发现」的。<br />
            我们相信答案一直在那里，只是需要一个空间被看见。
          </p>
        </motion.div>

        <div className="space-y-4">
          {DIMENSIONS.map((d, i) => (
            <motion.div
              key={d.num}
              initial={{ opacity: 0, x: i % 2 === 0 ? -24 : 24 }}
              whileInView={{ opacity: 1, x: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.5, delay: i * 0.07 }}
              className="bd-eff-card rounded-2xl p-6 md:p-8 flex flex-col md:flex-row md:items-start gap-5"
              style={{
                background: d.varBg,
                border: `1px solid ${d.varBorder}`,
              }}
            >
              <div className="flex-shrink-0 pt-0.5">
                <span className="text-4xl font-black" style={{ color: 'var(--bd-fg-ghost)' }}>{d.num}</span>
              </div>
              <div className="flex-1 space-y-2">
                <div className="flex items-center gap-2">
                  <h3 className="text-xl font-bold" style={{ color: d.varColor }}>{d.name}</h3>
                  <span className="text-xs font-medium tracking-wider" style={{ color: 'var(--bd-fg-subtle)' }}>{d.en}</span>
                </div>
                <p className="text-sm leading-relaxed" style={{ color: 'var(--bd-fg-muted)' }}>{d.desc}</p>
                <p className="text-xs italic pt-1" style={{ color: 'var(--bd-fg-subtle)' }}>「{d.question}」</p>
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ④ 职业双轨 */}
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
          <h2 className="text-2xl md:text-3xl font-bold" style={{ color: 'var(--bd-fg)' }}>职业双轨</h2>
          <p className="text-sm max-w-md mx-auto leading-relaxed" style={{ color: 'var(--bd-fg-muted)' }}>
            职业不是人生的全部，但可以是人生最重要的表达。我们正在构建一套工具，帮你同时规划职业成就路径与人生意义路径。
          </p>
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
        </motion.div>
      </section>

    </div>
  );
}
