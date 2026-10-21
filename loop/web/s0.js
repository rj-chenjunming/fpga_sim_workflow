/* S0 准备记录投影；表单不参与轮询重建，所有结论由 Host 返回。 */
"use strict";
window.S0Workbench = (function () {
  var api, busy = false, selected = null, selection = 0;
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  function error(message) {
    $("s0Error").replaceChildren();
    if (message) $("s0Error").appendChild(el("div", "alert bad", message));
  }
  function setBusy(value) {
    busy = value;
    $("s0Prepare").disabled = value;
    $("s0Refresh").disabled = value;
    $("s0Form").setAttribute("aria-busy", String(value));
    $("s0Prepare").textContent = value ? "正在派生与校验…" : "派生并校验 →";
    $("s0SubmitHint").textContent = value ? "完整工程复制可能需要较长时间，请保留本页" : "准备完成后仍需 S0-b 与 GATE-1";
    ["s0Baseline", "s0Version", "s0Rtl", "s0Work"].forEach(function (id) { $(id).disabled = value; });
    $("s0History").querySelectorAll("button").forEach(function (b) { b.disabled = value; });
  }
  function render(record) {
    selected = record.id;
    var readiness = $("s0Readiness");
    readiness.replaceChildren(el("span", "dot " + (record.ready_for_execution ? "" : "warn")),
      document.createTextNode(record.ready_for_execution ? " 服务端已准出" : " 尚未准出"));
    $("s0PhaseAStatus").textContent = record.status === "prepared" ? "已完成" : "失败";
    $("s0PhaseAStatus").className = "chip " + (record.status === "prepared" ? "ok" : "bad");
    var result = $("s0Result");
    result.replaceChildren(el("div", "receipt-label", record.status === "prepared" ? "S0-a 已完成 / S0-b 尚未完成" : "准备或重新核验失败"),
      el("div", "mono receipt-id", record.id || "—"), el("div", "mono receipt-path", record.work_env || "—"));
    if (record.error) result.appendChild(el("div", "alert bad", record.error));
    var drift = record.verification && record.verification.drift;
    Object.keys(drift || {}).forEach(function (key) {
      result.appendChild(el("div", "alert bad", key + " 内容变化：" + drift[key].join("、")));
    });
    ((record.verification && record.verification.errors) || []).forEach(function (message) {
      result.appendChild(el("div", "alert bad", message));
    });
    if (Array.isArray(record.checks) && record.checks.length) {
      $("s0Checks").replaceChildren();
      record.checks.forEach(function (check, index) {
        var item = el("li", check.status === "passed" ? "check-passed" : "");
        item.appendChild(el("span", null, check.status === "passed" ? "✓" : String(index + 1).padStart(2, "0")));
        item.appendChild(el("div", null, check.label || check.key));
        item.appendChild(el("b", null, {passed: "已验证", failed: "失败", waiting: "未完成"}[check.status] || check.status));
        $("s0Checks").appendChild(item);
      });
    }
    // 历史检查通过 + 当前漂移需要并列可见，不把历史证据回填成另一份状态。
    if (record.status === "failed") result.appendChild(el("p", "muted tiny", "下方检查项为派生时记录；当前核验失败以此处漂移和错误为准。"));
    $("s0Blockers").replaceChildren();
    (record.blockers || []).forEach(function (blocker) {
      $("s0Blockers").appendChild(el("p", null, blocker.message || blocker));
    });
    var report = $("s0Report");
    report.classList.toggle("hidden", !/^S0-[A-Za-z0-9_-]+$/.test(record.id || ""));
    if (/^S0-[A-Za-z0-9_-]+$/.test(record.id || "")) report.href = "/api/s0/" + encodeURIComponent(record.id) + "/report";
  }
  async function loadIndex() {
    var data = await api("/api/s0");
    if (!$("s0Baseline").value && data.baseline) $("s0Baseline").value = data.baseline;
    if (Array.isArray(data.allowed_roots)) $("s0AllowedRoots").textContent = data.allowed_roots.join("\n");
    var history = $("s0History");
    history.replaceChildren();
    if (!(data.records || []).length) history.appendChild(el("div", "muted tiny", "暂无准备记录。派生操作只会新建副本，不覆盖已有目录。"));
    (data.records || []).forEach(function (record) {
      var button = el("button", "s0-history-item");
      button.type = "button";
      button.disabled = busy;
      button.appendChild(el("b", "mono", record.baseline_version || record.id));
      button.appendChild(el("span", "mono tiny muted", record.work_env));
      button.appendChild(el("small", "muted", "派生时记录 · " + record.status + " · 点击重新核验"));
      button.addEventListener("click", function () { loadRecord(record.id); });
      history.appendChild(button);
    });
  }
  async function loadRecord(id) {
    if (busy) return;
    var token = ++selection;
    error("");
    try {
      var record = await api("/api/s0/" + encodeURIComponent(id));
      if (token === selection) render(record);
    } catch (e) { if (token === selection) error(e.message); }
  }
  async function submit(event) {
    event.preventDefault();
    if (busy) return;
    if (!$("s0Form").reportValidity()) return;
    var payload = {baseline: $("s0Baseline").value.trim(), baseline_version: $("s0Version").value.trim(),
      rtl_source: $("s0Rtl").value.trim(), work_env: $("s0Work").value.trim()};
    var token = ++selection;
    error("");
    setBusy(true);
    try {
      // 工程复制不套用普通 GET 的短超时；断连后用户可从准备记录重新查询。
      var record = await api("/api/s0", {method: "POST", body: payload}, 0);
      if (token === selection) render(record);
    } catch (e) {
      if (token === selection) {
        error(e.message + (e.status === 0 ? "；服务端操作可能仍在进行，请刷新准备记录确认，勿覆盖目标。" : ""));
        var failed = e.body && e.body.detail && e.body.detail.record;
        if (failed) render(failed);
      }
    } finally {
      setBusy(false);
      try { await loadIndex(); } catch (e) { error("读取准备记录失败：" + e.message); }
    }
  }
  return {init: function (request) {
    api = request;
    $("s0Form").addEventListener("submit", submit);
    $("s0Refresh").addEventListener("click", async function () {
      if (busy) return;
      try { await loadIndex(); if (selected) await loadRecord(selected); }
      catch (e) { error("读取准备记录失败：" + e.message); }
    });
    loadIndex().catch(function (e) { error("环境准备服务暂不可用：" + e.message); });
  }};
})();
