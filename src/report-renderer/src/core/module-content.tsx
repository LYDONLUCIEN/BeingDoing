import type { CSSProperties } from "react";
import { GENERAL_CONTENT_PAGE } from "./report-page-content";
import { EditorialFrame } from "./report-pages";
import { REPORT_MODULES } from "./report-config";

export const MODULE_PAGE_THEMES = [
  {
    number: "01",
    motif: "框架 · 定位 · 搭建",
    description: "让分散的角色线索找到各自的位置",
    ornamentAsset: "/report-assets/module-trims/module-01-career-framework-trim-v2.png",
    ornamentLayout: "vertical-right",
    ornamentAnchor: null,
    ornamentAlign: null,
    ornamentTop: "29%",
    ornamentOffset: "11px",
    ornamentHeight: "390px",
  },
  {
    number: "02",
    motif: "中心 · 衡量 · 坚持",
    description: "辨认内在标准，知道什么对自己真正重要",
    ornamentAsset: "/report-assets/module-trims/module-02-values-center-vertical-v2.png",
    ornamentLayout: "vertical-left",
    ornamentAnchor: null,
    ornamentAlign: null,
    ornamentTop: "26%",
    ornamentOffset: "13px",
    ornamentHeight: "350px",
  },
  {
    number: "03",
    motif: "生长 · 支撑 · 发挥",
    description: "看见能力如何彼此支撑，并在场景中被调用",
    ornamentAsset: "/report-assets/module-trims/module-03-strengths-growth-trim-v1.png",
    ornamentLayout: "vertical-right",
    ornamentAnchor: null,
    ornamentAlign: null,
    ornamentTop: "41%",
    ornamentOffset: "18px",
    ornamentHeight: "345px",
  },
  {
    number: "04",
    motif: "节奏 · 能量 · 投入",
    description: "找到让行动自然延续的内在牵引力",
    ornamentAsset: "/report-assets/module-trims/module-04-passion-rhythm-vertical-v2.png",
    ornamentLayout: "vertical-right",
    ornamentAnchor: null,
    ornamentAlign: null,
    ornamentTop: "52%",
    ornamentOffset: "15px",
    ornamentHeight: "315px",
  },
  {
    number: "05",
    motif: "指向 · 远景 · 意义",
    description: "让长期目标与想带来的影响逐渐清晰",
    ornamentAsset: "/report-assets/module-trims/module-05-mission-direction-trim-v1.png",
    ornamentLayout: "vertical-left",
    ornamentAnchor: null,
    ornamentAlign: null,
    ornamentTop: "49%",
    ornamentOffset: "15px",
    ornamentHeight: "330px",
  },
  {
    number: "06",
    motif: "汇聚 · 决断 · 行动",
    description: "把多重可能收束成可以验证的第一步",
    ornamentAsset: "/report-assets/module-trims/module-06-choice-convergence-vertical-v2.png",
    ornamentLayout: "vertical-left",
    ornamentAnchor: null,
    ornamentAlign: null,
    ornamentTop: "31%",
    ornamentOffset: "10px",
    ornamentHeight: "340px",
  },
  {
    number: "07",
    motif: "拆解 · 重组 · 洞见",
    description: "把复杂线索重新组织成可执行的方向",
    ornamentAsset: "/report-assets/module-trims/module-07-insights-synthesis-trim-v1.png",
    ornamentLayout: "vertical-left",
    ornamentAnchor: null,
    ornamentAlign: null,
    ornamentTop: "36%",
    ornamentOffset: "8px",
    ornamentHeight: "375px",
  },
  {
    number: "08",
    motif: "层理 · 时间 · 沉淀",
    description: "借由相似原型，看见经验累积出的个人脉络",
    ornamentAsset: "/report-assets/module-trims/module-08-archetype-strata-vertical-v2.png",
    ornamentLayout: "vertical-right",
    ornamentAnchor: null,
    ornamentAlign: null,
    ornamentTop: "43%",
    ornamentOffset: "9px",
    ornamentHeight: "365px",
  },
] as const;

export type ModulePageNumber = (typeof MODULE_PAGE_THEMES)[number]["number"];

export function ModuleContentPage({ moduleNumber }: { moduleNumber: ModulePageNumber }) {
  const moduleInfo = REPORT_MODULES.find((item) => item.number === moduleNumber) ?? REPORT_MODULES[0];
  const theme = MODULE_PAGE_THEMES.find((item) => item.number === moduleNumber) ?? MODULE_PAGE_THEMES[0];
  const style = { "--theme-color": moduleInfo.color, "--theme-deep": moduleInfo.colorDeep } as CSSProperties;
  const trimStyle = {
    "--trim-top": theme.ornamentTop ?? "40%",
    "--trim-offset": theme.ornamentOffset ?? "10px",
    "--trim-height": theme.ornamentHeight ?? "360px",
  } as CSSProperties;
  return (
    <EditorialFrame
      pageNumber={`M${moduleInfo.number}`}
      pageClassName="editorial-page--module module-content-page"
    >
      <img className={`module-content-page__trim module-content-page__trim--${theme.ornamentLayout}`} style={trimStyle} src={theme.ornamentAsset} alt="" aria-hidden="true" />
      <section className="editorial-content general-editorial module-content-page__content" style={style}>
        <header className="module-content-page__chapter">
          <span className="module-content-page__number">{moduleInfo.number}</span>
          <div>
            <small>{moduleInfo.subtitle}</small>
            <h1>{moduleInfo.title}</h1>
            <p>{theme.motif}<i />{theme.description}</p>
          </div>
        </header>
        <section className="general-editorial__section module-content-page__intro">
          <h2>{GENERAL_CONTENT_PAGE.introductionTitle}</h2>
          <p>{GENERAL_CONTENT_PAGE.introduction}</p>
        </section>
        <section className="general-editorial__section">
          <h2>{GENERAL_CONTENT_PAGE.sectionTitle}</h2>
          <h3>{GENERAL_CONTENT_PAGE.directionTitle}</h3>
          <h4>{GENERAL_CONTENT_PAGE.roleTitle}</h4>
          <p>{GENERAL_CONTENT_PAGE.role}</p>
        </section>
        <section className="general-editorial__section general-editorial__fit">
          <h4>{GENERAL_CONTENT_PAGE.fitTitle}</h4>
          <ul>{GENERAL_CONTENT_PAGE.fitPoints.map((point) => <li key={point}>{point}</li>)}</ul>
        </section>
        <table className="general-editorial__table">
          <thead><tr>{GENERAL_CONTENT_PAGE.table.headings.map((heading) => <th key={heading}>{heading}</th>)}</tr></thead>
          <tbody>{GENERAL_CONTENT_PAGE.table.rows.map((row) => <tr key={row[0]}>{row.map((cell) => <td key={cell}>{cell}</td>)}</tr>)}</tbody>
        </table>
      </section>
    </EditorialFrame>
  );
}
