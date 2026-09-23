# LLM 场景分流配置（Admin 页）+ 外观/分流一键恢复默认

**完成日期**：2026-09-23
**分支**：newui
**关联测试**：`test/backend/test_llm_scene_config.py`（35 例）、`test/backend/test_llm_scene_model_split.py`（更新）

## 背景

2026-08-19 起模型按 `usage_context.scene` 分流：chat→flash 档、其余→pro 档（读 `.env` 的 `LLM_FLASH_MODEL`/`LLM_PRO_MODEL`）；thinking 只有全局布尔 `LLM_THINKING_ENABLED`，admin 无法调整。本次新增 admin 配置页，可按场景选档位与 thinking 开关，并为外观/分流两页补上「一键恢复默认并保存生效」。

**拍板决策**（grill 确认）：
1. 档位**固定映射**：flash→`deepseek-v4-flash`、pro→`deepseek-v4-pro`，不受 `.env` 覆盖影响（原 `.env` 已把 `LLM_FLASH_MODEL` 覆盖为 pro，导致前四轮实际在用 pro）
2. **默认值**：chat→flash、rumination/report→pro，thinking 全开（= 代码设计意图；**部署后前四轮 chat 即真正切到 v4-flash**）
3. 恢复默认 = **一键恢复并立即保存生效**（两页一致）
4. 独立新页面 `/admin/llm-scene`（导航「AI 模型分流」），与「Chat 外观配置」并列

**技术要点**：DeepSeek V4 关闭思维链的官方参数为 `extra_body={"thinking": {"type": "disabled"}}`（此前代码从未显式发送，V4 默认 thinking=on；开启时不发 temperature——思维链模式下该参数被静默忽略）。

## 架构

```
Admin UI (/admin/llm-scene)  ──复用 ol-chat-appearance-* 样式
    ↓ GET/PUT /api/v1/admin/llm-scene、POST .../reset（super admin）
api/v1/llm_scene.py（校验：场景限三、tier∈{flash,pro}、thinking 为 bool）
    ↓
data/admin_runtime_config.json 的 llm_scene_config 键（app.utils.admin_config，同 chat_appearance）
    ↓
core/llmapi/scene_config.py（默认值合并 / 档位映射 / thinking 判定）
    ├─ factory._scene_model()：三场景优先读配置（固定映射），team_analysis/unknown 仍走 .env
    └─ openai_provider._thinking_enabled()：三场景读配置，其余兜底 settings.LLM_THINKING_ENABLED
          └─ _apply_thinking_kwargs()（chat/chat_stream 共用）：
             开 → 不发 temperature；关(V4系) → temperature + extra_body thinking disabled
```

## 改动清单

**后端**
- 新增 `app/core/llmapi/scene_config.py`：`DEFAULT_LLM_SCENE_CONFIG`、`TIER_MODELS`、`get_llm_scene_config()`（逐场景与默认合并、脏值回落）、`get_scene_tier_model()`、`is_scene_thinking_enabled()`、`validate_scene_config()`
- 新增 `app/api/v1/llm_scene.py`：GET（合并默认视图）/ PUT（校验后以默认填齐落盘，幂等）/ reset（写回出厂默认）
- `app/main.py`：注册 llm_scene router
- `app/core/llmapi/factory.py::_scene_model()`：admin 配置优先，异常回退 .env 分流（原行为保留为兜底）
- `app/core/llmapi/openai_provider.py`：`_is_reasoning_model` 拆为 `_model_supports_thinking` + `_thinking_enabled`（读 usage_context 的 scene）+ `_apply_thinking_kwargs`；`chat()` 非流式不再无条件发 temperature（原发了也被 V4 忽略，现对齐 chat_stream 语义）
- `app/api/v1/chat_appearance.py`：固化 `DEFAULT_CHAT_APPEARANCE`（= 前端 `RECOMMENDED_CHAT_APPEARANCE` 14 字段，两处须同步）+ `POST /api/v1/admin/chat-appearance/reset`

**前端**
- 新增 `lib/api/llmScene.ts`（类型 + fetch/put/reset + `TIER_MODEL_NAMES` 展示映射）
- 新增 `app/(main)/admin/llm-scene/page.tsx`：三场景卡片（前四轮对话/沉淀对话/报告生成），档位 flash·快省 / pro·强慢 二选一 + 当前模型名展示，thinking 开/关 + 说明；保存即生效提示
- `app/(main)/admin/appearance/page.tsx`：`handleReset` 改调 reset 端点→`applyGlobalConfig(返回值)`，文案「恢复推荐」→「恢复默认」
- `lib/api/chatAppearance.ts`：补 `resetAdminChatAppearance()`
- `app/(main)/admin/layout.tsx`：导航加 `{ path: '/admin/llm-scene', icon: Shuffle, label: 'AI 模型分流' }`（model-config 之后）

## 行为变化（重要）

- **部署即生效**：`data/` 未保存过 `llm_scene_config` 时走默认 → 前四轮 chat 立即从 pro（.env 覆盖）切到 `deepseek-v4-flash` + thinking 开。若要维持全 pro，去 /admin/llm-scene 把前四轮改为 pro 保存即可。
- `.env` 的 `LLM_FLASH_MODEL`/`LLM_PRO_MODEL` 降级为**未覆盖场景**（team_analysis/unknown）兜底；`LLM_THINKING_ENABLED` 降级为未覆盖场景的 thinking 兜底。
- thinking 关闭后 `max_tokens` 只计正文（V4 thinking 模式下原含思维链），现有调用点上限（8192/65536）充足，未改。
- VIP1/VIP2 均为 deepseek（ADR-0008）故两档用户都按场景配置分流；非 deepseek 渠道（kimi/qwen）不走档位映射，thinking 走「模型不支持」分支（只发 temperature）。

## 验证

- `pytest test/backend/test_llm_scene_config.py test/backend/test_llm_scene_model_split.py` → 35 passed（默认合并/脏值回落/校验 400 分支/factory 固定映射压过 .env/未覆盖场景 .env 兜底/provider kwargs 四分支/路由读写+403+reset/外观 reset 落盘）
- 全量回归 950 passed / 56 failed——失败经 stash 对比确认为**存量问题**（tts/asr/knowledge/conversation_stats 等，与本次无关）
- `npm run lint` 无新增问题（仅存量 no-img-element warning）
- 真实服务冒烟：`/api/v1/admin/llm-scene` 无 token 401；真实 `data/` 下 chat→`deepseek-v4-flash`、rumination/report→`deepseek-v4-pro`、team_analysis→`deepseek-v4-pro`

## 回归风险与观察点

- 前四轮 chat 切 v4-flash 后注意空回复监控（2026-09-21 事故在 flash 上出现过「只吐思维链」，thinking 分流已统一处理；若复发可把 chat 场景 thinking 关或切回 pro）
- `chat()` 非流式在 thinking on 时不发 temperature——对 kimi/qwen 无影响（走 supports=False 分支照发）
