# BeingDoing 服务器操作手册：dev 与 prod

适用方式：**两台独立 Linux 服务器，目前用 `./start.sh`／tmux 启动，数据库为 SQLite**。2026-10-13 按 `clean@0c7e93d` 的脚本核对。服务器实际目录、Conda、代理和配置未现场读取；下面的路径默认值来自仓库，执行前按本机核实。

本手册负责日常运行与版本更新；首次安装／新建空库见 [开发指南](DEVELOPMENT.md)，现有测试债和上线条件见 [TESTING](TESTING.md)、[安全评估](SECURITY_REVIEW.md)。不把“提交已推送”当成生产验收完成。

使用顺序：只修这次缺包，读第 2、3、5 节；完整更新，依次读第 2、4、5 节，先 dev 后 prod；平时查日志／重启看第 6 节，失败处理看第 7 节。更新过程中的环境变量在同一个 SSH／Bash 会话有效；新开终端后要重新选择本机环境及记录的目标／备份路径。

## 1. 两台机器分别负责什么

| 项目 | dev 测试服务器 | prod 生产服务器 |
| --- | --- | --- |
| 用途 | 测试候选版本、复现问题、验证迁移和业务流程 | 对真实用户提供服务 |
| 环境文件 | 仓库根 `.env`，再覆盖 `.env.dev` | 仓库根 `.env`，再覆盖 `.env.prod` |
| `APP_ENV` | 明确设置 `development` | 明确设置 `production` |
| 正式验收启动 | `./start.sh start dev` | `./start.sh start prod` |
| 前端热更新 | 临时调试用 `./start.sh start dev --hot` | 发布验收使用构建模式 |
| 脚本默认 Conda | `/mnt/vdb1/miniconda3` 中的 `py312` | `/root/miniconda3` 中的 `base` |
| 代码版本 | 本轮候选来自 `origin/clean` | 使用 dev **实际验收过的完整提交 SHA** |
| DB／data／密钥／支付／邮件／OSS | 使用测试侧资源；导入脱敏副本也要先处理后台模型配置和外部服务凭据 | 保留生产侧资源；不能用 dev 的 DB／data／环境文件覆盖 |

`dev/prod`、Git 分支、前端运行模式是三件不同的事。`start prod` 不会切分支，也不会自动把 `APP_ENV` 改成 production；配置文件必须明确设置。当前 `main` 仍在 `v1.8.0`，清理改动在 `clean`；不能以 `git pull origin main` 取得 clean 的修复。

`start dev` 默认也会清除 `.next` 并重新构建。`--hot` 才会用 `npm run dev`；后端目前两种环境都带 `--reload`，这是现有脚本的事实，后续生产进程管理应去掉它。普通探索数据仍在本机仓库的 `data/simple`，`data/test/simple` 是管理员沙箱目录；设置 APP_ENV=development 不会把全部数据自动迁到后者。

**长期建议：prod 改用 systemd，dev 可继续 tmux。** systemd 支持服务生命周期、异常重启和集中日志；本次先沿用现有方式，另行验证迁移。仓库的 systemd 模板写死旧路径／py312、读取 `/etc/beingdoing.env`，与 prod 当前默认 base 不同，不能直接覆盖使用。迁移时统一用户、路径、环境文件、单进程策略、127.0.0.1 监听、预先构建及健康检查，并停掉同端口的 tmux 服务。[systemd 项目说明](https://systemd.io/)

## 2. 每次操作先选对机器、目录和 Python

以下使用 Bash，先进入服务器上**实际部署目录**。各代码块逐块执行，任何一步报错就停在该步；不要继续迁移或重启。示例路径来自现有模板，实际不是此路径就先替换。

```bash
cd /home/gitclone/BeingDoing
export BD_OPS_ROOT="$(pwd -P)"
hostname
git status --short --branch
git log -1 --oneline
```

只选下面一组，不要两组一起运行。

**dev 服务器：**

```bash
export BD_OPS_ENV=dev
export CONDA_BASE=/mnt/vdb1/miniconda3
export CONDA_ENV=py312
```

**prod 服务器：**

```bash
export BD_OPS_ENV=prod
export CONDA_BASE=/root/miniconda3
export CONDA_ENV=base
```

共同执行；如果 Conda 路径不同，先修改上面的值。Conda 环境名不能证明 Python 版本，当前锁文件验证目标是 Python 3.12。检查失败时先单独准备匹配的环境，并让安装依赖和 start.sh 使用同一套 `CONDA_BASE/CONDA_ENV`，不要把另一版本的锁文件强装进旧环境。

```bash
source "$CONDA_BASE/etc/profile.d/conda.sh" && conda activate "$CONDA_ENV"
python -c 'import sys; print(sys.executable, sys.version); assert sys.version_info[:2] == (3, 12), "需要核对 Python 3.12 环境"'
node --version
npm --version
```

Node 至少 20；dev／prod 应使用相同、经过该版本验收的 Node／npm，不能只因达到最低版本就认为兼容性已验证。

定义本次会话的环境加载函数，按 start.sh 的顺序加载。使用可信的本机配置，**不要把完整 `.env` 或 `env` 输出发到聊天／issue**。

```bash
bd_load_env() {
  case "$BD_OPS_ENV" in dev|prod) ;; *) return 1 ;; esac
  test -f "$BD_OPS_ROOT/.env" || return 1
  test -f "$BD_OPS_ROOT/.env.$BD_OPS_ENV" || return 1
  unset DEBUG DEBUG_MODE LLM_PROVIDER LLM_BASE_URL LLM_MODEL
  unset OPENAI_API_KEY DEEPSEEK_API_KEY GLM_API_KEY KIMI_API_KEY CLAUDE_API_KEY
  unset NEXT_PUBLIC_API_URL FRONTEND_MODE FRONTEND_URL
  set -a
  source "$BD_OPS_ROOT/.env"
  local bd_base_status=$?
  source "$BD_OPS_ROOT/.env.$BD_OPS_ENV"
  local bd_override_status=$?
  set +a
  test "$bd_base_status" -eq 0 && test "$bd_override_status" -eq 0
}
bd_load_env
```

配置必须核对：prod 的 `APP_ENV=production`、`DEBUG=False`、`REFRESH_COOKIE_SECURE=True` 和 HTTPS；SECRET_KEY 为至少 32 字符的随机值，独立 refresh 密钥如配置也要满足长度。保留现有有效密钥，**不要每次发布重新生成**：这会影响登录；某些加密配置还依赖密钥。前端域名、API 代理、刷新 cookie 域和 Server Actions 稳定密钥使用本机配置。现行变量含义见开发指南。

`.env.dev` 已被 Git 跟踪；若服务器修改过它，Git 更新前需要先留存并人工合并差异。不要用 `reset --hard` 或 `clean -fd` 清掉本机修改。

## 3. 仅修复这次缺少 rehype-sanitize

适用于：服务器代码已经更新完整，只是构建失败、没有 schema 变更；已完成第 2 节。若仍运行旧前端，先停止其 tmux 窗口再重装依赖；`npm ci` 会替换 node_modules。prod 先按第 4 节开启并确认维护页。

```bash
# 只关闭前端窗口，保留后端；没有前端窗口时跳过本行
tmux kill-window -t beingdoing:frontend
```

```bash
(
  set -e
  cd "$BD_OPS_ROOT/src/frontend"
  node -e 'const p=require("./package.json"); if(!p.dependencies?.["rehype-sanitize"]) process.exit(1)'
  npm ci --include=dev
  npm ls rehype-sanitize --depth=0
)
```

应显示 `rehype-sanitize@6.0.0`。若依赖声明都没有，先确认源码和锁文件是否来自同一个 clean 提交，不单独补一个最新版包来掩盖混版。`npm ci` 按锁文件安装，`--include=dev` 保留 TypeScript／Tailwind 等构建依赖；锁文件不匹配会报错，不应删除锁文件绕过。[npm 官方说明](https://docs.npmjs.com/cli/v11/commands/npm-ci/)

确保 `.start_env` 等于本机 `dev` 或 `prod`、tmux 后端仍在，再执行：

```bash
cd "$BD_OPS_ROOT"
cat .start_env
BD_SKIP_TMUX_ATTACH=1 ./start.sh restart frontend
tmux capture-pane -p -S -100 -t beingdoing:frontend
```

重启命令会执行前端构建，无需此前额外跑一次 build。`.start_env` 不正确或不存在时，改走下一节完整更新中的明确环境启动，不执行无环境参数的裸 `./start.sh`。按第 5 节验证后关闭维护页。

## 4. 完整更新：dev 先验收，prod 发布相同提交

### 4.1 选择目标版本，此时只 fetch，不切换运行中的源码

先完成第 2 节，确认 Git 工作区没有需要保留的改动／未跟踪源码。以下更新采用 detached HEAD 固定提交，服务器只运行版本、不提交开发代码；以后更新仍先 fetch 再指定提交，无需在 detached HEAD 上 pull。

```bash
cd "$BD_OPS_ROOT"
git fetch origin
git status --short
export BD_OPS_PREVIOUS="$(git rev-parse HEAD)"
```

**dev：**锁定此次要验收的 clean 提交，记录该 SHA，后续即使 clean 又有更新也不改变此次目标。

```bash
export BD_OPS_TARGET="$(git rev-parse origin/clean)"
git show --no-patch --oneline "$BD_OPS_TARGET"
```

**prod：**将占位文字替换为 dev 验收记录中的完整 SHA。不能每次都自动取最新 clean。

```bash
export BD_OPS_TARGET='替换成dev已验收的完整40位提交SHA'
git cat-file -e "$BD_OPS_TARGET^{commit}"
git show --no-patch --oneline "$BD_OPS_TARGET"
```

### 4.2 进入维护、停止所有写入，再备份

生产必须验证公网维护页确实生效；开发机按需要开启。维护脚本只加载 `.env.dev/.env.prod`，因此维护路径、模板和 nginx 重载命令须放在对应覆盖文件中，不能依赖只写在基础 `.env`。首次未配置 nginx 的维护拦截时先配置并验收，不把脚本输出 ON 当作代理已拦截成功。

```bash
cd "$BD_OPS_ROOT"
./scripts/maintenance.sh on --env "$BD_OPS_ENV" --reason '版本更新'
./scripts/maintenance.sh status --env "$BD_OPS_ENV"
```

用未带维护绕过 cookie 的浏览器检查本机对应域名。确认后：

```bash
./start.sh stop
tmux list-sessions
ss -ltnp '( sport = :8000 or sport = :3000 )'
```

没有 tmux session 时 `tmux list-sessions` 返回非零是正常的；8000／3000 不应再有本应用监听。另有 systemd、cron、手工迁移或后台写入进程时也须停止它们，不能同时由两种管理器拉起应用。当前 stop 会按 `uvicorn app.main:app` 匹配残留进程，因此本流程限定一台机只有这一套 BeingDoing 服务。

账户／订单在 DB，探索／激活码／报告在 `data/`，必须在全部写入停止后备份同一时点的两部分。下面从有效的 DATABASE_URL 解析 SQLite 文件，不硬编码它必然叫 app.db；相对路径按后端工作目录解析。非 SQLite 或特殊 URI 不适用此段。

```bash
export BD_OPS_DB="$(python - <<'PY'
import os
from pathlib import Path
url = os.environ.get('DATABASE_URL', 'sqlite+aiosqlite:///./app.db')
prefix = next((p for p in ('sqlite+aiosqlite:///', 'sqlite:///') if url.startswith(p)), None)
if prefix is None:
    raise SystemExit('此备份流程仅适用于 SQLite')
name = url[len(prefix):]
if not name or name == ':memory:' or '?' in name or name.startswith('file:'):
    raise SystemExit('特殊 SQLite 地址需要单独核对')
path = Path(name)
if not path.is_absolute():
    path = Path(os.environ['BD_OPS_ROOT']) / 'src/backend' / path
path = path.resolve()
if not path.is_file():
    raise SystemExit('存量数据库不存在，停止；不要让迁移创建错位置的空库')
print(path)
PY
)"
test -n "$BD_OPS_DB" && test -f "$BD_OPS_DB"
```

备份目录选在仓库之外、有足够空间且不由网站直接提供的磁盘上。下面按时间创建新目录，已存在就拒绝覆盖。需要外部保存的支付证书、OSS 对象和自定义目录另行纳入本机备份；下面只覆盖所列本地文件。

```bash
export BD_OPS_BACKUP="/var/backups/beingdoing/$BD_OPS_ENV/$(date +%Y%m%d_%H%M%S)"
(
  set -e
  umask 077
  python - <<'PY'
import os, shutil, sqlite3
from pathlib import Path
root = Path(os.environ['BD_OPS_ROOT'])
db = Path(os.environ['BD_OPS_DB'])
dest = Path(os.environ['BD_OPS_BACKUP'])
if not (root / 'data').is_dir():
    raise SystemExit('data 目录不存在，先核对真实路径')
dest.mkdir(parents=True, mode=0o700, exist_ok=False)
with sqlite3.connect(db.as_uri() + '?mode=ro', uri=True) as source:
    with sqlite3.connect(dest / 'database.sqlite') as target:
        source.backup(target)
        if target.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise SystemExit('数据库备份完整性检查失败')
shutil.copytree(root / 'data', dest / 'data')
config = dest / 'config'
config.mkdir(mode=0o700)
for parent, label in ((root, 'root'), (root / 'src/frontend', 'frontend')):
    target = config / label
    target.mkdir(mode=0o700)
    for path in parent.glob('.env*'):
        if path.is_file():
            shutil.copy2(path, target / path.name)
(dest / 'previous-commit.txt').write_text(os.environ['BD_OPS_PREVIOUS'] + '\n')
(dest / 'database-path.txt').write_text(str(db) + '\n')
(dest / 'environment.txt').write_text(os.environ['BD_OPS_ENV'] + '\n')
print('DB、data、环境配置已保存；继续保存依赖记录')
PY
  python -m pip freeze > "$BD_OPS_BACKUP/python-freeze.txt"
  conda env export > "$BD_OPS_BACKUP/conda-environment.yml"
  node --version > "$BD_OPS_BACKUP/node-version.txt"
  npm --version > "$BD_OPS_BACKUP/npm-version.txt"
  printf '%s\n' "$BD_OPS_TARGET" > "$BD_OPS_BACKUP/target-commit.txt"
  touch "$BD_OPS_BACKUP/BACKUP_COMPLETE"
)
```

只有最后成功生成 `BACKUP_COMPLETE` 才继续。配置和依赖记录按私密备份保管，不提交 Git、不公开发送。SQLite Backup API 能包含 WAL 中已提交内容；跨 DB／JSON 的同一时点仍依赖前面的停写。[SQLite 官方说明](https://www.sqlite.org/backup.html)

### 4.3 切换代码、安装依赖、核对实际配置

```bash
(
  set -e
  cd "$BD_OPS_ROOT"
  test -f "$BD_OPS_BACKUP/BACKUP_COMPLETE"
  test -z "$(git status --porcelain)"
  git switch --detach "$BD_OPS_TARGET"
  test "$(git rev-parse HEAD)" = "$BD_OPS_TARGET"
  python -m pip install -r src/backend/requirements.lock
  python -m pip check
  cd src/frontend
  npm ci --include=dev
  npm ls rehype-sanitize --depth=0
)
```

出现网络失败、权限错误、锁文件不一致或 Python 版本不符时，停在安装步骤排查，不用 `npm audit fix --force` 或删除锁文件改变发布版本。报告渲染器的 `dist/` 已随代码提交，常规部署无需重建；Node 和 Chrome／Chromium 路径须能使用。只有修改渲染器源码时，才在 dev 的 `src/report-renderer` 执行 `npm ci --include=dev && npm test`，把经过验证的 dist 随发布代码提交。

重新加载更新后的配置，并检查将被应用使用的 DB 路径。脚本不打印密钥；如果新配置指向另一个 DB，必须先解决，不能直接对新路径迁移。

```bash
bd_load_env
(
  set -e
  cd "$BD_OPS_ROOT/src/backend"
  python - <<'PY'
import os
from pathlib import Path
from sqlalchemy.engine import make_url
from app.config.settings import settings
url = make_url(settings.DATABASE_URL)
if url.get_backend_name() != 'sqlite' or not url.database:
    raise SystemExit('数据库类型与本手册不一致')
if Path(url.database).resolve() != Path(os.environ['BD_OPS_DB']).resolve():
    raise SystemExit('新旧配置数据库路径不同，停止迁移')
expected = {'dev': {'development', 'dev'}, 'prod': {'production', 'prod'}}
if settings.APP_ENV.lower().strip() not in expected[os.environ['BD_OPS_ENV']]:
    raise SystemExit('APP_ENV 与目标机器不一致，先修正配置')
print('配置校验通过；APP_ENV:', settings.APP_ENV)
PY
)
```

### 4.4 存量数据库迁移

先只读查看：

```bash
(
  set -e
  cd "$BD_OPS_ROOT/src/backend"
  python -m alembic current
  python -m alembic heads
)
```

本次代码的 head 为 `025_user_type_admin_note`。已有版本正常、待执行迁移已在 dev 的隔离副本验证后再升级；两者已相同则无需重复升级。`current` 没有版本、提示 missing revision／表不存在／多 head 时停止核对，不猜测版本，也不对存量库执行 `stamp head`。全新 dev 空库另走开发指南，不走这里。

```bash
(
  set -e
  cd "$BD_OPS_ROOT/src/backend"
  python -m alembic upgrade head
  python -m alembic current
)
```

更新配置、依赖不等于更新表结构；更新表结构也不等于已完成历史 JSON 数据迁移。旧 `migrate_*`／`fix_*` 脚本必须有对应版本的明确需求才运行。[Alembic 说明](https://alembic.sqlalchemy.org/en/latest/tutorial.html)

### 4.5 明确环境启动

```bash
cd "$BD_OPS_ROOT"
BD_SKIP_TMUX_ATTACH=1 ./start.sh start "$BD_OPS_ENV"
cat .start_env
tmux list-windows -t beingdoing
tmux capture-pane -p -S -100 -t beingdoing:backend
tmux capture-pane -p -S -100 -t beingdoing:frontend
```

脚本输出“服务已启动”仅代表已向 tmux 下发命令。前端仍可能正在构建，也可能已经失败；必须等日志完成并通过下一节检查再恢复流量。start 会重新构建前端，不要一边运行旧前端一边在相同目录删除 `.next`。

## 5. 验收、记录版本和结束维护

先在服务器本机检查，避免公网维护页掩盖应用状态：

```bash
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8000/health
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:3000/ -o /dev/null
```

后端应返回 `{"status":"healthy"}`，前端请求应成功。`/health` 只表示 HTTP 进程可响应，**没有验证数据库、支付、模型或报告生成**。

再经本环境的真实 HTTPS 域名验收：管理员按已配置的维护绕过方式访问；登录／刷新、普通账户权限、历史报告读取、四阶段与 v4、SSE、PDF，以及此次改动相关的订单／优惠券／退款。dev 使用测试身份和外部服务测试配置；prod 不为“冒烟”随意制造真实扣款或退款。对已复制到 dev 的数据库，额外核对后台保存的模型密钥、邮件发送、支付对账与 OSS 配置，避免测试机继续访问生产服务。

dev 将通过的 **完整 SHA、Node／Python 版本、迁移前后版本、检查结果与已知失败**记到发布记录，再把同一 SHA 交给 prod。完整后端已有历史失败，不能把“服务启动”或定向通过写成全量通过。

通过后关闭维护，并用无绕过 cookie 的浏览器验证公网已恢复：

```bash
cd "$BD_OPS_ROOT"
./scripts/maintenance.sh off --env "$BD_OPS_ENV"
./scripts/maintenance.sh status --env "$BD_OPS_ENV"
git rev-parse HEAD
```

若 nginx reload 报错，即使脚本最后仍打印了状态，也要修复并重新验证。保留本轮备份、发布 SHA 和验收记录。

## 6. 日常操作速查

以下均从仓库根目录执行；`restart` 使用 `.start_env`，先检查内容正确。自定义 Conda 时，每次 start／restart 都需要同一套覆盖变量。

| 操作 | 命令／说明 |
| --- | --- |
| dev 构建模式启动 | `BD_SKIP_TMUX_ATTACH=1 ./start.sh start dev` |
| prod 构建模式启动 | `BD_SKIP_TMUX_ATTACH=1 ./start.sh start prod` |
| dev 热更新调试 | 停止现有服务后 `./start.sh start dev --hot`；调试结束用显式 dev 构建模式重新验收 |
| 重启后端 | `./start.sh restart backend` |
| 重启前端 | `./start.sh restart frontend`；会重新构建，不自动安装依赖 |
| 查看窗口 | `tmux list-windows -t beingdoing` |
| 查看日志 | `./start.sh attach`；Ctrl-B 后按 d 仅分离终端，服务继续运行 |
| 只读截取日志 | `tmux capture-pane -p -S -100 -t beingdoing:frontend`；后端替换为 backend |
| 停止服务 | `./start.sh stop`；检查端口与残留进程，停止会删除 `.start_env` |
| 停止后再启动 | 明确写 `start dev`／`start prod`，不依赖被删除的状态文件 |
| 维护模式 | 直接用 `./scripts/maintenance.sh on/off/status --env dev` 或 prod；不要依赖 start.sh 包装器的默认环境推断 |

机器重启后 tmux 服务不会自行恢复；重新完成环境选择后显式启动。当前 `start` 发现同名 session 已存在就返回，不会切换该 session 的环境。prod／dev 因为是两台机器，可以各自用 3000／8000 和同名 `beingdoing` session；本手册不适用于同机双实例。

## 7. 失败时怎么处理

| 现象 | 处理顺序 |
| --- | --- |
| Can't resolve rehype-sanitize／其他新包 | 核对当前 SHA、前端 package／lock，再在同目录 `npm ci --include=dev`；看安装错误，不删除安全清洗组件 |
| no such column／no such table | 保存完整 Traceback，核对有效 DB 路径及 `alembic current/heads`；`payment_orders` 的普通 SQL 日志本身不证明缺表 |
| Python import 缺包 | 检查 `python` 与 `python -m pip` 是否同一 Conda 环境，再按目标版本锁文件安装 |
| prod 被配置校验拒绝启动 | 修正 production 的密钥、DEBUG、Secure cookie／HTTPS；不要把 APP_ENV 改成 development 来绕过 |
| 端口占用／启动看似成功但打不开 | 检查 tmux 日志、端口、是否另有 systemd 实例；不重复拉多个后端 |
| 前端构建内存不足／进程被 killed | 核对内存与系统日志；部署容量需单独调整，不能靠关闭类型检查当修复 |
| 健康检查通过但报告／支付出错 | 单独核对 DB、data、外部配置、Node／Chrome；HTTP 健康不覆盖这些能力 |

**回滚分两类，先保持维护并停写：**

1. **仅代码／依赖回退且 schema 仍兼容：**从备份的 previous-commit.txt 读取旧 SHA；工作区确认干净后 `git switch --detach <旧SHA>`。按旧版本的安装说明恢复 Python 依赖，前端按旧锁文件安装并重建，再明确启动目标环境和验收。旧版本没有 requirements.lock 时不能拿新版本的锁文件代替；使用本次留存的 Conda／依赖记录。保留现有业务数据。
2. **涉及 schema 或数据格式回退：**先再备份失败状态，保留用于对账；在隔离位置恢复发布前**同一份快照的 DB、data 和对应配置**并验证旧代码。确认业务写入和支付／退款的对账方案后才替换生产资源。已对外恢复流量后产生的新订单／对话不能用旧快照直接抹掉；外部支付事实也不会随 DB 回滚。不要只覆盖 app.db 而保留新 data，更不要随手 `alembic downgrade -1`。

回滚时校验 SQLite WAL／SHM 与恢复数据库的配套状态，不能把失败版本的 sidecar 搭配旧库；保留失败状态整套文件，恢复在独立位置完成后切换。配置密钥与加密业务数据也须配套。数据库恢复是独立操作，不给缺少现场确认的“一键覆盖”命令。

## 8. 为什么暂时不用现有 deploy.sh 一键发布

该脚本当前：先在服务运行时 cp 默认 app.db，只备份单文件而没有 data；缺少 pip／npm 安装；Conda 默认为 `/mnt/vdb1/miniconda3` 的 py312，与 start prod 默认不同；启动命令返回不代表前端构建成功；结尾输出的回滚包含 reset --hard 和只还原 DB。这些都不满足上面的发布流程。

本次仅提供并验证手册，未改生产配置、实际运行脚本或连接服务器。后续若统一部署脚本／迁移 systemd，应把停写快照、环境校验、依赖、构建失败停止、健康检查和恢复验证作为同一项改动验收，再替换本页操作入口。
