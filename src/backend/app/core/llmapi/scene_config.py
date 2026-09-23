"""
LLM 场景分流配置（2026-09-23 拍板：admin 可配置 chat/rumination/report 三场景的
flash|pro 档位与 thinking 开关，全局生效）。

- 档位固定映射：flash→deepseek-v4-flash，pro→deepseek-v4-pro，不受 .env 覆盖影响
- 默认值：chat→flash、rumination/report→pro，thinking 全开（= 代码设计意图；
  注意默认生效后前四轮 chat 将真正切到 v4-flash）
- 存储：data/admin_runtime_config.json 的 `llm_scene_config` 键（app.utils.admin_config），
  部分保存的字段逐场景与默认合并
- 未覆盖场景（team_analysis/unknown）仍走 settings（.env）兜底，与 2026-08-19 分流行为一致
"""

from typing import Any, Dict, Optional, Tuple

from app.utils.admin_config import get_admin_config

CONFIG_KEY = "llm_scene_config"

# 可配置场景（usage_context.scene 的取值；team_analysis 等不在此列，保持 .env 兜底）
SCENES: Tuple[str, ...] = ("chat", "rumination", "report")

TIERS: Tuple[str, ...] = ("flash", "pro")

# 档位 → 具体模型名（固定映射；换模型须改这里并同步前端 llm-scene 页展示）
TIER_MODELS: Dict[str, str] = {
    "flash": "deepseek-v4-flash",
    "pro": "deepseek-v4-pro",
}

# 默认配置（reset 端点与未配置时的兜底值）
DEFAULT_LLM_SCENE_CONFIG: Dict[str, Dict[str, Any]] = {
    "chat": {"tier": "flash", "thinking": True},
    "rumination": {"tier": "pro", "thinking": True},
    "report": {"tier": "pro", "thinking": True},
}


def get_llm_scene_config() -> Dict[str, Dict[str, Any]]:
    """读取场景配置，逐场景与默认合并（存的部分字段覆盖默认），异常返回纯默认。"""
    try:
        saved = get_admin_config(CONFIG_KEY)
        saved = saved if isinstance(saved, dict) else {}
    except Exception:
        saved = {}
    merged: Dict[str, Dict[str, Any]] = {}
    for scene in SCENES:
        default = DEFAULT_LLM_SCENE_CONFIG[scene]
        item = saved.get(scene)
        item = item if isinstance(item, dict) else {}
        merged[scene] = {
            "tier": item.get("tier") if item.get("tier") in TIERS else default["tier"],
            "thinking": item["thinking"] if isinstance(item.get("thinking"), bool) else default["thinking"],
        }
    return merged


def get_scene_tier_model(scene: Optional[str]) -> Optional[str]:
    """场景在配置范围内 → 返回档位映射的模型名；否则 None（调用方走 .env 兜底）。"""
    scene = (scene or "").strip()
    if scene not in SCENES:
        return None
    return TIER_MODELS.get(get_llm_scene_config()[scene]["tier"])


def is_scene_thinking_enabled(scene: Optional[str]) -> bool:
    """场景在配置范围内 → 返回其 thinking 开关；否则兜底全局 settings.LLM_THINKING_ENABLED。"""
    scene = (scene or "").strip()
    if scene in SCENES:
        return bool(get_llm_scene_config()[scene]["thinking"])
    from app.config.settings import settings

    return bool(settings.LLM_THINKING_ENABLED)


def validate_scene_config(cfg: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """校验并归一化 admin 提交的配置：场景键限 SCENES、可缺省；tier/thinking 类型校验。
    非法值抛 ValueError（路由层转 400），未知字段拒绝。"""
    if not isinstance(cfg, dict):
        raise ValueError("config 须为对象")
    unknown = set(cfg.keys()) - set(SCENES)
    if unknown:
        raise ValueError(f"未知场景：{sorted(unknown)}，可选 {list(SCENES)}")
    cleaned: Dict[str, Dict[str, Any]] = {}
    for scene, item in cfg.items():
        if not isinstance(item, dict):
            raise ValueError(f"{scene} 须为对象")
        unknown_fields = set(item.keys()) - {"tier", "thinking"}
        if unknown_fields:
            raise ValueError(f"{scene} 含未知字段：{sorted(unknown_fields)}")
        if "tier" in item and item["tier"] not in TIERS:
            raise ValueError(f"{scene}.tier 非法：{item['tier']}，可选 {list(TIERS)}")
        if "thinking" in item and not isinstance(item["thinking"], bool):
            raise ValueError(f"{scene}.thinking 须为布尔值")
        # 未提交的场景/字段由读取侧与默认合并，这里只存显式提交且合法的部分
        cleaned[scene] = {
            k: v for k, v in item.items() if k in ("tier", "thinking")
        }
    return cleaned
