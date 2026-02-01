"""
数据库初始化脚本（命令行工具）
"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database.init_db import init_db, drop_db


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "drop":
        print("警告：将删除所有数据库表！")
        confirm = input("确认删除？(yes/no): ")
        if confirm.lower() == "yes":
            asyncio.run(drop_db())
        else:
            print("已取消")
    else:
        asyncio.run(init_db())
