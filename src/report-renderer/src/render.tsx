/**
 * 精简报告渲染器 CLI：markdown → A4 HTML（react-dom/server）→ Chrome headless 打印 PDF。
 *
 * 用法：
 *   node dist/render-pdf.mjs --md <报告.md> --out <输出.pdf>
 *       [--nickname 昵称] [--date "2026 年 08 月 20 日"] [--signature 01|02|03]
 *       [--keep-html <调试.html>] [--chrome <chrome 路径>]
 *
 * 退出码：0 成功；非 0 失败（错误信息走 stderr，stdout 仅输出 PDF 路径）。
 */
import { spawnSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MarkdownReportDocument, type ReportMeta } from "./core/markdown-report";
import { SIGNATURE_OPTIONS } from "./core/report-design";
import { extractNickname, normalizeReportMarkdown } from "./normalize";

const RENDERER_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ASSETS_DIR = path.join(RENDERER_ROOT, "assets", "report-assets");
const CSS_PATH = path.join(RENDERER_ROOT, "src", "styles", "report.css");
const FONTS_DIR = path.join(RENDERER_ROOT, "assets", "fonts");

/** 内嵌衬线中文字体（字重 → 文件名）。缺文件时回退系统字体并警告。 */
const EMBEDDED_FONTS: Array<[number, string]> = [
  [400, "NotoSerifSC_400Regular.ttf"],
  [500, "NotoSerifSC_500Medium.ttf"],
  [600, "NotoSerifSC_600SemiBold.ttf"],
  [700, "NotoSerifSC_700Bold.ttf"],
];

function buildFontFaceCss(): string {
  const faces = EMBEDDED_FONTS.map(([weight, file]) => {
    const fontPath = path.join(FONTS_DIR, file);
    if (!existsSync(fontPath)) return undefined;
    return `@font-face { font-family: "Noto Serif SC"; src: url("${pathToFileURL(fontPath).href}") format("truetype"); font-weight: ${weight}; font-display: block; }`;
  }).filter(Boolean);
  if (!faces.length) {
    process.stderr.write(`[render-pdf] 警告：未找到内嵌字体（${FONTS_DIR}），将使用系统字体，版式可能有差异。\n`);
  } else if (faces.length < EMBEDDED_FONTS.length) {
    process.stderr.write("[render-pdf] 警告：部分字重字体文件缺失。\n");
  }
  return faces.join("\n");
}

function fail(message: string): never {
  process.stderr.write(`[render-pdf] ${message}\n`);
  process.exit(1);
}

function parseArgs(argv: string[]) {
  const args: Record<string, string> = {};
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (!key.startsWith("--")) fail(`无法识别的参数：${key}`);
    const value = argv[index + 1];
    if (!value || value.startsWith("--")) fail(`参数 ${key} 缺少值`);
    args[key.slice(2)] = value;
    index += 1;
  }
  if (!args.md) fail("缺少 --md <报告 markdown 文件>");
  if (!args.out) fail("缺少 --out <输出 pdf 文件>");
  return args;
}

function findChrome(explicit?: string): string {
  const candidates = [
    explicit,
    process.env.CHROME_PATH,
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
  ].filter(Boolean) as string[];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  fail("没有找到 Chrome/Chromium，可用 --chrome 或 CHROME_PATH 指定。");
}

function formatDate(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y} 年 ${m} 月 ${d} 日`;
}

function toYearMonth(dateText: string): string {
  const match = /(\d{4})\s*年\s*(\d{1,2})\s*月/.exec(dateText);
  return match ? `${match[1]}年${Number(match[2])}月` : dateText;
}

function buildHtml(body: string): string {
  const css = `${buildFontFaceCss()}\n${readFileSync(CSS_PATH, "utf8")}`;
  const assetsBaseUrl = pathToFileURL(ASSETS_DIR).href;
  const inlinedBody = body.replaceAll('"/report-assets/', `"${assetsBaseUrl}/`);
  return [
    "<!doctype html>",
    '<html lang="zh-CN"><head><meta charset="utf-8" />',
    "<title>寻路 · OpenLife 职业发展深度报告</title>",
    `<style>${css}</style>`,
    "</head><body>",
    inlinedBody,
    "</body></html>",
  ].join("\n");
}

const args = parseArgs(process.argv.slice(2));
const rawMarkdown = readFileSync(args.md, "utf8");
const markdown = normalizeReportMarkdown(rawMarkdown);

const date = args.date ?? formatDate(new Date());
const signatureId = args.signature ?? "02";
const signature = SIGNATURE_OPTIONS.find((item) => item.id === signatureId);
if (!signature) fail(`未知签名方案：${signatureId}（可选 ${SIGNATURE_OPTIONS.map((item) => item.id).join("/")}）`);

const meta: ReportMeta = {
  nickname: args.nickname ?? extractNickname(markdown) ?? "探索者",
  date,
  yearMonth: toYearMonth(date),
  signatureAsset: signature.asset,
};

const body = renderToStaticMarkup(createElement(MarkdownReportDocument, { markdown, meta }));
const html = buildHtml(body);

const htmlPath = args["keep-html"]
  ? path.resolve(args["keep-html"])
  : path.join(tmpdir(), `xunlu-report-${process.pid}-${Date.now()}.html`);
mkdirSync(path.dirname(htmlPath), { recursive: true });
writeFileSync(htmlPath, html);

const outPath = path.resolve(args.out);
mkdirSync(path.dirname(outPath), { recursive: true });

const chrome = findChrome(args.chrome);
const result = spawnSync(
  chrome,
  [
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--allow-file-access-from-files",
    "--no-pdf-header-footer",
    "--print-to-pdf-no-header",
    "--virtual-time-budget=10000",
    `--print-to-pdf=${outPath}`,
    pathToFileURL(htmlPath).href,
  ],
  { encoding: "utf8" },
);
if (result.error) fail(`Chrome 启动失败：${result.error.message}`);
if (result.status !== 0) fail(`Chrome 退出码 ${result.status}：${result.stderr || result.stdout}`);
if (!existsSync(outPath) || statSync(outPath).size === 0) fail("Chrome 未产出有效 PDF 文件。");

process.stdout.write(`${outPath}\n`);
