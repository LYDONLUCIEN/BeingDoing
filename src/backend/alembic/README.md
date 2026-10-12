# Alembic 数据库迁移

## 本地空库与存量库

本仓库历史迁移从已有基础表的数据库开始，不能用 `alembic upgrade head` 从零建库，也不应为本地安装生成新的 initial migration。

新本地 SQLite 库使用[开发指南的空库流程](../../../docs/DEVELOPMENT.md#本地启动)：拒绝已有表，按当前 ORM 建表，成功后标记 head。此流程不回填历史数据。

存量库先备份并在副本验证，检查 `alembic current` 后升级。没有版本号的旧库需先核对表结构；不得直接 `stamp head` 跳过变更。

## 创建新迁移

```bash
# 自动生成迁移脚本
alembic revision --autogenerate -m "描述信息"

# 手动创建迁移脚本
alembic revision -m "描述信息"
```

## 应用迁移

```bash
# 升级到最新版本
alembic upgrade head

# 升级到指定版本
alembic upgrade <revision>

# 降级一个版本
alembic downgrade -1

# 降级到指定版本
alembic downgrade <revision>
```

## 查看迁移历史

```bash
# 查看当前版本
alembic current

# 查看迁移历史
alembic history
```
