import type { CSSProperties } from "react";
import { REPORT_ASSETS, REPORT_MODULES, type ReportModule } from "./report-config";

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`brand ${compact ? "brand--compact" : ""}`}>
      <div className="brand__mark" aria-hidden="true">
        <img src={REPORT_ASSETS.logoMark} alt="" />
      </div>
      <div className="brand__type">
        <div className="brand__name">寻路<span>·OpenLife</span></div>
        <div className="brand__caption">OPEN LIFE</div>
      </div>
    </div>
  );
}

function Landscape() {
  return (
    <figure className="landscape">
      <img src={REPORT_ASSETS.hero} alt="暖橙日出映照青蓝群山，一条白色道路蜿蜒通向远方" />
    </figure>
  );
}

function ReportCard({ module }: { module: ReportModule }) {
  const style = { "--module-color": module.color, "--module-deep": module.colorDeep } as CSSProperties;
  return (
    <article className="report-card" style={style}>
      <img className="report-card__art" src={module.cardAsset} alt="" aria-hidden="true" />
      <div className="report-card__header">
        <div className="report-card__heading">
          <span className="report-card__number">{module.number}</span>
          <h2>{module.title}</h2>
        </div>
        <span className="report-card__tag"><span aria-hidden="true">{module.tagIcon}</span>{module.tag}</span>
      </div>
      <div className="report-card__body">
        <p>{module.subtitle}</p>
        <span className="report-card__line" />
        <span className="report-card__symbol" aria-hidden="true">{module.symbol}</span>
      </div>
    </article>
  );
}

export function ReportOverview({ yearMonth, totalPages }: { yearMonth?: string; totalPages?: number }) {
  return (
    <main className="page-shell">
      <section className="report-page">
        <header className="topbar">
          <Brand />
          <div className="report-meta" aria-label="报告信息">
            <div><span aria-hidden="true">▣</span><b>日期：</b>{yearMonth ?? "2026年8月"}</div>
            <div><span aria-hidden="true">▱</span><b>页数：</b>共 {totalPages ?? "—"} 页</div>
          </div>
        </header>

        <div className="section-rule" />

        <section className="hero">
          <div className="hero__copy">
            <p className="eyebrow">CAREER INTELLIGENCE REPORT · 职业发展深度报告</p>
            <h1>报告内容预览</h1>
            <div className="title-ornament"><span /></div>
            <p className="hero__intro">本报告共包含 8 大分析模块，从职业角色到名人画像，<br />通过提升自我认知，提供结构化的行动参考。</p>
          </div>
          <Landscape />
        </section>

        <section className="module-grid" aria-label="报告模块列表">
          {REPORT_MODULES.map((module) => <ReportCard key={module.number} module={module} />)}
        </section>

        <footer className="report-footer">
          <div className="quote-strip">
            <span className="quote-strip__mark">“</span>
            <p>更了解自己，才能更清晰地选择；更清晰地选择，才能走得更远。</p>
            <div className="quote-strip__scenery" aria-hidden="true"><img src={REPORT_ASSETS.footer} alt="" /></div>
          </div>
          <div className="footer-row">
            <div className="page-number"><strong>03</strong><span>PAGE</span></div>
            <Brand compact />
            <p>AI生成，仅供参考</p>
          </div>
        </footer>
      </section>
    </main>
  );
}
