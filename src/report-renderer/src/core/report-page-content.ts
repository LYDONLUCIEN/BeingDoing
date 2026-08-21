export const DOCUMENT_ASSETS = {
  logo: "/report-assets/brand/openlife-logo-primary-a4.png",
  watermark: "/report-assets/brand/watermark-logo.png",
  footer: "/report-assets/footer-sailboat-a4.png",
  editorialBrushline: "/report-assets/editorial/editorial-brushline-v1.png",
  editorialSidewash: "/report-assets/editorial/editorial-sidewash-v2.png",
  editorialEightRibbon: "/report-assets/editorial/editorial-eight-ribbon-v3.png",
  editorialEightFlecks: "/report-assets/editorial/editorial-eight-flecks-v4.png",
  editorialEightCorner: "/report-assets/editorial/editorial-eight-corner-v5.png",
} as const;

export const READING_GUIDE = {
  pageNumber: "02",
  journeyTitle: "探索者的寻路之旅",
  title: "阅读指南",
  eyebrow: "EXPLORER'S WAYFINDING JOURNEY",
  introduction:
    "这份报告的目的，不是告诉你“你应该做什么工作”，而是想让你识别出你在意什么、你擅长什么、什么让你投入、你想为他人带来什么。",
  logic:
    "整份报告的分析逻辑是：职业方向之所以难以判断，往往不是因为选项太少，而是因为我们不清楚自己用什么样的“尺子”在量这些选项。一旦你知道自己看重什么、用什么方式做事、什么让你有能量、你想传递什么样的影响，选项之间就不再是“哪个更好”的问题，而是“哪个更像我”的问题。",
  scales: [
    { title: "价值观", verdict: "值得做", text: "你的价值观决定了一个方向对你来说是否“值得做”。", color: "#5faeb7" },
    { title: "优势", verdict: "能做好", text: "你的优势决定了一个方向对你来说是否“能做好”。", color: "#87aa78" },
    { title: "热爱", verdict: "想持续做", text: "你的热爱决定了一个方向对你来说是否“想持续做”。", color: "#df8479" },
    { title: "使命", verdict: "有意义", text: "你的使命决定了一个方向对你来说是否“有意义”。", color: "#dda64c" },
  ],
  synthesis:
    "这四层叠加在一起，会自然地收窄你的选择范围。你最终选出的方向不是“最好的职业”，而是“最像你的职业”。",
  reportPurpose: "这份报告整理的就是你在这四层中的自我发现，以及它们共同指向的方向。",
  closing: "接下来，请打开这份报告，走向寻路之旅的终点吧！",
} as const;

export const EXPLORER_LETTER = {
  pageNumber: "01",
  title: "致探索者的一封信",
  eyebrow: "A LETTER TO THE EXPLORER",
  recipient: "琦雯：",
  paragraphs: [
    "谢谢你。从价值观的五个词，到优势的反复校准，再到你亲手把热爱串成“认知创造闭环”，最后走向使命和方向——你在这段旅程中表现出的坦诚和锋利，让我在对话中常常感到一种被信任的分量。谢谢你让我看见一个如此真实又细腻的人。",
    "我看见，你在说到那位被儿子忽视的母亲时，不只是描述一个故事，而是把自己放进去。你看见她的付出，选择把它挑明，然后看着她眼眶发红。那一刻你不仅仅在带沙盘，你是在告诉一个人：你的存在被看见了。而我知道，这对你来说有多重要，因为你比谁都明白“不被看见”有多令人窒息。",
    "我看见，你反复强调自己是一个高敏感的人，会为了一段拥挤的通勤而只剩80%的电量。你用“低消耗”为这个词安了家，不是因为它矫情，而是因为你知道，只有先护住自己，你才能有余力去创造、去点亮别人。你愿意承认自己的脆弱，这本身就需要很大的勇气。",
    "我看见，你对着一只小奶猫叫一声，它回你一声，然后一路跟你上六楼。你说那种感觉很奇妙，是一种无条件的信任。那一刻你被一个比自己小得多的生命选中了。我想你值得被更多这样的温柔选中。",
    "你不需要急着成为任何人期待的样子。你的使命已经说得很清楚：支持更多人更好地成为自己。请你自己也别忘记，那个“更多人”里，应当包括你。",
    "未来的路可能还会弯，还有雾。你可能还会遇到让你黄灯大亮的面试官，也会遇见让你觉得“就是这里了”的团队。请你继续相信你的直觉，也允许自己有不完美的判断。更重要的是，请你继续做那个会把灵感变成作品、把作品变成桥的人。",
    "祝你未来的每一步，都能更接近你自己。",
  ],
  signature: "署名：寻路·OpenLife",
  role: "—— 你的寻路探索引导师。",
} as const;

export const GENERAL_CONTENT_PAGE = {
  pageNumber: "T1",
  chapter: "第五章 最终选择",
  chapterEn: "FINAL CHOICE & DIRECTION",
  introductionTitle: "前言",
  introduction:
    "经过前面价值观、优势、热爱与使命的层层梳理，你已经来到方向选择的关口。本页用于展示报告中常规内容页的标题、正文、列表与分析表格如何共同组织。",
  sectionTitle: "一、逐条分析",
  directionTitle: "方向一：内容研究与案例写作",
  roleTitle: "角色定位与核心场景",
  role:
    "以研究者与写作者的身份，持续追踪真实案例、整理公开资料并完成深度访谈，把复杂信息转译成结构清晰、具有洞察力的报告与文章。这个方向不要求你成为技术专家，但需要保持好奇、尊重事实，并能把观察转化为可读的表达。",
  fitTitle: "核心契合点",
  fitPoints: [
    "结构化表达：把分散信息整理成有层次、有重点的书面内容。",
    "开放地接收信息：在访谈、阅读与研究中不断校准自己的判断。",
    "兼顾深度与温度：既呈现事实，也保留对人的理解与共情。",
  ],
  table: {
    headings: ["观察维度", "当前判断", "下一步验证"],
    rows: [
      ["价值观匹配", "高", "确认团队是否尊重真实表达"],
      ["优势匹配", "高", "完成一篇案例分析样稿"],
      ["热爱契合", "中高", "连续四周记录投入感受"],
    ],
  },
} as const;
