# 生产副本自动验收

状态：2026-10-14，本地工具已实现；未连接 dev/prod、未读取真实用户数据、未执行部署。产品接口、鉴权、业务状态机和用户页面没有因本工具而修改。

入口为 `scripts/test_snapshot.sh`（或直接用 Python 运行 `scripts/test_snapshot.py`）。执行链路：

```text
生产一致备份 DB＋data
  → 源端脱敏 → SSH 单向传输 → 校验清单 → 独立基准
  → 固定当前源码 → 独立副本执行 Alembic／明确登记的文件迁移
  → 每组恢复升级后副本 → 存量兼容与自定义业务测试
  → 可选既有核心 API/UI 回归 → result.json、JUnit、日志
```

**不会合并或覆盖正在使用的 dev 数据库，不把测试数据库传回生产，不发布代码，不开启/关闭维护。** 这里的通过仅覆盖实际执行的迁移和用例；不是线上支付、真实模型效果或完整发布的通过证明。

## 1. 一次性准备

dev 使用项目的 Python 3.12 环境和后端锁定依赖（包括 pytest、Alembic）。已有测试中心可复用依赖。执行 UI 回归还需要现有前端及 `test_agent/l2` 的 node_modules 和 Playwright 浏览器；安装方式见 [测试中心](TEST_CENTER.md)。源端 capture/export/keygen 只使用 Python 标准库，无需启动产品或安装后端依赖。

在 dev 仓库根目录：

```bash
export BD_SNAPSHOT_PYTHON="$PWD/.venv/bin/python"
bash scripts/test_snapshot.sh init \
  --directory "$HOME/.config/beingdoing-snapshot" \
  --state-root "$HOME/beingdoing-snapshot-state"
```

命令独占创建目录，已有目录拒绝覆盖。生成 `pipeline.json`、`policy.json`；私密目录权限为 0700、文件默认 0600。不要把配置、脱敏密钥、快照和运行记录提交 Git。

`state_root` 必须在仓库之外，与源备份目录互不包含。空间需求至少包括原始脱敏包、基准、升级后副本、执行中的一份副本及固定源码；大库应预留其体积数倍的空间。启动最低检查 512 MiB 空闲，单个传输包/解包内容上限 8 GiB、20 万文件。

生产侧单独安装工具即可，无需切换正在运行的产品版本。在开发机打包工具：

```bash
tar --exclude='__pycache__' -czf /tmp/beingdoing-snapshot-tools.tgz \
  scripts/test_snapshot.py test_agent/snapshot
```

由运维将包放到生产侧非网站目录并解压，例如 `/opt/beingdoing-snapshot`。该工具目录由运维维护，导出账号只有读取权限。这个包不包含产品数据库、`.env`、产品 API 或部署脚本。

在生产侧创建持久脱敏密钥，并把生成的 `policy.json` 模板放在同目录：

```bash
python3 /opt/beingdoing-snapshot/scripts/test_snapshot.py keygen \
  --output /etc/beingdoing-snapshot/redaction.key
```

路径是示例，应由服务器管理员设置目录归属。密钥只留源端，不能传给 dev；同一密钥可使同一邮箱/激活码跨批次保持稳定假名。更换密钥会更换假名。

## 2. 准备一致备份（生产侧）

优先复用 [操作手册 §4.2](OPERATIONS.md) 已生成且不再变化的备份：目录内必须有 `database.sqlite`、`data/`、`BACKUP_COMPLETE`。附带的私密配置备份不会导出。

需要新快照时，由你按现行手册进入维护、等待在途操作结束、停止应用和所有后台写入后执行：

```bash
python3 /opt/beingdoing-snapshot/scripts/test_snapshot.py capture \
  --database /实际后端目录/app.db \
  --data /实际项目目录/data \
  --output /var/backups/beingdoing/prod/20261014-验收基准 \
  --writers-stopped
```

使用实际配置中的数据库路径，不能默认一定是 `app.db`。`--writers-stopped` 是操作者对停写前提的明确声明，不是工具自动检测出全部进程已停止。工具自身不停止、重启或升级生产，只读源数据并创建新备份；检查源文件前后摘要，一旦发现变化，不生成完成标记并移除本次不完整目录。

SQLite 使用 Backup API，DB 和 JSON 的共同一致性仍依赖协调停写；文件摘要检查不能代替停写。备份完成后，你按现有流程恢复生产服务。之后重复测试这份固定备份，不再影响线上。

## 3. 配置单向拉取

编辑 dev 的 `pipeline.json`，替换 init 生成的主机别名和路径：

```json
{
  "state_root": "/home/tester/beingdoing-snapshot-state",
  "source": {
    "kind": "ssh_export",
    "host": "beingdoing-export",
    "python": "/usr/bin/python3",
    "script": "/opt/beingdoing-snapshot/scripts/test_snapshot.py",
    "backup": "/var/backups/beingdoing/prod/20261014-验收基准",
    "key_file": "/etc/beingdoing-snapshot/redaction.key",
    "policy_file": "/etc/beingdoing-snapshot/policy.json",
    "timeout": 900
  },
  "migration_target": "head",
  "migration_timeout": 300,
  "allow_row_count_changes": [],
  "file_migrations": [],
  "suites": [
    {
      "id": "historical-compatibility",
      "targets": ["test_agent/snapshot/cases.py"],
      "timeout": 300
    }
  ],
  "regression_cases": ["@core"]
}
```

在 dev 的 SSH 配置中设置该别名、源端只读导出账号、专用密钥和已核验的主机指纹。工具强制 `BatchMode=yes` 和 `StrictHostKeyChecking=yes`，不会自动接受新主机指纹，也不接受配置中的密码。

建议服务器端将这把 SSH 公钥限制为一个固定导出命令，并禁用端口转发、代理转发和 PTY。例如由服务器管理员在专用账号的 `authorized_keys` 配置 `restrict,command="...固定的 export 命令..."`。固定命令仅导出指定的完成备份，忽略客户端任意命令。切换备份时由运维修改固定路径。脚本不会替你修改账号或 SSH 权限。

导出在源端执行，私有临时目录内完成脱敏后才传输。dev 接收不到原始库/原始聊天包或脱敏密钥。没有生产写权限的专用账号是主要边界；Python 的网络/路径检查不是操作系统沙箱。

另有两种来源：

- **已有脱敏包**：`"source": {"kind":"archive","path":"/private/sanitized.tar.gz"}`。仍会校验包内清单。仅使用可信源端生成的包，清单摘要用于完整性检查，不是匿名化证明或数字签名。
- **本机私密备份演练**：`"source": {"kind":"local_backup","backup":"/private/backup","key_file":"/private/redaction.key","policy_file":"/private/policy.json"}`。只适用于备份已经在受控机器上的情况；生产真实数据日常使用 SSH 源端脱敏方式。

手动生成脱敏包也可使用：

```bash
python3 /opt/beingdoing-snapshot/scripts/test_snapshot.py export \
  --backup /var/backups/beingdoing/prod/20261014-验收基准 \
  --key-file /etc/beingdoing-snapshot/redaction.key \
  --policy /etc/beingdoing-snapshot/policy.json \
  --output /private/sanitized.tar.gz
```

## 4. 一条命令运行

在 dev 仓库根目录：

```bash
export BD_SNAPSHOT_PYTHON="$PWD/.venv/bin/python"
bash scripts/test_snapshot.sh doctor --config "$HOME/.config/beingdoing-snapshot/pipeline.json"
bash scripts/test_snapshot.sh run --config "$HOME/.config/beingdoing-snapshot/pipeline.json"
```

`doctor` 只检查本地配置与执行依赖，不连接生产。`run` 失败返回非零；输出最终状态和新建运行目录。每次 run 使用新的目录，不覆盖上次结果。迁移失败立即停止，不执行测试；零用例、跳过、断言失败、执行器错误、超时均不算通过。

目录含义：

| 路径 | 内容 |
| --- | --- |
| `result.json` | 总状态、失败阶段、源码摘要、Git 提交、Python 版本、迁移结果、各套件计数 |
| `snapshot.tar.gz`、`baseline/` | 接收的脱敏包及验证后的旧结构基准，不对它们运行迁移 |
| `source/`、`source-hashes.json` | 本轮固定源码及文件摘要；不包含原仓库 data、数据库、`.env` |
| `migration/` | 迁移日志和前后版本、表行数 |
| `upgraded/` | 迁移成功后的基准；每组测试从这里重新复制 |
| `suites/<id>/` | 使用生产副本的测试日志与 JUnit |
| `regression/` | 可选测试中心 API/UI 回归及证据，使用既有测试夹具 |

迁移失败的工作目录保留便于调查；正常结束的执行副本清理。日志和假名化聊天仍可能敏感，按受限资料保管。工具不会自动删除历史基准或证据；空间整理由管理员在无运行任务时进行。

## 5. 迁移和测试覆盖

`migration_target: "head"` 指本轮固定源码中的唯一 Alembic head，不是之后再拉取的新代码。也可填写明确 revision。旧库没有版本、版本未知、多头或版本与实际结构不符时不能跳过检查，必须先定位问题；不允许通过 `stamp head` 或 `create_all` 掩盖缺失迁移。

默认要求升级前存在的表保持行数。确有设计要求删表/合并记录时，审阅迁移后在 `allow_row_count_changes` 填对应表名，并补充能验证正确转换的业务用例；行数相同本身不代表金额、字段含义和所有关系正确。

JSON、聊天或报告格式的变化通过 `file_migrations` 明确指定。格式为 `[{"script":"src/backend/scripts/已审阅的脚本.py","args":["实际参数"]}]`；只执行本轮源码里的 Python 脚本，没有 shell 字符串。它们在独立工作区运行、无生产环境变量，禁止网络及启动外部程序。默认列表为空：不要把历史迁移目录全部执行一遍，尤其不能恢复已退役的沉淀流程。

默认存量套件验证：

1. SQLite 完整性、外键、当前 ORM 字段能够读取旧库。
2. 现有激活码/报告读取器能够读取导入记录，历史 JSON 可解析。
3. 以副本独立密钥签发普通用户 token，经现有鉴权访问 `/api/v1/auth/me`，验证读取的是导入账户。没有绕过鉴权或新增 API。此项不代表生产密码、短信、邮件渠道已经验证。

默认基准必须有用户和报告记录；缺少资料会明确失败。若本次专项基准有意不含报告，可配置所需的具体 pytest 节点，并在验收记录中注明覆盖范围。

新 bug 的存量测试放在 `test_agent/snapshot/test_<业务>.py`，在 `suites` 登记固定文件或 `::test_name`；普通测试也可选择 `test/backend/test_<业务>.py`。通过 `BD_SNAPSHOT_WORKSPACE` 定位当前工作区，数据库为该目录下的 `app.db`，文件在 `data/`。不要自己重建空库替换它。

**每组 suite 重新恢复副本；同组内测试共享该副本。** 需要单个操作独立重置时，为该 pytest 节点单独配置一组。连续多轮对话应在同一用例内承接状态。每个用例仍分别维护输入与断言，并在固定用例目录登记其工具/业务测试。

`regression_cases` 可指定现有目录 ID，或用 `["@core"]` 选择源码目录里的全部可用核心 API/UI 用例；`[]` 表示仅本次存量套件。它使用独立控制库，不改 admin 的分类、用例修订或历史结果。这里选的是源码登记，不自动继承另一个 admin 控制库的人工调整；需要时把明确 ID 写入配置。

普通 API/UI 夹具测试与生产副本测试在报告中分开标记，不能把夹具通过当成生产旧数据已走过所有 UI/业务路径。用户自定义的完整业务链仍需对应真实断言脚本。

## 6. 脱敏范围与新增字段

`policy.json` 支持：

```json
{
  "redact_literals": ["需要额外替换的人名或机构名"],
  "extra_schema": {}
}
```

- 自动发现用户姓名/昵称、邮箱、电话、激活码/优惠码和部分外部交易标识，使用带密钥的稳定假名；对应 JSON 动态键和跨文件引用同步转换。
- 清除密码/服务凭据字段，清空刷新令牌表；处理文本内常见邮箱、手机、证件、模型 key/JWT 和 URL。保留内部用户/订单/报告关系、状态、时间、数值与 NULL。
- 数据库按 `test_agent/snapshot/schema.json` 登记的表/列导出。未知字段立即拒绝。审阅新增字段的含义和敏感性后更新这份清单及脱敏测试；临时历史结构可通过 `extra_schema` 提供该表的完整列名列表。涉及新的秘密字段要补程序规则，不能只加列白名单。
- 文件导出仅含 `data/simple`、`data/user`、`data/conversations`、`data/question_progress` 中 JSON/JSONL/Markdown/TXT。排除 `data/test`、运行配置、日志及不在业务清单内的目录。
- PDF、图片、音频等二进制附件不导出，只记录排除数量。报告的 JSON/Markdown 会处理并保留；本工具不声称 PDF 视觉效果已经覆盖。需要时从脱敏内容另做渲染测试。
- 符号链接、异常路径、未支持的数据库二进制字段/触发器、结构异常及清单校验失败会停止处理。

**假名化不等于彻底匿名。** 自由文本中的罕见身份线索、特殊联系方式、姓名变体仍需要人工审阅。manifest 固定标记 `pseudonymized-restricted` 和 `external_ai_allowed:false`；本流水线不调用外部模型，也不自动把这些文本送入现有 AI 回放。真实 AI 回放继续使用测试中心中已审阅的上下文、明确模型配置和预算。无需为此开放新的产品接口。

## 7. 常见失败

| 提示/阶段 | 处理 |
| --- | --- |
| SSH 失败 | 核对主机指纹、只读账号、专用密钥及固定导出命令；不要关闭主机验证 |
| 缺少 BACKUP_COMPLETE / 源仍变化 | 重新取得停写一致备份，不在活动业务目录伪造完成标记 |
| 未登记的数据结构 | 审阅表/列与隐私规则，补清单及测试；不要忽略 |
| 迁移失败 | 查看 migration 日志，在新副本复现并修复迁移；源备份与 dev 不受影响 |
| 当前模型字段缺失 | 补正式迁移，不能依靠应用启动时自动补字段骗过验收 |
| 网络/外部写入被拒绝 | 检查测试/迁移是否误用了生产资源；不要解除守卫来获得通过 |
| 既有核心回归失败 | 与已知基线对比，明确旧失败和新回归；失败结果保留，不能称全量通过 |

发布仍由你按 [操作手册](OPERATIONS.md) 操作；生产只应用同一套已验证代码与迁移，不恢复测试后的库和 data。
