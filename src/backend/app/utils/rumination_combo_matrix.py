"""
组合矩阵工具：构建 3×5 热爱×优势组合，提供 combo_id 查找。

遍历顺序：热爱优先（00, 01, ..., 04, 10, 11, ..., 24）。
combo_id 格式：passion_idx + strength_idx（两位字符串，如 "02"）。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


def build_combo_matrix(
    passions: List[str],
    strengths: List[str],
    non_matching_pairs: Optional[set] = None,
) -> List[Dict[str, Any]]:
    """构建组合矩阵列表，热爱优先遍历。

    non_matching_pairs: {(passion_name, strength_name), ...} 不匹配的组合集合。
        这些组合在矩阵中标记 is_non_matching=True，供前端置灰展示。
    """
    if not passions:
        passions = ["热爱1", "热爱2"]
    if not strengths:
        strengths = ["优势1", "优势2"]
    nm = non_matching_pairs or set()
    matrix: List[Dict[str, Any]] = []
    for pi, p in enumerate(passions[:3]):
        for si, s in enumerate(strengths[:5]):
            p_s = p.strip()
            s_s = s.strip()
            matrix.append({
                "combo_id": f"{pi}{si}",
                "passion_idx": pi,
                "strength_idx": si,
                "passion_name": p_s,
                "strength_name": s_s,
                "is_non_matching": (p_s, s_s) in nm,
            })
    return matrix


def get_combo_by_id(
    matrix: List[Dict[str, Any]], combo_id: str
) -> Optional[Dict[str, Any]]:
    """按 combo_id 查找组合条目。"""
    for item in matrix:
        if item.get("combo_id") == combo_id:
            return item
    return None


def get_passion_strength_names(
    matrix: List[Dict[str, Any]], combo_id: str
) -> Tuple[str, str]:
    """获取指定组合的热爱名称和优势名称。"""
    item = get_combo_by_id(matrix, combo_id)
    if not item:
        return "", ""
    return str(item.get("passion_name") or ""), str(item.get("strength_name") or "")


def build_combo_id_to_name_map(
    matrix: List[Dict[str, Any]],
) -> Dict[str, Dict[str, str]]:
    """构建 combo_id → {passion, strength} 映射。"""
    return {
        item["combo_id"]: {
            "passion": str(item.get("passion_name") or ""),
            "strength": str(item.get("strength_name") or ""),
        }
        for item in matrix
    }


def get_next_combo_by_order(
    matrix: List[Dict[str, Any]],
    completed_combo_ids: set,
) -> Optional[Dict[str, Any]]:
    """按遍历顺序获取下一个未完成的组合。"""
    for item in matrix:
        if item["combo_id"] not in completed_combo_ids:
            return item
    return None


def count_completed_combos(
    combo_conclusions: Dict[str, Any],
    matrix: Optional[List[Dict[str, Any]]] = None,
) -> int:
    """统计已确认+已跳过的组合数量（不含不匹配组合）。"""
    # 不匹配组合集合
    nm_ids: set = set()
    if matrix:
        for item in matrix:
            if item.get("is_non_matching"):
                nm_ids.add(item["combo_id"])
    count = 0
    for v in (combo_conclusions or {}).values():
        if isinstance(v, dict) and v.get("state") in ("confirmed", "skipped"):
            count += 1
    return count


def build_combo_matrix_meta(matrix: List[Dict[str, Any]]) -> Dict[str, Any]:
    """从已构建好的 combo_matrix 派生聚合元数据。

    纯派生函数：不读 progress，不写文件。输入 matrix（含 is_non_matching），
    输出按热爱/优势分行的静态统计信息，供前端直接渲染（置灰、默认优势、初始 combo）。

    这些结论在 step2 跑完时定死，跟用户后续的 confirmed/skipped 操作无关；
    动态派生（passionDone / strengthDone）仍由前端 useMemo 计算。
    """
    # 收集热爱与优势的 idx 顺序（按 matrix 中首次出现顺序）
    passions_order: List[int] = []
    strengths_order: List[int] = []
    passion_name_by_idx: Dict[int, str] = {}
    strength_name_by_idx: Dict[int, str] = {}
    for item in matrix:
        pi = item.get("passion_idx")
        si = item.get("strength_idx")
        if isinstance(pi, int) and pi not in passion_name_by_idx:
            passion_name_by_idx[pi] = str(item.get("passion_name") or "")
            passions_order.append(pi)
        if isinstance(si, int) and si not in strength_name_by_idx:
            strength_name_by_idx[si] = str(item.get("strength_name") or "")
            strengths_order.append(si)

    passions_order.sort()
    strengths_order.sort()

    # 统计每个热爱/优势下的 matchable 数，以及每热爱的第一个 matchable strength_idx
    passion_matchable: Dict[int, int] = {pi: 0 for pi in passions_order}
    strength_matchable: Dict[int, int] = {si: 0 for si in strengths_order}
    passion_default_strength: Dict[int, int] = {}
    total_matchable = 0
    default_combo_id: Optional[str] = None

    # 按 passion_idx 升序、strength_idx 升序遍历，保证"第一个 matchable"的语义稳定
    sorted_matrix = sorted(
        matrix,
        key=lambda x: (x.get("passion_idx", 0), x.get("strength_idx", 0)),
    )
    for item in sorted_matrix:
        if item.get("is_non_matching"):
            continue
        pi = item.get("passion_idx")
        si = item.get("strength_idx")
        if not isinstance(pi, int) or not isinstance(si, int):
            continue
        passion_matchable[pi] = passion_matchable.get(pi, 0) + 1
        strength_matchable[si] = strength_matchable.get(si, 0) + 1
        total_matchable += 1
        # 该热爱的第一个 matchable strength_idx
        if pi not in passion_default_strength:
            passion_default_strength[pi] = si
        # 整个矩阵的第一个 matchable combo
        if default_combo_id is None:
            default_combo_id = item.get("combo_id")

    passions_meta = []
    for pi in passions_order:
        cnt = passion_matchable.get(pi, 0)
        passions_meta.append({
            "idx": pi,
            "name": passion_name_by_idx.get(pi, ""),
            "matchable_count": cnt,
            "all_disabled": cnt == 0,
            "default_strength_idx": passion_default_strength.get(pi),
        })

    strengths_meta = []
    for si in strengths_order:
        strengths_meta.append({
            "idx": si,
            "name": strength_name_by_idx.get(si, ""),
            "matchable_count": strength_matchable.get(si, 0),
        })

    return {
        "total_matchable": total_matchable,
        "default_combo_id": default_combo_id,
        "passions": passions_meta,
        "strengths": strengths_meta,
    }


def classify_combo_conclusions(
    combo_conclusions: Dict[str, Any],
    matrix: List[Dict[str, Any]],
) -> Dict[str, List[str]]:
    """将组合分为 empty / text_skipped / confirmed / empty_skipped / non_matching 五类。"""
    result: Dict[str, List[str]] = {
        "empty": [],           # 纯空：从未填写
        "text_skipped": [],    # 有字跳过：用户写了内容但放弃了
        "confirmed": [],       # 已确认
        "empty_skipped": [],   # 空内容跳过
        "non_matching": [],    # 不匹配（step2 标记）
    }
    all_ids = {item["combo_id"]: item for item in matrix}
    for cid, item in all_ids.items():
        if item.get("is_non_matching"):
            result["non_matching"].append(cid)
            continue
        entry = (combo_conclusions or {}).get(cid) or {}
        state = str(entry.get("state") or "empty")
        text = str(entry.get("text") or "").strip()
        if state == "confirmed":
            result["confirmed"].append(cid)
        elif state == "skipped":
            if text:
                result["text_skipped"].append(cid)
            else:
                result["empty_skipped"].append(cid)
        else:
            result["empty"].append(cid)
    return result
