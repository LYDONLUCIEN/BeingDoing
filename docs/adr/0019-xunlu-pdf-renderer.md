# ADR-0019: 报告 PDF 渲染接入 xunlu 精简渲染器（子进程 + 开关共存）

**状态**: accepted
**日期**: 2026-08-20
**决策者**: 产品 + 开发 Grill

## 背景

原报告 PDF 渲染为 WeasyPrint（`report_pdf_service._markdown_to_pdf`，markdown → HTML → PDF bytes，即时渲染不落盘）。新报告设计项目 `report/xunlu`（Next.js/vinext + React + Chrome headless 打印）产出的 A4 排版质量显著更优（31 页设计版式、八模块主题、封面/总览/签名体系），但整个项目含大量演示/对比页面（交互阅读器、8 个独立模块路由、design-options 等），且 markdown 输入是构建期 `?raw` 硬编码导入，无法直接服务化。

## 决策

- **精简渲染模块**：新建 `src/report-renderer/`，从 `report/xunlu` 抽取核心渲染闭包（markdown-parser + markdown-report + report-pages/overview/config/design/page-content + 裁剪版 CSS，约 1000 行），`react-dom/server` 出静态 HTML + Chrome headless `--print-to-pdf` 出 PDF。**`report/xunlu` 保持只读不动**，作为设计/素材母版；渲染效果与母版一致（同输入同输出，样例报告逐页分页一致）。
- **衔接方式**：FastAPI 子进程调用（`subprocess.run node dist/render-pdf.mjs`，md/输出走临时文件，同步拿 bytes），无新常驻服务、无端口、无 nginx 变更。契约保持 `markdown: str → pdf: bytes`。
- **开关共存**：新增 `RENDER_ENGINE`（`weasyprint` 默认 / `xunlu`），在 `_markdown_to_pdf` 顶部单点分流；用户下载（`export.py`）与 admin staging 预览（`admin.py`）两个调用方零改动。WeasyPrint 链路完整保留兜底，回滚 = 改回环境变量。**2026-08-20 起升级为运行时配置**：admin 报告页「PDF 渲染引擎」单选（简洁版 WeasyPrint 约 1MB / 设计版 xunlu 约 9MB），`GET/POST /admin/report-render-config` 读写 `data/report_render_config.json`（`report_render_config.py`，mtime 缓存），优先级 运行时 > env > 默认，即时生效无需重启。
- **md 直渲端点**：新增 `POST /api/v1/admin/render-pdf-from-md`（super admin），body `{markdown, nickname?, date?, signature?}` → PDF。**强制走 xunlu 渲染器**（不受开关影响），供灰度前调试渲染效果与素材替换；仅接口，无前端 UI。
- **元数据动态传入**：封面昵称由渲染器从 md「{昵称}的寻路之旅」标题提取（兜底「探索者」）；日期取 record.json `report_markdown_generated_at`（缺失取当天）；签名沿用 record.json `report_signature`（`signature_1/2/3` 按下标映射渲染器 `signature-01/02/03`）。
- **字体内嵌**：渲染器内嵌 Noto Serif SC 400/500/600/700（`assets/fonts/`，来源 npm `@expo-google-fonts/noto-serif-sc`），消除服务器无衬线中文字体导致的版式漂移。

## Markdown 方言适配（渲染器输入归一化层 `src/normalize.ts`）

主流程真实报告与 xunlu 样例方言不同，归一化层在 parser 之前处理（对 xunlu 原生样例为恒等变换）：

1. 分页符统一：旧式 `<div STYLE="page-break-after: always;"></div>` / `<<<PAGEBREAK>>>` → `<div class="pb"></div>`（存量缓存报告两种并存）。
2. 行首 `* ` 列表 → `- `（同 `report_postprocess._STAR_LIST_RE` 口径，存量报告未过后处理管线）。
3. h5/h6 → h4（parser 只识别 1-4 级）。
4. 章节标题提升：段内首个标题为 `##/### 第X章` 时提升为一级（parser 以段内首个一级标题为章标题；存量有 `#`/`##`/`###` 三种写法）。其余三级小节标题不动（保持强调样式）。
5. 职业角色章识别泛化（parser 内）：`/^开篇[:：]/` 标记 + 动态角色名/英文名（原硬编码「个人故事整理师」仅作兜底）。

已知限制：parser 不支持有序列表与链接（并入段落文本），本次不扩展。

## 实现

- `src/report-renderer/`：`src/render.tsx`（CLI 入口）+ `src/normalize.ts` + `src/core/*`（拷贝自 xunlu 并最小修改：去 next/link、元数据参数化、role 识别泛化）+ `src/styles/report.css`（globals.css 裁剪版，删 tailwind import 与演示页区段）+ `assets/report-assets/`（正式链路素材拷贝）+ `assets/fonts/`；esbuild 打包 `dist/render-pdf.mjs`（提交入库，生产免构建）。
- 素材以 `file://` 绝对路径注入（Chrome 加 `--allow-file-access-from-files`）；A4 零边距由 CSS `@page` 保证。
- 去掉原版封面 meta 的 `backdrop-filter`：Linux headless Chrome 打印会让该元素整体丢失（Mac Chrome 正常），背景色已接近不透明，视觉无差。
- 后端：`settings.py` 新增 `RENDER_ENGINE` / `REPORT_RENDERER_DIR` / `REPORT_RENDERER_NODE` / `CHROME_PATH` / `REPORT_RENDER_TIMEOUT`（默认 120s）；`app/services/report_xunlu_renderer.py`（子进程桥接，超时→`XunluRenderTimeout`，非零退出→`XunluRenderError` 带 stderr 摘要）；`report_pdf_service._markdown_to_pdf_via_xunlu`（元数据组装 + 分流）；admin 端点经 `asyncio.to_thread` 避免阻塞事件循环。
- **admin 「重新渲染」链路**（与「重新生成」语义区分：生成=LLM 出新 markdown；渲染=现有 markdown 出新版式 PDF，因 PDF 本就即时渲染不落盘，天然成立）：`GET /admin/reports/{id}/render-pdf`（super admin，强制 xunlu 引擎，无缓存 409）+ 前端报告列表行「重渲染PDF」按钮（`lib/api/admin.ts renderAdminReportPdf`，blob 下载）；运维脚本 `scripts/rerender_report.sh <激活码> [输出目录]`（反查 record.json → 检查 markdown 缓存 → 自动带签名/日期 → 渲染）。
- **按钮语义与「生成中」状态恢复**（2026-08-20）：admin 列表「下载PDF」改为**纯渲染下载**（先查状态，md 不存在不再隐式触发 LLM 生成，报错提示）；「生成中」按钮态的真源在后端单轨锁——新增 `GET /admin/reports/generating`（`list_generation_inflight`），admin 列表页 3s 轮询恢复按钮态，刷新页面不丢；用户报告页原本就有同等恢复（mount 时 `check()` → generating 则 `prepare()` 接管轮询）；重渲染按钮的「渲染中」为请求内同步态（5-10s，刷新即取消，可接受）。
- 测试：`src/report-renderer/tests/normalize.test.mjs`（7 项，含 xunlu 样例恒等变换断言）；`test/backend/test_report_xunlu_renderer.py`（13 项：默认引擎/分流与元数据映射/weasyprint 不触碰/未构建报错/直渲端点 403·200·400/render-pdf 端点 403·409·200）。

## 后果

- `RENDER_ENGINE=xunlu` 时用户下载与 admin staging 预览走新渲染器；默认 `weasyprint` 行为与现状完全一致。
- 渲染耗时约 5-10s（Chrome 冷启动 + 31 页打印），与 WeasyPrint 同量级；下载口径仍为即时渲染不落盘。
- 部署前提：服务器需 Node ≥20 与 Chrome/Chromium（`CHROME_PATH` 可指定）；`src/report-renderer` 已构建（dist 入库）则无需 npm install。
- 素材替换流程：在 `report/xunlu` 母版更新素材后，重新拷贝 `public/report-assets/` 对应文件到 `src/report-renderer/assets/report-assets/` 即生效（即时渲染，无需重生成报告）。
- 后续可选：验证稳定后把默认值切到 `xunlu`；WeasyPrint 链路再评估下线。
