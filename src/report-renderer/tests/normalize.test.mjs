/**
 * 渲染器归一化层与 parser 方言适配的单测（node:test）。
 * 运行：npm test（先构建 dist/core.mjs）。
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const {
  normalizeReportMarkdown,
  extractNickname,
  parseReportSections,
  paginateReport,
} = await import(path.join(root, "dist", "core.mjs"));

const PB = '<div class="pb"></div>';

test("旧式分页符与 <<<PAGEBREAK>>> 统一为 pb div", () => {
  const md = `# 小明的寻路之旅\n\n## 阅读指南\n\n指南\n\n<div STYLE="page-break-after: always;"></div>\n\n# 第一章 价值观分析\n\n甲\n<<<PAGEBREAK>>>\n# 致小明的一封信\n\n乙`;
  const sections = parseReportSections(normalizeReportMarkdown(md));
  assert.deepEqual(sections.map((s) => s.kind), ["guide", "module", "letter"]);
});

test("### 方言：章节标题提升为一级，小节标题保持强调样式", () => {
  const md = [
    "# 小明的寻路之旅", "", "## 阅读指南", "", "指南", "", PB, "",
    "### 第一章 价值观分析", "", "### 一、逐项解析", "", "内容", "",
  ].join("\n");
  const sections = parseReportSections(normalizeReportMarkdown(md));
  assert.equal(sections[1].kind, "module");
  assert.equal(sections[1].moduleNumber, "02");
  assert.equal(sections[1].title, "第一章 价值观分析");
  // 「一、逐项解析」留在正文 blocks 里且仍是三级（渲染为强调段落，不是大标题）
  const sub = sections[1].blocks.find((b) => b.type === "heading");
  assert.equal(sub.text, "一、逐项解析");
  assert.equal(sub.level, 3);
});

test("## 方言：章节标题同样提升为一级", () => {
  const md = ["# 小明的寻路之旅", "", "## 阅读指南", "", "指南", "", PB, "", "## 第二章 优势分析", "", "内容"].join("\n");
  const sections = parseReportSections(normalizeReportMarkdown(md));
  assert.equal(sections[1].moduleNumber, "03");
  assert.equal(sections[1].title, "第二章 优势分析");
});

test("h5/h6 标题降级为 h4，行首 * 列表转 -", () => {
  const md = ["# 小明的寻路之旅", "", "## 阅读指南", "", "指南", "", PB, "",
    "# 第一章 价值观分析", "", "##### 1. 利他", "", "* 第一条", "* 第二条", "", "**加粗**行不误伤"].join("\n");
  const sections = parseReportSections(normalizeReportMarkdown(md));
  const h5 = sections[1].blocks.find((b) => b.type === "heading");
  assert.equal(h5.level, 4);
  const list = sections[1].blocks.find((b) => b.type === "list");
  assert.deepEqual(list.items, ["第一条", "第二条"]);
  const para = sections[1].blocks.find((b) => b.type === "paragraph");
  assert.equal(para.text, "**加粗**行不误伤");
});

test("职业角色章：开篇标记 + 动态角色名/英文名", () => {
  const md = ["# 小明的寻路之旅", "", "## 阅读指南", "", "指南", "", PB, "",
    "### 开篇：职业角色", "", "### 组织催化师", "", "### The Organization Catalyst", "", "角色描述"].join("\n");
  const sections = parseReportSections(normalizeReportMarkdown(md));
  assert.equal(sections[1].kind, "role");
  assert.equal(sections[1].title, "组织催化师");
  assert.equal(sections[1].subtitle, "The Organization Catalyst");
  // 开篇标记与角色名/英文名标题不进入正文
  assert.equal(sections[1].blocks.every((b) => b.type !== "heading"), true);
});

test("昵称提取：任意标题层级", () => {
  assert.equal(extractNickname("# happy的寻路之旅"), "happy");
  assert.equal(extractNickname("## 探索者的寻路之旅"), "探索者");
  assert.equal(extractNickname("# 没有旅程标题"), undefined);
});

test("xunlu 原生样例：归一化是恒等变换，章节结构与页数不变", () => {
  const sample = readFileSync(
    "/home/gitclone/BeingDoing/report/xunlu/content/reports/mixkz-report.md",
    "utf8",
  );
  const normalized = normalizeReportMarkdown(sample);
  const sections = parseReportSections(normalized);
  assert.deepEqual(
    sections.map((s) => `${s.kind}:${s.moduleNumber}`),
    ["guide:01", "role:01", "module:02", "module:03", "module:04", "module:05", "module:06", "module:07", "module:07", "module:08", "letter:01"],
  );
  // 分页结果与原始输入一致（页数不变）
  assert.equal(paginateReport(normalized).length, paginateReport(sample).length);
});
