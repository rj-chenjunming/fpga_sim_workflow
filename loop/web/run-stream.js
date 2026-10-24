/* U2-a（SPEC-REV-07 / SPEC-04 §7.3）：SSE 客户端传输状态机。
 *
 * 定位：只做连接/实时/回退/停止四态与重试节拍；不读全局、不写 DOM、不发请求
 * （EventSource 与计时器全部注入）。回退态**不**自带轮询——运行详情拉取回到
 * app.js 既有轮询路径（§7.3：回退后行为与现状逐字一致，不双通道并发写）。
 * stop 为终态：需要重建连接时由调用方新建控制器（app.js 每次选择运行重建）。
 * 状态机口径与 tests/test_run_stream_client.py 同源。
 */
"use strict";

(function (root) {
  var RETRY_MS_DEFAULT = 15000;

  function createRunStream(opts) {
    var url = String(opts.url);
    var ESCtor = opts.EventSource;
    var onEvent = typeof opts.onEvent === "function" ? opts.onEvent : function () {};
    var onStateChange = typeof opts.onStateChange === "function" ? opts.onStateChange : function () {};
    var retryMs = typeof opts.retryMs === "number" && opts.retryMs > 0 ? opts.retryMs : RETRY_MS_DEFAULT;
    var setTimeoutFn = opts.setTimeout || function (fn, ms) { return root.setTimeout(fn, ms); };
    var clearTimeoutFn = opts.clearTimeout || function (id) { root.clearTimeout(id); };

    var es = null;
    var retryTimer = null;
    var started = false;
    var terminated = false;
    var state = "stopped";

    function setState(next) {
      if (state === next) return;
      state = next;
      onStateChange(next);
    }

    function clearRetry() {
      if (retryTimer !== null) {
        clearTimeoutFn(retryTimer);
        retryTimer = null;
      }
    }

    function closeES() {
      if (es) {
        try { es.close(); } catch (e) { /* 已关 */ }
        es = null;
      }
    }

    function dispatch(name, raw) {
      var data = null;
      try { data = JSON.parse(raw); } catch (e) { data = { raw: String(raw) }; }
      onEvent(name, data);
    }

    function connect() {
      es = new ESCtor(url);
      es.addEventListener("open", function () { clearRetry(); setState("open"); });
      es.addEventListener("run_view", function (e) { dispatch("run_view", e.data); });
      es.addEventListener("gone", function (e) {
        dispatch("gone", e.data);
        degrade();
      });
      es.addEventListener("error", function () { degrade(); });
      setState("connecting");
    }

    function degrade() {
      closeES();
      setState("fallback");
      clearRetry();
      retryTimer = setTimeoutFn(connect, retryMs);
    }

    return {
      start: function () {
        if (started || terminated) return;
        started = true;
        connect();
      },
      stop: function () {
        clearRetry();
        closeES();
        terminated = true;
        setState("stopped");
      },
      state: function () { return state; }
    };
  }

  var RunStream = { createRunStream: createRunStream };

  root.RunStream = RunStream;
  if (typeof module !== "undefined" && module.exports) module.exports = RunStream;
})(typeof window !== "undefined" ? window : globalThis);
