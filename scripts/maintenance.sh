#!/usr/bin/env bash
# ============================================================
# maintenance.sh — 维护模式切换脚本（nginx 静态页硬拦截）
#
# 工作机制：
#   on  → 用模板替换占位符 → 拷贝到目标路径 → touch flag → nginx reload
#   off → rm flag → nginx reload
#   status → 看 flag 是否存在
#
# nginx 配置一次性加好（见 plan），脚本只切 flag 文件 + reload。
#
# 用法：
#   ./scripts/maintenance.sh on  [--end "2026-07-05 04:00"] [--reason "数据库升级"] [--env dev|prod]
#   ./scripts/maintenance.sh off [--env dev|prod]
#   ./scripts/maintenance.sh status [--env dev|prod]
#
# 环境变量（从 .env.$ENV 读取，默认 dev）：
#   MAINTENANCE_FLAG_PATH     flag 文件路径（nginx 检测它存在则进入维护）
#   MAINTENANCE_PAGE_DIR      维护页 HTML 输出目录
#   NGINX_RELOAD_CMD          nginx 重载命令（默认 "nginx -s reload"）
#   BYPASS_COOKIE_NAME        绕过 cookie 名（默认 bypass_maintenance）
# ============================================================

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ACTION="${1:-}"
ENV_NAME="${ENV_NAME:-dev}"

# ── 颜色 ─────────────────────────────────────────────────────
G='\033[0;32m'; Y='\033[1;33m'; R='\033[0;31m'; C='\033[0;36m'; B='\033[1m'; X='\033[0m'
info() { echo -e "${C}[maint]${X} $*"; }
ok()   { echo -e "${G}[maint]${X} $*"; }
warn() { echo -e "${Y}[maint]${X} $*"; }
die()  { echo -e "${R}[maint 错误]${X} $*" >&2; exit 1; }

# ── 解析 --env 和额外参数 ─────────────────────────────────────
END_AT=""
REASON=""
shift_args=()
for arg in "$@"; do
  case "$arg" in
    --env) ENV_NAME="__next__" ;;      # 占位，下个参数覆盖
    --env=*) ENV_NAME="${arg#--env=}" ;;
    --end) END_AT="__next__" ;;
    --end=*) END_AT="${arg#--end=}" ;;
    --reason) REASON="__next__" ;;
    --reason=*) REASON="${arg#--reason=}" ;;
    *)
      # 处理 --xx __next__ 的取值模式
      if [ "$END_AT" = "__next__" ]; then END_AT="$arg"
      elif [ "$REASON" = "__next__" ]; then REASON="$arg"
      elif [ "$ENV_NAME" = "__next__" ]; then ENV_NAME="$arg"
      else shift_args+=("$arg"); fi
      ;;
  esac
done
[ "$END_AT" = "__next__" ] && END_AT=""
[ "$REASON" = "__next__" ] && REASON=""

# ── source .env.$ENV_NAME ────────────────────────────────────
ENV_FILE="$REPO_ROOT/.env.$ENV_NAME"
if [ ! -f "$ENV_FILE" ]; then
  die "环境文件不存在: $ENV_FILE"
fi
set -a; source "$ENV_FILE"; set +a

# 默认值
MAINTENANCE_FLAG_PATH="${MAINTENANCE_FLAG_PATH:-/www/sites/zhiyinapp/maintenance.flag}"
MAINTENANCE_PAGE_DIR="${MAINTENANCE_PAGE_DIR:-/www/sites/zhiyinapp/maintenance}"
MAINTENANCE_TEMPLATE_PATH="${MAINTENANCE_TEMPLATE_PATH:-$REPO_ROOT/src/frontend/maintenance.html}"
NGINX_RELOAD_CMD="${NGINX_RELOAD_CMD:-nginx -s reload}"
BYPASS_COOKIE_NAME="${BYPASS_COOKIE_NAME:-bypass_maintenance}"

# ── 帮助 ─────────────────────────────────────────────────────
usage() {
  cat <<EOF
用法: ./scripts/maintenance.sh <on|off|status> [选项]

选项:
  --env dev|prod       选择环境（默认 dev）
  --end "2026-07-05 04:00"   维护页显示的预计恢复时间
  --reason "数据库升级"      维护页显示的维护原因

环境: $ENV_NAME
flag:  $MAINTENANCE_FLAG_PATH
page:  $MAINTENANCE_PAGE_DIR/maintenance.html

示例:
  ./scripts/maintenance.sh on --end "2026-07-05 04:00" --reason "数据库升级" --env prod
  ./scripts/maintenance.sh off --env prod
  ./scripts/maintenance.sh status
EOF
}

# ── on: 渲染模板 + 创建 flag + reload ────────────────────────
do_on() {
  [ -f "$MAINTENANCE_TEMPLATE_PATH" ] || die "模板不存在: $MAINTENANCE_TEMPLATE_PATH"

  # 创建输出目录
  mkdir -p "$MAINTENANCE_PAGE_DIR" 2>/dev/null || die "无法创建目录: $MAINTENANCE_PAGE_DIR（权限不足？sudo 执行）"

  OUT_FILE="$MAINTENANCE_PAGE_DIR/maintenance.html"

  # 占位符替换（用 sed，安全转义 / & 等）
  esc_end=$(printf '%s' "${END_AT:-稍后}" | sed 's/[&/\]/\\&/g')
  esc_reason=$(printf '%s' "${REASON:-例行升级}" | sed 's/[&/\]/\\&/g')

  info "渲染模板 → $OUT_FILE"
  info "  原因: ${REASON:-例行升级}"
  info "  恢复: ${END_AT:-稍后}"
  sed \
    -e "s|<span data-slot=\"reason\">[^<]*</span>|<span data-slot=\"reason\">$esc_reason</span>|" \
    -e "s|<strong data-slot=\"end_at\">[^<]*</strong>|<strong data-slot=\"end_at\">$esc_end</strong>|" \
    "$MAINTENANCE_TEMPLATE_PATH" > "$OUT_FILE" || die "渲染失败"

  # 创建 flag
  info "创建 flag: $MAINTENANCE_FLAG_PATH"
  touch "$MAINTENANCE_FLAG_PATH" || die "无法创建 flag（权限不足？sudo 执行）"
  echo "{\"env\":\"$ENV_NAME\",\"reason\":\"$REASON\",\"end_at\":\"$END_AT\",\"switched_at\":\"$(date -Iseconds)\"}" > "$MAINTENANCE_FLAG_PATH"

  # nginx reload
  info "reload nginx: $NGINX_RELOAD_CMD"
  if eval "$NGINX_RELOAD_CMD"; then
    ok "维护模式已开启"
  else
    warn "nginx reload 失败，请手动检查: $NGINX_RELOAD_CMD"
  fi

  cat <<EOF

${B}━━━ 维护模式已开启 ━━━${X}
用户访问站点将看到维护页。
你（管理员）请在浏览器 DevTools Console 执行：

  ${C}document.cookie='${BYPASS_COOKIE_NAME}=1;path=/;max-age=86400;domain=.soulhappylab.com'${X}

即可绕过维护页，走正常 HTTPS 验证。

完成部署后退出维护：
  ${C}./scripts/maintenance.sh off --env $ENV_NAME${X}
EOF
}

# ── off: 删除 flag + reload ──────────────────────────────────
do_off() {
  if [ ! -f "$MAINTENANCE_FLAG_PATH" ]; then
    warn "flag 不存在，本就不在维护模式: $MAINTENANCE_FLAG_PATH"
    exit 0
  fi
  info "删除 flag: $MAINTENANCE_FLAG_PATH"
  rm -f "$MAINTENANCE_FLAG_PATH" || die "无法删除 flag（权限不足？sudo 执行）"

  info "reload nginx: $NGINX_RELOAD_CMD"
  if eval "$NGINX_RELOAD_CMD"; then
    ok "维护模式已关闭，用户恢复访问"
  else
    warn "nginx reload 失败，请手动检查: $NGINX_RELOAD_CMD"
  fi
}

# ── status ───────────────────────────────────────────────────
do_status() {
  if [ -f "$MAINTENANCE_FLAG_PATH" ]; then
    echo -e "${R}[maint]${X} 状态: ${B}ON (维护中)${X}"
    echo "  flag: $MAINTENANCE_FLAG_PATH"
    echo "  内容: $(cat "$MAINTENANCE_FLAG_PATH" 2>/dev/null)"
  else
    echo -e "${G}[maint]${X} 状态: OFF (正常运行)"
  fi
}

# ── 入口 ─────────────────────────────────────────────────────
case "$ACTION" in
  on)     do_on ;;
  off)    do_off ;;
  status) do_status ;;
  ""|-h|--help|help) usage ;;
  *) die "未知动作: $ACTION（应为 on/off/status）" ;;
esac
