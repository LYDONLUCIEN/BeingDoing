"""check_env.py 的离线 CLI 测试；全部配置均由 tmp_path 合成。"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_env.py"
OUTPUT_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]* (PASS|INFO|FAIL) .+$")
BASE_REQUIRED = {
    "TEAM_ANALYSIS_EMAIL": "openlife.lab@outlook.com",
    "ALIPAY_GATEWAY": "https://openapi.alipay.com/gateway.do",
    "ALIPAY_NOTIFY_URL": "https://openlife.beyondego.me/api/v1/payment/notify/alipay",
    "ALIPAY_RETURN_URL": "https://openlife.beyondego.me/payment/result",
}
DEV_REQUIRED = {
    "APP_ENV": "development",
    "FRONTEND_URL": "https://career.beyondego.me",
    "NEXT_PUBLIC_SITE_URL": "",
}
PROD_REQUIRED = {
    "APP_ENV": "production",
    "DEBUG": "False",
    "DEBUG_MODE": "False",
    "REFRESH_COOKIE_SECURE": "True",
    "FRONTEND_URL": "https://openlife.beyondego.me",
    "NEXT_PUBLIC_SITE_URL": "https://openlife.beyondego.me",
}


def _overlay_text(env: str, marker: str, **changes: str | None) -> str:
    required = dict(DEV_REQUIRED if env == "dev" else PROD_REQUIRED)
    required["SECRET_KEY"] = f"{marker}-{env}-secret-with-enough-length"
    for key, value in changes.items():
        if value is None:
            required.pop(key)
        else:
            required[key] = value
    return "".join(f"{key}={value}\n" for key, value in required.items())


def _write_case(tmp_path: Path, marker: str, **changes: str | None) -> dict[str, Path]:
    """公共固定项放在 base；环境显式值和秘密放在 overlay。"""
    paths = {
        "base": tmp_path / "base.env",
        "dev": tmp_path / "dev.env",
        "prod": tmp_path / "prod.env",
    }
    base = dict(BASE_REQUIRED)
    base["TEST_SENTINEL_SECRET"] = f"{marker}-base-secret"
    overlay_changes: dict[str, str | None] = {}
    for key, value in changes.items():
        if key in base:
            if value is None:
                base.pop(key)
            else:
                base[key] = value
        else:
            overlay_changes[key] = value
    paths["base"].write_text(
        "".join(f"{key}={value}\n" for key, value in base.items()), encoding="utf-8"
    )
    for env in ("dev", "prod"):
        text = _overlay_text(env, marker, **overlay_changes)
        paths[env].write_text(text + f"DEEPSEEK_API_KEY={env}-{marker}-model\n", encoding="utf-8")
    return paths


def _raw_lines(paths: dict[str, Path]) -> list[str]:
    return [
        line
        for path in paths.values()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _run_command(
    args: list[str],
    cwd: Path,
    *,
    paths: dict[str, Path] | None = None,
    stdin_source: str | None = None,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-"] if stdin_source is not None else [sys.executable, str(SCRIPT)]
    result = subprocess.run(
        [*command, *args],
        cwd=cwd,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8"},
        input=stdin_source,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if paths is not None:
        result.raw_lines = _raw_lines(paths)  # type: ignore[attr-defined]
    return result


def _run(env: str, paths: dict[str, Path], cwd: Path) -> subprocess.CompletedProcess[str]:
    args = ["--env", env, "--base", str(paths["base"])]
    if env == "all":
        args += ["--dev", str(paths["dev"]), "--prod", str(paths["prod"])]
    else:
        args += ["--overlay", str(paths[env])]
    return _run_command(args, cwd, paths=paths)


def _assert_clean(
    result: subprocess.CompletedProcess[str],
    *sentinels: str,
    raw_lines: list[str] | None = None,
) -> None:
    output = result.stdout + result.stderr
    for sentinel in sentinels:
        assert sentinel not in output
    for line in raw_lines if raw_lines is not None else getattr(result, "raw_lines", []):
        assert line not in output
    assert result.stderr == ""
    assert "Traceback" not in output
    assert "Python-dotenv" not in output
    for line in result.stdout.splitlines():
        assert OUTPUT_PATTERN.fullmatch(line)


@pytest.mark.parametrize("env", ["dev", "prod", "all"])
def test_valid_environment(tmp_path: Path, env: str) -> None:
    """合法配置退出 0；空 cwd 加显式路径确保不读默认真实 env。"""
    marker = f"valid-{env}-sentinel"
    paths = _write_case(tmp_path, marker)
    cwd = tmp_path / "empty"
    cwd.mkdir()
    result = _run(env, paths, cwd)

    assert result.returncode == 0
    assert " FAIL " not in result.stdout
    if env == "dev":
        assert "DEV_ALIPAY_SHARED_PRODUCTION INFO" in result.stdout
    if env == "all":
        assert "ALL_SECRET_KEY_ISOLATION PASS" in result.stdout
    _assert_clean(result, marker)


@pytest.mark.parametrize(
    ("env", "changes", "rule"),
    [
        ("dev", {"APP_ENV": "production"}, "DEV_APP_ENV FAIL"),
        ("prod", {"APP_ENV": "development"}, "PROD_APP_ENV FAIL"),
        ("prod", {"DEBUG": "True"}, "PROD_DEBUG FAIL"),
        ("prod", {"DEBUG_MODE": "True"}, "PROD_DEBUG_MODE FAIL"),
        ("prod", {"REFRESH_COOKIE_SECURE": "False"}, "PROD_REFRESH_COOKIE_SECURE FAIL"),
        ("prod", {"NEXT_PUBLIC_SITE_URL": "https://bad.example"}, "PROD_NEXT_PUBLIC_SITE_URL FAIL"),
        ("dev", {"NEXT_PUBLIC_SITE_URL": "https://bad.example"}, "DEV_NEXT_PUBLIC_SITE_URL FAIL"),
        ("dev", {"TEAM_ANALYSIS_EMAIL": "team@example.com"}, "DEV_TEAM_ANALYSIS_EMAIL FAIL"),
        ("prod", {"TEAM_ANALYSIS_EMAIL": "team@example.com"}, "PROD_TEAM_ANALYSIS_EMAIL FAIL"),
        ("prod", {"ALIPAY_NOTIFY_URL": None}, "PROD_ALIPAY_NOTIFY_URL FAIL"),
        ("dev", {"ALIPAY_RETURN_URL": None}, "DEV_ALIPAY_RETURN_URL FAIL"),
        ("prod", {"ALIPAY_GATEWAY": "https://bad.example"}, "PROD_ALIPAY_GATEWAY FAIL"),
    ],
)
def test_invalid_fixed_value(
    tmp_path: Path, env: str, changes: dict[str, str | None], rule: str
) -> None:
    marker = f"invalid-{env}-{rule.split('_', 2)[1].lower()}-sentinel"
    result = _run(env, _write_case(tmp_path, marker, **changes), tmp_path)
    assert result.returncode == 1
    assert rule in result.stdout
    _assert_clean(result, marker)


@pytest.mark.parametrize("env", ["dev", "prod"])
@pytest.mark.parametrize("kind", ["short", "placeholder"])
def test_invalid_main_secret(tmp_path: Path, env: str, kind: str) -> None:
    marker = f"main-{kind}-{env}-sentinel"
    secret = "short-secret" if kind == "short" else "your-secret-key-here-change-in-production"
    paths = _write_case(tmp_path, marker)
    paths[env].write_text(
        _overlay_text(env, marker, SECRET_KEY=None) + f"SECRET_KEY={secret}\n",
        encoding="utf-8",
    )
    result = _run(env, paths, tmp_path)

    assert result.returncode == 1
    assert f"{env.upper()}_SECRET_KEY FAIL" in result.stdout
    _assert_clean(result, marker, secret)


def test_invalid_prod_refresh_secret(tmp_path: Path) -> None:
    marker = "refresh-short-sentinel"
    paths = _write_case(tmp_path, marker)
    with paths["prod"].open("a", encoding="utf-8") as file:
        file.write("REFRESH_TOKEN_SECRET_KEY=short-refresh-secret\n")
    result = _run("prod", paths, tmp_path)

    assert result.returncode == 1
    assert "PROD_REFRESH_TOKEN_SECRET_KEY FAIL" in result.stdout
    _assert_clean(result, marker, "short-refresh-secret")


def test_misspelled_payment_notify_key(tmp_path: Path) -> None:
    marker = "misspelled-notify-sentinel"
    paths = _write_case(tmp_path, marker, ALIPAY_NOTIFY_URL=None)
    with paths["prod"].open("a", encoding="utf-8") as file:
        file.write("LIPAY_NOTIFY_URL=https://bad.example\n")
    result = _run("prod", paths, tmp_path)

    assert result.returncode == 1
    assert "PROD_ALIPAY_NOTIFY_URL FAIL" in result.stdout
    assert "LIPAY_NOTIFY_URL 错名" in result.stdout
    _assert_clean(result, marker, "https://bad.example")


@pytest.mark.parametrize(
    ("target", "key"), [("base", "TEAM_ANALYSIS_EMAIL"), ("dev", "SECRET_KEY")]
)
def test_duplicate_key(tmp_path: Path, target: str, key: str) -> None:
    marker = f"duplicate-{target}-sentinel"
    duplicate = f"{marker}-second-value"
    paths = _write_case(tmp_path, marker)
    with paths[target].open("a", encoding="utf-8") as file:
        file.write(f"{key}={duplicate}\n")
    result = _run("dev", paths, tmp_path)

    assert result.returncode == 2
    assert "ENV_DUPLICATE_KEY FAIL" in result.stdout
    _assert_clean(result, marker, duplicate)


@pytest.mark.parametrize("target", ["base", "prod"])
def test_invalid_line(tmp_path: Path, target: str) -> None:
    marker = f"invalid-line-{target}-sentinel"
    paths = _write_case(tmp_path, marker)
    with paths[target].open("a", encoding="utf-8") as file:
        file.write(f"BROKEN LINE {marker}\n")
    result = _run("prod", paths, tmp_path)

    assert result.returncode == 2
    assert "ENV_INVALID_LINE FAIL" in result.stdout
    _assert_clean(result, marker, "BROKEN LINE")


@pytest.mark.parametrize("shared_key", ["SECRET_KEY", "OPENAI_API_KEY"])
def test_all_rejects_shared_secret(tmp_path: Path, shared_key: str) -> None:
    marker = f"shared-{shared_key.lower()}-sentinel"
    shared = f"{marker}-same-value"
    paths = _write_case(tmp_path, marker)
    for env in ("dev", "prod"):
        lines = [
            line
            for line in paths[env].read_text(encoding="utf-8").splitlines()
            if not line.startswith(f"{shared_key}=")
        ]
        text = "\n".join([*lines, f"{shared_key}={shared}"]) + "\n"
        paths[env].write_text(text, encoding="utf-8")
    result = _run("all", paths, tmp_path)

    assert result.returncode == 1
    assert f"ALL_{shared_key}_ISOLATION FAIL" in result.stdout
    _assert_clean(result, marker, shared)


@pytest.mark.parametrize("args", [[], ["--env", "staging"]])
def test_invalid_usage(tmp_path: Path, args: list[str]) -> None:
    result = _run_command(args, tmp_path)
    assert result.returncode == 2
    assert "CLI_USAGE FAIL" in result.stdout
    _assert_clean(result, "usage-sentinel")


def test_incompatible_and_missing_file_errors(tmp_path: Path) -> None:
    marker = "input-error-sentinel"
    paths = _write_case(tmp_path, marker)
    incompatible = _run_command(
        ["--env", "all", "--base", str(paths["base"]), "--overlay", str(paths["prod"])],
        tmp_path,
        paths=paths,
    )
    missing = _run_command(
        ["--env", "prod", "--base", str(paths["base"]), "--overlay", str(tmp_path / "none.env")],
        tmp_path,
        paths=paths,
    )

    assert incompatible.returncode == 2
    assert "CLI_USAGE FAIL" in incompatible.stdout
    assert missing.returncode == 2
    assert "ENV_FILE_READ FAIL" in missing.stdout
    _assert_clean(incompatible, marker)
    _assert_clean(missing, marker, "none.env")


def test_stdin_execution(tmp_path: Path) -> None:
    marker = "stdin-sentinel"
    paths = _write_case(tmp_path, marker)
    result = _run_command(
        ["--env", "prod", "--base", str(paths["base"]), "--overlay", str(paths["prod"])],
        tmp_path,
        paths=paths,
        stdin_source=SCRIPT.read_text(encoding="utf-8"),
    )

    assert result.returncode == 0
    assert "PROD_APP_ENV PASS" in result.stdout
    _assert_clean(result, marker)
