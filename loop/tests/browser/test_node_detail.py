"""SPEC-REV-01 R4/R2/R5 + SPEC-REV-02 R1/§R2/§4 前端验收：节点面板人话优先、闸门二级清单、报告只读。

真实静态页 + 受控 API（不模拟人工签署证据）：
  · 节点 chip → 独立 <dialog> 出现 → Esc 关闭 → 焦点回到 chip；
  · 首屏是「这一步做什么 / 结果 / 关键数字 / 过程」；原始事件与 seq 默认收起，展开才可见；
  · 「结果」显示 story.headline；summary 原文移到「原始记录」；story.note 是首屏黄条；
  · 状态 chip 保留服务端原值 + 中文释义（步骤 chip 同样带 glossary 释义）；
  · 未到达 / 未执行不再说「等它跑完」；evidence_note 指向 Agent 工作窗口时不报「证据缺失」；
  · 闸门区：共 N 条修订点 / 已处置 M 条、逐条一行、前后对比浮窗（两栏 + hunk 行号）、
    逐条处置写入共享草稿（window.GateDraftBridge），未处置时提示、已决策只读；
  · 浮窗宽 ≥ 80% 视口、窄屏全屏；Esc 只关上层、焦点回触发按钮；
  · N12 报告全文只读浮窗（GET /api/runs/{run_id}/report）；
  · 面板内不产生任何 POST；窄屏无页面横向溢出。
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlsplit

import pytest

from test_run_sessions import ui, static_url, select, tick, release, pw  # noqa: F401

GATE = "G1_diff_confirm"
G2 = "G2_report_accept"
G3 = "G3_regression_decision"
ENTRY_ID = "RTL/pcie_register.v"
DOC_ID = "doc/interface.md"

DEFAULT_GLOSSARY = {
    "ok": "通过", "fail": "未通过", "live": "真实模型调用", "standin": "替身（非模型结论）",
    "intact": "完整", "broken": "不完整", "confirmed": "已确认", "ignored": "忽略",
    "disputed": "有疑义", "accept": "接受", "rework": "返工", "refused": "晋升被拒",
    "halted": "已终止", "applied": "已写入", "pass": "通过", "waiting": "等待中",
    "failed": "未通过", "not_reached": "未到达",
}


def story_for(node="N1", *, purpose="给当前代码和文档拍一张快照：多少文件、什么指纹、哪些用例，作为对比起点。",
              steps=None, key_results=None, headline="快照完成：3374 个文件，冻结 162 个用例。",
              headline_source="template", note=None, not_reached=False, not_executed=False,
              evidence_note=None, status_note=None, status_glossary=None):
    """与 `services.node_story.build_story` 同形的展示投影（契约 §1）。"""
    return {
        "purpose": purpose,
        "headline": headline,
        "headline_source": headline_source,
        "note": note,
        "not_reached": not_reached,
        "not_executed": not_executed,
        "evidence_note": evidence_note,
        "status_note": status_note,
        "status_glossary": dict(status_glossary or DEFAULT_GLOSSARY),
        "steps": steps if steps is not None else [
            {"seq": 4, "at": 1792650932.891, "kind": "node_started", "status": "running", "text": "开始执行"},
            {"seq": 5, "at": 1792650933.5, "kind": "node_finished", "status": "ok", "text": "结束，状态 ok"},
        ],
        "key_results": key_results if key_results is not None else [
            {"field": "artifact", "label": "清单文件", "value": "/kb/runs/A/n1_manifest_new.json",
             "text": "n1_manifest_new.json", "missing": False},
            {"field": "parent", "label": "父基线", "value": "v0", "text": "v0", "missing": False},
        ],
    }


def node_detail(node="N1", **overrides):
    data = {
        "run_id": "A", "node": node, "known": True, "kind": "host",
        "name": "输入摄取", "owner": "Host", "status": "ok",
        "started_at": 1792650932.891, "finished_at": 1792650933.5,
        "source": "drill_fixture",
        "summary": "N1：v0→v1，manifest 已产出",
        "detail": {"artifact": "/kb/runs/A/n1_manifest_new.json", "parent": "v0",
                   "allfiles_count": 3374, "cases_frozen": 162},
        "refs": ["/kb/runs/A/n1_manifest_new.json"],
        "events": [
            {"seq": 4, "kind": "node_started", "node": node, "status": "running",
             "ts": 1792650932.891},
            {"seq": 5, "kind": "node_finished", "node": node, "status": "ok",
             "ts": 1792650933.5, "detail": {"source": "drill_fixture"},
             "refs": ["/kb/runs/A/n1_manifest_new.json"]},
        ],
        "missing_fields": ["manifest_entries"],
        "authority": "projection",
        "story": story_for(node),
        # 契约 §2：run 投影新增字段（S3）
        "run_status": "waiting_gate",
        "run_terminal": False,
        "node_started_present": True,
        "gate": None,
        "report": None,
    }
    data.update(overrides)
    return data


def failed_detail(node="N9_submit"):
    return {
        "run_id": "A", "node": node, "known": True, "kind": "host",
        "name": "提交全跑", "owner": "Host", "status": "failed",
        "started_at": 1792650940.0, "finished_at": 1792650941.0,
        "source": "kb_tool", "summary": "提交失败：模拟器不可用",
        "detail": {"error": "模拟器启动失败：UVS_LICENSE 未设置"},
        "refs": [],
        "events": [
            {"seq": 11, "kind": "node_started", "node": node, "status": "running",
             "ts": 1792650940.0},
            {"seq": 12, "kind": "node_failed", "node": node, "status": "failed",
             "ts": 1792650941.0, "detail": {"error": "模拟器启动失败：UVS_LICENSE 未设置"}},
        ],
        "missing_fields": [],
        "authority": "projection",
        "run_status": "failed",
        "run_terminal": True,
        "node_started_present": True,
        "gate": None,
        "report": None,
        "story": story_for(
            node,
            purpose="把全跑作业交出去后先返回，流程停在等待作业完成。",
            headline="提交失败：模拟器不可用（错误原文见失败区）。",
            status_note="未通过",
            steps=[
                {"seq": 11, "at": 1792650940.0, "kind": "node_started", "status": "running", "text": "开始执行"},
                {"seq": 12, "at": 1792650941.0, "kind": "node_failed", "status": "failed",
                 "text": "失败：模拟器启动失败：UVS_LICENSE 未设置"},
            ],
            key_results=[
                {"field": "job_id", "label": "作业号", "value": None, "text": "未下发", "missing": True},
            ],
        ),
    }


def setup_run(api):
    v = api["views"]["A"]
    v.update(mode="drill", s0_record_id=None, baseline="v1.2-stable",
             node_history=[{"node": "N1", "status": "ok", "kind": "node_finished"},
                           {"node": "N6_apply", "status": "ok"},
                           {"node": "N9_submit", "status": "failed"},
                           {"node": "N15_select", "status": "ok"},
                           {"node": "N15_submit", "status": "ok"},
                           {"node": "HALT", "status": "halted"},
                           {"node": "N_FUTURE", "status": "ok"}])
    v["pending_interrupt"]["payload"]["gate"] = GATE
    api["nodes"][("A", "N1")] = node_detail()
    api["nodes"][("A", "N9_submit")] = failed_detail()
    return v


def open_run_view(page):
    page.locator("#segRun").click()
    pw.expect(page.locator("#viewRun")).to_be_visible()


# 四段流程里默认只展开当前段；其它段的节点 chip 需先展开所属段（STAGE_FALLBACK）。
STAGE_OF = {
    "N6": "修订", "N5": "修订", "N7": "修订", "N8": "修订",
    "N12": "验证", "N9": "验证", "N10": "验证", "N11": "验证",
    "N13": "决策", "N14": "决策", "N15": "决策", "N16": "决策",
    "N9_submit": "验证", "N15_submit": "决策",
}


def open_node(page, node):
    chip = page.locator(f'#viewRun [data-node-chip="{node}"]')
    if not chip.is_visible() and STAGE_OF.get(node):
        page.locator("#viewRun .stage-head", has_text=STAGE_OF[node]).click()
    chip.click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    return chip


# ---------------- 闸门材料 mock（契约 §2.4） ----------------

def gate_detail_entries(*, disposed=False):
    return [
        {"entry_id": ENTRY_ID, "title": "内容有改动：第 171–172 行，偏移 0xd04",
         "kinds": ["rtl_file"], "change": "modified",
         "unresolved": False, "unresolved_reason": None,
         "lines": [171, 172], "offset": "0xd04", "encoding": "utf-8",
         "has_hunk": True,
         "diff_hunk": "@@ -168,7 +168,8 @@\n"
                      " module pcie (input clk);\n"
                      "-    assign baud = 16'h0010;\n"
                      "+    assign baud = 16'h0064;\n"
                      "+    assign extra = 1'b1;\n",
         "before": None, "after": None, "evidence": "5fcc1a → 18fc02（md5 变化）",
         "attached": [{"kind": "allfile", "redundant_of": ENTRY_ID,
                       "before": "5fcc1a", "after": "18fc02",
                       "evidence": "n2_allfile_diff.json",
                       "note": "整文件指纹，不计入修订点"}],
         "disposition": ({"decision": "confirmed", "reason": None} if disposed else None)},
        {"entry_id": DOC_ID, "title": "文档字段有改动：baud 9600 → 115200（其余字段未变）",
         "kinds": ["doc_entry"], "change": "modified",
         "unresolved": "旧版正文缺失，需人工核对", "unresolved_reason": "旧版正文缺失",
         "lines": None, "offset": None, "encoding": "utf-8",
         "has_hunk": False, "diff_hunk": None,
         "before": {"name": "dma_ctrl", "baud": 9600, "mode": "polling"},
         "after": {"name": "dma_ctrl", "baud": 115200, "mode": "polling"},
         "evidence": "doc/interface.md", "attached": [],
         "disposition": ({"decision": "ignored", "reason": "旧版正文缺失，忽略"} if disposed else None)},
    ]


GATE_OPTIONS = {
    GATE: [
        {"value": "confirmed", "label": "差异确认", "requires_reason": False},
        {"value": "ignored", "label": "忽略", "requires_reason": True},
        {"value": "disputed", "label": "有疑义", "requires_reason": True},
    ],
    G2: [
        {"value": "accept", "label": "接受", "requires_reason": False},
        {"value": "rework", "label": "返工", "requires_reason": True},
    ],
    G3: [
        {"value": "full_now", "label": "全量回归", "requires_reason": False},
        {"value": "subset_only", "label": "子集回归", "requires_reason": False},
        {"value": "milestone_only", "label": "仅里程碑", "requires_reason": False},
        {"value": "defer", "label": "暂缓", "requires_reason": True},
    ],
}


def gate_block(*, gate=GATE, state="waiting", entries=None, disposed=0, decision=None,
               hard_block=None, note=None, items=None):
    if entries is None:
        entries = gate_detail_entries(disposed=(state == "decided")) if gate == GATE else []
    return {
        "gate": gate, "state": state, "cycle": 0,
        "entries_required": gate == GATE,
        "decision_options": GATE_OPTIONS.get(gate, []),
        "counts": {"entries": len(entries), "revision_points": len(entries),
                   "disposed": disposed, "unresolved": 1 if gate == GATE else 0},
        "entries": entries, "decision": decision, "hard_block": hard_block or [],
        "items": items or [],
        "source": "pending_interrupt" if state == "waiting" else "decisions_ledger",
        "note": note,
    }


DECIDED = {"decision": "confirmed", "actor": "human:chen", "actor_kind": "human",
           "human_signed": True, "signed_at": 1792650999.0, "reason": "逐条看过", "history_len": 1}
DECIDED_G3 = {"decision": "milestone_only", "actor": "human:chen", "actor_kind": "human",
              "human_signed": True, "signed_at": 1792650999.0,
              "reason": "按受影响子集跑回归后晋升", "history_len": 1}

# 裁决 #2：G2/G3 的只读待确认项（gate.items；无 disposition、无勾选）
ITEMS_N14 = [
    {"id": "case:tc_pcie_rw_02", "kind": "case", "title": "回归用例 tc_pcie_rw_02",
     "detail": "本轮将真跑（G3=仅里程碑）", "severity": "info"},
    {"id": "conflict:C-07", "kind": "conflict", "title": "冲突清单 72 条未清零",
     "detail": "文档/RTL 互相矛盾的登记项，需人逐条裁决", "severity": "blocker"},
]
ITEMS_N13 = [
    {"id": "open:imprint", "kind": "open_item", "title": "3 个用例缺观测点印记",
     "detail": "无法证明预期检查真的跑过并通过", "severity": "warning"},
    {"id": "blocker:I4", "kind": "blocker", "title": "72 条冲突未清零", "detail": None,
     "severity": "blocker"},
]


def setup_items_gate_node(api, *, node="N14", gate_name=G3, state="decided",
                          items=None, hard_block=None):
    """G2/G3 面板：gate.items 只读清单（任意 state 都显示）。"""
    v = setup_run(api)
    items = list(ITEMS_N14 if items is None else items)
    if state == "waiting":
        v["pending_interrupt"]["id"] = gate_name + ":0"
        v["pending_interrupt"]["payload"]["gate"] = gate_name
        v["gate_options"] = {gate_name: GATE_OPTIONS[gate_name]}
    decided = state == "decided"
    status = {"decided": "confirmed", "waiting": "waiting", "read_only": "waiting",
              "no_material": None}.get(state)
    headline = {
        "waiting": "等待你处理：本轮停在闸门（" + gate_name + "）。",
        "decided": "已决定本轮策略（签署人 human:chen）。",
        "read_only": "只读：运行已过这个节点，但没有可读的权威决策记录。",
        "no_material": "本轮没有走到这个节点（运行停在 waiting_gate）。",
    }[state]
    story = story_for(
        node,
        purpose="由人决定这轮做不做回归、发不发版。",
        headline=headline,
        headline_source="template",
        note=({"text": "还有 72 条冲突未清零", "level": "warn"} if hard_block else None),
        status_note="已确认" if decided else ("等待中" if state == "waiting" else None),
        steps=[{"seq": 70, "at": 1792650990.0, "kind": "gate_pending",
                "status": status, "text": "闸门事件"}],
        key_results=[{"field": "gate", "label": "闸门", "value": gate_name,
                      "text": gate_name, "missing": False}],
    )
    decision = None
    if decided:
        decision = DECIDED_G3 if gate_name == G3 else DECIDED
    api["nodes"][("A", node)] = node_detail(
        node=node, name="闸门3" if node == "N14" else "闸门2", owner="人",
        status=status, source="human_gate",
        detail={"gate": gate_name},
        events=[{"seq": 70, "kind": "gate_pending", "node": node,
                 "status": status, "ts": 1792650990.0}],
        story=story,
        gate=gate_block(gate=gate_name, state=state, entries=[], disposed=0,
                        decision=decision, hard_block=hard_block, items=items),
        run_status="waiting_gate", run_terminal=False)
    return v


def setup_gate_node(api, *, state="waiting", entries=None, hard_block=None, note=None):
    v = setup_run(api)
    entries = entries if entries is not None else gate_detail_entries(disposed=(state == "decided"))
    payload = v["pending_interrupt"]["payload"]
    payload["gate"] = GATE
    payload["entry_decisions_required"] = True
    payload["difference_items"] = {
        "present": True, "count": len(entries), "unresolved_count": 1,
        "entries": [{"entry_id": e["entry_id"], "kind": e["kinds"][0],
                     "change": e["change"], "unresolved": bool(e.get("unresolved"))}
                    for e in entries],
    }
    decided = state == "decided"
    story = story_for(
        "N4",
        purpose="由人确认差异清单没问题；点了确认，流程才往下走。",
        headline=("人已确认差异清单（允许继续修订），签署人 human:chen，理由：逐条看过。" if decided
                  else "等待你处理：本轮停在闸门 1（差异确认）。"),
        headline_source="template",
        note=({"text": "还有 3 个用例改完没在全跑里验证通过", "level": "warn"}
              if (hard_block and not decided) else None),
        status_note="已确认" if decided else "等待中",
        steps=([{"seq": 21, "at": 1792650999.0, "kind": "gate_decided", "status": "confirmed",
                 "text": "人已确认差异清单"}] if decided
               else [{"seq": 20, "at": 1792650990.0, "kind": "gate_pending", "status": "waiting",
                      "text": "流程停在闸门 1，等待人工决策"}]),
        key_results=[
            {"field": "gate", "label": "闸门", "value": GATE, "text": GATE, "missing": False},
        ],
    )
    api["nodes"][("A", "N4")] = node_detail(
        node="N4", name="闸门1", owner="人",
        status="confirmed" if decided else "waiting",
        source="human_gate",
        detail={"gate": GATE},
        events=[{"seq": 20, "kind": "gate_pending", "node": "N4",
                 "status": "confirmed" if decided else "waiting", "ts": 1792650990.0}],
        story=story,
        gate=gate_block(state=state, entries=entries,
                        disposed=len(entries) if decided else 0,
                        decision=DECIDED if decided else None,
                        hard_block=hard_block, note=note),
        run_status="waiting_gate", run_terminal=False)
    return v


# ---------------- 报告 mock（契约 §2.6） ----------------

def stub_report(page, *, body=None, status=200, calls=None):
    """在 fixture 的 **/api/** 路由之上叠一层（Playwright 后注册者优先）。"""
    def handler(route):
        if calls is not None:
            calls.append(urlsplit(route.request.url).path)
        if body is None:
            route.fulfill(status=404, json={"detail": {"error": "报告不存在"}})
        else:
            route.fulfill(status=status, json=body)
    page.route("**/api/runs/*/report", handler)


# ---------------- 既有特征测试（按契约 §4 更新断言落点） ----------------

def test_every_node_chip_opens_independent_dialog_and_escape_restores_focus(ui):
    page, api = ui
    setup_run(api)
    select(page, "A")
    open_run_view(page)

    chip = page.locator('#viewRun [data-node-chip="N1"]')
    pw.expect(chip).to_be_visible()
    chip.click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#ndTitle")).to_contain_text("N1")
    # 首屏区块（人话优先；失败块无失败时隐藏）
    for heading in ("这一步做什么", "结果", "关键数字", "过程", "证据", "原始记录（排查用）"):
        pw.expect(page.locator("#nodeDetail")).to_contain_text(heading)
    # 执行方式 / owner / 用时在头部可见（服务端原值 + 中文说明）
    pw.expect(page.locator("#ndMeta")).to_contain_text("drill_fixture")
    pw.expect(page.locator("#ndMeta")).to_contain_text("Host")
    pw.expect(page.locator("#ndMeta")).to_contain_text("用时")
    # drill 场景：来源用大白话 + 首屏一行解释"预置数据 / 不碰真实环境 / 不是 S0"
    pw.expect(page.locator("#ndMeta")).to_contain_text("演示数据")
    pw.expect(page.locator("#ndModeNote")).to_contain_text("预置数据")
    pw.expect(page.locator("#ndModeNote")).to_contain_text("不碰真实环境")
    pw.expect(page.locator("#ndModeNote")).to_contain_text("环境搭建（S0）")
    # 这一步做什么 + 结果一句话（headline）+ 关键数字 + 过程（均在首屏，无需展开）
    pw.expect(page.locator("#ndPurpose")).to_contain_text("拍一张快照")
    pw.expect(page.locator("#ndHeadline")).to_be_visible()
    pw.expect(page.locator("#ndHeadline")).to_contain_text("快照完成")
    pw.expect(page.locator("#ndKey")).to_contain_text("父基线")
    pw.expect(page.locator("#ndSteps")).to_contain_text("开始执行")
    pw.expect(page.locator("#ndSteps")).to_contain_text("结束，状态 ok")
    # 非闸门节点不显示差异清单区
    pw.expect(page.locator("#ndGateBlock")).to_be_hidden()
    # 正文不出现 seq（seq 只在收起的原始记录里）
    assert "seq" not in page.locator("#ndContent .nd-block-first").inner_text().lower()
    assert "seq" not in page.locator("#ndSteps").inner_text().lower()
    # 原始记录默认收起；展开后才看得到 seq / summary 原文 / 完整 detail / 未下发字段
    assert page.locator("#ndRaw").get_attribute("open") is None
    pw.expect(page.locator("#ndEvents")).to_be_hidden()
    page.locator("#ndRawToggle").click()
    assert page.locator("#ndRaw").get_attribute("open") == ""
    pw.expect(page.locator("#ndEvents")).to_be_visible()
    pw.expect(page.locator("#ndRaw")).to_contain_text("事件流水号")
    pw.expect(page.locator("#ndRaw")).to_contain_text("不是业务状态")
    pw.expect(page.locator("#ndRaw")).to_contain_text("服务端 summary 原文")
    pw.expect(page.locator("#ndSummaryRaw")).to_contain_text("N1：v0→v1，manifest 已产出")
    pw.expect(page.locator("#ndEvents")).to_contain_text("node_finished")
    seqs = page.locator("#ndEvents .nd-seq").all_inner_texts()
    assert seqs[:2] == ["#5", "#4"], seqs
    pw.expect(page.locator("#ndDetailBody")).to_contain_text("allfiles_count")
    pw.expect(page.locator("#ndIdentity")).to_contain_text("drill_fixture")
    pw.expect(page.locator("#ndIdentity")).to_contain_text("Host")
    pw.expect(page.locator("#ndMissing")).to_contain_text("manifest_entries")
    # 证据：存在性探测，不打开正文
    page.locator('#ndRefs button').first.click()
    pw.expect(page.locator("#ndRefs .nd-probe").first).to_contain_text("存在")
    # 固定诚实标注
    pw.expect(page.locator(".nd-foot")).to_contain_text("投影，非权威")

    # 轮询全量重建四段流程不得清掉/关闭面板
    tick(page)
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#ndTitle")).to_contain_text("N1")

    # Esc 关闭 + 焦点回到 chip
    page.keyboard.press("Escape")
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()
    pw.expect(page.locator('#viewRun [data-node-chip="N1"]')).to_be_focused()

    # 键盘可达：Enter 打开、Space 打开
    page.locator('#viewRun [data-node-chip="N1"]').focus()
    page.keyboard.press("Enter")
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    page.keyboard.press("Escape")
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()
    page.locator('#viewRun [data-node-chip="N1"]').focus()
    page.keyboard.press(" ")
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    page.keyboard.press("Escape")
    assert not api["posts"], "节点面板不得产生写动作"


@pytest.mark.parametrize("node", ["N9_submit", "HALT", "N6_apply", "N15_submit", "N_FUTURE"])
def test_non_stage_and_unknown_nodes_are_clickable(ui, node):
    page, api = ui
    setup_run(api)
    select(page, "A")
    open_run_view(page)
    chip = page.locator(f'#viewRun [data-node-chip="{node}"]')
    chip.scroll_into_view_if_needed()
    chip.click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#ndSub")).to_contain_text(node)
    page.keyboard.press("Escape")
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()


def test_failed_node_shows_error_text_and_never_claims_done(ui):
    page, api = ui
    setup_run(api)
    select(page, "A")
    open_run_view(page)
    page.locator('#viewRun [data-node-chip="N9_submit"]').scroll_into_view_if_needed()
    page.locator('#viewRun [data-node-chip="N9_submit"]').click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#ndFailure")).to_contain_text("模拟器启动失败：UVS_LICENSE 未设置")
    pw.expect(page.locator("#ndFailure")).to_contain_text("node_failed")
    # 失败步骤直接说"失败"，关键数字缺失写"未下发"
    pw.expect(page.locator("#ndSteps")).to_contain_text("失败：模拟器启动失败")
    pw.expect(page.locator("#ndKey")).to_contain_text("未下发")
    # 状态原值逐字保留 + 中文释义；结果一句话不得声称成功
    pw.expect(page.locator("#ndStatus")).to_have_text("failed 未通过")
    pw.expect(page.locator("#ndHeadline")).not_to_contain_text("完成")
    pw.expect(page.locator("#ndSteps")).not_to_contain_text("结束，状态 ok")
    page.keyboard.press("Escape")

    # 未知节点：known=false 空投影 + 原始事件，不 404、不静默不可点
    page.locator('#viewRun [data-node-chip="HALT"]').scroll_into_view_if_needed()
    page.locator('#viewRun [data-node-chip="HALT"]').click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#ndError")).to_contain_text("known=false")
    pw.expect(page.locator("#ndSteps")).to_contain_text("events 为空")
    page.locator("#ndRawToggle").click()
    pw.expect(page.locator("#ndEvents")).to_contain_text("events 为空")


def test_stale_node_response_cannot_replace_reopened_panel(ui):
    page, api = ui
    setup_run(api)
    select(page, "A")
    open_run_view(page)
    api["hold"] = lambda path: "/nodes/" in path

    page.locator('#viewRun [data-node-chip="N1"]').click()
    page.wait_for_timeout(80)
    assert len(api["pending"]) == 1, api["pending"]
    page.keyboard.press("Escape")
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()

    # 重新打开：先回旧选择的过期回包，再回新请求；旧回包不得覆盖新面板
    page.locator('#viewRun [data-node-chip="N1"]').click()
    page.wait_for_timeout(80)
    assert len(api["pending"]) == 2
    release(page, api, node_detail(story=story_for(headline="新请求的回包")), index=1)
    pw.expect(page.locator("#ndHeadline")).to_contain_text("新请求的回包")
    release(page, api, node_detail(story=story_for(headline="过期回包")), index=0)
    pw.expect(page.locator("#ndHeadline")).to_contain_text("新请求的回包")
    pw.expect(page.locator("#ndHeadline")).not_to_contain_text("过期回包")
    page.keyboard.press("Escape")


def test_gate_node_jumps_to_gate_view_and_model_node_offers_agent_window(ui):
    page, api = ui
    setup_run(api)
    api["nodes"][("A", "N3")] = node_detail(
        node="N3", name="差异语义总结", owner="analyst", source="model_standin",
        summary="3 组 / 27 条差异摘要", detail={"mode": "standin"})
    select(page, "A")
    open_run_view(page)

    # 闸门节点：可跳同源材料；Host 节点不提供 Agent 工作窗口入口
    page.locator('#viewRun [data-node-chip="N4"]').click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#nodeDetail")).not_to_contain_text("打开 Agent 工作窗口")
    page.locator("#ndAgentJump button").click()
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()
    pw.expect(page.locator("#viewGate")).to_be_visible()

    # 模型节点：可跳 Agent 工作窗口（SPEC-REV-01 R6 边界）
    open_run_view(page)
    page.locator('#viewRun [data-node-chip="N3"]').click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#ndAgentJump")).to_contain_text("打开 Agent 工作窗口")
    pw.expect(page.locator("#ndIdentity")).to_contain_text("model_standin")
    page.keyboard.press("Escape")


# ---------------- S4：结果区 headline / 黄条 / summary 原文 ----------------

def test_result_uses_story_headline_and_moves_summary_into_raw_record(ui):
    page, api = ui
    setup_run(api)
    api["nodes"][("A", "N1")] = node_detail(story=story_for(
        headline="快照完成：3374 个文件，冻结 162 个用例。",
        note={"text": "1 条需要你确认，到 G1 逐条处置", "level": "warn"}))
    select(page, "A")
    open_run_view(page)
    open_node(page, "N1")

    # 首屏「结果」是 headline，不是 summary 原文
    pw.expect(page.locator("#ndHeadline")).to_be_visible()
    pw.expect(page.locator("#ndHeadline")).to_have_text("快照完成：3374 个文件，冻结 162 个用例。")
    pw.expect(page.locator("#ndHeadline")).not_to_contain_text("manifest 已产出")
    # story.note 是首屏黄条（一行）
    pw.expect(page.locator("#ndNote .nd-note-warn")).to_be_visible()
    pw.expect(page.locator("#ndNote .nd-note-warn")).to_have_text("1 条需要你确认，到 G1 逐条处置")
    # summary 原文默认收起，展开原始记录后可见并注明来源
    assert page.locator("#ndRaw").get_attribute("open") is None
    page.locator("#ndRawToggle").click()
    pw.expect(page.locator("#ndRaw")).to_contain_text("服务端 summary 原文")
    pw.expect(page.locator("#ndSummaryRaw")).to_contain_text("N1：v0→v1，manifest 已产出")


def test_status_chips_keep_raw_value_and_add_glossary(ui):
    page, api = ui
    setup_run(api)
    api["nodes"][("A", "N6")] = node_detail(
        node="N6", name="修订", owner="author", status="live", source="model_live",
        summary="N6：目标 3 个用例，校验通过", detail={"cycle": 0, "targets": 3, "validation_ok": True},
        events=[
            {"seq": 30, "kind": "node_started", "node": "N6", "status": "running",
             "ts": 1792650940.0},
            {"seq": 31, "kind": "node_finished", "node": "N6", "status": "live",
             "ts": 1792650941.0, "detail": {"source": "model_live"}},
        ],
        story=story_for(
            "N6",
            purpose="让作者模型按影响清单改/补用例，并检查它的输出格式对不对。",
            headline="改了 3 个用例：tc_pcie_rw_02（1 处）；输出校验通过。",
            status_note="真实模型调用",
            steps=[
                {"seq": 30, "at": 1792650940.0, "kind": "node_started", "status": "live", "text": "开始执行"},
                {"seq": 31, "at": 1792650941.0, "kind": "node_finished", "status": "ok", "text": "结束，状态 ok"},
            ]))
    select(page, "A")
    open_run_view(page)
    open_node(page, "N6")

    # 头部状态 chip：原值逐字保留 + story.status_note
    pw.expect(page.locator("#ndStatus")).to_have_text("live 真实模型调用")
    # 过程步骤 chip 同样带 glossary 释义
    step_chips = page.locator("#ndSteps .nd-step-status").all_inner_texts()
    assert step_chips == ["live 真实模型调用", "ok 通过"], step_chips
    # 原始记录里仍是服务端原值，不被释义替换
    page.locator("#ndRawToggle").click()
    pw.expect(page.locator("#ndIdentity")).to_contain_text("model_live")
    pw.expect(page.locator("#ndEvents")).to_contain_text("live")


# ---------------- S4：未到达 / 未执行 / evidence_note ----------------

def test_not_reached_never_asks_to_wait_for_it_to_finish(ui):
    page, api = ui
    setup_run(api)
    api["nodes"][("A", "N14")] = node_detail(
        node="N14", name="闸门3", owner="人", status=None, source=None,
        summary=None, detail={}, refs=[], events=[], known=True,
        missing_fields=["summary", "source"],
        run_status="waiting_gate", run_terminal=False,
        story=story_for(
            "N14",
            purpose="由人决定这轮做不做回归、发不发版。",
            headline="本轮没有走到这个节点（运行停在 waiting_gate）。",
            not_reached=True,
            steps=[],
            key_results=[]))
    select(page, "A")
    open_run_view(page)
    open_node(page, "N14")

    pw.expect(page.locator("#ndHeadline")).to_contain_text("本轮没有走到这个节点")
    pw.expect(page.locator("#ndKey")).to_contain_text("没有关键数字")
    pw.expect(page.locator("#ndSteps")).to_contain_text("没有走到这个节点")
    body = page.locator("#ndContent").inner_text()
    assert "等它跑完" not in body, body
    assert "证据缺失" not in body, body


def test_evidence_note_points_to_agent_calls_without_claiming_missing(ui):
    page, api = ui
    setup_run(api)
    api["nodes"][("A", "N3")] = node_detail(
        node="N3", name="差异语义总结", owner="analyst", source="model_live",
        status="live", summary="N3：模型摘要已产出",
        detail={"mode": "live", "digest_summary": "把 baud 从 9600 改成 115200"},
        refs=[],
        story=story_for(
            "N3",
            purpose="让分析模型把原始差异翻成一句人话，讲清楚这次改了什么。",
            headline="模型说：把 baud 从 9600 改成 115200（另有 1 条需要你确认）。",
            status_note="真实模型调用",
            evidence_note={"text": "模型调用记录在 Agent 工作窗口（本轮是真实模型调用）。",
                           "kind": "agent_calls"},
            steps=[{"seq": 40, "at": 1792650940.0, "kind": "node_finished", "status": "live",
                    "text": "模型返回摘要"}],
            key_results=[]))
    select(page, "A")
    open_run_view(page)
    open_node(page, "N3")

    pw.expect(page.locator("#ndRefs .nd-evidence-note")).to_contain_text("Agent 工作窗口")
    pw.expect(page.locator("#ndRefs")).not_to_contain_text("证据缺失")
    pw.expect(page.locator("#ndRefs")).to_contain_text("打开 Agent 工作窗口")
    page.keyboard.press("Escape")

    # 未执行（drill 不真跑）：说"未执行（无证据）"，不报缺失；"未下发"≠"未执行"
    api["nodes"][("A", "N15")] = node_detail(
        node="N15", name="回归", owner="TriggerFlow", source="drill_fixture",
        status="ok", summary="drill 显式 no-op（未真跑回归）",
        detail={}, refs=[], events=[],
        story=story_for(
            "N15",
            purpose="跑回归作业，确认改动没有引入回退。",
            headline="演示模式：不真跑回归。本轮回归集 = 5 个受影响用例。",
            not_executed=True,
            evidence_note={"text": "本轮未执行回归（无证据）", "kind": "not_executed"},
            steps=[{"seq": 50, "at": 1792650950.0, "kind": "node_finished", "status": "ok",
                    "text": "演示模式：不真跑回归"}],
            key_results=[]))
    tick(page)
    open_node(page, "N15")
    pw.expect(page.locator("#ndKey")).to_contain_text("本轮未执行")
    pw.expect(page.locator("#ndKey")).not_to_contain_text("等它跑完")
    pw.expect(page.locator("#ndRefs")).to_contain_text("本轮未执行")
    pw.expect(page.locator("#ndRefs")).not_to_contain_text("证据缺失")


# ---------------- S4：闸门二级清单 + 浮窗 + 共享草稿 ----------------

def test_gate_lists_revision_points_with_compact_rows(ui):
    page, api = ui
    setup_gate_node(api)
    select(page, "A")
    open_run_view(page)
    open_node(page, "N4")

    pw.expect(page.locator("#ndGateBlock")).to_be_visible()
    pw.expect(page.locator("#ndGateSummaryLine")).to_have_text("共 2 条修订点，已处置 0 条")
    rows = page.locator("#ndGate .nd-gate-row")
    pw.expect(rows).to_have_count(2)
    first = rows.first
    pw.expect(first.locator(".nd-gate-title")).to_contain_text("内容有改动")
    pw.expect(first.locator(".nd-gate-meta")).to_contain_text("pcie_register.v")
    pw.expect(first.locator(".nd-gate-meta")).to_contain_text("第 171–172 行")
    pw.expect(first.locator(".nd-gate-meta")).to_contain_text("偏移 0xd04")
    pw.expect(first.locator(".nd-gate-meta")).to_contain_text("修改（modified）")
    # md5-only 附证据不计入修订点
    pw.expect(first.locator(".nd-gate-meta")).to_contain_text("另有整文件指纹 1 条（不计入修订点）")
    # 未决条目有醒目徽标
    pw.expect(rows.nth(1).locator(".nd-gate-unresolved")).to_have_text("未决")
    # 勾选框与「查看前后对比」是两个独立命中区
    pw.expect(page.locator("#ndGate .nd-gate-row input[type=checkbox]")).to_have_count(2)
    pw.expect(page.locator("#ndGate .nd-gate-open")).to_have_count(2)
    # 未处置时底部给提示（不是静默禁用）
    pw.expect(page.locator("#ndGateFoot")).to_contain_text("还有 2 条未处置")
    pw.expect(page.locator("#ndGateFoot")).to_contain_text("去闸门视图确认并提交")

    # 点勾选不打开浮窗；点入口按钮才打开
    first.locator("input[type=checkbox]").check()
    pw.expect(page.locator("#ndDiffOverlay")).to_be_hidden()
    pw.expect(page.locator("#ndGateSummaryLine")).to_have_text("共 2 条修订点，已处置 1 条")
    pw.expect(page.locator("#ndGateFoot")).to_contain_text("还有 1 条未处置")
    first.locator(".nd-gate-open").click()
    pw.expect(page.locator("#ndDiffOverlay")).to_be_visible()
    pw.expect(page.locator("#ndDiffTitle")).to_contain_text("内容有改动")
    page.keyboard.press("Escape")


def test_diff_overlay_renders_two_columns_with_hunk_line_numbers(ui):
    page, api = ui
    setup_gate_node(api)
    select(page, "A")
    open_run_view(page)
    open_node(page, "N4")
    page.locator("#ndGate .nd-gate-row").first.locator(".nd-gate-open").click()
    pw.expect(page.locator("#ndDiffOverlay")).to_be_visible()

    # 浮窗宽度 ≥ 80% 视口；代码自动换行（不横向滚动）
    viewport = page.viewport_size
    box = page.locator("#ndDiffOverlay .nd-overlay-card").bounding_box()
    assert box["width"] >= viewport["width"] * 0.8, box
    wrap = page.evaluate(
        "() => getComputedStyle(document.querySelector('#ndDiffOverlay .nd-hunk-text')).whiteSpace")
    assert wrap == "pre-wrap", wrap

    # 左右两栏 before / after，hunk 行号来自 @@ 头
    pw.expect(page.locator("#ndDiffOverlay .nd-hunk-cell.before").first).to_be_visible()
    pw.expect(page.locator("#ndDiffOverlay .nd-hunk-cell.after").first).to_be_visible()
    before_numbers = page.locator("#ndDiffOverlay .nd-hunk-cell.before .nd-hunk-no").all_inner_texts()
    after_numbers = page.locator("#ndDiffOverlay .nd-hunk-cell.after .nd-hunk-no").all_inner_texts()
    assert before_numbers == ["168", "169"], before_numbers
    assert after_numbers == ["168", "169", "170"], after_numbers
    before_text = " ".join(page.locator("#ndDiffOverlay .nd-hunk-cell.before .nd-hunk-text").all_inner_texts())
    after_text = " ".join(page.locator("#ndDiffOverlay .nd-hunk-cell.after .nd-hunk-text").all_inner_texts())
    assert "16'h0010" in before_text and "16'h0064" not in before_text, before_text
    assert "16'h0064" in after_text and "assign extra" in after_text, after_text
    # 元信息含 offset / encoding / evidence / 夹具
    pw.expect(page.locator("#ndDiffMeta")).to_contain_text("偏移：0xd04")
    pw.expect(page.locator("#ndDiffMeta")).to_contain_text("编码：utf-8")
    pw.expect(page.locator("#ndDiffMeta")).to_contain_text("证据：")
    # Esc 只关上层：浮窗关闭、面板仍在，焦点回触发按钮
    page.keyboard.press("Escape")
    pw.expect(page.locator("#ndDiffOverlay")).to_be_hidden()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(page.locator("#ndGate .nd-gate-row").first.locator(".nd-gate-open")).to_be_focused()
    # 再 Esc 才关面板
    page.keyboard.press("Escape")
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()


def test_diff_overlay_shows_no_hunk_reason_and_alternative_evidence(ui):
    page, api = ui
    setup_gate_node(api)
    select(page, "A")
    open_run_view(page)
    open_node(page, "N4")
    page.locator("#ndGate .nd-gate-row").nth(1).locator(".nd-gate-open").click()
    pw.expect(page.locator("#ndDiffOverlay")).to_be_visible()

    # 无 hunk：显示原因 + 替代证据（行号 / md5 / 附证据），不留空
    nohunk = page.locator("#ndDiffOverlay .nd-nohunk")
    pw.expect(nohunk).to_be_visible()
    pw.expect(nohunk).to_contain_text("原因：")
    pw.expect(nohunk).to_contain_text("旧版正文缺失")
    pw.expect(nohunk).to_contain_text("替代证据：")
    # doc_entry 变化字段先列、其余折叠
    pw.expect(page.locator("#ndDiffOverlay .diff-fields").first).to_contain_text("baud")
    pw.expect(page.locator("#ndDiffOverlay .diff-fields").first).to_contain_text("115200")
    pw.expect(page.locator("#ndDiffOverlay .diff-unchanged summary")).to_contain_text("其余字段未变（2 项）")
    page.keyboard.press("Escape")


def test_gate_disposition_writes_shared_draft_and_jumps_to_gate_view(ui):
    page, api = ui
    setup_gate_node(api)
    select(page, "A")
    open_run_view(page)
    open_node(page, "N4")

    first = page.locator("#ndGate .nd-gate-row").first
    first.locator("input[type=checkbox]").check()
    assert page.evaluate("() => window.GateDraftBridge.counts()") == {
        "entries": 2, "disposed": 1, "complete": False,
        "error": "逐条处置未覆盖全部条目（缺 1 条）：doc/interface.md",
    }

    # 浮窗里逐条处置：忽略必须填理由
    page.locator("#ndGate .nd-gate-row").nth(1).locator(".nd-gate-open").click()
    pw.expect(page.locator("#ndDiffOverlay")).to_be_visible()
    page.locator('#ndDiffOverlay .nd-dispose-options input[value="ignored"]').check()
    pw.expect(page.locator("#ndDiffOverlay .nd-dispose-hint")).to_contain_text("必须填理由")
    counts = page.evaluate("() => window.GateDraftBridge.counts()")
    assert counts["complete"] is False and "必须填写理由" in counts["error"], counts
    page.locator("#ndDiffOverlay .nd-dispose-reason-input").fill("旧版正文缺失，忽略")
    pw.expect(page.locator("#ndDiffOverlay .nd-dispose-hint")).to_contain_text("已写入共享草稿")
    counts = page.evaluate("() => window.GateDraftBridge.counts()")
    assert counts == {"entries": 2, "disposed": 2, "complete": True, "error": None}, counts
    # 勾选与理由写在共享草稿状态里（同一 GateSession 身份）
    assert page.evaluate(
        "() => window.GateDraftBridge.get('doc/interface.md')") == {
        "decision": "ignored", "reason": "旧版正文缺失，忽略"}
    page.keyboard.press("Escape")
    pw.expect(page.locator("#ndGateSummaryLine")).to_have_text("共 2 条修订点，已处置 2 条")
    pw.expect(page.locator("#ndGateFoot")).to_contain_text("全部已处置")

    # 节点面板不发 POST；提交入口只有闸门视图
    assert not api["posts"]
    page.locator("#ndGateFoot .nd-gate-jump").click()
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()
    pw.expect(page.locator("#viewGate")).to_be_visible()
    pw.expect(page.locator("#gatePanel [data-gate-submit]")).to_be_enabled()
    pw.expect(page.locator("#gatePanel [data-gate-submit]")).to_have_text("提交闸门决策")
    assert not api["posts"], "节点面板内绝不发 POST"


def test_decided_gate_is_read_only_with_disposition_and_decision(ui):
    page, api = ui
    setup_gate_node(api, state="decided")
    select(page, "A")
    open_run_view(page)
    open_node(page, "N4")

    pw.expect(page.locator("#ndGateSummaryLine")).to_have_text("共 2 条修订点，已处置 2 条")
    rows = page.locator("#ndGate .nd-gate-row")
    pw.expect(rows.first.locator("input[type=checkbox]")).to_be_disabled()
    pw.expect(rows.first.locator(".nd-gate-state")).to_have_text("已确认（confirmed）")
    pw.expect(rows.nth(1).locator(".nd-gate-state")).to_have_text("忽略（ignored）")
    # 整门决策 / 签署人 / 时间 / 理由原文
    foot = page.locator("#ndGateFoot")
    pw.expect(foot).to_contain_text("整门决策：差异确认（confirmed）")
    pw.expect(foot).to_contain_text("签署人：human:chen")
    pw.expect(foot).to_contain_text("签署时间：")
    pw.expect(foot).to_contain_text("理由：逐条看过")
    pw.expect(foot).to_contain_text("不允许改判")
    # 已决策态没有提交/跳转入口
    pw.expect(page.locator("#ndGate .nd-gate-jump")).to_have_count(0)
    # 浮窗里也只读展示当时的逐条处置
    rows.nth(1).locator(".nd-gate-open").click()
    pw.expect(page.locator("#ndDiffOverlay")).to_be_visible()
    pw.expect(page.locator("#ndDiffOverlay .nd-dispose-readonly")).to_contain_text("处置：忽略（ignored）")
    pw.expect(page.locator("#ndDiffOverlay .nd-dispose-reason")).to_contain_text("旧版正文缺失，忽略")
    pw.expect(page.locator("#ndDiffOverlay .nd-dispose-options input")).to_have_count(0)
    assert not api["posts"]


def test_waiting_gate_hard_block_is_plain_language_with_code_footnote(ui):
    page, api = ui
    setup_gate_node(api, hard_block=[
        {"code": "I2_CASES_PENDING", "title": "还有 3 个用例没验证通过",
         "message": "有 3 个受影响的用例改完没在全跑里验证通过"},
    ])
    select(page, "A")
    open_run_view(page)
    open_node(page, "N4")

    block = page.locator("#ndGate .nd-hardblock")
    pw.expect(block).to_be_visible()
    pw.expect(block.locator(".nd-hb-title")).to_contain_text("还有 3 个用例")
    pw.expect(block.locator(".nd-hb-msg")).to_contain_text("3 个受影响")
    # 代号只作小字附注，正文不是只有代号
    pw.expect(block.locator(".nd-hb-code")).to_contain_text("I2_CASES_PENDING")
    msg = block.locator(".nd-hb-msg").inner_text()
    assert msg.strip() and "I2_CASES_PENDING" not in msg, msg
    # 等待态首屏黄条同样有一句白话
    pw.expect(page.locator("#ndNote .nd-note-warn")).to_contain_text("3 个用例")


# ---------------- 裁决 #2：G2/G3 只读待确认项清单（gate.items） ----------------

def test_gate_items_readonly_list_for_g3_decided(ui):
    page, api = ui
    setup_items_gate_node(api, node="N14", gate_name=G3, state="decided")
    select(page, "A")
    open_run_view(page)
    open_node(page, "N14")

    pw.expect(page.locator("#ndGateBlock")).to_be_visible()
    # 标题与 G1「差异清单（N 条修订点）」区分：待确认项 + 只读
    pw.expect(page.locator("#ndGate .nd-items-head")).to_have_text("待确认项（只读，2 条）")
    rows = page.locator("#ndGate .nd-item")
    pw.expect(rows).to_have_count(2)
    pw.expect(rows.first.locator(".nd-item-kind")).to_have_text("用例")
    pw.expect(rows.first.locator(".nd-item-title")).to_contain_text("tc_pcie_rw_02")
    pw.expect(rows.first.locator(".nd-item-detail")).to_contain_text("仅里程碑")
    pw.expect(rows.nth(1).locator(".nd-item-kind")).to_have_text("冲突")
    pw.expect(rows.nth(1).locator(".nd-item-severity")).to_have_text("blocker")
    # 只读：无勾选/处置控件；非 G1 不出现修订点计数与逐条行
    pw.expect(page.locator("#ndGate .nd-items input")).to_have_count(0)
    pw.expect(page.locator("#ndGate .nd-gate-row")).to_have_count(0)
    pw.expect(page.locator("#ndGateSummaryLine")).to_have_count(0)
    # 已决策态显示决策信息，但不提供跳转提交入口
    pw.expect(page.locator("#ndGateFoot")).to_contain_text("整门决策：仅里程碑（milestone_only）")
    pw.expect(page.locator("#ndGateFoot")).to_contain_text("理由：按受影响子集跑回归后晋升")
    pw.expect(page.locator("#ndGate .nd-gate-jump")).to_have_count(0)
    assert not api["posts"]


def test_gate_items_with_hard_block_in_waiting_state(ui):
    page, api = ui
    setup_items_gate_node(
        api, node="N14", gate_name=G3, state="waiting", items=ITEMS_N14,
        hard_block=[{"code": "I4_CONFLICTS_UNCLEARED", "title": "72 条冲突未清零",
                     "message": "文档/RTL 互相矛盾的登记项未清零，full_now / subset_only 会被拒"}])
    select(page, "A")
    open_run_view(page)
    open_node(page, "N14")

    # 等待态：只读待确认项 + 硬阻断白话（代号只作小字附注）
    pw.expect(page.locator("#ndGate .nd-items-head")).to_have_text("待确认项（只读，2 条）")
    pw.expect(page.locator("#ndGate .nd-hardblock .nd-hb-msg")).to_contain_text("未清零")
    pw.expect(page.locator("#ndGate .nd-hardblock .nd-hb-code")).to_contain_text("I4_CONFLICTS_UNCLEARED")
    # 非 G1：没有逐条处置控件/修订点计数
    pw.expect(page.locator("#ndGate .nd-items input")).to_have_count(0)
    pw.expect(page.locator("#ndGateSummaryLine")).to_have_count(0)
    # 等待态仍有"去闸门视图确认并提交"（决策在闸门视图提交）
    pw.expect(page.locator("#ndGateFoot")).to_contain_text("本门没有逐条处置项")
    pw.expect(page.locator("#ndGateFoot .nd-gate-jump")).to_have_count(1)
    assert not api["posts"]


def test_read_only_state_shows_items_without_disposition_or_jump(ui):
    """gate.state=read_only：只渲染 gate.items，不出现"等待你处理"措辞/处置控件/跳转。"""
    page, api = ui
    setup_items_gate_node(api, node="N14", gate_name=G3, state="read_only", items=ITEMS_N14)
    select(page, "A")
    open_run_view(page)
    open_node(page, "N14")

    pw.expect(page.locator("#ndGate .nd-items-head")).to_have_text("待确认项（只读，2 条）")
    pw.expect(page.locator("#ndGate input")).to_have_count(0)
    pw.expect(page.locator("#ndGate .nd-hardblock")).to_have_count(0)
    pw.expect(page.locator("#ndGate .nd-gate-jump")).to_have_count(0)
    pw.expect(page.locator("#ndGateFoot")).to_contain_text("只读")
    pw.expect(page.locator("#ndHeadline")).not_to_contain_text("等待你处理")
    assert not api["posts"]


@pytest.mark.parametrize("state", ["waiting", "no_material"])
def test_items_missing_falls_back_to_server_not_sent(ui, state):
    page, api = ui
    setup_items_gate_node(api, node="N13", gate_name=G2, state=state, items=[])
    select(page, "A")
    open_run_view(page)
    open_node(page, "N13")

    # gate.items 缺失/空 ⇒ 明说来源未定，不编条目、不出现处置控件
    pw.expect(page.locator("#ndGateBlock")).to_be_visible()
    pw.expect(page.locator("#ndGate")).to_contain_text("服务端未下发待确认项（来源未定）")
    pw.expect(page.locator("#ndGate .nd-items")).to_have_count(0)
    pw.expect(page.locator("#ndGate input")).to_have_count(0)
    pw.expect(page.locator("#ndGate .nd-gate-row")).to_have_count(0)


def test_g1_read_only_hides_revision_points_and_disposition(ui):
    """G1 修订点清单/处置控件只在 waiting/decided 出现；read_only 只给只读说明。"""
    page, api = ui
    setup_gate_node(api, state="read_only")
    select(page, "A")
    open_run_view(page)
    open_node(page, "N4")

    pw.expect(page.locator("#ndGateBlock")).to_be_visible()
    pw.expect(page.locator("#ndGate .nd-gate-row")).to_have_count(0)
    pw.expect(page.locator("#ndGateSummaryLine")).to_have_count(0)
    pw.expect(page.locator("#ndGate input")).to_have_count(0)
    pw.expect(page.locator("#ndGate .nd-gate-jump")).to_have_count(0)
    pw.expect(page.locator("#ndGateFoot")).to_contain_text("只读")


# ---------------- S4：N12 报告只读浮窗 ----------------

def n12_detail(**overrides):
    data = node_detail(
        node="N12", name="报告", owner="reporter", status="ok", source="model_live",
        summary="N12：报告 claimed_verdict=not_passed",
        detail={"claimed_verdict": "not_passed", "ref_count": 18},
        story=story_for(
            "N12",
            purpose="让报告模型写本轮评估报告，并核对它引用的证据都能对上。",
            headline="报告结论：未通过；引用 18 条证据（不可解析 0 条）；未闭环 0 项。",
            status_note="通过",
            steps=[{"seq": 60, "at": 1792650960.0, "kind": "node_finished", "status": "ok",
                    "text": "报告已生成"}],
            key_results=[{"field": "claimed_verdict", "label": "报告结论",
                          "value": "not_passed", "text": "未通过", "missing": False}]))
    data.update(overrides)
    return data


def test_report_missing_and_readonly_overlay(ui):
    page, api = ui
    setup_run(api)
    api["nodes"][("A", "N12")] = n12_detail(
        report={"file": "n12_report.md", "available": False, "bytes": 0})
    select(page, "A")
    open_run_view(page)
    open_node(page, "N12")
    pw.expect(page.locator("#ndReport")).to_contain_text("本轮没有报告文件")
    page.keyboard.press("Escape")

    calls = []
    stub_report(page, body={"run_id": "A", "file": "n12_report.md", "path": "/kb/runs/A/n12_report.md",
                            "bytes": 123, "truncated": False,
                            "content": "# 评估报告\n\n结论：未通过（not_passed）。\n证据 18 条。"},
                calls=calls)
    api["nodes"][("A", "N12")] = n12_detail(
        report={"file": "n12_report.md", "available": True, "bytes": 123})
    open_node(page, "N12")
    button = page.locator("#ndReport .nd-report-open")
    pw.expect(button).to_have_text("查看报告全文")
    button.click()
    pw.expect(page.locator("#ndReportOverlay")).to_be_visible()
    pw.expect(page.locator("#ndReportTitle")).to_contain_text("n12_report.md")
    pw.expect(page.locator("#ndReportMeta")).to_contain_text("123 B")
    pw.expect(page.locator("#ndReportBody")).to_contain_text("结论：未通过（not_passed）")
    assert page.evaluate("() => document.getElementById('ndReportBody').tagName") == "PRE"
    assert calls == ["/api/runs/A/report"], calls
    # Esc 只关报告浮窗、焦点回按钮；再 Esc 关面板
    page.keyboard.press("Escape")
    pw.expect(page.locator("#ndReportOverlay")).to_be_hidden()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    pw.expect(button).to_be_focused()
    page.keyboard.press("Escape")
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()
    assert not api["posts"]


def test_diff_overlay_is_full_screen_on_narrow_viewport(ui):
    page, api = ui
    setup_gate_node(api)
    page.set_viewport_size({"width": 390, "height": 844})
    select(page, "A")
    open_run_view(page)
    open_node(page, "N4")
    page.locator("#ndGate .nd-gate-row").first.locator(".nd-gate-open").click()
    pw.expect(page.locator("#ndDiffOverlay")).to_be_visible()
    box = page.locator("#ndDiffOverlay .nd-overlay-card").bounding_box()
    assert box["width"] >= 389, box
    assert box["height"] >= 843, box
    page.keyboard.press("Escape")


# ---------------- 既有 G1 材料 / 溢出 / S0 徽标特征测试 ----------------

def g1_payload(v):
    v["pending_interrupt"]["payload"]["entry_decisions_required"] = True
    v["pending_interrupt"]["payload"]["difference_items"] = {
        "present": True, "count": 2, "unresolved_count": 1, "unresolved_ids": ["D-002"],
        "entries": [
            {"entry_id": "D-001", "kind": "doc_entry", "change": "modified",
             "before": {"name": "dma_ctrl", "baud": 9600, "mode": "polling"},
             "after": {"name": "dma_ctrl", "baud": 115200, "mode": "polling"},
             "evidence": "doc/interface.md"},
            {"entry_id": "D-002", "kind": "rtl_file", "change": "modified",
             "segment": "sys_reg.v", "lines": [12], "encoding": "gbk",
             "drill_fixture": True,
             "before": "assign baud = 16'h0010;",
             "after": "assign baud = 16'h0064;",
             "diff_hunk": "@@ -11,3 +11,3 @@\n context line\n"
                           "-    assign baud = 16'h0010;\n"
                           "+    assign baud = 16'h0064;\n",
             "unresolved": "GBK 解码后仍需人工核对"},
        ],
    }
    v["pending_interrupt"]["payload"]["n3_digest"] = {
        "path": "/kb/runs/A/n3_digest.md", "exists": False}
    v["pending_interrupt"]["payload"]["host_trace"] = {
        "path": "/kb/runs/A/mock_change_applied.json", "exists": True,
        "changes": [{"id": "H-1", "kind": "mock", "old": "16'h0010", "new": "16'h0064",
                     "line_before": 12, "line_after": 12, "encoding": "gbk",
                     "rationale": "夹具替换寄存器默认值",
                     "evidence": "mock_change_applied.json"}]}


def test_g1_material_renders_before_after_hunk_encoding_and_entries(ui):
    page, api = ui
    v = setup_run(api)
    g1_payload(v)
    select(page, "A")
    pw.expect(page.locator("#viewGate")).to_be_visible()

    material = page.locator("#gateMaterial")
    pw.expect(material.locator(".diff-item")).to_have_count(2)
    # 每条差异都有 before/after 双栏
    pw.expect(material.locator(".diff-pair")).to_have_count(2)
    pw.expect(material.locator(".diff-pane.before")).to_have_count(2)
    pw.expect(material.locator(".diff-pane.after")).to_have_count(2)
    pw.expect(material.locator(".diff-item").first.locator(".diff-text").first).to_contain_text("9600")
    pw.expect(material.locator(".diff-item").first.locator(".diff-pane.after .diff-text")).to_contain_text("115200")

    # doc_entry 变化字段先列，其余字段折叠
    first = material.locator(".diff-item").first
    pw.expect(first.locator(".diff-fields").first).to_contain_text("baud")
    pw.expect(first.locator(".diff-fields").first).to_contain_text("9600")
    pw.expect(first.locator(".diff-fields").first).to_contain_text("115200")
    pw.expect(first.locator(".diff-unchanged summary")).to_contain_text("其余字段未变（2 项）")

    # rtl_file 行级 hunk 带行号；encoding 与 drill 徽标
    second = material.locator(".diff-item").nth(1)
    pw.expect(second.locator(".diff-hunk")).to_be_visible()
    pw.expect(second.locator(".diff-hunk")).to_contain_text("16'h0064")
    line_numbers = second.locator(".diff-hunk .dh-no").all_inner_texts()
    assert "12" in line_numbers, line_numbers
    pw.expect(material).to_contain_text("编码 gbk（解码后对比）")
    pw.expect(material).to_contain_text("drill_fixture")
    pw.expect(material).to_contain_text("GBK 解码后仍需人工核对")
    # doc_entry 无 hunk 时显示原因，不是空白
    pw.expect(first.locator(".diff-nohunk")).to_contain_text("无行级 hunk")
    pw.expect(first.locator(".diff-nohunk")).to_contain_text("原因")

    # 材料入口：n3_digest 存在性（缺则未生成）+ Host 留痕 changes
    pw.expect(material).to_contain_text("n3_digest.md")
    pw.expect(material.locator(".material-extra").first).to_contain_text("未生成")
    pw.expect(material.locator(".host-trace-table")).to_contain_text("16'h0010 → 16'h0064")
    pw.expect(material.locator(".host-trace-table")).to_contain_text("夹具替换寄存器默认值")

    # 逐条处置控件已在闸门视图提供（SPEC-04 §4.4，2026-10-23）：不再让人"走 API"，也不得盲签
    entries_box = page.locator("#gatePanel .gate-entries-box")
    pw.expect(entries_box).to_be_visible()
    pw.expect(entries_box).to_contain_text("D-001")
    pw.expect(entries_box).to_contain_text("D-002")
    pw.expect(material).not_to_contain_text("不得盲签")

    # 轮询重建材料后仍可判
    tick(page)
    pw.expect(page.locator("#gateMaterial .diff-pair")).to_have_count(2)
    pw.expect(page.locator("#gateMaterial .diff-hunk")).to_be_visible()


@pytest.mark.parametrize("width", [390, 768, 1280])
def test_node_dialog_and_g1_material_have_no_page_overflow(ui, width):
    page, api = ui
    v = setup_run(api)
    g1_payload(v)
    page.set_viewport_size({"width": width, "height": 900})
    select(page, "A")
    pw.expect(page.locator("#viewGate")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    open_run_view(page)
    page.locator('#viewRun [data-node-chip="N1"]').scroll_into_view_if_needed()
    page.locator('#viewRun [data-node-chip="N1"]').click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    box = page.locator("#nodeDetail").bounding_box()
    assert box["width"] <= width + 1, box
    page.keyboard.press("Escape")


def test_s0_source_badge_distinguishes_record_from_drill(ui):
    page, api = ui
    v = setup_run(api)
    v["s0_record_id"] = "S0-20261022-01"
    select(page, "A")
    pw.expect(page.locator("#gateHead")).to_contain_text("S0 记录 S0-20261022-01")
    open_run_view(page)
    pw.expect(page.locator("#runHead")).to_contain_text("S0 记录 S0-20261022-01")
    pw.expect(page.locator("#runHead")).not_to_contain_text("未经 S0 派生")

    # drill 且无 S0 记录：显式「未经 S0 派生（drill 不覆盖 S0）」，不得暗示环境就绪
    api["views"]["B"]["mode"] = "drill"
    api["views"]["B"]["s0_record_id"] = None
    select(page, "B")
    open_run_view(page)
    pw.expect(page.locator("#runHead")).to_contain_text("未经 S0 派生（drill 不覆盖 S0）")
    pw.expect(page.locator("#runHead")).not_to_contain_text("环境就绪")


def test_g2_material_opens_report_overlay_in_one_click(ui):
    """P-28 + 裁决 #8：G2 材料区**一次点击**直接弹报告全文浮窗（不再先开 N12 面板）。

    只读、无 POST；Esc 只关浮窗（节点面板本就没开），焦点可回触发按钮。
    """
    page, api = ui
    v = setup_run(api)
    v["pending_interrupt"]["id"] = "G2_report_accept:0"
    v["pending_interrupt"]["payload"]["gate"] = G2
    v["pending_interrupt"]["payload"]["report"] = {
        "n12_report": {"report_path": "runs/A/n12_report.md", "exists": True}}
    v["gate_options"][G2] = GATE_OPTIONS[G2]
    calls = []
    stub_report(page, body={"run_id": "A", "file": "n12_report.md",
                            "path": "/kb/runs/A/n12_report.md", "bytes": 321,
                            "truncated": False,
                            "content": "# G2 报告\n\n结论：未通过（not_passed）。"}, calls=calls)
    select(page, "A")
    pw.expect(page.locator("#viewGate")).to_be_visible()

    # 材料区仍保留"按 run 目录探测存在性"的那行路径
    row = page.locator("#gateMaterial .material-extra", has_text="N12 报告全文")
    pw.expect(row).to_be_visible()
    pw.expect(row).to_contain_text("n12_report.md")
    button = row.get_by_role("button", name="查看报告全文")
    button.click()

    # 一次点击：直接出现报告浮窗，节点面板没有被打开
    pw.expect(page.locator("#ndReportOverlay")).to_be_visible()
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()
    pw.expect(page.locator("#ndReportTitle")).to_contain_text("n12_report.md")
    pw.expect(page.locator("#ndReportMeta")).to_contain_text("321 B")
    pw.expect(page.locator("#ndReportBody")).to_contain_text("结论：未通过（not_passed）")
    assert page.evaluate("() => document.getElementById('ndReportBody').tagName") == "PRE"
    assert calls == ["/api/runs/A/report"], calls
    assert not api["posts"], api["posts"]

    # Esc 只关浮窗（节点面板未打开也要能正常关），回到闸门视图
    page.keyboard.press("Escape")
    pw.expect(page.locator("#ndReportOverlay")).to_be_hidden()
    pw.expect(page.locator("#viewGate")).to_be_visible()
    pw.expect(page.locator("#nodeDetail")).to_be_hidden()
    assert not api["posts"]


# ============================================================================
# 第三轮补充修订（R3-03/R3-06/R3-07/R3-08/R3-10/R3-12/R3-13）前端渲染
# 契约：doc/plans/2026-10-23-node-panel-revision-round3-impl.md §1.1/§1.2/§1.5/§6。
# 只读 DOM 断言：null（未下发）/ []（0 条）/ 有值 三种事实分别可见，前端不补默认值。
# ============================================================================

OBS_POINTS = [
    {"case": "tc_pcie_rw_02", "marker": "N6_fpga_date",
     "addr": "0x0000", "offset": "0x04", "expected_value": "0x20260708"},
    {"case": "tc_pcie_rw_03", "marker": "N6_baud_rate",
     "addr": "0x0010", "offset": "0x00", "expected_value": "0x0064"},
]


def n6_obs_story(points=OBS_POINTS, **overrides):
    """N6 story：observation_points 由服务端确定性透传（三态：数组 / null / []）。"""
    rows = 0 if points == [] else (len(points) if points else 0)
    story = story_for(
        "N6",
        purpose="让作者模型按影响清单改/补用例，并检查它的输出格式对不对。",
        headline="改了 2 个用例：tc_pcie_rw_02、tc_pcie_rw_03；输出校验通过。",
        status_note="真实模型调用",
        key_results=[
            {"field": "observation_points", "label": "观测点",
             "value": None if points is None else rows,
             "text": ("未下发（旧 run 或替身，模型未产出观测点）" if points is None
                      else "%d 条（逐条见下）" % rows),
             "missing": points is None},
        ],
        steps=[
            {"seq": 30, "at": 1792650940.0, "kind": "node_started", "status": "live", "text": "开始执行"},
            {"seq": 31, "at": 1792650941.0, "kind": "node_finished", "status": "ok", "text": "结束，状态 ok"},
        ],
    )
    story["observation_points"] = points
    story.update(overrides)
    return story


def n6_detail(points=OBS_POINTS):
    return node_detail(
        node="N6", name="修订", owner="author", status="live", source="model_live",
        summary="N6：目标 2 个用例，校验通过",
        detail={"cycle": 0, "targets": 2, "validation_ok": True},
        events=[
            {"seq": 30, "kind": "node_started", "node": "N6", "status": "running",
             "ts": 1792650940.0},
            {"seq": 31, "kind": "node_finished", "node": "N6", "status": "ok",
             "ts": 1792650941.0, "detail": {"source": "model_live"}},
        ],
        story=n6_obs_story(points))


def test_n6_observation_points_three_states_are_distinct(ui):
    """R3-03：数组 ⇒ 可折叠「观测点（N 条）」+ 每条四列；null ⇒ 未下发小字；[] ⇒ 0 条。"""
    page, api = ui
    setup_run(api)
    api["nodes"][("A", "N6")] = n6_detail()
    select(page, "A")
    open_run_view(page)
    open_node(page, "N6")

    details = page.locator("#ndKey .nd-obs-details")
    pw.expect(details).to_have_count(1)
    pw.expect(page.locator("#ndKey .nd-obs-summary")).to_contain_text("观测点（2 条）")
    # 默认收起：行在 DOM 里但不可见，点开后可见
    assert details.get_attribute("open") is None
    rows = page.locator("#ndKey .nd-obs-row")
    pw.expect(rows).to_have_count(2)
    pw.expect(rows.first).to_be_hidden()
    page.locator("#ndKey .nd-obs-summary").click()
    pw.expect(rows.first).to_be_visible()
    first_text = rows.first.inner_text()
    for token in ("用例", "tc_pcie_rw_02", "marker", "N6_fpga_date",
                  "addr+off", "0x0000+0x04", "期望值", "0x20260708"):
        assert token in first_text, (token, first_text)
    # 关键数字仍显示服务端给的「观测点」行（明细不替换摘要）
    pw.expect(page.locator("#ndKey")).to_contain_text("2 条（逐条见下）")
    page.keyboard.press("Escape")

    # null ⇒ 明说未下发（旧 run / 替身），不伪造 0 条
    api["nodes"][("A", "N6")] = n6_detail(points=None)
    tick(page)
    open_node(page, "N6")
    pw.expect(page.locator("#ndKey .nd-obs-details")).to_have_count(0)
    missing = page.locator("#ndKey .nd-obs-missing")
    pw.expect(missing).to_be_visible()
    pw.expect(missing).to_contain_text("未下发（旧 run 或替身，模型未产出观测点）")
    pw.expect(page.locator("#ndKey")).to_contain_text("未下发（旧 run 或替身，模型未产出观测点）")
    page.keyboard.press("Escape")

    # [] ⇒ 下发了但 0 条（不冒充 null）
    api["nodes"][("A", "N6")] = n6_detail(points=[])
    tick(page)
    open_node(page, "N6")
    pw.expect(page.locator("#ndKey .nd-obs-summary")).to_contain_text("观测点（0 条）")
    pw.expect(page.locator("#ndKey .nd-obs-missing")).to_have_count(0)
    page.locator("#ndKey .nd-obs-summary").click()
    pw.expect(page.locator("#ndKey .nd-obs-empty")).to_contain_text("0 条观测点")
    assert not api["posts"]


def test_evidence_groups_render_by_case_and_empty_group_keeps_server_note(ui):
    """R3-06：按用例分组；空 refs 组显示服务端 note；[] + note 显示说明；null ⇒ 平铺 refs。"""
    page, api = ui
    setup_run(api)
    groups = [
        {"case": "tc_pcie_rw_02", "refs": ["/kb/runs/A/logs/tc_pcie_rw_02_1_run.log"], "note": None},
        {"case": "tc_pcie_rw_03", "refs": [], "note": "本轮未执行/无证据"},
    ]
    story = story_for(
        "N9",
        purpose="让仿真真跑一遍受影响的用例，拿到可对账的日志。",
        headline="2 个用例全跑完：2 通过 0 失败。",
        steps=[{"seq": 45, "at": 1792650945.0, "kind": "node_finished", "status": "ok",
                "text": "全跑结束"}],
        key_results=[{"field": "executed", "label": "已执行", "value": True,
                      "text": "是", "missing": False}])
    story["evidence_groups"] = groups
    api["nodes"][("A", "N9")] = node_detail(
        node="N9", name="全跑", owner="Host", status="ok", source="kb_tool",
        summary="N9：2 个用例跑完",
        detail={"executed": True, "failed_cases": []},
        refs=["/kb/runs/A/logs/tc_pcie_rw_02_1_run.log"],
        story=story)
    select(page, "A")
    open_run_view(page)
    open_node(page, "N9")

    # 组头 = 服务端 case 原值；组内是 refs 行（存在性探测按钮仍保留）
    pw.expect(page.locator("#ndRefs .nd-ref-group")).to_have_count(2)
    first = page.locator("#ndRefs .nd-ref-group").first
    pw.expect(first.locator(".nd-ref-group-case")).to_have_text("tc_pcie_rw_02")
    pw.expect(first.locator(".nd-ref")).to_have_count(1)
    pw.expect(first.locator(".nd-ref .mono")).to_contain_text("tc_pcie_rw_02_1_run.log")
    # 空 refs 组不得留空白：显示服务端 note
    second = page.locator("#ndRefs .nd-ref-group").nth(1)
    pw.expect(second.locator(".nd-ref-group-case")).to_have_text("tc_pcie_rw_03")
    pw.expect(second.locator(".nd-ref")).to_have_count(0)
    pw.expect(second.locator(".nd-ref-group-note")).to_contain_text("本轮未执行/无证据")
    assert second.locator(".nd-ref-group-note").inner_text().strip() != ""
    page.keyboard.press("Escape")

    # [] + evidence_groups_note ⇒ 显示服务端说明（不编组），且不再报"证据缺失"
    story2 = story_for("N9", purpose="让仿真真跑一遍受影响的用例，拿到可对账的日志。",
                       headline="本轮没有可展示的证据文件。",
                       steps=[{"seq": 45, "at": 1792650945.0, "kind": "node_finished",
                               "status": "ok", "text": "全跑结束"}],
                       key_results=[])
    story2["evidence_groups"] = []
    story2["evidence_groups_note"] = "本轮没有证据文件（服务端未列出用例，也没有可展示的证据件）"
    api["nodes"][("A", "N9")] = node_detail(
        node="N9", name="全跑", owner="Host", status="ok", source="kb_tool",
        summary="N9：无证据文件", detail={"executed": True}, refs=[], story=story2)
    tick(page)
    open_node(page, "N9")
    pw.expect(page.locator("#ndRefs .nd-evidence-groups-note")).to_contain_text("本轮没有证据文件")
    pw.expect(page.locator("#ndRefs .nd-ref-group")).to_have_count(0)
    pw.expect(page.locator("#ndRefs")).not_to_contain_text("证据缺失")
    page.keyboard.press("Escape")

    # null（字段不存在）⇒ 维持现状平铺 refs，不报错
    story3 = story_for("N9", purpose="让仿真真跑一遍受影响的用例，拿到可对账的日志。",
                       headline="2 个用例全跑完：2 通过 0 失败。",
                       steps=[{"seq": 45, "at": 1792650945.0, "kind": "node_finished",
                               "status": "ok", "text": "全跑结束"}],
                       key_results=[])
    api["nodes"][("A", "N9")] = node_detail(
        node="N9", name="全跑", owner="Host", status="ok", source="kb_tool",
        summary="N9：2 个用例跑完", detail={"executed": True},
        refs=["/kb/runs/A/logs/tc_pcie_rw_02_1_run.log"], story=story3)
    tick(page)
    open_node(page, "N9")
    pw.expect(page.locator("#ndRefs .nd-ref-group")).to_have_count(0)
    pw.expect(page.locator("#ndRefs .nd-ref")).to_have_count(1)
    pw.expect(page.locator("#ndRefs .nd-evidence-groups-note")).to_have_count(0)
    assert not api["posts"]


def test_example_line_is_collapsed_and_omitted_when_not_sent(ui):
    """R3-07：N9 的 detail.example_line 默认收起，展开见原文；null/空 ⇒ 不渲染该块。"""
    page, api = ui
    setup_run(api)
    example = 'UVM_INFO top_env.sv(154) @ 0.000 us [N6_fpga_date] OK 0x0000+0x04 fpga_date = 0x20260708'
    api["nodes"][("A", "N9")] = node_detail(
        node="N9", name="全跑", owner="Host", status="ok", source="kb_tool",
        summary="N9：2 个用例跑完",
        detail={"executed": True, "example_line": example},
        refs=["/kb/runs/A/logs/tc_pcie_rw_02_1_run.log"], story=story_for("N9"))
    select(page, "A")
    open_run_view(page)
    open_node(page, "N9")

    box = page.locator("#ndRefs .nd-example")
    pw.expect(box).to_have_count(1)
    pw.expect(page.locator("#ndRefs .nd-example-summary")).to_contain_text("看一行示例")
    assert box.get_attribute("open") is None
    pw.expect(page.locator("#ndRefs .nd-example-line")).to_be_hidden()
    page.locator("#ndRefs .nd-example-summary").click()
    pw.expect(page.locator("#ndRefs .nd-example-line")).to_be_visible()
    pw.expect(page.locator("#ndRefs .nd-example-line")).to_have_text(example)
    page.keyboard.press("Escape")

    # example_line 未下发（null）⇒ 不渲染该块
    api["nodes"][("A", "N9")] = node_detail(
        node="N9", name="全跑", owner="Host", status="ok", source="kb_tool",
        summary="N9：2 个用例跑完", detail={"executed": True, "example_line": None},
        refs=["/kb/runs/A/logs/tc_pcie_rw_02_1_run.log"], story=story_for("N9"))
    tick(page)
    open_node(page, "N9")
    pw.expect(page.locator("#ndRefs .nd-example")).to_have_count(0)
    page.keyboard.press("Escape")

    # 空字符串同样不渲染
    api["nodes"][("A", "N9")] = node_detail(
        node="N9", name="全跑", owner="Host", status="ok", source="kb_tool",
        summary="N9：2 个用例跑完", detail={"executed": True, "example_line": "   "},
        refs=["/kb/runs/A/logs/tc_pcie_rw_02_1_run.log"], story=story_for("N9"))
    tick(page)
    open_node(page, "N9")
    pw.expect(page.locator("#ndRefs .nd-example")).to_have_count(0)


@pytest.mark.parametrize("run_status,gloss", [("failed", "失败"), ("finished", "已完成")])
def test_not_reached_headline_keeps_server_gloss_and_never_asks_to_wait(ui, run_status, gloss):
    """R3-08：not_reached 文案以服务端 story.headline 为准（状态原值 + 中文 gloss），不含"等它跑完"。"""
    page, api = ui
    setup_run(api)
    headline = "本轮没有走到这个节点（运行停在 %s，%s）。" % (run_status, gloss)
    api["nodes"][("A", "N10")] = node_detail(
        node="N10", name="结果对账", owner="checker", status=None, source=None,
        summary=None, detail={}, refs=[], events=[], known=True,
        missing_fields=["summary", "source"],
        run_status=run_status, run_terminal=True,
        story=story_for("N10", purpose="让检查模型把跑出来的日志和预期对一遍。",
                        headline=headline, not_reached=True, steps=[], key_results=[]))
    select(page, "A")
    open_run_view(page)
    open_node(page, "N10")

    # 服务端原文逐字显示：run_status 原值 + 中文 gloss 都在
    pw.expect(page.locator("#ndHeadline")).to_have_text(headline)
    pw.expect(page.locator("#ndHeadline")).to_contain_text(run_status)
    pw.expect(page.locator("#ndHeadline")).to_contain_text(gloss)
    body = page.locator("#ndContent").inner_text()
    assert "等它跑完" not in body, body
    pw.expect(page.locator("#ndSteps")).to_contain_text("没有走到这个节点")
    # template 来源不出现 headline 来源小字
    pw.expect(page.locator("#ndHeadline .nd-headline-src")).to_have_count(0)
    assert not api["posts"]


def test_not_executed_attribution_uses_server_text_without_demo_mode_phrase(ui):
    """R3-08/R3-10 前端兜底：未执行归因只取服务端 headline / evidence_note，不自行拼"演示模式"。"""
    page, api = ui
    setup_run(api)
    api["nodes"][("A", "N15_submit")] = node_detail(
        node="N15_submit", name="提交回归", owner="Host", status=None,
        source="drill_fixture", summary=None, detail={}, refs=[], events=[],
        known=True, missing_fields=["summary", "source"],
        run_status="halted", run_terminal=True,
        story=story_for(
            "N15_submit",
            purpose="把回归作业提交给集群，等待作业回执。",
            headline="本轮未执行这个节点（没有提交记录）。",
            not_executed=True,
            evidence_note={"text": "本轮未执行这个节点：没有提交记录，因此没有证据文件。",
                           "kind": "not_executed"},
            steps=[{"seq": 80, "at": 1792650980.0, "kind": "node_finished", "status": None,
                    "text": "跳过：运行在本节点之前已终止"}],
            key_results=[]))
    select(page, "A")
    open_run_view(page)
    page.locator('#viewRun [data-node-chip="N15_submit"]').scroll_into_view_if_needed()
    page.locator('#viewRun [data-node-chip="N15_submit"]').click()
    pw.expect(page.locator("#nodeDetail")).to_be_visible()

    # 归因文案逐字来自服务端（不是前端按 drill/演示拼的）
    pw.expect(page.locator("#ndHeadline")).to_have_text("本轮未执行这个节点（没有提交记录）。")
    pw.expect(page.locator("#ndRefs .nd-evidence-note")).to_have_text(
        "本轮未执行这个节点：没有提交记录，因此没有证据文件。")
    body = page.locator("#ndContent").inner_text()
    assert "演示模式" not in body, body          # R3-10：服务端给中性文案，前端不得自拼
    assert "等它跑完" not in body, body
    pw.expect(page.locator("#ndRefs")).not_to_contain_text("证据缺失")
    assert not api["posts"]


@pytest.mark.parametrize("source,badge", [("summary", "（原文摘要）"), ("missing", "（未下发）")])
def test_headline_source_badge_is_consumed_and_template_hides_it(ui, source, badge):
    """R3-12：headline_source 的授权消费者（summary/missing 显示小字，template 不显示）。"""
    page, api = ui
    setup_run(api)
    api["nodes"][("A", "N1")] = node_detail(story=story_for(
        headline="模型给出的一句话摘要：v0→v1，162 个用例未变。", headline_source=source))
    select(page, "A")
    open_run_view(page)
    open_node(page, "N1")

    src = page.locator("#ndHeadline .nd-headline-src")
    pw.expect(src).to_be_visible()
    pw.expect(src).to_have_text(badge)
    pw.expect(page.locator("#ndHeadline")).to_contain_text("模型给出的一句话摘要")
    page.keyboard.press("Escape")

    # template（默认）⇒ 不显示来源小字
    api["nodes"][("A", "N1")] = node_detail(story=story_for(headline="模板生成的一句话结果。"))
    tick(page)
    open_node(page, "N1")
    pw.expect(page.locator("#ndHeadline")).to_have_text("模板生成的一句话结果。")
    pw.expect(page.locator("#ndHeadline .nd-headline-src")).to_have_count(0)
    assert not api["posts"]


def test_gate_attached_evidence_note_visible_in_entry_overlay(ui):
    """R3-12：gate.entries[].attached[].note 必须在条目浮窗的附证据区可见（不只显示条数）。"""
    page, api = ui
    setup_gate_node(api)
    select(page, "A")
    open_run_view(page)
    open_node(page, "N4")

    first = page.locator("#ndGate .nd-gate-row").first
    # 行内仍只给条数（不计入修订点）
    pw.expect(first.locator(".nd-gate-meta")).to_contain_text("另有整文件指纹 1 条（不计入修订点）")
    first.locator(".nd-gate-open").click()
    pw.expect(page.locator("#ndDiffOverlay")).to_be_visible()

    attached = page.locator("#ndDiffOverlay .nd-attached")
    pw.expect(attached).to_be_visible()
    pw.expect(attached.locator(".nd-attached-item")).to_have_count(1)
    pw.expect(attached.locator(".nd-attached-meta")).to_contain_text("allfile")
    pw.expect(attached.locator(".nd-attached-meta")).to_contain_text("5fcc1a → 18fc02")
    # 服务端 note 原文必须可见（不是只显示"另有整文件指纹 N 条"）
    pw.expect(attached.locator(".nd-attached-note")).to_have_text("整文件指纹，不计入修订点")
    pw.expect(attached.locator(".nd-attached-hint")).to_contain_text("不计入")
    page.keyboard.press("Escape")
    pw.expect(page.locator("#ndDiffOverlay")).to_be_hidden()
    assert not api["posts"]


def test_dead_entry_decision_hint_path_is_removed_from_web_bundle():
    """R3-13：死路径 renderEntryDecisionHint 与其唯一调用已删除，全仓前端无残留引用。"""
    web = Path(__file__).resolve().parents[2] / "web"
    app_js = (web / "app.js").read_text(encoding="utf-8")
    css = (web / "app.css").read_text(encoding="utf-8")
    assert "renderEntryDecisionHint" not in app_js
    assert "entry-decisions-sample" not in app_js
    assert "entry-decisions-sample" not in css
    # 删的只是死路径：既有的逐条处置控件与闸门表单仍在
    assert "function renderEntryDecisionControls" in app_js
    assert "function syncEntryDecisionControls" in app_js
