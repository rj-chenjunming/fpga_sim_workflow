"""S7a：N6 材料面瘦身 + 提交格式前置（**判据只加严，不放宽**）。

判据（不读实现也应成立）：
- N6 的 attempt `input/` **不含** 345 KB 级 run 产物全文（`n5_impact.json` / `n5_impact.md`）；
- N6 的 input 里有一份 **Host 派生** 的影响面摘要，且 attempt 记录里写明"派生自哪个源件 +
  源件 md5/size"（证据可复核，不靠口头说明）；
- 摘要**不是**第二套判据：只投影 `n5_impact.json` 里 targets 实际用到的字段，不带原文 hunk/文档正文；
- 非 N6 节点的材料面**不变**（仍按 `INPUT_MATERIALS` 白名单）——瘦身不许夹带别的节点；
- 派生源件缺失 ⇒ `present=False`（不补、不猜）；源件是符号链接 ⇒ 显式失败；
- 任务文本与 `submit_result` 工具描述把"payload 必须是 JSON 对象"写成**显式要求**；
- `apply_edits` 行号漂移的错误信息点名字段、实际行号与声明值，并指出 `line` 该从哪来；
- `BadSubmission` 的 payload 类型错误信息点名字段与**期望类型**。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from host.agent_backends import dsh as D
from host.agent_backends import dsh_assets as A

#: 真夹具的量级（`RUN-20261015-120626/n5_impact.json` 实测 345638 B）；用例用同量级假件，
#: 只为钉"全文不许进 input"，不复制真实工程内容。
FULL_IMPACT = {"schema": "kb/n5_impact", "version": 1, "must_change_count": 1,
               "must_change": [{"case": "tc_demo", "file": "TESTLIB/tc_demo.sv", "line": 217,
                                "entry_id": "RTL-1", "segment": "reg_a", "offset": "0x04",
                                "rtl_files": ["RTL/demo.sv"],
                                "padding": "x" * 345000}],
               "must_change_cases": ["tc_demo"]}


def _run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "runs" / "RUN-S7A"
    run_dir.mkdir(parents=True)
    (run_dir / "n5_impact.json").write_text(json.dumps(FULL_IMPACT), encoding="utf-8")
    (run_dir / "n5_impact.md").write_text("# impact\n" + "y" * 140000, encoding="utf-8")
    (run_dir / "n2_diff.json").write_text('{"diffs": []}', encoding="utf-8")
    return run_dir


def _backend(tmp_path: Path) -> D.DshBackend:
    bin_path = tmp_path / "bin.js"
    bin_path.write_text("// fixture bin\n", encoding="utf-8")
    return D.DshBackend(D.DshConfig(enabled=True, version="0.2.1-rc.2",
                                    node=bin_path, bin=bin_path,
                                    bin_sha256=hashlib.sha256(
                                        bin_path.read_bytes()).hexdigest(),
                                    timeout_s=30.0))


# ---------------------------------------------------------------- 材料面瘦身

def test_n6_input_excludes_full_impact_documents(tmp_path: Path) -> None:
    """N6 的 `input/` 不得含 n5_impact 全文（S5/S6 实测 345 KB 诱导反复解析、300 s 未进候选）。"""
    run_dir = _run_dir(tmp_path)
    workspace = _backend(tmp_path).prepare_attempt(run_dir, "N6", 1)
    staged = sorted(path.name for path in workspace.layout.input_dir.iterdir())
    assert "n5_impact.json" not in staged
    assert "n5_impact.md" not in staged
    assert A.N6_SUMMARY_NAME in staged
    # 全文体积不许以"换个名字"的方式回流
    total = sum(path.stat().st_size for path in workspace.layout.input_dir.iterdir())
    assert total < 16384, "N6 input 总量必须远小于原件（实际 %d B）" % total


def test_n6_summary_records_derivation_source_and_md5(tmp_path: Path) -> None:
    """派生物必须可复核：记录里写明源件名、源件 md5/size，以及派生物自己的 md5/size。"""
    run_dir = _run_dir(tmp_path)
    source = (run_dir / "n5_impact.json").read_bytes()
    workspace = _backend(tmp_path).prepare_attempt(run_dir, "N6", 1)
    staged = {item["name"]: item for item in workspace.materials}
    summary = staged[A.N6_SUMMARY_NAME]
    assert summary["present"] is True
    assert summary["derived_from"] == {"name": "n5_impact.json",
                                       "md5": hashlib.md5(source).hexdigest(),
                                       "size": len(source)}
    written = (workspace.layout.input_dir / A.N6_SUMMARY_NAME).read_bytes()
    assert summary["md5"] == hashlib.md5(written).hexdigest()
    assert summary["size"] == len(written)
    # 记录也要进 attempt 记录（复核入口只有一个）
    record = {item["name"]: item for item in workspace.record(run_dir=run_dir)["materials"]}
    assert record[A.N6_SUMMARY_NAME]["derived_from"]["md5"] == summary["derived_from"]["md5"]


def test_n6_summary_projects_only_target_fields_not_a_second_judgement(tmp_path: Path) -> None:
    """摘要只投影 targets 需要的字段；不含原文 hunk / 文档正文 / 判定结论（不是第二套判据）。"""
    run_dir = _run_dir(tmp_path)
    _backend(tmp_path).prepare_attempt(run_dir, "N6", 1)
    summary = json.loads((run_dir / "agent_workspaces" / "N6" / "attempt-000001"
                          / "input" / A.N6_SUMMARY_NAME).read_text(encoding="utf-8"))
    assert summary["schema"] == A.N6_SUMMARY_SCHEMA
    assert summary["must_change_count"] == 1
    assert [item["case"] for item in summary["cases"]] == ["tc_demo"]
    for item in summary["cases"]:
        assert set(item) == {"case", "file", "line", "entry_id", "segment", "offset",
                             "rtl_files"}
    assert "padding" not in json.dumps(summary), "摘要不得夹带原件正文"
    assert len(json.dumps(summary).encode("utf-8")) < 4096


def test_non_n6_nodes_keep_the_full_material_face(tmp_path: Path) -> None:
    """瘦身只针对 N6：其它节点的白名单材料面不许被顺手改掉。"""
    run_dir = _run_dir(tmp_path)
    workspace = _backend(tmp_path).prepare_attempt(run_dir, "N8", 1)
    staged = sorted(path.name for path in workspace.layout.input_dir.iterdir())
    assert staged == ["n2_diff.json", "n5_impact.json", "n5_impact.md"]
    assert A.materials_for("N8") == A.INPUT_MATERIALS
    assert A.materials_for("N6") == A.N6_MATERIALS


def test_n6_missing_derivation_source_is_absent_not_faked(tmp_path: Path) -> None:
    """源件缺失 ⇒ `present=False`（不补、不猜、不生成半个摘要）。"""
    run_dir = tmp_path / "runs" / "RUN-S7A"
    run_dir.mkdir(parents=True)
    (run_dir / "n2_diff.json").write_text('{"diffs": []}', encoding="utf-8")
    workspace = _backend(tmp_path).prepare_attempt(run_dir, "N6", 1)
    staged = {item["name"]: item for item in workspace.materials}
    assert staged[A.N6_SUMMARY_NAME]["present"] is False
    assert not (workspace.layout.input_dir / A.N6_SUMMARY_NAME).exists()


def test_n6_derivation_source_symlink_is_rejected(tmp_path: Path) -> None:
    """源件是符号链接 ⇒ 显式失败（与既有材料白名单同一条逃逸判据）。"""
    run_dir = tmp_path / "runs" / "RUN-S7A"
    run_dir.mkdir(parents=True)
    real = tmp_path / "outside.json"
    real.write_text(json.dumps(FULL_IMPACT), encoding="utf-8")
    (run_dir / "n5_impact.json").symlink_to(real)
    with pytest.raises(D.BackendConfigurationError, match="符号链接"):
        _backend(tmp_path).prepare_attempt(run_dir, "N6", 1)


def test_n6_derivation_from_malformed_source_is_explicit_failure(tmp_path: Path) -> None:
    """源件不是 JSON 对象 ⇒ 显式失败（不生成空摘要糊过去）。"""
    run_dir = tmp_path / "runs" / "RUN-S7A"
    run_dir.mkdir(parents=True)
    (run_dir / "n5_impact.json").write_text("not json", encoding="utf-8")
    with pytest.raises(D.BackendConfigurationError, match="n6_impact_summary"):
        _backend(tmp_path).prepare_attempt(run_dir, "N6", 1)


# ---------------------------------------------------------------- 提交格式前置

def test_task_text_requires_payload_object() -> None:
    """任务文本必须显式要求 payload 是 JSON 对象（模型最先读到的硬要求）。"""
    request = D.BackendRequest(input_data={}, info="i", instruct="do", schema=None)
    task = D._compose_task(request, attempt_key="RUN-S7A/N6/1")
    flat = task.replace("\n", " ")
    assert "payload" in flat
    assert "对象" in flat and "字符串" in flat, "必须显式禁止把 payload 传成 JSON 字符串"


def test_n6_prompt_pins_line_to_excerpt_prefix() -> None:
    """N6 的 `line` 来源必须写成"逐字取自 excerpts 片段行首的行号"（S6 第 4 次真机 218≠217）。"""
    from workflows.chunks import model_request as MR

    contract = MR.request_contract("n6_author")
    flat = (contract["instruct"] + "\n" + contract["info"]).replace("\n", " ")
    assert "excerpts" in flat
    assert "行号" in flat, "必须显式说明 line 就是 excerpts 片段行首的行号"
    assert "不得自己数" in flat or "逐字" in flat


def test_submit_tool_description_forbids_stringified_payload() -> None:
    """`submit_result` 工具描述（模型最先看到的参数说明）必须写明"对象，不是字符串"。"""
    body = (Path(D.__file__).parent / A.PLUGIN_SOURCE_DIR.name / "submit_result.mjs"
            ).read_text(encoding="utf-8")
    flat = " ".join(item.strip() for item in body.splitlines())
    start = flat.find("payload:")
    assert start >= 0, "插件必须声明 payload 参数"
    entry = flat[start:start + 400]
    assert "对象" in entry and "字符串" in entry, entry


def test_apply_edits_line_drift_error_names_field_actual_and_hint() -> None:
    """行号漂移的错误信息必须点名字段、实际行号、声明值，并指出 line 该从哪来。"""
    from workflows.chunks.host_steps import apply_edits

    text = "a\nb\ntarget_line\n"
    with pytest.raises(ValueError) as info:
        apply_edits(text, [{"line": 9, "old": "target_line", "new": "changed",
                            "basis": "doc_bitdef"}], case="tc_demo")
    message = str(info.value)
    assert "edits[0].line" in message
    assert "3" in message and "9" in message
    assert "excerpts" in message


def test_bad_submission_payload_type_error_states_expected_type() -> None:
    """payload 传成字符串 ⇒ `BadSubmission` 必须写出期望类型与收到的类型（人一眼可定位）。"""
    from host.agent_backends.dsh_protocol import BadSubmission, SubmissionCall, _submission

    call = SubmissionCall(call_id="c1", input={"task_id": "t", "summary": "s",
                                               "payload": '{"revisions": []}'},
                          results=())
    with pytest.raises(BadSubmission) as info:
        _submission(call, {"accepted": True, "problems": ()}, expect_task_id="t")
    message = str(info.value)
    assert "payload" in message and "JSON 对象" in message
    assert "str" in message and "期望" in message
