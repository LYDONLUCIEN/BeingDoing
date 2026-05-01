"""md_checklist_parser 自测"""
import os
import tempfile

from parser.md_checklist_parser import parse_checklist


def _write_temp_md(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".md", text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def test_parse_basic_checklist():
    md = """# 测试清单

## 一、基础功能

### 1.1 登录
- [x] 登录后跳转正确 **(O-02)**
- [ ] 清缓存后登录正常 **(S-04)**

### 1.2 表格
- [ ] 优势标记列只读 **(S-02)**
- [ ] 匹配原因列已移除 **(P-06, U-04)**

## 二、视觉检查

### 2.1 样式
- [ ] 表头不透明 **(U-01)**
- [ ] hover 效果精致 **(U-05)**
"""
    path = _write_temp_md(md)
    try:
        title, items, priorities = parse_checklist(path)
        assert title == "测试清单"
        assert len(items) == 6

        # checked 项
        assert items[0].status == "passed"
        assert items[0].task_ids == ["O-02"]
        assert items[0].item_type == "automated"

        # unchecked
        assert items[1].status == "pending"
        assert items[1].task_ids == ["S-04"]
        assert items[1].section == "1.1 登录"

        # 多 task ID
        assert items[3].task_ids == ["P-06", "U-04"]

        # human_reviewed（U-01 视觉 / U-05 视觉）
        assert items[4].item_type == "human_reviewed"  # U-01
        assert items[5].item_type == "human_reviewed"  # U-05
    finally:
        os.unlink(path)


def test_parse_with_priority_table():
    md = """# 测试清单

## 一、功能

### 1.1 登录
- [ ] 登录正常 **(O-02)**

| 优先级 | 测试范围 |
|--------|---------|
| **P0** | 一、功能 |
| **P1** | 二、视觉 |
"""
    path = _write_temp_md(md)
    try:
        title, items, priorities = parse_checklist(path)
        assert len(items) == 1
        assert items[0].priority == "P0"
    finally:
        os.unlink(path)


def test_parse_real_checklist():
    """用实际 4.28 开发待测清单做冒烟测试"""
    real_path = os.path.join(
        os.path.dirname(__file__), "..", "..", "..", "4.28开发待测清单.md"
    )
    real_path = os.path.normpath(real_path)
    if not os.path.isfile(real_path):
        return  # CI 环境可能没有这个文件
    title, items, priorities = parse_checklist(real_path)
    assert "4.28" in title
    assert len(items) > 40  # 清单项应该足够多

    # 确认有不同类型
    types = {it.item_type for it in items}
    assert "automated" in types
    assert "human_reviewed" in types

    # 确认有关联测试文件的项
    with_test = [it for it in items if it.test_file]
    assert len(with_test) > 10
