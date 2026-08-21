"""xunlu 精简渲染器桥接（ADR-0019）。

子进程调用 src/report-renderer 的 Node 渲染脚本（markdown → A4 HTML → Chrome headless
打印 PDF），与内置 WeasyPrint 渲染器通过 RENDER_ENGINE 开关共存。

契约：
- 输入：报告 markdown 文本 + 可选元数据（昵称/日期/签名方案）
- 输出：PDF bytes（渲染器不落盘，临时文件即用即清）
- 昵称缺省时由渲染器从 markdown 的「{昵称}的寻路之旅」标题提取
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)


class XunluRenderError(RuntimeError):
    """xunlu 渲染器调用失败（未构建 / 非零退出 / 无产出）。"""


class XunluRenderTimeout(XunluRenderError):
    """渲染超时（默认 120s，REPORT_RENDER_TIMEOUT 可调）。"""


def _renderer_entry() -> Path:
    return Path(settings.REPORT_RENDERER_DIR) / "dist" / "render-pdf.mjs"


def render_pdf_with_xunlu(
    markdown_text: str,
    *,
    nickname: Optional[str] = None,
    date: Optional[str] = None,
    signature: Optional[str] = None,
) -> bytes:
    """用 xunlu 精简渲染器把报告 markdown 渲染为 PDF bytes。

    Args:
        markdown_text: 报告 markdown（后处理完毕；渲染器自带存量方言归一化）
        nickname: 封面探索者昵称（缺省由渲染器从 markdown 标题提取）
        date: 封面报告日期（如 "2026 年 08 月 20 日"，缺省取当天）
        signature: 落款签名方案 01/02/03（缺省用渲染器当前设计默认值）

    Raises:
        XunluRenderTimeout: 渲染超时
        XunluRenderError: 其余失败（stderr 摘要进异常信息）
    """
    entry = _renderer_entry()
    if not entry.is_file():
        raise XunluRenderError(
            f"xunlu 渲染器未构建：{entry} 不存在"
            "（请在 src/report-renderer 执行 npm install && npm run build）"
        )

    md_tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", prefix="xunlu-render-", encoding="utf-8", delete=False
    )
    md_tmp.write(markdown_text)
    md_tmp.close()
    out_tmp = tempfile.NamedTemporaryFile(suffix=".pdf", prefix="xunlu-render-", delete=False)
    out_tmp.close()

    cmd = [
        settings.REPORT_RENDERER_NODE,
        str(entry),
        "--md", md_tmp.name,
        "--out", out_tmp.name,
    ]
    if nickname:
        cmd += ["--nickname", nickname]
    if date:
        cmd += ["--date", date]
    if signature:
        cmd += ["--signature", signature]
    if settings.CHROME_PATH:
        cmd += ["--chrome", settings.CHROME_PATH]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=settings.REPORT_RENDER_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        raise XunluRenderTimeout(f"xunlu 渲染超时（>{settings.REPORT_RENDER_TIMEOUT}s）")
    except OSError as e:
        raise XunluRenderError(f"xunlu 渲染进程启动失败: {e}")
    finally:
        Path(md_tmp.name).unlink(missing_ok=True)

    try:
        if result.returncode != 0:
            stderr_tail = (result.stderr or result.stdout or "").strip()[-500:]
            logger.error("xunlu 渲染失败: exit=%s stderr=%s", result.returncode, stderr_tail)
            raise XunluRenderError(f"xunlu 渲染失败（exit={result.returncode}）: {stderr_tail}")
        pdf_bytes = Path(out_tmp.name).read_bytes()
        if not pdf_bytes:
            raise XunluRenderError("xunlu 渲染器产出了空 PDF")
        return pdf_bytes
    finally:
        Path(out_tmp.name).unlink(missing_ok=True)
