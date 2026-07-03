# 孤儿 report 清理脚本使用说明

**脚本路径**:`scripts/audit_orphan_reports.py`
**创建日期**:2026-07-03

---

## 一句话介绍

扫描、归档、清理 `data/simple/reports/` 目录里那些**已经没有合法引用的 report**(俗称"孤儿"),让激活码与 report 的对应关系保持干净。

---

## 什么是孤儿 report?

简单说:**这个 report 目录还在,但它对应的激活码要么不存在、要么已删除、要么 user_id 对不上**,业务上已经不会被任何代码读到,纯占磁盘。

| 类型 | 标签 | 含义 | 默认处理 |
|------|------|------|----------|
| 激活码不存在 | `activation_missing` | record 里的 activation_code 在 activations.json 找不到 | 自动清理 |
| 激活码已删 | `activation_deleted` | 激活码 status=deleted 或已进回收站 | 自动清理 |
| 重复 report | `duplicate` | 同一 (激活码, user_id) 有多份,保留最早创建的 canonical,其余是冗余 | 自动清理 extras |
| ORPHAN 前缀 | `orphan_prefix` | 激活码以 `ORPHAN__` 开头(历史迁移脚本留下的废弃数据) | 默认不动,需 `--include-orphans` |
| 用户不匹配 | `cross_user` | record.user_id ≠ 激活码的 owner_user_id(常见于 admin 历史污染 / 手动迁移残留) | 默认不动,需 `--include-cross-user` |

**为什么 ORPHAN 和 cross_user 默认不动**:这两类有可能是合理的迁移残留(比如你手动改过 owner),脚本只标记让你人工确认,不自动删。

---

## 三个子命令

```
scan      只读扫描,列出所有可疑 report,不动任何文件(默认命令)
archive   把可疑 report 移动到 data/simple/reports_archive/{时间戳}/,可恢复
clean     永久删除(rm -rf),需双重显式确认
```

**安全级别**:`scan` < `archive` < `clean`
- `scan`:零风险,只读
- `archive`:可恢复(数据移到备份目录,有 manifest 记录原路径)
- `clean`:不可恢复,慎用

---

## 推荐操作流程(三步走)

### 第 1 步:扫描看状况

```bash
python scripts/audit_orphan_reports.py scan
```

输出示例:
```
孤儿分类:
  activation_missing: 0
  activation_deleted: 0
  orphan_prefix:      7  (默认不处理,需 --include-orphans)
  cross_user:         2  (诊断用,需 --include-cross-user)
  duplicates:         1 组

建议操作:
  可安全归档(默认): 1 份
  python scripts/audit_orphan_reports.py archive --confirm-count 1
```

想看 JSON 格式(便于程序解析):
```bash
python scripts/audit_orphan_reports.py scan --json
```

### 第 2 步:dry-run 预览(强烈推荐,不实际执行)

**dry-run 不需要填 `--confirm-count`**,只看不动:

```bash
# 只看默认安全项(activation_missing/deleted/duplicates)
python scripts/audit_orphan_reports.py archive --dry-run

# 也要看 ORPHAN 和 cross_user
python scripts/audit_orphan_reports.py archive --dry-run --include-orphans --include-cross-user
```

输出会列出每一份将被处理的 report:
```
将归档以下 10 份 report:
  [duplicate] 8e30aa60-...  code=1EPJC91L88
    reason: duplicate of canonical df0b212f-...
  [orphan_prefix] 0d834991-...  code=ORPHAN__63A7F607-...
    reason: ORPHAN__ 前缀(历史迁移残留)
  ...

[dry-run] 未实际归档,去掉 --dry-run 执行。
```

**记住输出里的数量 N**(比如"10 份")。

### 第 3 步:实际执行

把上一步看到的数量填进 `--confirm-count`(防误操作的双保险):

```bash
# 归档(可恢复)
python scripts/audit_orphan_reports.py archive --include-orphans --include-cross-user --confirm-count 10

# 或者永久清理(不可恢复,需额外加 --i-know-this-is-destructive)
python scripts/audit_orphan_reports.py clean --include-orphans --include-cross-user --confirm-count 10 --i-know-this-is-destructive
```

---

## 参数速查

| 参数 | 适用命令 | 说明 |
|------|---------|------|
| `--base-dir PATH` | 全局 | 覆盖数据根目录(默认 `data/simple`) |
| `--json` | scan | 输出 JSON 格式 |
| `--dry-run` | archive/clean | 只打印不执行(confirm-count 可不填) |
| `--confirm-count N` | archive/clean | **实际执行时必填**:确认数量,必须与脚本算出的数量一致 |
| `--include-orphans` | archive/clean | 纳入 `ORPHAN__` 前缀的 report |
| `--include-cross-user` | archive/clean | 纳入 user_id 不匹配的 report |
| `--i-know-this-is-destructive` | clean only | 必填,确认永久删除不可恢复 |

---

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 正常,无可疑 / 执行成功 |
| 1 | scan 发现可疑 report(便于 CI 脚本判断) |
| 2 | 参数错误 / confirm-count 不匹配 |
| 3 | IO 错误 |

---

## 归档后怎么恢复?

归档目录结构:
```
data/simple/reports_archive/
  └── 20260703T100000Z/              ← 时间戳目录
      ├── _manifest.json             ← 记录每份 report 的原路径 + 归档原因
      ├── 8e30aa60-.../
      ├── 0d834991-.../
      └── ...
```

恢复方法:看 `_manifest.json` 里的 `original_path` 字段,把目录 `mv` 回去即可。

---

## 常见问题

**Q: `--confirm-count` 该填几?**
A: 先跑 `--dry-run`,看输出顶部"将归档以下 N 份 report"那行,N 就是答案。

**Q: archive 和 clean 怎么选?**
A: 永远先 archive。确认业务没问题(过几天用户没反馈数据丢失),再考虑 clean 释放磁盘。archive 几乎零风险。

**Q: 清理后用户访问会受影响吗?**
A: 不会。孤儿定义上就是"没有合法引用"的 report,用户访问走的是 activations.json 的 report_id 索引,指向的是 canonical report,不会被孤儿影响。

**Q: 我手动改过 activations.json 的 owner,算孤儿吗?**
A: 可能算 cross_user(如果你只改了 owner 没改 record.user_id)。脚本默认不动 cross_user,你可以用 scan 看清楚再决定要不要 `--include-cross-user` 清理。
