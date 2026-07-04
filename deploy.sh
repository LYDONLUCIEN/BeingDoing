#!/usr/bin/env bash
# ============================================================
# deploy.sh — BeingDoing 生产部署脚本（SQLite）
#
# 流程（任一步失败即停，手动从该步接着干）：
#   1. 备份 app.db
#   2. git pull（可用 --skip-pull 跳过）
#   3. ./start.sh stop
#   4. alembic upgrade head     （一次到位，升到最新版本）
#   5. ./start.sh start prod
#   6. 冒烟检测（alembic 版本 + bounces 路由）
#   7. 可选：列出 scripts/ 一次性迁移脚本供选择执行
#
# 用法：
#   ./deploy.sh              # 完整部署
#   ./deploy.sh --skip-pull  # 已手动 pull 过
#   ./deploy.sh --dry-run    # 只打印不执行（模拟全程）
# ============================================================

set -uo pipefail   # 故意不开 -e：让用户自己控制每步失败后的处理

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$REPO_ROOT/src/backend"
DB_FILE="$BACKEND_DIR/app.db"
CONDA_BASE="${CONDA_BASE:-/mnt/vdb1/miniconda3}"
CONDA_ENV="py312"
SCRIPTS_DIR="$BACKEND_DIR/scripts"

# ── 颜色 ─────────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; C='\033[0;36m'; B='\033[1m'; X='\033[0m'
info() { echo -e "${C}[deploy]${X} $*"; }
ok()   { echo -e "${G}[deploy]${X} $*"; }
warn() { echo -e "${Y}[deploy]${X} $*"; }
die()  { echo -e "${R}[deploy 错误]${X} $*" >&2; exit 1; }
step() { echo -e "\n${B}━━━ $* ━━━${X}"; }

# ── 参数解析 ─────────────────────────────────────────────────
DRY_RUN=false
SKIP_PULL=false
for arg in "$@"; do
  case "$arg" in
    --dry-run)   DRY_RUN=true ;;
    --skip-pull) SKIP_PULL=true ;;
    *) die "未知参数: $arg（支持: --dry-run | --skip-pull）" ;;
  esac
done

# dry-run 包装：拦截真实副作用命令
if $DRY_RUN; then
  info "${Y}=== DRY-RUN 模式：只打印，不执行 ===${X}\n"
  RUN()    { echo -e "${Y}  ▶ 会执行:${X} $*"; }
  COND()   { echo -e "${Y}  ▶ 会执行:${X} $*"; }
else
  RUN()    { "$@"; }
  COND()   { "$@"; }
fi

# ── 前置检查 ─────────────────────────────────────────────────
cd "$REPO_ROOT" || die "无法 cd 到 $REPO_ROOT"
[ -f "$DB_FILE" ]      || die "找不到 db: $DB_FILE"
[ -f "start.sh" ]      || die "找不到 start.sh"
[ -f "$BACKEND_DIR/alembic.ini" ] || die "找不到 alembic.ini"

PREV_COMMIT="$(git rev-parse --short HEAD)"
TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="$DB_FILE.bak.$TS"

info "DB 文件:      $DB_FILE ($(du -h "$DB_FILE" | cut -f1))"
info "部署前 commit: $PREV_COMMIT"
info "时间戳:       $TS"

# ── Step 1: 备份 ─────────────────────────────────────────────
step "[1/6] 备份 app.db"
if $DRY_RUN; then
  echo -e "${Y}  ▶ 会执行:${X} cp $DB_FILE $BACKUP_FILE"
else
  cp "$DB_FILE" "$BACKUP_FILE" || die "备份失败"
  ok "已备份 → $BACKUP_FILE"
  ok "MD5: $(md5sum "$BACKUP_FILE" | awk '{print $1}')"
fi

# ── Step 2: git pull ─────────────────────────────────────────
step "[2/6] git pull"
if $SKIP_PULL; then
  warn "已跳过 (--skip-pull)"
elif $DRY_RUN; then
  echo -e "${Y}  ▶ 会执行:${X} git pull --ff-only"
else
  git pull --ff-only || die "git pull 失败，请手动处理冲突后从 Step 3 接着干"
  ok "已更新: $PREV_COMMIT → $(git rev-parse --short HEAD)"
fi

# ── Step 3: 停服务 ───────────────────────────────────────────
step "[3/6] 停止服务"
if $DRY_RUN; then
  echo -e "${Y}  ▶ 会执行:${X} ./start.sh stop"
else
  ./start.sh stop || warn "start.sh stop 报错（可能本来就未运行）"
  sleep 2
  if pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
    warn "uvicorn 仍在运行，手动处理: pkill -f 'uvicorn app.main:app'"
    die "请确认服务已停后重新运行（可用 --skip-pull 跳过已完成的步骤）"
  fi
  ok "服务已停止"
fi

# ── Step 4: alembic upgrade head ─────────────────────────────
step "[4/6] 同步数据库 (alembic upgrade head)"

# env.py 可能读 settings，需要加载 .env
unset DEBUG DEBUG_MODE LLM_PROVIDER LLM_BASE_URL LLM_MODEL \
      OPENAI_API_KEY DEEPSEEK_API_KEY GLM_API_KEY KIMI_API_KEY CLAUDE_API_KEY \
      NEXT_PUBLIC_API_URL FRONTEND_MODE FRONTEND_URL
set -a
[ -f ".env" ]      && source ".env"
[ -f ".env.prod" ] && source ".env.prod"
set +a

if ! $DRY_RUN; then
  source "$CONDA_BASE/etc/profile.d/conda.sh" || die "conda source 失败"
  conda activate "$CONDA_ENV" || die "conda activate $CONDA_ENV 失败"
fi

cd "$BACKEND_DIR" || die "无法 cd 到 $BACKEND_DIR"

if $DRY_RUN; then
  echo -e "${Y}  ▶ 会执行:${X} alembic current"
  echo -e "${Y}  ▶ 会执行:${X} alembic upgrade head"
  echo -e "${Y}  ▶ 会执行:${X} alembic current  (验证)"
else
  BEFORE="$(alembic current 2>/dev/null | awk 'NR==1{print $1}')"
  info "升级前版本: ${BEFORE:-<空>}"

  # 核心一步：upgrade head 一次到位（无论中间隔了多少版本）
  alembic upgrade head || die "alembic upgrade 失败，DB 已备份，请手动排查后重跑 alembic upgrade head"

  AFTER="$(alembic current 2>/dev/null | awk 'NR==1{print $1}')"
  info "升级后版本: $AFTER"
  ok "数据库已同步到最新"

  # 简单验证 006 表存在（如果升级到 006 或之后）
  if [[ "$AFTER" > "005" ]]; then
    if sqlite3 "$DB_FILE" ".schema email_bounces" 2>/dev/null | grep -q "email_bounces"; then
      ok "验证: email_bounces 表已存在"
    else
      warn "验证: email_bounces 表未找到（请检查）"
    fi
  fi
fi

cd "$REPO_ROOT"

# ── Step 5: 启动服务 ─────────────────────────────────────────
step "[5/6] 启动服务（生产模式）"
if $DRY_RUN; then
  echo -e "${Y}  ▶ 会执行:${X} ./start.sh start prod"
else
  ./start.sh start prod || die "启动失败，请手动: tmux attach -t beingdoing 看日志"
  ok "启动命令已下发（服务在 tmux 后台）"
fi

# ── Step 6: 冒烟检测 ─────────────────────────────────────────
step "[6/6] 冒烟检测"
if $DRY_RUN; then
  echo -e "${Y}  ▶ 会等待 backend 就绪并检测 openapi.json${X}"
else
  info "等待 backend 就绪 ..."
  READY=false
  for i in $(seq 1 30); do
    curl -sf http://localhost:8000/openapi.json >/dev/null 2>&1 && { READY=true; break; }
    sleep 1
  done
  if ! $READY; then
    die "backend 30s 未响应。手动检查: tmux attach -t beingdoing"
  fi
  ok "backend 就绪 (${i}s)"

  # 检测 bounces 路由
  HITS="$(curl -s http://localhost:8000/openapi.json | python3 -c "
import sys, json
try:
    paths = json.load(sys.stdin).get('paths', {})
    print('\n'.join(p for p in paths if 'bounce' in p.lower()))
except Exception:
    pass
" 2>/dev/null)"
  if [ -n "$HITS" ]; then
    ok "bounces 路由已注册:"
    echo "$HITS" | sed 's/^/      /'
  else
    warn "openapi.json 未找到 bounce 路由（可能需登录才显示，或代码未挂载）"
  fi
fi

# ── Step 7: 可选 - scripts/ 迁移脚本 ─────────────────────────
if ! $DRY_RUN; then
  step "[可选] scripts/ 一次性迁移/清理脚本"
  echo "以下是可能需要执行的一次性脚本（每个都是幂等/可选的）："
  echo ""
  echo "  [a] fix_timestamps.py          修复历史 naive 时间 → +00:00"
  echo "                                   （005 migration 已自动做，通常无需再跑）"
  echo "  [b] migrate_metadata_fields.py 旧结论字段 → 新字段（pending_status → conclusion_state 等）"
  echo "  [c] migrate_basic_info_to_user basic_info 从 session/ 迁到 user/"
  echo "  [d] reconcile_report_threads   报告线程对账"
  echo "  [e] rebuild_report_lineage.py  重建报告血缘链"
  echo ""
  echo "  [q] 跳过，结束部署"
  echo ""
  read -rp "选择要执行的脚本（可多选如 ab，或 q 跳过）: " CHOICE </dev/tty

  if [ "$CHOICE" = "q" ] || [ -z "$CHOICE" ]; then
    info "跳过 scripts/"
  else
    # 每个脚本都先 dry-run 预览，再问是否真正执行
    run_script_dry() {
      local script="$1"
      local name="$(basename "$script")"
      echo ""
      info "预览 $name (--dry-run)"
      cd "$BACKEND_DIR"
      if python "$script" --dry-run 2>&1 | head -40; then
        :
      fi
      echo ""
      read -rp "确认执行 $name 真实写入？[y/N] " ANS </dev/tty
      if [ "$ANS" = "y" ] || [ "$ANS" = "Y" ]; then
        python "$script" || warn "$name 执行失败，请查看日志"
        ok "$name 完成"
      else
        warn "已跳过 $name"
      fi
      cd "$REPO_ROOT"
    }

    [[ "$CHOICE" == *a* ]] && run_script_dry "$SCRIPTS_DIR/fix_timestamps.py"
    [[ "$CHOICE" == *b* ]] && run_script_dry "$SCRIPTS_DIR/migrate_metadata_fields.py"
    [[ "$CHOICE" == *c* ]] && run_script_dry "$SCRIPTS_DIR/migrate_basic_info_to_user.py"
    [[ "$CHOICE" == *d* ]] && run_script_dry "$SCRIPTS_DIR/reconcile_report_threads.py"
    [[ "$CHOICE" == *e* ]] && run_script_dry "$SCRIPTS_DIR/rebuild_report_lineage.py"
  fi
fi

# ── 结尾 ─────────────────────────────────────────────────────
echo ""
ok "=== 部署完成 $(date '+%F %T') ==="
if ! $DRY_RUN; then
  echo ""
  warn "手动确认两项："
  echo "  1) scheduler 日志（应见 'bounce scheduler started'）:"
  echo "     tmux attach -t beingdoing    # Ctrl-B d 退出"
  echo "  2) 前端可访问:"
  echo "     浏览器打开 https://你的域名/admin/notifications"
  echo ""
  echo "=== 回滚命令 ==="
  echo "  cd $REPO_ROOT && ./start.sh stop"
  echo "  cp $BACKUP_FILE $DB_FILE"
  echo "  git reset --hard $PREV_COMMIT"
  echo "  ./start.sh start prod"
  echo ""
  info "备份文件: $BACKUP_FILE"
else
  echo ""
  info "dry-run 结束，去掉 --dry-run 参数实际执行"
fi
