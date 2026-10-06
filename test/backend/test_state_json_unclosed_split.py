"""未闭合 [STATE_JSON] 块解析测试（2026-10-05 用户气泡出现协议 JSON 事故修复）。

口径：
- 块未闭合但尾部 JSON 可完整解析（finish_reason=stop 漏写结束标记）：
  可见正文只留标记之前内容，状态对象照常返回（进度/结论卡不丢）；
- 块未闭合且 JSON 解析失败（max_tokens 截断）：正文只留标记之前内容，状态按无处理；
- 不再把整段原文当可见正文（那会落盘并经 done.response 盖回气泡）；
- /history 返回前对助手正文做同样的只读剥离（含生产已落盘脏数据）。
"""

from app.api.v1.simple_chat.stream_utils import split_visible_reply_and_state
from app.api.v1.simple_chat_routes import _strip_state_json_from_history_messages


# ---------------------------------------------------------------------------
# split_visible_reply_and_state
# ---------------------------------------------------------------------------

def test_no_marker_returns_raw_text():
    assert split_visible_reply_and_state("你好，我们继续聊聊。") == ("你好，我们继续聊聊。", None)


def test_closed_block_stripped_and_state_parsed():
    raw = "我们来看第 3 条经历。\n[STATE_JSON]\n{\"state\":\"continue\",\"draft\":null}\n[/STATE_JSON]"
    visible, state = split_visible_reply_and_state(raw)
    assert visible == "我们来看第 3 条经历。"
    assert state == {"state": "continue", "draft": None}


def test_closed_block_invalid_json_keeps_visible():
    raw = "正文在此。\n[STATE_JSON]\n{\"state\":\n[/STATE_JSON]"
    visible, state = split_visible_reply_and_state(raw)
    assert visible == "正文在此。"
    assert state is None


def test_unclosed_block_with_complete_json_recovered():
    """事故原始形态：finish_reason=stop，JSON 完整但缺 [/STATE_JSON]。"""
    raw = (
        "好的，已把第 2 条经历定为掌控感，我们来看第 3 条。\n\n"
        "[STATE_JSON]\n"
        '{"state":"continue","draft":null,"purpose_progress":{"current_index":2,'
        '"confirmed_rows":[{"experience":"帮上级理汇报材料","values":["被认可"]}],"completed":false}}'
    )
    visible, state = split_visible_reply_and_state(raw)
    # 协议块不得出现在可见正文
    assert "[STATE_JSON]" not in visible
    assert visible == "好的，已把第 2 条经历定为掌控感，我们来看第 3 条。"
    # 状态对象被抢救回来（进度可继续更新）
    assert state is not None
    assert state["state"] == "continue"
    assert state["purpose_progress"]["current_index"] == 2


def test_unclosed_block_with_broken_json_state_dropped():
    """max_tokens 截断：JSON 不完整，正文仍只留中文，状态按无。"""
    raw = "这是正常中文回复。\n[STATE_JSON]\n{\"state\":\"continue\",\"draft\":"
    visible, state = split_visible_reply_and_state(raw)
    assert visible == "这是正常中文回复。"
    assert state is None


def test_unclosed_block_empty_visible_returns_empty():
    """模型只输出了协议块：可见正文为空，交由上游空回复重试路径处理。"""
    raw = '[STATE_JSON]\n{"state":"continue","draft":null}'
    visible, state = split_visible_reply_and_state(raw)
    assert visible == ""
    assert state == {"state": "continue", "draft": None}


def test_unclosed_block_trailing_whitespace_after_json():
    raw = '中文。\n[STATE_JSON]\n{"state":"continue","draft":null}\n\n  '
    visible, state = split_visible_reply_and_state(raw)
    assert visible == "中文。"
    assert state == {"state": "continue", "draft": None}


# ---------------------------------------------------------------------------
# _strip_state_json_from_history_messages
# ---------------------------------------------------------------------------

def _msg(role: str, content: str) -> dict:
    return {"role": role, "content": content, "event": "assistant_reply"}


def test_history_strips_closed_block():
    msgs = [_msg("assistant", "正文。[STATE_JSON]\n{\"state\":\"continue\"}\n[/STATE_JSON]")]
    out = _strip_state_json_from_history_messages(msgs)
    assert out[0]["content"] == "正文。"


def test_history_strips_unclosed_block_prod_dirty_data():
    """生产 LZ3QRF8FH8 落盘形态：正文 + 未闭合块 + 完整 JSON。"""
    msgs = [
        _msg(
            "assistant",
            '已记录，接下来聊第 4 条。\n[STATE_JSON]\n'
            '{"state":"continue","draft":null,"purpose_progress":{"current_index":3,"confirmed_rows":[],"completed":false}}',
        )
    ]
    out = _strip_state_json_from_history_messages(msgs)
    assert "[STATE_JSON]" not in out[0]["content"]
    assert out[0]["content"] == "已记录，接下来聊第 4 条。"


def test_history_untouched_messages_keep_identity():
    """无协议块的消息不复制、原对象返回（省内存）；用户消息不动。"""
    assistant = _msg("assistant", "普通回复")
    user = _msg("user", "[STATE_JSON] 用户输入里出现标记也不动")
    out = _strip_state_json_from_history_messages([assistant, user])
    assert out[0] is assistant
    assert out[1] is user
    assert user["content"].startswith("[STATE_JSON]")


def test_history_cleaned_message_is_copy_not_mutation():
    msgs = [_msg("assistant", "正文。[STATE_JSON] {\"state\":\"continue\"}")]
    out = _strip_state_json_from_history_messages(msgs)
    assert out[0]["content"] == "正文。"
    # 原消息对象不被就地修改
    assert "[STATE_JSON]" in msgs[0]["content"]
