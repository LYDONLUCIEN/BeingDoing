/**
 * 输入归一化层：把主流程（FastAPI + report_postprocess）产出的报告 markdown
 * 适配为 xunlu 渲染 parser 期望的方言。对 xunlu 原生样例输入是恒等变换。
 *
 * 与主流程 report_postprocess.py 的对应关系（渲染侧兜底，覆盖存量缓存报告）：
 * 1. 分页符统一：旧式 `<div STYLE="page-break-after: always;"></div>` 与
 *    `<<<PAGEBREAK>>>` 统一为 parser 唯一识别的 `<div class="pb"></div>`。
 * 2. 行首 `* ` 列表 → `- `（同 _normalize_lists 的 _STAR_LIST_RE 口径）。
 * 3. h5/h6 标题 → h4（parser 只识别 1-4 级；同 _normalize_headings 口径）。
 * 4. 章节标题层级提升：parser 以「段内第一个一级标题」作为模块章标题，
 *    而存量报告的章节标题有 `##`/`###` 两种写法。规则：分段后，若段内
 *    第一个标题匹配「第X章」且级别 > 1，仅把该标题提升为一级。
 *    （guide/role/letter 的识别均为文本匹配、与层级无关，无需提升；
 *    段内其余三级小节标题保持原样，维持强调样式渲染。）
 */

const PB_DIV = '<div class="pb"></div>';
const CHAPTER_RE = /^(#{2,6})(\s+第[一二三四五六七八九十百]+章)/;

/** 统一分页符写法（parser 按独占一行的精确形态切分章节）。 */
function normalizePagebreaks(markdown: string): string {
  return markdown
    .replace(/<<<PAGEBREAK>>>/g, PB_DIV)
    .replace(/<div[^>]*page-break-after\s*:\s*always[^>]*>\s*<\/div>/gi, PB_DIV);
}

/** 行级语法修正：`* ` 列表 → `- `；h5/h6 → h4。 */
function normalizeLines(markdown: string): string {
  return markdown
    .split("\n")
    .map((line) => {
      const starred = line.replace(/^(\s*)\*\s+/, "$1- ");
      return starred.replace(/^#{5,6}(\s+)/, "####$1");
    })
    .join("\n");
}

/** 段内第一个标题为「第X章」且级别 > 1 时，仅提升该标题为一级。 */
function promoteChapterHeading(segment: string): string {
  const lines = segment.split("\n");
  const firstHeadingIndex = lines.findIndex((line) => /^#{1,6}\s+/.test(line.trim()));
  if (firstHeadingIndex < 0) return segment;
  if (!CHAPTER_RE.test(lines[firstHeadingIndex].trim())) return segment;
  lines[firstHeadingIndex] = lines[firstHeadingIndex].replace(CHAPTER_RE, "#$2");
  return lines.join("\n");
}

/**
 * 归一化入口。返回值的章节分段形态与 parser 的切分正则完全一致。
 */
export function normalizeReportMarkdown(markdown: string): string {
  const text = normalizeLines(normalizePagebreaks(markdown.replace(/\r/g, "")));
  return text
    .split(/^\s*<div class="pb"><\/div>\s*$/m)
    .map((segment) => promoteChapterHeading(segment).trim())
    .filter(Boolean)
    .join(`\n${PB_DIV}\n`);
}

/** 从报告 markdown 提取探索者昵称（`{昵称}的寻路之旅` 标题，层级不限）。 */
export function extractNickname(markdown: string): string | undefined {
  const match = /^#{1,6}\s+(.+?)的寻路之旅\s*$/m.exec(markdown);
  return match?.[1]?.trim() || undefined;
}
