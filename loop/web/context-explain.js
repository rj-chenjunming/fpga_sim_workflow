/* 上下文与尝试的只读解释（F10 / F11 前半）。
 *
 * 纯函数：不读全局、不发请求、不写 DOM，只把**记录里的事实**整理成可读行：
 *   - 预算构成（UTF-8 字节与占比）与上限（上限由服务端下发，不在前端硬编码）；
 *   - 人工确认经验的采用/拒绝原因（experience_diagnostics）；
 *   - 尝试摘要（status/model/cycle）；
 *   - 输入顶层字段差异（字节变化）。
 *
 * token 估算没有测量依据 ⇒ 永远返回 "unknown"，不得用字节数折算冒充。
 */
(function (root) {
  "use strict";

  var FIELDS = ["input", "info", "instruct", "schema", "offered", "scope"];

  function byteLength(text) {
    var str = text === null || text === undefined ? "" : String(text);
    if (typeof TextEncoder !== "undefined") return new TextEncoder().encode(str).length;
    return unescape(encodeURIComponent(str)).length;
  }

  function jsonBytes(value) {
    if (value === undefined) return 0;
    var text;
    try {
      text = JSON.stringify(value);
    } catch (e) {
      return 0;
    }
    if (text === undefined) return 0;
    return byteLength(text);
  }

  function budget(request, limitBytes) {
    request = request || {};
    var rows = [];
    var total = 0;
    FIELDS.forEach(function (key) {
      if (!Object.prototype.hasOwnProperty.call(request, key)) return;
      var bytes = jsonBytes(request[key]);
      rows.push({ label: key, bytes: bytes });
      total += bytes;
    });
    rows.forEach(function (row) {
      row.percent = total > 0 ? Math.round((row.bytes / total) * 100) : 0;
    });
    var limit = typeof limitBytes === "number" && isFinite(limitBytes) && limitBytes > 0 ? limitBytes : null;
    return {
      rows: rows,
      totalBytes: total,
      limitBytes: limit,
      usage: limit === null ? "unknown" : "known",
      usedPercent: limit === null ? null : Math.round((total / limit) * 100),
      tokenEstimate: "unknown"
    };
  }

  function experience(request) {
    var diagnostics = request && Array.isArray(request.experience_diagnostics)
      ? request.experience_diagnostics : [];
    return diagnostics.map(function (item) { return { message: String(item) }; });
  }

  function attempts(items) {
    return (Array.isArray(items) ? items : []).slice().sort(function (a, b) {
      return Number(a.attempt) - Number(b.attempt);
    }).map(function (item) {
      return {
        attempt: Number(item.attempt),
        status: item.status ? String(item.status) : "未知",
        model: item.model ? String(item.model) : "未知",
        cycle: item.cycle === undefined || item.cycle === null ? "未知" : item.cycle
      };
    });
  }

  function inputDiff(previous, current) {
    var before = previous && typeof previous === "object" ? previous : {};
    var after = current && typeof current === "object" ? current : {};
    var keys = {};
    Object.keys(before).forEach(function (key) { keys[key] = true; });
    Object.keys(after).forEach(function (key) { keys[key] = true; });
    var rows = [];
    Object.keys(keys).sort().forEach(function (key) {
      var hasBefore = Object.prototype.hasOwnProperty.call(before, key);
      var hasAfter = Object.prototype.hasOwnProperty.call(after, key);
      var fromBytes = hasBefore ? jsonBytes(before[key]) : 0;
      var toBytes = hasAfter ? jsonBytes(after[key]) : 0;
      if (hasBefore === hasAfter &&
          safeStringify(before[key]) === safeStringify(after[key])) {
        return;
      }
      rows.push({
        key: key,
        change: !hasBefore ? "added" : (!hasAfter ? "removed" : "changed"),
        fromBytes: fromBytes,
        toBytes: toBytes
      });
    });
    return { changed: rows.length > 0, rows: rows };
  }

  function safeStringify(value) {
    try {
      return JSON.stringify(value);
    } catch (e) {
      return String(value);
    }
  }

  function tokenEstimate() {
    return "unknown";
  }

  var api = {
    byteLength: byteLength,
    budget: budget,
    experience: experience,
    attempts: attempts,
    inputDiff: inputDiff,
    tokenEstimate: tokenEstimate
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.ContextExplain = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
