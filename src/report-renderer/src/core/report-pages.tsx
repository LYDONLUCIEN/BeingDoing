import type { ReactNode } from "react";
import { REPORT_DESIGN } from "./report-design";
import { DOCUMENT_ASSETS } from "./report-page-content";

type DocumentFrameProps = {
  children: ReactNode;
  pageNumber: string;
  section: string;
  sectionEn: string;
  footerNote: string;
  pageClassName?: string;
};

export function DocumentFrame({
  children,
  pageNumber,
  section,
  sectionEn,
  footerNote,
  pageClassName = "",
}: DocumentFrameProps) {
  return (
    <main className="document-shell">
      <article className={`document-page ${pageClassName}`}>
        <header className="document-header">
          <img className="document-header__logo" src={DOCUMENT_ASSETS.logo} alt="寻路 OpenLife" />
          <div className="document-header__meta">
            <span>{sectionEn}</span>
            <strong>{section}</strong>
            <small>CAREER INTELLIGENCE REPORT</small>
          </div>
        </header>
        <div className="document-rule" />

        {children}

        <footer className="document-footer">
          <img className="document-footer__scenery" src={DOCUMENT_ASSETS.footer} alt="" aria-hidden="true" />
          <div className="document-footer__row">
            <div className="document-page-number"><strong>{pageNumber}</strong><span>PAGE</span></div>
            <img className="document-footer__logo" src={DOCUMENT_ASSETS.logo} alt="寻路 OpenLife" />
            <p>{footerNote}</p>
          </div>
        </footer>
      </article>
    </main>
  );
}

export function DocumentTitle({ eyebrow, overline, children }: { eyebrow: string; overline?: string; children: ReactNode }) {
  return (
    <header className="document-title">
      <p>{eyebrow}</p>
      {overline ? <span>{overline}</span> : null}
      <h1>{children}</h1>
      <div className="document-title__ornament"><i /></div>
    </header>
  );
}

type EditorialFrameProps = {
  children: ReactNode;
  pageNumber: string;
  footerNote?: string;
  pageClassName?: string;
  footerMark?: string;
};

export function EditorialFrame({
  children,
  pageNumber,
  footerNote = "AI生成，仅供参考",
  pageClassName = "",
  footerMark = REPORT_DESIGN.footerMark.asset,
}: EditorialFrameProps) {
  return (
    <main className="editorial-shell">
      <article className={`editorial-page ${pageClassName}`}>
        <header className="editorial-header">
          <div className="editorial-header__label"><span>CAREER INTELLIGENCE REPORT</span><small>职业发展深度报告</small></div>
          <img className="editorial-header__logo" src={DOCUMENT_ASSETS.logo} alt="寻路 OpenLife" />
        </header>

        <div className="editorial-watermark" aria-hidden="true">寻路 · OPEN LIFE</div>
        {children}

        <footer className="editorial-footer">
          <div className="editorial-footer__page"><strong>{pageNumber}</strong><span>PAGE</span></div>
          <div className="editorial-footer__brand">
            <img src={footerMark} alt="" aria-hidden="true" />
            <span>OPEN LIFE</span>
          </div>
          <p>{footerNote}</p>
        </footer>
      </article>
    </main>
  );
}
