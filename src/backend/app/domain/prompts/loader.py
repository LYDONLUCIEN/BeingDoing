"""
领域提示词加载器：从 templates 目录加载 YAML，Jinja2 渲染注入上下文。
仅此一层，节点直接调用 get_*_prompt(ctx)，不嵌套多级读取。
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
        self._env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, name: str, context: Optional[Dict[str, Any]] = None) -> str:
        context = context or {}
        template = self._env.get_template(f"{name}.yaml")
        rendered = template.render(**context)
        data = yaml.safe_load(rendered)
        return (data or {}).get("prompt", "")


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
