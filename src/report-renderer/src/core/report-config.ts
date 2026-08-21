import { REPORT_PAPER_COLOR } from "./report-design";

export const PDF_SPEC = {
  standard: "A4 portrait",
  dpi: 300,
  width: 2480,
  height: 3508,
  background: REPORT_PAPER_COLOR,
} as const;

export const REPORT_ASSETS = {
  pageBackground: "/report-assets/page-background-a4-300dpi.png",
  logoMark: "/report-assets/logo-mark-a4.png",
  hero: "/report-assets/hero-watercolor-a4.png",
  footer: "/report-assets/footer-sailboat-a4.png",
} as const;

export type ReportModule = {
  number: string;
  title: string;
  tag: string;
  subtitle: string;
  color: string;
  colorDeep: string;
  symbol: string;
  tagIcon: string;
  cardAsset: string;
};

// 文案、标签、颜色与完整水粉卡片底图统一在这里配置。
export const REPORT_MODULES: ReportModule[] = [
  { number: "01", title: "职业角色", tag: "基础框架", subtitle: "CAREER ROLE DEFINITION", color: "#65c5c6", colorDeep: "#177f93", symbol: "♙", tagIcon: "▧", cardAsset: "/report-assets/cards/card-01-career-role.png" },
  { number: "02", title: "价值观分析", tag: "价值锚点", subtitle: "VALUES ANALYSIS", color: "#8fbde9", colorDeep: "#4a79b8", symbol: "◇", tagIcon: "◈", cardAsset: "/report-assets/cards/card-02-values.png" },
  { number: "03", title: "优势分析", tag: "能力图谱", subtitle: "STRENGTHS & ROLE FIT", color: "#9bc593", colorDeep: "#4e8456", symbol: "☆", tagIcon: "▥", cardAsset: "/report-assets/cards/card-03-strengths.png" },
  { number: "04", title: "热爱分析", tag: "动力来源", subtitle: "PASSION ANALYSIS", color: "#ee938d", colorDeep: "#d65355", symbol: "♡", tagIcon: "♡", cardAsset: "/report-assets/cards/card-04-passion.png" },
  { number: "05", title: "使命分析", tag: "长期愿景", subtitle: "MISSION ANALYSIS", color: "#efbd57", colorDeep: "#d58c28", symbol: "⚑", tagIcon: "♙", cardAsset: "/report-assets/cards/card-05-mission.png" },
  { number: "06", title: "最终选择", tag: "行动决策", subtitle: "FINAL CHOICE & MVP", color: "#9a88cf", colorDeep: "#654cab", symbol: "◎", tagIcon: "◉", cardAsset: "/report-assets/cards/card-06-choice.png" },
  { number: "07", title: "关键洞察与方向推荐", tag: "综合结论", subtitle: "KEY INSIGHTS & RECOMMENDATIONS", color: "#3d9db8", colorDeep: "#17647d", symbol: "☼", tagIcon: "♧", cardAsset: "/report-assets/cards/card-07-insights.png" },
  { number: "08", title: "谁与你最接近", tag: "参照原型", subtitle: "ARCHETYPE PORTRAITS", color: "#a26f49", colorDeep: "#653f28", symbol: "♧", tagIcon: "♙", cardAsset: "/report-assets/cards/card-08-archetypes.png" },
];
