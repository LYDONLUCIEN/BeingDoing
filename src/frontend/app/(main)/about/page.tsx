'use client';

import { motion } from 'framer-motion';

// 文案来源：wiki/开发文档/0907-关于我们.md
const ABOUT_PARAGRAPHS = [
  '寻路OpenLife成立于2026年，致力于成为自由职业者最值得信赖的个人成长支持平台。我们深知，传统职业成长规划往往周期漫长、见效迟缓、结果难以衡量，于是选择结合科技的效率和人文的关怀，重新定义这条路径。让定制化成长变得更低门槛、更高效、更贴合每个人真实的需求，同时不失专业深度与温度。',
  '创始人Lillian毕业于斯坦福大学，拥有近十年横跨国内外的多元职业履历，曾先后担任技术开发、项目经理、产品负责人、咨询顾问等角色，积累了从执行到决策的完整视野。创始团队同样来自国内外知名院校，成员背景覆盖互联网、外企、央国企等多元行业，包含岗位从业者、自由职业者、连续创业者和跨界探索者。我们每个人，都曾是“转换赛道”的亲历者。正因如此，我们更懂当下职场人与自由职业者在新旧价值体系交替中的迷茫与渴望，并希望用更落地、更有效、更富人文关怀的方式，帮助每一位个体构建属于自己的事业发展体系。',
  '我们的产品设计，源自创始团队亲身验证的方法论，融合国内外前沿的职业发展成长框架，并经过大量真实咨询案例的反复打磨，最终形成一套从“定位”到“规划”再到“成长”的完整闭环。我们始终相信：真正能陪伴你走得更远的成长伙伴，既要懂专业，更要懂人生。',
  '在服务理念上，我们坚持透明、低门槛、可信赖——所有服务与收费公开明细，绝无隐形消费；你可以随时查阅来自真实用户的客观反馈。寻路OpenLife，专注且只专注于个人成长支持。',
];

export default function AboutPage() {
  return (
    <div className="min-h-screen bg-bd-gradient text-bd-fg">
      <div className="max-w-3xl mx-auto px-4 py-16 space-y-10">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex items-center justify-center gap-4"
        >
          <img
            src="/assets/logo.png"
            alt="寻路·OpenLife"
            className="w-14 h-14 md:w-16 md:h-16 shrink-0"
          />
          <div className="space-y-1">
            <h1 className="text-3xl md:text-4xl font-bold">关于我们</h1>
            <p className="text-bd-muted text-lg">帮助每个人找到真正想做的事</p>
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="rounded-xl border border-bd-border bg-bd-card p-6 md:p-8 space-y-5 text-bd-muted leading-loose text-sm md:text-base"
        >
          {ABOUT_PARAGRAPHS.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
          <p>
            如有任何产品疑问、合作意向或希望加入我们，欢迎通过邮箱联系我们：
            <a
              href="mailto:openlife.lab@outlook.com"
              className="font-semibold text-bd-fg hover:underline"
            >
              openlife.lab@outlook.com
            </a>
            。期待与你同行。
          </p>
        </motion.div>
      </div>
    </div>
  );
}
