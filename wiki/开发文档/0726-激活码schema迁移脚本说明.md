# 激活码 schema 迁移脚本说明（ADR-0008 存量数据补全）

**脚本路径**：`scripts/migrate_activation_schema.py`（随本文档交付）
**创建日期**：2026-07-26
**背景**：ADR-0008 套餐与试用体系上线后，激活码记录新增多个字段。存量记录在磁盘上缺这些字段，靠 `_load_all()` 的 setdefault 懒迁移兜底（运行时一律视为完整码）。本脚本把默认值**显式回写磁盘**，让磁盘数据成为真相。

---

## 一句话介绍

对生产/测试两个数据根的 `activations.json`（+ 两个回收站文件）做一次**无损字段补全**：凡缺新 schema 字段的记录，补上默认值（`code_type="full"`、`vip_level=1`、`package_type=None` 等），已有字段一律不动。

---

## 〇、最简操作手册（复制粘贴即完事）

```bash
cd /home/gitclone/BeingDoing
./start.sh stop                                        # 1. 停服
python3 scripts/migrate_activation_schema.py           # 2. 迁移（自动备份，没停服会拒绝执行）
./start.sh                                             # 3. 重启
```

看到 `✅ 迁移完成` 即成功。脚本自动备份、幂等（重跑显示“已补全 0”）。

**万一出问题，恢复：**

```bash
./start.sh stop
cp $(ls -dt data/backups/activation_schema_migration_* | head -1)/simple_activations.json data/simple/activations.json
./start.sh
```

> 恢复后功能不受影响（运行时懒迁移兜底），排查后可重跑。需要逐步核对/验证看下面 §〇·五，一般不用。

---

## 〇·五、完整指令（可选：含预检/测试/验证）

```bash
cd /home/gitclone/BeingDoing

# ① 预检（只读，不写盘）——看各文件有多少记录待补
python3 scripts/migrate_activation_schema.py --dry-run

# ② 停服（必须，消除并发写丢码风险 R1）
./start.sh stop

# ③ 执行迁移（自动时间戳备份 + 原子写，幂等）
python3 scripts/migrate_activation_schema.py

# ④ 回归测试（用 start.sh 同款 conda 运行时 py312）
/mnt/vdb1/miniconda3/envs/py312/bin/python -m pytest \
  test/backend/test_migrate_activation_schema.py \
  test/backend/test_trial_codes.py \
  test/backend/test_activation_transfer.py -v

# ⑤ 重启服务
./start.sh

# ⑥ 验证：预期输出「缺字段 0、非法值 无」
python3 -c "
import json
for f in ['data/simple/activations.json', 'data/test/simple/activations.json']:
    raw = json.load(open(f))
    bad = {c: d.get('code_type') for c, d in raw.items() if d.get('code_type') not in ('trial', 'full')}
    missing = [c for c, d in raw.items() if 'code_type' not in d]
    print(f, '缺字段', len(missing), '非法值', bad or '无')
"

# ⑦ 幂等验证（可选）：再预检一遍，预期「将补全 0」
python3 scripts/migrate_activation_schema.py --dry-run
```

**④失败或⑥异常 → 先别放流量，直接回滚**（详见 §四.1）：

```bash
./start.sh stop
BK=$(ls -dt data/backups/activation_schema_migration_* | head -1)
cp "$BK/simple_activations.json" data/simple/activations.json
cp "$BK/test_activations.json"   data/test/simple/activations.json
# 以下两个文件存在才拷（回收站文件可能本来就没有）
[ -f "$BK/simple_activations_recycle_bin.json" ] && cp "$BK/simple_activations_recycle_bin.json" data/simple/activations_recycle_bin.json
[ -f "$BK/test_activations_recycle_bin.json" ] && cp "$BK/test_activations_recycle_bin.json" data/test/simple/activations_recycle_bin.json
./start.sh
```

回滚后系统回到懒迁移兜底状态，功能不受影响，可从容排查后重跑。

> ⚠️ 注意：后端运行中脚本会拒绝执行（检测 8000 端口）；确需在线执行加 `--force`（自担 R1 风险）。

---

## 一、本次改动的影响

### 1.1 改的是什么

| 文件 | 说明 |
|------|------|
| `data/simple/activations.json` | 生产激活码索引（真实用户） |
| `data/test/simple/activations.json` | 沙箱激活码索引（SBX/ADM 调试码） |
| `data/simple/activations_recycle_bin.json` | 生产回收站（补丁打在 `original_record` 内） |
| `data/test/simple/activations_recycle_bin.json` | 测试回收站（同上） |

**不动的**：SQL 数据库（`backend.db`，激活码本就不在库里，无需 Alembic）、`.duplicate/`、`data_backup_*/`、`.bak_data/` 等历史备份（备份应保持历史快照原样）、任何对话/报告/用户目录。

### 1.2 补的字段及默认值（与 `_load_all()` setdefault 清单严格一致）

| 字段 | 默认值 | 含义与影响 |
|------|--------|-----------|
| `code_type` | `"full"` | **核心**：存量码一律完整版，不受试用门控（10 轮限制、values 阶段锁）影响 |
| `vip_level` | `1` | DeepSeek 档。当前两档均配 DeepSeek，零功能差异；将来 vip2 切高级模型时老用户保持现状 |
| `package_type` | `None` | 无套餐类型 → **不能延期**（续费），到期只能重新买套餐（代码既有决策："存量无类型码拒延，引导买套餐"） |
| `source_order_id` | `None` | 无来源订单（存量码非支付交付） |
| `purchaser_user_id` | `None` | 无所属人（单角色，激活人即主人） |
| `report_authorized` | `false` | 未授权报告给所属人（无所属人，无实际效果） |

### 1.3 对用户的影响

**正常路径：零影响。** 懒迁移（`_load_all` setdefault）本就让存量码在运行时表现为完整码，脚本只是把同样的值落到磁盘。迁移前后用户体感完全一致：

- 老用户继续全阶段可用，无 10 轮限制；
- 模型不变（DeepSeek）；
- 到期规则不变（原有 `expires_at` 一字不动）。

**已知的既有产品口径（非本次引入，本次只是固化到磁盘）**：

- 存量码 `package_type=None` → 无续费入口，到期需重买套餐拿新码；
- 重买拿新码后历史探索数据**不自动继承**（数据按码隔离）→ 走人工 transfer 兜底（见 §四.3）。

---

## 二、风险

| # | 风险 | 等级 | 说明与缓解 |
|---|------|------|-----------|
| R1 | **并发写丢码** | 中 | 服务运行中执行脚本时，若支付回调在"脚本读取→回写"窗口内交付新码，脚本回写会用旧快照覆盖新记录。**强制要求停服执行**（见 §三）。 |
| R2 | **写坏文件** | 低 | 脚本用原子写（临时文件 + rename），中途崩溃不会留半截文件；执行前自动做时间戳备份。 |
| R3 | **补错默认值** | 低 | 默认值清单直接复用 `_load_all()` 的权威定义，脚本与运行时永远一致；pytest 回归覆盖。万一补错（如手工改过脚本），恢复方案见 §四.2。 |
| R4 | **回收站记录污染** | 低 | 回收站补丁只打 `original_record` 字典内部，不动外层结构；恢复出的码走 dataclass 默认值，行为本已正确。 |
| R5 | **异常/残缺记录** | 低 | 脚本在原始 dict 层操作，**不丢任何记录**（包括 `_load_all` 会跳过的损坏条目、含未知字段的条目），原样保留只补缺字段。 |
| R6 | **误对备份目录执行** | 低 | 脚本路径写死两个数据根，不接受自定义路径参数，从机制上杜绝。 |

**不属于风险的项**：多次执行（幂等，重跑只补仍缺的字段）；停机时长（文件很小，脚本执行 < 1 秒，总停机取决于重启速度）。

---

## 三、管理员操作（执行 SOP）

### 3.1 执行前

```bash
# 1. 确认当前数据根里有存量记录缺字段（可选预检，只读）
cd /home/gitclone/BeingDoing
python3 -c "
import json
for f in ['data/simple/activations.json', 'data/test/simple/activations.json']:
    try:
        raw = json.load(open(f))
        missing = [c for c, d in raw.items() if 'code_type' not in d]
        print(f, '总记录', len(raw), '缺 code_type', len(missing))
    except FileNotFoundError:
        print(f, '不存在，跳过')
"
```

> 预期：生产根会列出一批缺字段的存量码；若全部为 0，说明之前某次 `_save_all` 已顺带落盘，脚本仍会跑但无实际改动。

### 3.2 执行（短暂停服）

快速指令见 §〇（含全部命令）。分步说明：

```bash
# 2. 停服（消除 R1 并发写窗口）
./start.sh stop

# 3. 跑迁移脚本（自带时间戳备份 + 原子写，幂等）
cd /home/gitclone/BeingDoing
python3 scripts/migrate_activation_schema.py

# 4. 查看输出统计：每个文件的 总记录数 / 已补全数 / 原本完整数 / 备份路径

# 5. 跑回归测试（用 start.sh 同款 conda 运行时 py312；src/backend/venv 缺依赖勿用）
/mnt/vdb1/miniconda3/envs/py312/bin/python -m pytest \
  test/backend/test_migrate_activation_schema.py \
  test/backend/test_trial_codes.py \
  test/backend/test_activation_transfer.py -v

# 6. 重启服务
./start.sh
```

### 3.3 执行后验证

```bash
# 7. 确认所有记录已带 code_type 且全部为 full/trial 合法值
python3 -c "
import json
for f in ['data/simple/activations.json', 'data/test/simple/activations.json']:
    raw = json.load(open(f))
    bad = {c: d.get('code_type') for c, d in raw.items() if d.get('code_type') not in ('trial', 'full')}
    missing = [c for c, d in raw.items() if 'code_type' not in d]
    print(f, '缺字段', len(missing), '非法值', bad or '无')
"
```

8. 后台管理页抽查：激活码列表正常展示；挑 1 个老码对应用户登录，确认可正常进入对话（非 values 阶段不被 402 拦）。
9. 确认备份文件已生成：`ls data/backups/ | grep activations`（或脚本输出中的备份路径）。

**回滚点**：步骤 5 测试失败或步骤 7/8 验证异常 → 先不要重启流量，直接走 §四.1 恢复备份。

---

## 四、补救（改错了怎么办）

### 4.1 整体恢复（首选）

脚本执行前对每个目标文件做了时间戳备份（原样字节拷贝，未打补丁）：

```bash
# 备份位置（以脚本输出为准），形如：
# data/backups/activation_schema_migration_20260726_HHMMSS/
#   ├── simple_activations.json
#   ├── simple_activations_recycle_bin.json
#   ├── test_activations.json
#   └── test_activations_recycle_bin.json

# 恢复 = 停服 + 拷回 + 重启
./start.sh stop
cp data/backups/activation_schema_migration_<时间戳>/simple_activations.json \
   data/simple/activations.json
cp data/backups/activation_schema_migration_<时间戳>/simple_activations_recycle_bin.json \
   data/simple/activations_recycle_bin.json
cp data/backups/activation_schema_migration_<时间戳>/test_activations.json \
   data/test/simple/activations.json
cp data/backups/activation_schema_migration_<时间戳>/test_activations_recycle_bin.json \
   data/test/simple/activations_recycle_bin.json
./start.sh
```

恢复后系统回到懒迁移兜底状态，**功能不受任何影响**（运行时 setdefault 仍在），可从容排查后重跑。

### 4.2 单条记录修错了

若个别码的字段被补错（例如某码本应是 `trial` 却被写成 `full`——正常流程不会发生，脚本只对缺字段补默认值、不覆盖已有值）：

1. 停服（或避开该用户使用时段）；
2. 直接编辑 `data/simple/activations.json` 中对应码的记录，改回正确值；
3. 重启服务。文件存储无缓存，重启即生效。

### 4.3 相关但独立的既有问题：老码到期数据承接

与迁移脚本无关，但属同一决策链的遗留口径：存量码到期 → 买套餐得新码 → 历史对话/报告留在旧码名下。**处置流程（客服/管理员人工 transfer）**：

1. 用户提供旧码 + 新购套餐的订单号/新码；
2. 管理员用现有 transfer 能力（归属/报告转移，见 `test/backend/test_activation_transfer.py` 覆盖的工具路径）把旧码报告归属迁到新码或新 owner；
3. 对话记录默认不迁（按码隔离为设计口径），如用户强诉求再个案评估。

---

## 五、验收清单

- [ ] 脚本输出四个文件的统计（总记录/已补全/原完整），数量与 §3.1 预检一致
- [ ] 备份目录生成且四个备份文件齐全
- [ ] `pytest` 三个测试文件全绿（migrate_activation_schema / trial_codes / activation_transfer，用 py312 运行时）
- [ ] §3.3 验证脚本输出"缺字段 0、非法值 无"
- [ ] 管理页激活码列表正常；抽查 1 个老码用户可正常对话
- [ ] 重跑脚本一次，输出"已补全 0"（验证幂等）
