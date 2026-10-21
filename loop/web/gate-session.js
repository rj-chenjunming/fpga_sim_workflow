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

  var api = {
    sessionKey: sessionKey,
    freshDraft: freshDraft,
    reconcile: reconcile,
    isSubmitting: isSubmitting,
    beginSubmission: beginSubmission,
    endSubmission: endSubmission,
    sameSelection: sameSelection
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.GateSession = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
