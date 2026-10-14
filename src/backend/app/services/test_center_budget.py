"""真实模型显式配置、批次调用上限与持久化预留；不继承业务模型密钥。"""

import json
import os
import time
import uuid
from urllib.parse import urlparse

from app.services.test_center import digest, encode

OUTPUT_LIMIT = 8192


def model_config():
    raw = os.environ.get("TEST_CENTER_AI_CONFIG", "")
    if not raw:
        raise ValueError("未配置 TEST_CENTER_AI_CONFIG；真实 AI 未启用")
    try:
        value = json.loads(raw)
        if set(value) - {
            "provider",
            "base_url",
            "chat",
            "rumination",
            "conclusion",
            "report",
            "unknown",
            "input_price",
            "output_price",
            "currency",
        }:
            raise ValueError("模型配置含未知字段；密钥只能通过 worker 专用环境变量传入")
        url = urlparse(value["base_url"])
        if (
            url.scheme != "https"
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError("模型地址必须是不含凭据和查询参数的 HTTPS 地址")
        if value["provider"] not in {"deepseek", "kimi", "qwen", "openai"}:
            raise ValueError("不支持此模型协议")
        for scene in (
            "chat",
            "rumination",
            *(s for s in ("conclusion", "report", "unknown") if s in value),
        ):
            profile = value[scene]
            if (
                set(profile) != {"model", "thinking"}
                or not isinstance(profile["model"], str)
                or not profile["model"].strip()
                or not isinstance(profile["thinking"], bool)
            ):
                raise ValueError("每个模型场景必须明确 model 和 thinking")
            if profile["thinking"] and not (
                value["provider"] == "deepseek" and "v4" in profile["model"].lower()
            ):
                raise ValueError("当前执行器仅支持 DeepSeek v4 的思考开关；其他模型请关闭")
        pricing = {"input_price", "output_price", "currency"}
        if pricing & set(value):
            if (
                not pricing <= set(value)
                or not value["currency"]
                or any(
                    not isinstance(value[k], (int, float)) or not 0 <= value[k] < 1000000
                    for k in ("input_price", "output_price")
                )
            ):
                raise ValueError("费用需同时配置币种与每百万输入/输出 token 单价")
        return value
    except (KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("模型配置格式错误") from error


def capabilities(center):
    try:
        config = model_config()
        return {
            "configured": True,
            "config": config,
            "config_digest": digest(config),
            "worker_key_ready": bool(center.worker_status().get("ai_key_ready")),
            "budget_unit": "calls_and_tokens",
        }
    except ValueError as error:
        return {"configured": False, "reason": str(error), "worker_key_ready": False}


def prepare(center, cases, budget):
    from app.services.test_center_ai import get_context

    config = model_config()
    if not budget:
        raw = os.environ.get("TEST_CENTER_AI_BUDGET", "")
        try:
            budget = json.loads(raw) if raw else None
        except ValueError as error:
            raise ValueError("默认批次预算格式错误") from error
    if not isinstance(budget, dict) or set(budget) != {"max_calls", "max_tokens"}:
        raise ValueError("真实 AI 需要显式 max_calls/max_tokens 预算或运维配置的上限")
    if (
        any(isinstance(v, bool) or not isinstance(v, int) for v in budget.values())
        or not 1 <= budget["max_calls"] <= 1000
        or not 1 <= budget["max_tokens"] <= 20000000
    ):
        raise ValueError("预算须为正整数，最多 1000 次调用和 2000 万 token")
    planned = 0
    contexts = {}
    for case in cases:
        value = case["definition"]
        context = get_context(center, value["context_id"])
        contexts[value["context_id"]] = context
        if value.get("conversation_mode") == "workflow":
            from app.services.test_center_workflow import maximum_calls

            planned += value["repeats"] * maximum_calls(value, context["spec"]["phase"])
            continue
        planned += value["repeats"] * sum(
            1
            + any(c["type"] == "semantic" and c.get("turn", turn) == turn for c in value["checks"])
            for turn in range(1, len(value["inputs"]) + 1)
        )
    if planned > budget["max_calls"]:
        raise ValueError(f"预计 {planned} 次调用（含语义判定），超过调用预算")
    return {
        "config": config,
        "config_digest": digest(config),
        "budget": budget,
        "planned_calls": planned,
        "contexts": contexts,
        "max_output_tokens": OUTPUT_LIMIT,
    }


def reserve_tokens(messages, output_limit):
    # 字节数加消息封装余量的保守预算，不冒充模型 tokenizer 或计费账单。
    return sum(len(m["content"].encode()) + 256 for m in messages) + 4096 + output_limit


def reserve(center, run, case_id, attempt, purpose, messages, config, output_limit=OUTPUT_LIMIT):
    if not isinstance(output_limit, int) or not 1 <= output_limit <= 65536:
        raise ValueError("模型输出上限必须明确且不超过 65536 token")
    reserved = reserve_tokens(messages, output_limit)
    with center.db() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT cancel FROM runs WHERE id=?", (run["id"],)).fetchone()[0]:
            raise InterruptedError("批次已取消，不再发起模型调用")
        rows = [
            json.loads(r[0])
            for r in db.execute("SELECT payload FROM calls WHERE run_id=?", (run["id"],))
        ]
        if any(row["status"] in {"issued", "usage_unknown", "accounting_error"} for row in rows):
            raise ValueError("本批次有未完成或用量未知的调用，停止后续调用并人工核对")
        used = sum(r["charged_tokens"] for r in rows)
        budget = run["ai"]["budget"]
        if len(rows) >= budget["max_calls"] or used + reserved > budget["max_tokens"]:
            raise ValueError("批次预算不足；本次调用未发出，剩余测试未完成")
        call = {
            "id": uuid.uuid4().hex,
            "run_id": run["id"],
            "case_id": case_id,
            "attempt": attempt,
            "purpose": purpose,
            "created": time.time(),
            "status": "issued",
            "reserved_tokens": reserved,
            "charged_tokens": reserved,
            "usage": None,
            "prompt_digest": digest(messages),
            "messages": messages,
            "config": config,
            "executor": "ai-replay-v1",
            "max_output_tokens": output_limit,
        }
        db.execute(
            "INSERT INTO calls VALUES(?,?,?,?)",
            (call["id"], run["id"], call["created"], encode(call)),
        )
    return call


def settle(center, call, result=None):
    if result:
        usage = result.get("usage") or {}
        counts = [usage.get("prompt_tokens"), usage.get("completion_tokens")]
        if all(isinstance(n, int) and not isinstance(n, bool) and n >= 0 for n in counts):
            call.update(usage=usage, charged_tokens=sum(counts), status="completed")
            if sum(counts) > call["reserved_tokens"]:
                call["status"] = "accounting_error"
            config = call["config"]
            if "input_price" in config:
                call["cost"] = (
                    counts[0] * config["input_price"] + counts[1] * config["output_price"]
                ) / 1000000
                call["currency"] = config["currency"]
        else:
            call["status"] = "usage_unknown"
        call["response"] = result
    else:
        call["status"] = "usage_unknown"
    call["finished"] = time.time()
    with center.db() as db:
        db.execute("UPDATE calls SET payload=? WHERE id=?", (encode(call), call["id"]))
    return call


def evidence(center, run, compact=False):
    with center.db() as db:
        calls = [
            json.loads(r[0])
            for r in db.execute(
                "SELECT payload FROM calls WHERE run_id=? ORDER BY created",
                (run["id"],),
            )
        ]
        reviews = [
            json.loads(r[0])
            for r in db.execute(
                "SELECT payload FROM reviews WHERE run_id=? ORDER BY created",
                (run["id"],),
            )
        ]
    run["calls"] = calls
    run["reviews"] = reviews
    run["usage"] = {
        "calls": len(calls),
        "total_tokens": sum(
            (c.get("usage") or {}).get("prompt_tokens", 0)
            + (c.get("usage") or {}).get("completion_tokens", 0)
            for c in calls
        ),
        "charged_tokens": sum(c["charged_tokens"] for c in calls),
        "unknown_calls": sum(c["status"] != "completed" for c in calls),
        "cost": (
            sum(c.get("cost", 0) for c in calls)
            if calls and all("cost" in c for c in calls)
            else None
        ),
        "currency": calls[0].get("currency") if calls else None,
    }
    if compact:
        # 列表不重复传输所有上下文/提示词，按批次详情查看完整证据。
        run.pop("calls", None)
        run.pop("reviews", None)
        if run.get("ai"):
            run["ai"].pop("contexts", None)
        for case in run["cases"]:
            case.pop("attempts", None)
            case.pop("upstream", None)
    return run
