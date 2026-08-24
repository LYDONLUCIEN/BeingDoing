import { Fragment, type CSSProperties, type ReactNode } from "react";
import { MODULE_PAGE_THEMES } from "./module-content";
import { REPORT_DESIGN } from "./report-design";
import { REPORT_MODULES } from "./report-config";
import { ReportOverview } from "./report-overview";
import { EditorialFrame } from "./report-pages";
import { paginateReport, type MarkdownBlock, type MarkdownReportPage } from "./markdown-parser";

/** 报告元数据（由渲染入口按报告动态传入，缺省时回落到设计默认值）。 */
export type ReportMeta = {
  nickname?: string;
  date?: string;
  yearMonth?: string;
  signatureAsset?: string;
};

function renderInline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean).map((part, index) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={`${part}-${index}`}>{part.slice(2, -2)}</strong>
      : <span key={`${part}-${index}`}>{part}</span>,
  );
}

function MarkdownBlockView({ block }: { block: MarkdownBlock }) {
  if (block.type === "heading") {
    if (block.level <= 2) return <h2>{renderInline(block.text)}</h2>;
    return <p className="markdown-report__emphasis">{renderInline(block.text)}</p>;
  }
  if (block.type === "paragraph") {
    const isLabel = /^\*\*[^*]+\*\*$/.test(block.text);
    return <p className={isLabel ? "markdown-report__label" : undefined}>{renderInline(block.text)}</p>;
  }
  if (block.type === "list") {
    return <ul>{block.items.map((item) => <li key={item}>{renderInline(item)}</li>)}</ul>;
  }
  return (
    <table>
      <thead><tr>{block.headers.map((cell) => <th key={cell}>{renderInline(cell)}</th>)}</tr></thead>
      <tbody>{block.rows.map((row, rowIndex) => <tr key={`${row[0]}-${rowIndex}`}>{row.map((cell, cellIndex) => <td key={`${cell}-${cellIndex}`}>{renderInline(cell)}</td>)}</tr>)}</tbody>
    </table>
  );
}

function PageChrome({ page, pageNumber, totalPages, isSectionLast, meta }: { page: MarkdownReportPage; pageNumber: number; totalPages: number; isSectionLast: boolean; meta: ReportMeta }) {
  const moduleInfo = REPORT_MODULES.find((item) => item.number === page.section.moduleNumber) ?? REPORT_MODULES[0];
  const theme = MODULE_PAGE_THEMES.find((item) => item.number === page.section.moduleNumber) ?? MODULE_PAGE_THEMES[0];
  const pageStyle = {
    "--theme-color": moduleInfo.color,
    "--theme-deep": moduleInfo.colorDeep,
    "--trim-top": theme.ornamentTop ?? "40%",
    "--trim-offset": theme.ornamentOffset ?? "10px",
    "--trim-height": theme.ornamentHeight ?? "360px",
  } as CSSProperties;
  const pageLabel = String(pageNumber).padStart(2, "0");
  // 页头右上角章节标签：指南/信件有独立文案，其余取模块编号 · 英文副标题
  const cornerTag =
    page.section.kind === "guide" ? "00 · READING GUIDE"
    : page.section.kind === "letter" ? "信 · A LETTER TO THE EXPLORER"
    : `${moduleInfo.number} · ${moduleInfo.subtitle}`;

  return (
    <EditorialFrame
      pageNumber={pageLabel}
      pageClassName={`markdown-report-page module-content-page markdown-report-page--${page.section.kind}`}
      footerNote={`${pageLabel} / ${String(totalPages).padStart(2, "0")}`}
      cornerTag={cornerTag}
    >
      <img className={`module-content-page__trim module-content-page__trim--${theme.ornamentLayout}`} style={pageStyle} src={theme.ornamentAsset} alt="" aria-hidden="true" />
      <section className="markdown-report-page__content" style={pageStyle}>
        {page.section.kind === "letter" ? (
          <img
            className="markdown-report-letter-bg"
            style={{ top: page.sectionPage === 0 ? 120 : 52 }}
            src="/report-assets/editorial/letter-frame.png"
            alt=""
            aria-hidden="true"
          />
        ) : null}
        {page.sectionPage === 0 ? (
          <header className="module-content-page__chapter markdown-report-page__chapter">
            <span className="module-content-page__number">{page.section.kind === "guide" ? "00" : page.section.kind === "letter" ? "信" : moduleInfo.number}</span>
            <div>
              <small>{page.section.subtitle}</small>
              <h1>{page.section.title}</h1>
              <p>{theme.motif}<i />{theme.description}</p>
            </div>
          </header>
        ) : (
          <header className="markdown-report-page__running"><span>{moduleInfo.number}</span><strong>{page.section.title}</strong><small>续 · {String(page.sectionPage + 1).padStart(2, "0")}</small></header>
        )}
        {page.section.kind === "guide" && page.sectionPage === 0 ? (
          <img className="markdown-report-guide-bar" src="/report-assets/editorial/guide-brush-bar.png" alt="" aria-hidden="true" />
        ) : null}
        <div className="markdown-report-page__body">{page.blocks.map((block, index) => <MarkdownBlockView key={`${block.type}-${index}`} block={block} />)}</div>
        {page.section.kind === "letter" && isSectionLast ? (
          <aside className="markdown-report-letter-signature">
            <span>—— 你的寻路探索引导师</span>
            <img src={meta.signatureAsset ?? REPORT_DESIGN.signature.asset} alt="探索引导师签名" />
          </aside>
        ) : null}
      </section>
    </EditorialFrame>
  );
}

function ReportCoverPage({ totalPages, meta }: { totalPages: number; meta: ReportMeta }) {
  return (
    <main className="editorial-shell markdown-report-cover-shell">
      <article className="editorial-page markdown-report-page markdown-report-cover">
        <img className="markdown-report-cover__art" src={REPORT_DESIGN.cover.asset} alt="" aria-hidden="true" />
        <div className="markdown-report-cover__topline"><span>OPEN LIFE</span><small>CAREER INTELLIGENCE REPORT</small></div>
        <section className="markdown-report-cover__copy">
          <p>寻路 · OPEN LIFE</p>
          <h1>寻路·OpenLife<br />职业发展深度报告</h1>
          <i />
          <strong>所有热爱,都值得成为事业。</strong>
        </section>
        <dl className="markdown-report-cover__meta">
          <div><dt>探索者</dt><dd>{meta.nickname ?? "探索者"}</dd></div>
          <div><dt>报告日期</dt><dd>{meta.date ?? ""}</dd></div>
          <div><dt>报告页数</dt><dd>{totalPages} PAGES</dd></div>
        </dl>
        <footer><span>PERSONAL CAREER REPORT</span><small>个人机密 · 仅供本人阅读</small></footer>
      </article>
    </main>
  );
}

function InsertedOverviewPage({ meta, totalPages }: { meta: ReportMeta; totalPages: number }) {
  return <div className="markdown-report__overview"><ReportOverview yearMonth={meta.yearMonth} totalPages={totalPages} /></div>;
}

export function MarkdownReportDocument({ markdown, meta = {} }: { markdown: string; meta?: ReportMeta }) {
  const pages = paginateReport(markdown);
  const firstNonGuidePage = pages.findIndex((page) => page.section.kind !== "guide");
  const overviewIndex = firstNonGuidePage < 0 ? pages.length : firstNonGuidePage;
  const totalPages = pages.length + 2;
  const nickname = meta.nickname ?? "探索者";
  return (
    <main className="markdown-report" style={{ "--paper": REPORT_DESIGN.paperColor } as CSSProperties}>
      <nav className="markdown-report__toolbar" aria-label="报告操作">
        <div><strong>{nickname} 的寻路报告</strong><span>{totalPages} 页 · 当前预览：封面 {REPORT_DESIGN.cover.id} / 页脚 {REPORT_DESIGN.footerMark.id} / 签名 {(SIGNATURE_BY_ASSET(meta.signatureAsset))}</span></div>
      </nav>
      <div className="markdown-report__pages">
        <ReportCoverPage totalPages={totalPages} meta={meta} />
        {pages.map((page, index) => (
          <Fragment key={`${page.section.title}-${page.sectionPage}`}>
            {index === overviewIndex ? <InsertedOverviewPage meta={meta} totalPages={totalPages} /> : null}
            <PageChrome
              page={page}
              pageNumber={index + 2 + (index >= overviewIndex ? 1 : 0)}
              totalPages={totalPages}
              isSectionLast={pages[index + 1]?.section !== page.section}
              meta={meta}
            />
          </Fragment>
        ))}
        {overviewIndex === pages.length ? <InsertedOverviewPage meta={meta} totalPages={totalPages} /> : null}
      </div>
    </main>
  );
}

function SIGNATURE_BY_ASSET(asset?: string) {
  const match = /signature-(\d+)\.png$/.exec(asset ?? "");
  return match ? match[1] : REPORT_DESIGN.signature.id;
}
