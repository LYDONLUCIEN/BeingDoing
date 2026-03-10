"""
迁移脚本：将 interests_goals 相关文件重命名为 interests

- data/simple/{session_id}/interests_goals.json -> interests.json
- data/simple/{session_id}/interests_goals__{thread_id}.json -> interests__{thread_id}.json

用法（在项目根目录执行）：
  cd src/backend && python scripts/migrate_interests_goals_to_interests.py
  cd src/backend && python scripts/migrate_interests_goals_to_interests.py --dry-run   # 仅预览，不实际重命名
"""
import argparse
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.simple_activation_manager import get_simple_base_dir


def migrate(dry_run: bool = False) -> int:
    base_dir = get_simple_base_dir()
    if not base_dir.exists():
        print(f"目录不存在: {base_dir}")
        return 1

    renamed = 0
    skipped = 0

    for session_dir in base_dir.iterdir():
        if not session_dir.is_dir():
            continue

        # 1. interests_goals.json -> interests.json
        old_path = session_dir / "interests_goals.json"
        new_path = session_dir / "interests.json"
        if old_path.exists():
            if new_path.exists():
                print(f"[跳过] {session_dir.name}/interests.json 已存在，不覆盖: {old_path}")
                skipped += 1
            else:
                if dry_run:
                    print(f"[预览] 将重命名: {old_path} -> {new_path}")
                else:
                    old_path.rename(new_path)
                    print(f"[完成] {session_dir.name}/interests_goals.json -> interests.json")
                renamed += 1

        # 2. interests_goals__*.json -> interests__*.json
        for old_file in session_dir.glob("interests_goals__*.json"):
            thread_suffix = old_file.name.replace("interests_goals__", "", 1)
            new_name = f"interests__{thread_suffix}"
            new_file = session_dir / new_name
            if new_file.exists():
                print(f"[跳过] {session_dir.name}/{new_name} 已存在，不覆盖: {old_file}")
                skipped += 1
            else:
                if dry_run:
                    print(f"[预览] 将重命名: {old_file} -> {new_file}")
                else:
                    old_file.rename(new_file)
                    print(f"[完成] {session_dir.name}/{old_file.name} -> {new_name}")
                renamed += 1

    print(f"\n总计: 重命名 {renamed} 个, 跳过 {skipped} 个")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将 interests_goals 文件迁移为 interests")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不实际重命名")
    args = parser.parse_args()

    sys.exit(migrate(dry_run=args.dry_run))
