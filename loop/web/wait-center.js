/* U1 等待送达（SPEC-REV-07，2026-10-24）：等待态提醒的**纯判定**。
 *
 * 定位：本模块只回答三件事——
 *   · deriveAlerts：两拍 run 快照之间，哪些 run 发生了值得提醒的跃迁；
 *   · deriveActions：行动条聚合哪些条目（等待人工 / 失败）；
 *   · badgeTitle：标题徽标文本。
 * 提醒是投影的另一个消费者，不携带判定、不可回放为签署凭据；
 * DOM / Notification / 计时器由 app.js（会话协调 owner）承担，本模块不碰它们。
 *
 * 判定口径（与 tests/test_wait_center.py 同源）：
 *   · 首拍（prev 为 null）不提醒——没有「从什么跃迁」；
 *   · 跃迁进入 waiting_gate ⇒ gate；进入 failed ⇒ failed；离开 waiting_job ⇒ job_done；
 *   · 同一拍同一 run 至多一条，优先级 gate > failed > job_done（闸门更需要人）；
 *   · 状态不变、新出现的 run 不提醒。
 */
"use strict";

(function (root) {
  function snapshotOf(runs) {
    var map = Object.create(null);
    var list = Array.isArray(runs) ? runs : [];
    for (var i = 0; i < list.length; i++) {
      var r = list[i];
      if (r && r.run_id) map[String(r.run_id)] = r.status;
    }
    return map;
  }

  function alertKindOf(from, to) {
    /* 返回该 run 本拍的提醒类型；无跃迁返回 null。优先级在返回值上体现：
       gate > failed > job_done（waiting_job → waiting_gate 同时满足两条，只取 gate）。 */
    if (to === "waiting_gate" && from !== "waiting_gate") return "gate";
    if (to === "failed" && from !== "failed") return "failed";
    if (from === "waiting_job" && to !== "waiting_job") return "job_done";
    return null;
  }

  function deriveAlerts(prevRuns, nextRuns) {
    var prev = prevRuns === null || prevRuns === undefined
      ? null : snapshotOf(prevRuns);
    if (prev === null) return [];
    var next = Array.isArray(nextRuns) ? nextRuns : [];
    var out = [];
    for (var i = 0; i < next.length; i++) {
      var r = next[i];
      if (!r || !r.run_id) continue;
      var rid = String(r.run_id);
      if (!(rid in prev)) continue;
      var kind = alertKindOf(prev[rid], r.status);
      if (kind) out.push({ run_id: rid, from: prev[rid], to: r.status, kind: kind });
    }
    return out;
  }

  function deriveActions(runs) {
    var gates = [], failed = [];
    var list = Array.isArray(runs) ? runs : [];
    for (var i = 0; i < list.length; i++) {
      var r = list[i];
      if (!r || !r.run_id) continue;
      if (r.status === "waiting_gate") gates.push({ run_id: String(r.run_id), status: r.status, kind: "gate" });
      else if (r.status === "failed") failed.push({ run_id: String(r.run_id), status: r.status, kind: "failed" });
    }
    return gates.concat(failed);
  }

  function attentionCount(runs) {
    return deriveActions(runs).length;
  }

  function badgeTitle(base, count) {
    var n = typeof count === "number" && count > 0 ? count : 0;
    return n > 0 ? "(" + n + ") " + String(base) : String(base);
  }

  var WaitCenter = {
    deriveAlerts: deriveAlerts,
    deriveActions: deriveActions,
    attentionCount: attentionCount,
    badgeTitle: badgeTitle
  };

  root.WaitCenter = WaitCenter;
  if (typeof module !== "undefined" && module.exports) module.exports = WaitCenter;
})(typeof window !== "undefined" ? window : globalThis);
