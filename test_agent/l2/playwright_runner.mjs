#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import yaml from "js-yaml";
import { chromium } from "playwright";

function parseArgs(argv) {
  const out = {
    scenario: "",
    baseUrl: "",
    backendUrl: "",
    activationCode: "",
    threadId: "",
    savepointId: "",
    headless: "true",
    timeoutMs: "30000",
  };
  for (let i = 2; i < argv.length; i += 1) {
    const k = argv[i];
    const v = argv[i + 1];
    if (k === "--scenario") out.scenario = v || "";
    if (k === "--base-url") out.baseUrl = v || "";
    if (k === "--backend-url") out.backendUrl = v || "";
    if (k === "--activation-code") out.activationCode = v || "";
    if (k === "--thread-id") out.threadId = v || "";
    if (k === "--savepoint-id") out.savepointId = v || "";
    if (k === "--headless") out.headless = v || "true";
    if (k === "--timeout-ms") out.timeoutMs = v || "30000";
  }
  return out;
}

function loadScenario(filePath) {
  const raw = fs.readFileSync(filePath, "utf8");
  const ext = path.extname(filePath).toLowerCase();
  if (ext === ".yaml" || ext === ".yml") {
    return yaml.load(raw) || {};
  }
  if (ext === ".json") {
    return JSON.parse(raw || "{}");
  }
  throw new Error("仅支持 .yaml/.yml/.json 场景文件");
}

function resolveUrl(baseUrl, maybeRelative) {
  if (!maybeRelative) return baseUrl;
  if (maybeRelative.startsWith("http://") || maybeRelative.startsWith("https://")) return maybeRelative;
  return `${baseUrl.replace(/\/+$/, "")}/${maybeRelative.replace(/^\/+/, "")}`;
}

function applyExploreQuery(rawUrl, activationCode, threadId) {
  if (!activationCode && !threadId) return rawUrl;
  const u = new URL(rawUrl);
  if (activationCode) u.searchParams.set("activation_code", activationCode);
  if (threadId) u.searchParams.set("thread_id", threadId);
  return u.toString();
}

async function firstVisible(page, selectors, timeoutMs) {
  for (const selector of selectors) {
    const loc = page.locator(selector).first();
    if ((await loc.count()) > 0) {
      try {
        await loc.waitFor({ state: "visible", timeout: Math.min(timeoutMs, 3000) });
        return loc;
      } catch {
        continue;
      }
    }
  }
  return null;
}

function readStepParam(step, key, fallback = undefined) {
  if (Object.prototype.hasOwnProperty.call(step, key)) return step[key];
  const p = step.params;
  if (p && typeof p === "object" && Object.prototype.hasOwnProperty.call(p, key)) {
    return p[key];
  }
  return fallback;
}

async function executeDomainTableEdit(page, payload, timeoutMs) {
  const row = Number.parseInt(String(payload.row || "1"), 10);
  const rowIdx = Number.isNaN(row) ? 0 : Math.max(0, row - 1);
  const field = String(payload.field || "").trim().toLowerCase();
  const value = String(payload.value || "").trim();
  if (!value) throw new Error("domain_action.table_edit 缺少 value");

  const rowLocatorCandidates = [
    ".rumination-table-widget tbody tr",
    ".rumination-beautiful-table-widget tbody tr",
    "table tbody tr",
  ];
  let rowLocator = null;
  for (const sel of rowLocatorCandidates) {
    const loc = page.locator(sel);
    const n = await loc.count();
    if (n > rowIdx) {
      rowLocator = loc.nth(rowIdx);
      break;
    }
  }
  if (!rowLocator) {
    throw new Error(`domain_action.table_edit 未找到第 ${row} 行`);
  }

  // 针对 hypothesis 字段优先走「填写假设」路径（select -> textarea）
  if (field === "hypothesis" || field === "hypothesis_confirmed" || field === "假设") {
    const select = rowLocator.locator("select").first();
    if ((await select.count()) > 0) {
      try {
        await select.selectOption({ value: "__rum_s3_fill__" }, { timeout: Math.min(timeoutMs, 3000) });
      } catch {
        // 若 value 不存在，尝试按可见文本选择
        await select.selectOption({ label: "填写假设" }, { timeout: Math.min(timeoutMs, 3000) });
      }
    }
    const area = rowLocator.locator("textarea").first();
    if ((await area.count()) > 0) {
      await area.fill(value, { timeout: timeoutMs });
      await page.locator("body").click({ position: { x: 8, y: 8 }, timeout: timeoutMs });
      return;
    }
  }

  const editable = await firstVisible(
    page,
    [
      ".rumination-table-widget tbody tr textarea",
      ".rumination-table-widget tbody tr input[type='text']",
      ".rumination-table-widget tbody tr input",
      "table tbody tr textarea",
      "table tbody tr input[type='text']",
      "table tbody tr input",
    ],
    timeoutMs
  );
  if (!editable) {
    throw new Error("domain_action.table_edit 未找到可编辑输入控件");
  }
  await editable.fill(value);
  await page.locator("body").click({ position: { x: 8, y: 8 }, timeout: timeoutMs });
}

async function run() {
  const args = parseArgs(process.argv);
  if (!args.scenario) {
    throw new Error("缺少 --scenario");
  }

  const scenarioPath = path.resolve(args.scenario);
  const scenario = loadScenario(scenarioPath);
  const scenarioId = String(scenario.id || "unnamed_scenario").trim();
  const data = typeof scenario.data === "object" && scenario.data ? scenario.data : {};
  const steps = Array.isArray(scenario.steps) ? scenario.steps : [];
  const assertions = typeof scenario.assertions === "object" && scenario.assertions ? scenario.assertions : {};

  const baseUrl = String(args.baseUrl || data.base_url || process.env.L2_BASE_URL || "http://127.0.0.1:3000");
  const backendUrl = String(
    args.backendUrl || data.backend_url || process.env.L2_BACKEND_URL || "http://127.0.0.1:8000"
  );
  const activationCode = String(args.activationCode || data.activation_code || "").trim();
  const savepointId = String(args.savepointId || data.savepoint_id || "").trim();
  const phase = String(data.phase || "values");
  let threadId = String(args.threadId || data.thread_id || "").trim();
  const timeoutMs = Number.parseInt(args.timeoutMs || "30000", 10);
  const headless = String(args.headless || "true").toLowerCase() !== "false";
  let startPhase = phase;

  const adminToken = process.env.L2_ADMIN_BEARER_TOKEN || process.env.L2_ADMIN_TOKEN || "";
  let savepointLoad = null;
  if (savepointId) {
    if (!activationCode) {
      throw new Error("使用 savepoint_id 时必须提供 data.activation_code");
    }
    if (!adminToken) {
      throw new Error(
        "触发 savepoint 自动加载时需要环境变量 L2_ADMIN_BEARER_TOKEN（或 L2_ADMIN_TOKEN）"
      );
    }
    const loadUrl = resolveUrl(backendUrl, "/api/v1/admin/savepoints/load");
    const resp = await fetch(loadUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${adminToken}`,
      },
      body: JSON.stringify({
        activation_code: activationCode,
        savepoint_id: savepointId,
      }),
    });
    const payload = await resp.json().catch(() => ({}));
    if (!resp.ok || Number(payload.code || 0) !== 200) {
      throw new Error(`savepoint load 失败: HTTP ${resp.status}, payload=${JSON.stringify(payload)}`);
    }
    const loaded = payload.data || {};
    if (loaded.loaded !== true) {
      throw new Error(`savepoint load 未成功: ${JSON.stringify(loaded)}`);
    }
    startPhase = String(loaded.phase || startPhase);
    threadId = String(loaded.thread_id || threadId);
    savepointLoad = {
      ok: true,
      activation_code: activationCode,
      savepoint_id: savepointId,
      phase: startPhase,
      thread_id: threadId || null,
    };
  }

  const defaultUrl = applyExploreQuery(
    resolveUrl(baseUrl, `/explore/chat/${startPhase}`),
    activationCode || null,
    threadId || null
  );

  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const root = path.resolve(scriptDir, "..", "..");
  const ts = new Date().toISOString().replace(/[:.]/g, "-");
  const artifactsDir = path.join(root, "test_agent", "reports", "artifacts", `${scenarioId}_${ts}`);
  fs.mkdirSync(artifactsDir, { recursive: true });
  const finalShot = path.join(artifactsDir, "final.png");
  const traceFile = path.join(artifactsDir, "trace.zip");

  const result = {
    scenario_id: scenarioId,
    engine: "playwright",
    phase: startPhase,
    backend_url: backendUrl,
    activation_code: activationCode || null,
    thread_id: threadId || null,
    savepoint_id: savepointId || null,
    savepoint_load: savepointLoad,
    base_url: baseUrl,
    start_url: defaultUrl,
    passed: false,
    steps_total: steps.length,
    steps_ok: 0,
    steps_failed: 0,
    assertion_failures: [],
    action_failures: [],
    artifacts: {
      final_screenshot: finalShot,
      trace: traceFile,
      artifacts_dir: artifactsDir,
    },
    elapsed_ms: 0,
  };

  const startedAt = Date.now();
  const browser = await chromium.launch({ headless });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  await context.tracing.start({ screenshots: true, snapshots: true, sources: true });

  let aiCount = 0;
  let firstError = "";
  try {
    await page.goto(defaultUrl, { waitUntil: "domcontentloaded", timeout: timeoutMs });
    try {
      await page.waitForLoadState("networkidle", { timeout: 5000 });
    } catch {}

    aiCount = await page.locator(".flow-msg-ai-content").count();

    for (const [idx, rawStep] of steps.entries()) {
      const step = typeof rawStep === "object" && rawStep ? rawStep : {};
      const action = String(step.action || "").trim();
      try {
        if (action === "goto") {
          const url = resolveUrl(baseUrl, String(readStepParam(step, "url", "") || ""));
          await page.goto(applyExploreQuery(url, activationCode || null, threadId || null), {
            waitUntil: "domcontentloaded",
            timeout: timeoutMs,
          });
        } else if (action === "chat_send") {
          const text = String(readStepParam(step, "text", "") || "").trim();
          if (!text) throw new Error("chat_send 缺少 text");
          const input = await firstVisible(
            page,
            ["textarea.flow-input-field", "textarea[placeholder*='想法']", "textarea"],
            timeoutMs
          );
          if (!input) throw new Error("未找到聊天输入框");
          await input.fill(text);
          const sendButton = await firstVisible(
            page,
            ["button.flow-send-btn[title='发送']", "button[title='发送']", "button.flow-send-btn"],
            timeoutMs
          );
          if (sendButton) {
            await sendButton.click();
          } else {
            await input.press("Enter");
          }
        } else if (action === "wait_for_ai") {
          const expectDelta = Number.parseInt(String(readStepParam(step, "delta", "1") || "1"), 10);
          const delta = Number.isNaN(expectDelta) ? 1 : expectDelta;
          await page.waitForFunction(
            ({ prev, delta: d }) =>
              document.querySelectorAll(".flow-msg-ai-content").length >= prev + d,
            { prev: aiCount, delta },
            { timeout: timeoutMs }
          );
          aiCount = await page.locator(".flow-msg-ai-content").count();
        } else if (action === "wait_ms") {
          const ms = Number.parseInt(String(readStepParam(step, "ms", "1000") || "1000"), 10);
          await page.waitForTimeout(Number.isNaN(ms) ? 1000 : ms);
        } else if (action === "screenshot") {
          const name = String(readStepParam(step, "name", `step_${idx + 1}.png`) || `step_${idx + 1}.png`).replace(
            /[^a-zA-Z0-9_.-]/g,
            "_"
          );
          await page.screenshot({ path: path.join(artifactsDir, name), fullPage: true });
        } else if (action === "click") {
          const selector = String(readStepParam(step, "selector", "") || "").trim();
          if (!selector) throw new Error("click 缺少 selector");
          await page.locator(selector).first().click({ timeout: timeoutMs });
        } else if (action === "fill") {
          const selector = String(readStepParam(step, "selector", "") || "").trim();
          const text = String(readStepParam(step, "text", "") || "");
          if (!selector) throw new Error("fill 缺少 selector");
          await page.locator(selector).first().fill(text, { timeout: timeoutMs });
        } else if (action === "assert_dom") {
          const selector = String(readStepParam(step, "selector", "") || "").trim();
          if (!selector) throw new Error("assert_dom 缺少 selector");
          await page.locator(selector).first().waitFor({ state: "visible", timeout: timeoutMs });
        } else if (action === "assert_text") {
          const txt = String(readStepParam(step, "text", "") || "").trim();
          if (!txt) throw new Error("assert_text 缺少 text");
          const bodyText = await page.locator("body").innerText();
          if (!bodyText.includes(txt)) {
            throw new Error(`页面未包含文本: ${txt}`);
          }
        } else if (action === "domain_action") {
          const name = String(readStepParam(step, "name", "") || "").trim();
          const payload = readStepParam(step, "payload", {});
          const payloadObj = payload && typeof payload === "object" ? payload : {};
          if (name === "table_edit") {
            await executeDomainTableEdit(page, payloadObj, timeoutMs);
          } else {
            throw new Error(`不支持的 domain_action: ${name || "(empty)"}`);
          }
        } else {
          throw new Error(`不支持的 action: ${action || "(empty)"}`);
        }
        result.steps_ok += 1;
      } catch (err) {
        result.steps_failed += 1;
        const msg = err instanceof Error ? err.message : String(err);
        result.action_failures.push({ step_index: idx, action, message: msg });
        if (!firstError) firstError = msg;
        break;
      }
    }

    const bodyText = await page.locator("body").innerText();
    if (typeof assertions.expected_hint === "string" && assertions.expected_hint.trim()) {
      if (!bodyText.includes(assertions.expected_hint.trim())) {
        result.assertion_failures.push(`expected_hint 未命中: ${assertions.expected_hint}`);
      }
    }
    if (Array.isArray(assertions.expected_keywords)) {
      for (const kw of assertions.expected_keywords) {
        const keyword = String(kw || "").trim();
        if (!keyword) continue;
        if (!bodyText.includes(keyword)) {
          result.assertion_failures.push(`expected_keywords 未命中: ${keyword}`);
        }
      }
    }
    if (Array.isArray(assertions.no_leak_tags)) {
      for (const tag of assertions.no_leak_tags) {
        const t = String(tag || "").trim();
        if (!t) continue;
        if (bodyText.includes(t)) {
          result.assertion_failures.push(`no_leak_tags 触发泄露: ${t}`);
        }
      }
    }
  } finally {
    try {
      await page.screenshot({ path: finalShot, fullPage: true });
    } catch {}
    try {
      await context.tracing.stop({ path: traceFile });
    } catch {}
    await context.close();
    await browser.close();
    result.elapsed_ms = Date.now() - startedAt;
  }

  const hasActionFailure = result.action_failures.length > 0;
  const hasAssertFailure = result.assertion_failures.length > 0;
  result.passed = !hasActionFailure && !hasAssertFailure;
  if (!result.passed && firstError) {
    result.error = firstError;
  }

  console.log("=== L2_PLAYWRIGHT_RESULT ===");
  console.log(JSON.stringify(result, null, 2));
  if (!result.passed) {
    process.exit(1);
  }
}

run().catch((err) => {
  const message = err instanceof Error ? err.message : String(err);
  console.log("=== L2_PLAYWRIGHT_RESULT ===");
  console.log(
    JSON.stringify(
      {
        engine: "playwright",
        passed: false,
        fatal_error: message,
      },
      null,
      2
    )
  );
  process.exit(1);
});
