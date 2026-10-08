'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { motion, AnimatePresence } from 'framer-motion';
import PaperVeilLayers from '@/components/explore/PaperVeilLayers';
import XiaohongshuQrEntry from '@/components/common/XiaohongshuQrEntry';

// 文案来源：wiki/开发文档/10-05/咨询师.md（2026-10-06 上线咨询师介绍页，入口在顶部导航「咨询团队」）
// v3（2026-10-07）：咨询师改为一次展示一位、左右切换；卡内多栏铺开全量内容
// （背景/咨询风格/适合人群并列 + 价值观标签），保证一屏内看完一位咨询师。
// v4（2026-10-08）：卡片视觉按 wiki/开发文档/10-07/consultants.html 重做——
// 左人物栏（头像/编号/姓名/风格标签/元信息）+ 右内容栏（背景要点/
// 咨询风格/适合人群双栏/价值观 chips），每位咨询师独立 accent 色
// （祝余=蓝、Mary=绿、Lena=紫）。样式见 styles/components/consultants-coach.css。

// 统一介绍（含小红书/反馈指引，文案与需求文档保持一致）
const INTRO_PARAGRAPH =
  '寻路OpenLife 严选在自由职业、转型赛道与职场发展领域经验丰富的咨询师，为您提供定制化报告解读。目前，我们已帮助 100+ 自由职业者和职场转型人理清思路并找到自己的方向。想了解匹配建议或预约方式，可前往小红书店铺，或点击右下角“提交问题反馈”联系我们。';

const SCOPE_TEXT =
  '寻路OpenLife 咨询师团队提供专业的寻路OpenLife 报告解读，覆盖自我认知提升、职场答疑解惑、自由职业探索、职业方向转型等维度。所有咨询师均由团队严选并接受培训，咨询效果稳定，全程无导流、无额外收费。';

const REQUIREMENT_TEXT = '你需要已经持有一份寻路OpenLife的报告。';

const FORMAT_ITEMS = [
  '线上 60 分钟 1v1 深度对话，不受地域限制，沟通私密、聚焦、高效。',
  '咨询前，根据您的需求与特点匹配咨询师。',
  '提供 1 次免费更换机会：若咨询开始后的前 15 分钟内不满意，可申请更换咨询师。',
];

// 咨询师数据来源：wiki/开发文档/10-05/咨询师.md（全量展示：背景 / 咨询风格 / 适合人群 / 价值观）
// id 用于 consultants-coach.css 的 data-coach accent 配色；initial 为头像字母
interface Coach {
  id: 'zhuyu' | 'mary' | 'lena';
  name: string;
  initial: string;
  subtitle: string;
  industry: string;
  format: string;
  years: string;
  background: string[];
  style: string[];
  audience: string[];
  values: string[];
}

const COACHES: Coach[] = [
  {
    id: 'zhuyu',
    name: '祝余',
    initial: '祝',
    subtitle: '结构化梳理 · 优势挖掘 · 职业转型',
    industry: '公益、教育、互联网、职业咨询',
    format: '线上',
    years: '10+年',
    background: [
      '公益与教育行业十年以上沉淀，兼具NGO与互联网大厂经验。',
      '拥有国际交流背景与团队管理经验，跨领域视野扎实。',
      '经历从公益到互联网的行业转换，理解不同赛道的工作逻辑。',
      '擅长报告解读、优势挖掘、职业转型梳理与行动方案设计。',
    ],
    style: [
      '结构化拆解，用框架把模糊感受变成清晰问题。',
      '温和但有力量，会直接指出你的不一致和盲区。',
      '追问式引导，不替你给答案，帮你自己找到方向。',
      '赋能式反馈，擅长把“缺点”重构为你的优势。',
      '盯行动、给方法，咨询结束时有明确的下一步。',
    ],
    audience: [
      '职业迷茫、想转型、有报告但不会用的人。',
      '高反思、低自信、长期缺正反馈的人。',
      '喜欢逻辑框架、愿意自我探索的人。',
      '需要被看见、被肯定、被推一把的人。',
      '想探索副业、第二曲线、公益/心理/内容方向的人。',
    ],
    values: ['价值实现', '自爱', '自由', '正直', '奋斗'],
  },
  {
    id: 'mary',
    name: 'Mary',
    initial: 'M',
    subtitle: '温和陪伴 · 职业定位 · 选择梳理',
    industry: '互联网、电商、职业咨询',
    format: '线上',
    years: '10+年',
    background: [
      '大厂营销/运营实战背景，熟悉电商行业岗位、校招、转行求职的真实场景。',
      '亲身经历岗位调整、求职选择、自由职业，懂职场人的纠结内耗、被卡住的真实感受。',
      '擅长优势梳理、职业定位、转行规划、心理疏导，帮你理清职业选择中的取舍。',
    ],
    style: [
      '温和陪伴式沟通，循循引导，不急着下结论。',
      '善于倾听共情，接纳你的迷茫，再慢慢一起拆解卡点。',
      '以提问引导思考，不灌输标准答案，帮你听见自己内心的倾向。',
      '兼顾感受与落地，先梳理情绪，再一起敲定可执行的步骤。',
    ],
    audience: [
      '在多个选项之间反复纠结、容易内耗的人。',
      '不清楚自身优势、害怕试错风险的人。',
      '需要有人耐心帮你梳理现状，看清取舍的人。',
      '希望被理解、被支持，不喜欢高压式沟通的人。',
    ],
    values: ['接纳', '看见', '从容', '长期成长'],
  },
  {
    id: 'lena',
    name: 'Lena',
    initial: 'L',
    subtitle: '高效破局 · 天赋优势 · 行动落地',
    industry: 'AI、科技/互联网、咨询',
    format: '线上',
    years: '10+年',
    background: [
      '十年以上职场沉淀，横跨世界500强互联网公司的技术、产品与项目管理。',
      '三次转岗转行，跨职能、跨行业经验扎实。',
      '两次职业空窗，亲历空窗后求职与互联网创业。',
      '擅长内在成长、挖掘天赋优势、职业转型、目标和执行力管理。',
    ],
    style: [
      '拆解问题快准狠，专治卡点。',
      '用追问代替说教，带你自己找到答案。',
      '反馈直接，节奏明快，不绕弯。',
      '盯行动、看落地，不只聊感受。',
    ],
    audience: [
      '想高效破局、拒绝拖沓的人。',
      '能接受直言、不怕被追问的人。',
      '愿意表达、也愿意独立思考的人。',
      '目标感强、希望咨询后立刻有方向的人。',
    ],
    values: ['清醒', '批判', '自由', '成长', '正直'],
  },
];

function CoachCarousel() {
  // [当前下标, 切换方向]；方向用于左右滑动动效
  const [[index, direction], setState] = useState<[number, number]>([0, 0]);
  const coach = COACHES[index];
  const move = (delta: number) =>
    setState(([i]) => [(i + delta + COACHES.length) % COACHES.length, delta]);

  return (
    <div className="space-y-5">
      {/* 姓名页签：直接选人 */}
      <div className="flex justify-center gap-2" role="tablist" aria-label="选择咨询师">
        {COACHES.map((item, i) => (
          <button
            key={item.name}
            type="button"
            role="tab"
            aria-selected={i === index}
            onClick={() => setState([i, i > index ? 1 : -1])}
            className={`rounded-full border px-4 py-1.5 text-sm transition-colors ${
              i === index
                ? 'border-bd-fg bg-bd-overlay-md font-semibold text-bd-fg'
                : 'border-bd-border text-bd-muted hover:text-bd-fg'
            }`}
          >
            {item.name}
          </button>
        ))}
      </div>

      {/* 卡片与上方介绍卡同宽；箭头骑跨卡片两缘（落在卡片 padding 内不遮内容），≤720px 由全局样式隐藏 */}
      <div className="relative" aria-live="polite">
        <AnimatePresence mode="wait" initial={false}>
            <motion.article
              key={coach.name}
              role="tabpanel"
              data-coach={coach.id}
              initial={{ opacity: 0, x: direction >= 0 ? 24 : -24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: direction >= 0 ? -24 : 24 }}
              transition={{ duration: 0.22, ease: 'easeOut' }}
              /* v4 卡面（consultants-coach.css）：外壳仍用玻璃纸面质感，内部为
                 左人物栏 + 右内容栏；min-height 在 CSS 内按断点控制，宽度随容器 */
              className="ol-coach-card bd-glass-card ol-reading-glass rounded-[26px]"
            >
              {/* 左：人物栏（头像 / 编号 / 姓名 / 风格标签 / 元信息） */}
              <aside className="ol-coach-aside">
                <div className="ol-coach-avatar" aria-hidden="true">
                  {coach.initial}
                </div>
                <span className="ol-coach-count">
                  CONSULTANT {String(index + 1).padStart(2, '0')}
                </span>
                <h3 className="ol-coach-name">{coach.name}</h3>
                <p className="ol-coach-subtitle">{coach.subtitle}</p>
                <dl className="ol-coach-meta">
                  <div className="ol-coach-meta-row">
                    <dt>行业</dt>
                    <dd>{coach.industry}</dd>
                  </div>
                  <div className="ol-coach-meta-row">
                    <dt>形式</dt>
                    <dd>{coach.format}</dd>
                  </div>
                  <div className="ol-coach-meta-row">
                    <dt>工作年限</dt>
                    <dd>{coach.years}</dd>
                  </div>
                </dl>
              </aside>

              {/* 右：背景要点 / 咨询风格·适合人群双栏 / 价值观 */}
              <div className="ol-coach-content">
                <ul className="ol-coach-summary">
                  {coach.background.map((item, j) => (
                    <li key={j}>{item}</li>
                  ))}
                </ul>

                <div className="ol-coach-detail-grid">
                  {(
                    [
                      ['咨询风格', coach.style],
                      ['适合人群', coach.audience],
                    ] as const
                  ).map(([label, items]) => (
                    <section key={label} aria-label={label}>
                      <div className="ol-coach-detail-title">{label}</div>
                      <ul className="ol-coach-detail-list">
                        {items.map((item, j) => (
                          <li key={j}>{item}</li>
                        ))}
                      </ul>
                    </section>
                  ))}
                </div>

                <div className="ol-coach-value-row">
                  <span className="ol-coach-value-label">价值观</span>
                  {coach.values.map((value) => (
                    <span key={value} className="ol-coach-value-chip">
                      {value}
                    </span>
                  ))}
                </div>
              </div>
            </motion.article>
        </AnimatePresence>

        <button
          type="button"
          aria-label="上一位咨询师"
          onClick={() => move(-1)}
          className="ol-round-arrow absolute top-1/2 -translate-y-1/2 z-10 -left-4"
        >
          ←
        </button>
        <button
          type="button"
          aria-label="下一位咨询师"
          onClick={() => move(1)}
          className="ol-round-arrow absolute top-1/2 -translate-y-1/2 z-10 -right-4"
        >
          →
        </button>
      </div>

      {/* 移动端分页圆点（首页用户评价同款；桌面用两侧圆箭头 + 页签）。外层包 md:hidden 控制，
          因 .ol-review-dots 的 display:flex 无层叠层，会压过 tailwind 工具类 */}
      <div className="md:hidden">
        <div className="ol-review-dots" aria-label="咨询师分页" style={{ marginTop: 8 }}>
          {COACHES.map((item, i) => (
            <button
              key={item.name}
              type="button"
              aria-label={`第 ${i + 1} 位咨询师：${item.name}`}
              aria-current={i === index}
              onClick={() => setState([i, i > index ? 1 : -1])}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function ConsultantsPage() {
  const router = useRouter();
  // 与 /about 同款纸层背景：置 data-mesh-page 统一布局底色
  useEffect(() => {
    document.documentElement.setAttribute('data-mesh-page', 'true');
    return () => document.documentElement.removeAttribute('data-mesh-page');
  }, []);

  return (
    <div className="bd-mesh-page min-h-screen text-bd-fg">
      <PaperVeilLayers />
      <div className="relative z-[2] max-w-5xl mx-auto px-4 py-16 space-y-10">
        <motion.button
          type="button"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.1 }}
          onClick={() => router.push('/')}
          className="text-sm text-bd-subtle hover:text-bd-fg transition-colors"
        >
          ← 返回首页
        </motion.button>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-center gap-4"
        >
          <img
            src="/assets/lulu-logo.webp"
            alt="寻路·OpenLife"
            className="w-14 h-14 md:w-16 md:h-16 shrink-0 rounded-full object-cover"
          />
          <div className="space-y-1">
            <h1 className="text-3xl md:text-4xl font-bold">咨询团队</h1>
            <p className="text-bd-muted text-lg">定制化报告解读 · 线上 1v1 深度对话</p>
          </div>
        </motion.div>

        {/* 上：完整介绍（统一介绍 + 咨询须知，单张玻璃卡内分三节，正文限宽保证可读性） */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="bd-glass-card ol-reading-glass relative rounded-2xl p-6 md:p-8 space-y-6 text-bd-muted leading-loose text-sm md:text-base [&_p]:max-w-[42rem]"
        >
          {/* 小红书二维码入口：文字面板右上角（与关于我们同款） */}
          <XiaohongshuQrEntry className="ol-about-qr" />
          <p>{INTRO_PARAGRAPH}</p>

          <div className="space-y-2 border-t border-bd-border pt-6">
            <h2 className="text-sm font-semibold text-bd-fg">咨询范围</h2>
            <p>{SCOPE_TEXT}</p>
          </div>

          <div className="space-y-2 border-t border-bd-border pt-6">
            <h2 className="text-sm font-semibold text-bd-fg">咨询条件</h2>
            <p>{REQUIREMENT_TEXT}</p>
          </div>

          <div className="space-y-2 border-t border-bd-border pt-6">
            <h2 className="text-sm font-semibold text-bd-fg">咨询形式</h2>
            <ol className="list-decimal pl-5 space-y-1.5">
              {FORMAT_ITEMS.map((item, i) => (
                <li key={i}>{item}</li>
              ))}
            </ol>
          </div>
        </motion.div>

        {/* 下：咨询师介绍（一次一位、左右切换；卡内三栏铺开全量内容，一屏看完） */}
        <div className="space-y-6">
          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="text-center space-y-1"
          >
            <h2 className="text-2xl font-bold text-bd-fg">咨询师介绍</h2>
            <p className="text-bd-muted text-sm">咨询前，根据您的需求与特点匹配咨询师</p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 15 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
          >
            <CoachCarousel />
          </motion.div>
        </div>
      </div>
    </div>
  );
}
