# 寻路·OpenLife

职业探索产品：价值观 → 优势 → 兴趣 → 使命 → 沉淀 → 报告。仓库名仍为 BeingDoing；对外中文品牌使用「寻路·OpenLife」。

当前代码包含 FastAPI 后端、Next.js 前端及独立报告渲染器。账户/交易在 SQLite，探索记录仍在 JSON 文件；全量入库是演进计划，尚未完成。

## 开始开发

1. 阅读 [BeingDoing 现行开发指南](docs/DEVELOPMENT.md)，在独立开发目录安装依赖。
2. 阅读 [贡献规范](CONTRIBUTING.md)，运行与改动相关的测试。
3. 涉及业务时先查 [业务术语](docs/glossary.md)、[字段字典](docs/DATA_DICTIONARY.md) 和 [当前产品规则](docs/PRODUCT_RULES.md)。

## 文档入口

| 需要做什么 | 入口 |
| --- | --- |
| 启动、配置、测试 | [开发指南](docs/DEVELOPMENT.md) · [验证记录](docs/TESTING.md) |
| dev／prod 服务器更新、备份、重启与回滚 | [服务器操作手册](docs/OPERATIONS.md) |
| 找模块、理解存储 | [架构](docs/ARCHITECTURE.md) |
| 接口与权限 | [API 契约](docs/API_DOCUMENTATION.md) |
| 理解字段、状态和跨产品关系 | [字段字典](docs/DATA_DICTIONARY.md) · [新产品边界](docs/PRODUCT_EVOLUTION.md) |
| 安全与本次清理 | [安全评估](docs/SECURITY_REVIEW.md) · [清理依据](docs/CLEANUP.md) · [双轴复审](docs/REVIEW.md) |
| 根目录文件用途、旧文件去向 | [根目录职责与处置索引](docs/ROOT_FILES.md) |
| 理解现行选择、原因和约束 | [架构与开发决策](docs/DECISIONS.md) · [开发变更记录](docs/CHANGELOG.md) |
| 查历史过程和替代关系 | [历史证据](docs/HISTORY_EVIDENCE.md) · [GitHub 全量索引](docs/ISSUE_HISTORY.md) · [ADR 状态](docs/adr/README.md) |

`docs/历史文档/`、[Wiki 历史资料库](wiki/README.md) 和 `tasks/` 保存版本背景、设计与运维记录。Wiki 原“开发文档”已改为“历史开发记录”；保留、删除及旧路径映射见 [资料索引](wiki/资料索引.md)。历史文档中的命令需核对版本，不能替代上面的现行入口。

本次整理基线：`main = v1.8.0 = e6181d4e8dc34270e6948d2c78695e6855931368`，所有改动在 `clean`。尚未部署，也未导入服务器的 `data/` 或 `app.db`。
