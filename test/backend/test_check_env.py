"""环境配置检查器的合成数据测试；不读取仓库真实 env。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_env.py"

TEAM_EMAIL = "openlife.lab@outlook.com"
PAYMENT = {
    "ALIPAY_NOTIFY_URL": "https://openlife.beyondego.me/api/v1/payment/notify/alipay",
    "ALIPAY_RETURN_URL": "https://openlife.beyondego.me/payment/result",
    "ALIPAY_GATEWAY": "https://openapi.alipay.com/gateway.do",
}
DEV_REQUIRED = {
    "APP_ENV": "development",
    "DEBUG": "True",
    "DEBUG_MODE": "True",
    "FRONTEND_URL": "https://career.beyondego.me",
    "NEXT_PUBLIC_SITE_URL": "",
    "TEAM_ANALYSIS_EMAIL": TEAM_EMAIL,
    **PAYMENT,
}
PROD_REQUIRED = {
    "APP_ENV": "production",
    "DEBUG": "False",
    "DEBUG_MODE": "False",
    "REFRESH_COOKIE_SECURE": "True",
    "FRONTEND_URL": "https://openlife.beyondego.me",
    "NEXT_PUBLIC_SITE_URL": "https://openlife.beyondego.me",
    "TEAM_ANALYSIS_EMAIL": TEAM_EMAIL,
    **PAYMENT,
}


def _overlay_text(env: str, marker: str, **changes: str | None) -> str:
    """生成完整覆盖层；值为 None 表示删除该键。"""
    required = dict(DEV_REQUIRED if env == "dev" else PROD_REQUIRED)
    required["SECRET_KEY"] = f"{marker}-{env}-secret-with-enough-length"
    for key, value in changes.items():
        if value is None:
            required.pop(key)
        else:
            required[key] = value
    return "".join(f"{key}={value}\n" for key, value in required.items())


def _write_case(tmp_path: Path, marker: str, **changes: str | None) -> dict[str, Path]:
    """写入互不相同的 dev/prod 合成配置，路径使用显式参数传入。"""
    paths = {
        "base": tmp_path / "base.env",
        "dev": tmp_path / "dev.env",
        "prod": tmp_path / "prod.env",
    }
    paths["base"].write_text("# 合成公共配置\n", encoding="utf-8")
    for env in ("dev", "prod"):
        text = _overlay_text(env, marker, **changes)
        text += f"DEEPSEEK_API_KEY={env}-model-key\n"
        paths[env].write_text(text, encoding="utf-8")
    return paths


def _raw_config_lines(paths: dict[str, Path]) -> list[str]:
    """收集合成配置原始行，用于断言输出未回显任何输入行。"""
    return [
        line
        for path in paths.values()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run(env: str, paths: dict[str, Path], cwd: Path) -> subprocess.CompletedProcess[str]:
    """在指定空工作目录运行 CLI，只允许读取显式给出的合成文件。"""
    command = [sys.executable, str(SCRIPT), "--env", env, "--base", str(paths["base"])]
    if env == "all":
        command += ["--dev", str(paths["dev"]), "--prod", str(paths["prod"])]
    else:
        command += ["--overlay", str(paths[env])]
    process_env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    result = subprocess.run(
        command,
        cwd=cwd,
        env=process_env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    result.raw_lines = _raw_config_lines(paths)  # type: ignore[attr-defined]
    return result


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return result.stdout + result.stderr


def _assert_no_secret_leak(
    result: subprocess.CompletedProcess[str],
    *sentinels: str,
    raw_lines: list[str] | None = None,
) -> None:
    output = _combined_output(result)
    for sentinel in sentinels:
        assert sentinel not in output
    lines = raw_lines if raw_lines is not None else getattr(result, "raw_lines", [])
    for line in lines:
        assert line not in output
    assert result.stderr == ""
    assert "Traceback" not in output
    assert "Python-dotenv" not in output


@pytest.mark.parametrize("env", ["dev", "prod", "all"])
def test_valid_environments_pass_without_reading_real_env(tmp_path: Path, env: str) -> None:
    marker = f"valid-{env}-sentinel"
    paths = _write_case(tmp_path, marker)
    empty_cwd = tmp_path / "empty"
    empty_cwd.mkdir()

    result = _run(env, paths, empty_cwd)

    assert result.returncode == 0, _combined_output(result)
    assert "PASS" in result.stdout
    assert "FAIL" not in result.stdout
    if env == "dev":
        assert "DEV_ALIPAY_SHARED_PRODUCTION INFO" in result.stdout
    if env == "all":
        assert "ALL_SECRET_KEY_ISOLATION PASS" in result.stdout
    _assert_no_secret_leak(result, marker, "dev-model-key", "prod-model-key")


@pytest.mark.parametrize(
    ("env", "changes", "expected_rule"),
    [
        ("dev", {"APP_ENV": "production"}, "DEV_APP_ENV FAIL"),
        ("prod", {"APP_ENV": "development"}, "PROD_APP_ENV FAIL"),
        ("prod", {"DEBUG": "True"}, "PROD_DEBUG FAIL"),
        ("prod", {"DEBUG_MODE": "True"}, "PROD_DEBUG_MODE FAIL"),
        ("prod", {"REFRESH_COOKIE_SECURE": "False"}, "PROD_REFRESH_COOKIE_SECURE FAIL"),
        (
            "prod",
            {"NEXT_PUBLIC_SITE_URL": "https://wrong.example"},
            "PROD_NEXT_PUBLIC_SITE_URL FAIL",
        ),
        (
            "dev",
            {"NEXT_PUBLIC_SITE_URL": "https://career.beyondego.me"},
            "DEV_NEXT_PUBLIC_SITE_URL FAIL",
        ),
        ("prod", {"TEAM_ANALYSIS_EMAIL": "team@example.com"}, "PROD_TEAM_ANALYSIS_EMAIL FAIL"),
        ("prod", {"ALIPAY_NOTIFY_URL": None}, "PROD_ALIPAY_NOTIFY_URL FAIL"),
        ("prod", {"ALIPAY_GATEWAY": "https://gateway.example"}, "PROD_ALIPAY_GATEWAY FAIL"),
    ],
)
def test_invalid_values_fail_without_leaking_values(
    tmp_path: Path,
    env: str,
    changes: dict[str, str | None],
    expected_rule: str,
) -> None:
    marker = f"invalid-{env}-{expected_rule.split('_')[1]}-sentinel"
    paths = _write_case(tmp_path, marker, **changes)

    result = _run(env, paths, tmp_path)

    assert result.returncode == 1
    assert expected_rule in result.stdout
    _assert_no_secret_leak(result, marker, "dev-model-key", "prod-model-key")


def test_short_secret_fails(tmp_path: Path) -> None:
    marker = "short-secret-sentinel"
    paths = _write_case(tmp_path, marker)
    paths["prod"].write_text(
        _overlay_text("prod", marker, SECRET_KEY=None) + "SECRET_KEY=short-secret\n",
        encoding="utf-8",
    )

    result = _run("prod", paths, tmp_path)

    assert result.returncode == 1
    assert "PROD_SECRET_KEY FAIL" in result.stdout
    _assert_no_secret_leak(result, marker, "short-secret")


def test_placeholder_secret_fails(tmp_path: Path) -> None:
    marker = "placeholder-sentinel"
    paths = _write_case(tmp_path, marker)
    paths["prod"].write_text(
        _overlay_text("prod", marker, SECRET_KEY=None)
        + "SECRET_KEY=your-secret-key-here-change-in-production\n",
        encoding="utf-8",
    )

    result = _run("prod", paths, tmp_path)

    assert result.returncode == 1
    assert "PROD_SECRET_KEY FAIL" in result.stdout
    _assert_no_secret_leak(result, marker)


def test_misspelled_alipay_key_fails_with_fixed_message(tmp_path: Path) -> None:
    marker = "misspelled-payment-sentinel"
    paths = _write_case(tmp_path, marker, ALIPAY_NOTIFY_URL=None)
    with paths["prod"].open("a", encoding="utf-8") as file:
        file.write("LIPAY_NOTIFY_URL=https://wrong.example\n")

    result = _run("prod", paths, tmp_path)

    assert result.returncode == 1
    assert "PROD_ALIPAY_NOTIFY_URL FAIL" in result.stdout
    assert "LIPAY_NOTIFY_URL 错名" in result.stdout
    _assert_no_secret_leak(result, marker, "https://wrong.example")


def test_duplicate_key_returns_input_error(tmp_path: Path) -> None:
    marker = "duplicate-secret-sentinel"
    paths = _write_case(tmp_path, marker)
    with paths["dev"].open("a", encoding="utf-8") as file:
        file.write(f"SECRET_KEY={marker}-second-value\n")

    result = _run("dev", paths, tmp_path)

    assert result.returncode == 2
    assert "ENV_DUPLICATE_KEY FAIL" in result.stdout
    _assert_no_secret_leak(result, marker, f"{marker}-second-value")


def test_invalid_line_returns_input_error_without_raw_line(tmp_path: Path) -> None:
    marker = "invalid-line-secret-sentinel"
    paths = _write_case(tmp_path, marker)
    with paths["prod"].open("a", encoding="utf-8") as file:
        file.write(f"THIS LINE IS INVALID {marker}\n")

    result = _run("prod", paths, tmp_path)

    assert result.returncode == 2
    assert "ENV_INVALID_LINE FAIL" in result.stdout
    _assert_no_secret_leak(result, marker, "THIS LINE IS INVALID")


def test_missing_file_returns_input_error(tmp_path: Path) -> None:
    paths = _write_case(tmp_path, "missing-file-sentinel")
    missing = tmp_path / "missing.env"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--env",
            "prod",
            "--base",
            str(paths["base"]),
            "--overlay",
            str(missing),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 2
    assert "ENV_FILE_READ FAIL" in result.stdout
    _assert_no_secret_leak(result, "missing-file-sentinel")


@pytest.mark.parametrize("shared_key", ["SECRET_KEY", "DEEPSEEK_API_KEY"])
def test_all_rejects_shared_isolated_secret(tmp_path: Path, shared_key: str) -> None:
    marker = f"shared-{shared_key.lower()}-sentinel"
    paths = _write_case(tmp_path, marker)
    for name in ("dev", "prod"):
        text = paths[name].read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if not line.startswith(f"{shared_key}=")]
        lines.append(f"{shared_key}={marker}-same-value")
        paths[name].write_text("\n".join(lines) + "\n", encoding="utf-8")

    result = _run("all", paths, tmp_path)

    assert result.returncode == 1
    assert f"ALL_{shared_key}_ISOLATION FAIL" in result.stdout
    _assert_no_secret_leak(result, marker, f"{marker}-same-value")


def test_argument_combination_error_is_sanitized(tmp_path: Path) -> None:
    paths = _write_case(tmp_path, "usage-sentinel")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--env",
            "all",
            "--base",
            str(paths["base"]),
            "--overlay",
            str(paths["prod"]),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 2
    assert "CLI_USAGE FAIL" in result.stdout
    _assert_no_secret_leak(result, "usage-sentinel")


def test_script_can_run_from_stdin(tmp_path: Path) -> None:
    marker = "stdin-sentinel"
    paths = _write_case(tmp_path, marker)

    result = subprocess.run(
        [
            sys.executable,
            "-",
            "--env",
            "prod",
            "--base",
            str(paths["base"]),
            "--overlay",
            str(paths["prod"]),
        ],
        input=SCRIPT.read_text(encoding="utf-8"),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, _combined_output(result)
    assert "PROD_APP_ENV PASS" in result.stdout
    _assert_no_secret_leak(result, marker)
