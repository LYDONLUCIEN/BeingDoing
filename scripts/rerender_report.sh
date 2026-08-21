#!/usr/bin/env bash
# 按激活码重新渲染报告 PDF（xunlu 精简渲染器，ADR-0019）
#
# 用法：
#   scripts/rerender_report.sh <激活码> [输出目录]
#
# 行为：
#   1. 在 data/simple/reports/*/record.json 中按 activation_code 反查报告
#   2. 检查报告 markdown 缓存（report_markdown.md）是否存在；不存在则提醒并退出
#   3. 从 record.json 取签名方案与报告生成日期（与正式件一致）
#   4. 调 src/report-renderer 渲染 PDF，输出到 [输出目录]/寻路报告_<激活码>_<report_id前8位>.pdf
#
# 依赖：Node ≥20 + Chrome（渲染器）；python3（解析 record.json）
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORTS_DIR="$REPO_ROOT/data/simple/reports"
RENDERER="$REPO_ROOT/src/report-renderer/dist/render-pdf.mjs"

CODE="${1:-}"
OUT_DIR="${2:-$REPO_ROOT/output/reports}"

if [[ -z "$CODE" ]]; then
  echo "用法：$0 <激活码> [输出目录]" >&2
  exit 2
fi

if [[ ! -f "$RENDERER" ]]; then
  echo "错误：渲染器未构建（$RENDERER 不存在）" >&2
  echo "请先执行：cd src/report-renderer && npm install && npm run build" >&2
  exit 1
fi

# 1. 激活码 → record.json
RECORD_FILE=""
for f in "$REPORTS_DIR"/*/record.json; do
  [[ -f "$f" ]] || continue
  if grep -q "\"activation_code\": \"$CODE\"" "$f" 2>/dev/null; then
    RECORD_FILE="$f"
    break
  fi
done

if [[ -z "$RECORD_FILE" ]]; then
  echo "未找到激活码 $CODE 对应的报告（data/simple/reports 下无此 activation_code）" >&2
  exit 1
fi

REPORT_ID="$(basename "$(dirname "$RECORD_FILE")")"
MD_FILE="$(dirname "$RECORD_FILE")/report_markdown.md"

# 2. markdown 缓存存在性检查
if [[ ! -s "$MD_FILE" ]]; then
  echo "报告 $REPORT_ID（激活码 $CODE）尚未生成 markdown 缓存：$MD_FILE 不存在" >&2
  echo "请先走报告生成流程（生成报告 / 审核批复自动生成）后再渲染。" >&2
  exit 1
fi

# 3. 元数据：签名方案 + 报告日期（缺失则用渲染器默认）
META="$(python3 - "$RECORD_FILE" <<'EOF'
import json, sys
from datetime import datetime
rec = json.load(open(sys.argv[1]))
sig = {"signature_1": "01", "signature_2": "02", "signature_3": "03"}.get(rec.get("report_signature"), "")
raw = rec.get("report_markdown_generated_at") or ""
date_text = ""
if raw:
    try:
        date_text = datetime.fromisoformat(str(raw)).strftime("%Y 年 %m 月 %d 日")
    except ValueError:
        date_text = ""
print(f"{sig}\t{date_text}")
EOF
)"
SIG="${META%%$'\t'*}"
DATE_TEXT="${META#*$'\t'}"

# 4. 渲染
mkdir -p "$OUT_DIR"
OUT_PDF="$OUT_DIR/寻路报告_${CODE}_${REPORT_ID:0:8}.pdf"

ARGS=(--md "$MD_FILE" --out "$OUT_PDF")
[[ -n "$SIG" ]] && ARGS+=(--signature "$SIG")
[[ -n "$DATE_TEXT" ]] && ARGS+=(--date "$DATE_TEXT")

echo "渲染中：报告 $REPORT_ID（激活码 $CODE，签名 ${SIG:-默认}，日期 ${DATE_TEXT:-当天}）..."
node "$RENDERER" "${ARGS[@]}"

echo "完成：$OUT_PDF"
