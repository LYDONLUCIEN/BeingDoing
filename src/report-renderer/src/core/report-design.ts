export const REPORT_PAPER_COLOR = "rgb(255, 253, 249)";

export const COVER_OPTIONS = [
  {
    id: "A",
    name: "静谧地平线",
    description: "最接近寻路主视觉，重心稳定，标题区最安静。",
    asset: "/report-assets/cover-options/cover-a-quiet-horizon.png",
  },
  {
    id: "B",
    name: "抽象罗盘",
    description: "方向感更强，不使用重复的太阳与道路意象。",
    asset: "/report-assets/cover-options/cover-b-compass-arcs.png",
  },
  {
    id: "C",
    name: "汇流笔触",
    description: "更轻盈、更抽象，纵向笔触与正文页装饰呼应。",
    asset: "/report-assets/cover-options/cover-c-converging-strokes.png",
  },
] as const;

export const FOOTER_MARK_OPTIONS = [
  {
    id: "A",
    name: "路径圆章",
    asset: "/report-assets/footer-marks/footer-mark-a-path-seal.png",
  },
  {
    id: "B",
    name: "竖向罗盘",
    asset: "/report-assets/footer-marks/footer-mark-b-compass-needle.png",
  },
  {
    id: "C",
    name: "时间层理",
    asset: "/report-assets/footer-marks/footer-mark-c-time-strata.png",
  },
] as const;

export const SIGNATURE_OPTIONS = [
  { id: "01", name: "签名一", asset: "/report-assets/signatures/signature-01.png" },
  { id: "02", name: "签名二", asset: "/report-assets/signatures/signature-02.png" },
  { id: "03", name: "签名三", asset: "/report-assets/signatures/signature-03.png" },
] as const;

// 这两个值是当前报告中的临时预览选择。确认方案后只需修改这里。
export const REPORT_DESIGN = {
  paperColor: REPORT_PAPER_COLOR,
  cover: COVER_OPTIONS[0],
  footerMark: FOOTER_MARK_OPTIONS[0],
  signature: SIGNATURE_OPTIONS[1],
} as const;
