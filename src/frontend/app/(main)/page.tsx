'use client';

import { useEffect, useState, type CSSProperties } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useLocale } from '@/hooks/useLocale';
import LegalDocLink from '@/components/legal/LegalDocLink';
import LegacyBrowserNotice from '@/components/layout/LegacyBrowserNotice';
import { FAQ_ITEMS } from '@/lib/content/faq';
import XiaohongshuQrEntry from '@/components/common/XiaohongshuQrEntry';

const TESTIMONIALS: Array<{
  quote: string;
  name: string;
  role: string;
  avatarPosition: string;
  color: string;
}> = [
  { quote: '我第一次意识到，我一直在做别人期待的事，而不是我认为重要的事。这个过程让我看清了自己。', name: '小林', role: '产品经理', avatarPosition: '0% 0%', color: '#818cf8' },
  { quote: '原来沟通协调这件事对我来说真的是优势，不是习惯。这个区分让我第一次觉得自己有竞争力。', name: 'Maggie', role: '市场运营', avatarPosition: '50% 0%', color: '#fb7185' },
  { quote: '帮助别人成长这件事，让我忘我。我以为那只是爱好，没想到可以成为职业核心。', name: '阿文', role: '应届生', avatarPosition: '100% 0%', color: '#f5b938' },
  { quote: '使命感这个词以前对我太虚了。但当我说出「我想帮普通人做出好决策」的时候，我哭了。', name: '晓敏', role: '咨询顾问', avatarPosition: '0% 50%', color: '#34b98b' },
  { quote: '以为自己什么都喜欢，其实是什么都没认真想过。四个维度逼着我去想清楚，很有价值。', name: '老K', role: '创业者', avatarPosition: '50% 50%', color: '#22b8cf' },
  { quote: '第一次做完就哭了，太多东西压在心里没被看见。这是一份给自己的礼物。', name: '苏苏', role: '教师', avatarPosition: '100% 50%', color: '#e66fb0' },
  { quote: '以前觉得职业规划是套路，但这里的对话让我真正在思考「我」是谁。', name: '浩然', role: '程序员', avatarPosition: '0% 100%', color: '#818cf8' },
  { quote: '热爱那一关，我写了五件小事。没想到它们可以串成一条清晰的线。', name: '小雨', role: '设计师', avatarPosition: '50% 100%', color: '#e6ad31' },
  { quote: '和伴侣一起做完探索，才发现我们原来有这么多共振点。', name: '阿杰', role: '创业合伙人', avatarPosition: '100% 100%', color: '#34b98b' },
];

const DIMENSION_KEYS = ['values', 'strengths', 'interests', 'purpose', 'rumination'] as const;
type DimensionKey = (typeof DIMENSION_KEYS)[number];

const REFERENCES = [
  {
    title: '世界一やさしい「やりたいこと」の見つけ方',
    detail: '八木仁平. 世界一やさしい「やりたいこと」の見つけ方——人生のモヤモヤから解放される自己理解メソッド[M]. 東京: KADOKAWA, 2020.',
    summary: '这套自我理解方法把“真正想做的事”拆成三个可以梳理的部分：重视的事、擅长的事与喜欢的事。它强调答案不是等待某次命运般的相遇，而是先澄清价值观，再盘点自然反复出现的能力与兴趣，最后寻找三者的交点。对职业选择而言，价值观决定方向，优势提供做事方式，兴趣则给出持续探索的领域。',
  },
  {
    title: 'Ikigai',
    detail: 'GARCÍA H, MIRALLES F. Ikigai: The Japanese Secret to a Long and Happy Life[M]. London: Hutchinson, 2017.',
    summary: '作者通过对冲绳长寿社区的访谈，把 ikigai 理解为“每天愿意起床的理由”。它不只关乎职业，也来自持续投入的活动、亲密关系、社区联结与对日常小事的专注。书中把保持行动、进入心流、适度饮食、经常运动和彼此照应放在同一幅生活图景里，提醒我们：有意义的工作需要嵌入一种可长期维持的生活方式。',
  },
  {
    title: 'Designing Your Life',
    detail: 'BURNETT B, EVANS D. Designing Your Life: How to Build a Well-Lived, Joyful Life[M]. New York: Alfred A. Knopf, 2016.',
    summary: '这本书把设计思维用于人生与职业：先重新定义那些让人卡住的问题，再通过记录投入感与能量、绘制多条“奥德赛计划”、开展原型访谈和小型体验来验证方向。核心不是一次想出唯一正确答案，而是保持好奇、采取行动、从反馈中迭代。职业选择因此从高压的终局决定，变成一连串成本可控、能产生真实证据的实验。',
  },
  {
    title: 'The Element',
    detail: 'ROBINSON K, ARONICA L. The Element: How Finding Your Passion Changes Everything[M]. New York: Viking, 2009.',
    summary: '“Element”指天赋与热情相遇的状态：做一件事既有自然能力，也真心喜欢，并因此感到更像自己。书中的人物故事说明，年龄、学历和既有职位并不会封死可能性，但发现天赋需要更多接触、练习、支持自己的同伴，以及敢于质疑单一成功标准的态度。它鼓励我们观察哪些活动同时带来能力表现、沉浸感与持续投入的愿望。',
  },
  {
    title: 'The Pathfinder',
    detail: 'LORE N. The Pathfinder: How to Choose or Change Your Career for a Lifetime of Satisfaction and Success[M]. New York: Simon & Schuster, 1998.',
    summary: '《The Pathfinder》把职业设计视为一项需要系统调查的个人工程。书中的大量自测与诊断练习，引导读者越过职位名称，辨认自己的兴趣、性格、能力、价值观与理想工作条件，再把这些线索组合成候选方向。重点不是凭感觉立刻转行，而是研究现实机会、比较适配度、逐步验证，让“我想要怎样的工作”变成可以执行的选择标准。',
  },
  {
    title: 'Career Anchors',
    detail: 'SCHEIN E H. Career Anchors: Discovering Your Real Values[M]. Rev. ed. San Francisco: Jossey-Bass/Pfeiffer, 1990.',
    summary: '职业锚是一个人在经验中逐渐稳定下来的自我概念，由能力、动机与价值观共同构成。Schein 提出的八类职业锚包括专业技术、综合管理、自主独立、安全稳定、创业创造、服务奉献、纯粹挑战与生活方式。它的价值不在给人贴标签，而在揭示你面对晋升、转型或取舍时最不愿牺牲的部分，从而理解某些“看似更好”的机会为何并不适合自己。',
  },
  {
    title: 'StrengthsFinder 2.0',
    detail: 'RATH T. StrengthsFinder 2.0[M]. New York: Gallup Press, 2007.',
    summary: 'CliftonStrengths 用 34 个才干主题描述人们自然形成的思考、感受与行动模式，并通过测评呈现最突出的主题组合。它主张把时间投入在已有潜能上：才干经过知识、技能与持续练习，才会发展成稳定优势。用于职业探索时，关键不是寻找一个与主题同名的岗位，而是辨认自己怎样解决问题、建立关系、影响他人或推动执行，再设计能频繁使用这些模式的角色与合作方式。',
  },
  {
    title: 'Character Strengths and Virtues',
    detail: 'PETERSON C, SELIGMAN M E P. Character Strengths and Virtues: A Handbook and Classification[M]. Washington, DC: American Psychological Association; New York: Oxford University Press, 2004.',
    summary: '这项积极心理学框架以六类美德统整 24 项品格优势，为好奇、勇敢、仁爱、公平、节制、希望等积极特质提供共同语言。每个人都拥有这些优势，只是程度、组合和使用情境不同。它并非简单的优劣排名，而是帮助人们识别哪些品质最自然、最有活力，以及何时需要更平衡地表达。用于生涯设计时，它补充了技能之外“我希望以怎样的方式成为一个人”的视角。',
  },
  {
    title: 'What Color Is Your Parachute?',
    detail: 'BOLLES R N, BROOKS K. What Color Is Your Parachute? 2022: Your Guide to a Lifetime of Meaningful Work and Career Success[M]. Berkeley, CA: Ten Speed Press, 2021.',
    summary: '这本长期更新的求职与转型指南，把找工作同时看作认识自己与理解市场的过程。其经典练习帮助读者盘点可迁移技能、偏好的工作环境、知识领域、合作对象、生活目标与回报方式，再用信息访谈、定向研究和主动接触去寻找匹配。它提醒我们，批量投递只是方法之一；更有效的行动往往来自清晰的自我画像、具体的目标组织，以及对真实工作内容的持续求证。',
  },
  {
    title: 'The Renaissance Soul',
    detail: 'LOBENSTINE M. The Renaissance Soul: Life Design for People with Too Many Passions to Pick Just One[M]. New York: Broadway Books, 2006.',
    summary: '《The Renaissance Soul》写给同时拥有多种兴趣、难以接受“一生只选一条路”的人。它不把变化快、爱跨界视为缺陷，而是建议从共同价值中理解这些兴趣，并在一个阶段只设少数焦点，通过轮换项目、组合职业与清晰的时间边界保持进展。真正的问题不是逼自己永久放弃其他可能，而是设计一种既能容纳多重热情，又能兼顾收入、承诺和完成感的生活结构。',
  },
];

function PhaseSymbol({ phase }: { phase: DimensionKey }) {
  if (phase === 'values') {
    return <svg viewBox="0 0 48 48" aria-hidden><circle cx="24" cy="24" r="12" /><path d="m28.8 18.6-3 8.1-6.6 2.7 3-8.1 6.6-2.7Z" /><circle cx="24" cy="24" r="1.5" /></svg>;
  }
  if (phase === 'strengths') {
    return <svg viewBox="0 0 48 48" aria-hidden><path d="M24 36V20" /><path d="M24 25c-7 0-11-4-11-10 7 0 11 3 11 10Z" /><path d="M24 22c6 0 10-4 10-10-6 0-10 4-10 10Z" /></svg>;
  }
  if (phase === 'interests') {
    return <svg viewBox="0 0 48 48" aria-hidden><path d="M24 35S11 28 11 19.5C11 14.8 14.3 12 18.2 12c2.7 0 4.7 1.4 5.8 3.6C25.1 13.4 27.1 12 29.8 12c3.9 0 7.2 2.8 7.2 7.5C37 28 24 35 24 35Z" /></svg>;
  }
  if (phase === 'purpose') {
    return <svg viewBox="0 0 48 48" aria-hidden><circle cx="24" cy="24" r="8" /><path d="M24 6v6M24 36v6M6 24h6M36 24h6M11.3 11.3l4.2 4.2M32.5 32.5l4.2 4.2M36.7 11.3l-4.2 4.2M15.5 32.5l-4.2 4.2" /></svg>;
  }
  return <svg viewBox="0 0 48 48" aria-hidden><ellipse cx="24" cy="32.5" rx="12" ry="4.5" /><ellipse cx="24" cy="23" rx="8.5" ry="4" /><ellipse cx="24" cy="14.5" rx="5" ry="3" /></svg>;
}

function JourneyHero({ onStart, t }: { onStart: () => void; t: (key: string) => string }) {
  const [selected, setSelected] = useState<DimensionKey>('values');
  const [autoSelectPaused, setAutoSelectPaused] = useState(false);

  useEffect(() => {
    if (autoSelectPaused) return;
    const timer = window.setInterval(() => {
      setSelected((current) => {
        const alternatives = DIMENSION_KEYS.filter((key) => key !== current);
        return alternatives[Math.floor(Math.random() * alternatives.length)];
      });
    }, 3600);
    return () => window.clearInterval(timer);
  }, [autoSelectPaused]);

  return (
    <>
      <section className="ol-hero ol-home-section" aria-label="寻路 OpenLife 首页">
        <div className="ol-home-scene">
          <img className="ol-home-scene-bg" src="/assets/openlife-journey/home-scene.webp?v=20260921" alt="" fetchPriority="high" decoding="async" />
          <div className="ol-hero-copy">
            <p className="ol-eyebrow"><span />{t('home.tagline')}<span /></p>
            <h1>{t('home.heroTitle')}</h1>
            <p>{t('home.heroSlogan')}</p>
            <button type="button" className="ol-hero-cta" onClick={onStart}>
              {t('common.startExplore')} <span>→</span>
            </button>
          </div>

          <div className="ol-journey-dock" id="journey">
            <h2>{t('home.dimensionsTitle')}</h2>
            <div
              className="ol-phase-cards"
              role="radiogroup"
              aria-label={t('home.dimensionsTitle')}
              onMouseLeave={() => setAutoSelectPaused(false)}
            >
              <svg className="ol-journey-connector" viewBox="0 0 1500 110" preserveAspectRatio="none" aria-hidden>
                <path d="M36 64 C142 10 224 102 334 62 S516 18 624 65 S818 102 924 62 S1114 18 1218 64 S1386 96 1464 60" />
                <circle cx="300" cy="67" r="5" /><circle cx="600" cy="67" r="5" /><circle cx="900" cy="67" r="5" /><circle cx="1200" cy="67" r="5" />
              </svg>
              {DIMENSION_KEYS.map((key) => (
                <button
                  key={key}
                  type="button"
                  className={`ol-phase-card ol-phase-card--${key}`}
                  role="radio"
                  aria-checked={selected === key}
                  tabIndex={selected === key ? 0 : -1}
                  onMouseEnter={() => { setAutoSelectPaused(true); setSelected(key); }}
                  onFocus={() => { setAutoSelectPaused(true); setSelected(key); }}
                  onBlur={() => setAutoSelectPaused(false)}
                  onClick={() => { setAutoSelectPaused(true); setSelected(key); }}
                >
                  <span className="ol-phase-no">{t(`dimensions.${key}.step`)}</span>
                  <span className="ol-phase-symbol"><PhaseSymbol phase={key} /></span>
                  <strong>{t(`dimensions.${key}.name`)}</strong>
                  <small>{t(`dimensions.${key}.desc`)}</small>
                </button>
              ))}
            </div>
          </div>
        </div>
        <a className="ol-scroll-cue" href="#report"><span>继续向下探索</span><b>↓</b></a>
      </section>
      <div className="ol-white-transition" aria-hidden><span /></div>
    </>
  );
}

function FloatingBotanical() {
  return (
    <div className="ol-floating-botanical" aria-hidden>
      <img src="/assets/openlife-journey/botanical-scene.webp?v=20260921" alt="" loading="lazy" decoding="async" />
      <span className="ol-botanical-halo ol-botanical-halo--blue" />
      <span className="ol-botanical-halo ol-botanical-halo--gold" />
      <span className="ol-botanical-mote ol-botanical-mote--coral" />
      <span className="ol-botanical-mote ol-botanical-mote--green" />
      <span className="ol-botanical-mote ol-botanical-mote--violet" />
    </div>
  );
}

function ReportSection({ onStart, t }: { onStart: () => void; t: (key: string) => string }) {
  return (
    <section className="ol-report ol-home-section" id="report">
      <div className="ol-report-panel ol-glass-surface">
        <div className="ol-report-copy">
          <p className="ol-kicker">YOUR OPENLIFE REPORT</p>
          <p className="ol-report-subtitle">{t('home.reportCard.titleLine2')}</p>
          <p>{t('home.reportCard.intro')}</p>
          <ul>
            {Array.from({ length: 6 }, (_, i) => {
              const [lead, rest] = t(`home.reportCard.item${i + 1}`).split('::');
              return <li key={i}><strong>{lead}</strong>{rest}</li>;
            })}
          </ul>
          <button type="button" className="ol-text-link" onClick={onStart}>{t('home.reportCard.cta')} <span>→</span></button>
        </div>
        <div className="ol-report-visual">
          <h2 className="ol-report-preview-title">{t('home.reportCard.titleLine1')}</h2>
          <figure className="ol-report-preview" aria-label={t('home.reportCard.previewAlt')}>
            <div className="ol-report-fan">
              <img className="ol-report-page ol-report-page--left" src="/assets/openlife-journey/report-preview-2.webp?v=20260921" alt="职业探索报告：热爱分析章节预览" loading="lazy" decoding="async" />
              <img className="ol-report-page ol-report-page--center" src="/assets/openlife-journey/report-preview-1.webp?v=20260921" alt="职业探索报告：报告内容预览" loading="lazy" decoding="async" />
              <img className="ol-report-page ol-report-page--right" src="/assets/openlife-journey/report-preview-3.webp?v=20260921" alt="职业探索报告：最终选择章节预览" loading="lazy" decoding="async" />
            </div>
            <figcaption>{t('home.reportCard.previewCaption')}</figcaption>
          </figure>
        </div>
      </div>
    </section>
  );
}

function ReviewsSection() {
  const { t } = useLocale();
  const pageCount = Math.ceil(TESTIMONIALS.length / 3);
  const [page, setPage] = useState(0);
  const visible = TESTIMONIALS.slice(page * 3, page * 3 + 3);
  const move = (delta: number) => setPage((current) => (current + delta + pageCount) % pageCount);

  return (
    <section className="ol-reviews ol-home-section ol-section-shell ol-glass-surface" id="reviews" aria-labelledby="reviews-title">
      <div className="ol-section-heading">
        <p className="ol-kicker">STORIES FROM THE JOURNEY</p>
        <h2 id="reviews-title">{t('home.theirStories')}</h2>
        <p>{t('home.testimonialsSubtitle')}</p>
      </div>
      <div className="ol-review-stage" aria-live="polite">
        <button type="button" className="ol-round-arrow" aria-label="上一组评价" onClick={() => move(-1)}>←</button>
        <div className="ol-review-grid" key={page}>
          {visible.map((item) => (
            <article key={`${item.name}-${item.role}`} className="ol-review-card" style={{ '--review-color': item.color } as CSSProperties}>
              <div className="ol-stars" aria-label="5 星">★★★★★</div>
              <blockquote>{item.quote}</blockquote>
              <div className="ol-review-author">
                <span
                  className="ol-review-avatar ol-review-avatar--art"
                  style={{ '--avatar-position': item.avatarPosition } as CSSProperties}
                  role="img"
                  aria-label={`${item.role}风格头像`}
                />
                <p><b>{item.name}</b><small>{item.role}</small></p>
              </div>
            </article>
          ))}
        </div>
        <button type="button" className="ol-round-arrow" aria-label="下一组评价" onClick={() => move(1)}>→</button>
      </div>
      <div className="ol-review-dots" aria-label="评价分页">
        {Array.from({ length: pageCount }, (_, i) => (
          <button key={i} type="button" aria-label={`第 ${i + 1} 组评价`} aria-current={i === page} onClick={() => setPage(i)} />
        ))}
      </div>
    </section>
  );
}

function MethodSection() {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const selectedReference = REFERENCES[selectedIndex];

  return (
    <section className="ol-method ol-home-section" id="method" aria-labelledby="method-title">
      <div className="ol-method-panel ol-glass-surface">
        <div className="ol-section-heading ol-method-heading">
          <p className="ol-kicker">OPENLIFE METHODOLOGY</p>
          <h2 id="method-title">参考文献</h2>
          <p>有温度，也有依据</p>
        </div>
        <div className="ol-method-intro">
          <p>我们把职业心理学、生涯设计、优势研究与长期主义方法，转译成一次次可理解的对话。</p>
          <p className="ol-method-note">本产品的流程与内容设计，参考了以下经典著作与理论研究。方法不会替你作决定，只帮助你看见决定背后的自己。</p>
          <article className="ol-reference-insight" key={selectedReference.title} aria-live="polite">
            <h3>{selectedReference.title}</h3>
            <hr className="ol-reference-rule" />
            <p>{selectedReference.summary}</p>
          </article>
        </div>
        <ol className="ol-reference-list">
          {REFERENCES.map((item, i) => (
            <li key={item.title} data-selected={selectedIndex === i}>
              <button
                type="button"
                aria-pressed={selectedIndex === i}
                onPointerEnter={() => setSelectedIndex(i)}
                onFocus={() => setSelectedIndex(i)}
                onClick={() => setSelectedIndex(i)}
              >
                <span>{String(i + 1).padStart(2, '0')}</span>
                <p><b>{item.title}</b><small>{item.detail}</small></p>
              </button>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

function FaqSection() {
  const [openIndex, setOpenIndex] = useState<number | null>(0);
  return (
    <section className="ol-faq ol-home-section ol-section-shell ol-glass-surface" id="faq" aria-labelledby="faq-title">
      <div className="ol-section-heading">
        <p className="ol-kicker">QUESTIONS, ANSWERED</p>
        <h2 id="faq-title">常见问题解答</h2>
        <p>关于使用流程、报告与购买的常见疑问</p>
      </div>
      <div className="ol-faq-list">
        {FAQ_ITEMS.map((item, i) => (
          <details key={item.q} open={openIndex === i}>
            <summary onClick={(event) => { event.preventDefault(); setOpenIndex(openIndex === i ? null : i); }}>
              {item.q}<span className="ol-faq-toggle" aria-hidden />
            </summary>
            <p>{item.a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

function LandingFooter() {
  const { t } = useLocale();
  const year = new Date().getFullYear();
  return (
    <footer className="ol-footer">
      <div className="ol-footer-brand"><img src="/assets/openlife-journey/logo.svg" alt="" /><strong>{t('nav.brand')}</strong></div>
      <p>{t('footer.copyright').replace('{year}', String(year))}</p>
      <div className="ol-footer-links">
        {/* 小红书二维码入口在「关于我们」左侧（2026-09-21 起） */}
        <XiaohongshuQrEntry className="ol-footer-qr" />
        <Link href="/about">{t('footer.aboutUs')}</Link>
        <LegalDocLink type="privacy" className="ol-footer-link" />
        <LegalDocLink type="terms" className="ol-footer-link" />
      </div>
    </footer>
  );
}

export default function LandingPage() {
  const router = useRouter();
  const { t } = useLocale();
  const startExplore = () => router.push('/explore/intro');

  useEffect(() => {
    const root = document.documentElement;
    root.setAttribute('data-landing', 'true');
    root.removeAttribute('data-landing-lite');
    let ticking = false;

    const updateLandingMotion = () => {
      if (ticking) return;
      ticking = true;
      window.requestAnimationFrame(() => {
        const hero = document.querySelector<HTMLElement>('.ol-hero');
        const plant = document.querySelector<HTMLElement>('.ol-floating-botanical');
        const reportFan = document.querySelector<HTMLElement>('.ol-report-fan');
        const navbar = document.querySelector<HTMLElement>('.journey-navbar');
        navbar?.classList.toggle('is-journey-condensed', window.scrollY > 84);

        if (reportFan) {
          const reportRect = reportFan.getBoundingClientRect();
          const viewportHeight = window.innerHeight;
          const startTop = viewportHeight * 0.92;
          const endTop = viewportHeight * 0.5 - reportRect.height * 0.5;
          const rawReportProgress = (startTop - reportRect.top) / Math.max(1, startTop - endTop);
          const boundedReportProgress = Math.max(0, Math.min(1, rawReportProgress));
          const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
          const reportProgress = reduced
            ? 1
            : boundedReportProgress * boundedReportProgress * (3 - 2 * boundedReportProgress);
          const initialSpread = reportFan.offsetWidth * (window.innerWidth <= 720 ? 0.33 : 0.31);
          const finalSpread = reportFan.offsetWidth * (window.innerWidth <= 720 ? 0.14 : 0.135);
          const currentSpread = initialSpread + (finalSpread - initialSpread) * reportProgress;
          reportFan.style.setProperty('--report-progress', reportProgress.toFixed(4));
          reportFan.style.setProperty('--report-left-x', `${(-currentSpread).toFixed(1)}px`);
          reportFan.style.setProperty('--report-right-x', `${currentSpread.toFixed(1)}px`);
          reportFan.style.setProperty('--report-left-rotate', `${(-9.5 * reportProgress).toFixed(2)}deg`);
          reportFan.style.setProperty('--report-right-rotate', `${(9.5 * reportProgress).toFixed(2)}deg`);
          reportFan.style.setProperty('--report-center-y', `${(-12 * reportProgress).toFixed(1)}px`);
          reportFan.style.setProperty('--report-side-y', `${(-6 * reportProgress).toFixed(1)}px`);
        }

        if (!hero || !plant) {
          root.style.setProperty('--botanical-opacity', '0');
          ticking = false;
          return;
        }
        const heroEnd = hero.offsetTop + hero.offsetHeight;
        const start = Math.max(0, heroEnd - window.innerHeight * 0.12);
        const end = heroEnd + window.innerHeight * 0.16;
        const raw = Math.max(0, Math.min(1, (window.scrollY - start) / (end - start)));
        const progress = raw * raw * (3 - 2 * raw);
        const remaining = document.documentElement.scrollHeight - (window.scrollY + window.innerHeight);
        const footerFade = Math.max(0, Math.min(1, remaining / 420));
        const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
        const drift = reduced ? 0 : Math.sin(window.scrollY / 500) * 8;
        const x = reduced ? 0 : Math.cos(window.scrollY / 720) * 5;
        const scale = reduced ? 1 : 1 + Math.sin(window.scrollY / 960) * 0.007;
        const opacityCap = window.innerWidth <= 720 ? 0.4 : 0.58;
        root.style.setProperty('--botanical-drift', `${drift.toFixed(1)}px`);
        root.style.setProperty('--botanical-x', `${x.toFixed(1)}px`);
        root.style.setProperty('--botanical-scale', scale.toFixed(3));
        root.style.setProperty('--botanical-opacity', (progress * opacityCap * footerFade).toFixed(3));
        ticking = false;
      });
    };

    updateLandingMotion();
    window.addEventListener('scroll', updateLandingMotion, { passive: true });
    window.addEventListener('resize', updateLandingMotion);
    return () => {
      window.removeEventListener('scroll', updateLandingMotion);
      window.removeEventListener('resize', updateLandingMotion);
      document.querySelector<HTMLElement>('.journey-navbar')?.classList.remove('is-journey-condensed');
      root.removeAttribute('data-landing');
      root.style.removeProperty('--botanical-drift');
      root.style.removeProperty('--botanical-x');
      root.style.removeProperty('--botanical-scale');
      root.style.removeProperty('--botanical-opacity');
    };
  }, []);

  return (
    <div className="openlife-reference-home">
      <LegacyBrowserNotice />
      <div className="ol-home-grain" aria-hidden />
      <JourneyHero onStart={startExplore} t={t} />
      <div className="ol-scrolling-content">
        <FloatingBotanical />
        <ReportSection onStart={startExplore} t={t} />
        <ReviewsSection />
        <MethodSection />
        <FaqSection />
        <section className="ol-closing ol-home-section">
          <div className="ol-closing-card ol-glass-surface">
            <p>{t('home.exploreYourStorySub')}</p>
            <h2>{t('home.exploreYourStory')}</h2>
            <button type="button" className="ol-hero-cta" onClick={startExplore}>{t('common.startExplore')} <span>→</span></button>
          </div>
        </section>
        <LandingFooter />
      </div>
    </div>
  );
}
