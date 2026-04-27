# 4-26 Rumination 逻辑修改手工回归脚本

## 测试目标

验证 4-26 的 rumination 调整在实际流程中符合预期：

1. rumination 阶段不再依赖 `STATE_JSON`。
2. rumination 阶段不再产生 pending 结论卡 / `dimension_conclusion`。
3. rumination 阶段不再依赖 `question_bank` 逻辑。
4. rumination 2/3/5/6 步否定反问闸门、step7 最终确认、过渡页跳转保持正常。
5. 非 rumination 阶段（values/strengths/interests/purpose）结论卡机制不受影响。

---

## 测试范围

- 前端：`/explore/chat/rumination` 页面交互。
- 后端：`/simple-chat/message`、`/simple-chat/message/stream`、`/simple-chat/rumination-*` 相关接口行为。
- 仅做手工回归，不改代码、不改配置。

---

## 前置准备

1. 使用一组可正常进入 rumination 的测试账号/激活码。
2. 至少准备两种测试会话：
   - A：全新进入 rumination 的会话。
   - B：历史 rumination 会话（最好含旧数据，便于验证 pending 清理）。
3. 打开浏览器开发者工具（Network + Console）。
4. 清理浏览器缓存可选（建议至少做一轮“无缓存”验证）。

---

## 回归用例

### 用例 1：rumination 首次进入开场正常

**步骤**

1. 进入 `rumination` 页面（新会话）。
2. 观察首条助手消息。

**预期**

- 有开场白（LLM 或兜底文案均可）。
- 不出现“结论卡待确认”相关 UI。
- Network 中无与 rumination 结论卡相关的插卡动作。

---

### 用例 2：step opening 正常（1~3 步）

**步骤**

1. 按顺序加载/提交 step1 到 step3。
2. 观察每一步左侧表格 + 右侧引导语。

**预期**

- 每步有对应 opening 引导。
- 表格列和可编辑列正确切换。
- 不出现结论卡或 pending 弹卡。

---

### 用例 3：否定反问闸门（step2）

**步骤**

1. 在 step2 人为标记若干 `不匹配` 后点击确认。

**预期**

- 返回闸门确认态（继续下一步 / 深入讨论）。
- 选择“深入讨论”后，右侧出现开场提示并进入 exploring。
- 选择“继续”后正常推进下一步。

---

### 用例 4：否定反问闸门（step3 自填假设）

**步骤**

1. step3 选“其他/自填”写入边界假设后点击确认。

**预期**

- 命中 step3 闸门（如检测到不合定义项）。
- 深入讨论与继续路径都可正常收敛。

---

### 用例 5：step4（价值过滤）无闸门但流程正常

**步骤**

1. 完成 step4 的“工作目的”选择（含部分 `都不符合`）。
2. 点击确认。

**预期**

- 不触发否定反问闸门（这是预期行为）。
- `都不符合` 行在后续过滤生效，流程可继续推进。

---

### 用例 6：否定反问闸门（step5）

**步骤**

1. step5 标记若干 `应该做` 后确认。

**预期**

- 命中闸门，流程同用例 3。
- 深聊结束后可回表修改并继续。

---

### 用例 7：否定反问闸门（step6）

**步骤**

1. step6 标记若干 `未来` 后确认。

**预期**

- 命中闸门，流程同用例 3。
- 继续推进时不出现结论卡。

---

### 用例 8：step7 最终确认与跳转

**步骤**

1. step7 选择 1~3 行并确认。
2. 完成后进入过渡页/解锁报告路径。

**预期**

- `next_action` 为 finalize 过渡相关动作。
- 不出现 `rumination_conclusion_insert` 路径。
- 页面行为以 transition/finalize 为主，不出现结论卡插入。

---

### 用例 9：rumination 聊天消息中不再受 `STATE_JSON` 影响

**步骤**

1. 在 rumination 任一步连续发送数条右侧聊天消息。
2. 观察 SSE chunk 与最终展示内容。

**预期**

- 回复正常展示。
- 不出现 pending 结论状态变更触发。
- 不出现 `dimension_conclusion` SSE 事件依赖行为。

---

### 用例 10：历史 rumination 线程 pending 清理验证

**步骤**

1. 打开历史 rumination 线程（优先选择可能带旧 metadata 的）。
2. 发送一条新消息触发后端主流程。

**预期**

- 不会自动补 pending 结论卡。
- 聊天继续正常，不阻塞输入。

---

### 用例 11：同步与流式边界一致

**步骤**

1. 用常规 UI 走流式路径验证（默认）。
2. 使用接口工具单独调用 `/simple-chat/message` 做一次 rumination 消息请求（如测试环境允许）。

**预期**

- 两条路由在 rumination 都不生成结论卡状态逻辑。
- 结果一致：自然对话 + 表格流程，不走 pending 卡。

---

### 用例 12：非 rumination 回归防回退

**步骤**

1. 在 values/strengths/interests/purpose 任一阶段完成一轮对话到可出卡状态。

**预期**

- 仍能正常走结论卡（pending/确认）逻辑。
- 证明本次修改未误伤其他阶段。

---

## 结果记录模板

| 用例 | 结果(PASS/FAIL) | 现象摘要 | 截图/请求ID |
|---|---|---|---|
| 1 |  |  |  |
| 2 |  |  |  |
| 3 |  |  |  |
| 4 |  |  |  |
| 5 |  |  |  |
| 6 |  |  |  |
| 7 |  |  |  |
| 8 |  |  |  |
| 9 |  |  |  |
| 10 |  |  |  |
| 11 |  |  |  |
| 12 |  |  |  |

---

## 通过标准（建议）

- 必须通过：1~11。
- 12 若失败，判定为高优先级回归（阻塞上线）。

---

## 自动化脚本与测试数据（文件化）

为确保“真实接口被调用 + 可复现”，本次补充了文件化脚本与 fixture：

- 脚本：`wiki/回归测试/scripts/run_rumination_regression.py`
- 配置模板：`wiki/回归测试/fixtures/rumination_regression_config.template.json`
- 场景数据：`wiki/回归测试/fixtures/rumination_scenarios.json`

### 作用说明

1. 脚本会读取场景文件，调用真实接口：
   - `GET /simple-chat/rumination-get-table`
   - `POST /simple-chat/rumination-table-submit`
   - `POST /simple-chat/message/stream`
   - `POST /simple-chat/message`
2. 场景通过文件定义“第几步、改哪些列、预期 next_action/neg_kind”。
3. 输出 JSON 报告，包含每个用例状态、接口耗时、关键返回字段，便于归档。

### 运行步骤

1. 复制配置模板并填写真实值：

```bash
cp "wiki/回归测试/fixtures/rumination_regression_config.template.json" \
   "wiki/回归测试/fixtures/rumination_regression_config.json"
```

2. 编辑 `rumination_regression_config.json`：
   - `base_url`：后端地址（含 `/api/v1` 前缀）
   - `auth_token`：Bearer token
   - `activation_code`：测试激活码
   - `thread_id`：可选（为空时走默认线程）

3. 执行脚本：

```bash
python "wiki/回归测试/scripts/run_rumination_regression.py" \
  --config "wiki/回归测试/fixtures/rumination_regression_config.json" \
  --scenarios "wiki/回归测试/fixtures/rumination_scenarios.json" \
  --output "wiki/回归测试/fixtures/rumination_regression_report.json"
```

### 判定标准（自动化）

- `scenario_results[].ok` 全部为 `true`
- `stream_sync_checks.stream.ok == true`
  - 不应出现 `dimension_conclusion` / `conclusion_loading`
- `stream_sync_checks.sync.ok == true`
  - `reply` 中不应包含 `[STATE_JSON]` 标记
- `overall_ok == true`

### 可按需扩展的场景字段

`rumination_scenarios.json` 中每个场景支持：

- `step`：要测试的 rumination 子步
- `mutations[]`：
  - `row_index`：修改第几行
  - `field`：列名（如 `匹配性`、`激情标记`、`现实标记`）
  - `value`：写入值
- `expect`：
  - `next_action`
  - `neg_kind`

> 说明：当前脚本不修改业务代码，只通过接口驱动流程；若接口鉴权失败，请先确认 token、激活码与环境地址。
