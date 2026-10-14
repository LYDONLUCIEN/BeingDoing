#!/usr/bin/env python3
"""生产副本工具启动入口；源端导出只依赖 Python 标准库。"""

import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(root), str(root / "src/backend")]

from test_agent.snapshot.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
