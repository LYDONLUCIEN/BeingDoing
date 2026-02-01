# Alembic 数据库迁移

## 初始化数据库

```bash
# 从 src/backend 目录执行
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```

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
