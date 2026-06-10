#!/usr/bin/env bash
# ============================================================
# start.sh — BeingDoing 开发服务管理脚本
#
# 用法：
#   ./start.sh              启动 backend + frontend（默认，仅加载 .env）
#   ./start.sh start        同上
#   ./start.sh start dev    开发环境：clean build + start（默认）
#   ./start.sh start prod   生产环境：clean build + start（默认）
#   ./start.sh start test   测试环境：clean build + start（默认）
#   ./start.sh start dev --hot    开发环境：热更新模式 (npm run dev)
#   ./start.sh start prod --hot  生产环境：热更新模式
#   ./start.sh start-dev    同 start dev（向后兼容）
#   ./start.sh start-run    同 start prod（向后兼容）
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

# ── 解析命令与环境参数 ───────────────────────────────────
COMMAND="${1:-start}"
TARGET="${2:-}"
# 第三个参数：--hot 表示前端使用热更新模式 (npm run dev)
HOT_MODE=false
if [ "${3:-}" = "--hot" ]; then
  HOT_MODE=true
fi

# 向后兼容：start-dev → dev, start-run → prod
if [ "$COMMAND" = "start-dev" ]; then
  TARGET="dev"; COMMAND="start"
elif [ "$COMMAND" = "start-run" ]; then
  TARGET="prod"; COMMAND="start"
fi

# 确定环境文件（dev / prod / test / 空）
ENV_FILE=""
ENV_LABEL=""
if [ -n "$TARGET" ]; then
  case "$TARGET" in
    dev|prod|test)
      ENV_FILE="$REPO_ROOT/.env.$TARGET"
      ENV_LABEL="$TARGET"
      if [ ! -f "$ENV_FILE" ]; then
        echo "[start.sh] 错误: $ENV_FILE 不存在"
        exit 1
      fi
      ;;
    *)
      echo "用法: ./start.sh start [dev|prod|test]"
      exit 1
      ;;
  esac
fi

# ── 关键：每次启动前先清理容易串项目的环境变量 ─────────
CONFLICT_ENV_VARS=(
  DEBUG DEBUG_MODE
  LLM_PROVIDER LLM_BASE_URL LLM_MODEL
  OPENAI_API_KEY DEEPSEEK_API_KEY
  GLM_API_KEY KIMI_API_KEY CLAUDE_API_KEY
  NEXT_PUBLIC_API_URL FRONTEND_MODE FRONTEND_URL
)
for v in "${CONFLICT_ENV_VARS[@]}"; do
  unset "$v" 2>/dev/null || true
done

# 加载 .env（base），再加载环境覆盖文件
if [ -f "$REPO_ROOT/.env" ]; then
  set -a; source "$REPO_ROOT/.env"; set +a
fi
if [ -n "$ENV_FILE" ]; then
  set -a; source "$ENV_FILE"; set +a
fi

BACKEND_DIR="$REPO_ROOT/src/backend"
FRONTEND_DIR="$REPO_ROOT/src/frontend"

# 构建 tmux 窗口内的环境加载命令（需要重新 unset + source）
UNSET_VARS="unset DEBUG DEBUG_MODE LLM_PROVIDER LLM_BASE_URL LLM_MODEL OPENAI_API_KEY DEEPSEEK_API_KEY GLM_API_KEY KIMI_API_KEY CLAUDE_API_KEY NEXT_PUBLIC_API_URL FRONTEND_MODE FRONTEND_URL"
ENV_LOAD_CMD="$UNSET_VARS; set -a; [ -f '$REPO_ROOT/.env' ] && source '$REPO_ROOT/.env'"
if [ -n "$ENV_FILE" ]; then
  ENV_LOAD_CMD="$ENV_LOAD_CMD; source '$ENV_FILE'"
fi
ENV_LOAD_CMD="$ENV_LOAD_CMD; set +a"

CONDA_BASE="${CONDA_BASE:-/mnt/vdb1/miniconda3}"
CONDA_ENV="py312"
# source conda.sh 使 conda activate 在非交互式 shell 里生效
BACKEND_CMD="$ENV_LOAD_CMD && source '$CONDA_BASE/etc/profile.d/conda.sh' && conda activate $CONDA_ENV && cd '$BACKEND_DIR' && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

# ── 前端运行模式 ────────────────────────────────────────
# 默认（dev/prod/test）：clean build + npm run start
# 加 --hot：热更新模式 npm run dev
# 无 TARGET（仅 ./start.sh）：按 .env 的 FRONTEND_MODE 决定

if [ "$HOT_MODE" = "true" ]; then
  RUN_MODE="dev"
elif [ -n "$TARGET" ]; then
  # 有明确环境参数（dev/prod/test）→ 一律 clean build + start
  RUN_MODE="production"
elif [ "${FRONTEND_MODE:-}" = "production" ]; then
  RUN_MODE="production"
else
  RUN_MODE="dev"
fi

if [ "$RUN_MODE" = "production" ]; then
  FRONTEND_CMD="$ENV_LOAD_CMD && cd '$FRONTEND_DIR' && rm -rf .next && npm run build && FRONTEND_MODE=production npm run start"
  FRONTEND_MODE_LABEL="production (clean build)"
else
  FRONTEND_CMD="$ENV_LOAD_CMD && cd '$FRONTEND_DIR' && FRONTEND_MODE=dev npm run dev"
  FRONTEND_MODE_LABEL="dev (hot reload)"
fi

# ── 颜色输出 ────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
info()  { echo -e "${CYAN}[start.sh]${RESET} $*"; }
ok()    { echo -e "${GREEN}[start.sh]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[start.sh]${RESET} $*"; }

# Next.js 生产 Server Actions：稳定密钥可避免多次 build 后旧标签页请求解密失败（日志里偶见 Failed to find Server Action "x"）
if [ "$RUN_MODE" = "production" ] && [ -z "${NEXT_SERVER_ACTIONS_ENCRYPTION_KEY:-}" ]; then
  warn "生产模式 frontend：.env 未设置 NEXT_SERVER_ACTIONS_ENCRYPTION_KEY。"
  warn "建议写入 openssl rand -base64 32 的随机串（不要写命令本身），保存后 ./start.sh start prod 重新 build。"
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
    warn "tmux session '$SESSION' 已存在。如需重启请用: ./start.sh restart"
    if [ -t 1 ] && [ -t 0 ] && [ "${BD_SKIP_TMUX_ATTACH:-0}" != "1" ]; then
      tmux attach-session -t "$SESSION"
    else
      info "已跳过 tmux attach；查看会话： tmux attach -t $SESSION"
    fi
    return
  fi

  local env_info="($FRONTEND_MODE_LABEL)"
  if [ -n "$ENV_LABEL" ]; then
    env_info="($ENV_LABEL, $FRONTEND_MODE_LABEL)"
  fi

  info "创建 tmux session '$SESSION'…"
  # 创建 session，第一个窗口先命名为 backend
  tmux new-session -d -s "$SESSION" -n backend
  tmux send-keys -t "$SESSION:backend" "$BACKEND_CMD" Enter

  start_frontend

  # 默认选中 backend 窗口
  tmux select-window -t "$SESSION:backend"

  ok "服务已启动！$env_info"
  echo ""
  echo "  Backend  → http://localhost:8000"
  echo "  Frontend → http://localhost:3000"
  echo ""
  echo "  附加到终端查看日志：  tmux attach -t $SESSION"
  echo "  在 tmux 中分离：      Ctrl-B  d"
  echo ""
  # 无 TTY 时 attach 会报错 open terminal failed: not a terminal，脚本以非 0 退出，误判为启动失败
  if [ -t 1 ] && [ -t 0 ] && [ "${BD_SKIP_TMUX_ATTACH:-0}" != "1" ]; then
    tmux attach-session -t "$SESSION"
  else
    info "已跳过 tmux attach（当前无交互终端或已设 BD_SKIP_TMUX_ATTACH=1）。进程在 tmux 后台运行；查看日志仍可用： tmux attach -t $SESSION"
  fi
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
    echo "用法: ./start.sh [start [dev|prod|test] [--hot]] | start-dev | start-run | stop | restart [backend|frontend|all] | attach"
    exit 1 ;;
esac
