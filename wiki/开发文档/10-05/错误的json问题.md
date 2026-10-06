> **已于 2026-10-06 修复**，方案与结论见 [claude-completed-2026-10-06-未闭合STATE_JSON解析修复.md](../claude-completed-2026-10-06-未闭合STATE_JSON解析修复.md)。生产历史脏数据在 `/history` 返回时只读截断，刷新即恢复。

这个激活码在使命阶段有 3 轮把协议 JSON 直接写进了用户可见对话。提示词里确实禁止这么做，模型没按格式闭合，后端又把未闭合的块当成正文保存并覆盖到气泡上。

用户是 `LZ3QRF8FH8`（完整码，使命阶段线程）。漏出的是今天 18:01、18:02、18:03 这三轮（北京时间）。模型是 `deepseek-v4-flash`，`finish_reason=stop`，不是被 `max_tokens` 截断。每轮正文正常，末尾却是：

```text
[STATE_JSON]
{"state":"continue","draft":null,"purpose_progress":{...}}
```

没有结束标记 `[/STATE_JSON]`。同一次对话里，后面正常写了结束标记的轮次已被剥掉，用户看不到 JSON。价值观、优势、热爱三段没有这种情况。

提示词要求的是两件事：块必须包在 `[STATE_JSON]` 和 `[/STATE_JSON]` 之间，而且这块不能出现在给用户看的正文里。

```123:139:src/backend/app/api/v1/simple_chat/prompt_builder.py
[输出协议 - 必须遵守]
在你的自然语言回复末尾，追加如下块（严格 JSON）：
[STATE_JSON]
{"state":"continue|pending_ready","draft":{"summary":"...","keywords":["..."]}}
[/STATE_JSON]
...
【用户可见正文 - 硬性禁止】
- 不要在自然语言里提及本协议、隐藏块名称、state 取值英文名、或「JSON / 待确认草案 / 机器协议」等字眼。
```

使命阶段还额外要求每轮都在这个块里回传 `purpose_progress`（经历匹配进度）。这三轮模型在思维链里写了 “Let me update STATE_JSON progress”，然后输出了 JSON 就停了，结束标记没写。

流式过程中，过滤器会从 `[STATE_JSON]` 起把后面全部截掉，所以打字时用户先看到的是正常中文。流结束后，解析函数发现块没闭合，就把整段原文（含 JSON）当作可见正文：

```179:188:src/backend/app/api/v1/simple_chat/stream_utils.py
    if end < 0 or end <= start:
        # 块未闭合（典型原因：max_tokens 截断），此前静默返回导致不出卡且不可查
        logger.warning(...)
        return raw_text.strip(), None
```

这段原文会写入对话文件，并放进 SSE 的 `done.response`。前端收到 `done` 后用 `payload.response` 整段替换气泡内容，所以 JSON 会在回复结束时突然出现，刷新后也还在。


没闭合时不要一律报错重生成。这三轮的中文回复是好的，JSON 本身也完整，只缺结束标记。整轮作废会把用户已经看完的话扔掉，再生成一次内容还会变。

按坏的程度分三档处理：

1. **有 `[STATE_JSON]` 但没写 `[/STATE_JSON]`，后面的 JSON 能完整解析。** 这就是这次的情况（`finish_reason=stop`，对象是完整的）。剥掉标记之后的内容再落盘、再放进 `done.response`。进度照常更新。用户气泡保持流式时已经看到的那段中文。
2. **块被截断，JSON 解析失败。** 这才是现在注释里说的 `max_tokens` 截断。这时才值得重试一次，沿用现有「可见正文为空就原样重试」那条路。重试仍失败，再给前端现有的失败条，让用户点重新尝试。
3. **无论哪一档，原始协议块都不能写入对话，也不能出现在 `done.response` 里。** 现在流式过滤器已经从 `[STATE_JSON]` 起截断了，所以打字过程中用户看不到 JSON。漏出来是因为流结束后 `split_visible_reply_and_state` 发现没闭合，把整段原文当成可见正文，前端再用 `done.response` 覆盖气泡。

提示词已经要求闭合、并且禁止正文出现 JSON，flash 还是会漏写结束标记。再加一句禁止解决不了落盘覆盖。

另外，这三轮把 `purpose_progress` 放在了顶层、`draft` 为 `null`，而更新进度的代码只读 `draft.purpose_progress`。即便把未闭合块救回来，进度也不会前进，除非顶层这个字段也认。


JSON 第一次出现在**使命阶段第 7 轮用户发言之后**的助手回复里，接着第 8、第 9 轮也漏了。按北京时间是今天 18:01、18:02、18:03。前面价值观、优势、热爱都没有，使命阶段前 6 轮也没有。

这里的「轮」按用户发言计。使命阶段前面是这样走的：

1. 用户一次列出 5 段经历（带新人、给父母买新奇食物、帮上级理汇报材料、陪朋友过中秋、把好吃的分给同事）。
2. 第 1 条对上掌控感、被认可、被珍视。
3. 第 2 条先说「看到他们开心我也开心」。
4. 用户否定「被记挂的孩子 / 被珍视」。
5. 改口选「不焦虑」和「被认可」。
6. 又改口：父母那件事开心，是因为「我有能力、也有这份心」。助手提议改成**掌控感**，问他确认。
7. 用户回「确认」。助手把第 2 条定成掌控感，开始问第 3 条。**这条回复末尾第一次带上了没闭合的 `[STATE_JSON]`。**
8. 第 3 条：被认可、被上级信任、被需要。助手记成被认可 + 被珍视，转去问第 4 条，JSON 又漏出来。
9. 第 4 条：陪伴和被认可，没有自由。助手记成被珍视 + 被认可，转去问第 5 条，JSON 第三次漏出。

第 10 轮用户说第 5 条是「被珍视、被认可」之后，助手开始写使命总结，这条没有再带 JSON。后面两轮「认可」模型把块正确闭合了，正文里就被剥掉了。

以前几乎看不到，是因为模型之前根本没把这块写进回复。前 6 轮它只在思维链里计划要输出 `STATE_JSON`，真正发给用户的正文里没有这个标记，所以没有东西可漏。从第 7 轮「确认」开始，思维链改成 “Let me update STATE_JSON progress”，它才把标记和进度 JSON 写出来，但写完对象就停了，没有 `[/STATE_JSON]`。`finish_reason` 是 `stop`，不是被长度截断。

留存的轮次日志（9 月 23 日至今）里，模型写过 `[STATE_JSON]` 的有 96 次，92 次正常闭合并被剥掉。没闭合的只有 4 次，都是使命阶段、都是 `deepseek-v4-flash`、都是自己停住：今天这 3 次，加上 10 月 3 日另一个码 `RYITIGJ1CA` 的 1 次。所以不是这个用户的话触发了新逻辑，是 flash 在回传使命进度时偶尔漏写结束标记，而没闭合时后端会把整段协议当成正文留下。


改解析，不要靠重生成，也不要只改提示词。这 4 次漏出的 JSON 都是完整的，缺的只是结束标记。把没闭合的块从正文里拿掉，用户就看不到了。

改 `split_visible_reply_and_state`（`src/backend/app/api/v1/simple_chat/stream_utils.py`）。现在没找到 `[/STATE_JSON]` 时，它把整段原文当成可见正文返回，落盘和 `done.response` 都会带上 JSON。流式过滤器其实已经从 `[STATE_JSON]` 起截断了，所以只要落盘和 `done` 用同一套截断，气泡就不会在结束时被盖回去。

具体按块尾部分三种情况：

- **标记后面的 JSON 能完整解析**（这次就是这样，`finish_reason=stop`）。可见正文只留标记之前的中文，状态对象照常拿去更新进度和结论卡。不要重试。
- **标记后面的 JSON 解析失败**（真正被 `max_tokens` 截断）。可见正文仍然只留中文，状态当本轮没有。只有中文也是空的，才走现有的空回复重试。不要因为缺一个结束标记就把已经生成好的话扔掉。
- **没有 `[STATE_JSON]`**。保持现状，整段都是正文。

同一个函数还被断线时的部分落盘调用（约 6768 行）。改这一处，正常结束和中途断开都不会再把协议块写进对话。

还要顺手改一处协议对不齐，否则救回来的进度仍然写不进 metadata。提示词要求 `state=continue` 时 `draft` 必须是 `null`，同时又要求每轮把 `purpose_progress` 放进 `draft`。`draft` 是 `null` 时放不进去，flash 就把它写到顶层。更新代码只读 `draft.purpose_progress`：

```6991:6997:src/backend/app/api/v1/simple_chat_routes.py
            draft_raw = state_obj.get("draft")
            if isinstance(draft_raw, dict) and "purpose_progress" in draft_raw:
                ...
                    updated_prog = apply_progress_update(cur_prog, draft_raw["purpose_progress"])
```

顶层有 `purpose_progress` 时也要认。提示词改成一句话即可：`continue` 时 `draft` 为 `null`，`purpose_progress` 与 `draft` 同级，块必须以 `[/STATE_JSON]` 结束。这只是减少再发生，不能代替上面的截断。

已经写进 `LZ3QRF8FH8` 对话文件的那 3 条，改解析不会自动消失。历史接口返回前，对助手正文做一次同样的截断（从 `[STATE_JSON]` 起丢掉），刷新后这 3 条也会恢复成正常中文。