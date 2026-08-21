/**
 * 供测试与外部复用的库入口（构建为 dist/core.mjs）。
 * CLI 入口见 render.tsx（构建为 dist/render-pdf.mjs）。
 */
export { normalizeReportMarkdown, extractNickname } from "./normalize";
export { parseMarkdownBlocks, parseReportSections, paginateReport } from "./core/markdown-parser";
export type { MarkdownBlock, MarkdownReportPage, ReportSection } from "./core/markdown-parser";
export type { ReportMeta } from "./core/markdown-report";
