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

test("跨页拆表被 rebalance 合并回同页时，片段按相同表头拼回一张表", () => {
  // 构造：填满大半个续页的正文 + 一张 6 行表 + 短收尾段，
  // 使表格在章节最后两页之间被拆（2+4），随后 rebalance 把尾页合并回来。
  const filler = "这是一段用于填充页面高度的正文内容，".repeat(2);
  const body = Array.from({ length: 11 }, () => filler).join("\n\n");
  const row = Array.from({ length: 8 }, (_, i) => `| 方向${i} | 价值观匹配度较高 | 优势匹配度中高 | 热爱匹配度高 | 核心吸引力描述文字 | 风险描述 | 入门难度中 |`).join("\n");
  const md = [
    "# 小明的寻路之旅", "", "## 阅读指南", "", "指南", "", PB, "",
    "# 第七章 其余职业方向推荐", "", body, "",
    "### 推荐方向总结表", "",
    "| 方向名称 | 价值观匹配度 | 优势匹配度 | 热爱匹配度 | 核心吸引力 | 风险 | 入门难度 |",
    "| --- | --- | --- | --- | --- | --- | --- |",
    row, "",
    "**结语**", "", "收尾。", "",
  ].join("\n");
  const pages = paginateReport(normalizeReportMarkdown(md));
  let fragmentPairs = 0;
  let totalRows = 0;
  for (const page of pages) {
    for (let i = 1; i < page.blocks.length; i += 1) {
      const a = page.blocks[i - 1];
      const b = page.blocks[i];
      if (a.type === "table" && b.type === "table" && a.headers.join() === b.headers.join()) fragmentPairs += 1;
      if (a.splitGroup !== undefined && a.splitGroup === b.splitGroup) fragmentPairs += 1;
    }
    for (const b of page.blocks) if (b.type === "table" && b.headers[0] === "方向名称") totalRows += b.rows.length;
  }
  assert.equal(fragmentPairs, 0, "同页不应出现相邻的同源拆分片段（表格重复表头/段落拦腰截断）");
  assert.equal(totalRows, 8, "表格行数在拆分/合并后不得丢失");
});
