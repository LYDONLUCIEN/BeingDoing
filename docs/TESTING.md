# 验证与已知基线问题

核查日期 2026-10-12。基线从 v1.8.0 用 git archive 导出到独立临时目录；clean 与基线使用同一 Python 3.12.14 环境、APP_ENV=test、独立测试密钥，没有复制生产数据库/用户数据。Node 本次实际为 26.0.0；目标部署 Node 需另行验收。

## 可复跑命令

根目录激活虚拟环境后：

```bash
APP_ENV=test DEBUG=False python -m pytest test/backend
python -m pytest test/backend/test_security_boundaries.py test/backend/test_security_config.py test/backend/test_analytics_privacy.py test/backend/test_password_reset_sessions.py
black --check --config src/backend/pyproject.toml src/backend
isort --check-only --settings-path src/backend/pyproject.toml src/backend
```

前端目录运行 `npm run lint`、`npm run test:security`、`NEXT_TELEMETRY_DISABLED=1 npm run build`。渲染器目录运行 `npm test`。依赖审计：`python -m pip_audit`、前端 `npm audit`，结果需按可达条件人工判断。

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

## 上线前另行验证

实际 LLM 多阶段探索、SMTP 验证/重置、OSS 上传、真实渠道支付/退款、Chrome PDF、反向代理 SSE/刷新/限流及数据恢复未完成现场端到端验证。代码回归证据不能替代这些检查。
