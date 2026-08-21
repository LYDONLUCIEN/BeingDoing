import type { ModulePageNumber } from "./module-content";

export type MarkdownBlock =
  | { type: "heading"; level: 1 | 2 | 3 | 4; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; items: string[] }
  | { type: "table"; headers: string[]; rows: string[][] };

export type ReportSectionKind = "guide" | "role" | "module" | "letter";

export type ReportSection = {
  kind: ReportSectionKind;
  moduleNumber: ModulePageNumber;
  title: string;
  subtitle: string;
  blocks: MarkdownBlock[];
};

export type MarkdownReportPage = {
  section: ReportSection;
  blocks: MarkdownBlock[];
  sectionPage: number;
};

function parseTableRow(line: string) {
  return line.trim().replace(/^\||\|$/g, "").split("|").map((cell) => cell.trim());
}

function isTableDivider(cells: string[]) {
  return cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

export function parseMarkdownBlocks(markdown: string): MarkdownBlock[] {
  const lines = markdown.replace(/\r/g, "").split("\n");
  const blocks: MarkdownBlock[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index].trim();
    if (!line) {
      index += 1;
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      blocks.push({ type: "heading", level: heading[1].length as 1 | 2 | 3 | 4, text: heading[2].trim() });
      index += 1;
      continue;
    }

    if (line.startsWith("- ")) {
      const items: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith("- ")) {
        items.push(lines[index].trim().slice(2).trim());
        index += 1;
      }
      blocks.push({ type: "list", items });
      continue;
    }

    if (line.startsWith("|")) {
      const tableLines: string[] = [];
      while (index < lines.length && lines[index].trim().startsWith("|")) {
        tableLines.push(lines[index].trim());
        index += 1;
      }
      const parsedRows = tableLines.map(parseTableRow);
      const headers = parsedRows[0] ?? [];
      const rows = parsedRows.slice(isTableDivider(parsedRows[1] ?? []) ? 2 : 1);
      blocks.push({ type: "table", headers, rows });
      continue;
    }

    const paragraph: string[] = [line];
    index += 1;
    while (index < lines.length) {
      const next = lines[index].trim();
      if (!next || /^(#{1,4})\s+/.test(next) || next.startsWith("- ") || next.startsWith("|")) break;
      paragraph.push(next);
      index += 1;
    }
    blocks.push({ type: "paragraph", text: paragraph.join(" ") });
  }

  return blocks;
}

function getHeading(blocks: MarkdownBlock[], pattern: RegExp) {
  return blocks.find((block) => block.type === "heading" && pattern.test(block.text));
}

function removeHeading(blocks: MarkdownBlock[], target?: MarkdownBlock) {
  return target ? blocks.filter((block) => block !== target) : blocks;
}

function sectionFromSegment(segment: string): ReportSection {
  let blocks = parseMarkdownBlocks(segment);
  const guideHeading = getHeading(blocks, /^阅读指南$/);
  const journeyHeading = getHeading(blocks, /寻路之旅$/);
  if (guideHeading) {
    blocks = removeHeading(removeHeading(blocks, guideHeading), journeyHeading);
    return { kind: "guide", moduleNumber: "01", title: guideHeading.text, subtitle: journeyHeading?.text ?? "探索者的寻路之旅", blocks };
  }

  // 主流程方言：职业角色章以「开篇：职业角色」为标记，角色名/英文名为动态标题。
  const roleMarker = getHeading(blocks, /^开篇[:：]/);
  if (roleMarker) {
    blocks = removeHeading(blocks, roleMarker);
    const isLatin = (text: string) => /^[A-Za-z0-9][A-Za-z0-9\s&·,\-/|']*$/.test(text);
    const roleName = blocks.find((block) => block.type === "heading" && !isLatin(block.text));
    const roleEn = blocks.find((block) => block.type === "heading" && isLatin(block.text));
    blocks = removeHeading(removeHeading(blocks, roleName), roleEn);
    return {
      kind: "role",
      moduleNumber: "01",
      title: roleName?.type === "heading" ? roleName.text : "职业角色",
      subtitle: roleEn?.type === "heading" ? roleEn.text : "CAREER ROLE DEFINITION",
      blocks,
    };
  }

  const roleHeading = getHeading(blocks, /^个人故事整理师$/);
  if (roleHeading) {
    const roleEn = getHeading(blocks, /^Life Story Weaver$/);
    blocks = removeHeading(removeHeading(blocks, roleHeading), roleEn);
    return { kind: "role", moduleNumber: "01", title: roleHeading.text, subtitle: roleEn?.text ?? "CAREER ROLE DEFINITION", blocks };
  }

  const letterHeading = getHeading(blocks, /^致.+的一封信$/);
  if (letterHeading) {
    blocks = removeHeading(blocks, letterHeading);
    return { kind: "letter", moduleNumber: "01", title: letterHeading.text, subtitle: "A LETTER TO THE EXPLORER", blocks };
  }

  const chapterHeading = blocks.find((block) => block.type === "heading" && block.level === 1);
  const title = chapterHeading?.type === "heading" ? chapterHeading.text : "报告正文";
  const moduleNumber: ModulePageNumber =
    /价值观/.test(title) ? "02" :
    /优势/.test(title) ? "03" :
    /热爱/.test(title) ? "04" :
    /使命/.test(title) ? "05" :
    /最终选择/.test(title) ? "06" :
    /关键洞察|职业方向推荐/.test(title) ? "07" :
    /谁与你最接近/.test(title) ? "08" : "01";
  blocks = removeHeading(blocks, chapterHeading);
  return { kind: "module", moduleNumber, title, subtitle: "CAREER INTELLIGENCE REPORT", blocks };
}

export function parseReportSections(markdown: string): ReportSection[] {
  return markdown
    .split(/^\s*<div class="pb"><\/div>\s*$/m)
    .map((segment) => segment.trim())
    .filter(Boolean)
    .map(sectionFromSegment);
}

function visibleLength(text: string) {
  return text.replace(/\*\*/g, "").length;
}

function lineCount(text: string, charactersPerLine: number) {
  return Math.max(1, Math.ceil(visibleLength(text) / charactersPerLine));
}

export function estimateBlockHeight(block: MarkdownBlock) {
  if (block.type === "heading") {
    if (block.level <= 2) return 25 + lineCount(block.text, 30) * 31;
    return 22 + lineCount(block.text, 44) * 21;
  }
  if (block.type === "paragraph") {
    if (/^\*\*[^*]+\*\*$/.test(block.text)) return 20 + lineCount(block.text, 44) * 22;
    return 11 + lineCount(block.text, 52) * 23;
  }
  if (block.type === "list") {
    return 13 + block.items.reduce((height, item) => height + lineCount(item, 48) * 21 + 5, 0);
  }
  const columns = Math.max(1, block.headers.length);
  const charactersPerCell = Math.max(12, Math.floor(64 / columns));
  const rowHeight = (row: string[]) => 15 + Math.max(...row.map((cell) => lineCount(cell, charactersPerCell))) * 18;
  return 18 + rowHeight(block.headers) + block.rows.reduce((height, row) => height + rowHeight(row), 0);
}

function needsFollower(block: MarkdownBlock) {
  return block.type === "heading" || (block.type === "paragraph" && /^\*\*[^*]+\*\*$/.test(block.text));
}

function blockMargins(block: MarkdownBlock) {
  if (block.type === "heading") return block.level <= 2 ? { top: 9, bottom: 13 } : { top: 13, bottom: 9 };
  if (block.type === "paragraph") return /^\*\*[^*]+\*\*$/.test(block.text) ? { top: 10, bottom: 8 } : { top: 0, bottom: 11 };
  if (block.type === "list") return { top: 2, bottom: 13 };
  return { top: 7, bottom: 14 };
}

function collapsedMargin(previous: MarkdownBlock | undefined, current: MarkdownBlock) {
  if (!previous) return 0;
  return Math.min(blockMargins(previous).bottom, blockMargins(current).top);
}

function addedBlockHeight(block: MarkdownBlock, previous?: MarkdownBlock) {
  return estimateBlockHeight(block) - collapsedMargin(previous, block);
}

function minimumBlockHeight(block: MarkdownBlock) {
  if (block.type === "paragraph") {
    if (/^\*\*[^*]+\*\*$/.test(block.text)) return estimateBlockHeight(block);
    return 11 + Math.min(2, lineCount(block.text, 52)) * 23;
  }
  if (block.type === "list") {
    const firstItem = block.items[0];
    return firstItem ? 13 + lineCount(firstItem, 48) * 21 + 5 : 0;
  }
  if (block.type === "table") {
    const columns = Math.max(1, block.headers.length);
    const charactersPerCell = Math.max(12, Math.floor(64 / columns));
    const rowHeight = (row: string[]) => 15 + Math.max(...row.map((cell) => lineCount(cell, charactersPerCell))) * 18;
    return 18 + rowHeight(block.headers) + (block.rows[0] ? rowHeight(block.rows[0]) : 0);
  }
  return estimateBlockHeight(block);
}

function minimumFollowerHeight(blocks: MarkdownBlock[], previous: MarkdownBlock) {
  let height = 0;
  let previousBlock: MarkdownBlock | undefined = previous;
  for (const block of blocks) {
    if (needsFollower(block)) {
      height += addedBlockHeight(block, previousBlock);
      previousBlock = block;
      continue;
    }
    height += minimumBlockHeight(block) - collapsedMargin(previousBlock, block);
    break;
  }
  return height;
}

function findTextSplitIndex(text: string, maxVisibleCharacters: number) {
  const minimumHeadCharacters = Math.min(70, Math.floor(maxVisibleCharacters * 0.65));
  let visibleCharacters = 0;
  let strongOpen = false;
  let latestBoundary = -1;
  let latestSafeIndex = -1;

  for (let index = 0; index < text.length; index += 1) {
    if (text.startsWith("**", index)) {
      strongOpen = !strongOpen;
      index += 1;
      continue;
    }

    visibleCharacters += 1;
    if (!strongOpen) {
      latestSafeIndex = index + 1;
      if (visibleCharacters >= minimumHeadCharacters && /[。！？；：，、,.!?;:]|\s/.test(text[index])) {
        latestBoundary = index + 1;
      }
    }
    if (visibleCharacters >= maxVisibleCharacters) break;
  }

  return latestBoundary > 0 ? latestBoundary : latestSafeIndex;
}

function splitParagraph(block: Extract<MarkdownBlock, { type: "paragraph" }>, maxHeight: number) {
  if (/^\*\*[^*]+\*\*$/.test(block.text)) return undefined;
  const availableLines = Math.floor((maxHeight - 11) / 23);
  if (availableLines < 2) return undefined;

  const maxVisibleCharacters = availableLines * 52;
  const totalCharacters = visibleLength(block.text);
  if (totalCharacters <= maxVisibleCharacters) return undefined;

  const minimumTailCharacters = Math.min(70, Math.floor(totalCharacters / 3));
  const splitLimit = Math.min(maxVisibleCharacters, totalCharacters - minimumTailCharacters);
  const splitIndex = findTextSplitIndex(block.text, splitLimit);
  if (splitIndex <= 0 || splitIndex >= block.text.length) return undefined;

  const head = block.text.slice(0, splitIndex).trim();
  const tail = block.text.slice(splitIndex).trim();
  if (!head || !tail) return undefined;
  return [{ ...block, text: head }, { ...block, text: tail }] as const;
}

function splitList(block: Extract<MarkdownBlock, { type: "list" }>, maxHeight: number) {
  let height = 13;
  let splitIndex = 0;
  for (const item of block.items) {
    const itemHeight = lineCount(item, 48) * 21 + 5;
    if (splitIndex > 0 && height + itemHeight > maxHeight) break;
    if (splitIndex === 0 && height + itemHeight > maxHeight) return undefined;
    height += itemHeight;
    splitIndex += 1;
  }
  if (splitIndex <= 0 || splitIndex >= block.items.length) return undefined;
  return [{ ...block, items: block.items.slice(0, splitIndex) }, { ...block, items: block.items.slice(splitIndex) }] as const;
}

function splitTable(block: Extract<MarkdownBlock, { type: "table" }>, maxHeight: number) {
  const columns = Math.max(1, block.headers.length);
  const charactersPerCell = Math.max(12, Math.floor(64 / columns));
  const rowHeight = (row: string[]) => 15 + Math.max(...row.map((cell) => lineCount(cell, charactersPerCell))) * 18;
  let height = 18 + rowHeight(block.headers);
  let splitIndex = 0;
  for (const row of block.rows) {
    const nextHeight = rowHeight(row);
    if (splitIndex > 0 && height + nextHeight > maxHeight) break;
    if (splitIndex === 0 && height + nextHeight > maxHeight) return undefined;
    height += nextHeight;
    splitIndex += 1;
  }
  if (splitIndex <= 0 || splitIndex >= block.rows.length) return undefined;
  return [{ ...block, rows: block.rows.slice(0, splitIndex) }, { ...block, rows: block.rows.slice(splitIndex) }] as const;
}

function splitBlock(block: MarkdownBlock, maxHeight: number) {
  if (block.type === "paragraph") return splitParagraph(block, maxHeight);
  if (block.type === "list") return splitList(block, maxHeight);
  if (block.type === "table") return splitTable(block, maxHeight);
  return undefined;
}

function pageBudget(section: ReportSection, sectionPage: number) {
  if (section.kind === "letter") return sectionPage === 0 ? 560 : 670;
  // 阅读指南首页插入横条装饰（渲染层高约 56px + 间距），预算相应扣减防溢出
  if (section.kind === "guide" && sectionPage === 0) return 705;
  return sectionPage === 0 ? 785 : 850;
}

function sequenceHeight(blocks: MarkdownBlock[]) {
  return blocks.reduce((height, block, index) => height + addedBlockHeight(block, blocks[index - 1]), 0);
}

function rebalanceSectionEnd(pages: MarkdownReportPage[], sectionStartIndex: number) {
  const sectionPages = pages.slice(sectionStartIndex);
  if (sectionPages.length < 2 || sectionPages[0].section.kind === "letter") return;

  const previous = sectionPages.at(-2)!;
  const last = sectionPages.at(-1)!;
  const previousBudget = pageBudget(previous.section, previous.sectionPage);
  const lastBudget = pageBudget(last.section, last.sectionPage);
  const combined = [...previous.blocks, ...last.blocks];

  // The estimator intentionally rounds rows and wrapped lines up. A small
  // merge allowance avoids creating a nearly empty final page for a few
  // trailing lines while the browser still keeps a safe footer clearance.
  if (sequenceHeight(combined) <= previousBudget + 35) {
    previous.blocks = combined;
    pages.pop();
    return;
  }

  const currentWorstGap = Math.max(previousBudget - sequenceHeight(previous.blocks), lastBudget - sequenceHeight(last.blocks));
  let best: { splitIndex: number; worstGap: number; balance: number } | undefined;
  for (let splitIndex = 1; splitIndex < combined.length; splitIndex += 1) {
    if (needsFollower(combined[splitIndex - 1])) continue;
    const previousBlocks = combined.slice(0, splitIndex);
    const lastBlocks = combined.slice(splitIndex);
    const previousHeight = sequenceHeight(previousBlocks);
    const lastHeight = sequenceHeight(lastBlocks);
    if (previousHeight > previousBudget || lastHeight > lastBudget) continue;

    const worstGap = Math.max(previousBudget - previousHeight, lastBudget - lastHeight);
    const balance = Math.abs(previousHeight / previousBudget - lastHeight / lastBudget);
    if (!best || worstGap < best.worstGap || (worstGap === best.worstGap && balance < best.balance)) {
      best = { splitIndex, worstGap, balance };
    }
  }

  if (!best || best.worstGap >= currentWorstGap - 20) return;
  previous.blocks = combined.slice(0, best.splitIndex);
  last.blocks = combined.slice(best.splitIndex);
}

export function paginateReport(markdown: string): MarkdownReportPage[] {
  const pages: MarkdownReportPage[] = [];
  for (const section of parseReportSections(markdown)) {
    const sectionStartIndex = pages.length;
    let sectionPage = 0;
    let current: MarkdownBlock[] = [];
    let usedHeight = 0;
    let budget = pageBudget(section, sectionPage);

    const finishPage = () => {
      if (!current.length) return;
      pages.push({ section, blocks: current, sectionPage });
      sectionPage += 1;
      current = [];
      usedHeight = 0;
      budget = pageBudget(section, sectionPage);
    };

    const queue = [...section.blocks];
    while (queue.length) {
      const block = queue.shift()!;
      const previousBlock = current.at(-1);
      const marginCollapse = collapsedMargin(previousBlock, block);
      const blockHeight = addedBlockHeight(block, previousBlock);
      const availableHeight = budget - usedHeight;
      const followerHeight = needsFollower(block) ? minimumFollowerHeight(queue, block) : 0;

      if (current.length && blockHeight <= availableHeight && blockHeight + followerHeight > availableHeight) {
        queue.unshift(block);
        finishPage();
        continue;
      }

      if (blockHeight <= availableHeight) {
        current.push(block);
        usedHeight += blockHeight;
        continue;
      }

      const split = splitBlock(block, availableHeight + marginCollapse);
      if (split) {
        current.push(split[0]);
        usedHeight += addedBlockHeight(split[0], previousBlock);
        queue.unshift(split[1]);
        finishPage();
        continue;
      }

      if (current.length) {
        queue.unshift(block);
        finishPage();
        continue;
      }

      current.push(block);
      usedHeight += blockHeight;
      finishPage();
    }
    finishPage();
    rebalanceSectionEnd(pages, sectionStartIndex);
  }
  return pages;
}
