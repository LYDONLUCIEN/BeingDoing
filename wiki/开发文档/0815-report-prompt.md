# 报告生成提示词、流程与渲染素材说明（2026-08-15）

> 面向需要调整报告生成提示词、报告样式/素材的同学。本文梳理：提示词位置、完整生成流程、注入的用户变量、图表/渲染链路、素材文件清单与调整入口。

---

## 一、报告生成提示词位置

**主提示词（唯一一个大提示词，一次性生成整份报告）：**

```
src/backend/app/domain/prompts/templates/report_system.yaml
```

- 202607 版八章框架，约 290 行，Jinja2 模板。
- 通过 `src/backend/app/domain/prompts/loader.py` 的 `DomainPromptLoader.render("report_system", context)`（loader.py L31-46）先 YAML 解析再 Jinja2 渲染。
- 章节结构（LLM 一次输出全部）：
  - 扉页（`{{ user_nickname }}的寻路之旅` + 阅读指南，固定内容原样输出）
  - 开篇：职业角色（800 字内）
  - 第一章~第八章：价值观分析 / 优势分析 / 热爱分析 / 使命分析 / 最终选择 / 关键洞察 / 其余职业方向推荐 / 谁与你最接近（名人画像）
  - 致 `{{ user_nickname }}` 的一封信（800 字内，书信体）
- 格式契约：列表用 `-`、标题最多 h4、每章末尾插分页标记 `<<<PAGEBREAK>>>`、直接输出 Markdown；**明确约定"如需图表辅助说明，请以 Markdown 表格或文本图形呈现"**（见下文第四节）。

### 后处理修正管线（ADR-0017：一次生成 + 按章节分步修正）

**`src/backend/app/services/report_postprocess.py`**（约 221 行），入口 `apply_report_postprocess(markdown_text, llm_call)`（L197）：

| 处理器 | 类型 | 函数 |
|---|---|---|
| 分页标记规范化 | 确定性 | `_normalize_pagebreaks`（L55）：`<<<PAGEBREAK>>>` / 旧式内联 div → `<div class="pb"></div>` |
| 列表规范化 | 确定性 | `_normalize_lists`（L74）：`*`→`-`，列表块前后补空行 |
| 标题层级归一化 | 确定性 | `_normalize_headings`（L103）：h5/h6→h4 |
| 信件压缩器 | LLM 修正器 | `_compress_letter`（L164）：信 >700 字时用内联 prompt `_LETTER_COMPRESS_PROMPT`（L151-161）压到 550-650 字，失败回退原文 |

原则：任一修正器失败保留原文；框架可插拔扩展新的修正器。决策记录：`docs/adr/0017-report-post-processing-pipeline.md`。

---

## 二、完整生成流程

三条触发路径，统一走 `report_pdf_service` 单轨锁（`_generation_inflight`，report_pdf_service.py L99-121），同报告不并发：

```
【路径1 审核预生成】GET /export/my-report-id（用户进报告页）
  → export.py:322 _ensure_review_started（L278）
  → export.py:301 _kick_pdf_generation（L240）

【路径2 批复自动生成】POST /admin/reports/{id}/approve（admin.py L964 人工批复）
  或 APScheduler 超时自动批复 auto_approve_overdue（report_review_service.py L201）
  → report_review_service.py approve_report（L158）
  → 五阶段完成时 kick_report_generation（L126）→ asyncio 后台任务

【路径3 手动生成】POST /export/report-pdf/{report_id}（export.py L446）
  → 完成度门控 409 / 审核阻塞 / 普通用户 force 限 2 次（record.report_regen_count，成功才计数）
  → _kick_pdf_generation（L505）

三条路径汇合：
  → ReportPdfService.generate_markdown_only（report_pdf_service.py L184）
  → _generate_report_markdown（L461）：
      1. _collect_phase_data（L231）        收集四维结论卡
      2. _collect_profile_async（L528）     用户 profile（可选）
      3. _collect_nickname（L346）          昵称
      4. _collect_conversation_block（L388）五阶段对话全文
      5. render("report_system", context)（L480）渲染提示词
      6. LLM 流式生成（get_default_llm_provider，L509；
         messages = [system=完整prompt, user="请开始撰写报告。"]，temperature=0.7）
      7. apply_report_postprocess（L504）   后处理管线
  → _save_cached_markdown（L665）：
      写 data/simple/reports/{report_id}/report_markdown.md
      + record.json 记 report_markdown_generated_at

下载时即时渲染 PDF（markdown 不重复生成）：
  GET /export/report-pdf-download/{id}（export.py L576）
  → load_cached_markdown → _markdown_to_pdf（report_pdf_service.py L790）
  → python-markdown 转 HTML → 拼封面/总览页/水印/字体/CSS → WeasyPrint write_pdf
```

**生成产物：**
- markdown 缓存：`data/simple/reports/{report_id}/report_markdown.md`（测试/沙箱：`data/test/simple/reports/...`）
- 缓存过期判定：结论卡 updated_at > generated_at（`_is_cache_expired` L613）
- PDF：下载时即时渲染，不落盘缓存

---

## 三、Prompt 注入的用户变量清单

`_generate_report_markdown`（report_pdf_service.py L474-479）渲染 context 共 8 个变量：

| 变量 | 数据源 | 收集函数 |
|---|---|---|
| `values_block` / `strengths_block` / `interests_block` / `purpose_block` | `data/simple/reports/{rid}/dimension_conclusions.json`（四维结论卡快照）：`final_answer`（确认结论）、`keywords`、`summary`/`ai_summary`；purpose 另有 `mission_core`/`mission_detail` | `_collect_phase_data`（L231）→ `survey_storage.load_dimension_conclusions`（L236） |
| `rumination_block` | `data/simple/reports/{rid}/rumination_v4_progress.json`：`final_selection.selected_combo_ids` 命中的 combo（passion、strengths、结论卡 hypothesis/motivation/work_purposes/passion_mark/timing_mark） | `_collect_rumination_block`（L284）→ `rumination_v4_service.load_v4_state`（L119） |
| `conversation_block` | `data/simple/reports/{rid}/{step_id}__{session_id}.json` 五阶段对话全文：只保留 user/assistant 消息，单阶段 >20000 字符时头 6000 + 尾保留、中间省略 | `_collect_conversation_block`（L388）；STEP_IDS=[values,strengths,interests,purpose,rumination]（report_registry.py L99） |
| `user_nickname` | basic_info 问卷 nickname → `User.username` → 「探索者」兜底 | `_collect_nickname`（L346）→ `survey_storage.load_basic_info_by_user`（L106） |
| `profile_block`（可选） | DB：`User` + `UserProfile` + `WorkHistory`（username、gender、age、工作经历：公司/职位/起止时间） | `_collect_profile_async`（L528） |

**注意：**
- 激活码信息**不进** prompt（仅用于权限校验和 PDF 文件名）。
- 调试工具：`scripts/dump_report_pdf_input.py` 可 dump 实际喂给 LLM 的原始数据块；`scripts/batch_generate_reports.py` 可批量导出报告 markdown。

---

## 四、图表渲染在哪里？（重要结论）

**当前报告中没有任何真正的「数据图表」（雷达图/柱状图/公式图）**——没有 matplotlib、没有 echarts/recharts、没有前端图表组件。

- 报告里的"图表"全部是 **LLM 按提示词输出的 Markdown 表格 / 文本图形**（价值观速查表、方向总结表、使命价值公式等），样式由 PDF CSS 控制。
- 提示词 `report_system.yaml` 明确限定"以 Markdown 表格或文本图形呈现"。
- **不存在"五阶段得分"之类的结构化数值驱动图表**。
- `report/` 目录（`export-pdf.js` + `index2.html`）是**独立的静态原型工具**（Playwright HTML→PDF 手工导出 demo 稿），与生产链路无关；`uidesign/beautiful/` 是设计源文件，同样非生产。
- 前端报告页 `src/frontend/app/(main)/explore/report/view/page.tsx` 只做审核状态门控 + 「生成/重新生成/下载 PDF」按钮，**不在浏览器渲染报告内容**。

### 生产渲染链路

```
report_markdown.md（缓存）
  → python-markdown 转 HTML（extensions=["extra","nl2br"]）
  → 拼装完整 HTML：封面 + 报告模块总览页 + 正文 + 水印层 + 落款签名
     （封面/总览页 HTML 是 report_pdf_service.py 内联 f-string，无独立模板文件）
  → CSS 注入：report_pdf.css + report_theme.json 配色 token 替换 + 字体/logo data URI
  → WeasyPrint write_pdf → PDF bytes
```

> 若想引入真正的图表：WeasyPrint 不支持 JS，需要后端预渲染（SVG 内嵌或图片）并扩展链路，属新功能而非配置调整。

---

## 五、素材文件清单（`src/backend/app/static/`）

| 文件 | 用途 |
|---|---|
| `styles/report_pdf.css` | PDF 全部样式：`@page` 页眉页脚、封面 `.cover`、总览页 `.overview-*`、正文表格、水印 `.watermark-*`、信件 `.letter`、签名 `.report-signature`、分页 `.pb`；内含 `{{token}}` 配色占位符和 `__FONT_DIR_URL__` / `__PAGE_LOGO_HEADER_URL__` / `__PAGE_LOGO_FOOTER_URL__` 占位符 |
| `styles/report_theme.json` | 配色主题 token（页面底色/正文/标题/表格/总览页卡片等 ~30 个），渲染时替换 CSS 占位符 |
| `fonts/NotoSansSC-Regular.ttf` / `-Medium.ttf` / `-Bold.ttf` | 随仓库打包的中文字体，CSS `@font-face` 内嵌，不依赖服务器字体 |
| `assets/watermark_logo.png` | 整页水印图（3 条 45° 斜带，base64 嵌入 HTML） |
| `assets/openlifelogo_header.png` | `@page` 页眉右上角 logo（data URI 注入） |
| `assets/openlifelogo_footer.png` | `@page` 页脚正中 logo（data URI 注入） |
| `assets/openlifelogo.png` | 品牌 logo 备用 |
| `assets/signature_1.png` / `_2.png` / `_3.png` | 报告末尾落款签名图，首次生成随机分配并持久化到 record.json 的 `report_signature` |

设计源文件（非生产，替换素材时可从这里取原图）：`uidesign/beautiful/`（水印/签名/页眉页脚原始图等）。

---

## 六、调整 / 替换入口速查

| 想改什么 | 改哪里 | 是否需重新生成报告 |
|---|---|---|
| 报告章节内容、结构、表格形态 | 提示词 `src/backend/app/domain/prompts/templates/report_system.yaml` | **需要** force 重新生成（普通用户每报告限 2 次，admin 不限） |
| 分页/列表/标题修正规则、信件压缩 | `src/backend/app/services/report_postprocess.py` | 需要重新生成 |
| 配色（正文/标题/表格/卡片颜色） | 只改 `src/backend/app/static/styles/report_theme.json` + 重启后端（详见 `wiki/开发文档/0812-报告配色配置说明.md`） | **不需要**（下载时即时渲染） |
| 版式/表格样式/水印位置/页眉页脚/信件排版 | `src/backend/app/static/styles/report_pdf.css`（注意 `{{token}}` 需在 theme.json 有对应 key） | 不需要，重启后端即可 |
| 字体 | 替换 `static/fonts/` 下 ttf 并同步改 `report_pdf.css` 顶部 `@font-face` | 不需要 |
| 水印 / 页眉页脚 logo | 替换 `static/assets/` 同名 png 即可 | 不需要 |
| 落款签名图 | 替换 `signature_*.png`；新增签名需改 `report_pdf_service.py` 的 `_SIGNATURE_CHOICES` | 不需要（已分配签名的报告不变） |
| 封面 / 报告模块总览页结构 | `report_pdf_service.py`：封面在 `_markdown_to_pdf` 的 full_html f-string（L866-876），总览页在 `_overview_page_html`（L724-786） | 不需要 |

---

## 七、关键文件索引

| 文件 | 作用 |
|---|---|
| `src/backend/app/domain/prompts/templates/report_system.yaml` | 报告主提示词（八章框架） |
| `src/backend/app/domain/prompts/loader.py` | YAML+Jinja2 模板加载器 |
| `src/backend/app/services/report_pdf_service.py` | 核心服务：数据收集（L231-457）、LLM 生成（L461-526）、缓存（L582-679）、PDF 渲染（L790-891）、单轨锁（L104-121） |
| `src/backend/app/services/report_postprocess.py` | ADR-0017 后处理管线 |
| `src/backend/app/services/report_review_service.py` | 审核批复 + 批复后自动生成（`kick_report_generation` L126） |
| `src/backend/app/api/v1/export.py` | 用户侧端点：生成/状态/下载 |
| `src/backend/app/utils/report_registry.py` | 报告 record 注册表、STEP_IDS、对话文件路径 |
| `src/backend/app/utils/survey_storage.py` | 结论卡 / basic_info 加载 |
| `src/backend/app/static/styles/report_pdf.css` + `report_theme.json` | PDF 排版与配色 |
| `scripts/dump_report_pdf_input.py` | dump 喂给 LLM 的原始数据块（调试用） |
| `docs/adr/0017-report-post-processing-pipeline.md` | 后处理管线决策记录 |
