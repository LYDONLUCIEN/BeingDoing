#!/usr/bin/env python3
"""
数据同步脚本 - 手动同步 debug 日志和 answer card 数据

功能：
1. sync_debug_logs  - 将 logs/ 和 data/debug_logs/ 双向同步（去重合并）
2. sync_answer_cards - 从对话历史 + question_progress 重建缺失的 answer card
3. report           - 显示当前数据状态统计

用法：
    python scripts/sync_data.py                  # 执行全部同步
    python scripts/sync_data.py --logs           # 仅同步 debug logs
    python scripts/sync_data.py --cards          # 仅同步 answer cards
    python scripts/sync_data.py --report         # 仅显示统计报告
    python scripts/sync_data.py --dry-run        # 仅预览，不写入
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# 项目路径
BACKEND_ROOT = Path(__file__).resolve().parent.parent  # src/backend/
DATA_DIR = BACKEND_ROOT / "data"
CONVERSATIONS_DIR = DATA_DIR / "conversations"
DEBUG_LOGS_DIR = DATA_DIR / "debug_logs"
QUESTION_PROGRESS_DIR = DATA_DIR / "question_progress"
LOGS_DIR = BACKEND_ROOT / "logs"


# ========== 工具函数 ==========

def load_jsonl(path: Path) -> List[Dict]:
    """读取 JSONL 文件"""
    entries = []
    if not path.is_file():
        return entries
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def save_jsonl(path: Path, entries: List[Dict]):
    """写入 JSONL 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_json(path: Path) -> Optional[Dict]:
    """读取 JSON 文件"""
    if not path.is_file():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, Exception):
        return None


def save_json(path: Path, data: Dict):
    """写入 JSON 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ========== 1. Debug Log 同步 ==========

def sync_debug_logs(dry_run: bool = False) -> Dict:
    """
    双向同步 debug logs:
    - data/debug_logs/{session_id}.jsonl  (旧路径, chat.py 写入)
    - logs/{user_id}/{session_id}/runs.jsonl  (新路径, chat_optimized.py 写入)

    合并策略：按 timestamp 去重，两边都写入合并后的完整记录
    """
    stats = {"sessions_synced": 0, "entries_merged": 0, "new_entries_old_path": 0, "new_entries_new_path": 0}

    # 收集所有 session_id → {path_type: path}
    session_paths: Dict[str, Dict[str, Path]] = {}

    # 扫描旧路径: data/debug_logs/{session_id}.jsonl
    if DEBUG_LOGS_DIR.is_dir():
        for f in DEBUG_LOGS_DIR.iterdir():
            if f.suffix == ".jsonl":
                sid = f.stem
                session_paths.setdefault(sid, {})["old"] = f

    # 扫描新路径: logs/{user_id}/{session_id}/runs.jsonl
    if LOGS_DIR.is_dir():
        for user_dir in LOGS_DIR.iterdir():
            if not user_dir.is_dir():
                continue
            for session_dir in user_dir.iterdir():
                if not session_dir.is_dir():
                    continue
                runs_file = session_dir / "runs.jsonl"
                if runs_file.is_file():
                    sid = session_dir.name
                    session_paths.setdefault(sid, {})["new"] = runs_file
                    # 记录 user_id 供新建旧路径时使用
                    session_paths[sid]["user_id"] = user_dir.name

    for sid, paths in session_paths.items():
        old_entries = load_jsonl(paths["old"]) if "old" in paths else []
        new_entries = load_jsonl(paths["new"]) if "new" in paths else []

        # 按 timestamp 去重合并
        seen = set()
        merged = []
        for entry in old_entries + new_entries:
            ts = entry.get("timestamp", "")
            if ts and ts in seen:
                continue
            if ts:
                seen.add(ts)
            merged.append(entry)

        # 排序
        merged.sort(key=lambda x: x.get("timestamp", ""))

        old_count = len(old_entries)
        new_count = len(new_entries)
        merged_count = len(merged)

        if merged_count == old_count and merged_count == new_count:
            # 两边内容相同，无需同步
            continue

        stats["sessions_synced"] += 1
        stats["entries_merged"] += merged_count

        # 写入旧路径
        if merged_count > old_count:
            stats["new_entries_old_path"] += merged_count - old_count
            if not dry_run:
                old_path = DEBUG_LOGS_DIR / f"{sid}.jsonl"
                save_jsonl(old_path, merged)

        # 写入新路径
        if merged_count > new_count:
            stats["new_entries_new_path"] += merged_count - new_count
            if not dry_run and "new" in paths:
                save_jsonl(paths["new"], merged)
            elif not dry_run and "user_id" in paths:
                # 新路径不存在，从旧记录中获取 user_id 创建
                user_id = paths.get("user_id") or _extract_user_id(merged)
                if user_id:
                    new_path = LOGS_DIR / user_id / sid / "runs.jsonl"
                    save_jsonl(new_path, merged)

    return stats


def _extract_user_id(entries: List[Dict]) -> Optional[str]:
    """从日志条目中提取 user_id"""
    for entry in entries:
        uid = entry.get("user_id")
        if uid:
            return str(uid)
    return None


# ========== 2. Answer Card 重建 ==========

def _extract_ai_summaries_from_history(messages: List[Dict]) -> List[Dict]:
    """
    从对话历史中提取 AI 总结的 "核心发现" 块

    AI 总结的格式通常是：
    - "很好！我理解你的想法了。让我为你总结一下...\n\n**核心发现：**..."
    - "好的，我来帮你梳理一下这道题的想法。\n\n**核心发现：**..."
    """
    summaries = []
    for i, msg in enumerate(messages):
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if "**核心发现：**" in content or "**核心发现:**" in content:
            # 提取核心发现内容
            match = re.search(r'\*\*核心发现[：:]\*\*(.*)', content, re.DOTALL)
            if match:
                summary_text = match.group(1).strip()
                # 往前找最近的题目内容（assistant 消息中包含 **题目**: 的那条）
                question_content = _find_preceding_question(messages, i)
                # 往前找用户的回答
                user_answers = _collect_user_answers(messages, i)
                summaries.append({
                    "ai_summary": summary_text,
                    "question_content": question_content,
                    "user_answers": user_answers,
                    "message_index": i,
                })
    return summaries


def _find_preceding_question(messages: List[Dict], current_idx: int) -> str:
    """向前查找最近的题目内容"""
    for i in range(current_idx - 1, -1, -1):
        msg = messages[i]
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        # 匹配 **题目**: xxx 或 ### N. xxx
        if "**题目**:" in content or "**题目**：" in content:
            match = re.search(r'\*\*题目\*\*[：:]\s*(.*?)(?:\n|$)', content)
            if match:
                return match.group(1).strip()
        # 匹配 ### N. 格式的题目
        match = re.search(r'(###\s*\d+\.\s*.+?)(?:\n|$)', content)
        if match:
            return match.group(1).strip()
    return ""


def _collect_user_answers(messages: List[Dict], summary_idx: int) -> str:
    """收集从上一个题目到总结之间的所有用户回答"""
    answers = []
    # 从总结往前找到上一个题目或上一个总结
    start_idx = 0
    for i in range(summary_idx - 1, -1, -1):
        msg = messages[i]
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if "**核心发现" in content or "**题目**" in content or "### " in content:
                start_idx = i + 1
                break

    for i in range(start_idx, summary_idx):
        msg = messages[i]
        if msg.get("role") == "user":
            content = msg.get("content", "").strip()
            if content:
                answers.append(content)
    return "\n".join(answers)


def sync_answer_cards(dry_run: bool = False) -> Dict:
    """
    从对话历史 + question_progress 重建缺失的 answer card

    逻辑：
    1. 扫描所有 session 的 question_progress
    2. 对于已完成(completed)的题目，检查是否已有 answer_card
    3. 如果缺失，从对话历史中提取 AI 总结内容，生成 answer_card
    """
    stats = {"sessions_scanned": 0, "cards_created": 0, "cards_existing": 0, "sessions_with_new_cards": 0}

    if not QUESTION_PROGRESS_DIR.is_dir():
        print("  [跳过] question_progress 目录不存在")
        return stats

    for qp_file in QUESTION_PROGRESS_DIR.iterdir():
        if qp_file.suffix != ".json":
            continue

        session_id = qp_file.stem
        stats["sessions_scanned"] += 1

        qp_data = load_json(qp_file)
        if not qp_data:
            continue

        # 检查现有 answer cards
        note_path = CONVERSATIONS_DIR / session_id / "note"
        existing_note = load_json(note_path)
        existing_card_qids = set()
        if existing_note:
            for note_entry in existing_note.get("notes", []):
                if note_entry.get("type") == "answer_card":
                    meta = note_entry.get("metadata", {})
                    qid = meta.get("question_id")
                    if qid is not None:
                        existing_card_qids.add(qid)

        stats["cards_existing"] += len(existing_card_qids)

        # 加载对话历史
        main_flow_json = CONVERSATIONS_DIR / session_id / "main_flow.json"
        main_flow_plain = CONVERSATIONS_DIR / session_id / "main_flow"
        history = None

        for path in [main_flow_json, main_flow_plain]:
            data = load_json(path)
            if data and data.get("messages"):
                history = data
                break

        if not history:
            continue

        messages = history.get("messages", [])
        ai_summaries = _extract_ai_summaries_from_history(messages)

        # 遍历所有步骤的已完成题目
        new_cards = []
        summary_idx = 0  # 按顺序匹配 AI 总结

        for step_id, step_data in qp_data.items():
            questions = step_data.get("questions", [])
            for q in questions:
                qid = q.get("question_id")
                status = q.get("status")
                q_content = q.get("question_content", "")

                if status != "completed":
                    continue
                if qid in existing_card_qids:
                    continue

                # 尝试匹配 AI 总结
                ai_summary = ""
                user_answer = ""
                if summary_idx < len(ai_summaries):
                    s = ai_summaries[summary_idx]
                    ai_summary = s["ai_summary"]
                    user_answer = s["user_answers"]
                    summary_idx += 1

                if not ai_summary and not user_answer:
                    # 没有数据可重建，跳过
                    continue

                card = {
                    "question_id": qid,
                    "question_content": q_content,
                    "user_answer": user_answer or "(自动重建 - 原始回答未记录)",
                    "ai_summary": ai_summary,
                    "ai_analysis": None,
                    "key_insights": None,
                    "current_step": step_id,
                }
                new_cards.append(card)

        if not new_cards:
            continue

        stats["sessions_with_new_cards"] += 1
        stats["cards_created"] += len(new_cards)

        if dry_run:
            for card in new_cards:
                print(f"    [预览] session={session_id} q{card['question_id']}: {card['question_content'][:40]}...")
            continue

        # 写入 note 文件
        if not existing_note:
            existing_note = {
                "session_id": session_id,
                "created_at": datetime.now(timezone.utc).isoformat() + "Z",
                "updated_at": datetime.now(timezone.utc).isoformat() + "Z",
                "notes": [],
            }

        for card in new_cards:
            note_entry = {
                "id": f"answer_card_{card['question_id']}",
                "type": "answer_card",
                "content": json.dumps(card, ensure_ascii=False),
                "created_at": datetime.now(timezone.utc).isoformat() + "Z",
                "metadata": {
                    "question_id": card["question_id"],
                    "current_step": card["current_step"],
                    "source": "sync_script",
                },
            }
            existing_note["notes"].append(note_entry)

        existing_note["updated_at"] = datetime.now(timezone.utc).isoformat() + "Z"
        save_json(note_path, existing_note)

    return stats


# ========== 3. 报告 ==========

def generate_report() -> str:
    """生成当前数据状态统计报告"""
    lines = []
    lines.append("=" * 60)
    lines.append("  BeingDoing 数据状态报告")
    lines.append("=" * 60)

    # 对话会话统计
    session_ids = set()
    if CONVERSATIONS_DIR.is_dir():
        for d in CONVERSATIONS_DIR.iterdir():
            if d.is_dir():
                session_ids.add(d.name)
    lines.append(f"\n会话总数: {len(session_ids)}")

    # 对话历史文件
    main_flow_count = 0
    all_flow_count = 0
    note_count = 0
    for sid in session_ids:
        sdir = CONVERSATIONS_DIR / sid
        if (sdir / "main_flow.json").is_file() or (sdir / "main_flow").is_file():
            main_flow_count += 1
        if (sdir / "all_flow").is_file():
            all_flow_count += 1
        if (sdir / "note").is_file():
            note_count += 1
    lines.append(f"  有 main_flow 记录: {main_flow_count}")
    lines.append(f"  有 all_flow 记录: {all_flow_count}")
    lines.append(f"  有 note (answer card) 记录: {note_count}")

    # Question Progress 统计
    qp_count = 0
    total_completed = 0
    total_questions = 0
    if QUESTION_PROGRESS_DIR.is_dir():
        for f in QUESTION_PROGRESS_DIR.iterdir():
            if f.suffix == ".json":
                qp_count += 1
                data = load_json(f)
                if data:
                    for step_data in data.values():
                        if isinstance(step_data, dict):
                            questions = step_data.get("questions", [])
                            total_questions += len(questions)
                            total_completed += sum(1 for q in questions if q.get("status") == "completed")
    lines.append(f"\nQuestion Progress 文件数: {qp_count}")
    lines.append(f"  总题目数: {total_questions}")
    lines.append(f"  已完成题目数: {total_completed}")

    # Debug Log 统计
    old_log_count = 0
    old_entries = 0
    if DEBUG_LOGS_DIR.is_dir():
        for f in DEBUG_LOGS_DIR.iterdir():
            if f.suffix == ".jsonl":
                old_log_count += 1
                old_entries += len(load_jsonl(f))
    lines.append(f"\nDebug Logs (data/debug_logs/): {old_log_count} 文件, {old_entries} 条记录")

    new_log_count = 0
    new_entries = 0
    if LOGS_DIR.is_dir():
        for user_dir in LOGS_DIR.iterdir():
            if not user_dir.is_dir():
                continue
            for session_dir in user_dir.iterdir():
                runs = session_dir / "runs.jsonl"
                if runs.is_file():
                    new_log_count += 1
                    new_entries += len(load_jsonl(runs))
    lines.append(f"Debug Logs (logs/*/): {new_log_count} 文件, {new_entries} 条记录")

    # Token 使用统计
    total_tokens = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "llm_calls": 0}
    all_entries = []
    if DEBUG_LOGS_DIR.is_dir():
        for f in DEBUG_LOGS_DIR.iterdir():
            if f.suffix == ".jsonl":
                all_entries.extend(load_jsonl(f))
    if LOGS_DIR.is_dir():
        for user_dir in LOGS_DIR.iterdir():
            if not user_dir.is_dir():
                continue
            for session_dir in user_dir.iterdir():
                runs = session_dir / "runs.jsonl"
                if runs.is_file():
                    all_entries.extend(load_jsonl(runs))

    # 去重
    seen_ts = set()
    unique_entries = []
    for e in all_entries:
        ts = e.get("timestamp", "")
        if ts and ts in seen_ts:
            continue
        if ts:
            seen_ts.add(ts)
        unique_entries.append(e)

    for entry in unique_entries:
        usage = entry.get("token_usage")
        if usage and isinstance(usage, dict):
            total_tokens["prompt_tokens"] += usage.get("prompt_tokens", 0)
            total_tokens["completion_tokens"] += usage.get("completion_tokens", 0)
            total_tokens["total_tokens"] += usage.get("total_tokens", 0)
            total_tokens["llm_calls"] += usage.get("llm_calls", 0)

    lines.append(f"\nToken 使用统计 (从日志聚合):")
    lines.append(f"  输入 tokens: {total_tokens['prompt_tokens']:,}")
    lines.append(f"  输出 tokens: {total_tokens['completion_tokens']:,}")
    lines.append(f"  总 tokens: {total_tokens['total_tokens']:,}")
    lines.append(f"  LLM 调用次数: {total_tokens['llm_calls']}")

    # Answer Card 详情
    lines.append(f"\nAnswer Card 详情:")
    for sid in sorted(session_ids):
        note_path = CONVERSATIONS_DIR / sid / "note"
        note_data = load_json(note_path)
        if note_data:
            cards = [n for n in note_data.get("notes", []) if n.get("type") == "answer_card"]
            if cards:
                lines.append(f"  {sid[:12]}... : {len(cards)} 张答题卡")
                for card_note in cards:
                    meta = card_note.get("metadata", {})
                    qid = meta.get("question_id", "?")
                    step = meta.get("current_step", "?")
                    source = meta.get("source", "agent")
                    lines.append(f"    Q{qid} [{step}] (来源: {source})")

    lines.append("\n" + "=" * 60)
    return "\n".join(lines)


# ========== 主入口 ==========

def main():
    parser = argparse.ArgumentParser(description="BeingDoing 数据同步工具")
    parser.add_argument("--logs", action="store_true", help="仅同步 debug logs")
    parser.add_argument("--cards", action="store_true", help="仅同步 answer cards")
    parser.add_argument("--report", action="store_true", help="仅显示统计报告")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入文件")
    args = parser.parse_args()

    # 切换到 backend 根目录（和服务器运行时一致）
    os.chdir(BACKEND_ROOT)
    print(f"工作目录: {os.getcwd()}")

    # 如果没有指定选项，执行全部
    run_all = not (args.logs or args.cards or args.report)

    if args.report:
        print(generate_report())
        return

    if run_all or args.logs:
        print("\n[1/2] 同步 Debug Logs...")
        log_stats = sync_debug_logs(dry_run=args.dry_run)
        prefix = "[预览] " if args.dry_run else ""
        print(f"  {prefix}同步会话数: {log_stats['sessions_synced']}")
        print(f"  {prefix}合并记录总数: {log_stats['entries_merged']}")
        print(f"  {prefix}写入旧路径新记录: {log_stats['new_entries_old_path']}")
        print(f"  {prefix}写入新路径新记录: {log_stats['new_entries_new_path']}")

    if run_all or args.cards:
        print("\n[2/2] 同步 Answer Cards...")
        card_stats = sync_answer_cards(dry_run=args.dry_run)
        prefix = "[预览] " if args.dry_run else ""
        print(f"  {prefix}扫描会话数: {card_stats['sessions_scanned']}")
        print(f"  {prefix}已存在答题卡: {card_stats['cards_existing']}")
        print(f"  {prefix}新建答题卡: {card_stats['cards_created']}")
        print(f"  {prefix}涉及会话数: {card_stats['sessions_with_new_cards']}")

    if not args.dry_run:
        print("\n同步完成！运行 --report 查看数据状态。")
    else:
        print("\n[预览模式] 未写入任何文件。去掉 --dry-run 执行实际同步。")

    # 同步完成后显示报告
    if run_all and not args.dry_run:
        print(generate_report())


if __name__ == "__main__":
    main()
