# ADR-0011: 存储演进路线——稳定性收敛 → SQLite 全量入库 → 条件触发 PostgreSQL

**状态**: accepted
**日期**: 2026-07-26
**决策者**: 产品 + 开发 Grill

## 背景

当前存储为混合架构：账户/支付订单/折扣券/咨询/埋点等 29 张表在 SQLite；而**核心业务数据在 JSON 文件**——激活码（`data/simple/activations.json`）、报告元信息与审核状态（`record.json`）、对话消息全文（`{phase}__{thread_id}.json` + `.lock` 文件锁）、rumination 进度、用户问卷 basic_info。由此产生三个既有问题：

1. **双写不一致**：admin 改激活码归属需双写 `activations.json` + `record.json`，失败仅留补偿日志，数据可永久处于半边不一致状态；
2. **并发脆弱**：`.lock` 文件锁仅单进程有效，多 worker/多实例即失效；
3. **备份无一致快照点**：`app.db` 与 `data/` 目录是两坨独立数据，任何备份时刻都可能横跨一次未完成的写入。

历史上激活码曾在 DB 中（`upsert_from_db_rows` 的 db_sync 遗留），后迁至 JSON 属 simple 模式图省事的历史偶然，非设计决策。

生产环境为单实例 2C4G（uvicorn 无 workers + nginx 反代），1 年内预期维持单实例。

## 决策

分四个阶段演进，**一次只改一个变量**：

- **阶段 0（当前）：稳定性收敛 → 打 tag v1.6.0。** 只验收三件事：① 支付闭环在新域名下走通真实小额订单全程（下单→支付→异步回调→发码→码可用，重点验证 `ALIPAY_NOTIFY_URL`/`ALIPAY_RETURN_URL` 换域名后的可达性）；② 新域名基础链路（HTTPS、SSE 流式不断流、JWT 刷新）；③ 核心用户旅程回归（注册→试用码→10 轮拦截→完整码→5 阶段→出报告）。**此期间存储层改动冻结。**
- **阶段 1：JSON → SQLite 全量入库。** 激活码、报告元信息/审核状态、对话消息全文、rumination 进度、basic_info、业务审计日志全部设计为 DB 表（含迁移脚本与读写层重写，对外接口不变）。对话消息入库的裁决依据：一致性优先于"文件好查看"——开发期查看/批量修改由 DB 工具（GUI + 事务内 UPDATE）解决，而非保留文件。**留在磁盘的仅**：PDF 成品、反馈截图等二进制附件（DB 存路径）、归档/备份目录、admin_mock 模板、应用运行日志。
- **阶段 2：SQLite → PostgreSQL，条件触发。** 三扳机任一命中即切：① 后端需开 `--workers ≥ 2`；② SQLite 频发 `database is locked`（真实并发写冲突出现）；③ 换机扩容至 4C8G 以上（顺手为之）。均不命中则不切——单实例中小流量下 SQLite 可靠性足够。
- **不做的事**：不引入第二个数据库（埋点/分析与业务库同库，避免跨库拼接重演 DB+JSON 拼接之痛）；应用运行日志不入任何数据库（文本文件 + logrotate，避免"库挂了连日志都看不了"）；PG 如需隔离用 schema 而非多 database。

## 理由（拒绝的备选）

- **直接一步上 PG（JSON→PG 同时做）**：schema 从零设计（90% 工作量）与引擎切换（10%）是复合变更，出 bug 难分因、回滚是双重回滚；且 2C4G 上阶段 1 零运维成本，PG 调优后虽可运行（常驻约 100MB），但没有提前承担的理由。
- **对话消息留文件**：体量大、写后不改，文件本可接受；但留 41MB 文件目录在外，"全量一个 dump 带走"的备份一致性闭环永远有缺口，且与一致性优先的原则冲突。
- **PG 默认配置恐惧**：PG 名声来自独占服务器的默认配置，调小 shared_buffers 后在 2C4G 上可与主程序共存；资源约束是阶段 2 的考量，不是否定 PG 的理由。

## 后果

- 阶段 1 后：`activations.json` / `record.json` / 对话 JSON / `rumination*_progress.json` / `basic_info.json` / 审计 jsonl 全部废止为数据源（可归档）；`.lock` 文件锁与双写补偿逻辑删除；admin 列表页从扫目录改为 SQL 查询。
- `docs/历史文档/DATA_STORAGE_SIMPLE.md` 的"JSON 是唯一主数据源"口径在阶段 1 完成后作废，需重写存储文档。
- alembic 迁移已做方言判断（005）、模型 JSON 字段均为 Text，阶段 2 切换仅需改 `DATABASE_URL` + 跑迁移 + 数据搬迁，预计一两天工作量。
- `.env.prod` 中注释掉的 postgresql 示例在阶段 2 启用并补全调优参数。
