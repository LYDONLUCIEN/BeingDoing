# 历史材料索引

本表只列本目录实际存在的材料，核对日期2026-10-12；不保留旧索引中不存在的环境/部署文件链接。当前入口见 [README](README.md)，以下文档均先按历史证据阅读。

| 分类 | 原始材料 | 阅读限制 |
| --- | --- | --- |
| 架构与目录 | [ARCHITECTURE](ARCHITECTURE.md)、[architecture-guide](architecture-guide.md)、[PROJECT_STRUCTURE](PROJECT_STRUCTURE.md)、[DESIGN](DESIGN.md)、[design_principle](design_principle.md)、[design-sonnet](design-sonnet) | 多代架构并存，不能据旧目录描述恢复未使用模块；当前以docs/ARCHITECTURE与源码为准。 |
| 数据与归属 | [DATA_STORAGE_SIMPLE](DATA_STORAGE_SIMPLE.md)、[DATABASE_SCHEMA](DATABASE_SCHEMA.md)、[ADMIN_SANDBOX_FORK](ADMIN_SANDBOX_FORK.md) | 可解释JSON和沙箱来源；不是全量入库已经完成的证明。跨文件一致性、权限与迁移顺序需现行证据。 |
| 请求与旧提示词链 | [REQUEST_FLOW](REQUEST_FLOW.md)、[HTML图](REQUEST_FLOW.html)、[V2提示词/数据流](V2版本全提示词流程拼接图与数据流转关系.md)、[prompt_content](prompt_content.md)、[PROMPT_TUNING](PROMPT_TUNING.md)、[PROGRESSIVE_GUIDANCE](PROGRESSIVE_GUIDANCE.md) | 文档中的V2/v3与当前v4不可混用；旧隐藏协议、模板名与调用图不是当前运行时保证。 |
| 旧重构提案 | [FLOW_REFACTOR_PLAN](FLOW_REFACTOR_PLAN.md)、[rumination开发清单](rumination-开发清单.md)、[左右分栏计划](rumination-左右分栏-开发计划.md) | 勾选/未勾选只反映当时计划；v3运行时已被本轮用户废止，不继续执行其残留待办。 |
| 开发与测试 | [DEVELOPMENT](DEVELOPMENT.md)、[TESTING](TESTING.md)、[API_DOCUMENTATION](API_DOCUMENTATION.md)、[RUN_LOCALLY](RUN_LOCALLY.md)、[QUICK_START](QUICK_START.md) | 当前入口为上级docs同类指南；旧启动命令、接口与依赖版本须重新核对。 |
| 部署与排障 | [DOCKER](DOCKER.md)、[SYSTEMD_SERVICES](SYSTEMD_SERVICES.md)、[ADMIN_403_TROUBLESHOOTING](ADMIN_403_TROUBLESHOOTING.md) | 记录特定旧环境；不能直接执行旧服务重启、反代或配置改动。 |
| 体验与视觉 | [USER_GUIDE](USER_GUIDE.md)、[BACKGROUND4_COLOR_ANALYSIS](BACKGROUND4_COLOR_ANALYSIS.md) | 旧界面能力与颜色方案可能已被0919/0923和ADR-0022替代。 |

若某历史文件因本轮授权清理移出工作树，使用Git中的原路径与提交追溯即可；不得把断开的历史说明重新包装成当前API或设计要求。对需保留的数据兼容、母版和迁移链，先在 [ADR索引](../adr/README.md) 确认明确条件。
