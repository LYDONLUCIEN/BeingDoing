#!/usr/bin/env python3
"""离线检查 base 与环境覆盖配置；只读取命令行指定的文件。"""

from __future__ import annotations

import argparse
import io
import logging
import warnings
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values
from dotenv.parser import parse_stream

PLACEHOLDER_SECRET = "your-secret-key-here-change-in-production"
TEAM_EMAIL = "openlife.lab@outlook.com"
ALIPAY_GATEWAY = "https://openapi.alipay.com/gateway.do"
ALIPAY_NOTIFY_URL = "https://openlife.beyondego.me/api/v1/payment/notify/alipay"
ALIPAY_RETURN_URL = "https://openlife.beyondego.me/payment/result"

DEV_OVERLAY_REQUIREMENTS = {
    "APP_ENV": "development",
    "FRONTEND_URL": "https://career.beyondego.me",
    "NEXT_PUBLIC_SITE_URL": "",
}
PROD_OVERLAY_REQUIREMENTS = {
    "APP_ENV": "production",
    "DEBUG": "False",
    "DEBUG_MODE": "False",
    "REFRESH_COOKIE_SECURE": "True",
    "FRONTEND_URL": "https://openlife.beyondego.me",
    "NEXT_PUBLIC_SITE_URL": "https://openlife.beyondego.me",
}
PAYMENT_REQUIREMENTS = {
    "ALIPAY_GATEWAY": ALIPAY_GATEWAY,
    "ALIPAY_NOTIFY_URL": ALIPAY_NOTIFY_URL,
    "ALIPAY_RETURN_URL": ALIPAY_RETURN_URL,
}
# settings.py 中实际字段为 BOUNCE_IMAP_PASS，而非 IMAP_PASS。
OPTIONAL_ISOLATED_SECRETS = (
    "REFRESH_TOKEN_SECRET_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "GLM_API_KEY",
    "KIMI_API_KEY",
    "CLAUDE_API_KEY",
    "QWEN_API_KEY",
    "SMTP_PASS",
    "BOUNCE_IMAP_PASS",
    "OSS_ACCESS_KEY_SECRET",
)


@dataclass(frozen=True)
class CheckResult:
    """一条只含固定规则标识和脱敏说明的结果。"""

    rule_id: str
    status: str
    message: str


class CheckError(Exception):
    """只携带可公开固定说明的用法、文件或解析错误。"""

    def __init__(self, rule_id: str, message: str) -> None:
        super().__init__(message)
        self.rule_id = rule_id
        self.message = message


class SafeArgumentParser(argparse.ArgumentParser):
    """避免 argparse 把动态参数错误写入 stderr。"""

    def error(self, message: str) -> None:
        raise CheckError("CLI_USAGE", "参数用法错误；请核对环境及文件参数组合。") from None


def build_parser() -> SafeArgumentParser:
    """构建无自动帮助输出的参数解析器，保证错误输出始终脱敏。"""
    parser = SafeArgumentParser(add_help=False)
    parser.add_argument("--env", choices=("dev", "prod", "all"), required=True)
    parser.add_argument("--base", default=".env")
    parser.add_argument("--overlay")
    parser.add_argument("--dev")
    parser.add_argument("--prod")
    return parser


def load_env_file(path: Path) -> dict[str, str]:
    """用 python-dotenv 从内存解析单个文件，并拒绝重复键及无效行。"""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        raise CheckError(
            "ENV_FILE_READ", "无法读取指定的环境文件；请检查文件路径及读取权限。"
        ) from None
    except UnicodeError:
        raise CheckError("ENV_PARSE", "环境文件不是可解析的 UTF-8 文本。") from None

    previous_disable = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    try:
        # dotenv 的日志、warning 和异常文本均不得进入进程输出。
        with (
            warnings.catch_warnings(),
            redirect_stdout(io.StringIO()),
            redirect_stderr(io.StringIO()),
        ):
            warnings.simplefilter("ignore")
            bindings = list(parse_stream(io.StringIO(text)))
            seen_keys: set[str] = set()
            has_duplicate = False
            has_invalid = False
            for binding in bindings:
                if binding.error:
                    has_invalid = True
                elif binding.key is not None:
                    if binding.key in seen_keys:
                        has_duplicate = True
                    seen_keys.add(binding.key)

            if has_invalid:
                raise CheckError("ENV_INVALID_LINE", "环境文件存在无效配置行；请修正后重试。")
            if has_duplicate:
                raise CheckError("ENV_DUPLICATE_KEY", "同一环境文件存在重复键；请去重后重试。")

            # 禁止从进程环境插值；有效配置只能来自显式给定的文件。
            parsed = dotenv_values(stream=io.StringIO(text), interpolate=False)
            return {
                key: value for key, value in parsed.items() if key is not None and value is not None
            }
    except CheckError:
        raise
    except Exception:
        raise CheckError("ENV_PARSE", "环境文件解析失败；未显示原始配置或异常详情。") from None
    finally:
        logging.disable(previous_disable)


def exact_check(
    env: str,
    key: str,
    actual: str | None,
    expected: str,
    *,
    explicit_overlay: bool = False,
) -> CheckResult:
    """生成固定值检查结果，不回显实际值或期望值。"""
    rule_id = f"{env.upper()}_{key}"
    scope = "覆盖文件中的显式配置" if explicit_overlay else "有效配置"
    if actual == expected:
        return CheckResult(rule_id, "PASS", f"{key} 的{scope}符合固定要求。")
    return CheckResult(rule_id, "FAIL", f"{key} 的{scope}缺失或不符合固定要求。")


def main_secret_check(env: str, config: dict[str, str]) -> CheckResult:
    """dev/prod 均检查主密钥的占位值和去空白后的最小长度。"""
    normalized = config.get("SECRET_KEY", "").strip()
    valid = bool(normalized) and normalized != PLACEHOLDER_SECRET and len(normalized) >= 32
    if valid:
        message = "SECRET_KEY 已通过占位值及最小长度检查。"
        status = "PASS"
    else:
        message = "SECRET_KEY 缺失、仍为占位值或去除空白后不足 32 个字符。"
        status = "FAIL"
    return CheckResult(f"{env.upper()}_SECRET_KEY", status, message)


def refresh_secret_check(config: dict[str, str]) -> CheckResult:
    """生产独立刷新密钥为空时允许回退，非空时必须满足最小长度。"""
    value = config.get("REFRESH_TOKEN_SECRET_KEY", "")
    valid = not value or len(value.strip()) >= 32
    if valid:
        message = "独立刷新密钥为空或已满足最小长度要求。"
        status = "PASS"
    else:
        message = "独立刷新密钥已配置，但去除空白后不足 32 个字符。"
        status = "FAIL"
    return CheckResult("PROD_REFRESH_TOKEN_SECRET_KEY", status, message)


def check_environment(
    env: str, config: dict[str, str], overlay: dict[str, str]
) -> list[CheckResult]:
    """检查单个环境的覆盖显式值与 base 合并后的有效配置。"""
    requirements = DEV_OVERLAY_REQUIREMENTS if env == "dev" else PROD_OVERLAY_REQUIREMENTS
    results = [
        exact_check(env, key, overlay.get(key), expected, explicit_overlay=True)
        for key, expected in requirements.items()
    ]
    results.append(main_secret_check(env, config))
    if env == "prod":
        results.append(refresh_secret_check(config))

    results.append(
        exact_check(env, "TEAM_ANALYSIS_EMAIL", config.get("TEAM_ANALYSIS_EMAIL"), TEAM_EMAIL)
    )
    for key, expected in PAYMENT_REQUIREMENTS.items():
        if key == "ALIPAY_NOTIFY_URL" and not config.get(key) and "LIPAY_NOTIFY_URL" in config:
            results.append(
                CheckResult(
                    f"{env.upper()}_ALIPAY_NOTIFY_URL",
                    "FAIL",
                    "ALIPAY_NOTIFY_URL 缺失，且检测到 LIPAY_NOTIFY_URL 错名；请使用正确字段。",
                )
            )
        else:
            results.append(exact_check(env, key, config.get(key), expected))

    if env == "dev" and all(
        config.get(key) == PAYMENT_REQUIREMENTS[key]
        for key in (
            "ALIPAY_NOTIFY_URL",
            "ALIPAY_RETURN_URL",
        )
    ):
        results.append(
            CheckResult(
                "DEV_ALIPAY_SHARED_PRODUCTION",
                "INFO",
                "开发环境共享生产支付宝 notify/return；生产域名不可用会影响这两条链路；"
                "本项不代表真实支付通过。",
            )
        )
    return results


def check_isolation(dev: dict[str, str], prod: dict[str, str]) -> list[CheckResult]:
    """比较 dev/prod 有效配置中要求隔离的秘密，不比较其他配置。"""
    if dev.get("SECRET_KEY", "").strip() == prod.get("SECRET_KEY", "").strip():
        main_result = CheckResult(
            "ALL_SECRET_KEY_ISOLATION",
            "FAIL",
            "dev/prod 的 SECRET_KEY 相同；两个环境必须使用不同主密钥。",
        )
    else:
        main_result = CheckResult(
            "ALL_SECRET_KEY_ISOLATION", "PASS", "dev/prod 的 SECRET_KEY 不同。"
        )

    results = [main_result]
    for key in OPTIONAL_ISOLATED_SECRETS:
        rule_id = f"ALL_{key}_ISOLATION"
        dev_value = dev.get(key, "").strip()
        prod_value = prod.get(key, "").strip()
        if not dev_value or not prod_value:
            results.append(
                CheckResult(rule_id, "PASS", f"{key} 未在两边同时非空配置，按规则无需比较。")
            )
        elif dev_value == prod_value:
            results.append(
                CheckResult(
                    rule_id,
                    "FAIL",
                    f"dev/prod 的 {key} 使用相同非空值；两个环境必须隔离该秘密。",
                )
            )
        else:
            results.append(CheckResult(rule_id, "PASS", f"dev/prod 的 {key} 非空值不同。"))
    return results


def resolve_path(root: Path, value: str) -> Path:
    """相对路径只相对于当前工作目录，绝不回退到脚本所在目录。"""
    path = Path(value)
    return path if path.is_absolute() else root / path


def collect_results(args: argparse.Namespace) -> list[CheckResult]:
    """校验参数组合，按 base 后 overlay 的顺序构造有效配置。"""
    if args.env == "all":
        if args.overlay is not None:
            raise CheckError("CLI_USAGE", "all 模式使用 --dev 和 --prod，不接受 --overlay。")
    elif args.dev is not None or args.prod is not None:
        raise CheckError("CLI_USAGE", "单环境模式使用 --overlay，不接受 --dev 或 --prod。")

    root = Path.cwd()
    base = load_env_file(resolve_path(root, args.base))
    if args.env != "all":
        overlay_name = args.overlay if args.overlay is not None else f".env.{args.env}"
        overlay = load_env_file(resolve_path(root, overlay_name))
        effective = {**base, **overlay}
        return check_environment(args.env, effective, overlay)

    dev_name = args.dev if args.dev is not None else ".env.dev"
    prod_name = args.prod if args.prod is not None else ".env.prod"
    dev_overlay = load_env_file(resolve_path(root, dev_name))
    prod_overlay = load_env_file(resolve_path(root, prod_name))
    dev = {**base, **dev_overlay}
    prod = {**base, **prod_overlay}
    results = check_environment("dev", dev, dev_overlay)
    results.extend(check_environment("prod", prod, prod_overlay))
    results.extend(check_isolation(dev, prod))
    return results


def emit(result: CheckResult) -> None:
    """按固定格式输出一条结果。"""
    print(f"{result.rule_id} {result.status} {result.message}")


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：0 全部必需项通过，1 任一 FAIL，2 用法/文件/解析错误。"""
    try:
        args = build_parser().parse_args(argv)
        results = collect_results(args)
    except CheckError as error:
        emit(CheckResult(error.rule_id, "FAIL", error.message))
        return 2

    for result in results:
        emit(result)
    return 1 if any(result.status == "FAIL" for result in results) else 0


def entrypoint() -> int:
    """CLI 边界兜底：即使发生意外异常，也只输出固定脱敏错误。"""
    try:
        return main()
    except BaseException:
        emit(
            CheckResult(
                "ENV_INTERNAL",
                "FAIL",
                "检查因内部错误中止；未显示原始配置或异常详情。",
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(entrypoint())
