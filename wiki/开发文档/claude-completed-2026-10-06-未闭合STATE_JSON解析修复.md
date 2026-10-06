# claude-completed-2026-10-06 未闭合 STATE_JSON 解析修复（用户气泡出现协议 JSON）

对应事故分析：[10-05/错误的json问题.md](./10-05/错误的json问题.md)

## 结论（先答问题）

**修复前：问题仍会发生。** 2026-10-05 事故文档描述的缺陷对当时代码 100% 成立，文档提出的修复一项都没落地（`stream_utils.py` 最后一次提交是 2026-08-25，早于事故）。本次已按文档方案全部实施。

## 验证过程（grill-me 模式逐条核实）

| # | 文档论断 | 修复前代码 | 状态 |
|---|---|---|---|
| 1 | 未闭合块被当正文返回 | `stream_utils.py:179-188` `return raw_text.strip(), None` | ❌ 属实 |
| 2 | 污染文本落盘 + `done.response` 盖回气泡 | `simple_chat_routes.py:6988-6989` → 落盘 `:7011`、done `:7306` | ❌ 属实 |
| 3 | 断线部分落盘同病 | `:6769` | ❌ 属实 |
| 4 | 流式中用户看不到（首标记起截断） | `:6685-6711` 过滤器正常 | ✅ 与文档一致 |
| 5 | 前端只挡已闭合块 | `MessageContent.tsx:45` 正则要求成对标记 | ❌ 属实 |
| 6 | 刷新后 JSON 还在 | `/history` 原样返回磁盘 messages | ❌ 属实 |
| 7 | 提示词自相矛盾 | `prompt_builder.py` 规则2 vs `conclusion_card_payload.py` purpose_progress 在 draft 内 | ❌ 属实 |
| 8 | 进度只读 `draft.purpose_progress` | `simple_chat_routes.py:6992-6998` | ❌ 属实 |

本机数据佐证：`data/simple/reports/` 消息 content 中未闭合污染 0 条（4 条脏数据在生产机；本机命中的 `[STATE_JSON]` 都在 `think_content`，不进气泡）。

## 定稿决策（AskUserQuestion 确认）

1. **ROW_STATE_JSON 同类缺陷不修**：用户判断沉淀子步3已非现行 rumination 主流程。数据证实：子步流量仅存在于 2026-05～2026-07，8 月后归零（`_split_visible_reply_and_row_state` 未闭合同样漏，留作已知遗留）。
2. **生产 4 条脏数据**（LZ3QRF8FH8×3 + RYITIGJ1CA×1）：`/history` 返回时只读截断，不动磁盘。代价：按用户导出仍含 JSON（面向运营，可接受）。
3. `continue` 是模型协议块 `[STATE_JSON]` 的 state 取值（continue=继续对话 / pending_ready=弹结论卡），非前端按钮；强调它是因为提示词规则2（continue→draft=null）与使命阶段要求（purpose_progress 放 draft 内）矛盾，是 flash 把进度写到顶层的根因。

## 改动清单

### 1. `src/backend/app/api/v1/simple_chat/stream_utils.py` — 核心

`split_visible_reply_and_state` 未闭合分支（原 179-188）重写：
- 可见正文一律只留 `[STATE_JSON]` **之前**的内容（与流式过滤器同口径）；
- 尾部 JSON 能完整解析 → 照常返回 state 对象（进度/结论卡正常推进，不重试、不弃轮）；
- 解析失败（真 max_tokens 截断）→ state 为 None；正文为空才走上游现有空回复重试；
- 不再把整段原文当正文（根除落盘 + done.response 两条污染路径）。

自动受益的调用点：主 done 路径、断线部分落盘（`:6769`）、两处初始化（`:4497`/`:4735`）。

### 2. `src/backend/app/api/v1/simple_chat_routes.py`

- 使命进度更新（原 6991-7005）：`draft.purpose_progress` 之外，**顶层 `purpose_progress` 也认**（draft 内优先）。
- 新增 `_strip_state_json_from_history_messages`：`/history` 返回前剥离助手正文协议块（已闭合整块删、未闭合从标记截断），只读清洗不改磁盘、不改原消息对象（复制修改）。生产 4 条脏数据刷新即恢复。

### 3. 提示词对齐（减少复发，不替代解析修复）

- `prompt_builder.py`：块头加「必须以 `[/STATE_JSON]` 结束」；规则2 改为「continue 时 draft=null，purpose_progress 放在与 draft 同级的顶层」。
- `conclusion_card_payload.py`：purpose_progress 从规则4（pending_ready draft 扩展）移出，独立为规则7：顶层、每轮必回传。
- `utils/purpose_progress.py` 注入块：补「与 draft 同级的顶层」位置说明。

## 测试

新增 `test/backend/test_state_json_unclosed_split.py`（11 用例，全过）：
- 解析：无标记 / 闭合+合法 / 闭合+非法 / **未闭合+完整 JSON（事故原始形态，正文纯净+状态抢救）** / 未闭合+截断 JSON / 未闭合+空正文 / 尾随空白；
- 历史清洗：闭合剥离 / 未闭合截断（生产脏数据形态）/ 无关消息不动且保对象身份 / 清洗为复制不就地改。

回归：
- 相关链路（空回复重试、结论卡轮数门、history 空线程）全过；
- 全量 `test/backend`：955 passed / 42 failed——**42 个在干净 HEAD 上逐条比对完全一致**（存量：knowledge CSV 缺失、db 环境类、沉淀 step3 遗留、payment 等，与本次无关；另 `test_prompt_catalog` 子步3 opening_mode、`core/agent` 需要 LLM key 两处存量失败未计入）。

## 遗留与风险

- 生产需重启后端生效；4 条脏数据在用户刷新后自动恢复显示（磁盘未动）。
- 按用户全量导出仍会包含历史协议 JSON（只修了展示层）。
- `_split_visible_reply_and_row_state`（沉淀子步3）存在同类未闭合缺陷，因子步已停用（2026-07 后无流量）明确不修；若未来重启子步3需一并处理。
