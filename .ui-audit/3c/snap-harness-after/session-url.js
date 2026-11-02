/* U7（SPEC-REV-08 / SPEC-04 §7.4）：会话深链编解码。
 *
 * 纯函数：只做 hash 的编码/解码与容错，不读 location、不写 history、不碰 DOM。
 * app.js 是唯一会话协调 owner：openRun/showView 用 replaceState 同步，init 按深链恢复，
 * hashchange 与当前状态比对后执行。深链优先；浏览器后退导航不在本片。
 */
(function (root) {
  "use strict";

  var VIEWS = { s0: 1, setup: 1, run: 1, gate: 1 };

  function encode(runId, view) {
    var parts = [];
    var r = runId == null ? "" : String(runId);
    var v = view == null ? "" : String(view);
    if (r) parts.push("run=" + encodeURIComponent(r));
    if (v && VIEWS[v]) parts.push("view=" + encodeURIComponent(v));
    return parts.length ? "#" + parts.join("&") : null;
  }

  function decode(hash) {
    var out = { runId: null, view: null };
    var s = hash == null ? "" : String(hash);
    if (s.charAt(0) === "#") s = s.slice(1);
    if (!s) return out;
    s.split("&").forEach(function (pair) {
      var eq = pair.indexOf("=");
      if (eq <= 0) return;
      var key = pair.slice(0, eq);
      var raw = pair.slice(eq + 1);
      var value;
      try {
        value = decodeURIComponent(raw.replace(/\+/g, " "));
      } catch (e) {
        return; /* 非法百分号序列：丢弃该段，不抛错 */
      }
      if (key === "run" && value) out.runId = value;
      if (key === "view" && VIEWS[value]) out.view = value;
    });
    return out;
  }

  var api = { encode: encode, decode: decode };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.RunSessionUrl = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
