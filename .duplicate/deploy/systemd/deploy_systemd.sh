#!/usr/bin/env bash
set -euo pipefail

# BeingDoing systemd deploy helper
# - Installs/updates service files
# - Syncs env file
# - Reloads and restarts services
# - Prints status summary

PROJECT_ROOT="/home/gitclone/BeingDoing"
SYSTEMD_DIR="/etc/systemd/system"
SYSTEM_ENV_FILE="/etc/beingdoing.env"

BACKEND_SERVICE_NAME="beingdoing-backend.service"
FRONTEND_SERVICE_NAME="beingdoing-frontend.service"

BACKEND_SERVICE_SRC="$PROJECT_ROOT/deploy/systemd/$BACKEND_SERVICE_NAME"
FRONTEND_SERVICE_SRC="$PROJECT_ROOT/deploy/systemd/$FRONTEND_SERVICE_NAME"
ENV_TEMPLATE_SRC="$PROJECT_ROOT/deploy/systemd/beingdoing.env.example"
PROJECT_ENV_SRC="$PROJECT_ROOT/.env"

ENV_SOURCE="${ENV_TEMPLATE_SRC}"
RESTART_SERVICES=true
ENABLE_SERVICES=true

usage() {
  echo "Usage: $0 [--from-project-env] [--from-template] [--no-restart] [--no-enable]"
  echo ""
  echo "Options:"
  echo "  --from-project-env  Use $PROJECT_ENV_SRC as /etc/beingdoing.env source"
  echo "  --from-template     Use template env (default): $ENV_TEMPLATE_SRC"
  echo "  --no-restart        Do not restart services after install"
  echo "  --no-enable         Do not enable services on boot"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --from-project-env)
      ENV_SOURCE="$PROJECT_ENV_SRC"
      ;;
    --from-template)
      ENV_SOURCE="$ENV_TEMPLATE_SRC"
      ;;
    --no-restart)
      RESTART_SERVICES=false
      ;;
    --no-enable)
      ENABLE_SERVICES=false
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
  shift
done

if [ "$(id -u)" -ne 0 ]; then
  echo "This script must run as root."
  echo "Try: sudo $0 $*"
  exit 1
fi

for required in "$BACKEND_SERVICE_SRC" "$FRONTEND_SERVICE_SRC" "$ENV_SOURCE"; do
  if [ ! -f "$required" ]; then
    echo "Required file not found: $required"
    exit 1
  fi
done

echo "[deploy] Installing service files..."
cp "$BACKEND_SERVICE_SRC" "$SYSTEMD_DIR/$BACKEND_SERVICE_NAME"
cp "$FRONTEND_SERVICE_SRC" "$SYSTEMD_DIR/$FRONTEND_SERVICE_NAME"

echo "[deploy] Installing env file from: $ENV_SOURCE"
cp "$ENV_SOURCE" "$SYSTEM_ENV_FILE"
chmod 600 "$SYSTEM_ENV_FILE"

echo "[deploy] Reloading systemd daemon..."
systemctl daemon-reload

if [ "$ENABLE_SERVICES" = true ]; then
  echo "[deploy] Enabling services on boot..."
  systemctl enable beingdoing-backend beingdoing-frontend
fi

if [ "$RESTART_SERVICES" = true ]; then
  echo "[deploy] Restarting services..."
  systemctl restart beingdoing-backend beingdoing-frontend
fi

echo "[deploy] Service status:"
systemctl --no-pager --full status beingdoing-backend beingdoing-frontend || true

echo ""
echo "[deploy] Done."
echo "Env file in use: $SYSTEM_ENV_FILE"
echo "Tip: verify runtime env with:"
echo "  systemctl show beingdoing-backend --property=Environment"
