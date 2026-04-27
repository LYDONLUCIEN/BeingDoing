#!/usr/bin/env python3
"""
Rumination regression runner (real API calls + file-driven fixtures).

Usage:
  python wiki/回归测试/scripts/run_rumination_regression.py \
    --config wiki/回归测试/fixtures/rumination_regression_config.json \
    --scenarios wiki/回归测试/fixtures/rumination_scenarios.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build_headers(token: str) -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token and not token.startswith("REPLACE_WITH_"):
        headers["Authorization"] = f"Bearer {token}"
    return headers


def http_json(
    method: str,
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any] | None = None,
) -> Tuple[int, Dict[str, Any], Dict[str, str], float]:
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url=url, method=method.upper(), headers=headers, data=data)
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            elapsed = time.time() - started
            parsed = json.loads(body) if body.strip() else {}
            return int(resp.status), parsed, dict(resp.headers), elapsed
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        elapsed = time.time() - started
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = {"raw": body}
        return int(e.code), parsed, dict(e.headers or {}), elapsed


def stream_sse(
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
) -> Tuple[int, List[Dict[str, Any]], float]:
    req = urllib.request.Request(
        url=url,
        method="POST",
        headers=headers,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
    )
    started = time.time()
    events: List[Dict[str, Any]] = []
    with urllib.request.urlopen(req, timeout=120) as resp:
        status = int(resp.status)
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            data_str = line[len("data:") :].strip()
            if not data_str:
                continue
            try:
                evt = json.loads(data_str)
            except Exception:
                evt = {"raw": data_str}
            events.append(evt)
            if evt.get("done") is True:
                break
    elapsed = time.time() - started
    return status, events, elapsed


def get_table(base_url: str, headers: Dict[str, str], activation_code: str, step: int) -> List[Dict[str, Any]]:
    q = urllib.parse.urlencode({"activation_code": activation_code, "step": step})
    url = f"{base_url}/simple-chat/rumination-get-table?{q}"
    status, body, _, _ = http_json("GET", url, headers)
    if status != 200:
        raise RuntimeError(f"rumination-get-table failed step={step} status={status} body={body}")
    rows = (((body or {}).get("data") or {}).get("table_widget") or {}).get("rows") or []
    if not isinstance(rows, list):
        raise RuntimeError(f"invalid rows type for step={step}: {type(rows)}")
    return rows


def apply_mutations(rows: List[Dict[str, Any]], mutations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = [dict(r) for r in rows]
    for m in mutations:
        idx = int(m["row_index"])
        field = str(m["field"])
        value = m["value"]
        if idx < 0 or idx >= len(out):
            raise RuntimeError(f"mutation row_index out of range: {idx} (rows={len(out)})")
        out[idx][field] = value
    return out


def run_scenario(
    base_url: str,
    headers: Dict[str, str],
    activation_code: str,
    thread_id: str,
    scenario: Dict[str, Any],
) -> Dict[str, Any]:
    sid = str(scenario["id"])
    step = int(scenario["step"])
    rows = get_table(base_url, headers, activation_code, step)
    edited = apply_mutations(rows, scenario.get("mutations") or [])
    payload = {
        "activation_code": activation_code,
        "thread_id": thread_id,
        "step": step,
        "table_data": edited,
    }
    url = f"{base_url}/simple-chat/rumination-table-submit"
    status, body, resp_headers, elapsed = http_json("POST", url, headers, payload)

    expected_action = (((scenario.get("expect") or {}).get("next_action")) or "").strip()
    expected_kind = (((scenario.get("expect") or {}).get("neg_kind")) or "").strip()
    got_data = (body or {}).get("data") or {}
    got_action = str(got_data.get("next_action") or "")
    got_kind = str(((got_data.get("neg_confirm") or {}).get("kind")) or "")
    ok = status == 200 and (not expected_action or got_action == expected_action) and (
        not expected_kind or got_kind == expected_kind
    )
    return {
        "scenario_id": sid,
        "status": status,
        "elapsed_s": round(elapsed, 3),
        "ok": ok,
        "expected_action": expected_action,
        "got_action": got_action,
        "expected_kind": expected_kind,
        "got_kind": got_kind,
        "response_code": body.get("code"),
        "response_message": body.get("message"),
        "x_request_id": resp_headers.get("X-Request-Id", ""),
    }


def run_stream_and_sync_checks(
    base_url: str,
    headers: Dict[str, str],
    activation_code: str,
    thread_id: str,
    locale: str,
    stream_message: str,
    sync_message: str,
) -> Dict[str, Any]:
    stream_payload = {
        "activation_code": activation_code,
        "phase": "rumination",
        "thread_id": thread_id,
        "locale": locale,
        "message": stream_message,
    }
    stream_url = f"{base_url}/simple-chat/message/stream"
    status_stream, events, elapsed_stream = stream_sse(stream_url, headers, stream_payload)
    has_dimension = any("dimension_conclusion" in e for e in events if isinstance(e, dict))
    has_loading = any(e.get("conclusion_loading") is True for e in events if isinstance(e, dict))
    stream_ok = status_stream == 200 and (not has_dimension) and (not has_loading)

    sync_payload = {
        "activation_code": activation_code,
        "phase": "rumination",
        "thread_id": thread_id,
        "locale": locale,
        "message": sync_message,
    }
    sync_url = f"{base_url}/simple-chat/message"
    status_sync, body_sync, _, elapsed_sync = http_json("POST", sync_url, headers, sync_payload)
    reply_text = str(((body_sync or {}).get("data") or {}).get("reply") or "")
    sync_ok = status_sync == 200 and ("[STATE_JSON]" not in reply_text) and ("[/STATE_JSON]" not in reply_text)

    return {
        "stream": {
            "status": status_stream,
            "elapsed_s": round(elapsed_stream, 3),
            "events_count": len(events),
            "has_dimension_conclusion_event": has_dimension,
            "has_conclusion_loading_event": has_loading,
            "ok": stream_ok,
        },
        "sync": {
            "status": status_sync,
            "elapsed_s": round(elapsed_sync, 3),
            "contains_state_json_marker": ("[STATE_JSON]" in reply_text or "[/STATE_JSON]" in reply_text),
            "reply_excerpt": reply_text[:200],
            "ok": sync_ok,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run rumination regression checks.")
    parser.add_argument("--config", required=True, help="Path to runtime config json.")
    parser.add_argument("--scenarios", required=True, help="Path to scenario json.")
    parser.add_argument("--output", default="", help="Optional output json report file.")
    args = parser.parse_args()

    config = load_json(Path(args.config))
    scenarios_data = load_json(Path(args.scenarios))
    scenarios = scenarios_data.get("scenarios") or []

    base_url = str(config.get("base_url", "")).rstrip("/")
    if not base_url:
        raise RuntimeError("config.base_url is required")
    activation_code = str(config.get("activation_code", "")).strip()
    if not activation_code:
        raise RuntimeError("config.activation_code is required")
    thread_id = str(config.get("thread_id", "")).strip()
    locale = str(config.get("locale", "zh")).strip() or "zh"
    token = str(config.get("auth_token", "")).strip()

    headers = build_headers(token)
    results: Dict[str, Any] = {
        "meta": {
            "base_url": base_url,
            "activation_code_masked": f"{activation_code[:4]}***{activation_code[-4:]}" if len(activation_code) >= 8 else "***",
            "thread_id": thread_id,
            "locale": locale,
            "ts": int(time.time()),
        },
        "scenario_results": [],
        "stream_sync_checks": {},
    }

    for sc in scenarios:
        res = run_scenario(base_url, headers, activation_code, thread_id, sc)
        results["scenario_results"].append(res)
        print(
            f"[SCENARIO] {res['scenario_id']}: status={res['status']} action={res['got_action']} "
            f"kind={res['got_kind']} ok={res['ok']}"
        )

    stream_message = str(config.get("stream_message", "请继续引导我完成这个步骤"))
    sync_message = str(config.get("sync_message", "请继续当前rumination流程"))
    checks = run_stream_and_sync_checks(
        base_url=base_url,
        headers=headers,
        activation_code=activation_code,
        thread_id=thread_id,
        locale=locale,
        stream_message=stream_message,
        sync_message=sync_message,
    )
    results["stream_sync_checks"] = checks
    print(
        "[STREAM] status={status} has_dimension={dim} has_loading={load} ok={ok}".format(
            status=checks["stream"]["status"],
            dim=checks["stream"]["has_dimension_conclusion_event"],
            load=checks["stream"]["has_conclusion_loading_event"],
            ok=checks["stream"]["ok"],
        )
    )
    print(
        "[SYNC] status={status} has_state_json={s} ok={ok}".format(
            status=checks["sync"]["status"],
            s=checks["sync"]["contains_state_json_marker"],
            ok=checks["sync"]["ok"],
        )
    )

    overall_ok = all(x.get("ok") for x in results["scenario_results"]) and checks["stream"]["ok"] and checks["sync"]["ok"]
    results["overall_ok"] = overall_ok

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[REPORT] written: {out_path}")
    else:
        print(json.dumps(results, ensure_ascii=False, indent=2))

    return 0 if overall_ok else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[FATAL] {exc}", file=sys.stderr)
        sys.exit(1)
