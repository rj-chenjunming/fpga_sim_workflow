"""S8k（SPEC-REV-18 §2）：会话日志 → 「人参与反馈次数」。

唯一判据在 `host/agent_backends/dsh_sdk.py`（会话日志的唯一解码者）。纪律：

- 只认 `source.kind == "user"`；其它来源（`time-context` / `system-reminder` / `runtime-context` / 缺 `source`）
  **一律不计**（不猜）；
- 去重键 `id` → 缺则 `rpcId`（同一条消息在 `agent/inbox/spliced` 与 `user/message` 各出现一次 ⇒ 只计 1）；
- 两个键都没有 ⇒ 不计，但 `skipped=N` 记进 `human_messages_basis`（宁可少算也不编数）；
- 源不可用 ⇒ 0（沿用 `availability="unavailable"`，界面不出数）。
"""
from __future__ import annotations

import json

import pytest

from host.agent_backends import dsh_sdk as SDK

BASIS = "source.kind=user,dedupe=id|rpcId,skipped=0"


def _human(mid: str, *, source_kind: str | None = "user", with_id: bool = True,
           rpc: str | None = None) -> dict:
    item: dict = {"role": "user", "content": [{"type": "text", "text": "值回复 ok"}]}
    source: dict = {}
    if source_kind is not None:
        source["kind"] = source_kind
    if source:
        source["rpcId"] = rpc or ("rpc-" + mid)
        item["source"] = source
    if with_id:
        item["id"] = mid
    return item


def _user_message(item, *, seq: int = 1) -> dict:
    return {"type": "user/message", "seq": seq, "time": 1770000000, "data": item}


def _spliced(items, *, seq: int = 0) -> dict:
    return {"type": "agent/inbox/spliced", "seq": seq, "time": 1770000000,
            "data": {"target": "next-turn", "start": 0, "inserted": items}}


def _parse(*events: dict) -> SDK.CompactionFacts:
    lines = [json.dumps({"type": "session", "id": "s-1"})]
    lines += [json.dumps(event) for event in events]
    return SDK.parse_session_log_lines(lines)


def test_single_human_message_counts_one():
    facts = _parse(_user_message(_human("m-1")))
    assert facts.human_messages == 1
    assert facts.human_messages_basis == BASIS


def test_spliced_and_user_message_with_same_id_count_once():
    """D3 旁路消息会先 spliced 进 inbox、再落成 user/message（同一条）⇒ 不得算两次。"""
    item = _human("m-1")
    facts = _parse(_spliced([item]), _user_message(item))
    assert facts.human_messages == 1
    assert facts.human_messages_basis == BASIS


def test_distinct_ids_count_separately():
    facts = _parse(_user_message(_human("m-1")), _user_message(_human("m-2"), seq=2))
    assert facts.human_messages == 2


@pytest.mark.parametrize("source_kind", [
    "time-context", "system-reminder", "runtime-context", "assistant", "",
])
def test_non_human_sources_are_not_counted(source_kind):
    """注入上下文不是人说的：`time-context`/`system-reminder`/`runtime-context` 一律不计。"""
    facts = _parse(_user_message(_human("m-1", source_kind=source_kind)))
    assert facts.human_messages == 0, source_kind


def test_missing_source_is_not_counted():
    facts = _parse(_user_message(_human("m-1", source_kind=None)))
    assert facts.human_messages == 0


def test_missing_id_falls_back_to_rpc_id():
    first = _human("m-1", with_id=False, rpc="rpc-shared")
    second = _human("m-2", with_id=False, rpc="rpc-shared")
    facts = _parse(_user_message(first), _user_message(second, seq=2))
    assert facts.human_messages == 1, "同一 rpcId 视为同一条（去重键 id → rpcId）"


def test_item_without_id_and_rpc_id_is_skipped_and_reported():
    loose = {"role": "user", "content": [{"type": "text", "text": "?"}],
             "source": {"kind": "user"}}
    facts = _parse(_user_message(_human("m-1")), _user_message(loose, seq=2))
    assert facts.human_messages == 1, "无 id/rpcId 的条目不得计数"
    assert facts.human_messages_basis == "source.kind=user,dedupe=id|rpcId,skipped=1"


def test_compaction_counts_are_unaffected_by_human_messages():
    summary = {"type": "compaction/summary", "seq": 5, "time": 1770000000,
               "data": {"compactionId": "c-1", "shadowedTokenCount": 10}}
    facts = _parse(_user_message(_human("m-1")), summary)
    assert (facts.count, facts.human_messages) == (1, 1)


def test_non_object_data_does_not_crash():
    facts = _parse({"type": "user/message", "seq": 1, "time": 1770000000, "data": "纯文本"})
    assert facts.human_messages == 0


def test_unavailable_source_has_no_human_count():
    facts = SDK.CompactionFacts.unavailable("zstd 不可用")
    assert facts.human_messages == 0
    assert facts.human_messages_basis is None, "不可用时不出数，也不给计数依据"
    assert facts.availability == SDK.AVAILABILITY_UNAVAILABLE


def test_negative_human_count_is_rejected():
    with pytest.raises(ValueError):
        SDK.CompactionFacts(availability=SDK.AVAILABILITY_OK, human_messages=-1)
