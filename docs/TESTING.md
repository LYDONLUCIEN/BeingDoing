# 验证与已知基线问题

核查日期 2026-10-12。基线从 v1.8.0 用 git archive 导出到独立临时目录；clean 与基线使用同一 Python 3.12.14 环境、APP_ENV=test、独立测试密钥，没有复制生产数据库/用户数据。Node 本次实际为 26.0.0；目标部署 Node 需另行验收。

## 可复跑命令

根目录激活虚拟环境后：

```bash
PYTHONPATH=src/backend:. python -m test_agent.center.verify_backend --output output/backend-本次唯一名称
PYTHONPATH=src/backend:. python -m test_agent.center.verify_backend --output output/security-本次唯一名称 test/backend/test_security_boundaries.py test/backend/test_security_config.py test/backend/test_analytics_privacy.py test/backend/test_password_reset_sessions.py
black --check --config src/backend/pyproject.toml src/backend
isort --check-only --settings-path src/backend/pyproject.toml src/backend
```

前端目录运行 `npm run lint`、`npm run test:security`、`NEXT_TELEMETRY_DISABLED=1 npm run build`。渲染器目录运行 `npm test`。依赖审计：`python -m pip_audit`、前端 `npm audit`，结果需按可达条件人工判断。

2026-10-14 更正：全量后端使用上述独立副本入口，不能直接从共享工作区运行 pytest。旧测试未全部自带隔离；本轮误用默认 `app.db` 的执行问题及处理见下方追加记录。历史独立导出源码的结果仍有效。

## 2026-10-23 环境配置只读预检验证

- `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src/backend:. python -m pytest -p no:cacheprovider -q test/backend/test_check_env.py`：**23 passed**。覆盖合法 dev/prod/all、拒绝路径、stdin、显式路径隔离、退出码 0/1/2 和哨兵秘密不进入 stdout/stderr。
- `check_catalog` 在当前真实配置下先因生产有效配置缺少 Secure Cookie 而在 Settings 导入阶段中止；仅在当前进程临时设置 `REFRESH_COOKIE_SECURE=True`（未写回配置）后执行，结果 **coverage_gaps=[]、unknown_cases=[]**。这不是服务器配置已修复的证明。
- 用当前真实 env 运行 `--env all` 返回 1，只按变量名报告：覆盖层缺少显式团队邮箱/支付地址、生产缺少 Secure Cookie，且主签名、KIMI、SMTP、OSS 秘密在合并结果中相同；未输出配置值。真实 env 未修改。
- `git diff --check` 与 `git diff --cached --check` 通过；两个新 Python 文件人工检查 100 列通过。当前环境没有 black/isort 命令或模块，未执行这两项格式器检查；未运行全量后端、前端构建或真实外部服务验收。

## 2026-10-20 沉淀首开引导与 v3 老报告收口验证

- 独立后端入口：`verify_backend --output output/backend-legacy-v3-target-final-20261020-130402 test/backend/test_rumination_retirement.py test/backend/test_rumination_v4_e2e.py test/backend/test_rumination_v4_service.py`，**73 passed / 0 failed / 0 errors**。新增正反用例确认只有完整 v3 证据命中收口，任何 combo、终选草稿/提交、active 组合或离开 matrix 均不命中；intro/matrix 快照不算实质 v4 数据。
- 只读扫描本地 `data/simple/reports`：10 份含实质 v4 内容的报告均未命中收口；2 份完整 v3 老报告命中，包括 `df0b212f-7e59-44d6-890b-3dbcecbe3db8`。未修改真实数据。
- 浏览器 `rumination`：Chromium 在 360/390/430/820/1440 五个视口完成 **132 项断言**，证据 `output/rumination-legacy-redirect-20261020-083911`；`desktop` Chromium 完成 **60 项断言**，证据 `output/desktop-legacy-redirect-20261020-084325`。两个 runner 随后都因环境缺少 WebKit 可执行文件退出 1，WebKit 不能记为通过。
- 前端 `npm run lint`、`npm run test:security`（3/3）和 `npm run build` 均退出 0；lint 仅保留既有警告。
- `check_catalog` 对本项无未知用例；当前仍列出支付相关既有并发改动覆盖缺口，见命令输出，不属于本项路径。
- 全量后端入口已尝试：`output/backend-legacy-v3-report-redirect-20261020-125525` 在收集 `test/backend/test_test_center_workflow.py` 时因既有独立副本未复制 `test/__init__.py` 报 `ModuleNotFoundError: No module named 'test.backend'`，未能形成全量结果；不得写成全量通过。

## 2026-10-13 服务器手册的命令验证

[服务器操作手册](OPERATIONS.md) 的 22 段 Bash 通过 `bash -n`，3 段内嵌 Python 通过语法检查。临时目录中使用合成配置、SQLite 和 data，复制本仓库的 Settings／data_paths 模块到隔离目录，完成 **16 项行为检查**：相对／绝对 DB 定位，缺失库／内存库／非 SQLite／特殊 URI 拒绝，含 WAL 数据的 DB 与 JSON／环境文件备份，重复目标拒绝，dev／prod 环境覆盖与实际 Settings 校验，DB 路径变化拒绝，APP_ENV 不匹配和不安全生产配置拒绝。

只执行上述隔离片段；Conda／npm 安装、Git 发布切换、服务器启停、生产迁移、nginx 维护和公网业务验收未在服务器运行。语法检查不证明这些外部步骤已通过，本次没有运行全量产品测试或真实数据恢复。

## 2026-10-13 根目录整理的定向验证

本轮只整理根目录文档／图像及测试工具的清单路径，应用源码未改。执行 `PYTHONPATH=test/claude-test python -m pytest -c test/claude-test/pytest.ini test/claude-test/parser/test_md_parser.py -q`：**3 passed**；缺失清单不再被静默当作成功。

对比迁移前后的解析对象：标题、优先级和 **109 项清单内容完全一致**；验证工具默认路径可读取新位置。7 份归档文档移除新增范围提示后与原文逐字节一致，6 张 PNG 哈希不变；另外 23 个未编辑保留的根目录文件字节不变。没有运行带旧七步规则的历史业务清单、重放旧报告或连接真实服务。本轮检查不能替代下列产品回归及其未通过项。

检查 Wiki、现行 docs、根入口及本轮修改文档共 160 份：881 条本地链接目标有效，106 个固定 Git 来源存在；同步修复引用旧根评审的并发分析文档中的相对路径。`git diff --check` 通过。这是本次列明文档范围的文件目标检查，不是全仓历史链接、页内锚点或外部网站可用性验证。

## 第一轮结果（截至 5b461e6，历史快照）

| 检查 | 结果与范围 |
| --- | --- |
| 全量后端基线 | 978 passed，56 failed，6 errors |
| clean 第一轮全量 | 1030 passed，56 failed，6 errors；失败 ID 集合与基线完全相同，新增 52 项通过 |
| 新增安全用例独立运行 | 52 passed，覆盖权限、归属、配置、重置令牌和导出正反路径 |
| 前端安全行为 | 3 passed；实际 React 组件渲染，不是文本搜索断言 |
| 前端 lint | 退出 0，保留原有 Hook 依赖/原生 img 提示 |
| 前端 production build | 退出 0，路由编译及 TypeScript 检查通过 |
| 报告 renderer | 8 passed；修复 node --test 的目录参数兼容，并以合成 fixture 替代硬编码服务器私有报告路径；dist 重建无差异 |
| 新开发指南空库流程 | 在独立临时 SQLite 执行文档原命令，创建 38 表（含 alembic_version）、版本为 025_user_type_admin_note；重复运行拒绝且库文件字节不变；后续 upgrade head 成功 |
| 全量 Python 格式 | 原有大量格式债：首次 Black 检查 204 文件待调整；isort 也有既有失败。新增文件完整格式化，旧文件只格式化变更行/导入，避免全仓无关重排 |
| pip-audit | 133 包，2 个不同未修复公告（原输出 3 条含重复），适用条件见安全评估 |
| npm audit | bulk advisory 请求 ECONNRESET；未获得可靠完整结果，不能写成通过 |

第一轮后端失败不是新增，但也不等于可忽略。下方保留当时的基线失败ID；第二轮按明确退役范围删除专属测试，数量不可直接与第一轮作修复率比较。

## 第二轮结果：v3 退役与历史分离

| 检查 | 实测结果 |
| --- | --- |
| 退役前新增拒绝用例 | 19项先失败，实施后通过；后续扩充只读、输入提取、版本和后台跳转边界 |
| 退役/v4/后台/导出/提示词/试用定向回归 | 135 passed，包括26项退役边界用例；管理员跳转仅沙箱、保留原生组合，模拟资料不写生产根 |
| 全量后端 | **856 passed、44 failed、6 errors**；失败/错误ID共50项，全部属于第一轮既有失败，无新增ID |
| 前端 | lint退出0（既有警告保留）、3项安全行为通过、production build与TypeScript通过；最终修复后重新构建通过 |
| 历史对话统计脚本（额外） | 31 passed、5 failed；独立导出v1.8.0源码复跑为相同5个失败，涉及测试Namespace缺gap_threshold_minutes和旧聚合预期，无新增失败 |
| 源码与文档 | Python编译、git diff --check；本轮新增Markdown相对链接核对；历史ADR原文仅增加顶部状态说明 |

总用例数由1092变为906：随v3删除整文件/专属场景，同时补退役边界和原生导出回归。减少的12个失败对应下面条目，**是功能退役，不是修好12个缺陷**。其余50个失败/错误仍需处理；本次不静默skip、不修改其预期来制造全绿。没有连接真实模型、支付渠道或生产数据库进行最终验收。

```text
test/backend/test_prompt_catalog.py::test_catalog_rumination_step3_fixed_opening
test/backend/test_rumination_neg_gate.py::TestStep3HypothesisDef::test_collect_multiple_candidates
test/backend/test_rumination_neg_gate.py::TestStep3HypothesisDef::test_collect_one_candidate
test/backend/test_rumination_neg_gate.py::TestStep3HypothesisDef::test_collect_zero_candidates
test/backend/test_rumination_opening_chain.py::TestFixedOpeningIsolation::test_fixed_templates_contain_row_count_placeholder
test/backend/test_rumination_opening_chain.py::TestFixedOpeningIsolation::test_render_fixed_opening_uses_correct_template
test/backend/test_rumination_ops.py::TestRuminationStepAnchors::test_load_rumination_step_anchors_reads_metadata
test/backend/test_rumination_row_chat.py::test_build_row_chat_step3_adds_cursor_note
test/backend/test_rumination_step3_flow.py::TestStep3PromptCopyNoLegacyUi::test_step3_addon_no_legacy
test/backend/test_savepoint_replay_batch.py::test_savepoint_batch_cases[sp_rumination_opening_chat_5_entry]
test/backend/test_step3_hyp_candidate.py::TestFallbackTrigger::test_no_trigger_when_candidates_present
test/backend/test_step3_hyp_candidate.py::TestSanitizeHypCandidates::test_filters_guide_phrase
```

本轮未修改渲染器，第一轮8项renderer结果仍适用其未变源码；本轮新增导出测试验证原生v4快照无损复制、旧矩阵不合成终选、重用暂存目录不残留上一次v4数据。沙箱回退测试验证清除下游状态且源报告不变。复审补充schema1/2/3历史导出回归，九步记录的第8/9步及对话不截断；后台跳转使用真实双根激活码索引验证，避免替换manager掩盖集成问题。

## 2026-10-13 Wiki 整理的补充验证

本轮删除的旧 HTTP 回归脚本只服务已退役七步沉淀，正式 `test/` 未改。重新执行 `APP_ENV=test DEBUG=False .venv/bin/python -m pytest -q test/backend/test_rumination_retirement.py`：**26 passed、18 warnings**。本轮没有重跑全量后端或前端构建；前述全量结果仍为 2026-10-12 的记录。

Wiki 与现行文档 849 条本地链接、105 条固定 Git 来源通过；全部 235 项处置去向核对，保留的 PNG／HTML／人工 diff／历史迁移源码字节不变。21 个应用／脚本文件逐字节对照仅有 `wiki/开发文档/` → `wiki/历史开发记录/` 的资料路径变化，Python 语法及差异空白检查通过。旧计划目录中其他既有失效链接不在此验证通过的范围。

## 失败分类与处理次序

- core/agent、LLM：缺真实 API/DB 默认模型、计费预期与现有实现不一致，部分 tokenizer 初次下载受网络限制。先拆开离线契约测试与真实服务集成测试。
- ASR/Chroma：可选组件未装；音频不属于本次默认运行配置。
- 知识库：干净克隆缺部署侧 CSV 路径/内容。先用受控 fixture 固定离线输入。
- 旧 ConversationFileManager 测试：仍期待已经改变的方法/返回值，需要按当前存储契约修订，不能据此删除仍挂载的旧聊天路由。
- 两个数据库测试：旧建表/异步会话假设与当前依赖环境冲突，需隔离 fixture。
- v3 prompt/候选与回放：第一轮曾保留且存在旧断言失败；第二轮按 ADR-0025 退役，不再作为现行产品回归。当前四阶段/v4回归和历史只读边界分别验证，见下面退役清单。
- 6 个 real_history 错误：测试依赖未入库的真实历史文件。应脱敏转受控 fixture，而非依赖某台机器目录。

## 基线失败 ID（便于追踪）

```text
test/backend/core/agent/test_graph.py::test_agent_graph_basic_flow
test/backend/core/agent/test_graph.py::test_agent_graph_basic_flow_deepseek
test/backend/core/asr/test_openai_whisper.py::test_transcribe_success
test/backend/core/knowledge/test_loader.py::test_load_all
test/backend/core/knowledge/test_loader.py::test_load_interests
test/backend/core/knowledge/test_loader.py::test_load_strengths
test/backend/core/knowledge/test_loader.py::test_load_values
test/backend/core/knowledge/test_search.py::test_get_similar_examples
test/backend/core/knowledge/test_search.py::test_search_interests
test/backend/core/knowledge/test_search.py::test_search_questions
test/backend/core/knowledge/test_search.py::test_search_strengths
test/backend/core/knowledge/test_search.py::test_search_values
test/backend/core/knowledge/vector/test_factory.py::test_create_chroma_vector_store
test/backend/core/llmapi/test_factory.py::test_get_default_llm_provider
test/backend/core/llmapi/test_openai_provider.py::test_count_tokens
test/backend/core/llmapi/test_openai_provider.py::test_estimate_cost
test/backend/core/tts/test_openai_tts.py::test_synthesize_invalid_speed
test/backend/core/tts/test_openai_tts.py::test_synthesize_invalid_voice
test/backend/test_conversation_file_manager.py::test_add_message
test/backend/test_conversation_file_manager.py::test_delete_session
test/backend/test_conversation_file_manager.py::test_file_structure
test/backend/test_conversation_file_manager.py::test_get_all_categories
test/backend/test_conversation_file_manager.py::test_get_conversation_history
test/backend/test_conversation_file_manager.py::test_get_messages
test/backend/test_conversation_file_manager.py::test_get_messages_with_limit
test/backend/test_database.py::test_user_model_crud
test/backend/test_database_operations.py::test_question_db
test/backend/test_database_operations.py::test_user_db_create
test/backend/test_database_operations.py::test_user_db_get_by_email
test/backend/test_database_operations.py::test_user_profile_create
test/backend/test_profile_sync_bug.py::test_db_failure_does_not_write_json
test/backend/test_profile_sync_bug.py::test_save_basic_info_raises_on_db_failure
test/backend/test_profile_sync_bug.py::test_save_basic_info_updates_user_profile_immediately
test/backend/test_profile_sync_bug.py::test_save_empty_survey_still_persists
test/backend/test_prompt_catalog.py::test_catalog_rumination_step3_fixed_opening
test/backend/test_rumination_neg_gate.py::TestStep3HypothesisDef::test_collect_multiple_candidates
test/backend/test_rumination_neg_gate.py::TestStep3HypothesisDef::test_collect_one_candidate
test/backend/test_rumination_neg_gate.py::TestStep3HypothesisDef::test_collect_zero_candidates
test/backend/test_rumination_opening_chain.py::TestFixedOpeningIsolation::test_fixed_templates_contain_row_count_placeholder
test/backend/test_rumination_opening_chain.py::TestFixedOpeningIsolation::test_render_fixed_opening_uses_correct_template
test/backend/test_rumination_ops.py::TestRuminationStepAnchors::test_load_rumination_step_anchors_reads_metadata
test/backend/test_rumination_row_chat.py::test_build_row_chat_step3_adds_cursor_note
test/backend/test_rumination_step3_flow.py::TestStep3PromptCopyNoLegacyUi::test_step3_addon_no_legacy
test/backend/test_savepoint_replay_batch.py::test_savepoint_batch_cases[savepoint_snap_values_20260501_a]
test/backend/test_savepoint_replay_batch.py::test_savepoint_batch_cases[savepoint_snap_values_20260501_conclusion_card_error_show]
test/backend/test_savepoint_replay_batch.py::test_savepoint_batch_cases[savepoint_snap_values_20260501_conclusion_card_repo_right]
test/backend/test_savepoint_replay_batch.py::test_savepoint_batch_cases[savepoint_snap_values_20260501_conclusion_card_show]
test/backend/test_savepoint_replay_batch.py::test_savepoint_batch_cases[savepoint_snap_values_20260501_conclusion_reject]
test/backend/test_savepoint_replay_batch.py::test_savepoint_batch_cases[sp_rumination_opening_chat_5_entry]
test/backend/test_savepoint_replay_batch.py::test_savepoint_batch_cases[sp_strengths_dialogue_continue_2_2]
test/backend/test_savepoint_replay_batch.py::test_savepoint_batch_cases[sp_values_pending_continue_1_2]
test/backend/test_savepoint_replay_batch.py::test_savepoint_batch_cases[sp_values_reject_then_reopen_pending_then_confirm]
test/backend/test_simple_chat_pending_real_history.py::test_flow_1_load_real_pending_history
test/backend/test_simple_chat_pending_real_history.py::test_flow_2_pending_confirm_emit_card
test/backend/test_simple_chat_pending_real_history.py::test_flow_3_pending_rejected_then_continue_chat
test/backend/test_simple_chat_pending_real_history.py::test_flow_4_thread_complete_from_real_pending
test/backend/test_simple_chat_pending_real_history.py::test_flow_5_reopen_after_complete
test/backend/test_simple_chat_pending_real_history.py::test_flow_6_rejected_history_can_reenter_pending
test/backend/test_simple_chat_replay_cases.py::test_replay_case_single_continue
test/backend/test_simple_chat_replay_cases.py::test_replay_cases_batch_basic
test/backend/test_step3_hyp_candidate.py::TestFallbackTrigger::test_no_trigger_when_candidates_present
test/backend/test_step3_hyp_candidate.py::TestSanitizeHypCandidates::test_filters_guide_phrase
```

## 第三轮结果：注册验证前置与强制绑邮箱（ADR-0026，2026-10-13）

| 检查 | 实测结果 |
| --- | --- |
| 新增前置流程用例 | test_register_preverification.py 16 项全过（发码/验码/链接/轮询/ticket/强制绑定正反路径） |
| 存量验证路径回归 | test_register_email_verification.py 11 项全过（重发、验证发码、journeys 懒补发、IP 频控按新口径调整） |
| 认证相关定向回归 | login_lockout/password_reset/account_deletion/change_password/security_boundaries/trial_codes/refresh_token/email_error 共 110 项全过 |
| 全量后端 | **893 passed、32 failed**；失败 ID 全部是上方第一轮既有基线（knowledge/conversation_file_manager/database/profile_sync 等），无一与本次改动相关，无新增失败 ID（总数少于上轮因 llmapi/savepoint 等部分旧失败在当前工作区通过，未追查原因，不归功于本轮） |
| 前端 | `next build` 退出 0（含新增 /bind-email、/register-verify 路由，TypeScript 通过） |

未做真机 SMTP 收发与浏览器端到端验收，见下节。

## 第四轮结果：会话隔离修复（2026-10-13）

| 检查 | 实测结果 |
| --- | --- |
| 新增防护用例 | test_thread_complete_requires_conclusion.py 2 项先红后绿（无结论卡 complete→400 且不写 phase 级选择；有 pending 草案→200） |
| 全量后端 | **895 passed、32 failed**；失败 ID 与第三轮基线完全一致（含 flow_6 既有失败），无新增失败 |
| 前端 | lint 退出 0（仅既有警告）、test:security 3 passed、production build 退出 0（TypeScript 通过） |

本轮修复：phase 1-4 流式期间禁新建会话 + SSE 事件按 thread 归属丢弃；thread/complete 无结论卡 400 前置校验；rumination v4 流式状态按 combo 归属（streamingComboId）。未做浏览器端到端验收与线上历史污染数据清理。

## 第五轮结果：admin 会话列表/详情覆盖 v4 combo（2026-10-13）

| 检查 | 实测结果 |
| --- | --- |
| 新增用例 | test_admin_conversations_v4.py 4 项先红后绿（列表补枚举 combo、step 过滤、详情返回原文且 ts→created_at 归一化、非管理员 403） |
| 全量后端 | **899 passed、32 failed**；失败 ID 与第三/四轮基线逐一比对完全一致，无新增失败 |
| 真实数据只读验证 | P7XC7VEFDO 会话列表由 5 行变为 13 行（4 phase thread + 旧 rumination thread + 8 个 v4 combo）；combo_7 详情返回 15 条消息原文 |
| Python 格式 | 新增测试文件 black/isort 通过；admin.py 的 black/isort 告警均为既有格式债（非本次改动区域），未做无关重排 |

背景：v4 combo 只存 rumination_v4_progress.json、从不登记 record.json session_ids，admin 会话页整组漏行；本次在展示层补枚举/回退，未动数据模型。未做浏览器端页面验收。

## 上线前另行验证

实际 LLM 多阶段探索、SMTP 验证/重置、OSS 上传、真实渠道支付/退款、Chrome PDF、反向代理 SSE/刷新/限流及数据恢复未完成现场端到端验证。代码回归证据不能替代这些检查。

## 测试中心与手机首页阶段一（2026-10-14）

基线 `clean@942849c`，开发分支 `codex/mobile-test-center`。使用临时源码目录、独立 SQLite/JSON 与无真实密钥环境，未读取或恢复真实业务数据、未操作 dev/prod 服务器。开始时本机缺少锁文件已声明的 openpyxl，安装 3.1.5 后再执行基线。

| 检查 | 实测结果 |
| --- | --- |
| clean 隔离全量基线 | **896 passed、37 failed、6 errors**；不同于此前带历史本地环境的 899/32 记录，不能混用 |
| 阶段一全量后端 | **915 passed、37 failed、6 errors**；JUnit 按 classname/name 比较，失败及错误 ID 集合与本轮基线完全相同 |
| 新增公开接口/执行器回归 | **19 passed**；未执行不能通过、CLI 不用断言代替输入、管理员与生产门禁、固定修订、两次独立副本、取消、超时、tag 约束 |
| 独立 worker 核心 API | **258 passed**，8 个目录套件全部通过：账户 9、激活码 63、认证 46、聊天 5、券 28、订单 59、退款 29、测试中心 19 |
| 首页/手机导航 | **64 项断言通过**；Chromium/WebKit × 360/390/430/820/1440px；九条评价、无横向溢出、导航和登录门禁；已查看截图 |
| admin 页面 | **16 项断言通过**；两引擎桌面，输入/断言展示、选择运行、保留首次失败、常驻、归档/恢复 |
| 真实聊天页 | **14 项断言通过**；两引擎桌面，流式期间新建禁用、请求线程正确、结束后恢复、切换不串消息；真实页面配受控接口/模型 |
| 目标回复断言 | **8 项断言通过**；两引擎，用户输入/旧回复不命中，未完成及无目标轮次不能通过 |
| 前端检查 | lint 成功（保留既有 warning），test:security 3 passed，build 成功，含新 `/admin/test-center` 路由 |
| 语法/格式 | 变更 Python 均通过 Black/isort，L2 mjs 均通过 node --check；后端全量存量格式债保留（基线 Black 182、isort 112 个文件，本次修正被改的 main.py） |

红→绿证据：旧 BDD 占位/空场景初测 6 失败；L4 以两条用户消息推断成功与 replay 输入混用各 1 失败；首页 360px 初测只能访问 3/9 评价；独立加载试用/聊天测试暴露 simple_chat 循环导入。修正后均通过。浏览器夹具调试中的失败批次也保留，未用重跑覆盖。

第一阶段复用固定用例，没有把真实 AI、自然语言编写、生产快照同步、真机或支付外部渠道说成已验收。v1.8.0 后还有未登记的历史改动，目录检查会列出覆盖缺口，正式发布验收仍被阻止。原有 37 个失败及 6 个历史/环境错误未在本次顺带改写。

运行方式与结果语义见 [测试中心指南](TEST_CENTER.md)。本地详细证据保存在忽略目录 `output/test-center-stage1/`，生产发布仍需对应环境与同一构建验收。


## 手机完整用户流程阶段二（2026-10-14）

沿用阶段一分支和隔离基线。本次只改用户端布局、输入处理、页内草稿及固定浏览器用例，服务端仅扩充允许的固定 UI 套件名；没有修改真实用户数据、支付渠道或服务器配置。

| 检查 | 实测结果 |
| --- | --- |
| 前四阶段聊天 | **272 项断言通过**；Chromium/WebKit × 360/1440px 跑 values/strengths/interests/purpose；另外以 values 覆盖 390/430/820px。验证抽屉、输入法回车、缩小可视高度、流式新建禁用、会话归属、反馈入口 |
| 沉淀 v4 | **150 项断言通过**；两引擎 × 360/390/430/820/1440px。真实页面选择/新建两个组合、跨组合流式锁定与回复隔离、未发送/结论草稿隔离恢复、原文确认和终选；已查看选点/对话/终选截图 |
| 注册/个人空间/报告/支付 | **210 项断言通过**；两引擎五种宽度。错误验证码和未同意协议不能建号；注册传验证凭证；阶段/报告门禁；按所选旅程下载有效测试 PDF；审核中无下载入口；同意协议才下单、继续支付沿用原单、离开不取消、显式取消、根据服务端交付结果回跳 |
| 首页与导航回归 | **64 项断言通过**；两引擎五种宽度，手机同时启用触控模拟 |
| 全量后端 | **915 passed、37 failed、6 errors**；失败/错误的 43 个 ID 与阶段一 clean 隔离基线逐一比较一致，无新增 |
| 前端检查 | lint 通过（既有警告保留），test:security **3 passed**，生产 build 通过 |
| 格式/登记 | 变更 Python Black/isort 通过；全量既有格式债为 Black **181**、isort **111**；14 个固定套件全部能登记，未知套件 0；仍有 104 个从 v1.8.0 起的历史路径覆盖缺口，发布验收继续阻止 |

红→绿与回归发现：360px 聊天输入区被常驻侧栏挤窄；输入法回车选词触发发送；沉淀原来没有手机双面板；未发送草稿可能串到另一组合，桌面重排又会清空草稿。抽屉、输入保护和页级分组合草稿处理后通过。WebKit 的注册后连续跳转测试改为验证注册成功后在同一 context 的新页面检查后续流程，避免测试导航与探索入口的自动跳转竞态；各套件仍运行真实前端。

模型、邮件、订单渠道和报告内容由受控接口提供。本轮验证的是 UI 状态与接口契约，不代表真实 AI 质量、支付网关可用性、实际报告渲染、iPhone/Android 软键盘/输入法、系统 PDF 保存或生产数据一致性已验收。支付宝仍沿用已有 page.pay/二维码能力，同机扫码与真实支付回跳需真机/渠道验收；未新增微信支付或原生 App。

证据在忽略目录 `output/test-center-stage2/`：各套件的 results.json、截图、trace 和执行日志，以及全量后端/前端检查日志。阶段二已本地实现，未提交、未部署；阶段三的自然语言编写、真实 AI/v4 快照回放及生产脱敏副本导入仍未实现。

## 管理员用例编写与 AI 单轮回放阶段三（2026-10-14）

基于相同 `clean@942849c` 和 `codex/mobile-test-center` 工作区。控制库 v2 增加草稿、上下文、调用账本、人工复核；不更改业务数据库。新增测试使用临时源码/DB/文件，模型 HTTP 边界用可核验的受控响应，不发送真实模型请求。

| 检查 | 实测结果 |
| --- | --- |
| 新增公开 API / 执行报告 | **12 passed**：草稿→保存→固定修订；未知断言不可执行；AI 起点独立；真实 v4 服务创建两组合后只读取指定组合；只匹配本轮回复；重复重置；取消后已发用量记账；预算不足不调用；缺 usage 停止后续用例；非法语义判定待复核；人工复核追加；源码更新保留人工定义；缺专用凭据不能继承业务密钥；控制库不可嵌套进源码 |
| 独立 worker | `test-center` **19 passed**，新增 `test-center-authoring` **12 passed**；完成后执行数据丢弃，证据保留 |
| 管理员浏览器流程 | **28 项断言通过**，Chromium/WebKit 桌面 1440px；旧核心/归档/重跑流程，加模板编辑、未知断言拦截、保存 v4 上下文、选择 AI 用例、提交预算、逐次回复和复核 |
| 全量后端 | **927 passed、37 failed、6 errors**；按 JUnit classname/name 对比，失败/错误 43 个 ID 与 clean 隔离基线完全一致，无新增 |
| 前端 | lint 通过（既有警告保留）、安全渲染 **3 passed**、生产 build 通过 |
| 格式与登记 | 变更 Python Black/isort 通过；全量格式债仍为 Black **181**、isort **111**；15 个固定目录套件，未知用例 0；历史 104 个路径覆盖缺口继续阻止发布验收 |

红→绿证据：起初编译/上下文接口 404；原本用量未知仍继续调用后续用例；v4 导入原先使用了错误的 `id` 字段，以真实服务创建组合后暴露失败，改用业务 `combo_id`；控制目录放入源码会被递归纳入快照，现直接拒绝。上述拒绝与允许路径均已有回归。独立 worker 还暴露了控制根校验过宽、误拒绝不在快照范围内的 pytest 临时目录，已将拒绝范围限定为业务 data 和会被复制的源码目录，失败证据另存保留。前端构建发现事件函数 `useDraft` 被识别为 Hook，已改名为 `openDraft`。

AI 验收范围是**固定当前提示词的单轮回复测试**，不代表结论确认、后台判断、摘要重算或完整业务状态机的真实模型联调。API/UI 作者入口目前限定已登记模板；未知自然语言操作保留待澄清，不会自动执行任意生成代码。来源工作区预览是当前起点；手工回退历史须同时核对摘要和卡片状态。

未验收：真实模型质量/账单、模型配置与线上逐项一致、dev 部署、生产一致脱敏基准导入、真机及真实支付。生产样本仅能提高覆盖真实数据状态的机会，不能替代环境、外部渠道、并发和权限差异的验证。当前修改未提交/推送/部署。

证据保存于忽略目录 `output/test-center-stage3/`，包含公开 API/JUnit、独立 worker 记录、双浏览器截图/trace、后端全量与前端构建日志；配置和实际支持范围见 [测试中心](TEST_CENTER.md)。

## 历史用例库、连续回放与 PC 布局保护（2026-10-14 追加）

同一 clean 基线和未提交开发分支。用户确认普通 PC 100% 缩放体验优先；这轮移除沉淀按高度 760px 强制改变工作方式的判断，宽度不足才收起辅助面板，用户主动展开覆盖层。补齐历史用例与开发登记准则，独立/连续聊天历史 AI 模式及逐轮标准，UI 明确步骤组合。

| 检查 | 实测结果 |
| --- | --- |
| 历史规则细分用例 | **60 个目录用例，84 项底层检查通过**；默认均不新增核心。当前目录共 **77** 个定义，全部有目的与来源，来源路径存在；不是全历史功能覆盖声明 |
| 后端全量（独立副本入口） | **933 passed、37 failed、6 errors**；976 项，失败/错误 43 个 ID 与上一隔离基线完全一致，无新增、无跳过 |
| 桌面沉淀 | **120 项断言通过**；Chromium/WebKit，1440/1280/1024/820 宽 × 900/700/600 高；检查正常三栏、展开选择器、输入和按钮可见、窄窗口覆盖层开闭及草稿保持 |
| 沉淀完整浏览器流程 | **150 项断言通过**；两引擎 × 360/390/430/820/1440；组合创建/切换、流式隔离、卡片及终选 |
| 首页与桌面外观保护 | **68 项断言通过**；两引擎 × 五种宽度，完整评价与登录门禁；桌面分页活动标记保持原有 23×6，手机扩大触控区域不带到桌面 |
| 管理员页面 | **36 项断言通过**；两引擎桌面，目的/来源、独立/连续模式、编辑保存及一键当前筛选/核心 |
| 可编辑 UI 步骤 | 注册验证 **28 项断言通过**；两引擎 × 390/1440，真实填写/点击、错误验证码拒绝、协议未同意拒绝及指定步骤断言；另有导航场景 8 项通过 |
| 反向验证 | 故意把注册可用按钮写成「禁用」，执行器明确失败，未假通过；报告保留于 `registration-negative/` |
| 前端 | lint 通过（原有警告保留），安全渲染 **3 passed**，生产 build 通过 |
| 格式/登记 | 本轮变更的 11 个 Python 文件 Black/isort 检查通过；目录未知用例 **0**，历史业务源码路径覆盖缺口仍 **104**，发布验收继续阻止 |

红→绿：1440×700 的沉淀输入被旧高度堆叠规则挤出视口，改为内部滚动后通过；窄桌面新建草稿曾被 active-combo effect 立即收起，改为仅实际组合激活时收起。新增注册步骤先暴露错误 `/register` 路径（实际 `/auth/register`），真实浏览器又发现按瞬时 `count()` 选择定位器会漏掉异步出现的字段，改为可自动等待的候选定位器。首页桌面尺寸断言先在 820px 失败，随后将手机触控放大限定至窄视口，双引擎回归通过。未改动注册业务页面来满足测试。

**运行方式纠正与保留记录**：本轮第一次全量命令误用了默认本地 `app.db`，旧测试可能写入测试记录，产生额外 7 个重复数据失败（44 failed、6 errors、924 passed）。已向所有者说明，原本地库保留，未擅自删除/清理/恢复；没有连接 dev 或生产。错误执行日志及 JUnit 留在 `backend-shared-db-*`，不作为有效隔离回归结论。之后全量均复制源码至临时目录并独立建库；新增 `test_agent.center.verify_backend` 及行为测试，验证不会复制源 DB/`.env`、继承业务凭据或覆盖源库。贡献规范、开发手册与 AGENTS 已要求使用此入口。

AI 框架的新行为由公开 API/执行证据验证：原上下文不变、独立模式每项重置、连续模式承接当前组的前轮回复、组间重置、逐轮标准和目的进入判定。**实际模型未调用；结论确认/后台判断/摘要重算等业务状态推进仍未接入 AI 回放**，不能把连续聊天历史称为完整 AI 业务流程。已有 API/UI 规则测试也不能替代真实模型质量验证。

其他未完成项：通用自然语言自动编程（当前 API 为完整模板、UI 为明确步骤）、生产一致脱敏样本生成/导入/每例恢复链路、dev 部署与现场验收。浏览器矩阵验证的是 CSS 视口，没有模拟全部 Windows 系统缩放、浏览器菜单缩放、真机键盘与外部支付渠道；不承诺所有终端均已验收。当前所有修改仍未提交/推送/部署。

本轮证据在 `output/test-center-stage4/`：`final-backend/`、`final-baseline-comparison.json`、历史 JUnit、各浏览器套件结果/截图/trace，以及前端日志。更早隔离全量 931/932 通过记录保留，不覆盖最终新增测试后的 933 通过结果。


## 2026-10-14 AI 业务回放补齐（阶段五，本地未部署）

基线仍为 `clean@942849c`；此阶段在未提交功能工作区继续。产品的 `simple_chat/__init__.py` 已恢复为 clean 原文件，`main.py` 仅保留测试中心的模块导入与 router 注册两行；正常包初始化由测试工具遵循原顺序处理。本轮未修改用户端布局、业务状态机、普通业务 API、业务数据库 schema 或部署配置。逐项代码边界见 [测试中心](TEST_CENTER.md)。

| 检查 | 本轮结果 |
| --- | --- |
| 后端全量，独立源码/数据库/文件根 | **947 passed、37 failed、6 errors**，共 990 项，无跳过；43 个失败/错误 ID 与阶段四隔离基线完全一致 |
| 新业务回放集 | **13 项通过**：独立重复、真实确认/锁定/再聊聊、自然出卡、pending 对话判定、手动请求结论、30 轮摘要、终选/报告 Markdown、判定重试记账、未知用量、禁止共享工作区、预算不足、取消前/最后一次调用取消 |
| 最后格式调整后的定向验证 | 测试中心、用例编写及业务回放 **36 项全部通过**，新增/修改的 12 个测试中心 Python 文件通过 Black/isort |
| admin 浏览器验收 | **46 项断言通过**，Chromium/WebKit 1440 CSS px；增加结构化起点、业务步骤保存、预算文案和状态证据展开；修复旧批次查询覆盖当前结果，未采用强制点击隐藏失败 |
| 前端 | lint 退出 0（存量警告保留）、3 项安全测试通过、生产构建退出 0（含 TypeScript） |
| 目录登记 | 78 个固定用例；新增 `test-center-workflow` 与对应变更清单；104 个既有 tag 范围登记缺口、0 个未知用例 ID，发布验收仍被如实阻止 |
| 格式 | 本轮新增/修改的测试中心 Python 通过 Black/isort；后端全量仍有存量格式债。main.py 保留原格式，以所有者要求的最小产品改动为先，不为格式检查重排产品入口 |

证据：`output/test-center-stage5/backend-final/{results.xml,results.json,execution.log}`、`final-baseline-comparison.json`、`admin-browser-race-fix/results.json`、两引擎截图/trace、`frontend-build.log`、`frontend-lint.log`、`catalog.json`。`backend-full` 为补最后一次调用取消用例前的 989 项验证，最后以 `backend-final` 990 项为准；最后的纯 Black 格式调整另以 `final-targeted` 检查测试中心、编写与业务回放三个套件。

保留开发中失败证据：`compiler-red`（业务语法尚未支持）、`manual-red`（模型 JSON 参数适配未齐）、`capture-red`（缺结构化状态）、`budget-red`（预算停止状态分类）、`cancel-final-red`（最后一次调用取消被算作通过）；各对应实现完成后的定向/全量检查已通过。`admin-browser` 首次命令使用了错误套件名，未执行任何断言，不计验证；其后 `admin-browser-correct-suite` / `admin-browser-final` 捕获了批次切换时旧查询覆盖新结果的页面问题，修复后两引擎通过。保存全部失败，不用最终成功覆盖原证据。

模型仅在外部 IO 边界使用固定回复，结论/摘要/报告状态、重试及 HTTP 路由使用实际产品代码。没有发起真实模型请求，也没有连接 dev/prod；本轮不修改或清理共享本地 `app.db`。上一阶段误运行旧测试的问题及保留处理仍见上节，不能抹去该记录。

尚未验收：真实模型质量与供应商参数匹配、公网 SSE 时序/断网、完整生产快照恢复、多组合完整报告、真实 PDF 渲染及外部渠道。当前业务回放复制的是所选线程/组合和明确声明的前置状态，不是整库复刻；生产脱敏导入、通用自然语言自动编程和 dev 部署不因本次通过而宣称完成。

### 2026-10-14 · 生产副本自动验收工具

新增独立工具见 [使用与配置手册](SNAPSHOT_TESTING.md)。验证只使用合成 SQLite／聊天／报告；未读取本机真实业务数据或连接 dev/prod。生产副本 CLI 不挂载产品 API；本轮未改产品后端、前端 UI、数据库迁移或部署脚本。

| 验证 | 结果与范围 |
| --- | --- |
| 工具与测试中心定向检查 | 最终 **26 项通过**，其中快照工具 20 项；包含源端假名化、关联/格式/状态保真、凭据清理、未知字段拒绝、安全解包、实际 SSH 子进程边界替身、隔离写入/网络、按组重置、失败/跳过/零用例/超时与文件迁移检查 |
| 实际产品路径 | 合成 024 数据经过仓库真实 025 Alembic 迁移，当前 ORM/激活/报告读取和正常 token 鉴权的 `/auth/me` 通过；工具没有新增或替换用户产品接口 |
| 完整后端基线比较 | 工具最初 16 项加入后的全量 **1006 项：963 通过、37 失败、6 错误**；与上一轮 990 项的 43 个失败/错误节点完全一致，新增失败 0。随后补充的文件迁移/码格式用例及脱敏保真修正，以最终 26 项定向结果为准，不把较早全量记录改写成最终 1010 项全过 |
| CLI | 真实执行 init、doctor、keygen：配置生成、重复初始化拒绝、密钥 0600 权限通过；capture 的停写声明拒绝/合法路径由测试执行。doctor 未连接远端 |
| 格式与脚本 | 9 个新增 Python 文件通过 Black/isort；Shell 语法检查、git diff --check 通过 |
| 固定用例登记 | 新增 `snapshot-pipeline` 核心用例与变更关联；既有 104 个历史 tag 覆盖缺口、0 个未知 ID，仍如实阻止正式发布验收 |

证据：`output/snapshot-final-check/{results.json,results.xml,execution.log}`；完整基线 `output/snapshot-backend-final/` 和其中 `baseline-comparison.json`。开发中 red 记录保留：缺导出/迁移/采集入口、字段名/状态假名冲突、码格式未保持，以及一次测试预期将 23 字符误写为 22 后的修正。没有删除失败证据。

源码固定副本中的普通 API/UI 回归仍使用其既有夹具，独立报告；不把它们冒充全部使用生产旧数据。真实远端 SSH/账号权限、生产历史数据库与附件、外部 AI、支付/邮件渠道未验收。源快照一致性依赖操作者协调停写，自动文本假名化不代表彻底匿名，PDF/图片等二进制内容未自动导出。生产发布仍由所有者操作。

### 2026-10-14 · clean 合入前最终检查

所有者要求将上述功能更新到 `clean`。本次已获取远端，确认 `origin/clean` 仍为 `942849c`，与功能分支开发起点一致。前文“未提交”等表述保留各阶段当时的状态；本节记录最终代码的合入前验证，不表示已部署或已通过生产发布验收。

- 独立副本全量后端 **1010 项：967 passed、37 failed、6 errors、0 skipped**；与上一轮 1006 项结果逐一比较，43 个失败/错误节点完全一致，新增失败 0。
- 前端 lint、安全渲染测试（3 项）和生产构建均退出 0；存量 lint 警告保留。回复命中浏览器测试通过；首次启动被本机沙箱拒绝创建 Chromium 通信端口，取得执行权限后原测试通过，没有修改测试来绕过断言。
- 79 个固定用例，未知 ID 为 0；既有 104 个历史 tag 覆盖缺口仍使登记检查退出 1，不修改登记来制造通过。
- 39 个变更 Python 文件中，38 个通过 Black/isort；`main.py` 在远端基线和本次都未通过，继续只保留两行测试中心挂载改动。全量后端只读检查列出 Black 182 / isort 112 个存量格式问题，未作无关重排。Shell 语法及 `git diff --check` 通过。
- 提交范围不包含真实数据库、用户数据、密钥文件或本地验证产物；没有连接 dev/prod、执行真实迁移或改动发布脚本。

本轮证据在忽略目录 `output/clean-integration-20261014/`：`backend/{results.xml,results.json,execution.log}`、`baseline-comparison.json`、前端三项日志及汇总、格式日志、`catalog.json` 和 `reply-assertions.log`。

### 2026-10-14 · 首页窄屏阶段卡纵向排列

基于 `clean@beafa5b`，产品改动仅在首页 CSS 既有窄屏规则内：左图右文的五张卡按顺序纵向排列，首屏容器随内容自然增高。保留原设计和完整文案；不改普通桌面、业务接口、真实数据或其他页面。固定用例 `home-mobile` 和变更关联已更新。

- Chromium/WebKit × 320、360、390、430、600、720、721、820、1050、1051、1440px 共 22 个视口场景，**822 项断言通过**；含 360px 中英文、600px 鼠标窄窗口、全部九条评价、导航、登录门禁、逐卡点击、完整文案、页面滚动和底部提示不遮挡。
- 非窄屏首页与 `beafa5b` 原样式在相同浏览器页面比较：11 组的首屏/标题/卡片/图标/说明的坐标、尺寸、字体、颜色、背景和圆角完全一致。这是指定元素和浏览器的比较，不是所有设备的像素一致承诺。
- WebKit 名义 721px 的窗口扣除滚动条后 CSS 可用宽度为 715px，实际命中窄屏规则，因此属于预期改动范围，不计入非窄屏不变比较。断点行为按浏览器实际 media query 判定，不能直接把 `innerWidth` 当作同一宽度口径。
- 前端 lint、安全测试（3 项）与生产构建通过；首屏自然增高修正后另跑最终构建。固定目录仍为 79 个定义、0 个未知 ID；104 个既有历史覆盖缺口继续使目录检查退出 1。此次没有后端改动，未重新运行后端全量。

红→绿：旧样式在 320px 明确因阶段卡必须横滑而失败。初版纵向样式的截图暴露绝对定位首屏会隐藏内部滚动、底部提示覆盖文案；将窄屏容器改为正常文档流，并加入可见性/滚动/提示位置检查后通过。保留初次验证中 WebKit 断点口径不一致导致的测试失败记录，未改桌面产品样式来迎合测试。

证据保留于 `output/home-vertical-20261014/`：`red/`、`green/`、`final-browser/`、`inspection-final/` 及前端/目录日志。最终 `final/` 在修正截图的即时回顶后再次验证 822 项全部通过；普通产品滚动行为未修改。其他页面的横向区域仅调查，候选建议见 [讨论记录](MOBILE_AND_TEST_CENTER.md) 末节；未部署，真机触控和浏览器菜单缩放未作现场验收。


## 2026-10-18 · admin 主动退款与协商部分退款

本轮改动涉及退款状态机、订单交付竞态、admin 退款界面和数据库迁移 026，未连接真实支付渠道、邮件或生产数据库。用户侧退款入口保持移除。

| 检查 | 实测结果 |
| --- | --- |
| 退款/支付相关后端定向回归（独立源码、数据库和文件根） | **90 passed、0 failed、0 skipped**：退款服务/API、支付订单服务、026 迁移升级与回滚 |
| 相邻流程回归 | **33 passed、0 failed、0 skipped**：套餐/延期守卫、账户注销关单、admin 订单导出 |
| 新增行为 | 覆盖 pending 渠道已付未交付全退、paid 全退、未付拒绝、创建/审批双查单、交付竞态认领、驳回后恢复 pending、在途退款禁止关单、季度 admin 协商部分退、重复退款行拒绝、保留激活码与失败重试沿用选择 |
| admin 浏览器界面 | Chromium 1440px **27 项断言通过**；WebKit 未执行，因为本机缺少 Playwright WebKit 可执行文件，未将缺失环境记为通过 |
| 前端 | lint 通过（仅既有 warning）、安全渲染 **3 passed**、生产构建与 TypeScript 通过 |
| 固定用例目录 | `check_catalog` 通过，`coverage_gaps=[]`、`unknown_cases=[]` |
| 语法/差异 | 变更 Python `py_compile`、L2 mjs `node --check`、JSON 解析和 `git diff --check` 通过 |

补充运行 `test_test_center.py` 与 `test_snapshot_pipeline.py` 时：首次因根文件系统剩余空间不足 512 MiB 出现 15 项环境失败；清理本轮生成的隔离浏览器副本后重跑为 **111 passed、3 failed**。3 项均卡在既有快照运行时的 Alembic 导入环境（本地 `alembic/` 目录遮蔽/控制台依赖），与本次退款断言无关；本轮换了一个最小测试 env 直接验证 026 升级和回滚并通过。Black/isort 命令在当前环境不可用，未伪造格式检查结论。

证据：`output/refund-admin-final-relevant-4-20261018/`、`output/refund-admin-adjacent-20261018/`、`output/admin-refund-ui-final-2-20261018/artifacts/`、`output/refund-admin-backend-with-migration-2-20261018/`。真实支付宝退款、退款后渠道到账、生产数据迁移和 WebKit 仍需在对应环境验收。
