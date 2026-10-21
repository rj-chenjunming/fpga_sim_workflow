/* 运行详情请求的展示状态判据（F13）。
 *
 * 唯一实现：app.js 只消费本模块，不再各写一套「加载中 / 读取失败 / 数据过期」判定。
 * 这里只做**展示状态**推导，不新增业务状态，不读取服务端之外的事实。
 *
 * 五种可观察情况（Web UI §7.2）：
 *   loading      无成功数据、无错误、有在途请求
 *   idle         无成功数据、无错误、无在途请求（页面尚未发起读取）
 *   first_error  无成功数据、有错误（首次失败：不得声称有上次成功数据）
 *   loaded       有成功数据、无错误
 *   stale_error  有成功数据、有错误（刷新失败：保留数据并标注已过期）
 *
 * 同时在 node 下可被 require：本机没有 playwright，判据用纯函数做受控断言。
 */
(function (root) {
  "use strict";

  function pad(n, width) {
    var s = String(n);
    while (s.length < width) s = "0" + s;
    return s;
  }

  function fmtClock(ts) {
    if (ts === null || ts === undefined) return "";
    var d = new Date(ts);
    if (isNaN(d.getTime())) return "";
    return pad(d.getHours(), 2) + ":" + pad(d.getMinutes(), 2) + ":" + pad(d.getSeconds(), 2);
  }

  /* 选择切换时的新状态：当前选择不继承上一运行的成功数据或成功时间。 */
  function empty() {
    return { data: null, error: null, lastSuccessAt: null, requesting: false };
  }

  /* 只有当前代次（runId + selectionEpoch + detailRequest）的回包可以写入状态。 */
  function isCurrent(pending, latest) {
    if (!pending || !latest) return false;
    return pending.runId === latest.runId &&
      pending.epoch === latest.epoch &&
      pending.request === latest.request;
  }

  function derive(input) {
    input = input || {};
    var hasData = !!input.hasData;
    var error = input.error ? String(input.error) : "";
    var requesting = !!input.requesting;
    var lastSuccessAt = input.lastSuccessAt === undefined ? null : input.lastSuccessAt;
    var kind;
    if (hasData && error) kind = "stale_error";
    else if (hasData) kind = "loaded";
    else if (error) kind = "first_error";
    else if (requesting) kind = "loading";
    else kind = "idle";

    var headStatusText = "";
    if (kind === "loading" || kind === "idle") headStatusText = "加载中…";
    else if (kind === "first_error") headStatusText = "读取失败";

    var alertText = "";
    var lastSuccessText = "";
    if (kind === "first_error") {
      alertText = "读取运行视图失败：" + error + "（尚无成功读取的数据）";
    } else if (kind === "stale_error") {
      lastSuccessText = fmtClock(lastSuccessAt);
      alertText = "读取运行视图失败：" + error +
        (lastSuccessText ? "（数据已过期；上次成功 " + lastSuccessText + "）" : "（数据已过期；上次成功时间未知）");
    }

    return {
      kind: kind,
      headStatusText: headStatusText,
      alertText: alertText,
      lastSuccessText: lastSuccessText,
      showRetry: !!error,
      stale: kind === "stale_error"
    };
  }

  var api = { empty: empty, isCurrent: isCurrent, derive: derive, fmtClock: fmtClock };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.RunViewState = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
