"""开发交付检查：验证固定定义，并把没有用例关联的业务改动列为缺口。"""

import json
import tempfile
from pathlib import Path

from app.services.test_center import TestCenter


def main():
    with tempfile.TemporaryDirectory(prefix="test-center-catalog-") as directory:
        catalog = TestCenter(Path(__file__).resolve().parents[2], Path(directory)).catalog()
        print(
            json.dumps(
                {key: catalog[key] for key in ("build", "coverage_gaps", "unknown_cases")},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1 if catalog["coverage_gaps"] or catalog["unknown_cases"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
