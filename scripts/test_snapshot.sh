#!/usr/bin/env bash
# 不加载业务 .env，不调用部署脚本；Python 由操作者明确选择。
set -euo pipefail
BD_SNAPSHOT_REPO="$(cd "$(dirname "$0")/.." && pwd)"
exec "${BD_SNAPSHOT_PYTHON:-python3}" "$BD_SNAPSHOT_REPO/scripts/test_snapshot.py" "$@"
