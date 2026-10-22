/* 上下文与尝试的只读解释（F10 / F11 前半 + R5）。
 *
 * 纯函数：不读全局、不发请求、不写 DOM，只把**记录里的事实**整理成可读行：
 *   - 预算构成：**只消费 Host 下发的 `context_budget` 测量**（`used_bytes`/`breakdown`/
 *     `overhead_bytes`/`limit_bytes`/`used_percent`），本层不求和、不另算占比、不判上限；
 *   - `offered`/`scope` 等未发送材料只作为 `storage`（记录存储大小）单列，不计费；
 *   - 人工确认经验的采用/拒绝原因（experience_diagnostics）；
 *   - 尝试摘要（status/model/cycle）；
 *   - 输入顶层字段差异（字节变化）。
 *
 * token 估算没有测量依据 ⇒ 永远返回 "unknown"，不得用字节数折算冒充。
 */
(function (root) {
  "use strict";

  /* 计费字段的展示顺序；数值全部来自 Host，不在此推导。 */
  var BILLED = ["input", "info", "instruct", "schema"];

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

  function numberOrNull(value) {
    return typeof value === "number" && isFinite(value) ? value : null;
  }

  function storage(host) {
    var raw = host && typeof host.storage === "object" && host.storage ? host.storage : {};
    return { offeredBytes: numberOrNull(raw.offered_bytes), scopeBytes: numberOrNull(raw.scope_bytes) };
  }

  function budget(measure) {
    var host = measure && typeof measure === "object" ? measure : {};
    var measured = host.measured === true && numberOrNull(host.used_bytes) !== null;
    var breakdown = measured && host.breakdown && typeof host.breakdown === "object" ? host.breakdown : {};
    var rows = [];
    if (measured) {
      BILLED.concat(Object.keys(breakdown).filter(function (key) {
        return BILLED.indexOf(key) < 0;
      }).sort()).forEach(function (field) {
        if (!Object.prototype.hasOwnProperty.call(breakdown, field)) return;
        var bytes = numberOrNull(breakdown[field]);
        if (bytes === null) return;
        rows.push({ label: field, bytes: bytes });
      });
    }
    var limit = numberOrNull(host.limit_bytes);
    if (limit !== null && limit <= 0) limit = null;
    return {
      measured: measured,
      rows: rows,
      totalBytes: measured ? numberOrNull(host.used_bytes) : null,
      overheadBytes: measured ? numberOrNull(host.overhead_bytes) : null,
      limitBytes: limit,
      usage: measured && limit !== null ? "known" : "unknown",
      usedPercent: measured && limit !== null ? numberOrNull(host.used_percent) : null,
      storage: storage(host),
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
