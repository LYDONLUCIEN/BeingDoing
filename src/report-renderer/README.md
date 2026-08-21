# xunlu 报告精简渲染器

把报告 markdown 渲染成寻路 A4 设计版式的 PDF。渲染核心抽取自设计母版 `report/xunlu`（**母版只读，不要改动**），不依赖 Next/vinext 常驻服务：

```
markdown → normalize（方言归一化）→ markdown-parser（解析/分页）→ React 组件装配
        → react-dom/server 出静态 HTML（CSS + 素材 file:// 注入 + 内嵌字体）
        → Chrome headless --print-to-pdf → PDF
```

## 使用

```bash
npm install        # 首次
npm run build      # 产出 dist/render-pdf.mjs（已提交入库，仅改源码后需重建）

node dist/render-pdf.mjs --md 报告.md --out 报告.pdf \
  [--nickname 昵称] [--date "2026 年 08 月 20 日"] [--signature 01|02|03] \
  [--keep-html 调试.html] [--chrome /path/to/chrome]
```

- 昵称缺省从 md 的「{昵称}的寻路之旅」标题提取，兜底「探索者」；日期缺省取当天；签名缺省用 `src/core/report-design.ts` 的当前设计值。
- 运行要求：Node ≥ 20 + Chrome/Chromium（自动探测 `/usr/bin/google-chrome` 等，或 `--chrome`/`CHROME_PATH` 指定）。
- 后端集成见 ADR `docs/adr/0019-xunlu-pdf-renderer.md`（FastAPI 子进程调用，`RENDER_ENGINE` 开关）。

## 目录

```
src/render.tsx        CLI 入口（参数解析/HTML 拼装/素材注入/Chrome 打印）
src/normalize.ts      输入归一化（旧分页符、* 列表、h5/h6、章节标题层级提升、昵称提取）
src/core/             渲染核心（拷贝自 report/xunlu/app，最小修改：去 next/link、
                      元数据参数化、role 章识别泛化）
src/styles/report.css 母版 globals.css 裁剪版（仅正式报告链路；分页估算与排版尺寸
                      强耦合，字号/行高/间距不要改）
assets/report-assets/ 正式链路素材（封面/页脚/签名/logo/hero/卡片×8/边饰×8/帆船）
assets/fonts/         内嵌 Noto Serif SC 400/500/600/700（服务器无衬线中文字体时保证一致）
tests/                node:test 单测（npm test）
```

## 与母版同步规则

- **素材替换**：在 `report/xunlu` 更新 `public/report-assets/` 后，把对应文件重新拷到 `assets/report-assets/`（PDF 即时渲染，拷贝即生效，无需重生成报告）。
- **渲染逻辑/版式修改**：改母版 `app/generated-report/`、`app/report-*.ts*`、`app/module-content.tsx`、`app/globals.css` 后，同步到 `src/core/` 与 `src/styles/report.css`，重新 `npm run build && npm test`，并用母版样例 `content/reports/mixkz-report.md` 对拍页数与版式。
- 反向修改禁止：本模块的方言适配（normalize.ts、role 识别泛化、元数据参数化）不回流母版。

## 已知限制

- markdown 方言仅支持：1-4 级标题、`**粗体**`、`-` 无序列表、GFM 表格、`<div class="pb"></div>` 分页符；有序列表/链接/图片会并入段落文本。
- 封面 meta 区去掉了母版的 `backdrop-filter`（Linux headless Chrome 打印会整元素丢失），视觉无差。
