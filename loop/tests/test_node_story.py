"""节点人类可读展示投影（SPEC-REV-02 R1 + §C.2 P-01～P-35；plan §1 接口契约）。

固定的是**展示契约**（可判定断言），不是措辞的实现细节：

- 每个已知节点都有 `purpose`（一句话用途），未知节点为 None；
- `story` 在 `purpose/steps/key_results` 之上**只增**：`headline` / `headline_source` /
  `note` / `not_reached` / `not_executed` / `evidence_note` / `status_note` /
  `status_glossary` / `gate` 透传；第三轮再增 `observation_points`（R3-03，**仅 N6 下发
  该 key**）/ `evidence_groups` + `evidence_groups_note`（R3-06，所有节点都有 key）；
- 缺字段一律"未下发"，不补默认值；`not_reached`（运行终态且无事件）与
  `not_executed`（drill 确实没执行）必须区分；失败节点全文不出现"完成"；
  正文不出现 seq；
- 同一输入 → 逐字节相同输出，且不改动入参。
"""

from __future__ import annotations

import copy
import json
from typing import Any

from services import node_story, node_view

RUN_ID = "RUN-TEST-0001"


def _ev(seq: int, kind: str, status: str, node: str, detail: dict | None = None,
        ts: float = 10.0, refs: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "seq": seq, "ts": ts, "run_id": RUN_ID, "node": node,
        "kind": kind, "status": status, "detail": detail or {},
        "refs": list(refs), "provisional": False,
    }


def _story(node: str, *, events: list[dict] | None = None, detail: dict | None = None,
           purpose: str | None = "一句话用途。", mode: str | None = None,
           run_status: str | None = None, gate: dict | None = None,
           run_halted: bool = False, refs: list[str] | None = None) -> dict[str, Any]:
    return node_story.build_story(
        node, events=events or [], detail=detail or {}, purpose=purpose,
        run_status=run_status, mode=mode, gate=gate, run_halted=run_halted,
        refs=refs,
    )


def _rows(story: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["field"]: row for row in story["key_results"]}


def _labels(story: dict[str, Any]) -> list[str]:
    return [row["label"] for row in story["key_results"]]


def _body_text(story: dict[str, Any]) -> str:
    """正文（结果 / 提示 / 证据 / 步骤）拼成的可检索文本（不含原始记录字段）。"""
    parts = [story["headline"], (story["note"] or {}).get("text") or "",
             (story["evidence_note"] or {}).get("text") or ""]
    parts += [step["text"] for step in story["steps"]]
    return " ".join(parts)


# ---------------------------------------------------------------- 契约形状


def test_every_known_node_has_plain_language_purpose() -> None:
    for node, meta in node_view.NODE_CATALOG.items():
        assert meta.get("purpose"), node
        # 一句话用途：以句号结尾、不过长，避免又变回术语墙
        assert meta["purpose"].endswith("。"), node
        assert len(meta["purpose"]) <= 60, (node, len(meta["purpose"]))


def test_story_contract_keys_are_added_on_top_of_purpose_steps_key_results() -> None:
    story = _story("N0", detail={"mode": "real", "baseline": "v0"})
    for key in ("purpose", "steps", "key_results", "headline", "headline_source",
                "note", "not_reached", "not_executed", "evidence_note",
                "status_note", "status_glossary", "gate",
                # R3-06 新字段：所有节点都有 key（null 语义 = 不分组、平铺 refs）
                "evidence_groups", "evidence_groups_note"):
        assert key in story, key
    assert isinstance(story["headline"], str) and story["headline"]
    assert story["headline_source"] in ("template", "summary", "missing")
    assert story["not_reached"] is False and story["not_executed"] is False
    assert isinstance(story["status_glossary"], dict) and story["status_glossary"]
    # 未给 gate 块 ⇒ None（原样透传，不编）
    assert story["gate"] is None
    # R3-03：`observation_points` 只在 N6 下发 key；非 N6 不许出现（否则每个节点都冒噪声行）
    assert "observation_points" not in story
    # 非 N7/N9 不分组 ⇒ 显式 null（前端据 null 维持平铺 refs）
    assert story["evidence_groups"] is None and story["evidence_groups_note"] is None
    # `run_halted` 是调用方输入，不得混进投影字段（R3-10）
    assert "run_halted" not in story


def test_story_is_deterministic_and_does_not_mutate_inputs() -> None:
    events = [_ev(1, "node_started", "running", "N2"),
              _ev(2, "node_finished", "ok", "N2", {"source": "kb_tool"})]
    detail = {"has_change": True, "unresolved_count": 1,
              "diffs": [{"id": "RTL/a.v", "entry_id": "RTL/a.v", "kind": "rtl_file",
                         "change": "modified", "diff_hunk": "@@ -1 +1 @@",
                         "lines": [3], "offsets": ["0x4"], "unresolved": None}]}
    before_events, before_detail = copy.deepcopy(events), copy.deepcopy(detail)
    first = _story("N2", events=events, detail=detail)
    second = _story("N2", events=events, detail=detail)
    assert json.dumps(first, sort_keys=True, ensure_ascii=False) == \
        json.dumps(second, sort_keys=True, ensure_ascii=False)
    assert events == before_events and detail == before_detail, "投影不得改写入参"


def test_unknown_node_has_no_purpose_and_falls_back_honestly() -> None:
    story = _story("N77", events=[_ev(1, "node_started", "running", "N77")],
                   detail={"summary": "未来节点的一句话"}, purpose=None)
    assert story["purpose"] is None
    assert story["key_results"] == []
    assert story["headline"] == "未来节点的一句话"
    assert story["headline_source"] == "summary"
    assert [step["text"] for step in story["steps"]] == ["开始执行"]

    gap = _story("N77", events=[_ev(1, "node_started", "running", "N77")], purpose=None)
    assert gap["headline_source"] == "missing"
    assert "还没有收尾记录" in gap["headline"]


# ---------------------------------------------------------------- P-09 N1


def test_p09_n1_headline_is_two_numbers_and_key_results_only_two_fields() -> None:
    detail = {
        "manifest": {"allfiles_entries": 4491, "allfiles_sha256": "a" * 64,
                     "cases_frozen": 162, "doc_fingerprint": "b" * 64,
                     "commit_parseable": True},
        "parent": "v0",
        "source": "kb_tool",
        "summary": "N1：allfiles 4491 条（sha256 aaaa…），cases 冻结 162 个 …",
    }
    story = _story("N1", detail=detail)
    assert story["headline"] == "快照完成：4491 个文件，冻结 162 个用例。"
    assert story["headline_source"] == "template"
    # 只留 2 项：sha256 / 指纹 / commit 不进关键数字（在原始记录里）
    assert _labels(story) == ["快照文件数", "冻结用例数"]
    fields = {row["field"] for row in story["key_results"]}
    assert fields == {"manifest.allfiles_entries", "manifest.cases_frozen"}
    assert _rows(story)["manifest.allfiles_entries"]["text"] == "4491"


def test_p09_n1_old_run_without_manifest_falls_back_to_summary_not_defaults() -> None:
    detail = {"artifact": "/runs/RUN-OLD/n1_manifest_new.json", "parent": "v0",
              "source": "drill_fixture", "summary": "N1：旧 run 的摘要原文"}
    story = _story("N1", detail=detail)
    assert story["headline"] == "N1：旧 run 的摘要原文"
    assert story["headline_source"] == "summary"
    assert all(row["missing"] for row in story["key_results"])
    assert all(row["text"] == "未下发" for row in story["key_results"])


# ---------------------------------------------------------------- P-10/P-11/P-12 N2


#: 真实 run 的两条差异是**同一文件**的两路证据（allfile md5-only + rtl_file hunk）。
REAL_N2_DIFFS = [
    {"id": "RTL/SRC/imports/SRC/pcie_controller/pcie_register.v",
     "entry_id": "RTL/SRC/imports/SRC/pcie_controller/pcie_register.v",
     "kind": "allfile", "change": "modified", "before": "d560…", "after": "50e4…",
     "diff_hunk": None, "lines": [], "offsets": [],
     "unresolved": "② 路只比逐文件 md5 清单，无文本 hunk（旧版正文不在 KB）"},
    {"id": "RTL/SRC/imports/SRC/pcie_controller/pcie_register.v",
     "entry_id": "RTL/SRC/imports/SRC/pcie_controller/pcie_register.v",
     "kind": "rtl_file", "change": "modified", "before": "d560…", "after": "50e4…",
     "diff_hunk": "--- \n+++ \n@@ -168,7 +168,8 @@\n-  assign …\n+  assign …",
     "lines": [171, 172], "offsets": ["0xd04"], "unresolved": None},
]


def test_p12_n2_single_file_headline_says_what_changed_with_lines_and_offset() -> None:
    detail = {"has_change": True, "unresolved_count": 1, "diffs": copy.deepcopy(REAL_N2_DIFFS),
              "self_check_ok": True, "routes": {"allfiles": {"ok": True}}}
    story = _story("N2", detail=detail, run_status="waiting_gate", mode="real")
    assert story["headline"] == (
        "内容有变化：1 个文件改了（pcie_register.v），第 171–172 行，偏移 0xd04。"
    )
    assert story["headline_source"] == "template"


def test_p10_p11_n2_note_is_one_sentence_and_same_file_evidence_is_not_double_counted() -> None:
    detail = {"has_change": True, "unresolved_count": 1, "diffs": copy.deepcopy(REAL_N2_DIFFS)}
    story = _story("N2", detail=detail)
    # P-10：只写一句；P-11：同一文件两路证据归并 ⇒ 1 条需要确认（不是 2 条）
    assert story["note"] == {"text": "1 条需要你确认，到 G1 逐条处置", "level": "warn"}
    rows = _rows(story)
    assert rows["n2.content.files"]["value"] == 1
    assert rows["n2.content.hunks"]["value"] == 1
    assert rows["n2.content.confirm"]["value"] == 1
    # P-12：md5 / 路由计数 / 偏移列表都不进关键数字
    assert not any("md5" in row["field"] for row in story["key_results"])
    assert {row["field"] for row in story["key_results"]} == {
        "n2.content.files", "n2.content.hunks", "n2.content.confirm", "self_check_ok",
    }


def test_p11_n2_multi_file_headline_counts_files_hunks_and_confirmations() -> None:
    # drill 夹具形状：两个不同 id（doc_entry 有行号无 hunk；rtl_file 未决且无 hunk）
    diffs = [
        {"entry_id": "0x0000#0x0004", "id": "0x0000#0x0004", "kind": "doc_entry",
         "change": "modified", "diff_hunk": None, "lines": [444],
         "offsets": ["0x4"], "offset": "0x4", "unresolved": None},
        {"entry_id": "RTL/SRC/imports/SRC/reg/sys_reg.v",
         "id": "RTL/SRC/imports/SRC/reg/sys_reg.v", "kind": "rtl_file",
         "change": "modified", "diff_hunk": None, "lines": [], "offsets": [],
         "unresolved": "非 UTF-8 文本（二进制/编码不可解）"},
    ]
    story = _story("N2", detail={"has_change": True, "unresolved_count": 1, "diffs": diffs})
    assert story["headline"] == (
        "内容有变化：2 个文件改了（0x0000#0x0004、sys_reg.v）；"
        "0 处有行级证据，1 条需要你确认；"
        "其中 0x0000#0x0004 第 444 行、偏移 0x4。"
    )
    assert story["headline"].count("其中") == 1
    rows = _rows(story)
    assert rows["n2.content.files"]["value"] == 2
    assert rows["n2.content.hunks"]["value"] == 0
    assert rows["n2.content.confirm"]["value"] == 1


def test_p11_n2_truncates_file_names_after_three() -> None:
    diffs = [{"entry_id": f"RTL/{index}.v", "id": f"RTL/{index}.v", "kind": "rtl_file",
              "change": "modified", "diff_hunk": "@@ -1 +1 @@", "lines": [index],
              "offsets": [f"0x{index:x}"], "unresolved": None}
             for index in range(1, 5)]
    story = _story("N2", detail={"has_change": True, "diffs": diffs})
    assert "4 个文件改了（1.v、2.v、3.v…）" in story["headline"]
    # P-12 ②：多文件也要能看出"改在哪"，只补 1 条（取第一条有 offset 的）
    assert story["headline"].endswith("；其中 1.v 第 1 行、偏移 0x1。")
    assert story["note"] is None  # 没有未决条目 ⇒ 不给黄条


def test_p12_n2_multi_file_headline_picks_one_locator_with_lines_and_offset() -> None:
    """4 个文件的真实形状：前几条只有 md5，pcie_register.v 才有行号+偏移 ⇒ 补它那一条。"""
    def entry(name: str, index: int, lines: list[int], offsets: list[str]) -> dict:
        return {"id": name, "entry_id": name, "kind": "rtl_file", "change": "modified",
                "diff_hunk": "@@ -1 +1 @@" if lines else None,
                "lines": lines, "offsets": offsets, "unresolved": None}

    diffs = [
        entry("RTL/TCS9620_MAC_TOP.v", 1, [], []),
        entry("RTL/dom_engine_top.v", 2, [], []),
        entry("RTL/pcie_register.v", 3, [171, 172], ["0x0d04"]),
        entry("RTL/sys_reg.v", 4, [], []),
    ]
    story = _story("N2", detail={"has_change": True, "diffs": diffs, "unresolved_count": 0})
    assert story["headline"] == (
        "内容有变化：4 个文件改了（TCS9620_MAC_TOP.v、dom_engine_top.v、pcie_register.v…）；"
        "1 处有行级证据，0 条需要你确认；"
        "其中 pcie_register.v 第 171–172 行、偏移 0x0d04。"
    )
    assert story["headline"].count("其中") == 1
    assert story["note"] is None


def test_p12_n2_no_change_headline_and_no_note() -> None:
    story = _story("N2", detail={"has_change": False, "diffs": [], "unresolved_count": 0})
    assert story["headline"] == "文件内容没有变化。"
    assert story["note"] is None
    rows = _rows(story)
    assert rows["n2.content.files"]["value"] == 0
    assert rows["n2.content.hunks"]["value"] == 0


def test_p12_n2_old_run_without_diffs_says_so_and_falls_back_to_unresolved_count() -> None:
    detail = {"has_change": True, "unresolved_count": 3,
              "summary": "N2：差异 3 条（allfile 2、rtl_file 1），未决 3 条"}
    story = _story("N2", detail=detail)
    assert "差异清单未下发（旧 run 的 detail 没有逐条清单）" in story["headline"]
    assert story["headline_source"] == "missing"
    assert story["note"] is not None
    assert "3 条需要你确认" in story["note"]["text"]
    assert "按未决条目数，旧 run 无逐条清单" in story["note"]["text"]
    rows = _rows(story)
    assert rows["n2.content.files"]["missing"] is True
    assert rows["n2.content.confirm"]["value"] == 3


def test_p11_n2_same_id_with_three_evidence_paths_counts_once() -> None:
    diffs = [
        {"entry_id": "RTL/a.v", "id": "RTL/a.v", "kind": "changelog", "change": "modified",
         "diff_hunk": None, "lines": [], "offsets": [], "unresolved": None},
        {"entry_id": "RTL/a.v", "id": "RTL/a.v", "kind": "allfile", "change": "modified",
         "diff_hunk": None, "lines": [], "offsets": [], "unresolved": None},
        {"entry_id": "RTL/a.v", "id": "RTL/a.v", "kind": "rtl_file", "change": "modified",
         "diff_hunk": "@@ -1 +1 @@", "lines": [9], "offsets": ["0x8"],
         "unresolved": None},
    ]
    story = _story("N2", detail={"has_change": True, "diffs": diffs, "unresolved_count": 0})
    rows = _rows(story)
    assert rows["n2.content.files"]["value"] == 1
    assert rows["n2.content.hunks"]["value"] == 1
    assert rows["n2.content.confirm"]["value"] == 0


# ---------------------------------------------------------------- 切片 1｜N3


def test_p13_n3_headline_uses_model_digest_summary_and_confirmation_count() -> None:
    detail = {"mode": "live", "provider": "agently", "source": "model_live",
              "digest_summary": "这次把 pcie_register.v 的 0x0d04 高位改成只读。",
              "digest_confirmations": ["映射对不上", "旧版正文缺失"],
              "groups_count": 0, "offered_segments_empty": True}
    story = _story("N3", detail=detail,
                   events=[_ev(1, "node_finished", "ok", "N3", detail)])
    assert story["headline"] == (
        "模型说：这次把 pcie_register.v 的 0x0d04 高位改成只读。"
        "（另有 2 条需要你确认）"
    )
    rows = _rows(story)
    assert rows["groups_count"]["text"] == "0（没有段信息，无法分组——不是没分析）"
    assert rows["digest_confirmations"]["text"] == "2 条"


def test_p13_n3_old_run_without_digest_summary_says_where_the_body_is() -> None:
    detail = {"mode": "standin", "provider": "none", "source": "model_standin",
              "summary": "N3：0 组语义摘要，覆盖 2 条差异（provider=None）"}
    story = _story("N3", detail=detail,
                   events=[_ev(1, "node_finished", "ok", "N3", detail)])
    assert story["headline"] == (
        "模型摘要未下发（旧 run 的 detail 没有摘要；"
        "正文在证据 n3_digest.md，面板不打开正文）。"
    )
    assert story["headline_source"] == "missing"
    assert story["evidence_note"]["kind"] == "agent_calls"
    assert "agent" in story["evidence_note"]["text"].lower() or "替身" in story["evidence_note"]["text"]
    assert story["status_note"] == "通过"


# ---------------------------------------------------------------- 切片 1｜N5 / N6 / N7


def test_p19_n5_headline_and_key_numbers_only_must_change_and_to_check() -> None:
    detail = {"must_change_count": 3, "must_change_cases": ["tc_a", "tc_b", "tc_c"],
              "to_check_count": 6, "index_gap_count": 5, "index_complete": False,
              "gate1_rc": 0, "cmd": "python -B kb/tools/n5_impact.py", "source": "kb_tool"}
    story = _story("N5", detail=detail)
    assert story["headline"] == (
        "必改 3 个用例：tc_a、tc_b、tc_c；另有 6 个待查（可能受影响，需人工确认）。"
    )
    assert _labels(story) == ["必改", "待查"]
    # P-19：索引缺口 / 索引完整 / gate1_rc 不进关键数字（在原始记录里）
    for hidden in ("index_gap_count", "index_complete", "gate1_rc", "cmd"):
        assert hidden not in {row["field"] for row in story["key_results"]}


def test_p19_n5_prefers_deduped_case_count_over_entry_count() -> None:
    """S2 定稿：`to_check_case_count`（去重用例数）优先；`to_check_count`（条目数）只在缺失时回退。"""
    detail = {"must_change_count": 3, "must_change_cases": ["tc_a", "tc_b", "tc_c"],
              "to_check_case_count": 6, "to_check_count": 178}
    story = _story("N5", detail=detail)
    assert story["headline"] == (
        "必改 3 个用例：tc_a、tc_b、tc_c；另有 6 个待查（可能受影响，需人工确认）。"
    )
    assert "178" not in story["headline"]
    row = _rows(story)["to_check_case_count"]
    assert row["label"] == "待查" and row["value"] == 6 and row["text"] == "6"
    # 两者都在时**不**展示条目数（避免"待查 178"）
    assert "to_check_count" not in {r["field"] for r in story["key_results"]}


def test_p19_n5_falls_back_to_entry_count_when_case_count_is_missing() -> None:
    detail = {"must_change_count": 3, "must_change_cases": ["tc_a"], "to_check_count": 178}
    story = _story("N5", detail=detail)
    assert "另有 178 个待查（可能受影响，需人工确认）。" in story["headline"]
    rows = _rows(story)
    assert rows["to_check_case_count"]["text"] == "178"  # 同一个"待查"行，回退展示
    assert "to_check_count" not in rows


def test_p19_n5_missing_to_check_count_is_said_explicitly() -> None:
    detail = {"must_change_count": 3, "must_change_cases": ["tc_a"]}
    story = _story("N5", detail=detail)
    assert story["headline"].endswith("另有待查（数量未下发）。")
    row = _rows(story)["to_check_case_count"]  # 对外稳定字段名（回退时也不改名）
    assert row["missing"] is True and row["text"] == "未下发"


def test_p20_n6_headline_lists_per_case_edits_and_validation() -> None:
    detail = {"cycle": 1, "targets": 3, "validation_ok": True, "mode": "live",
              "source": "model_live",
              "case_edits": [
                  {"case": "tc_a", "edit_count": 1, "edits": [{"line": 10}]},
                  {"case": "tc_b", "edit_count": 2, "edits": [{"line": 11}, {"line": 12}]},
              ]}
    story = _story("N6", detail=detail,
                   events=[_ev(1, "node_finished", "live", "N6", detail)])
    assert story["headline"] == (
        "改了 3 个用例：tc_a（1 处）、tc_b（2 处）；输出校验通过。"
    )
    assert _rows(story)["case_edits"]["text"] == "tc_a（1 处）、tc_b（2 处）"
    assert story["evidence_note"]["kind"] == "agent_calls"
    assert story["status_note"] == "真实模型调用"


def test_p20_n6_old_run_without_case_edits_says_the_gap() -> None:
    detail = {"cycle": 0, "targets": 3, "validation_ok": True, "mode": "standin"}
    story = _story("N6", detail=detail)
    assert story["headline"] == (
        "本轮修订目标 3 个用例；逐用例修改未下发（旧 run 的 detail 没有逐用例清单）；"
        "输出校验通过。"
    )
    assert _rows(story)["case_edits"]["missing"] is True


def test_p21_n6_apply_headline_and_applied_status_are_plain_language() -> None:
    detail = {"status": "applied", "cases": 3, "edits": 3, "source": "framework",
              "case_edits": [{"case": "tc_a", "edit_count": 1}]}
    story = _story("N6_apply", detail=detail,
                   events=[_ev(1, "node_finished", "ok", "N6_apply", detail)])
    assert story["headline"] == (
        "3 个用例共 3 处修改已写入沙箱；每条都在原文里唯一命中，改完的文件指纹已记录。"
    )
    assert _rows(story)["status"]["text"] == "已写入（applied）"
    # 事件 status 是 ok ⇒ 释义"通过"；`applied` 是**落盘状态**字段，走 glossary 的"已写入"
    assert story["status_note"] == "通过"
    assert story["status_glossary"]["applied"] == "已写入"


def test_p21_n6_apply_drill_fixture_headline_does_not_claim_new_edits() -> None:
    detail = {"status": "drill_fixture", "cases": 3, "source": "drill_fixture"}
    story = _story("N6_apply", detail=detail)
    assert story["headline"] == (
        "3 个用例写入沙箱；本次没有施加新的逐条修改（drill 夹具直接采用现成沙箱件）。"
    )


def test_p22_n7_headline_uses_compile_counts_and_lists_case_names() -> None:
    detail = {"case_count": 3, "failed_cases": [],
              "cases": [{"case": "tc_pcie_rw_02"}, {"case": "tc_pcie_rw_smoke"},
                        {"case": "tc_rtc_05"}],
              "all_ok": True, "source": "run_guarded"}
    story = _story("N7", detail=detail)
    assert story["headline"] == "3 个用例都编译通过（失败 0）。"
    rows = _rows(story)
    assert rows["case_count"]["text"] == (
        "3：tc_pcie_rw_02、tc_pcie_rw_smoke、tc_rtc_05"
    )
    # 不再重复"全部通过"这一项（P-22）
    assert "all_ok" not in {row["field"] for row in story["key_results"]}


def test_p22_n7_failed_cases_headline() -> None:
    story = _story("N7", detail={"case_count": 3, "failed_cases": ["tc_a", "tc_b"]})
    assert story["headline"] == "2 个用例编译失败。"
    assert _rows(story)["failed_cases"]["text"] == "2 个：tc_a、tc_b"


# ---------------------------------------------------------------- 切片 1｜N8 / N9 / N10 / N11 / N12


def test_p23_n8_headline_and_key_numbers_are_plain_language() -> None:
    detail = {"verdict": "pass", "cycle": 0, "limit": 3, "check_count": 9,
              "must_fix_count": 0, "source": "model_live"}
    story = _story("N8", detail=detail,
                   events=[_ev(1, "node_finished", "live", "N8", detail)])
    assert story["headline"] == (
        "复核通过：检查了 9 项，没有必须修改的地方（第 1 次复核，返工上限 3）。"
    )
    rows = _rows(story)
    assert rows["check_count"]["value"] == 9
    assert rows["must_fix_count"]["value"] == 0
    assert rows["cycle"]["text"] == "0（上限 3）"
    assert story["status_note"] == "真实模型调用"


def test_p23_n8_new_run_sentence_reads_smoothly_with_counts_and_limit() -> None:
    detail = {"verdict": "pass", "cycle": 0, "limit": 3, "check_count": 9,
              "must_fix_count": 0, "source": "model_live"}
    story = _story("N8", detail=detail,
                   events=[_ev(1, "node_finished", "live", "N8", detail)])
    assert story["headline"] == (
        "复核通过：检查了 9 项，没有必须修改的地方（第 1 次复核，返工上限 3）。"
    )
    # 不能出现"未下发"这种兜底词（数据齐了就不该退化成缺口句），也不能有双空格
    assert "未下发" not in story["headline"]
    assert "  " not in story["headline"]


def test_p23_n8_rework_headline_does_not_reuse_the_pass_sentence() -> None:
    detail = {"verdict": "rework", "cycle": 1, "limit": 3, "must_fix_count": 2}
    story = _story("N8", detail=detail,
                   events=[_ev(1, "node_finished", "rework", "N8", detail)])
    assert story["headline"] == (
        "复核不通过：2 项必须修改（第 1 次复核，返工上限 3）。"
    )
    assert "复核通过" not in story["headline"]


def test_p24_n9_headline_spells_out_both_koutou_and_the_rule() -> None:
    detail = {"cases": 3, "koutou1": 1687, "koutou2": {"UVM_ERROR": 0, "UVM_FATAL": 0},
              "job_id": "JOB-63f79d482690", "identity": {"consistent": True},
              "source": "kb_tool"}
    story = _story("N9", detail=detail,
                   events=[_ev(1, "node_finished", "fail", "N9", detail)])
    assert story["headline"] == (
        "全跑失败：口径一（日志错误标记行数）1687，"
        "口径二（UVM 报告）UVM_ERROR 0 / UVM_FATAL 0；"
        "两套口径都要为 0 才算通过 ⇒ 判失败。"
    )
    rows = _rows(story)
    assert rows["koutou1"]["label"] == "日志错误标记行数"
    assert rows["koutou2.UVM_ERROR"]["label"] == "UVM 报告 UVM_ERROR"
    assert rows["identity.consistent"]["text"] == "是"  # P-24 ④：身份一致进关键数字
    # 步骤最后一步讲清为什么失败（P-24 ⑤）
    assert story["steps"][-1]["text"] == "作业结束：日志错误标记 1687 行 ⇒ 判失败"
    assert story["status_note"] == "未通过"


def test_p24_n9_source_sentence_single_case() -> None:
    detail = {"cases": 3, "koutou1": 1687, "koutou2": {"UVM_ERROR": 0, "UVM_FATAL": 0},
              "koutou1_by_case": {"tc_pcie_rw_02": 1687, "tc_rtc_05": 0},
              "source": "kb_tool"}
    story = _story("N9", detail=detail,
                   events=[_ev(1, "node_finished", "fail", "N9", detail)])
    assert story["headline"].endswith("⇒ 判失败。（1687 行全部来自 tc_pcie_rw_02）")


def test_p24_n9_source_sentence_multiple_cases() -> None:
    detail = {"cases": 3, "koutou1": 9, "koutou2": {"UVM_ERROR": 0, "UVM_FATAL": 0},
              "koutou1_by_case": {"tc_a": 4, "tc_b": 3, "tc_c": 2, "tc_d": 0}}
    story = _story("N9", detail=detail,
                   events=[_ev(1, "node_finished", "fail", "N9", detail)])
    assert story["headline"].endswith("（分布在 3 个用例：tc_a、tc_b、tc_c）")


def test_p24_n9_source_sentence_is_omitted_when_field_missing() -> None:
    detail = {"cases": 1, "koutou1": 1687, "koutou2": {"UVM_ERROR": 0, "UVM_FATAL": 0}}
    story = _story("N9", detail=detail,
                   events=[_ev(1, "node_finished", "fail", "N9", detail)])
    assert story["headline"].endswith("⇒ 判失败。")
    assert "来自" not in story["headline"] and "分布在" not in story["headline"]


def test_p24_n9_pass_says_passed() -> None:
    detail = {"cases": 1, "koutou1": 0, "koutou2": {"UVM_ERROR": 0, "UVM_FATAL": 0}}
    story = _story("N9", detail=detail,
                   events=[_ev(1, "node_finished", "pass", "N9", detail)])
    assert story["headline"].startswith("全跑通过：")
    assert story["headline"].endswith("⇒ 判通过。")


def test_p26_n10_old_run_headline_states_the_verdict_and_the_gap() -> None:
    detail = {"cases": 3, "verdict_passed": False, "pending": 0, "source": "model_standin"}
    story = _story("N10", detail=detail,
                   events=[_ev(1, "node_finished", "fail", "N10", detail)])
    assert story["headline"] == (
        "判定未通过（verdict_passed=false）；"
        "逐用例原因未下发（旧 run 的 detail 没有这张表）。"
    )
    assert _rows(story)["verdict_passed"]["text"] == "未通过"
    assert story["evidence_note"]["kind"] == "agent_calls"


def test_p26_n10_new_run_lists_per_case_results_and_failure_buckets() -> None:
    detail = {
        "verdict_passed": False, "pending": 0,
        "cases_table": [
            {"case": "tc_pcie_rw_02", "passed": False,
             "reasons": ["日志错误标记 1687 行 ≠ 0", "缺观测点印记"]},
            {"case": "tc_rtc_05", "passed": False, "reasons": ["缺观测点印记"]},
        ],
        "classification": {"buckets": [{}] * 24, "既有缺陷": 24, "本轮引入": 0, "待裁决": 0},
    }
    story = _story("N10", detail=detail,
                   events=[_ev(1, "node_finished", "fail", "N10", detail)])
    assert story["headline"].startswith("整轮未通过：tc_pcie_rw_02 未通过（")
    assert "tc_rtc_05 未通过（缺观测点印记）" in story["headline"]
    assert story["headline"].endswith("待裁决 0 项。")
    assert _rows(story)["classification.buckets"]["text"] == (
        "24 个区间（既有缺陷 24、本轮引入 0、待裁决 0）"
    )


def test_p27_n11_headline_and_unclosed_count_are_plain_language() -> None:
    detail = {"chain": "intact", "host_consistent": True, "source": "model_live",
              "rework_requests_count": 0, "unclosed": ["印记缺失", "冻结件未核验", "待验"],
              "identity_table": [{"case": "a", "consistent": True},
                                 {"case": "b", "consistent": True},
                                 {"case": "c", "consistent": True}]}
    story = _story("N11", detail=detail,
                   events=[_ev(1, "node_finished", "intact", "N11", detail)])
    assert story["headline"] == (
        "证据链完整：3 个用例身份四处一致（run_id / 用例名 / 审的 md5 / 跑的 md5），"
        "返工请求 0 条。"
    )
    rows = _rows(story)
    assert rows["chain"]["text"] == "完整（intact）"
    assert rows["chain"]["value"] == "intact"  # 原值必须保留
    assert rows["unclosed"]["text"] == "3 条"
    assert rows["rework_requests_count"]["text"] == "0 条"
    assert story["status_note"] == "完整"


def test_p27_n11_old_detail_uses_host_consistent_for_identity_row() -> None:
    """S2 的 N11 detail 用 `host_consistent`（同义）⇒ 身份一致不能被误报成"未下发"。"""
    detail = {"chain": "intact", "host_consistent": True,
              "rework": 0, "source": "model_live"}
    story = _story("N11", detail=detail,
                   events=[_ev(1, "node_finished", "intact", "N11", detail)])
    rows = _rows(story)
    assert rows["identity.consistent"]["text"] == "是"
    assert rows["rework_requests_count"]["text"] == "0 条"


def test_p27_n11_broken_chain_headline_names_inconsistent_cases() -> None:
    detail = {"chain": "broken", "host_consistent": False, "rework_requests_count": 2,
              "identity_table": [{"case": "a", "consistent": False},
                                 {"case": "b", "consistent": True}]}
    story = _story("N11", detail=detail,
                   events=[_ev(1, "node_finished", "broken", "N11", detail)])
    assert story["headline"] == (
        "证据链不完整：1 个用例身份对不上（run_id / 用例名 / 审的 md5 / 跑的 md5），"
        "返工请求 2 条。"
    )
    assert story["status_note"] == "不完整"


def test_p28_n12_headline_says_verdict_refs_and_open_items() -> None:
    detail = {"mode": "live", "source": "model_live", "claimed_verdict": "not_passed",
              "ref_count": 18, "refs_parseable_count": 18,
              "open_items": ["用例仍待验", "冻结件未核验", "印记缺失"]}
    story = _story("N12", detail=detail,
                   events=[_ev(1, "node_finished", "live", "N12", detail)])
    assert story["headline"] == (
        "报告结论：未通过；引用 18 条证据（不可解析 0 条）；未闭环 3 项。"
    )
    rows = _rows(story)
    assert rows["claimed_verdict"]["text"] == "未通过（not_passed）"
    assert rows["refs_parseable_count"]["value"] == 18


# ---------------------------------------------------------------- P-30 未到达 / P-33 未执行


def test_p30_terminal_run_without_events_is_not_reached() -> None:
    story = _story("N14", run_status="finished")
    assert story["not_reached"] is True
    assert story["not_executed"] is False
    # R3-08：原值保留 + 中文释义（finished → 已完成）
    assert story["headline"] == "本轮没有走到这个节点（运行停在 finished，已完成）。"
    assert story["headline_source"] == "missing"
    # 未到达时正文不得出现"等它跑完"
    assert "等它跑完" not in _body_text(story)
    assert story["key_results"] == []
    assert story["evidence_note"] is None


def test_p30_non_terminal_run_without_events_is_not_reached_false() -> None:
    story = _story("N14", run_status="waiting_gate")
    assert story["not_reached"] is False
    assert story["headline"] == "这个节点还没有收尾记录（detail 为空），结果等它跑完再看。"


def test_p30_not_reached_wins_even_when_a_gate_block_is_absent() -> None:
    story = _story("N15_submit", run_status="failed", mode="real")
    assert story["not_reached"] is True and story["not_executed"] is False


def test_p33_drill_submit_node_is_not_executed_not_not_reached() -> None:
    story = _story("N15_submit", run_status="finished", mode="drill")
    # P-33：drill 不提交作业 ⇒ 未执行；不能说"没走到"、更不能说"等它跑完"
    assert story["not_executed"] is True
    assert story["not_reached"] is False
    assert "没有执行" in story["headline"] and "演示模式" in story["headline"]
    assert "等它跑完" not in _body_text(story)
    assert story["evidence_note"]["kind"] == "not_executed"
    assert story["key_results"] == []


def test_p33_submit_nodes_headline_and_step_are_plain_language() -> None:
    detail = {"job_id": "JOB-76001", "cases": 3, "source": "kb_tool"}
    for node, job_word in (("N9_submit", "全跑"), ("N15_submit", "回归")):
        story = _story(node, detail=detail,
                       events=[_ev(1, "node_finished", "ok", node, detail)])
        assert story["headline"] == (
            f"已提交{job_word}作业 JOB-76001，覆盖 3 个用例；"
            f"流程转入{'等待作业完成' if node == 'N9_submit' else '等待'}。"
        )
        assert story["steps"][0]["text"] == story["headline"].rstrip("。")
        assert story["not_executed"] is False
        assert _labels(story) == ["作业号", "覆盖用例数"]


# ---------------------------------------------------------------- P-31 / P-32 N15


def test_p31_n15_select_headline_names_cases_and_says_whether_it_really_runs() -> None:
    detail = {"count": 5, "g3": "milestone_only",
              "cases": ["tc_a", "tc_b", "tc_c", "tc_d", "tc_e"],
              "will_really_run": True, "source": "framework"}
    story = _story("N15_select", detail=detail, mode="real")
    assert story["headline"] == (
        "本轮 G3=仅里程碑：按受影响子集选出 5 个回归用例"
        "（tc_a、tc_b、tc_c、tc_d、tc_e）；会真跑这 5 个。"
    )
    rows = _rows(story)
    assert rows["g3"]["text"] == "仅里程碑（milestone_only）"
    assert rows["will_really_run"]["text"] == "是"


def test_p31_n15_select_drill_says_it_will_not_run() -> None:
    detail = {"count": 5, "g3": "milestone_only",
              "cases": ["tc_a", "tc_b", "tc_c", "tc_d", "tc_e"],
              "will_really_run": False, "source": "framework"}
    story = _story("N15_select", detail=detail, mode="drill",
                   events=[_ev(1, "node_finished", "ok", "N15_select", detail)])
    assert story["headline"].endswith("；演示模式不真跑。")
    assert _rows(story)["will_really_run"]["text"] == "否（drill 演示模式不真跑）"
    # P-31 ④：没有独立选集文件时说"记在事件里"，不误报证据缺失
    assert story["evidence_note"]["kind"] == "in_events"
    assert "事件里" in story["evidence_note"]["text"]


def test_p32_n15_drill_is_not_executed_with_no_evidence_and_no_fake_pass_count() -> None:
    detail = {"simulated": True, "executed": False, "count": 5, "job_id": None,
              "set": ["tc_a", "tc_b", "tc_c", "tc_d", "tc_e"],
              "cases": ["tc_a", "tc_b", "tc_c", "tc_d", "tc_e"], "source": "framework"}
    story = _story("N15", detail=detail, mode="drill", run_status="waiting_job",
                   events=[_ev(1, "node_finished", "ok", "N15", detail)])
    assert story["not_executed"] is True and story["not_reached"] is False
    assert story["headline"] == (
        "演示模式：不真跑回归。本轮回归集 = 5 个受影响用例"
        "（tc_a、tc_b、tc_c、tc_d、tc_e）。"
    )
    assert _rows(story)["passed"]["text"] == "—（未执行）"  # 不是"未下发"
    assert story["evidence_note"]["kind"] == "not_executed"
    assert "证据缺失" not in story["evidence_note"]["text"]


def test_p32_n15_cases_accepts_both_list_and_int() -> None:
    """host-owner 已把新 run 的 `cases` 改成用例名列表；旧 run 是计数 —— 两种都不能崩。"""
    as_list = {"executed": True, "will_really_run": True, "cases": ["tc_a", "tc_b"],
               "failed_cases": ["tc_b"], "passed": False, "job_id": "JOB-1"}
    story_list = _story("N15", detail=as_list, mode="real",
                        events=[_ev(1, "node_finished", "fail", "N15", as_list)])
    rows = _rows(story_list)
    assert rows["cases"]["text"] == "2 个：tc_a、tc_b"       # list ⇒ 名字
    assert "2 个用例" in story_list["headline"]

    as_int = {"count": 3, "passed": True, "job_id": "JOB-2"}
    story_int = _story("N15", detail=as_int, mode="real",
                       events=[_ev(1, "node_finished", "pass", "N15", as_int)])
    rows_int = _rows(story_int)
    assert rows_int["cases"]["text"] == "未下发"             # int 旧 run：没有名字就如实说
    assert rows_int["count"]["value"] == 3
    assert "3 个用例" in story_int["headline"]


def test_p32_n15_real_run_reports_counts() -> None:
    detail = {"executed": True, "simulated": False, "count": 3, "passed": 2,
              "failed_cases": ["tc_c"], "job_id": "JOB-1", "source": "kb_tool"}
    story = _story("N15", detail=detail, mode="real",
                   events=[_ev(1, "node_finished", "fail", "N15", detail)])
    assert story["not_executed"] is False
    assert story["headline"] == "回归跑完：3 个用例，通过 2，失败 1。"
    assert _rows(story)["passed"]["value"] == 2


def test_p32_n15_real_new_run_shape_keeps_verdict_bool_and_failed_cases() -> None:
    """S2 的 real detail：`passed` 是**整轮判定**（bool），失败用例在 `failed_cases`。"""
    detail = {"executed": True, "will_really_run": True, "case_count": 3,
              "cases": ["tc_a", "tc_b", "tc_c"], "passed": False,
              "failed_cases": ["tc_a", "tc_c"], "job_id": "JOB-9", "source": "kb_tool"}
    story = _story("N15", detail=detail, mode="real",
                   events=[_ev(1, "node_finished", "fail", "N15", detail)])
    assert story["headline"] == (
        "回归跑完：3 个用例，整轮判定未通过；失败 2 个（tc_a、tc_c）。"
    )
    rows = _rows(story)
    assert rows["passed"]["text"] == "否（整轮判定）"
    assert rows["failed_cases"]["text"] == "2 个：tc_a、tc_c"


def test_p26_n10_drill_shape_without_verdict_still_reports_per_case_and_buckets() -> None:
    """S2 的 drill detail 只有 both_zero，没有 verdict_passed ⇒ 不编"通过/未通过"。"""
    detail = {"both_zero": False,
              "cases_table": [{"case": "tc_a", "passed": False,
                               "reasons": ["日志错误标记 1687 行 ≠ 0"]}],
              "classification": {"buckets": 24, "既有缺陷": None, "本轮引入": None,
                                 "待裁决": None, "source": "not_classified"},
              "source": "model_standin"}
    story = _story("N10", detail=detail,
                   events=[_ev(1, "node_finished", "fail", "N10", detail)])
    assert story["headline"].startswith("整轮判定未下发：tc_a 未通过（")
    assert "整轮通过" not in story["headline"] and "整轮未通过" not in story["headline"]
    assert _rows(story)["classification.buckets"]["text"] == "24 个区间"


# ---------------------------------------------------------------- P-34 N16 / P-35 HALT


def test_p34_n16_refused_headline_explains_reason_and_dry_run() -> None:
    detail = {"rc": 3, "dry_run": True, "actor": "human:chenjunming",
              "actor_kind": "human", "source": "kb_tool",
              "reason_line": "I2：缺少 case_states.json，不得晋升",
              "stdout_tail": "…", "stderr_tail": "…", "cmd": "python -B …"}
    story = _story("N16", detail=detail,
                   events=[_ev(1, "node_finished", "refused", "N16", detail)])
    assert story["headline"] == (
        "晋升被拒：I2：缺少 case_states.json，不得晋升。"
        "本次是试运行（dry-run），没有真正落盘。"
    )
    rows = _rows(story)
    assert rows["status"]["text"] == "晋升被拒（refused）"
    assert rows["dry_run"]["text"] == "否（dry-run 试运行，不真正落盘）"
    assert rows["actor"]["value"] == "human:chenjunming"
    assert story["evidence_note"]["kind"] == "artifact"
    assert story["status_note"] == "晋升被拒"


def test_p34_n16_old_run_without_reason_line_says_the_reason_is_missing() -> None:
    detail = {"rc": 3, "dry_run": True, "actor": "human:x", "actor_kind": "human"}
    story = _story("N16", detail=detail,
                   events=[_ev(1, "node_finished", "refused", "N16", detail)])
    assert "拒绝原因未下发" in story["headline"]
    assert "本次是试运行（dry-run），没有真正落盘。" in story["headline"]
    # 退出码 / 命令留原始记录，不进关键数字
    assert "rc" not in {row["field"] for row in story["key_results"]}


def test_p35_halt_headline_and_steps_are_plain_language() -> None:
    detail = {"reason": "闸门未放行（G3=暂缓）", "source": "framework"}
    story = _story("HALT", detail=detail,
                   events=[_ev(1, "node_finished", "halted", "HALT", detail)])
    assert story["headline"] == "本轮已终止：闸门未放行（G3=暂缓）。这是合法终点，不是失败。"
    assert story["steps"][-1]["text"] == "流程终止：闸门未放行（G3=暂缓）"
    assert story["status_note"] == "已终止"
    assert story["evidence_note"]["kind"] == "in_events"
    assert _rows(story)["reason"]["text"] == "闸门未放行（G3=暂缓）"


def test_p35_halt_old_shape_uses_gate_decisions_without_internal_enums() -> None:
    detail = {"G1_diff_confirm": "confirmed", "G3_regression_decision": "defer",
              "source": "framework"}
    story = _story("HALT", detail=detail,
                   events=[_ev(1, "node_finished", "halted", "HALT", detail)])
    assert "本轮已终止：G1=已确认（confirmed）、G3=暂缓（defer）。" in story["headline"]
    assert "G3_regression_decision" not in story["headline"]
    assert "这是合法终点，不是失败。" in story["headline"]
    assert _rows(story)["reason"]["missing"] is True
    assert _rows(story)["reason"]["text"] == "未下发"


# ---------------------------------------------------------------- P-07 状态释义


def test_p07_status_glossary_is_served_and_raw_status_is_preserved() -> None:
    events = [_ev(1, "node_finished", "live", "N6", {"mode": "live",
                                                    "source": "model_live"})]
    story = _story("N6", events=events, detail=events[0]["detail"])
    # 原值必须在（不能在投影里归一成中文）
    assert story["steps"][0]["status"] == "live"
    assert story["status_note"] == "真实模型调用"
    glossary = story["status_glossary"]
    for raw, label in {
        "ok": "通过", "fail": "未通过", "live": "真实模型调用",
        "standin": "替身（非模型结论）", "intact": "完整", "broken": "不完整",
        "confirmed": "已确认", "ignored": "忽略", "disputed": "有疑义",
        "accept": "接受", "rework": "返工", "refused": "晋升被拒",
        "halted": "已终止", "applied": "已写入", "pass": "通过", "waiting": "等待中",
    }.items():
        assert glossary[raw] == label, raw


def test_p07_unknown_status_gets_no_note_but_glossary_is_still_served() -> None:
    events = [_ev(1, "node_finished", "escalated", "N8", {"verdict": "rework"})]
    story = _story("N8", events=events, detail={"verdict": "rework", "cycle": 3, "limit": 3})
    assert story["status_note"] is None
    assert story["status_glossary"]["rework"] == "返工"


# ---------------------------------------------------------------- §1.4 闸门三态（P-15/P-16/P-29/P-30）


WAITING_GATE = {
    "gate": "G2_report_accept", "state": "waiting", "cycle": 0,
    "entries_required": True,
    "decision_options": [{"value": "accept", "label": "接受", "requires_reason": False},
                         {"value": "rework", "label": "返工", "requires_reason": True}],
    "counts": {"entries": 2, "revision_points": 2, "disposed": 0, "unresolved": 1,
               "unresolved_points": 1,
               # S3 新下发（P-29 ②）：硬阻断条数 / 待验用例数 / 未清冲突（含总数）
               "hard_block": 3, "pending_cases": 3,
               "conflicts_open": 72, "conflicts_total": 126},
    "entries": [],
    "decision": None,
    "hard_block": [
        {"code": "I2_CASES_PENDING", "title": "本轮仍有 3 个用例「已修订待验」"},
        {"code": "I3_KOUTOU1_NONZERO", "title": "口径一 = 1687 ≠ 0（I3 第 4 项不成立）"},
        {"code": "I4_CONFLICTS_UNCLEARED", "title": "冲突未清零：72/126 项 blocks_release"},
    ],
    "source": "pending_interrupt",
    "note": None,
}

DECIDED_GATE = {
    "gate": "G1_diff_confirm", "state": "decided", "cycle": 0,
    "decision_options": [],
    "counts": {"entries": 1, "revision_points": 1, "disposed": 1, "unresolved": 0,
               "unresolved_points": 0},
    "entries": [],
    "decision": {"decision": "confirmed", "actor": "human:alice", "actor_kind": "human",
                 "human_signed": True, "signed_at": "2026-10-23T18:12:30+08:00",
                 "reason": "逐条核对过，没问题", "history_len": 1},
    "hard_block": [],
    "source": "decisions_ledger",
    "note": None,
}


def test_p29_waiting_gate_headline_says_waiting_and_blocks_accept() -> None:
    events = [_ev(1, "node_started", "running", "N13"),
              _ev(2, "gate_pending", "waiting", "N13",
                  {"decision_options": ["accept", "rework"]})]
    story = _story("N13", events=events, run_status="waiting_gate", gate=WAITING_GATE)
    assert story["headline"] == "等待你处理：本轮停在闸门 2（报告验收），现在不能接受。"
    assert story["not_reached"] is False
    # P-29：硬阻断逐条白话 + 数字（正文不能只写代号）
    note = story["note"]
    assert note is not None and note["level"] == "warn"
    assert "有 3 个用例改完没在全跑里验证通过" in note["text"]
    assert "日志错误标记 1687 行 ≠ 0" in note["text"]
    assert "72 条文档/RTL 冲突未清零" in note["text"]
    assert "I2_CASES_PENDING：有 3 个" in note["text"]  # 代号只作小字附注
    # 状态 chip 用 glossary 释义（waiting → 等待中）
    assert story["status_note"] == "等待中"
    assert story["evidence_note"]["kind"] == "in_events"


def test_p29_waiting_gate_key_numbers_come_from_gate_counts() -> None:
    """P-29 ②：等待态首屏就要有 硬阻断 / 待验用例 / 未清冲突（数字来自 S3 gate.counts）。"""
    story = _story("N13", run_status="waiting_gate", gate=WAITING_GATE)
    rows = _rows(story)
    assert rows["gate.counts.hard_block"]["label"] == "硬阻断"
    assert rows["gate.counts.hard_block"]["text"] == "3"
    assert rows["gate.counts.pending_cases"]["text"] == "3"
    assert rows["gate.counts.conflicts_open"]["label"] == "未清冲突"
    assert rows["gate.counts.conflicts_open"]["text"] == "72/126"
    # 等待态还没有收尾 ⇒ 不堆 decision/actor/human_signed 的"未下发"
    assert "decision" not in rows and "actor" not in rows


def test_p29_gate_counts_missing_fields_are_said_as_not_delivered() -> None:
    gate = {"gate": "G2_report_accept", "state": "waiting",
            "counts": {"entries": 2}, "entries": [], "decision": None, "hard_block": []}
    rows = _rows(_story("N13", run_status="waiting_gate", gate=gate))
    for field in ("gate.counts.hard_block", "gate.counts.pending_cases",
                  "gate.counts.conflicts_open"):
        assert rows[field]["missing"] is True, field
        assert rows[field]["text"] == "未下发", field


def test_p29_n4_gate_key_numbers_keep_zero_disposed() -> None:
    """N4：修订点 / 已处置 / 需要你确认；等待态 disposed=0 如实显示 0。"""
    gate = {"gate": "G1_diff_confirm", "state": "waiting",
            "counts": {"entries": 2, "revision_points": 2, "disposed": 0,
                       "unresolved": 1, "unresolved_points": 1},
            "entries": [], "decision": None, "hard_block": []}
    rows = _rows(_story("N4", run_status="waiting_gate", gate=gate))
    assert rows["gate.counts.revision_points"]["label"] == "修订点"
    assert rows["gate.counts.revision_points"]["text"] == "2"
    assert rows["gate.counts.disposed"]["text"] == "0"
    assert rows["gate.counts.disposed"]["missing"] is False
    assert rows["gate.counts.unresolved_points"]["label"] == "需要你确认"
    assert rows["gate.counts.unresolved_points"]["text"] == "1"


def test_p15_decided_gate_evidence_note_shows_wait_duration() -> None:
    """P-15：闸门节点的"用时"是**等人签署**的时长（gate_pending.ts → gate_decided.ts）。"""
    decided_at = 1000.0 + 4398  # 4398s ≈ 1 小时 13 分
    events = [
        _ev(1, "gate_pending", "waiting", "N14",
            {"decision_options": ["full_now", "subset_only", "milestone_only", "defer"]},
            ts=1000.0),
        _ev(2, "gate_decided", "milestone_only", "N14",
            {"decision": "milestone_only", "actor": "human:alice",
             "signed_at": "2026-10-23T18:12:30+08:00"}, ts=decided_at),
        _ev(3, "node_finished", "milestone_only", "N14",
            {"decision": "milestone_only", "actor": "human:alice"}, ts=decided_at),
    ]
    story = _story("N14", events=events, run_status="waiting_job", gate=DECIDED_GATE_SHAPE)
    assert story["evidence_note"]["text"] == (
        "签署记录在 gates.json（等待人签署 1 小时 13 分；"
        "签署时间 2026-10-23T18:12:30+08:00）。"
    )


def test_p15_decided_gate_without_pending_event_does_not_guess_duration() -> None:
    events = [
        _ev(1, "gate_decided", "confirmed", "N4",
            {"decision": "confirmed", "actor": "human:alice",
             "signed_at": "2026-10-23T18:12:30+08:00"}, ts=1000.0),
        _ev(2, "node_finished", "confirmed", "N4",
            {"decision": "confirmed", "actor": "human:alice"}, ts=1100.0),
    ]
    story = _story("N4", events=events, run_status="waiting_job", gate=DECIDED_GATE)
    assert "等待人签署" not in story["evidence_note"]["text"]
    assert "签署时间 2026-10-23T18:12:30+08:00" in story["evidence_note"]["text"]


def test_p29_waiting_gate_without_hard_block_has_no_accept_warning_and_no_note() -> None:
    gate = dict(WAITING_GATE, gate="G1_diff_confirm", hard_block=[])
    story = _story("N4", events=[_ev(1, "node_started", "running", "N4")],
                   run_status="waiting_gate", gate=gate)
    assert story["headline"] == "等待你处理：本轮停在闸门 1（差异确认）。"
    assert "现在不能接受" not in story["headline"]
    assert story["note"] is None


#: 已决策闸门块（G3 形状；headline/证据入口测试复用）
DECIDED_GATE_SHAPE = {
    "gate": "G3_regression_decision", "state": "decided", "cycle": 0,
    "decision_options": [],
    "counts": {"entries": 1, "revision_points": 1, "disposed": 1, "unresolved": 0,
               "unresolved_points": 0, "hard_block": 0, "pending_cases": 0,
               "conflicts_open": 0, "conflicts_total": 126},
    "entries": [],
    "decision": {"decision": "milestone_only", "actor": "human:alice",
                 "actor_kind": "human", "human_signed": True,
                 "signed_at": "2026-10-23T18:12:30+08:00",
                 "reason": "I4 未清零", "history_len": 1},
    "hard_block": [], "source": "decisions_ledger", "note": None,
}


def test_p16_decided_gate_headline_shows_actor_reason_and_no_internal_words() -> None:
    detail = {"gate": "G1_diff_confirm", "decision": "confirmed", "actor": "human:alice",
              "human_signed": True, "branch": "G1_CONFIRMED", "source": "human_gate",
              "summary": "N4 G1_diff_confirm：决策 confirmed，已由人签署（human_signed=true）"}
    story = _story("N4", events=[_ev(1, "node_finished", "confirmed", "N4", detail)],
                   detail=detail, run_status="waiting_job", gate=DECIDED_GATE)
    assert story["headline"] == (
        "人已确认差异清单（confirmed 已确认），签署人 human:alice，"
        "理由：逐条核对过，没问题。"
    )
    # P-16：内部词 / 事件名不进 headline
    for internal in ("human_signed", "G1_CONFIRMED", "branch", "G1_diff_confirm"):
        assert internal not in story["headline"], internal
    # P-15：人工理由与签署时间可见（签署时间在证据入口）
    assert "2026-10-23T18:12:30+08:00" in story["evidence_note"]["text"]
    rows = _rows(story)
    assert rows["decision"]["text"] == "已确认（confirmed）"
    assert rows["human_signed"]["text"] == "是"


def test_p16_decided_gate_without_reason_says_record_had_no_reason() -> None:
    gate = copy.deepcopy(DECIDED_GATE)
    gate["decision"]["reason"] = None
    story = _story("N4", detail={"decision": "confirmed", "actor": "human:alice",
                                 "human_signed": True},
                   run_status="waiting_job", gate=gate)
    assert "理由：未填写（原记录无理由）。" in story["headline"]


def test_p30_g3_milestone_only_and_defer_get_their_explanation() -> None:
    milestone = copy.deepcopy(DECIDED_GATE)
    milestone.update(gate="G3_regression_decision")
    milestone["decision"].update(decision="milestone_only", reason="I4 未清零")
    story = _story("N14", detail={"decision": "milestone_only"}, run_status="waiting_job",
                   gate=milestone)
    assert "人已决定回归策略（milestone_only 仅里程碑）" in story["headline"]
    assert "（按受影响子集跑回归后晋升，不要求冲突清零）。" in story["headline"]

    defer = copy.deepcopy(milestone)
    defer["decision"].update(decision="defer", reason="本轮不发版")
    halted = _story("N14", detail={"decision": "defer"}, run_status="finished", gate=defer)
    assert "（本轮显式终止）。" in halted["headline"]


def test_gate_no_material_headline_says_material_is_missing() -> None:
    gate = {"gate": "G3_regression_decision", "state": "no_material",
            "counts": {}, "entries": [], "decision": None, "hard_block": [],
            "note": "差异清单未下发（界面不编条目）"}
    story = _story("N14", run_status="waiting_gate", gate=gate)
    assert story["headline"] == "闸门材料未下发：差异清单未下发（界面不编条目）。"
    assert story["headline_source"] == "missing"
    assert story["not_reached"] is False


def test_gate_no_material_still_prefers_a_decision_that_exists_in_detail() -> None:
    """S3 说"没材料"，但节点已收尾且 detail 有整门决策 ⇒ 先说决策，不说"材料未下发"。"""
    gate = {"gate": "G3_regression_decision", "state": "no_material",
            "counts": {}, "entries": [], "decision": None, "hard_block": [],
            "note": "差异清单未下发（界面不编条目）"}
    detail = {"decision": "milestone_only", "actor": "human:alice", "human_signed": True,
              "source": "human_gate"}
    story = _story("N14", detail=detail,
                   events=[_ev(1, "node_finished", "milestone_only", "N14", detail)],
                   run_status="waiting_job", gate=gate)
    assert story["headline"].startswith("人已决定回归策略（milestone_only 仅里程碑）")
    assert "签署人 human:alice" in story["headline"]
    assert "材料未下发" not in story["headline"]


def test_gate_node_waiting_without_gate_block_still_says_waiting_from_events() -> None:
    """S3 闸门块缺失时也不许说"等它跑完"：事件流里 gate_pending 就足以说"在等人工"。"""
    events = [_ev(1, "node_started", "running", "N4"),
              _ev(2, "gate_pending", "waiting", "N4",
                  {"decision_options": ["confirmed", "ignored", "disputed"]})]
    story = _story("N4", events=events, run_status="waiting_gate")
    assert story["headline"] == "等待你处理：本轮停在闸门 1（差异确认）。"
    assert "等它跑完" not in _body_text(story)


def test_gate_block_is_passed_through_unchanged() -> None:
    story = _story("N13", run_status="waiting_gate", gate=WAITING_GATE)
    assert story["gate"] == WAITING_GATE
    story2 = _story("N13", run_status="waiting_gate", gate=None)
    assert story2["gate"] is None


def test_gate_node_decided_from_detail_without_gate_block_keeps_raw_decision() -> None:
    detail = {"gate": "G1_diff_confirm", "decision": "confirmed", "actor": "human:alice",
              "human_signed": True, "source": "human_gate"}
    story = _story("N4", events=[_ev(1, "node_finished", "confirmed", "N4", detail)],
                   detail=detail, run_status="waiting_job")
    assert "人已确认差异清单（confirmed 已确认）" in story["headline"]
    assert "签署人 human:alice" in story["headline"]
    assert "理由：未下发" in story["headline"]  # 没有 gate 块就不谎称"原记录无理由"


# ---------------------------------------------------------------- 失败节点 / 正文不含 seq


def test_failed_node_never_says_completed() -> None:
    detail = {"message": "夹具缺 n2_diff.json", "source": "drill_fixture"}
    story = _story("N2", events=[_ev(1, "node_failed", "failed", "N2", detail)],
                   detail=detail, run_status="failed")
    assert story["headline"] == "失败：夹具缺 n2_diff.json。"
    assert story["steps"][-1]["text"] == "失败：夹具缺 n2_diff.json"
    body = _body_text(story)
    assert "完成" not in body
    # P-07：`failed`（node_failed 的原值）也要有释义，原值仍原样留在 chip/steps
    assert story["status_note"] == "失败"
    assert story["status_glossary"]["failed"] == "失败"
    assert story["evidence_note"] is None


def test_failed_node_without_error_text_states_the_gap() -> None:
    story = _story("N9", events=[_ev(1, "node_failed", "failed", "N9")],
                   run_status="failed")
    assert story["headline"].startswith("失败：原因未下发")
    assert "完成" not in _body_text(story)


def test_body_never_contains_seq_but_steps_keep_it_for_the_raw_section() -> None:
    events = [_ev(1, "node_started", "running", "N9"),
              _ev(2, "admission_granted", "ok", "N9", {"job_id": "JOB-1"}),
              _ev(3, "job_submitted", "running", "N9",
                  {"job_id": "JOB-1", "cases": ["a", "b", "c"]}),
              _ev(4, "job_finished", "fail", "N9", {"job_id": "JOB-1", "koutou1": 1687}),
              _ev(5, "node_finished", "fail", "N9", {"koutou1": 1687})]
    story = _story("N9", events=events, detail={"koutou1": 1687})
    assert [step["seq"] for step in story["steps"]] == [1, 2, 3, 4, 5]
    body = _body_text(story)
    for token in ("seq", "#1", "#2", "#5"):
        assert token not in body, token


# ---------------------------------------------------------------- N0 / drill 措辞（P-01）


def test_p01_n0_headline_and_fixture_count_by_mode() -> None:
    drill = _story("N0", detail={"mode": "drill", "baseline": "v0", "fixture_files": 11,
                                 "gate_init_rc": 0, "source": "drill_fixture"})
    assert drill["headline"] == "工作目录已准备好：基线 v0，运行模式 drill。"
    assert _rows(drill)["fixture_files"]["text"] == "11"

    real = _story("N0", detail={"mode": "real", "baseline": "v0", "fixture_files": 0,
                                "gate_init_rc": 0, "source": "kb_tool"})
    assert _rows(real)["fixture_files"]["text"] == "0（真实运行不复制预置文件）"


def test_n0_uses_run_mode_parameter_when_detail_has_none() -> None:
    story = _story("N0", detail={"baseline": "v0"}, mode="drill")
    assert story["headline"] == "工作目录已准备好：基线 v0，运行模式 drill。"


def test_n0_missing_baseline_is_said_as_not_delivered() -> None:
    story = _story("N0", detail={"mode": "drill"})
    assert "基线 未下发" in story["headline"]
    assert _rows(story)["baseline"]["missing"] is True


# ---------------------------------------------------------------- R3-03 N6 观测点（P-25 第二半）
#
# 契约（impl plan §1.1）：`story.observation_points` 是 N6 `detail.observation_points` 的
# **确定性透传**；`null` = 未下发（旧 run / drill / standin），`[]` = 下发了但 0 条。

N6_OBSERVATION_POINTS = [
    {"case": "tc_pcie_rw_02", "marker": "N6_fpga_date", "addr": "0x0000",
     "offset": "0x04", "expected_value": "0x20260708"},
    {"case": "tc_rtc_05", "marker": "N6_rtc_ctrl", "addr": "0x0100",
     "offset": "0x08", "expected_value": "0x00000001"},
]


def test_r3_03_n6_observation_points_are_passed_through_in_order() -> None:
    detail = {"cycle": 1, "targets": 2, "validation_ok": True, "mode": "live",
              "source": "model_live",
              "case_edits": [{"case": "tc_pcie_rw_02", "edit_count": 1}],
              "observation_points": copy.deepcopy(N6_OBSERVATION_POINTS)}
    before = copy.deepcopy(detail)
    story = _story("N6", detail=detail,
                   events=[_ev(1, "node_finished", "live", "N6", detail)])
    # 原样逐条透传（顺序、字段名、值都不改；不改写入参）
    assert story["observation_points"] == N6_OBSERVATION_POINTS
    assert detail == before, "投影不得改写入参"
    row = _rows(story)["observation_points"]
    assert row["field"] == "observation_points" and row["label"] == "观测点"
    assert row["value"] == 2
    assert row["text"] == "2 条（逐条见下）"
    assert row["missing"] is False
    assert _labels(story)[-1] == "观测点"


def test_r3_03_n6_without_observation_points_says_not_delivered() -> None:
    detail = {"cycle": 0, "targets": 3, "validation_ok": True, "mode": "standin",
              "source": "model_standin"}
    story = _story("N6", detail=detail)
    # N6 一定有这个 key（旧 run/替身 ⇒ null），前端据此渲染"未下发"一行
    assert "observation_points" in story and story["observation_points"] is None
    row = _rows(story)["observation_points"]
    assert row["value"] == "未下发"
    assert row["text"] == "未下发（旧 run 或替身，模型未产出观测点）"
    assert row["missing"] is True


def test_r3_03_n6_explicit_null_is_not_delivered_but_empty_list_is_zero() -> None:
    null_story = _story("N6", detail={"targets": 1, "observation_points": None})
    assert null_story["observation_points"] is None
    assert _rows(null_story)["observation_points"]["missing"] is True

    empty_story = _story("N6", detail={"targets": 1, "observation_points": []})
    # 下发了 0 条 ≠ 未下发：不能拿 None 冒充
    assert empty_story["observation_points"] == []
    row = _rows(empty_story)["observation_points"]
    assert row["value"] == 0 and row["missing"] is False


def test_r3_03_observation_points_key_is_only_emitted_on_n6() -> None:
    """R3-03（Lead 追加）：非 N6 **不出现该 key**（前端 hasOwnProperty ⇒ 不渲染该块）。"""
    n6 = _story("N6", detail={"targets": 1})
    assert "observation_points" in n6 and n6["observation_points"] is None

    for node, detail in (
        ("N0", {"mode": "real", "baseline": "v0"}),
        ("N2", {"has_change": False, "diffs": []}),
        ("N7", {"case_count": 1, "failed_cases": [], "cases": [{"case": "tc_a"}]}),
        ("N9", {"koutou1": 0, "cases_detail": [{"case": "tc_a"}]}),
        ("N15_submit", {"job_id": "JOB-1", "cases": 1}),
        ("N77", {"summary": "未来节点"}),
    ):
        story = _story(node, detail=detail, purpose=None)
        assert "observation_points" not in story, node
        assert "observation_points" not in _rows(story), node


# ---------------------------------------------------------------- R3-06 证据按用例分组
#
# 契约（impl plan §1.2）：仅 N9/N7 分组；组内 refs 空 ⇒ note 说明；用例名不可知 /
# 一条 ref 都归不到 ⇒ `[]` + `evidence_groups_note`；其余节点 `null`（前端平铺 refs）。

N9_CASES_DETAIL = [
    {"case": "tc_pcie_rw_02", "koutou1": 3, "uvm_error": 0, "uvm_fatal": 0,
     "passed": False},
    {"case": "tc_pcie_rw_smoke", "koutou1": 0, "uvm_error": 0, "uvm_fatal": 0,
     "passed": True},
    {"case": "tc_rtc_05", "koutou1": 0, "uvm_error": 0, "uvm_fatal": 0,
     "passed": True},
]


def test_r3_06_n9_groups_evidence_by_case_and_notes_cases_without_refs() -> None:
    events = [
        _ev(1, "node_started", "running", "N9"),
        _ev(2, "job_finished", "fail", "N9", {"job_id": "JOB-1"},
            refs=("logs/RUN-TEST-0001_tc_pcie_rw_02_1_run.log",
                  "logs/RUN-TEST-0001_tc_pcie_rw_smoke_1_run.log")),
        _ev(3, "node_finished", "fail", "N9",
            {"cases_detail": copy.deepcopy(N9_CASES_DETAIL), "koutou1": 3,
             "koutou2": {"UVM_ERROR": 0, "UVM_FATAL": 0}}),
    ]
    story = _story("N9", events=events, detail=events[2]["detail"])
    groups = story["evidence_groups"]
    assert [group["case"] for group in groups] == [
        "tc_pcie_rw_02", "tc_pcie_rw_smoke", "tc_rtc_05"]
    assert groups[0]["refs"] == ["logs/RUN-TEST-0001_tc_pcie_rw_02_1_run.log"]
    assert groups[0]["note"] is None
    assert groups[1]["refs"] == ["logs/RUN-TEST-0001_tc_pcie_rw_smoke_1_run.log"]
    assert groups[1]["note"] is None
    # 没有证据件的用例组：空 refs + 一句说明（不留空白，也不说"缺失"）
    assert groups[2]["refs"] == []
    assert groups[2]["note"] == "本轮未执行/无证据"
    assert story["evidence_groups_note"] is None


def test_r3_06_n9_without_case_names_returns_empty_groups_with_reason() -> None:
    events = [_ev(1, "job_finished", "fail", "N9", {"job_id": "JOB-1"},
                  refs=("logs/RUN-TEST-0001_tc_pcie_rw_02_1_run.log",))]
    story = _story("N9", events=events, detail={"koutou1": 3})
    assert story["evidence_groups"] == []
    assert "没有列出用例名" in story["evidence_groups_note"]
    assert "缺失" not in story["evidence_groups_note"]


def test_r3_06_n9_without_cases_and_refs_says_no_evidence_files() -> None:
    story = _story("N9", detail={"koutou1": 0})
    assert story["evidence_groups"] == []
    assert story["evidence_groups_note"] == (
        "本轮没有证据文件（服务端未列出用例，也没有可展示的证据件）"
    )


def test_r3_06_n7_groups_by_listed_case_names() -> None:
    detail = {"case_count": 2, "failed_cases": [],
              "cases": [{"case": "tc_pcie_rw_02"}, {"case": "tc_rtc_05"}]}
    events = [_ev(1, "node_finished", "ok", "N7", detail,
                  refs=("evidence/RUN-TEST-0001_tc_pcie_rw_02_1_compile.log",))]
    story = _story("N7", events=events, detail=detail)
    groups = story["evidence_groups"]
    assert [group["case"] for group in groups] == ["tc_pcie_rw_02", "tc_rtc_05"]
    assert groups[0]["refs"] == ["evidence/RUN-TEST-0001_tc_pcie_rw_02_1_compile.log"]
    assert groups[1]["refs"] == []
    assert groups[1]["note"] == "本轮没有这个用例的证据文件"


def test_r3_06_n7_without_case_names_returns_empty_groups() -> None:
    """真实 N7 的 `cases` 是计数而非名字 ⇒ 用例名不可知，不编组但说明原因。"""
    detail = {"case_count": 3, "failed_cases": [], "cases": 3}
    story = _story("N7", detail=detail,
                   events=[_ev(1, "node_finished", "ok", "N7", detail,
                               refs=("evidence/RUN-TEST-0001_tc_a_1.log",))])
    assert story["evidence_groups"] == []
    assert story["evidence_groups_note"].startswith("服务端没有列出用例名")


def test_r3_06_unattributable_refs_return_empty_groups_with_reason() -> None:
    detail = {"case_count": 1, "failed_cases": [], "cases": [{"case": "tc_pcie_rw_02"}]}
    story = _story("N7", detail=detail,
                   events=[_ev(1, "node_finished", "ok", "N7", detail,
                               refs=("evidence/other_case.log",))])
    assert story["evidence_groups"] == []
    assert "1 个用例都没有可归属的证据件" in story["evidence_groups_note"]


def test_r3_06_non_group_nodes_keep_flat_refs_semantics() -> None:
    detail = {"must_change_count": 1}
    story = _story("N5", detail=detail,
                   events=[_ev(1, "node_finished", "ok", "N5", detail,
                               refs=("evidence/n5_impact.json",))])
    assert story["evidence_groups"] is None
    assert story["evidence_groups_note"] is None


def test_r3_06_display_refs_filter_out_paths_outside_the_run_dir() -> None:
    """SPEC-04 §6.7：分组只能取面板平铺展示的 refs（run 目录内），不得把目录外路径分进组。"""
    in_dir = "/runs/RUN-TEST-0001/logs/RUN-TEST-0001_tc_pcie_rw_02_1_run.log"
    out_dir = "/tmp/loop/state/jobs/JOB-1_tc_pcie_rw_02.log"  # basename 也含用例名，但目录外
    detail = {"koutou1": 1, "cases_detail": [{"case": "tc_pcie_rw_02"}]}
    events = [_ev(1, "job_finished", "fail", "N9", {"job_id": "JOB-1"},
                  refs=(out_dir, in_dir))]
    # 不传 refs（旧行为）：事件里的两条都能参与分组
    unfiltered = _story("N9", events=events, detail=detail)
    assert unfiltered["evidence_groups"][0]["refs"] == [out_dir, in_dir]

    # 传了展示 refs（node_view 已按 run 目录过滤）⇒ 组内只留 run 目录内的那一条
    filtered = _story("N9", events=events, detail=detail, refs=[in_dir])
    assert filtered["evidence_groups"][0]["refs"] == [in_dir]
    assert out_dir not in json.dumps(filtered["evidence_groups"], ensure_ascii=False)


def test_r3_06_display_refs_drive_the_attribution_fallback() -> None:
    """传了展示 refs 时，"一条都归不到"的判定同口径（只有目录外 refs ⇒ 不编组 + 原因）。"""
    out_dir = "/tmp/loop/state/jobs/JOB-1_tc_pcie_rw_02.log"
    detail = {"koutou1": 1, "cases_detail": [{"case": "tc_pcie_rw_02"}]}
    events = [_ev(1, "job_finished", "fail", "N9", {"job_id": "JOB-1"}, refs=(out_dir,))]
    story = _story("N9", events=events, detail=detail, refs=[])
    assert story["evidence_groups"] == []
    assert "1 个用例都没有可归属的证据件" in story["evidence_groups_note"]


# ---------------------------------------------------------------- R3-08 未到达态中文释义


def test_r3_08_not_reached_headline_keeps_raw_status_and_adds_gloss() -> None:
    failed = _story("N14", run_status="failed")
    assert failed["headline"] == "本轮没有走到这个节点（运行停在 failed，失败）。"
    assert failed["headline_source"] == "missing"
    # R1 硬规则：未到达正文不得出现"等它跑完"
    assert "等它跑完" not in _body_text(failed)

    finished = _story("N15_submit", run_status="finished", mode="real")
    assert finished["headline"] == "本轮没有走到这个节点（运行停在 finished，已完成）。"
    assert "等它跑完" not in _body_text(finished)


def test_r3_08_every_terminal_run_status_has_a_gloss() -> None:
    for run_status in node_story.TERMINAL_RUN_STATUSES:
        assert node_story.STATUS_GLOSSARY.get(run_status), run_status


def test_r3_08_not_reached_without_gloss_keeps_the_plain_sentence(monkeypatch) -> None:
    """gloss 缺失时不硬加（原值仍保留）——用临时删表项验证兜底分支。"""
    monkeypatch.delitem(node_story.STATUS_GLOSSARY, "finished")
    story = _story("N14", run_status="finished")
    assert story["headline"] == "本轮没有走到这个节点（运行停在 finished）。"
    assert "等它跑完" not in _body_text(story)


# ---------------------------------------------------------------- R3-10 提前终止下的未执行归因


def test_r3_10_halted_drill_submit_uses_neutral_wording() -> None:
    story = _story("N15_submit", run_status="failed", mode="drill", run_halted=True)
    assert story["not_executed"] is True and story["not_reached"] is False
    assert story["headline"] == "本轮未执行这个节点（没有提交记录）。"
    assert story["evidence_note"] == {
        "text": "本轮未执行这个节点：没有提交记录，因此没有证据文件。",
        "kind": "not_executed",
    }
    # R3-10：归因是"没有提交记录"，不得再说"演示模式"
    assert "演示模式" not in _body_text(story)


def test_r3_10_not_halted_drill_submit_keeps_p33_wording() -> None:
    story = _story("N15_submit", run_status="finished", mode="drill")
    assert story["not_executed"] is True
    assert story["headline"] == "演示模式下不提交作业：本轮这个节点没有执行。"
    assert story["evidence_note"]["text"] == (
        "本轮未执行这个节点：演示模式不提交作业，因此没有证据文件。"
    )


def test_r3_10_run_halted_only_affects_drill_skipped_nodes() -> None:
    detail = {"claimed_verdict": "pass", "ref_count": 1}
    events = [_ev(1, "node_finished", "live", "N12", detail)]
    without = _story("N12", events=events, detail=detail)
    with_halt = _story("N12", events=events, detail=detail, run_halted=True)
    assert json.dumps(without, sort_keys=True, ensure_ascii=False) == \
        json.dumps(with_halt, sort_keys=True, ensure_ascii=False)
    assert "run_halted" not in with_halt


# ---------------------------------------------------------------- R3-09 drill 下 submit / 编译细节
#
# detail 字段由 host-owner 在 drill 路径补（`N9_submit.cases` / `N7.case_count`）；
# 这里用契约形状的 detail 固定 story 的消费行为（字段存在即用，缺失走既有回退）。


def test_r3_09_drill_n9_submit_headline_reports_case_coverage() -> None:
    detail = {"job_id": "JOB-76001", "cases": 1, "source": "drill_fixture",
              "scenario": "ok"}
    story = _story("N9_submit", detail=detail,
                   events=[_ev(1, "node_finished", "ok", "N9_submit", detail)])
    assert story["headline"] == (
        "已提交全跑作业 JOB-76001，覆盖 1 个用例；流程转入等待作业完成。"
    )
    assert "覆盖用例数未下发" not in story["headline"]


def test_r3_09_drill_n7_headline_reports_compiled_case_count() -> None:
    detail = {"cases": [{"case": "drill", "rc": 0, "source": "drill_fixture"}],
              "case_count": 1, "failed_cases": [], "all_ok": True,
              "source": "drill_fixture", "check_c_present": True}
    story = _story("N7", detail=detail,
                   events=[_ev(1, "node_finished", "ok", "N7", detail)])
    assert story["headline"] == "1 个用例都编译通过（失败 0）。"


def test_r3_09_drill_n7_without_case_count_falls_back_to_delivered_cases() -> None:
    """host 还没补 `case_count` 时：drill 的 `cases` 对象列表仍能回退算出 1 个（不编数字）。"""
    detail = {"cases": [{"case": "drill", "rc": 0, "source": "drill_fixture"}],
              "failed_cases": [], "source": "drill_fixture"}
    story = _story("N7", detail=detail,
                   events=[_ev(1, "node_finished", "ok", "N7", detail)])
    assert story["headline"] == "1 个用例都编译通过（失败 0）。"


# ---------------------------------------------------------------- R3-15 GATE_NODES 单一来源


def test_r3_15_gate_nodes_come_from_the_single_registry() -> None:
    from services import node_registry

    assert node_story.GATE_NODES is node_registry.GATE_NODES
    assert node_story.GATE_NODES == frozenset({"N4", "N13", "N14"})
    # 模块级别名仍在，外部 `node_story.GATE_NODES` 引用不破裂
    assert "GATE_NODES" in node_story.__all__


# ---------------------------------------------------------------- 与 node_view 集成


def test_node_detail_projection_carries_the_extended_story() -> None:
    events = [
        _ev(1, "node_started", "running", "N0"),
        _ev(2, "node_finished", "ok", "N0", {
            "mode": "real", "fixture_files": 0, "gate_init_rc": 0,
            "baseline": "v0", "source": "kb_tool", "summary": "N0：初始化完成",
        }),
    ]
    got = node_view.build_node_detail(RUN_ID, "N0", events=events)
    story = got["story"]
    assert story["purpose"] == node_view.NODE_CATALOG["N0"]["purpose"]
    assert story["headline"] == "工作目录已准备好：基线 v0，运行模式 real。"
    assert [step["text"] for step in story["steps"]] == [
        "开始执行", "工作目录已准备好（基线 v0，模式 real）",
    ]
    rows = {row["field"]: row["text"] for row in story["key_results"]}
    assert rows["baseline"] == "v0"
    assert rows["fixture_files"] == "0（真实运行不复制预置文件）"
    # 原始字段不受 story 影响
    assert got["detail"]["baseline"] == "v0"
    assert [event["seq"] for event in got["events"]] == [2, 1]
    # 同一输入逐字节相同（确定性）
    again = node_view.build_node_detail(RUN_ID, "N0", events=events)
    assert json.dumps(got, sort_keys=True, ensure_ascii=False) == \
        json.dumps(again, sort_keys=True, ensure_ascii=False)


def test_not_started_node_has_no_evidence_promise() -> None:
    """节点还没有任何事件 ⇒ 不承诺"记录在 Agent 工作窗口 / 事件里"（不编证据入口）。"""
    story = _story("N12", run_status="waiting_gate")
    assert story["evidence_note"] is None
    assert "还没有收尾记录" in story["headline"]


def test_node_detail_projection_without_run_status_keeps_not_reached_false() -> None:
    got = node_view.build_node_detail(RUN_ID, "N14", events=[])
    assert got["story"]["not_reached"] is False
    assert got["story"]["not_executed"] is False
    assert got["story"]["gate"] is None
