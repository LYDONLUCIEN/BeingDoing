"""
static_tools.py —— 批量导出 zip 解压后的统计聚合工具

用法：
    python scripts/static_tools.py <zip解压后的根目录> [-o 输出csv路径]

功能：
    扫描指定目录下所有 report 子目录（每个子目录含一份 stats.json 和 raw/ 源文件），
    汇总成一份 CSV，每行一个 report，列含：
      - report_id
      - 五个阶段（values/strengths/interests/purpose/rumination）各自的：
          * prompt_tokens        AI 输入 token（来自 stats.json）
          * completion_tokens    AI 输出 token（来自 stats.json）
          * total_tokens         AI 总 token（来自 stats.json）
          * user_input_tokens    用户输入 token（脚本现场用 tiktoken 估算）
          * duration_seconds     活跃时长（秒，30min 超时切分口径）
          * duration_min         活跃时长（分钟）

说明：
    1. stats.json 里 token_usage 只挂在 assistant 消息上，是 AI 接口返回的
       prompt/completion/total，不含「纯用户输入」的 token。因此 user_input_tokens
       由本脚本读取 raw/{step}__{session}.json，对每条 role=user 消息的 content
       用 tiktoken 现场编码估算（编码器 cl100k_base，DeepSeek 等国产模型的通用近似）。
    2. 缺失该阶段的 report，对应列留空。
    3. 脚本不依赖后端代码，纯离线处理。

示例：
    # zip 解压到 ./exports，输出到 ./exports_summary.csv
    python scripts/static_tools.py ./exports -o ./exports_summary.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger("static_tools")

# 五个阶段固定顺序
PHASES = ["values", "strengths", "interests", "purpose", "rumination"]

# tiktoken 编码器（惰性加载，缺失时降级为字数估算）
_ENCODER = None


def _get_encoder():
    """惰性加载 tiktoken cl100k_base。不可用则返回 None，降级为字数估算。"""
    global _ENCODER
    if _ENCODER is not None:
        return _ENCODER
    try:
        import tiktoken

        _ENCODER = tiktoken.get_encoding("cl100k_base")
        return _ENCODER
    except Exception as e:
        logger.warning(
            "tiktoken 不可用（%s），user_input_tokens 将用「字数×1.3」粗略估算",
            e,
        )
        return None


def estimate_user_tokens(text: str) -> int:
    """
    估算用户输入文本的 token 数。
    优先用 tiktoken cl100k_base；不可用时按中英混合经验值（字数×1.3）粗估。
    """
    if not text:
        return 0
    enc = _get_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    # 降级：中文约 1 字 ≈ 1.3 token，英文约 4 字符 ≈ 1 token，取折中
    return int(len(text) * 1.3)


def _content_to_text(content) -> str:
    """把消息 content（str/list/dict）转纯文本，与后端统计口径一致。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                parts.append(c.get("text") or "")
            else:
                parts.append(str(c))
        return "".join(parts)
    if isinstance(content, dict):
        return content.get("text") or str(content)
    return str(content)


def _load_json(path: Path) -> Optional[dict]:
    try:
        return json.loads(path.read_text(encoding="utf-8") or "{}")
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("JSON 解析失败: %s err=%s", path, e)
        return None


def _compute_user_tokens_from_raw(raw_path: Path) -> int:
    """读 raw 源文件，累加所有 role=user 消息的 content token 估算值。"""
    raw = _load_json(raw_path)
    if not raw:
        return 0
    msgs = raw.get("messages") or []
    total = 0
    for m in msgs:
        if not isinstance(m, dict):
            continue
        if (m.get("role") or "") != "user":
            continue
        total += estimate_user_tokens(_content_to_text(m.get("content")))
    return total


def _find_raw_for_phase(report_dir: Path, step_id: str, session_id: Optional[str]) -> Optional[Path]:
    """在 report_dir/raw/ 下定位该阶段的源文件。优先精确名，否则按前缀模糊匹配。"""
    raw_dir = report_dir / "raw"
    if not raw_dir.is_dir():
        return None
    if session_id:
        exact = raw_dir / f"{step_id}__{session_id}.json"
        if exact.is_file():
            return exact
    # 兜底：按 {step_id}__ 前缀匹配（session_id 不一致时）
    matches = sorted(raw_dir.glob(f"{step_id}__*.json"))
    return matches[0] if matches else None


def collect_report_row(report_dir: Path) -> Optional[Dict]:
    """
    解析单个 report 子目录，返回一行 CSV 数据。
    无 stats.json 则返回 None。
    """
    stats_path = report_dir / "stats.json"
    stats = _load_json(stats_path)
    if not stats:
        return None

    row: Dict = {"report_id": stats.get("report_id") or report_dir.name}

    # 按 step_id 建索引，便于取该阶段的统计
    phase_map: Dict[str, dict] = {}
    for ph in stats.get("phases") or []:
        sid = ph.get("step_id")
        if sid:
            phase_map[sid] = ph

    for step_id in PHASES:
        ph = phase_map.get(step_id)
        tu = (ph or {}).get("token_usage") or {}
        sess = (ph or {}).get("session_id")

        # 三个 AI 侧 token（stats.json 已有）
        row[f"{step_id}__prompt_tokens"] = tu.get("prompt_tokens", "")
        row[f"{step_id}__completion_tokens"] = tu.get("completion_tokens", "")
        row[f"{step_id}__total_tokens"] = tu.get("total_tokens", "")

        # 用户输入 token：脚本现场读 raw 源文件估算
        if ph is None:
            row[f"{step_id}__user_input_tokens"] = ""
        else:
            raw_path = _find_raw_for_phase(report_dir, step_id, sess)
            row[f"{step_id}__user_input_tokens"] = (
                _compute_user_tokens_from_raw(raw_path) if raw_path else ""
            )

        # 耗时：秒数 + 分钟两个口径
        dur_sec = (ph or {}).get("duration_seconds")
        row[f"{step_id}__duration_seconds"] = dur_sec if dur_sec is not None else ""
        row[f"{step_id}__duration_min"] = (
            round(dur_sec / 60, 1) if isinstance(dur_sec, (int, float)) else ""
        )

    return row


def build_csv_header() -> List[str]:
    cols = ["report_id"]
    for step_id in PHASES:
        cols.extend(
            [
                f"{step_id}__prompt_tokens",
                f"{step_id}__completion_tokens",
                f"{step_id}__total_tokens",
                f"{step_id}__user_input_tokens",
                f"{step_id}__duration_seconds",
                f"{step_id}__duration_min",
            ]
        )
    return cols


def aggregate(root: Path, out_csv: Path) -> int:
    """
    扫描 root 下所有含 stats.json 的子目录，聚合输出 CSV。
    返回处理的 report 数量。
    """
    # 候选：root 本身 / root 的每个一级子目录 / 递归所有含 stats.json 的目录
    candidate_dirs: List[Path] = []
    if (root / "stats.json").is_file():
        candidate_dirs.append(root)
    for child in sorted(root.iterdir()) if root.is_dir() else []:
        if child.is_dir() and (child / "stats.json").is_file():
            candidate_dirs.append(child)
    # 兜底递归（zip 结构有额外层级时）
    if not candidate_dirs:
        candidate_dirs = sorted({p.parent for p in root.rglob("stats.json")})

    rows: List[Dict] = []
    for d in candidate_dirs:
        row = collect_report_row(d)
        if row is not None:
            rows.append(row)

    if not rows:
        logger.error("未在 %s 下找到任何 stats.json", root)
        return 0

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    header = build_csv_header()
    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    logger.info("已写入 %d 条 report -> %s", len(rows), out_csv)
    return len(rows)


def main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(message)s",
    )
    parser = argparse.ArgumentParser(
        description="聚合批量导出 zip 解压目录下的 stats.json 为 CSV",
    )
    parser.add_argument(
        "input_dir",
        type=str,
        help="zip 解压后的根目录（每个 report 子目录含 stats.json 和 raw/）",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="输出 CSV 路径，默认 <input_dir>_summary.csv",
    )
    args = parser.parse_args(argv)

    root = Path(args.input_dir).expanduser().resolve()
    if not root.is_dir():
        logger.error("输入不是目录: %s", root)
        return 2

    out_csv = Path(args.output).expanduser().resolve() if args.output else root.with_name(
        root.name + "_summary.csv"
    )

    # 预热 tokenizer
    _get_encoder()

    n = aggregate(root, out_csv)
    if n == 0:
        return 1
    print(f"\n完成：{n} 个 report，CSV -> {out_csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
