"""Host 闸门逐条处置落账（`run_dir/decisions/<gate>.json`）的写入不变量。

契约：`LOOP_ORCHESTRATION_SPEC` §10.4.2 —— 该文件是「已决策 run 逐条处置」的**唯一**来源，
append-only、只增不改；`gates.json` 是闸门权威 + `gates.sha256` 锚，**不存**逐条处置
（冻结的 `kb/schema/gate_state.schema.json` 的 required 不含该字段，且规格禁止从它反推）。

本文件是 2026-10-26 补的**回归钉子**：这些不变量此前只有散落在 `test_flow.py` 全链路里的
存在性断言，缺"只增不改 / 不碰权威文件 / 损坏不静默覆盖"三条容易被顺手破坏的约束。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from workflows.chunks import gates as G

GATE = "G1_diff_confirm"


def _ctx(tmp_path: Path) -> SimpleNamespace:
    """落账只需要 `run_dir` 与 `run_id`（唯一写者是这个函数，不碰 state/事件）。"""
    return SimpleNamespace(run_dir=tmp_path, run_id="RUN-TEST-LEDGER")


def _record(*, signed_at: str = "2026-10-26T12:00:00+08:00", decision: str = "confirmed",
            entries: dict | None = None, hard_block: list | None = None) -> dict:
    return {
        "decision": decision,
        "actor": "human:reviewer",
        "signed_at": signed_at,
        "reason": "逐条看过",
        "entries": entries if entries is not None else {
            "D-001": {"decision": "confirmed", "reason": None},
            "D-002": {"decision": "ignored", "reason": "旧版正文缺失", "source": "draft"},
        },
        "cycle": 0,
        "hard_block": hard_block or [],
    }


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_ledger_is_append_only_and_only_writes_contract_fields(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    path = G.append_decision_ledger(ctx, GATE, _record())
    assert path == tmp_path / "decisions" / f"{GATE}.json"
    first = _read(path)
    assert first["schema"] == "loop/gate_entries"
    assert first["gate"] == GATE and first["run_id"] == ctx.run_id
    assert len(first["records"]) == 1

    # 第二轮（如 G2 返工回边）追加：旧记录**逐值等价**（append-only 的语义不变量；
    # 整文件按同值不同格式重排不在本用例约束内）
    second_path = G.append_decision_ledger(
        ctx, GATE, _record(signed_at="2026-10-26T13:00:00+08:00", decision="rework"))
    second = _read(second_path)
    assert len(second["records"]) == 2
    assert second["records"][0] == first["records"][0], "append-only：旧记录不得被改写"
    assert [r["decision"] for r in second["records"]] == ["confirmed", "rework"]

    record = second["records"][0]
    assert {"cycle", "decided_at", "decision", "actor", "reason", "entries", "hard_block"} <= set(record)
    # decided_at 取权威签署时间（时间只有单一注入入口，不新取墙钟）
    assert record["decided_at"] == "2026-10-26T12:00:00+08:00"
    # 落账只写契约字段：内部附加键（如 `source`）不得进账本
    assert record["entries"]["D-002"] == {"decision": "ignored", "reason": "旧版正文缺失"}
    assert set(record["entries"]["D-001"]) == {"decision", "reason"}


def test_ledger_write_never_touches_the_authority_file(tmp_path: Path) -> None:
    """落账不得改写 `gates.json`（权威 + sha256 锚）：否则锚失效、且形成第二个来源。"""
    gates_json = tmp_path / "gates.json"
    gates_json.write_text(json.dumps({"schema": "loop/gate_state", "gates": {}}, indent=2),
                          encoding="utf-8")
    before = hashlib.md5(gates_json.read_bytes()).hexdigest()

    G.append_decision_ledger(_ctx(tmp_path), GATE, _record())

    assert hashlib.md5(gates_json.read_bytes()).hexdigest() == before, "落账改写了 gates.json"
    body = json.loads(gates_json.read_text(encoding="utf-8"))
    assert "entry_decisions" not in json.dumps(body), "逐条处置不得进权威文件（唯一来源是 decisions/）"


@pytest.mark.parametrize("corrupt", [
    "{not json",                                        # 不可解析
    json.dumps({"schema": "loop/gate_entries", "gate": GATE}),   # 缺 records 列表
    json.dumps({"schema": "loop/gate_entries", "records": "oops"}),
])
def test_corrupt_ledger_fails_closed_and_is_not_overwritten(tmp_path: Path, corrupt: str) -> None:
    """损坏/形状非法 ⇒ 显式失败；绝不静默覆盖（那会抹掉已签闸门的处置记录）。"""
    path = tmp_path / "decisions" / f"{GATE}.json"
    path.parent.mkdir(parents=True)
    path.write_text(corrupt, encoding="utf-8")
    before = path.read_bytes()

    with pytest.raises(RuntimeError, match="闸门处置落账"):
        G.append_decision_ledger(_ctx(tmp_path), GATE, _record())

    assert path.read_bytes() == before, "失败路径不得改写落账文件"
