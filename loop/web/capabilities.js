/* 能力事实的唯一前端格式化（F02-c）。
 *
 * 四维事实由服务端 `services/agent_view.py` 投影（运行视图角色卡与 Agent 窗口同一来源），
 * 前端只做**展示**：未知维度显示「未知」，`standin` 不显示成真实完成。
 * app.js 与 agent-window.js 都必须调用这里，不得各自再写一套。
 */
(function (root) {
  "use strict";

  var EXECUTION = { not_started: "未开始", standin: "替身", real: "真实", unknown: "未知" };
  var KEYS = ["implemented", "dependencies_ready", "execution", "verification_scope"];

  function line(c) {
    if (!c || typeof c !== "object") return "";
    var present = false;
    for (var i = 0; i < KEYS.length; i++) {
      if (Object.prototype.hasOwnProperty.call(c, KEYS[i])) { present = true; break; }
    }
    if (!present) return "";
    var impl = c.implemented === true ? "已实现" : (c.implemented === false ? "未实现" : "未知");
    var dep = c.dependencies_ready === true ? "齐备" : (c.dependencies_ready === false ? "缺失" : "未知");
    var exec = EXECUTION[c.execution] || "未知";
    var scope = c.verification_scope ? String(c.verification_scope) : "未知";
    return "能力 实现 " + impl + " · 依赖 " + dep + " · 本次 " + exec + " · 验证范围 " + scope;
  }

  var api = { line: line };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.Capabilities = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
