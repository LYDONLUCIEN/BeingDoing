#!/usr/bin/env bash
# ============================================================
# deploy.sh — BeingDoing 生产部署脚本（SQLite）
#
# 用途：pull 代码后，一键完成
#   1. 备份 app.db（005 是数据修改型 migration，不可逆，必须备份）
#   2. ./start.sh stop 停服务
#   3. alembic upgrade head 同步数据库
#   4. ./start.sh start prod 启动服务
#   5. 部署后冒烟检测（alembic 版本 / 路由注册 / scheduler 启动）
#
# 用法：
#   ./deploy.sh              # 完整部署
#   ./deploy.sh --skip-pull  # 已手动 pull 过，跳过 git pull
#
# 设计原则：
#   - 任一步骤失败立即 set -e 退出，不留半完成状态
#   - 备份带时间戳，保留多份不覆盖
#   - 不自动 git reset / 还原，回滚由人工执行（脚本只打印回滚命令）
# ============================================================

set -euo pipefail

# ── 路径与配置 ───────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$REPO_ROOT/src/backend"
DB_FILE="$BACKEND_DIR/app.db"
BACKUP_RETAIN_DAYS=7    # 备份保留天数（手动清理用，脚本不自动删）

# conda 环境（与 start.sh 一致）
CONDA_BASE="${CONDA_BASE:-/mnt/vdb1/miniconda3}"
CONDA_ENV="py312"

# 期望的最终 alembic 版本（部署成功的判定线）
EXPECTED_REVISION="006_email_bounces"

# ── 颜色输出 ─────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; RESET='\033[0m'
info()  { echo -e "${CYAN}[deploy]${RESET} $*"; }
ok()    { echo -e "${GREEN}[deploy]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[deploy]${RESET} $*"; }
die()   { echo -e "${RED}[deploy 错误]${RESET} $*" >&2; exit 1; }

# ── 前置检查 ─────────────────────────────────────────────────
cd "$REPO_ROOT"

[ -f "$DB_FILE" ] || die "找不到 db 文件: $DB_FILE（请确认生产 db 路径）"
[ -f "$REPO_ROOT/start.sh" ] || die "找不到 start.sh"
[ -f "$BACKEND_DIR/alembic.ini" ] || die "找不到 alembic.ini"

SKIP_PULL=false
[ "${1:-}" = "--skip-pull" ] && SKIP_PULL=true

BACKUP_TS="$(date +%Y%m%d_%H%M%S)"
BACKUP_FILE="$DB_FILE.bak.$BACKUP_TS"

info "=== 部署开始 $(date '+%F %T') ==="
info "DB 文件:      $DB_FILE"
info "DB 大小:      $(du -h "$DB_FILE" | cut -f1)"
info "期望版本:     $EXPECTED_REVISION"
[ "$SKIP_PULL" = "true" ] && warn "已跳过 git pull（--skip-pull）"
echo ""

# 记录部署前的 commit（回滚要用）
PREV_COMMIT="$(git rev-parse --short HEAD)"
info "部署前 commit: $PREV_COMMIT"

# ── Step 1: 备份 db ──────────────────────────────────────────
info "[1/5] 备份 app.db ..."
cp "$DB_FILE" "$BACKUP_FILE"
BACKUP_MD5="$(md5sum "$BACKUP_FILE" | awk '{print $1}')"
ok "已备份 → $BACKUP_FILE"
ok "MD5: $BACKUP_MD5"
echo ""

# ── Step 2: git pull（可选） ─────────────────────────────────
if [ "$SKIP_PULL" = "false" ]; then
  info "[2/5] git pull ..."
  git pull --ff-only || die "git pull 失败（有冲突或需手动处理）"
  NOW_COMMIT="$(git rev-parse --short HEAD)"
  ok "已更新: $PREV_COMMIT → $NOW_COMMIT"
else
  info "[2/5] 跳过 git pull"
fi
echo ""

# ── Step 3: 停服务 ───────────────────────────────────────────
info "[3/5] 停止服务 ..."
./start.sh stop || warn "start.sh stop 报错（可能本来就未运行，继续）"
# 兜底：确认 uvicorn 真的停了
sleep 2
if pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
  warn "uvicorn 仍在运行，强制清理 ..."
  pkill -f "uvicorn app.main:app" || true
  sleep 1
fi
ok "服务已停止"
echo ""

# ── Step 4: alembic upgrade ──────────────────────────────────
info "[4/5] 同步数据库 (alembic upgrade head) ..."

# 加载环境变量（与 start.sh 一致，alembic env.py 可能读 settings）
unset DEBUG DEBUG_MODE LLM_PROVIDER LLM_BASE_URL LLM_MODEL \
      OPENAI_API_KEY DEEPSEEK_API_KEY GLM_API_KEY KIMI_API_KEY CLAUDE_API_KEY \
      NEXT_PUBLIC_API_URL FRONTEND_MODE FRONTEND_URL
set -a
[ -f "$REPO_ROOT/.env" ] && source "$REPO_ROOT/.env"
[ -f "$REPO_ROOT/.env.prod" ] && source "$REPO_ROOT/.env.prod"
set +a

# 激活 conda
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$CONDA_ENV"

cd "$BACKEND_DIR"

# 升级前版本
BEFORE_REV="$(alembic current 2>/dev/null | awk '{print $1}' | head -1)"
info "升级前版本: ${BEFORE_REV:-<空>}"

# 执行升级
alembic upgrade head

# 升级后版本
AFTER_REV="$(alembic current 2>/dev/null | awk '{print $1}' | head -1)"
info "升级后版本: $AFTER_REV"

[ "$AFTER_REV" = "$EXPECTED_REVISION" ] || die "alembic 版本未达预期（期望 $EXPECTED_REVISION，实际 $AFTER_REV）"
ok "数据库已同步到 $AFTER_REV"
echo ""

# ── Step 5: 启动服务 ─────────────────────────────────────────
info "[5/5] 启动服务（生产模式）..."
cd "$REPO_ROOT"
./start.sh start prod
ok "启动命令已下发（服务在 tmux 后台启动）"
echo ""

# ── 部署后冒烟检测 ───────────────────────────────────────────
info "=== 部署后检测 ==="

# 等后端起来（最多 30 秒）
info "等待 backend 就绪 ..."
BE_READY=false
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/openapi.json >/dev/null 2>&1; then
    BE_READY=true
    break
  fi
  sleep 1
done
[ "$BE_READY" = "true" ] || die "backend 30 秒内未响应，请手动检查: tmux attach -t beingdoing"
ok "backend 已就绪 (${i}s)"

# 检测 1: alembic 版本（startup log 里会打印，这里直接查 DB）
info "检测 [1/2] alembic 版本一致性 ..."
DB_REV="$(alembic current 2>/dev/null | awk '{print $1}' | head -1)"
[ "$DB_REV" = "$EXPECTED_REVISION" ] && ok "DB 版本: $DB_REV ✓" || warn "DB 版本 $DB_REV ≠ $EXPECTED_REVISION"

# 检测 2: bounces 路由是否注册
info "检测 [2/2] bounces 路由注册 ..."
BOUNCE_PATHS="$(curl -s http://localhost:8000/openapi.json | python3 -c "
import sys, json
try:
    paths = json.load(sys.stdin).get('paths', {})
    hits = [p for p in paths if 'bounce' in p.lower()]
    print('\n'.join(hits) if hits else '')
except Exception:
    print('')
")"
if [ -n "$BOUNCE_PATHS" ]; then
  ok "bounces 路由已注册:"
  echo "$BOUNCE_PATHS" | sed 's/^/      /'
else
  warn "openapi.json 里没找到 bounce 路由（可能 admin 路由需要登录才显示，或代码未挂载）"
fi

# ── 提示手动确认项 ───────────────────────────────────────────
echo ""
ok "=== 部署完成 $(date '+%F %T') ==="
echo ""
warn "以下两项请手动确认："
echo ""
echo "  1) scheduler 启动日志（应看到 'bounce scheduler started'）："
echo "     tmux attach -t beingdoing    # Ctrl-B d 退出"
echo ""
echo "  2) 前端 admin 页面可访问："
echo "     浏览器打开 https://你的域名/admin/notifications"
echo ""
echo "=== 回滚命令（万一出问题）==="
echo "  cd $REPO_ROOT"
echo "  ./start.sh stop"
echo "  cp $BACKUP_FILE $DB_FILE"
echo "  git reset --hard $PREV_COMMIT"
echo "  ./start.sh start prod"
echo ""
info "备份文件: $BACKUP_FILE"
info "（旧备份超过 ${BACKUP_RETAIN_DAYS} 天的可手动清理: find $BACKEND_DIR -name 'app.db.bak.*' -mtime +${BACKUP_RETAIN_DAYS} -delete）"
