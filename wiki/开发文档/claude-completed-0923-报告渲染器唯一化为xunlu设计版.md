# 0923 报告渲染器唯一化为 xunlu 设计版（移除 WeasyPrint 简洁版）

## 背景

ADR-0019 引入 xunlu 渲染器时采用双引擎开关，`RENDER_ENGINE` 默认 `weasyprint`，生产从未切换 —— 线上报告一直是简洁版（观感不可接受）。决策：彻底移除简洁版，xunlu 设计版为唯一引擎。详见 `docs/adr/0021-single-xunlu-report-renderer.md`。

## 关键事实

- **PDF 即时渲染不落盘**（仅缓存 markdown），因此无需存量迁移：移除引擎后新旧报告下次下载自动出设计版。
- xunlu 链路实测可用：`src/report-renderer/dist/` 已构建入库、Chrome headless 端到端渲染验证通过（exit 0、合法 PDF）。
- 渲染失败直接报错，无兜底（宁可不发也不发简洁版）；回滚 = git revert。

## 改动清单

**后端**
- 删 `app/services/report_render_config.py`（运行时配置模块）、`settings.RENDER_ENGINE`。
- 删 `GET/POST /api/v1/admin/report-render-config` 端点（`admin.py`）。
- `report_pdf_service.py`：`_markdown_to_pdf` 变为 `_markdown_to_pdf_via_xunlu` 薄委托；删除 WeasyPrint 渲染路径（HTML/CSS 主题注入、水印、信件容器、`_overview_page_html`、`_signature_block_html`、`_image_data_uri`、`_load_report_theme`/`_apply_theme`、`md_lib`/`re` import）。
- 删孤儿样式 `app/static/styles/report_pdf.css`、`report_theme.json`；**weasyprint 依赖保留**（`export_service` 会话导出仍用）。

**前端**
- 删 admin 报告页「PDF 渲染引擎」单选 UI 及 state；删 `lib/api/admin.ts` 的 `fetchReportRenderConfig`/`updateReportRenderConfig`/`ReportRenderConfig`。
- `tsc --noEmit` 通过。

**测试**
- `test_report_xunlu_renderer.py`：删引擎分流/运行时配置用例，保留渲染桥接、元数据映射、admin 端点用例 —— 10 passed。
- 存量失败（`test_admin_batch_export.py` 7 项、`test_rumination_opening_chain.py` 2 项）在未修改基线同样失败，与本次无关。

## 遗留提醒

- admin 两个调试端点（`/reports/{id}/render-pdf`、`/render-pdf-from-md`）保留，原「强制 xunlu」注释语义已更新。
- 旧配色文档 `wiki/开发文档/0812-报告配色配置说明.md` 所述 `report_theme.json` 已删除（weasyprint 专用，设计版配色在 `src/report-renderer` 内）。
