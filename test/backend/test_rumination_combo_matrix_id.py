"""回归测试：combo matrix -> step3b 表行的 id 必须与 gen_table 体系同源。

背景：1EPJC91L88 报告出现 id=20/23 的脏数据。
根因：simple_chat_routes 把 combo_id（"pi"+"si" 双位编码）直接当成表行 id 写入 snapshot[3]。
本测试锁定修复：combo_id_to_row_id 将 combo_id 反推为 1 + pi*5 + si（gen_table 行号）。
"""
from __future__ import annotations

from app.utils.rumination_combo_matrix import (
    build_combo_matrix,
    combo_id_to_row_id,
)
from app.utils.rumination_ops import gen_table


def test_combo_id_to_row_id_matches_gen_table_3x5():
    """3 热爱 × 5 优势：combo matrix 每个 item 的反推 id 必须等于 gen_table 对应行 id。"""
    passions = ["感官创作", "自我探索", "万物融通"]
    strengths = ["审美判断", "建立关联", "自驱探索", "根源性思考", "信息搜索"]

    matrix = build_combo_matrix(passions, strengths)
    table = gen_table(strengths, passions)

    # gen_table 行 id 与 (热爱, 优势) 的映射
    gen_id_by_pair = {(r["热爱"], r["优势"]): r["id"] for r in table}

    assert len(matrix) == 15, "matrix 应为 15 行"
    for item in matrix:
        row_id = combo_id_to_row_id(item)
        pair = (item["passion_name"], item["strength_name"])
        assert row_id == gen_id_by_pair[pair], (
            f"combo {item['combo_id']} ({pair}) 行 id={row_id} "
            f"与 gen_table id={gen_id_by_pair[pair]} 不一致"
        )


def test_combo_id_to_row_id_specific_regression_case():
    """锁定 1EPJC91L88 报告的两个具体组合：原 combo_id 20/23 必须翻译为 11/14。"""
    passions = ["感官创作", "自我探索", "万物融通"]
    strengths = ["审美判断", "建立关联", "自驱探索", "根源性思考", "信息搜索"]
    matrix = build_combo_matrix(passions, strengths)

    m20 = next(x for x in matrix if x["combo_id"] == "20")  # 万物融通 × 审美判断
    m23 = next(x for x in matrix if x["combo_id"] == "23")  # 万物融通 × 根源性思考

    assert combo_id_to_row_id(m20) == "11"
    assert combo_id_to_row_id(m23) == "14"

    # 同时确认 1EPJC91L88 snapshot[3].initial 残留的错误 id 不再出现
    all_ids = {combo_id_to_row_id(it) for it in matrix}
    assert all_ids == {str(i) for i in range(1, 16)}, "id 必须落在 1..15"
    assert "20" not in all_ids and "23" not in all_ids


def test_combo_id_to_row_id_resilient_to_missing_indices():
    """缺 passion_idx/strength_idx 时按 combo_id 字符串回退解析；再不行则原样返回。"""
    # 仅 combo_id，无 idx
    assert combo_id_to_row_id({"combo_id": "20"}) == "11"
    # combo_id 长度不足，回退原值（绝不抛异常）
    assert combo_id_to_row_id({"combo_id": "x"}) == "x"
    assert combo_id_to_row_id({}) == ""
