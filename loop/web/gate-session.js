/* 闸门会话判定（F05）：身份、草稿协调与提交互斥的唯一实现。
 *
 * 纯函数：不读全局、不写 DOM、不发请求。会话协调 owner 仍是 app.js
 * （持有 state.gateDraft / state.gateSubmissions / selectionEpoch 并负责渲染）。
 *
 * 草稿身份 = run_id + interrupt.id + gate + cycle（Web UI §7.1）。
 */
(function (root) {
  "use strict";

  function sessionKey(runId, pending) {
    return JSON.stringify([runId, pending.id, pending.gate, pending.cycle]);
  }

  function freshDraft(key, gate) {
    return {
      key: key == null ? null : key,
      gate: gate == null ? null : gate,
      decision: null,
      actor: "human:",
      reason: "",
      // 逐条处置（Web UI §4.4 2026-10-23）：{entry_id: {decision, reason}}；只存界面输入，
      // 是否覆盖全部条目、是否与整门决策一致由服务端（I1）最终判定。
      entryDecisions: {},
      submitting: false,
      error: null,
      blockers: null,
      note: null
    };
  }

  /* 返回 {changed, draft}：新身份 ⇒ 全新草稿；同身份 ⇒ 保留输入；撤回选项只清决策。 */
  function reconcile(draft, input) {
    var key = sessionKey(input.runId, input.pending);
    if (!draft || draft.key !== key) {
      return { changed: true, draft: freshDraft(key, input.pending.gate) };
    }
    var options = Array.isArray(input.options) ? input.options : [];
    var valid = function (value) {
      for (var i = 0; i < options.length; i++) {
        if (options[i] && options[i].value === value) return true;
      }
      return false;
    };
    if (draft.decision !== null && draft.decision !== undefined && !valid(draft.decision)) {
      var next = {};
      for (var k in draft) {
        if (Object.prototype.hasOwnProperty.call(draft, k)) next[k] = draft[k];
      }
      next.decision = null;
      return { changed: false, draft: next };
    }
    return { changed: false, draft: draft };
  }

  function isSubmitting(ledger, key) {
    return !!(ledger && key != null && ledger[key]);
  }

  function beginSubmission(ledger, key) {
    if (isSubmitting(ledger, key)) return { started: false, ledger: ledger || {} };
    var next = {};
    for (var k in ledger || {}) {
      if (Object.prototype.hasOwnProperty.call(ledger, k)) next[k] = ledger[k];
    }
    next[key] = true;
    return { started: true, ledger: next };
  }

  function endSubmission(ledger, key) {
    var next = {};
    for (var k in ledger || {}) {
      if (Object.prototype.hasOwnProperty.call(ledger, k) && k !== key) next[k] = ledger[k];
    }
    return next;
  }

  function sameSelection(a, b) {
    if (!a || !b) return false;
    return a.runId === b.runId && a.epoch === b.epoch && a.request === b.request;
  }

  /* 逐条处置 → 整门决策的推导（Web UI §4.4 2026-10-23）。
   * 口径与服务端 gates.normalize_entry_decisions 一致：有 disputed ⇒ disputed；
   * 否则有 ignored ⇒ ignored；否则 confirmed。未选完返回 null（不猜）。 */
  function deriveEntryDecision(values) {
    var list = Array.isArray(values) ? values : [];
    if (!list.length) return null;
    var hasIgnored = false;
    for (var i = 0; i < list.length; i++) {
      var v = list[i];
      if (v === "disputed") return "disputed";
      if (v === "ignored") hasIgnored = true;
      if (v !== "confirmed" && v !== "ignored" && v !== "disputed") return null;
    }
    return hasIgnored ? "ignored" : "confirmed";
  }

  /* 逐条处置的界面前置校验（不是权威：服务端 I1 仍会再判一次）。
   * 返回 {ok, error, entry_decisions}；覆盖全部 ids、取值合法、ignored/disputed 带理由。 */
  function validateEntryDecisions(entryDecisions, ids, allowed) {
    var store = entryDecisions && typeof entryDecisions === "object" ? entryDecisions : {};
    var list = Array.isArray(ids) ? ids : [];
    var values = Array.isArray(allowed) ? allowed : ["confirmed", "ignored", "disputed"];
    var out = {};
    var missing = [];
    for (var i = 0; i < list.length; i++) {
      var id = String(list[i]);
      var raw = store[id];
      var value = raw && typeof raw === "object" ? String(raw.decision || "") : "";
      if (!value) { missing.push(id); continue; }
      if (values.indexOf(value) < 0) {
        return { ok: false, error: "条目 " + id + " 的处置非法：" + value, entry_decisions: null };
      }
      var reason = raw && typeof raw === "object" ? String(raw.reason || "").trim() : "";
      if ((value === "ignored" || value === "disputed") && !reason) {
        return { ok: false, error: "条目 " + id + " 判 " + value + " 必须填写理由", entry_decisions: null };
      }
      out[id] = { decision: value, reason: reason || null };
    }
    if (missing.length) {
      return {
        ok: false,
        error: "逐条处置未覆盖全部条目（缺 " + missing.length + " 条）：" + missing.slice(0, 3).join("、"),
        entry_decisions: null
      };
    }
    return { ok: true, error: null, entry_decisions: out };
  }

  /* U8-b（SPEC-REV-08，2026-10-24）：整门理由复用判定。
   * 推导出的整门决策 requires_reason 且逐条处置里已有同判据非空理由时，
   * 返回可预填文本（entry_id 排序首个，确定性）；否则 null。
   * app.js 只在整门理由为空时预填——不为空不覆盖，用户输入优先。 */
  function reusableReason(entryDecisions, derivedDecision, options) {
    if (!derivedDecision) return null;
    var list = Array.isArray(options) ? options : [];
    var needReason = false;
    for (var i = 0; i < list.length; i++) {
      if (list[i] && list[i].value === derivedDecision && list[i].requires_reason) {
        needReason = true;
        break;
      }
    }
    if (!needReason) return null;
    var store = entryDecisions && typeof entryDecisions === "object" ? entryDecisions : {};
    var ids = Object.keys(store).sort();
    for (var j = 0; j < ids.length; j++) {
      var cur = store[ids[j]];
      if (cur && typeof cur === "object" && String(cur.decision || "") === derivedDecision) {
        var reason = String(cur.reason || "").trim();
        if (reason) return reason;
      }
    }
    return null;
  }

  var api = {
    sessionKey: sessionKey,
    freshDraft: freshDraft,
    reconcile: reconcile,
    deriveEntryDecision: deriveEntryDecision,
    validateEntryDecisions: validateEntryDecisions,
    reusableReason: reusableReason,
    isSubmitting: isSubmitting,
    beginSubmission: beginSubmission,
    endSubmission: endSubmission,
    sameSelection: sameSelection
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.GateSession = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
