# ADR-0021: 移除 WeasyPrint 简洁版，xunlu 设计版成为唯一报告渲染引擎

**状态**: accepted
**日期**: 2026-09-23
**决策者**: 产品 + 开发 Grill
**取代**: ADR-0019 的「开关共存」部分（渲染器本体与元数据契约不变）

## 背景与动机

ADR-0019 引入 xunlu 精简渲染器时采用双引擎开关共存：`RENDER_ENGINE` 默认 `weasyprint`（简洁版约 1MB），admin 可运行时切换到 `xunlu`（设计版约 9MB）。生产从未切换过运行时配置，也未设置 env 覆盖 —— **线上用户拿到的报告一直是简洁版**，与设计版版式质量差距明显（产品结论：简洁版观感不可接受）。

xunlu 渲染链路已经过 admin 灰度接口（`/admin/reports/{id}/render-pdf`、`/admin/render-pdf-from-md`）验证可用；`src/report-renderer/dist/` 提交入库生产免构建，Chrome headless 实测渲染正常。

## 决策

- **xunlu 为唯一报告渲染引擎**，无任何开关/回退。渲染失败（未构建 / Chrome 异常 / 超时）直接报错给用户，宁可不发也不发简洁版。
- **PDF 即时渲染不落盘**（缓存仅 markdown），故无需任何存量迁移：引擎移除后，新旧报告下次下载即自动出设计版。
- 删除项：
  - `settings.RENDER_ENGINE` 配置项；
  - `app/services/report_render_config.py`（运行时配置模块）与 `data/report_render_config.json` 机制；
  - `GET/POST /api/v1/admin/report-render-config` 端点与 admin 报告页「PDF 渲染引擎」单选 UI、`lib/api/admin.ts` 对应封装；
  - `report_pdf_service` 内 WeasyPrint 渲染路径（HTML/CSS 主题注入、水印、信件容器、总览页 `_overview_page_html`、签名区块 `_signature_block_html`、`_image_data_uri`、`_load_report_theme`/`_apply_theme`）；
  - `app/static/styles/report_pdf.css` 与 `report_theme.json`（weasyprint 专用样式，已无引用）。
- 保留项：`REPORT_RENDERER_DIR` / `REPORT_RENDERER_NODE` / `CHROME_PATH` / `REPORT_RENDER_TIMEOUT` 配置；`report_xunlu_renderer.py` 桥接与元数据契约（签名/日期/昵称）；admin 重渲染与 md 直渲调试端点（原「强制 xunlu」语义自然消失）。
- **weasyprint 依赖保留在 requirements.txt**：`export_service.export_to_pdf`（会话导出）仍在使用。

## 影响

- `_markdown_to_pdf` 变为 `_markdown_to_pdf_via_xunlu` 的薄委托，调用方（用户下载 `export.py`、admin 下载/staging 预览）零改动。
- 回滚方式：git revert（无运行时开关可切回）。
- 测试：`test/backend/test_report_xunlu_renderer.py` 删除引擎分流/运行时配置相关用例，保留渲染桥接、元数据映射与 admin 端点用例。
