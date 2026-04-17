#!/usr/bin/env bash
# ============================================================
# start.sh — BeingDoing 开发服务管理脚本
#
# 用法：
#   ./start.sh              启动 backend + frontend（默认）
#   ./start.sh start        同上
#   ./start.sh start-dev    以开发模式启动（frontend: next dev）
#   ./start.sh start-run    以运行模式启动（frontend: 清理 .next + build + start）
#   ./start.sh stop         关闭所有窗口并销毁 tmux session
#   ./start.sh restart      重启所有服务
#   ./start.sh restart backend   仅重启 backend
#   ./start.sh restart frontend  仅重启 frontend
#   ./start.sh attach       重新附加到已有 session（查看日志）
#
# 依赖：tmux（已预装）
# ============================================================

set -e

SESSION="beingdoing"
REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"

# 关键：每次启动前先清理容易串项目的环境变量，再仅加载本项目 .env
CONFLICT_ENV_VARS=(
  DEBUG DEBUG_MODE
  LLM_PROVIDER LLM_BASE_URL LLM_MODEL
  OPENAI_API_KEY DEEPSEEK_API_KEY
  GLM_API_KEY KIMI_API_KEY CLAUDE_API_KEY
  NEXT_PUBLIC_API_URL FRONTEND_MODE
)
for v in "${CONFLICT_ENV_VARS[@]}"; do
  unset "$v" 2>/dev/null || true
done
if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi
BACKEND_DIR="$REPO_ROOT/src/backend"
FRONTEND_DIR="$REPO_ROOT/src/frontend"
ENV_LOAD_CMD="unset DEBUG DEBUG_MODE LLM_PROVIDER LLM_BASE_URL LLM_MODEL OPENAI_API_KEY DEEPSEEK_API_KEY GLM_API_KEY KIMI_API_KEY CLAUDE_API_KEY NEXT_PUBLIC_API_URL FRONTEND_MODE; set -a; [ -f \"$REPO_ROOT/.env\" ] && source \"$REPO_ROOT/.env\"; set +a"

CONDA_BASE="/mnt/vdb1/miniconda3"
CONDA_ENV="py312"
# source conda.sh 使 conda activate 在非交互式 shell 里生效
BACKEND_CMD="$ENV_LOAD_CMD && source '$CONDA_BASE/etc/profile.d/conda.sh' && conda activate $CONDA_ENV && cd '$BACKEND_DIR' && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

COMMAND="${1:-start}"
TARGET="${2:-}"

# 默认根据 .env 的 FRONTEND_MODE 推断；可被 start-dev / start-run 覆盖
if [ "${FRONTEND_MODE:-}" = "production" ]; then
  RUN_MODE="production"
else
  RUN_MODE="dev"
fi

if [ "$COMMAND" = "start-dev" ]; then
  RUN_MODE="dev"
  COMMAND="start"
fi

if [ "$COMMAND" = "start-run" ]; then
  RUN_MODE="production"
  FORCE_CLEAN_BUILD="1"
  COMMAND="start"
fi

if [ "$RUN_MODE" = "production" ]; then
  if [ "${FORCE_CLEAN_BUILD:-0}" = "1" ]; then
    # start-run 场景：强制清理构建缓存并重新 build，避免旧产物/manifest 导致线上异常
    FRONTEND_CMD="$ENV_LOAD_CMD && cd '$FRONTEND_DIR' && rm -rf .next && npm run build && FRONTEND_MODE=production npm run start"
  else
    FRONTEND_CMD="$ENV_LOAD_CMD && cd '$FRONTEND_DIR' && (test -f .next/BUILD_ID || npm run build) && FRONTEND_MODE=production npm run start"
  fi
  FRONTEND_MODE_LABEL="production"
else
  FRONTEND_CMD="$ENV_LOAD_CMD && cd '$FRONTEND_DIR' && FRONTEND_MODE=dev npm run dev"
  FRONTEND_MODE_LABEL="dev"
fi

# ── 颜色输出 ────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
info()  { echo -e "${CYAN}[start.sh]${RESET} $*"; }
ok()    { echo -e "${GREEN}[start.sh]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[start.sh]${RESET} $*"; }

# Next.js 生产 Server Actions：稳定密钥可避免多次 build 后旧标签页请求解密失败（日志里偶见 Failed to find Server Action "x"）
if [ "$RUN_MODE" = "production" ] && [ -z "${NEXT_SERVER_ACTIONS_ENCRYPTION_KEY:-}" ]; then
  warn "生产模式 frontend：.env 未设置 NEXT_SERVER_ACTIONS_ENCRYPTION_KEY。"
  warn "建议写入 openssl rand -base64 32 的随机串（不要写命令本身），保存后 ./start.sh start-run 重新 build。"
fi

# ── 辅助函数 ────────────────────────────────────────────────

session_exists() {
  tmux has-session -t "$SESSION" 2>/dev/null
}

start_backend() {
  info "启动 backend (窗口 backend)…"
  tmux new-window -t "$SESSION" -n backend
  tmux send-keys -t "$SESSION:backend" "$BACKEND_CMD" Enter
}

start_frontend() {
  info "启动 frontend (窗口 frontend)…"
  tmux new-window -t "$SESSION" -n frontend
  tmux send-keys -t "$SESSION:frontend" "$FRONTEND_CMD" Enter
}

kill_window() {
  local win="$1"
  if tmux list-windows -t "$SESSION" 2>/dev/null | grep -q "^[0-9]*: $win"; then
    info "关闭窗口 $win…"
    tmux kill-window -t "$SESSION:$win" 2>/dev/null || true
  fi
}

cmd_start() {
  if session_exists; then
    warn "tmux session '$SESSION' 已存在，直接附加。如需重启请用: ./start.sh restart"
    tmux attach-session -t "$SESSION"
    return
  fi

  info "创建 tmux session '$SESSION'…"
  # 创建 session，第一个窗口先命名为 backend
  tmux new-session -d -s "$SESSION" -n backend
  tmux send-keys -t "$SESSION:backend" "$BACKEND_CMD" Enter

  start_frontend

  # 默认选中 backend 窗口
  tmux select-window -t "$SESSION:backend"

  ok "服务已启动！（frontend mode: $FRONTEND_MODE_LABEL）"
  echo ""
  echo "  Backend  → http://localhost:8000"
  echo "  Frontend → http://localhost:3000"
  echo ""
  echo "  附加到终端查看日志：  tmux attach -t $SESSION"
  echo "  在 tmux 中分离：      Ctrl-B  d"
  echo ""
  tmux attach-session -t "$SESSION"
}

cmd_stop() {
  if session_exists; then
    info "停止并销毁 session '$SESSION'…"
    tmux kill-session -t "$SESSION"
    ok "已停止。"
  else
    warn "session '$SESSION' 不存在，无需停止。"
  fi
  # tmux 强杀时，uvicorn --reload 的子进程偶发仍会占用 8000；stop 只杀 session 不能保证端口已释放。
  # 这里再收一遍「本项目的」监听进程（命令行含 app.main:app），避免你停干净后仍报 Address already in use。
  if pgrep -f "uvicorn app.main:app" >/dev/null 2>&1; then
    info "清理残留的 uvicorn (app.main:app)…"
    pkill -f "uvicorn app.main:app" 2>/dev/null || true
    sleep 0.5
  fi
}

cmd_restart_backend() {
  if ! session_exists; then
    warn "session '$SESSION' 不存在，请先运行 ./start.sh"
    exit 1
  fi
  kill_window backend
  start_backend
  ok "backend 已重启。"
  tmux select-window -t "$SESSION:backend"
}

cmd_restart_frontend() {
  if ! session_exists; then
    warn "session '$SESSION' 不存在，请先运行 ./start.sh"
    exit 1
  fi
  kill_window frontend
  start_frontend
  ok "frontend 已重启。"
  tmux select-window -t "$SESSION:frontend"
}

cmd_restart_all() {
  info "重启全部服务…"
  if session_exists; then
    kill_window backend
    kill_window frontend
    start_backend
    start_frontend
    tmux select-window -t "$SESSION:backend"
    ok "全部服务已重启。"
  else
    warn "session '$SESSION' 不存在，正在全新启动…"
    cmd_start
  fi
}

cmd_attach() {
  if session_exists; then
    tmux attach-session -t "$SESSION"
  else
    warn "session '$SESSION' 不存在，请先运行 ./start.sh"
    exit 1
  fi
}

# ── 入口 ────────────────────────────────────────────────────

case "$COMMAND" in
  start)
    cmd_start ;;
  stop)
    cmd_stop ;;
  restart)
    case "$TARGET" in
      backend)  cmd_restart_backend ;;
      frontend) cmd_restart_frontend ;;
      all|"")   cmd_restart_all ;;
      *) echo "用法: ./start.sh restart [backend|frontend|all]"; exit 1 ;;
    esac
    ;;
  attach)
    cmd_attach ;;
  *)
    echo "用法: ./start.sh [start|start-dev|start-run|stop|restart [backend|frontend|all]|attach]"
    exit 1 ;;
esac
