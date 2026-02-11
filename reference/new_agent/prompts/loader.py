import os
from typing import Any, Dict, Optional

import yaml
from jinja2 import Environment, FileSystemLoader


class PromptLoader:
    """
    极简提示词加载器。

    功能：
    - 从 templates 目录加载 YAML；
    - 读取其中的 `prompt` 字段；
    - 可选使用 Jinja2 对 prompt 做一次渲染，注入知识/用户历史等上下文。
    """

    def __init__(self, templates_dir: Optional[str] = None):
        if templates_dir is None:
            templates_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.templates_dir = templates_dir

        self._env = Environment(
            loader=FileSystemLoader(self.templates_dir),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def _load_yaml(self, name: str) -> Dict[str, Any]:
        path = os.path.join(self.templates_dir, f"{name}.yaml")
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def load_prompt(self, name: str) -> str:
        """仅加载 YAML 中的纯 prompt 文本。"""
        data = self._load_yaml(name)
        return data.get("prompt", "")

    def render_prompt(self, name: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        使用 Jinja2 渲染模板中的 prompt 字段。
        - context 可包含专业知识片段、用户历史总结等。
        """
        context = context or {}
        template = self._env.get_template(f"{name}.yaml")
        rendered = template.render(**context)

        # YAML 里一般是 `prompt: | ...`，渲染完需要再解析一次以取出 prompt 字段
        data = yaml.safe_load(rendered)
        return data.get("prompt", "")


_loader = PromptLoader()


def get_loader() -> PromptLoader:
    return _loader

