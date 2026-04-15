"""
领域提示词加载器：从 templates 目录加载 YAML，Jinja2 渲染注入上下文。

加载流程（鲁棒设计）：
1. 先用 YAML.safe_load() 解析模板文件，获取原始的 prompt 模板（此时 Jinja2 变量还未被替换）
2. 再用 Jinja2 渲染 prompt 模板，插入动态内容

这样设计的好处：
- 提示词内容可以是任意格式，不受 YAML 语法限制
- 动态插入的内容（如 counselor_guidelines）可以包含 "1. xxx"、"- xxx" 等常见格式
- 用户写提示词时不需要考虑 YAML 转义问题
"""
import os
from typing import Any, Dict, Optional

import yaml
from jinja2 import Environment, FileSystemLoader


class DomainPromptLoader:
    def __init__(self, templates_dir: Optional[str] = None):
        if templates_dir is None:
            templates_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.templates_dir = templates_dir
        # 用于从字符串创建 Jinja2 模板（保持与原配置一致）
        self._jinja_env = Environment(
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, name: str, context: Optional[Dict[str, Any]] = None) -> str:
        context = context or {}
        template_path = os.path.join(self.templates_dir, f"{name}.yaml")

        # 1. 先用 YAML 解析模板文件（此时 Jinja2 变量还是原样）
        with open(template_path, 'r', encoding='utf-8') as f:
            yaml_content = f.read()
        data = yaml.safe_load(yaml_content)

        if not data or 'prompt' not in data:
            return ""

        # 2. 再用 Jinja2 渲染 prompt 字段（插入动态内容）
        prompt_template = data['prompt']
        template = self._jinja_env.from_string(prompt_template)
        return template.render(**context)


_loader: Optional[DomainPromptLoader] = None


def _get_loader() -> DomainPromptLoader:
    global _loader
    if _loader is None:
        _loader = DomainPromptLoader()
    return _loader


def get_reasoning_prompt(context: Dict[str, Any]) -> str:
    """推理节点系统提示。context: current_step, step_summary, user_input, tools_used"""
    return _get_loader().render("reasoning", context)


def get_observation_prompt(context: Dict[str, Any]) -> str:
    """观察节点系统提示。context: tool_output"""
    return _get_loader().render("observation", context)


def get_guide_prompt(context: Dict[str, Any]) -> str:
    """引导节点系统提示。context: current_step, user_input"""
    return _get_loader().render("guide", context)


def get_answer_card_prompt(context: Dict[str, Any]) -> str:
    """答题卡总结提示。context: question_content, category_label, question_goal, conversation_text"""
    return _get_loader().render("answer_card_summary", context)


def get_pending_conclusion_injection(context: Dict[str, Any]) -> str:
    """
    结论卡待展示时的动态提示词注入（追加在对话消息末尾）。
    context: prior_summary, prior_keywords, conclusion_rules_and_goals
    """
    return _get_loader().render("pending_conclusion_reply", context)


def get_simple_chat_system_prompt(context: Dict[str, Any]) -> str:
    """
    simple_chat 系统提示词。
    context: phase, question_bank, basic_info, prior_block,
             values_info（可选）, rumination_step_addon（可选）
    """
    return _get_loader().render("simple_chat_system", context)


def get_step_copy(phase: str, position: str = "intro", locale: str = "zh") -> str:
    """
    获取阶段引导文案（intro/outro）。
    phase: values | strengths | interests | purpose | rumination
    position: intro | outro
    locale: zh | en（读 step_copy.yaml 中 intro_zh / intro_en / outro_zh / outro_en）
    """
    loader = _get_loader()
    template_path = os.path.join(loader.templates_dir, "step_copy.yaml")
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f.read())
        phase_data = (data or {}).get(phase) or {}
        loc = (locale or "zh").strip().lower()
        if loc.startswith("en"):
            key = f"{position}_en"
            hit = (phase_data.get(key) or "").strip()
            if hit:
                return hit
        key_zh = f"{position}_zh"
        hit_zh = (phase_data.get(key_zh) or "").strip()
        if hit_zh:
            return hit_zh
        return (phase_data.get(position) or "").strip()
    except (FileNotFoundError, yaml.YAMLError):
        return ""
