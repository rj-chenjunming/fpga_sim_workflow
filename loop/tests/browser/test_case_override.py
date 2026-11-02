"""SPEC-REV-20 §8 界面契约：G2/N13 面板「机器原因 + 认定通过/撤销」、二次确认、豁免徽标、终态只读。

真实静态页 + 受控 API 替身（与 `test_run_sessions.py` 共用 `ui` fixture）：不模拟真实台账，
只证明展示层的可观察行为 ——

1. 逐用例表把 `case_failures.cases[*].reasons` **原文**显示出来（不翻译、不截断成结论），
   证据件 `path` / `md5` 同屏；
2. 点「认定通过」⇒ 二次确认弹窗：原文机器原因 + 证据 path + md5 + 必填理由，
   空理由/全空白理由不能提交；弹窗明确写「这是人签例外，会记入台账，报告仍显示本轮未通过」；
3. 提交形状 = `POST /api/runs/{run_id}/cases/override {action,cases,actor,reason}`；
4. 服务端 400/403/409/404 一律显示服务端 `detail.error`（409 读 `detail.reason`）原文，
   不得改写成「操作失败」；
5. **判据只在服务端**：缺 `case_override` 投影 ⇒ 明说「服务端未下发可覆写判定 ⇒ 不可提交」，
   按钮禁用、不发请求；逐例 `available=false` ⇒ 禁用并显示服务端 `blocked_reason`；
6. 「人签豁免」徽标（含 actor 与日期）出现在逐用例表 / 报告横幅 / 看板，且机器原判同屏
   （不得显示成普通通过）；
7. 撤销入口与覆写同处；终态 run 上按钮禁用并显示服务端 blocked_reason。

本文件不发真实请求、不改任何台账：POST 由替身挂起，测试显式 `release()`。
"""
from __future__ import annotations

import pytest

from test_run_sessions import ui, static_url, select, tick, release, pw  # noqa: F401

G2 = "G2_report_accept"
CASE = "tc_rtc_05"
CASE_OK = "tc_rtc_10"

# 机器原因：故意写长 + 带中文标点与枚举原值，钉住「原文照登、不截断」。
LONG_REASON = (
    "印记 N6_pcie_test_tc_rtc_05 三向不一致：['value_matches_expected']；"
    "期望值来自旧文档条目（doc/interface.md:120），实测 koutou1=0、koutou2 UVM_ERROR=0 / UVM_FATAL=0，"
    "该条不做任何截断或结论化改写，界面必须原文照登。"
)
CRITERION = "PASS ⟺ 两套口径皆 0 ∧ UVM Report Summary 出现 ∧ 期望观测点印记三向一致"
EVIDENCE_PATH = "evidence/20261024-003330_tc_rtc_05_1_run.log"
EVIDENCE_MD5 = "3f0c9a1b7f51e0d2e38c6a4b9d5a72c1e0b48f6d2a9c7e5b1f30d8c6a42b9e57"
WAIVER_ACTOR = "human:chenjunming"
WAIVER_AT = "2026-11-02T11:00:00+0800"
WAIVER_REASON = "期望值来自旧文档条目；实测值与本变预期一致，属期望过期"
REASON_TEXT = "期望值来自旧文档条目，属期望过期，同意人签例外"
MISSING_MACHINE_REASON = "该例机器原因未留存（n10_cases.json 无该例），不能盲签"
TERMINAL_REASON = "本轮已结束，不可撤销"


def machine_cases():
    """`n10_cases.json` 的界面投影（`case_failures`）：只有 tc_rtc_05 有机器原因。"""
    return {
        CASE: {
            "case": CASE, "passed": False, "criterion": CRITERION,
            "reasons": [LONG_REASON],
            "counts": {"koutou1": {"value": 0},
                       "koutou2": {"value": {"UVM_ERROR": 0, "UVM_FATAL": 0}}},
            "evidence": {"path": EVIDENCE_PATH, "md5": EVIDENCE_MD5, "bytes": 123456},
        },
    }


def ledger_cases(waived=False):
    """台账读模型（`case_states_view` 形状）：`waived`/`waiver` 是服务端投影。"""
    case = {"case": CASE, "state": "已修订待验", "own": True, "waived": False,
            "updated_at": "2026-11-01T10:00:00+0800", "updated_by": "host",
            "waiver": None}
    ok = {"case": CASE_OK, "state": "已验证通过", "own": True, "waived": False,
          "updated_at": "2026-11-01T10:00:00+0800", "updated_by": "host", "waiver": None}
    if waived:
        case["state"] = "已验证通过"
        case["waived"] = True
        case["waiver"] = {
            "action": "pass", "actor": WAIVER_ACTOR, "reason": WAIVER_REASON,
            "decided_at": WAIVER_AT, "prev_state": "已修订待验",
            "machine": {"passed": False, "criterion": CRITERION,
                        "reasons": [LONG_REASON],
                        "evidence": {"path": EVIDENCE_PATH, "md5": EVIDENCE_MD5}},
        }
    return [case, ok]


def waiver_view(waived=False):
    """人签豁免投影（`case_waivers_view` 形状）。"""
    if not waived:
        return {"present": True, "path": "/fixture/A/case_states.json", "count": 0,
                "count_waived": 0, "cases": [], "pending_count": 0, "pending": []}
    case = ledger_cases(True)[0]
    w = case["waiver"]
    return {"present": True, "path": "/fixture/A/case_states.json", "count": 1,
            "count_waived": 1, "pending_count": 1, "pending": [CASE],
            "cases": [{"case": CASE, "state": case["state"], "own": True,
                       "action": w["action"], "actor": w["actor"], "reason": w["reason"],
                       "decided_at": w["decided_at"], "prev_state": w["prev_state"],
                       "machine": w["machine"]}]}


def override_projection(*, waived=False, terminal=False, enabled=True):
    """服务端 `case_override` 投影（SPEC-REV-20 §6.1，Lead 2026-11-02 裁定 shape）。

    顶层 `enabled`/`blocked_reason` = **整轮**判定（终态 / 非等待闸门 / 机器原因未留存）；
    逐例 `cases[c].actions.<pass|revoke>` 各自 `{available, blocked_reason}` = **例级**动作判定。
    前端只消费这两处：整轮不可签就用顶层原因，整轮可签才看例级动作；不按 state/原因自拼。
    """
    if terminal:
        return {
            "enabled": False, "blocked_reason": TERMINAL_REASON,
            "cases": {CASE: {"state": "已验证通过", "machine_present": True, "actions": {
                # 故意让例级动作写着「可用」：界面必须以顶层 enabled=false 为准（两者不混用）
                "pass": {"available": True, "blocked_reason": None},
                "revoke": {"available": True, "blocked_reason": None},
            }}},
        }
    if waived:
        return {
            "enabled": enabled, "blocked_reason": None if enabled else "服务端未启用覆写",
            "cases": {
                CASE: {"state": "已验证通过", "machine_present": True, "actions": {
                    "pass": {"available": False,
                             "blocked_reason": "§4-4 当前态是「已验证通过」，pass 要求「已修订待验」"},
                    "revoke": {"available": enabled,
                               "blocked_reason": None if enabled else "服务端未启用覆写"},
                }},
                CASE_OK: {"state": "已验证通过", "machine_present": False, "actions": {
                    "pass": {"available": False, "blocked_reason": "§4-4 当前态已是「已验证通过」"},
                    "revoke": {"available": False,
                               "blocked_reason": "该例的通过不是人签覆写产生的，不得用撤销塞回待验"},
                }},
            },
        }
    return {
        "enabled": enabled, "blocked_reason": None if enabled else "服务端未启用覆写",
        "cases": {
            CASE: {"state": "已修订待验", "machine_present": True, "actions": {
                "pass": {"available": enabled,
                         "blocked_reason": None if enabled else "服务端未启用覆写"},
                "revoke": {"available": False,
                           "blocked_reason": "§4-4 当前态是「已修订待验」，revoke 要求「已验证通过」"},
            }},
            CASE_OK: {"state": "已修订待验", "machine_present": False, "actions": {
                "pass": {"available": False, "blocked_reason": MISSING_MACHINE_REASON},
                "revoke": {"available": False, "blocked_reason": "§4-4 当前态是「已修订待验」"},
            }},
        },
    }


def populate_g2(api, *, waived=False, override="default", run_status="waiting_gate",
                terminal=False):
    """把替身运行 A 变成 G2 闸门视图（材料带逐例机器原因/台账/豁免 + 覆写投影）。"""
    view = api["views"]["A"]
    view["status"] = run_status
    if terminal:
        view["pending_interrupt"] = None
    else:
        payload = view["pending_interrupt"]["payload"]
        payload.update({
            "gate": G2,
            "gate_node": "N13",
            "cycle": 0,
            "difference_items": {"present": True, "mode": "real", "entries": [],
                                 "count": 0, "unresolved_count": 0},
            "case_failures": {"present": True, "path": "/fixture/A/n10_cases.json",
                              "missing": None, "count": len(machine_cases()),
                              "criterion": CRITERION, "cases": machine_cases()},
            "case_states": {"present": True, "path": "/fixture/A/case_states.json",
                            "cases": ledger_cases(waived),
                            "pending_own": [] if waived else [CASE]},
            "case_waivers": waiver_view(waived),
        })
        view["gate_options"] = {G2: [{"value": "accept", "label": "接受", "requires_reason": True},
                                     {"value": "rework", "label": "返工", "requires_reason": True}]}
    view["case_states"] = {"present": True, "path": "/fixture/A/case_states.json",
                           "cases": ledger_cases(waived),
                           "pending_own": [] if waived else [CASE]}
    view["case_waivers"] = waiver_view(waived)
    view.pop("case_override", None)
    if override == "default":
        view["case_override"] = override_projection(waived=waived, terminal=terminal)
    elif override is not None:
        view["case_override"] = override
    return view


def open_g2(page, api, **kwargs):
    populate_g2(api, **kwargs)
    select(page, "A")
    pw.expect(page.locator("#viewGate")).to_be_visible()
    section = page.locator("#gateMaterial [data-case-override]")
    pw.expect(section).to_have_count(1)
    return section


def row_of(section, case=CASE):
    return section.locator('[data-case="%s"]' % case)


def fill_and_submit(dlg, reason=REASON_TEXT, actor=WAIVER_ACTOR):
    dlg.locator("#coActor").fill(actor)
    dlg.locator("#coReason").fill(reason)
    dlg.locator("[data-override-submit]").click()


# ---------------------------------------------------------------------------
# ① 机器原因原文 + 证据件 + 逐例可用性（判据只在服务端）
# ---------------------------------------------------------------------------
def test_g2_panel_shows_machine_reasons_verbatim_with_evidence(ui):
    page, api = ui
    section = open_g2(page, api)

    row = row_of(section)
    pw.expect(row).to_have_count(1)
    # 原文照登：整段 reasons 文本必须在，且不是结论化改写
    pw.expect(row).to_contain_text(LONG_REASON)
    # 证据件身份：路径与 md5 都要在
    pw.expect(row).to_contain_text(EVIDENCE_PATH)
    pw.expect(row).to_contain_text(EVIDENCE_MD5)
    # 机器原判同屏（不得只显示人的结论）
    pw.expect(row).to_contain_text("未通过")

    # 服务端说可签 ⇒ 按钮可用
    pw.expect(row.locator('[data-case-override-action="pass"]')).to_be_enabled()

    # 服务端说不可签（机器原因未留存）⇒ 按钮禁用 + 显示服务端 blocked_reason 原文
    other = row_of(section, CASE_OK)
    pw.expect(other).to_contain_text(MISSING_MACHINE_REASON)
    pw.expect(other.locator('[data-case-override-action="pass"]')).to_be_disabled()
    assert not api["posts"]


def test_missing_override_projection_blocks_submit_and_says_so(ui):
    """投影缺件时**不得兜底猜**：明说不可提交、按钮禁用、一个请求都不发。"""
    page, api = ui
    section = open_g2(page, api, override=None)
    pw.expect(section).to_contain_text("服务端未下发可覆写判定")
    btn = row_of(section).locator("[data-case-override-action]")
    pw.expect(btn).to_be_disabled()
    btn.evaluate("el => el.click()")
    page.wait_for_timeout(60)
    pw.expect(page.locator("#caseOverrideDialog")).not_to_be_visible()
    assert not api["posts"]


def test_projection_disabled_shows_server_blocked_reason_not_guess(ui):
    page, api = ui
    section = open_g2(page, api, override=override_projection(enabled=False))
    pw.expect(section).to_contain_text("服务端未启用覆写")
    pw.expect(row_of(section).locator('[data-case-override-action="pass"]')).to_be_disabled()
    assert not api["posts"]


# ---------------------------------------------------------------------------
# ② 二次确认：原文机器原因 + 证据 path/md5 + 必填理由 + 显式「人签例外」提示
# ---------------------------------------------------------------------------
def test_override_dialog_shows_evidence_requires_reason_and_submits(ui):
    page, api = ui
    section = open_g2(page, api)
    row_of(section).locator('[data-case-override-action="pass"]').click()

    dlg = page.locator("#caseOverrideDialog")
    pw.expect(dlg).to_be_visible()
    pw.expect(dlg).to_contain_text(LONG_REASON)
    pw.expect(dlg).to_contain_text(EVIDENCE_PATH)
    pw.expect(dlg).to_contain_text(EVIDENCE_MD5)
    pw.expect(dlg).to_contain_text("这是人签例外，会记入台账；报告仍显示本轮未通过")

    submit = dlg.locator("[data-override-submit]")
    pw.expect(submit).to_be_disabled()

    # 理由全空白 ⇒ 仍不可提交
    dlg.locator("#coActor").fill(WAIVER_ACTOR)
    dlg.locator("#coReason").fill("   \n  ")
    pw.expect(submit).to_be_disabled()
    assert not api["posts"], "空理由不得提交"

    dlg.locator("#coReason").fill(REASON_TEXT)
    pw.expect(submit).to_be_enabled()
    submit.click()
    page.wait_for_timeout(80)
    assert api["posts"] == [("/api/runs/A/cases/override",
                             {"action": "pass", "cases": [CASE],
                              "actor": WAIVER_ACTOR, "reason": REASON_TEXT})]
    release(page, api, {"ok": True, "action": "pass",
                        "results": [{"case": CASE, "state": "已验证通过"}],
                        "case_waivers": waiver_view(True), "warnings": []})
    pw.expect(dlg).not_to_be_visible()
    pw.expect(page.locator("#toast")).to_contain_text("人签豁免")


def test_override_dialog_cancel_sends_nothing_and_restores_focus(ui):
    page, api = ui
    section = open_g2(page, api)
    row = row_of(section)
    btn = row.locator('[data-case-override-action="pass"]')
    btn.click()
    dlg = page.locator("#caseOverrideDialog")
    pw.expect(dlg).to_be_visible()
    dlg.locator("#coCancel").click()
    pw.expect(dlg).not_to_be_visible()
    pw.expect(btn).to_be_focused()
    assert not api["posts"]


# ---------------------------------------------------------------------------
# ③ 服务端拒绝：原样显示 detail.error / detail.reason，不改写成「操作失败」
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("status,body,expected", [
    (400, {"detail": {"error": "cases 不能为空"}}, "cases 不能为空"),
    (403, {"detail": {"error": "该用例不在台账：tc_rtc_05",
                      "blockers": [{"code": "CASE_NOT_IN_LEDGER",
                                    "message": "台账里没有 tc_rtc_05"}]}},
     "该用例不在台账：tc_rtc_05"),
    (409, {"detail": {"reason": "台账与 n10_cases.json 不一致：n10_cases.json 缺失"}},
     "台账与 n10_cases.json 不一致：n10_cases.json 缺失"),
    (404, {"detail": {"error": "run 不存在：RUN-ABSENT"}}, "run 不存在：RUN-ABSENT"),
])
def test_override_rejection_shows_server_text_verbatim(ui, status, body, expected):
    page, api = ui
    section = open_g2(page, api)
    row_of(section).locator('[data-case-override-action="pass"]').click()
    dlg = page.locator("#caseOverrideDialog")
    pw.expect(dlg).to_be_visible()
    fill_and_submit(dlg)
    page.wait_for_timeout(80)
    release(page, api, body, status=status)
    err = dlg.locator("#coError")
    pw.expect(err).to_contain_text(expected)
    pw.expect(err).not_to_contain_text("操作失败")
    # 403 的 detail.blockers[] 逐条原样列出（每条自带 §4-x，界面不合并成结论）
    for blocker in (body.get("detail") or {}).get("blockers") or []:
        pw.expect(err).to_contain_text(blocker["message"])
    # 弹窗仍在、理由保留、提交按钮回到可用（不卡在「提交中…」）
    pw.expect(dlg).to_be_visible()
    pw.expect(dlg.locator("#coReason")).to_have_value(REASON_TEXT)
    pw.expect(dlg.locator("[data-override-submit]")).to_be_enabled()


# ---------------------------------------------------------------------------
# ④ 人签豁免徽标：用例表 / 报告横幅 / 看板（含 actor 与日期），且机器原判同屏
# ---------------------------------------------------------------------------
def test_waiver_badge_in_case_list_report_banner_and_board(ui):
    page, api = ui
    section = open_g2(page, api, waived=True)

    row = row_of(section)
    pw.expect(row).to_contain_text("人签豁免")
    pw.expect(row).to_contain_text(WAIVER_ACTOR)
    pw.expect(row).to_contain_text("2026-11-02")
    # O-5：不得显示成普通通过 —— 机器原判（未通过）+ 原文原因必须同屏
    pw.expect(row).to_contain_text("未通过")
    pw.expect(row).to_contain_text(LONG_REASON)

    # 报告页横幅（材料区 N12 报告入口同屏）
    pw.expect(page.locator("#gateMaterial")).to_contain_text("本轮 1 例人签豁免（见台账 overrides）")

    # 看板（运行视图）：同样带 actor 与日期
    page.locator("#segRun").click()
    board = page.locator("#countsBody")
    pw.expect(board).to_contain_text("人签豁免")
    pw.expect(board).to_contain_text(WAIVER_ACTOR)
    pw.expect(board).to_contain_text("2026-11-02")


# ---------------------------------------------------------------------------
# ⑤ 撤销入口与覆写同处；终态 run 禁用并显示服务端 blocked_reason
# ---------------------------------------------------------------------------
def test_revoke_entry_shares_row_and_submits_revoke_action(ui):
    page, api = ui
    section = open_g2(page, api, waived=True)
    row = row_of(section)
    btn = row.locator('[data-case-override-action="revoke"]')
    pw.expect(btn).to_be_enabled()
    btn.click()
    dlg = page.locator("#caseOverrideDialog")
    pw.expect(dlg).to_be_visible()
    pw.expect(dlg).to_contain_text("撤销")
    # 撤销也必须填理由（同一入口同一约束）
    pw.expect(dlg.locator("[data-override-submit]")).to_be_disabled()
    dlg.locator("#coActor").fill(WAIVER_ACTOR)
    dlg.locator("#coReason").fill("撤销刚才的人签豁免，恢复待验")
    pw.expect(dlg.locator("[data-override-submit]")).to_be_enabled()
    dlg.locator("[data-override-submit]").click()
    page.wait_for_timeout(80)
    assert api["posts"] == [("/api/runs/A/cases/override",
                             {"action": "revoke", "cases": [CASE],
                              "actor": WAIVER_ACTOR,
                              "reason": "撤销刚才的人签豁免，恢复待验"})]
    release(page, api, {"ok": True, "action": "revoke",
                        "results": [{"case": CASE, "state": "已修订待验"}],
                        "case_waivers": waiver_view(False), "warnings": []})


def test_non_override_pass_cannot_be_revoked(ui):
    """服务端说「该例的通过不是人签覆写产生的」⇒ 撤销禁用并显示原因（前端不自己判）。"""
    page, api = ui
    section = open_g2(page, api, waived=True)
    other = row_of(section, CASE_OK)
    pw.expect(other.locator('[data-case-override-action="revoke"]')).to_be_disabled()
    pw.expect(other).to_contain_text("该例的通过不是人签覆写产生的，不得用撤销塞回待验")
    assert not api["posts"]


def test_missing_per_action_verdict_blocks_that_entry(ui):
    """`cases[c].actions` 里没有本动作条目 ⇒ 该入口禁用并明说，不拿另一动作的判据顶替。"""
    page, api = ui
    partial = {"enabled": True, "blocked_reason": None,
               "cases": {CASE: {"state": "已验证通过", "machine_present": True,
                                "actions": {"pass": {
                                    "available": False,
                                    "blocked_reason": "§4-4 当前态是「已验证通过」，pass 要求「已修订待验」",
                                }}}}}
    section = open_g2(page, api, waived=True, override=partial)
    btn = row_of(section).locator('[data-case-override-action="revoke"]')
    pw.expect(btn).to_be_disabled()
    pw.expect(row_of(section)).to_contain_text("服务端未下发该用例「撤销」判定")
    btn.evaluate("el => el.click()")
    page.wait_for_timeout(60)
    assert not api["posts"]


def test_terminal_run_disables_actions_and_shows_server_blocked_reason(ui):
    page, api = ui
    populate_g2(api, waived=True, run_status="finished", terminal=True)
    select(page, "A")
    page.locator("#segGate").click()
    pw.expect(page.locator("#viewGate")).to_be_visible()

    section = page.locator("#gateMaterial [data-case-override]")
    pw.expect(section).to_have_count(1)
    pw.expect(section).to_contain_text(TERMINAL_REASON)
    # 终态仍要看得见豁免徽标（含 actor 与日期），只是不可再操作
    pw.expect(row_of(section)).to_contain_text("人签豁免")
    pw.expect(row_of(section)).to_contain_text(WAIVER_ACTOR)
    btn = row_of(section).locator('[data-case-override-action="revoke"]')
    pw.expect(btn).to_be_disabled()
    btn.evaluate("el => el.click()")
    page.wait_for_timeout(60)
    assert not api["posts"]


def test_server_downgrade_after_poll_disables_the_entry(ui):
    """判据只在服务端：轮询把 enabled 改成 false ⇒ 按钮立刻禁用、不再能发起（不缓存旧判定）。"""
    page, api = ui
    section = open_g2(page, api)
    pw.expect(row_of(section).locator('[data-case-override-action="pass"]')).to_be_enabled()
    api["views"]["A"]["case_override"] = override_projection(enabled=False)
    tick(page)
    section = page.locator("#gateMaterial [data-case-override]")
    pw.expect(section).to_contain_text("服务端未启用覆写")
    pw.expect(row_of(section).locator('[data-case-override-action="pass"]')).to_be_disabled()
    assert not api["posts"]


# ---------------------------------------------------------------------------
# ⑥ N16（晋升）面板：人签豁免清单（含 actor 与日期）+ 机器原判同屏
# ---------------------------------------------------------------------------
def test_n16_panel_lists_waivers_with_actor_and_date(ui):
    page, api = ui
    populate_g2(api, waived=True)
    select(page, "A")
    # N16 没有 agent 卡片 ⇒ 节点 chip 打开节点详情 <dialog>；折叠段里的 chip 直接派发 click。
    page.locator('#stages [data-node-chip="N16"]').evaluate("el => el.click()")
    panel = page.locator("#nodeDetail")
    pw.expect(panel).to_be_visible()
    block = page.locator("#ndWaiverBlock")
    pw.expect(block).to_be_visible()
    pw.expect(block).to_contain_text("人签豁免")
    pw.expect(block).to_contain_text(WAIVER_ACTOR)
    pw.expect(block).to_contain_text("2026-11-02")
    # 机器原判同屏（不得只显示人的结论）
    pw.expect(block).to_contain_text("机器原判：未通过")
    pw.expect(block).to_contain_text(LONG_REASON)
    assert not api["posts"]
