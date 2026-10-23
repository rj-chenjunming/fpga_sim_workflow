"""R3-01：N6 观测点印记「能被 host/evidence 解析」的定点回归（本轮 P0）。

背景（真实 bug）：提示词示例曾写成 `uvm_info("N6", $sformatf("[%s] OK …", "N6_FPGA_DATE", …))`
⇒ 日志里的 UVM report **ID** 是 `N6`，而 `host/evidence.py::_auto_markers()` 只认含 `N6_`
的 **ID** ⇒ "无预期观测点印记"，真实轮 I3 永远过不了。即使 ID 对了，marker 尾名解析不到
文档条目时 `_verdict` 也会判"期望不可解析"。

四条可判定断言（契约 §6 R3-01 a/b/c/d）：
  a. 提示词必须是 `uvm_info("<marker>", …)` 形态（marker = UVM_INFO 的 **ID**）；
  b. 合法 marker（含文档条目名）+ 合法 edits ⇒ Host 校验通过；
  c. 不可解析 marker（`N6_CHECK_1`）⇒ fail-closed 且问题点名该 marker 与原因；
  d. 真格式日志行 + `UVM Report Summary` + by-id 段 + run 级 `doc_entries.jsonl`
     ⇒ `host.evidence.evidence_view()` 该印记 `consistent=True` 且 `verdict.passed=True`
     （直接证明"新 run 能过 I3"；判据仍是 `host/evidence.py`，这里不另写一套）。

另加三条锁死旁路/形态的断言：
  - 生产路径 `run_model_node` 必须把 `ctx.run_dir` 绑进校验器（用只存在于本 run 快照的
    条目名区分"绑定 vs 未绑定"）；
  - **不传 run_dir 也恒执行**可解析校验 ⇒ 解析不到即 fail-closed（没有"没绑就跳过"的旁路）；
  - 反例：ID 写成 `N6`、`N6_FPGA_DATE` 只在消息里 ⇒ 自动判据取不到印记（锁死旧 bug 形态）。

**口径唯一**：期望解析/三向一致判定全部来自 `host/evidence.py`（只读，不改）；
本文件只负责"让输出可被它解析"。不放宽任何既有断言。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

#: 一条真实格式的观测点印记（`<addr>+<off>` 与 `= 0x…` 是 evidence 的解析锚点）。
IMPRINT_LINE = (
    "UVM_INFO top_env.sv(154) @ 0.000 us "
    "[N6_fpga_date] OK 0x0000+0x04 fpga_date = 0x20260708"
)


def _write_doc_entries(run_dir: Path, *, name: str = "fpga_date",
                       reset: str = "2026_0708", entry_id: str = "0x0000#0x0004",
                       segment: str = "0x0000", offset_global: str = "0x0004") -> None:
    """run 级文档条目快照（`<run>/doc_entries.jsonl`）= `resolve_expected_imprint` 的权威来源。"""
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "doc_entries.jsonl").write_text(
        json.dumps({"entry_id": entry_id, "name": name, "segment": segment,
                    "offset_global": offset_global, "reset": reset},
                   ensure_ascii=False) + "\n",
        encoding="utf-8")


def _revision(case: str, marker: str) -> dict[str, Any]:
    """一条合法 revision：edits[].new 里真的用该 marker 作 UVM_INFO 的 ID 打印实际读回值。"""
    new_text = (
        f'uvm_info("{marker}", $sformatf("OK 0x0000+0x04 fpga_date = 0x%08h", actual), UVM_LOW);'
    )
    return {"case": case, "rationale": "按 rtl_change 修订期望值并加观测点",
            "edits": [{"line": 3, "old": "check(0x0000+0x04, 8'h23);",
                       "new": new_text, "basis": "input.targets[0].revision_points[0].offset=0x4"}]}


def _payload(case: str, marker: str) -> dict[str, Any]:
    return {"data": {
        "revisions": [_revision(case, marker)],
        "observation_points": [{
            "case": case, "marker": marker, "addr": "0x0000", "offset": "0x04",
            "expected_value": "0x20260708",
            "basis": "input.targets[0].revision_points[0].offset=0x4；doc_bitdef reset=2026_0708"}],
        "rework_resolution": [], "notes": [],
    }}


# ---------------------------------------------------------------- a：提示词形态


def test_prompt_prints_marker_as_uvm_info_id() -> None:
    """a. 示例必须是 `uvm_info("<marker>", …)`；marker 是 ID，不是消息前缀。"""
    from workflows.chunks.model_common import load_prompts

    spec = load_prompts()["n6_author"]
    rules = " ".join(spec["info"]["rules"])
    instruct = " ".join(spec["instruct"])
    text = rules + " " + instruct

    assert 'uvm_info("<marker>"' in text, "示例必须用 <marker> 占位 UVM_INFO 的 ID 实参"
    assert 'uvm_info("N6",' not in text, "不得再出现「ID=N6 + 消息前缀」形态"
    assert "不是消息前缀" in text, "规则必须写清 marker 不是消息前缀"
    assert "解析不到" in rules, "规则必须写明解析不到的后果（fail-closed）"
    assert "N6_fpga_date" in text, "示例 marker 必须带文档条目名（可解析）"
    # 既有规则不得被本轮改掉（零放宽）
    assert "edits[].new" in rules and "只列不写" in rules
    assert "N6_<检查点名>" in rules
    assert "0x%08h" in instruct and "实际读回" in instruct


# ---------------------------------------------------------------- b / c：校验器


def test_legal_marker_passes_validation(tmp_path: Path) -> None:
    """b. 合法 marker（含文档条目名，能解析到期望）+ 合法 edits ⇒ 校验通过。"""
    from workflows.chunks.model_steps import _validate

    run_dir = tmp_path / "run"
    _write_doc_entries(run_dir)
    result = _validate("n6", _payload("tc_demo", "N6_fpga_date"),
                       offered={"cases": {"tc_demo"}}, run_dir=run_dir)
    assert result["ok"] is True, result["problems"]
    point = result["accepted"]["observation_points"][0]
    assert point["marker"] == "N6_fpga_date"


def test_unresolvable_marker_fails_closed_and_names_it(tmp_path: Path) -> None:
    """c. `N6_CHECK_1` 解析不到文档条目 ⇒ fail-closed，且问题点名 marker 与原因。"""
    from workflows.chunks.model_steps import _validate

    run_dir = tmp_path / "run"
    _write_doc_entries(run_dir)
    result = _validate("n6", _payload("tc_demo", "N6_CHECK_1"),
                       offered={"cases": {"tc_demo"}}, run_dir=run_dir)
    assert result["ok"] is False, "不可解析的 marker 不得放行"
    assert any("N6_CHECK_1" in p and "不可解析" in p for p in result["problems"]), \
        result["problems"]
    assert "accepted" in result and not result["accepted"].get("observation_points")


def test_unresolvable_marker_fails_closed_without_run_dir() -> None:
    """旁路已封：**不传 run_dir** 时校验也恒执行，解析不到 ⇒ fail-closed 并点名 marker。

    （"调用方没绑 run_dir ⇒ 跳过校验"会让后加的不绑 run_dir 调用点静默绕过 I3 判据，
    违反"校验未实现/未执行 = 不得判通过"；这里显式锁死。）
    """
    from workflows.chunks.model_steps import _validate

    result = _validate("n6", _payload("tc_demo", "N6_CHECK_1"),
                       offered={"cases": {"tc_demo"}})
    assert result["ok"] is False, "不传 run_dir 不得跳过可解析校验"
    assert any("N6_CHECK_1" in p and "不可解析" in p for p in result["problems"]), \
        result["problems"]


async def test_run_model_node_binds_ctx_run_dir_into_validator(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """生产路径（run_model_node）必须把 `ctx.run_dir` 绑进校验器 —— 否则校验形同虚设。

    用一个**只存在于本 run 快照**的文档条目名（`r3_imprint_probe`）来区分"绑定 vs 未绑定"：
    绑定 ⇒ 从 run 快照解析成功；不绑 ⇒ 跨 run/当前索引都查不到 ⇒ fail-closed。
    """
    from types import SimpleNamespace

    from workflows.chunks import model_request as MR
    from workflows.chunks import model_steps as M

    run_dir = tmp_path / "run"
    _write_doc_entries(run_dir, name="r3_imprint_probe", reset="0x00abcdef",
                       entry_id="0x0000#0x0040", offset_global="0x0040")
    captured: dict[str, Any] = {}

    async def fake(ctx: Any, node: str, *, prompt_key: str, input_data: dict[str, Any],
                   offered: dict[str, Any], validate: Any) -> dict[str, Any]:
        captured["validate"] = validate
        return {"mode": "standin"}

    monkeypatch.setattr(MR, "run_model_node", fake)
    ctx = SimpleNamespace(run_dir=run_dir, run_id="RUN-20261024-000001")
    await M.run_model_node(ctx, "N6", prompt_key="n6_author", input_data={},
                           offered={"cases": {"tc_demo"}})
    validate = captured["validate"]
    # 绑定 run_dir ⇒ 能从本 run 快照解析到该 marker 的期望
    bound = validate("n6", _payload("tc_demo", "N6_r3_imprint_probe"),
                     offered={"cases": {"tc_demo"}})
    assert bound["ok"] is True, bound["problems"]
    # 同一 marker 不绑 run_dir ⇒ 任何来源都查不到 ⇒ fail-closed（证明绑定真的生效）
    unbound = M._validate("n6", _payload("tc_demo", "N6_r3_imprint_probe"),
                          offered={"cases": {"tc_demo"}})
    assert unbound["ok"] is False, "该 marker 只能从本 run 快照解析；不绑 run_dir 不得通过"
    assert any("N6_r3_imprint_probe" in p and "不可解析" in p for p in unbound["problems"]), \
        unbound["problems"]


# ---------------------------------------------------------------- d：端到端证据视图


def test_evidence_view_passes_real_imprint_log(tmp_path: Path) -> None:
    """d. 真格式日志 + by-id 段 + run 级条目快照 ⇒ consistent=True 且 verdict.passed=True。"""
    from host import evidence

    run_dir = tmp_path / "runs" / "RUN-20261024-000001"
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True)
    _write_doc_entries(run_dir)
    # `_find_run_dir()` 需要 run 级产物标记文件才能从证据件回推 run 目录。
    (run_dir / "gates.json").write_text(
        json.dumps({"schema": "loop/gates", "gates": {}}, ensure_ascii=False), encoding="utf-8")

    log_path = evidence_dir / "20261024-000001_tc_pcie_rw_02_1_run.log"
    log_path.write_text("\n".join([
        IMPRINT_LINE,
        "",
        "UVM Report Summary",
        "------------------",
        "UVM_INFO : 1",
        "UVM_WARNING : 0",
        "UVM_ERROR : 0",
        "UVM_FATAL : 0",
        "",
        "Report counts by id",
        "[N6_fpga_date] 1",
        "---",
        "",
    ]) + "\n", encoding="utf-8")

    view = evidence.evidence_view(log_path)

    assert view["present"] is True
    assert view["run_dir"] == str(run_dir), "必须能从证据件回推 run 目录（期望解析的来源）"
    assert view["has_report_summary"] is True
    imprint = view["imprints"]["N6_fpga_date"]
    assert imprint["expected"]["address"] == "0x0000+0x04"
    assert imprint["expected"]["value"] == "0x20260708"
    assert imprint["expected"]["resolved_by"] == "run-snapshot"
    assert imprint["observed"]["address"] == "0x0000+0x04"
    assert imprint["observed"]["value"] == "0x20260708"
    assert imprint["checks"] == {
        "imprint_present": True,
        "id_count_present": True,
        "count_matches_id_count": True,
        "address_matches_expected": True,
        "value_matches_expected": True,
    }
    assert imprint["consistent"] is True, imprint
    assert view["verdict"]["passed"] is True, view["verdict"]["reasons"]


def test_imprint_with_message_prefix_id_is_not_parsed(tmp_path: Path) -> None:
    """反例（锁死 bug 形态）：ID 写成 `N6`、`N6_FPGA_DATE` 只在消息里 ⇒ 自动判据看不到印记。"""
    from host import evidence

    run_dir = tmp_path / "runs" / "RUN-20261024-000002"
    evidence_dir = run_dir / "evidence"
    evidence_dir.mkdir(parents=True)
    _write_doc_entries(run_dir)
    (run_dir / "gates.json").write_text("{}", encoding="utf-8")
    log_path = evidence_dir / "20261024-000002_tc_pcie_rw_02_1_run.log"
    log_path.write_text("\n".join([
        "UVM_INFO top_env.sv(154) @ 0.000 us [N6] [N6_FPGA_DATE] OK 0x0000+0x04 fpga_date = 0x20260708",
        "",
        "UVM Report Summary",
        "UVM_INFO : 1",
        "UVM_WARNING : 0",
        "UVM_ERROR : 0",
        "UVM_FATAL : 0",
        "",
        "Report counts by id",
        "[N6] 1",
        "---",
        "",
    ]) + "\n", encoding="utf-8")

    view = evidence.evidence_view(log_path)
    assert view["imprints"] == {}, "ID 不是 N6_* ⇒ 自动判据取不到印记（正是本轮要修的形态）"
    assert view["verdict"]["passed"] is False
    assert any("无预期观测点印记" in reason for reason in view["verdict"]["reasons"]), \
        view["verdict"]["reasons"]
