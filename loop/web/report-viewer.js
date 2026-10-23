/* 报告全文只读浮窗（SPEC-REV-02 P-28 / 裁决 #8：G2 材料一次点击）。
 *
 * 边界（与 SPEC-04 §6.8 一致）：
 *   · 唯一数据来源 GET /api/runs/{run_id}/report；服务端白名单仅本 run 的 n12_report.md；
 *   · 只读：不落盘、不缓存、不写任何状态，也不发 POST；
 *   · 独立 `<dialog>`（#ndReportOverlay）：节点面板没打开时也能弹；Esc 只关本浮窗、
 *     焦点回到触发按钮；窄屏全屏（样式见 app.css `.nd-report-dialog`）。
 *   · N12 面板入口与 G2 材料入口共用本模块，界面不出现第二套取正文逻辑。
 */
"use strict";
window.ReportViewer = (function () {
  var s = { open: false, runId: null, seq: 0, trigger: null, bound: false };

  function $(id) { return document.getElementById(id); }

  function isMissing(v) { return v === null || v === undefined; }

  function setText(id, text) {
    var node = $(id);
    if (node) node.textContent = text === undefined || text === null ? "" : String(text);
  }

  function errText(e) {
    if (!e) return "未知错误";
    var status = e.status ? "HTTP " + e.status + "：" : "";
    return status + (e.message ? String(e.message) : String(e));
  }

  function ensureBound() {
    if (s.bound) return;
    var dialog = $("ndReportOverlay");
    if (!dialog) return;
    s.bound = true;
    /* Esc：只关这一层（事件停在浮窗 dialog 上，不再冒泡给节点面板）。 */
    dialog.addEventListener("cancel", function (event) {
      event.preventDefault();
      close();
    });
    dialog.addEventListener("close", function () {
      s.open = false;
      s.runId = null;
      s.seq++;
    });
    /* 点遮罩空白处关闭：只认 dialog 自身命中，点内容不关。 */
    dialog.addEventListener("click", function (event) {
      if (event.target === dialog) close();
    });
    var closeBtn = $("ndReportClose");
    if (closeBtn) closeBtn.addEventListener("click", function () { close(); });
  }

  function restoreFocus() {
    var trigger = s.trigger;
    s.trigger = null;
    if (trigger && trigger.isConnected) {
      try { trigger.focus(); } catch (e) { /* 保留当前焦点 */ }
    }
  }

  function close() {
    s.seq++;
    s.open = false;
    s.runId = null;
    var dialog = $("ndReportOverlay");
    if (dialog && dialog.open) {
      try { dialog.close(); } catch (e) { dialog.removeAttribute("open"); }
    }
    restoreFocus();
  }

  function renderBody(body) {
    var file = body && body.file ? String(body.file) : "n12_report.md";
    setText("ndReportTitle", "报告全文 · " + file);
    var meta = [];
    if (body && !isMissing(body.bytes)) meta.push(String(body.bytes) + " B");
    if (body && body.truncated === true) meta.push("已截断（服务端上限）");
    setText("ndReportMeta", meta.length ? meta.join(" · ") : "—");
    setText("ndReportBody", body && !isMissing(body.content)
      ? String(body.content)
      : "报告内容未下发（服务端返回体没有 content）。");
    setText("ndReportNote", "只读；白名单仅本 run 的 n12_report.md；不落盘、不缓存。");
  }

  /* `runId`：当前 run；`api`：页面统一的 GET 包装（app.js 的 api）；`trigger`：触发按钮。 */
  async function open(runId, api, trigger) {
    ensureBound();
    var dialog = $("ndReportOverlay");
    if (!dialog) return;
    if (isMissing(runId) || runId === "") {
      trigger = trigger || null;
      s.trigger = trigger;
      s.seq++;
      setText("ndReportTitle", "报告全文");
      setText("ndReportMeta", "—");
      setText("ndReportBody", "尚未选择运行：无法确定报告属于哪个 run。");
      setText("ndReportNote", "本浮窗只按当前 run 取 n12_report.md，不跨 run、不猜路径。");
      if (!dialog.open) {
        try { dialog.showModal(); } catch (e) { dialog.setAttribute("open", "open"); }
      }
      focusClose();
      return;
    }
    s.open = true;
    s.runId = String(runId);
    s.trigger = trigger || document.activeElement || null;
    var seq = ++s.seq;
    setText("ndReportTitle", "报告全文");
    setText("ndReportMeta", "读取中…");
    setText("ndReportBody", "读取中…");
    setText("ndReportNote", "");
    if (!dialog.open) {
      try { dialog.showModal(); } catch (e) { dialog.setAttribute("open", "open"); }
    }
    focusClose();
    if (typeof api !== "function") {
      if (seq !== s.seq) return;
      setText("ndReportBody", "读取报告失败：页面没有提供请求函数（api）。");
      setText("ndReportNote", "这是界面装配问题，不是服务端 404。");
      return;
    }
    try {
      var body = await api("/api/runs/" + encodeURIComponent(s.runId) + "/report");
      if (seq !== s.seq || !s.open) return;
      renderBody(body);
    } catch (e) {
      if (seq !== s.seq || !s.open) return;
      setText("ndReportBody", "读取报告失败：" + errText(e));
      setText("ndReportNote", "报告文件缺失时服务端返回 404；本面板不猜路径、不回退到别的文件。");
    }
  }

  function focusClose() {
    var closeBtn = $("ndReportClose");
    if (closeBtn) {
      try { closeBtn.focus(); } catch (e) { /* 焦点失败不阻断 */ }
    }
  }

  return { open: open, close: close };
})();
