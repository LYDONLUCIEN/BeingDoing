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
assets/report-assets/ 正式链路素材（封面/页脚/签名/logo/hero/卡片×8/边饰×8/帆船/水印带）
  ├─ editorial/guide-brush-bar.png   阅读指南首页横条（2026-08-21 新增）
  ├─ editorial/letter-frame.png      信件页水彩框背景（2026-08-21 新增）
  └─ brand/watermark-logo.png        每页 3 条 45° 水印带（抠图版裁透明边，内容层之上）
assets/fonts/         内嵌 Noto Serif SC 400/500/600/700（服务器无衬线中文字体时保证一致）
scripts/calibrate_assets.py  新素材校准管线：白点缩放统一底色到纸色 #fffdf9 +
                      横条中间带自动裁剪（输入 uidesign/report/*.png）
tests/                node:test 单测（npm test）
```

## 素材校准与融合（2026-08-21 起）

- 封面等全幅素材：白点缩放把底色精确对齐到纸色 `#fffdf9`（`scripts/calibrate_assets.py`）。
- **抠图素材直接用（首选）**：`report/抠图/*-抠图.png`（hero/帆船/logo-mark/页脚标识A/
  指南横条/信件框）——背景已抠净的 RGBA 原图直接拷贝，页面 CSS 纸色精确透出，效果最好。
- 无抠图版的母版装饰素材（竖向边饰/签名/页脚标识BC）：Color-to-Alpha 透明化
  （脚本第 3 步自动从母版重新拷贝后处理，可重跑）。
- **不要**用「白底 + CSS `mix-blend-mode: multiply`」——实测 Chrome headless 打印
  不支持 multiply 与页面背景混合；不透明图片与 CSS 纸色也无法完全相等（ICC 色偏 1-2 级）。
- 验证方法：`pdftoppm -png -r 100` 后采样对比「图内背景 vs 页面纸色」，Δ≤1~2 级为融合达标。

## 与母版同步规则

- **素材替换**：uidesign 新素材先过 `python3 scripts/calibrate_assets.py`（校准+裁剪）再使用；母版 `report/xunlu` 的 `public/report-assets/` 更新后，把对应文件重新拷到 `assets/report-assets/`（PDF 即时渲染，拷贝即生效，无需重生成报告）。
- **渲染逻辑/版式修改**：改母版 `app/generated-report/`、`app/report-*.ts*`、`app/module-content.tsx`、`app/globals.css` 后，同步到 `src/core/` 与 `src/styles/report.css`，重新 `npm run build && npm test`，并用母版样例 `content/reports/mixkz-report.md` 对拍页数与版式。
- 反向修改禁止：本模块的方言适配（normalize.ts、role 识别泛化、元数据参数化）不回流母版。

## 已知限制

- markdown 方言仅支持：1-4 级标题、`**粗体**`、`-` 无序列表、GFM 表格、`<div class="pb"></div>` 分页符；有序列表/链接/图片会并入段落文本。
- 封面 meta 区去掉了母版的 `backdrop-filter`（Linux headless Chrome 打印会整元素丢失），视觉无差。
