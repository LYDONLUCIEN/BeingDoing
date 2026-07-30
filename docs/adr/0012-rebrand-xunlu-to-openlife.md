# ADR-0012: 品牌更名——寻路 (xunlu) → 寻路·OpenLife (openlife)

**状态**: accepted
**日期**: 2026-07-28（同日修订：品牌定稿由「寻路·LifeAsk」改为「寻路·OpenLife」，域名同步改为 openlife.beyondego.me，替换逻辑不变）
**决策者**: 产品 + 开发 Grill

## 背景

产品原品牌为「寻路 (xunlu)」，生产域名 `xunlu.beyondego.me`。因品牌升级需要，全面更名为「寻路·OpenLife」：

- **中文语境**：`寻路·OpenLife`（间隔号 U+00B7 连接，不连写、不用全角・）
- **英文/域名/代码语境**：`OpenLife` / `openlife`（域名、文件名、配置值一律小写）
- **新生产域名**：`openlife.beyondego.me`

更名前排查确认：JWT payload、数据库表/字段、API 路径、cookie 名、localStorage key（`bd-` 前缀）均不含旧品牌名，**不涉及任何数据迁移**；品牌文案 90% 集中于前端 4 个 i18n 文件与后端 PDF/邮件服务。

## 决策

1. **品牌书写口径**：中文一律「寻路·OpenLife」，英文一律 OpenLife/openlife；旧称「寻路 / xunlu / Xunlu / XUNLU」在新文案中禁用。术语已沉淀至 `CONTEXT.md`「品牌名 (Brand Name)」。
2. **域名迁移**：`xunlu.beyondego.me` → `openlife.beyondego.me`，旧域名 nginx 301 永久跳转到新域名；CORS 白名单只保留新 origin。
3. **支付宝回调**：`ALIPAY_NOTIFY_URL` / `ALIPAY_RETURN_URL` 从 `career.beyondego.me` 迁至 `openlife.beyondego.me`（需在支付宝开放平台同步修改授权回调域）。**这是本次唯一触碰的 career 项**——借此统一生产域名口径。
4. **品牌图片**：PDF 报告用 4 张图（主 logo / 页眉 / 页脚 / 水印）由产品侧重制，图内文字「寻路·OpenLife」，文件重命名为 `openlifelogo.png` / `openlifelogo_header.png` / `openlifelogo_footer.png` / `watermark_logo.png`，代码同步改引用。
5. **不改的部分**：
   - 联系邮箱 `xunlu.lab@outlook.com`（隐私政策/用户协议 ×2）——真实邮箱账号，暂不随品牌变更；
   - 内部不可见命名：`beingdoing-*` systemd 服务名、`bd-` localStorage 前缀、tmux session 名——改动无收益且有风险；
   - 历史遗留：`report/` KATE 品牌工具、`career-guide-frontend` 包名、docker `career_guide` 库名、`scripts/maintenance.sh` 的 zhiyinapp 旧路径——career 系列为生产在用的 dev 站/依赖项，不动；
   - `wiki/`、`kimi/`、`docs/` 下历史文档保持原样（它们记录的是历史状态），仅更新 `AGENTS.md` / `CLAUDE.md` / `CONTEXT.md` 三份主文档。

## 理由（拒绝的备选）

- **双域名并行**：SEO 不友好且公告环境判定（`siteNotices.ts` 按域名前缀判 prod）会长期背负双前缀逻辑；301 跳转既保老链接又保持单一口径。
- **顺带清理 career/KATE 等历史遗留**：career.beyondego.me 是生产在用的 dev 站，docker DB 名与包名变更会波及部署与依赖，爆炸半径远大于收益；更名应一次只改一个变量（同 ADR-0011 的演进原则）。
- **logo 沿用旧文件名覆盖**：文件名与内容不符会留下长期困惑，重命名 + 代码同步引用的成本仅两行。

## 影响

- 代码改动集中在：前端 i18n 四文件（`zh/en/legal.zh/legal.en.ts`）、`app/layout.tsx`、`maintenance.html`、`report_pdf_service.py`（封面/水印/文件名/logo 引用）、`batch_export_service.py`、邮件三服务（`email_service.py` / `payment_service.py` / `feedback_service.py`）、`settings.py` 默认值、`main.py`（title/CORS）、`siteNotices.ts`（prod 域名判定）、提示词（`report_system.yaml` / `rumination_v4_prompt.py`）。
- 运维配套（1panel/nginx）：新建 openlife 站点 + TLS、xunlu 站改 301、维护页目录迁移（`/opt/1panel/www/sites/xunlu/` → `.../openlife/`）并同步 `.env.prod` 的 `MAINTENANCE_FLAG_PATH` / `MAINTENANCE_PAGE_DIR`、支付宝平台回调域变更。
- 切流窗口内已发出的含旧域名链接的邮件（验证/重置类，短时有效）可能失效，可接受；激活码邮件为长效内容但链接均由 `FRONTEND_URL` 生成，切流后新发邮件即新域名。
- 随本次更名同步上线「落款签名」（CONTEXT.md：Report Signature）：PDF 报告末尾随机分配一张引导师签名图并持久化到 `record.json` 的 `report_signature` 字段，保证同一报告再生成签名不变。
