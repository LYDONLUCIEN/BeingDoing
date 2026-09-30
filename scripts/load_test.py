#!/usr/bin/env python3
"""
寻路·OpenLife 并发压测脚本（scripts/load_test.py）

模式：
- setup   ：在目标机上直接 import 后端内部服务，批量创建压测用户 + 试用激活码，
            写入 scripts/load_test_accounts.json（绕过注册接口的邮箱验证与 IP 频控）。
- run     ：对目标后端（默认 http://127.0.0.1:8000）按并发梯度压测，
            场景：readonly / chat_sse / pdf_render，可组合。
- teardown：按 load_test_accounts.json 物理清除压测用户及其激活码，并删除账号文件。

用法示例：
    python scripts/load_test.py --mode setup --users 60
    python scripts/load_test.py --mode run --scenario readonly --ladder 1,5,10,20,50 --duration 30
    python scripts/load_test.py --mode run --scenario chat_sse --ladder 1,5 --duration 15
    python scripts/load_test.py --mode run --scenario pdf_render --report-id <report_id> --ladder 1,3
    python scripts/load_test.py --mode teardown

注意：setup/teardown 需要在目标机上运行（能 import 后端 app 并访问其数据库与数据目录）。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import statistics
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

# ── 路径常量 ──────────────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parent.parent  # 项目根
BACKEND_DIR = ROOT_DIR / "src" / "backend"
DEFAULT_ACCOUNTS_FILE = ROOT_DIR / "scripts" / "load_test_accounts.json"

# ── 压测账号常量 ──────────────────────────────────────────────────────────
# 注意：域名必须能过 email-validator 格式校验（登录接口 LoginRequest 用了 EmailStr），
# .local 单标签域名会被拒（422），故用 example.com
LOADTEST_EMAIL_DOMAIN = "loadtest.example.com"
LOADTEST_EMAIL_PREFIX = "loadtest"
DEFAULT_PASSWORD = "LoadTest#2026"  # 统一密码（可用 --password 覆盖）

# ── 超时口径（秒）─────────────────────────────────────────────────────────
TIMEOUT_NORMAL = 30.0
TIMEOUT_SSE = 120.0
TIMEOUT_PDF = 180.0

# ── 保险丝默认值 ──────────────────────────────────────────────────────────
DEFAULT_MAX_CHAT_MESSAGES = 500  # chat_sse 全场景总 LLM 消息数上限（控 token 成本）
PDF_MAX_CONCURRENCY = 3  # pdf_render 并发硬上限（防打挂渲染进程）

# chat_sse 每轮迭代发送的极短消息（values 阶段，2-3 条）
CHAT_MESSAGES = ["你好", "我喜欢帮助别人", "我在意自由和创造"]

# SSE 终止事件：done=正常结束；error=失败；retrying=空回复自动重试（继续等待）
SSE_DONE_KEY = "done"
SSE_ERROR_KEY = "error"

logger = logging.getLogger("load_test")


# ══════════════════════════════════════════════════════════════════════════
# 指标收集
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class RequestRecord:
    """单条请求记录。"""

    latency_ms: float
    ok: bool
    status_code: Optional[int] = None
    error: Optional[str] = None  # 失败摘要（status + body 前 200 字符 / 异常信息）
    ttft_ms: Optional[float] = None  # chat_sse 专用：首个 SSE 数据块时间


@dataclass
class Bucket:
    """一档并发的指标桶（线程安全由 asyncio 单线程语义保证）。"""

    records: List[RequestRecord] = field(default_factory=list)
    error_samples: List[Dict[str, Any]] = field(default_factory=list)
    max_error_samples: int = 20

    def add(self, rec: RequestRecord) -> None:
        """记录一条请求结果；失败时保留摘要样本（最多 max_error_samples 条）。"""
        self.records.append(rec)
        if not rec.ok and len(self.error_samples) < self.max_error_samples:
            self.error_samples.append(
                {
                    "status_code": rec.status_code,
                    "error": (rec.error or "")[:200],
                    "latency_ms": round(rec.latency_ms, 1),
                }
            )


def percentile(sorted_vals: List[float], pct: float) -> float:
    """线性插值百分位。sorted_vals 必须已升序排序；空列表返回 0。"""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def summarize_bucket(
    bucket: Bucket, duration_s: float, concurrency: int, scenario: str
) -> Dict[str, Any]:
    """把指标桶聚合成一档的统计结果字典。"""
    lat = sorted(r.latency_ms for r in bucket.records)
    total = len(bucket.records)
    failed = sum(1 for r in bucket.records if not r.ok)
    ttft = sorted(r.ttft_ms for r in bucket.records if r.ttft_ms is not None)
    summary: Dict[str, Any] = {
        "scenario": scenario,
        "concurrency": concurrency,
        "duration_s": round(duration_s, 2),
        "requests": total,
        "succeeded": total - failed,
        "failed": failed,
        "error_rate": round(failed / total, 4) if total else 0.0,
        "throughput_rps": round(total / duration_s, 2) if duration_s > 0 else 0.0,
        "latency_ms": {
            "p50": round(percentile(lat, 50), 1),
            "p95": round(percentile(lat, 95), 1),
            "p99": round(percentile(lat, 99), 1),
            "max": round(lat[-1], 1) if lat else 0.0,
            "mean": round(statistics.fmean(lat), 1) if lat else 0.0,
        },
        "error_samples": bucket.error_samples,
    }
    if ttft:
        summary["ttft_ms"] = {
            "p50": round(percentile(ttft, 50), 1),
            "p95": round(percentile(ttft, 95), 1),
            "count": len(ttft),
        }
    return summary


# ══════════════════════════════════════════════════════════════════════════
# HTTP 辅助
# ══════════════════════════════════════════════════════════════════════════


def make_client(base_url: str, timeout: float) -> httpx.AsyncClient:
    """创建异步 HTTP 客户端（禁用代理环境变量干扰，连接复用交给调用方）。"""
    return httpx.AsyncClient(
        base_url=base_url.rstrip("/"),
        timeout=httpx.Timeout(timeout),
        trust_env=False,
        limits=httpx.Limits(max_connections=200, max_keepalive_connections=200),
    )


def auth_headers(token: str) -> Dict[str, str]:
    """构造 Bearer 鉴权头。"""
    return {"Authorization": f"Bearer {token}"}


async def api_login(client: httpx.AsyncClient, email: str, password: str) -> str:
    """登录并返回 access token。失败抛异常（含响应摘要）。

    响应包格式：{"code":200,"message":"...","data":{"token": ...}}
    """
    resp = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    if resp.status_code != 200:
        raise RuntimeError(f"登录失败 status={resp.status_code} body={resp.text[:200]}")
    body = resp.json()
    token = ((body or {}).get("data") or {}).get("token")
    if not token:
        raise RuntimeError(f"登录响应缺少 token: {resp.text[:200]}")
    return token


async def timed_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    bucket: Bucket,
    **kwargs: Any,
) -> Tuple[Optional[httpx.Response], float]:
    """执行一次普通 HTTP 请求并记录指标。返回 (响应或 None, 耗时 ms)。"""
    start = time.perf_counter()
    try:
        resp = await client.request(method, url, **kwargs)
        latency = (time.perf_counter() - start) * 1000
        ok = 200 <= resp.status_code < 300
        bucket.add(
            RequestRecord(
                latency_ms=latency,
                ok=ok,
                status_code=resp.status_code,
                error=None if ok else resp.text[:200],
            )
        )
        return resp, latency
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        bucket.add(
            RequestRecord(
                latency_ms=latency, ok=False, error=f"{type(e).__name__}: {e}"
            )
        )
        return None, latency


# ══════════════════════════════════════════════════════════════════════════
# SSE 消费
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class SseResult:
    """一次 SSE 流的消费结果。"""

    ok: bool
    ttft_ms: Optional[float] = None
    total_ms: float = 0.0
    status_code: Optional[int] = None
    error: Optional[str] = None
    trial_limited: bool = False  # 402 trial_limit_reached：账号轮数用尽，worker 应停止


async def consume_chat_sse(
    client: httpx.AsyncClient,
    token: str,
    payload: Dict[str, Any],
) -> SseResult:
    """消费一次 /simple-chat/message/stream SSE 流。

    事件格式（见 simple_chat_routes.py event_stream）：
    - 每行 ``data: {json}``；正文块 ``{"chunk": ...}``；思维链 ``{"think_chunk": ...}``
    - ``{"done": true, ...}`` 正常结束；``{"error": ...}`` 失败；
      ``{"retrying": true}`` 为空回复自动重试，继续等待。
    - TTFT 定义为首个 SSE data 事件到达时间。
    """
    start = time.perf_counter()
    ttft_ms: Optional[float] = None
    try:
        async with client.stream(
            "POST",
            "/api/v1/simple-chat/message/stream",
            json=payload,
            headers={**auth_headers(token), "Accept": "text/event-stream"},
            timeout=httpx.Timeout(TIMEOUT_SSE),
        ) as resp:
            if resp.status_code != 200:
                body = (await resp.aread()).decode("utf-8", errors="replace")
                total_ms = (time.perf_counter() - start) * 1000
                # 试用码 10 轮上限属预期拦截，标记后由上层优雅停止该 worker
                trial_limited = (
                    resp.status_code == 402 and "trial_" in body
                )
                return SseResult(
                    ok=False,
                    total_ms=total_ms,
                    status_code=resp.status_code,
                    error=body[:200],
                    trial_limited=trial_limited,
                )
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                if ttft_ms is None:
                    ttft_ms = (time.perf_counter() - start) * 1000
                data = line[len("data:") :].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    evt = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if SSE_ERROR_KEY in evt:
                    return SseResult(
                        ok=False,
                        ttft_ms=ttft_ms,
                        total_ms=(time.perf_counter() - start) * 1000,
                        status_code=200,
                        error=f"SSE error 事件: {str(evt.get('error'))[:200]}",
                    )
                if evt.get(SSE_DONE_KEY):
                    return SseResult(
                        ok=True,
                        ttft_ms=ttft_ms,
                        total_ms=(time.perf_counter() - start) * 1000,
                        status_code=200,
                    )
            # 连接关闭但未见 done：视为失败（流被截断）
            return SseResult(
                ok=False,
                ttft_ms=ttft_ms,
                total_ms=(time.perf_counter() - start) * 1000,
                status_code=200,
                error="SSE 流未收到 done 事件即关闭",
            )
    except Exception as e:
        return SseResult(
            ok=False,
            ttft_ms=ttft_ms,
            total_ms=(time.perf_counter() - start) * 1000,
            error=f"{type(e).__name__}: {e}",
        )


# ══════════════════════════════════════════════════════════════════════════
# 压测场景
# ══════════════════════════════════════════════════════════════════════════


@dataclass
class Account:
    """压测账号。"""

    email: str
    password: str
    user_id: str
    activation_code: str

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Account":
        return cls(
            email=d["email"],
            password=d["password"],
            user_id=d.get("user_id", ""),
            activation_code=d.get("activation_code", ""),
        )


class RunContext:
    """run 模式共享上下文：保险丝计数与停止标记。"""

    def __init__(self, max_requests: int = 0, max_chat_messages: int = 0) -> None:
        self.max_requests = max_requests  # 0 = 不限
        self.max_chat_messages = max_chat_messages  # 0 = 不限
        self.request_count = 0
        self.chat_message_count = 0
        self.chat_fuse_blown = False  # chat 消息保险丝触发后停止 chat_sse

    def allow_request(self) -> bool:
        """全局请求数保险丝。"""
        if self.max_requests and self.request_count >= self.max_requests:
            return False
        self.request_count += 1
        return True

    def allow_chat_message(self) -> bool:
        """chat_sse LLM 消息数保险丝（控 token 成本）。"""
        if self.chat_fuse_blown:
            return False
        if self.max_chat_messages and self.chat_message_count >= self.max_chat_messages:
            self.chat_fuse_blown = True
            logger.warning(
                "chat_sse 消息数达到保险丝上限 %d，停止该场景后续请求",
                self.max_chat_messages,
            )
            return False
        self.chat_message_count += 1
        return True


async def scenario_readonly(
    client: httpx.AsyncClient,
    account: Account,
    bucket: Bucket,
    ctx: RunContext,
    deadline: float,
) -> None:
    """readonly 场景 worker：循环执行 登录 → journeys → history（零 LLM token）。"""
    token: Optional[str] = None
    while time.perf_counter() < deadline:
        # token 失效或首次循环时重新登录（登录本身也计入指标）
        if token is None:
            if not ctx.allow_request():
                return
            start = time.perf_counter()
            try:
                token = await api_login(client, account.email, account.password)
                bucket.add(
                    RequestRecord(
                        latency_ms=(time.perf_counter() - start) * 1000,
                        ok=True,
                        status_code=200,
                    )
                )
            except Exception as e:
                bucket.add(
                    RequestRecord(
                        latency_ms=(time.perf_counter() - start) * 1000,
                        ok=False,
                        error=f"login: {e}",
                    )
                )
                await asyncio.sleep(0.5)  # 登录失败退避，防触发登录防爆破锁定
                continue

        if not ctx.allow_request():
            return
        resp, _ = await timed_request(
            client, "GET", "/api/v1/simple-auth/journeys", bucket,
            headers=auth_headers(token),
        )
        if resp is not None and resp.status_code == 401:
            token = None  # token 过期，下轮重新登录
            continue

        if not ctx.allow_request():
            return
        await timed_request(
            client,
            "GET",
            f"/api/v1/simple-chat/history?activation_code={account.activation_code}&phase=values",
            bucket,
            headers=auth_headers(token),
        )


async def scenario_chat_sse(
    client: httpx.AsyncClient,
    account: Account,
    bucket: Bucket,
    ctx: RunContext,
    deadline: float,
) -> None:
    """chat_sse 场景 worker：init(values) → 发 2-3 条极短消息，完整消费 SSE 流。

    成本控制：
    - 每条消息占用 ctx 保险丝额度，达到上限后全场景停止；
    - 试用码 values 阶段全 report 累计 10 轮用户消息后后端返回 402
      trial_limit_reached，此时该 worker 优雅退出（不计为服务器故障）。
    """
    try:
        token = await api_login(client, account.email, account.password)
    except Exception as e:
        bucket.add(RequestRecord(latency_ms=0, ok=False, error=f"login: {e}"))
        return

    while time.perf_counter() < deadline and not ctx.chat_fuse_blown:
        # 每轮迭代用新 thread_id（独立对话存储；init 首轮引导只在新 thread 触发一次）
        thread_id = str(uuid.uuid4())

        if not ctx.allow_request():
            return
        resp, _ = await timed_request(
            client,
            "POST",
            "/api/v1/simple-chat/init",
            bucket,
            json={
                "activation_code": account.activation_code,
                "phase": "values",
                "thread_id": thread_id,
                "locale": "zh",
            },
            headers=auth_headers(token),
        )
        if resp is None:
            continue
        if resp.status_code == 402:
            return  # 试用门控，worker 停止
        if resp.status_code != 200:
            continue  # init 失败已计入桶，跳过本轮消息

        for msg in CHAT_MESSAGES:
            if time.perf_counter() >= deadline or ctx.chat_fuse_blown:
                return
            if not ctx.allow_chat_message():
                return
            if not ctx.allow_request():
                return
            result = await consume_chat_sse(
                client,
                token,
                {
                    "activation_code": account.activation_code,
                    "phase": "values",
                    "message": msg,
                    "thread_id": thread_id,
                    "locale": "zh",
                },
            )
            bucket.add(
                RequestRecord(
                    latency_ms=result.total_ms,
                    ok=result.ok,
                    status_code=result.status_code,
                    error=result.error,
                    ttft_ms=result.ttft_ms,
                )
            )
            if result.trial_limited:
                return  # 该账号试用轮数用尽，优雅退出


async def scenario_pdf_render(
    client: httpx.AsyncClient,
    account: Account,
    bucket: Bucket,
    ctx: RunContext,
    deadline: float,
    report_id: str,
) -> None:
    """pdf_render 场景 worker：并发触发存量报告的 PDF 渲染端点（CPU 密集）。

    端点：POST /api/v1/export/report-pdf/{report_id}（异步触发 + 单轨锁）。
    缓存命中返回 status=ready（快路径），未命中 kick 后台渲染。
    注意：report 必须归属该压测账号的激活码（或账号为 super_admin），否则 403。
    """
    try:
        token = await api_login(client, account.email, account.password)
    except Exception as e:
        bucket.add(RequestRecord(latency_ms=0, ok=False, error=f"login: {e}"))
        return

    url = f"/api/v1/export/report-pdf/{report_id}"
    params = {"activation_code": account.activation_code}
    warned_403 = False
    while time.perf_counter() < deadline:
        if not ctx.allow_request():
            return
        start = time.perf_counter()
        try:
            resp = await client.post(
                url,
                params=params,
                headers=auth_headers(token),
                timeout=httpx.Timeout(TIMEOUT_PDF),
            )
            latency = (time.perf_counter() - start) * 1000
            # 触发语义：2xx（ready/generating/审核中）均视为成功；409（阶段未完成）
            # 与 403（无权访问）视为失败并给出提示
            ok = 200 <= resp.status_code < 300
            bucket.add(
                RequestRecord(
                    latency_ms=latency,
                    ok=ok,
                    status_code=resp.status_code,
                    error=None if ok else resp.text[:200],
                )
            )
            if resp.status_code == 403 and not warned_403:
                warned_403 = True
                logger.error(
                    "pdf_render 403：报告 %s 不归属账号 %s 的激活码。"
                    "请改用归属压测账号的报告，或在账号文件中使用 super_admin 账号",
                    report_id,
                    account.email,
                )
                return
            if resp.status_code == 409:
                logger.error(
                    "pdf_render 409：报告 %s 五阶段未完成，无法生成 PDF，场景终止",
                    report_id,
                )
                return
        except Exception as e:
            bucket.add(
                RequestRecord(
                    latency_ms=(time.perf_counter() - start) * 1000,
                    ok=False,
                    error=f"{type(e).__name__}: {e}",
                )
            )


# ══════════════════════════════════════════════════════════════════════════
# 梯度执行
# ══════════════════════════════════════════════════════════════════════════


async def run_rung(
    scenario: str,
    concurrency: int,
    duration_s: float,
    accounts: List[Account],
    ctx: RunContext,
    report_id: Optional[str] = None,
    base_url: str = "http://127.0.0.1:8000",
) -> Dict[str, Any]:
    """执行一档并发：N 个 worker 协程循环执行场景直到时间到。"""
    # pdf_render 并发硬上限（防打挂渲染进程）
    if scenario == "pdf_render":
        concurrency = min(concurrency, PDF_MAX_CONCURRENCY)

    bucket = Bucket()
    timeout = TIMEOUT_NORMAL
    if scenario == "chat_sse":
        timeout = TIMEOUT_SSE
    elif scenario == "pdf_render":
        timeout = TIMEOUT_PDF

    deadline = time.perf_counter() + duration_s
    start = time.perf_counter()
    async with make_client(base_url, timeout) as client:
        tasks = []
        for i in range(concurrency):
            account = accounts[i % len(accounts)]
            if scenario == "readonly":
                tasks.append(scenario_readonly(client, account, bucket, ctx, deadline))
            elif scenario == "chat_sse":
                tasks.append(scenario_chat_sse(client, account, bucket, ctx, deadline))
            elif scenario == "pdf_render":
                tasks.append(
                    scenario_pdf_render(
                        client, account, bucket, ctx, deadline, report_id or ""
                    )
                )
        await asyncio.gather(*tasks)
    actual_duration = time.perf_counter() - start
    return summarize_bucket(bucket, actual_duration, concurrency, scenario)


def print_rung_summary(summary: Dict[str, Any]) -> None:
    """在控制台打印一档结果（单行表格风格）。"""
    lat = summary["latency_ms"]
    ttft = summary.get("ttft_ms")
    ttft_str = (
        f" | TTFT p50 {ttft['p50']:.0f}ms p95 {ttft['p95']:.0f}ms" if ttft else ""
    )
    print(
        f"[{summary['scenario']}] 并发={summary['concurrency']:<3} "
        f"请求={summary['requests']:<6} 失败={summary['failed']:<5} "
        f"错误率={summary['error_rate'] * 100:5.1f}% "
        f"吞吐={summary['throughput_rps']:7.2f} req/s | "
        f"p50={lat['p50']:8.1f}ms p95={lat['p95']:8.1f}ms "
        f"p99={lat['p99']:8.1f}ms max={lat['max']:8.1f}ms{ttft_str}"
    )
    if summary["error_samples"]:
        sample = summary["error_samples"][0]
        print(
            f"  └─ 错误样本: status={sample['status_code']} "
            f"error={sample['error'][:150]}"
        )


async def probe_target(base_url: str) -> None:
    """探活目标服务；不可达则抛异常退出。"""
    try:
        async with make_client(base_url, 10.0) as client:
            resp = await client.get("/health")
            if resp.status_code != 200:
                raise RuntimeError(f"探活返回 status={resp.status_code}")
    except Exception as e:
        raise RuntimeError(
            f"目标 {base_url} 不可达（GET /health 失败: {e}）。"
            "请确认后端已启动（如 ./start.sh）"
        ) from e


def load_accounts(path: Path) -> List[Account]:
    """加载压测账号文件；不存在则报错退出。"""
    if not path.exists():
        raise RuntimeError(
            f"账号文件不存在: {path}。请先运行: python scripts/load_test.py --mode setup"
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    accounts = [Account.from_dict(d) for d in data.get("accounts", [])]
    if not accounts:
        raise RuntimeError(f"账号文件为空: {path}")
    return accounts


async def cmd_run(args: argparse.Namespace) -> None:
    """run 模式主流程：探活 → 按梯度压测 → 输出报告。"""
    base_url = args.base_url.rstrip("/")
    print(f"探活目标 {base_url} ...")
    await probe_target(base_url)
    print("探活成功")

    accounts = load_accounts(Path(args.accounts_file))
    print(f"加载压测账号 {len(accounts)} 个")

    scenarios: List[str] = []
    if args.scenario == "all":
        scenarios = ["readonly", "chat_sse", "pdf_render"]
    else:
        scenarios = [s.strip() for s in args.scenario.split(",") if s.strip()]

    if "pdf_render" in scenarios and not args.report_id:
        print("⚠️  未提供 --report-id，跳过 pdf_render 场景")
        scenarios = [s for s in scenarios if s != "pdf_render"]

    ladder = [int(x.strip()) for x in args.ladder.split(",") if x.strip()]
    ctx = RunContext(
        max_requests=args.max_requests, max_chat_messages=args.max_chat_messages
    )

    all_summaries: List[Dict[str, Any]] = []
    for scenario in scenarios:
        for concurrency in ladder:
            print(f"\n── 场景 {scenario} 并发档 {concurrency} 持续 {args.duration}s ──")
            summary = await run_rung(
                scenario=scenario,
                concurrency=concurrency,
                duration_s=args.duration,
                accounts=accounts,
                ctx=ctx,
                report_id=args.report_id,
                base_url=base_url,
            )
            print_rung_summary(summary)
            all_summaries.append(summary)
            # 档间短暂冷却，让服务器回收连接
            await asyncio.sleep(1)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result = {
        "base_url": base_url,
        "started_at": ts,
        "scenarios": scenarios,
        "ladder": ladder,
        "duration_per_rung_s": args.duration,
        "max_requests": args.max_requests or None,
        "max_chat_messages": args.max_chat_messages or None,
        "report_id": args.report_id,
        "summaries": all_summaries,
    }
    json_path = ROOT_DIR / "scripts" / f"load_test_result_{ts}.json"
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    md_path = ROOT_DIR / "scripts" / f"load_test_report_{ts}.md"
    md_path.write_text(render_markdown_report(result), encoding="utf-8")
    print(f"\n结果 JSON: {json_path}")
    print(f"Markdown 报告: {md_path}")


# ══════════════════════════════════════════════════════════════════════════
# 报告生成
# ══════════════════════════════════════════════════════════════════════════


def render_markdown_report(result: Dict[str, Any]) -> str:
    """渲染 Markdown 报告：每档表格 + 瓶颈结论。"""
    lines = [
        "# 压测报告",
        "",
        f"- 目标: `{result['base_url']}`",
        f"- 时间: {result['started_at']}",
        f"- 场景: {', '.join(result['scenarios'])}",
        f"- 并发梯度: {result['ladder']}，每档 {result['duration_per_rung_s']}s",
        f"- 保险丝: max_requests={result['max_requests'] or '不限'}, "
        f"max_chat_messages={result['max_chat_messages'] or '不限'}",
        "",
        "## 各档结果",
        "",
        "| 场景 | 并发 | 请求数 | 失败 | 错误率 | 吞吐(req/s) | p50(ms) | p95(ms) | p99(ms) | max(ms) | TTFT p50(ms) | TTFT p95(ms) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in result["summaries"]:
        lat = s["latency_ms"]
        ttft = s.get("ttft_ms") or {}
        lines.append(
            f"| {s['scenario']} | {s['concurrency']} | {s['requests']} | {s['failed']} "
            f"| {s['error_rate'] * 100:.1f}% | {s['throughput_rps']:.2f} "
            f"| {lat['p50']:.0f} | {lat['p95']:.0f} | {lat['p99']:.0f} | {lat['max']:.0f} "
            f"| {ttft.get('p50', '-')} | {ttft.get('p95', '-')} |"
        )

    # 瓶颈结论：按场景分组分析错误率与 p95 趋势
    lines += ["", "## 结论", ""]
    conclusions: List[str] = []
    by_scenario: Dict[str, List[Dict[str, Any]]] = {}
    for s in result["summaries"]:
        by_scenario.setdefault(s["scenario"], []).append(s)
    for scenario, rows in by_scenario.items():
        rows = sorted(rows, key=lambda r: r["concurrency"])
        prev_p95: Optional[float] = None
        bottleneck: Optional[str] = None
        for r in rows:
            p95 = r["latency_ms"]["p95"]
            if r["error_rate"] > 0.01:
                bottleneck = (
                    f"并发 {r['concurrency']} 档错误率 {r['error_rate'] * 100:.1f}% > 1%，"
                    f"视为瓶颈档"
                )
                break
            if prev_p95 and prev_p95 > 0 and p95 > prev_p95 * 2:
                bottleneck = (
                    f"并发 {r['concurrency']} 档 p95 {p95:.0f}ms 较上一档 "
                    f"{prev_p95:.0f}ms 翻倍以上，疑似达到处理能力拐点"
                )
                break
            prev_p95 = p95
        if bottleneck:
            conclusions.append(f"- **{scenario}**：⚠️ {bottleneck}")
        else:
            max_rps = max(r["throughput_rps"] for r in rows)
            conclusions.append(
                f"- **{scenario}**：梯度内未见明显瓶颈，峰值吞吐约 {max_rps:.2f} req/s"
            )
    lines += conclusions or ["- 无数据"]

    # 错误样本附录
    lines += ["", "## 错误样本（每档最多 20 条）", ""]
    any_sample = False
    for s in result["summaries"]:
        if not s["error_samples"]:
            continue
        any_sample = True
        lines.append(f"### {s['scenario']} 并发 {s['concurrency']}")
        lines.append("")
        for sample in s["error_samples"]:
            lines.append(
                f"- status={sample['status_code']} latency={sample['latency_ms']}ms "
                f"`{sample['error'][:150]}`"
            )
        lines.append("")
    if not any_sample:
        lines.append("无错误样本。")
    lines.append("")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════
# setup / teardown（直接 import 后端内部服务，需在目标机上运行）
# ══════════════════════════════════════════════════════════════════════════


def _import_backend() -> None:
    """把 src/backend 加入 sys.path，以便 import 后端 app 包。

    同时 chdir 到 src/backend：.env 里 DATABASE_URL=sqlite+aiosqlite:///./app.db
    是相对路径，后端实际运行目录是 src/backend（start.sh 会 cd 过去），
    不 chdir 的话会错误地连到项目根的 ./app.db（或新建一个空库）。
    """
    os.chdir(BACKEND_DIR)
    sys.path.insert(0, str(BACKEND_DIR))


def loadtest_email(index: int) -> str:
    """生成第 index 个压测账号邮箱（1 起）。"""
    return f"{LOADTEST_EMAIL_PREFIX}{index:03d}@{LOADTEST_EMAIL_DOMAIN}"


async def cmd_setup(args: argparse.Namespace) -> None:
    """setup：批量创建压测用户（email_verified=True）并发放试用激活码。

    绕过注册接口的原因：
    - 注册强制邮箱验证（假邮箱收不到验证邮件），这里直接置 email_verified=True；
    - 注册接口有 IP 频控（单 IP 5 次/小时），批量创建必然被拦。
    幂等：邮箱已存在的账号跳过创建并复用。
    """
    _import_backend()
    from sqlalchemy import select  # noqa: E402

    from app.models.database import AsyncSessionLocal  # noqa: E402
    from app.models.user import User  # noqa: E402
    from app.services.auth_service import AuthService  # noqa: E402
    from app.utils.trial_codes import (  # noqa: E402
        ensure_trial_code_for_user,
        list_owned_codes,
    )

    password = args.password or DEFAULT_PASSWORD
    password_hash = AuthService.get_password_hash(password)
    accounts: List[Dict[str, Any]] = []

    # 加载已有账号文件以支持幂等续建
    accounts_path = Path(args.accounts_file)
    if accounts_path.exists():
        try:
            accounts = json.loads(accounts_path.read_text(encoding="utf-8")).get(
                "accounts", []
            )
        except Exception:
            accounts = []

    async with AsyncSessionLocal() as db:
        for i in range(1, args.users + 1):
            email = loadtest_email(i)
            username = f"{LOADTEST_EMAIL_PREFIX}{i:03d}"
            existing = (
                await db.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if existing:
                user_id = existing.id
                print(f"[skip] {email} 已存在，复用 user_id={user_id}")
            else:
                user = User(
                    email=email,
                    username=username,
                    password_hash=password_hash,
                    is_active=True,
                    email_verified=True,  # 假邮箱无法走验证流程，直接置 True
                )
                db.add(user)
                await db.flush()
                user_id = user.id
                print(f"[create] {email} user_id={user_id}")

            # 发放试用码（幂等：名下已有可用码则 ensure 返回 None，再取已有码）
            user_dict = {"user_id": user_id, "email": email}
            rec = ensure_trial_code_for_user(user_dict)
            code = (rec.code if rec else None) or (
                list_owned_codes(user_id, email) or [None]
            )[0]
            if not code:
                print(f"[warn] {email} 未能获取试用激活码，跳过该账号")
                continue
            accounts.append(
                {
                    "email": email,
                    "password": password,
                    "user_id": user_id,
                    "activation_code": code,
                }
            )
        await db.commit()

    payload = {
        "created_at": datetime.now().isoformat(),
        "password": password,
        "accounts": accounts,
    }
    accounts_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n完成：{len(accounts)} 个账号已写入 {accounts_path}")


async def cmd_teardown(args: argparse.Namespace) -> None:
    """teardown：物理清除压测用户及其激活码/会话/报告，并删除账号文件。

    复用 AccountDeletionService.purge_account（三层物理清除：
    用户文件目录 + 名下激活码及会话目录 + DB 行），压测数据无需软删冷存。
    """
    _import_backend()
    from app.services.account_deletion_service import AccountDeletionService  # noqa: E402

    accounts_path = Path(args.accounts_file)
    if not accounts_path.exists():
        print(f"账号文件不存在: {accounts_path}，无需清理")
        return
    data = json.loads(accounts_path.read_text(encoding="utf-8"))
    accounts = data.get("accounts", [])

    purged = 0
    for acc in accounts:
        user_id = acc.get("user_id", "")
        email = acc.get("email", "")
        try:
            await AccountDeletionService.purge_account(user_id, email)
            purged += 1
            print(f"[purge] {email} user_id={user_id}")
        except Exception as e:
            print(f"[error] 清除 {email} 失败: {type(e).__name__}: {e}")

    accounts_path.unlink()
    print(f"\n完成：已清除 {purged}/{len(accounts)} 个账号，账号文件已删除")


# ══════════════════════════════════════════════════════════════════════════
# 入口
# ══════════════════════════════════════════════════════════════════════════


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="寻路·OpenLife 并发压测脚本（setup/run/teardown）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["setup", "run", "teardown"],
        help="运行模式",
    )
    parser.add_argument("--users", type=int, default=60, help="setup: 创建账号数量")
    parser.add_argument("--password", default=None, help=f"setup: 统一密码（默认 {DEFAULT_PASSWORD}）")
    parser.add_argument(
        "--accounts-file",
        default=str(DEFAULT_ACCOUNTS_FILE),
        help="压测账号文件路径（默认 scripts/load_test_accounts.json）",
    )
    parser.add_argument(
        "--base-url", default="http://127.0.0.1:8000", help="run: 目标后端地址"
    )
    parser.add_argument(
        "--scenario",
        default="readonly",
        help="run: 场景 readonly/chat_sse/pdf_render/all，逗号分隔可组合",
    )
    parser.add_argument(
        "--ladder", default="1,5,10,20,50", help="run: 并发梯度，逗号分隔"
    )
    parser.add_argument("--duration", type=float, default=30.0, help="run: 每档持续秒数")
    parser.add_argument("--report-id", default=None, help="run: pdf_render 场景的存量报告 ID")
    parser.add_argument(
        "--max-requests", type=int, default=0, help="run: 全局请求数保险丝（0=不限）"
    )
    parser.add_argument(
        "--max-chat-messages",
        type=int,
        default=DEFAULT_MAX_CHAT_MESSAGES,
        help=f"run: chat_sse 总 LLM 消息数保险丝（默认 {DEFAULT_MAX_CHAT_MESSAGES}，0=不限）",
    )
    return parser


def main() -> None:
    """脚本入口。"""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )
    args = build_parser().parse_args()
    # setup/teardown 会 chdir 到 src/backend（相对路径 DATABASE_URL 解析需要），
    # 提前把 accounts-file 转为绝对路径，避免相对路径在 chdir 后错位
    args.accounts_file = str(Path(args.accounts_file).resolve())
    if args.mode == "setup":
        asyncio.run(cmd_setup(args))
    elif args.mode == "teardown":
        asyncio.run(cmd_teardown(args))
    else:
        asyncio.run(cmd_run(args))


if __name__ == "__main__":
    main()
