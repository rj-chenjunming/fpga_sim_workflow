/* U9（SPEC-REV-08 / SPEC-04 §4.5 注）：长任务卡空态判定。
 *
 * 纯函数：只消费服务端既有事件流投影（job_submitted/job_finished/dead_job），
 * 区分「无作业记录 / 最近一次作业已完成 / 作业已死亡」三种空态。
 * 与 deriveAgentStatus 同模式：展示推导，不新增判据、不写状态、不发请求。
 */
(function (root) {
  "use strict";

  var TERMINALS = { job_finished: 1, dead_job: 1 };

  function lastTerminal(events) {
    var found = null;
    (Array.isArray(events) ? events : []).forEach(function (e) {
      if (e && TERMINALS[e.kind]) found = e;
    });
    return found;
  }

  function emptyHint(events) {
    var last = lastTerminal(events);
    if (!last) return { kind: "none" };
    var detail = last.detail && typeof last.detail === "object" ? last.detail : {};
    return {
      kind: last.kind === "dead_job" ? "dead" : "finished",
      node: last.node || null,
      rc: detail.rc === undefined || detail.rc === null ? null : detail.rc,
      jobId: detail.job_id ? String(detail.job_id) : null
    };
  }

  function emptyText(events) {
    var hint = emptyHint(events);
    if (hint.kind === "none") return null;
    if (hint.kind === "dead") {
      return "最近一次作业已死亡（dead_job" +
        (hint.node ? " · " + hint.node : "") +
        (hint.jobId ? " · " + hint.jobId : "") +
        "）；见事件流与阻断项。";
    }
    return "最近一次作业已完成" +
      (hint.node ? "（" + hint.node : "(") +
      (hint.rc !== null ? " · rc=" + hint.rc : "") +
      "）；当前没有活动作业。";
  }

  var api = { emptyHint: emptyHint, emptyText: emptyText };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.JobStatus = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
