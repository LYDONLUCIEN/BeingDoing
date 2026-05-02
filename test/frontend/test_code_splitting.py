"""代码分割和 Server Component 转换测试"""

import re
from pathlib import Path

COMPONENTS_DIR = Path(__file__).resolve().parents[2] / "src" / "frontend" / "components" / "explore"

# 应该转为 Server Component 的组件（不包含 'use client'）
SERVER_COMPONENTS = [
    "CurrentQuestionBanner.tsx",
    "ConversationSection.tsx",
    "AnswerCardHistory.tsx",
    "ChatPhaseBackground.tsx",
]

# 应该用 dynamic import 懒加载的组件
DYNAMIC_IMPORT_SOURCES = [
    # (从 src/frontend/ 开始的相对路径, 被懒加载的组件名)
    ("app/(main)/explore/chat/[phase]/page.tsx", "RuminationTableWidget"),
    ("app/(main)/explore/chat/[phase]/page.tsx", "RuminationSectionProgress"),
    ("app/(main)/explore/chat/[phase]/page.tsx", "ChatPhaseSidebar"),
    ("app/(main)/explore/chat/[phase]/page.tsx", "PhaseCelebrateBurst"),
]

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "src" / "frontend"


class TestServerComponentConversion:
    """验证 Server Component 转换：去掉 'use client' 且不使用客户端特性"""

    def test_no_use_client_directive(self):
        """这些组件不应有 'use client' 指令"""
        for name in SERVER_COMPONENTS:
            path = COMPONENTS_DIR / name
            assert path.exists(), f"组件不存在: {name}"
            content = path.read_text(encoding="utf-8")
            has_use_client = bool(re.search(r'^\s*[\'"]use client[\'"]', content, re.MULTILINE))
            assert not has_use_client, f"{name} 仍有 'use client' 指令，应该已移除"

    def test_no_client_hooks(self):
        """Server Component 不应使用客户端 hooks"""
        client_hooks = [
            "useState", "useEffect", "useReducer", "useContext",
            "useRef", "useCallback", "useMemo", "useLayoutEffect",
            "useImperativeHandle",
        ]
        for name in SERVER_COMPONENTS:
            path = COMPONENTS_DIR / name
            content = path.read_text(encoding="utf-8")
            for hook in client_hooks:
                # 匹配实际的 hook 调用，忽略注释和字符串
                pattern = rf'\b{hook}\s*\('
                matches = re.findall(pattern, content)
                assert not matches, f"{name} 使用了客户端 hook '{hook}'，不能作为 Server Component"


class TestDynamicImports:
    """验证重量级组件使用 dynamic import 懒加载"""

    def test_dynamic_import_usage(self):
        """重量级组件应通过 next/dynamic 懒加载，而非静态 import"""
        for rel_path, component_name in DYNAMIC_IMPORT_SOURCES:
            importer_path = FRONTEND_DIR / rel_path
            if not importer_path.exists():
                continue
            content = importer_path.read_text(encoding="utf-8")

            # 不应有静态 import { Xxx } from './RuminationTableWidget'
            static_import = rf'import\s+\{{[^}}]*\b{component_name}\b'
            has_static = bool(re.search(static_import, content))
            assert not has_static, f"{rel_path} 对 {component_name} 使用了静态 import，应改为 dynamic import"

            # 应有 dynamic(() => import(...))
            has_dynamic = bool(re.search(rf'dynamic\s*\(', content)) and bool(re.search(rf"import\([^)]*{component_name}", content))
            assert has_dynamic, f"{rel_path} 未找到对 {component_name} 的 dynamic import"
