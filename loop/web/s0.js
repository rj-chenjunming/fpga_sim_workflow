/* S0 准备记录投影；表单不参与轮询重建，所有结论由 Host 返回。
 *
 * T3（WEB_UI_SPEC §15 / 计划 2026-10-30 §4 T3）：入口改为「只填一个新版 RTL 文件夹」。
 * 本文件的硬边界：
 * - 不新增业务判据：阶段/端口/冒烟/准出/切换的**结论**一律读服务端 record 字段
 *   （checks / ports / smoke / ready_for_execution / env_switch / copy_plan / folder_warning），
 *   这里只做「显示」的分组与措辞；唯一由界面决定的是「是否已把同一次切换提交出去」。
 * - 轮询不清表单：切换期只读 /api/health，不重建 #s0Form；不重复提交靠 busy/token + 记录级去重。
 * - 切页不触发写操作：切到运行配置只通过 `loop:navigate` 事件请求视图切换。
 */
"use strict";
window.S0Workbench = (function () {
  var api, busy = false, rehearsalBusy = false, selected = null, selection = 0;
  /* 当前记录的只读投影：阶段/端口/切换渲染都只读它，不派生第二份状态。 */
  var current = null;
  var advanceBusy = false, activateBusy = false, switchBackBusy = false;
  /* record_id → 已自动提交过 activate（失败也不自动重提，改为人工点「请求切换」）。 */
  var activateTried = Object.create(null);
  var switchPoll = null, switchPollToken = 0;
  var switchState = { message: "", kind: "" };
  /* 本次页面会话里已确认切换成功的 record_id：成功后不再显示「请求切换」重试。 */
  var switchDone = null;
  var envState = null, envError = null;
  var copies = [], copiesError = null, copiesMessage = { text: "", kind: "" };
  var PREFILL_KEY = "loop.s0Prefill";
  var SWITCH_POLL_MS = 800, SWITCH_POLL_MAX = 300;
  /* 端口 waiting 的界面措辞：本入口没有提议入口，处置必须在既有 S0-b 端点完成。 */
  var PORTS_HINT = "提议来源未接入本入口，需既有提议/确认端点处置";

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  /* 图标（WEB_UI_SPEC §14「资产」）：唯一来源是 index.html 的内联 sprite，本文件只克隆
   * #iconTpl 并改 <use href>；不写 namespace 字符串（否则红 test_web_smoke.py 的外链断言）。 */
  var ICON_TPL = null;
  function iconNode(name) {
    if (ICON_TPL === null) {
      var tpl = $("iconTpl");
      ICON_TPL = tpl && tpl.content && tpl.content.firstElementChild
        ? tpl.content.firstElementChild.cloneNode(true) : false;
    }
    if (!ICON_TPL) return null;
    var svg = ICON_TPL.cloneNode(true);
    var use = svg.querySelector("use");
    if (use) use.setAttribute("href", "#icon-" + name);
    return svg;
  }
  /* 文案 + 尾部图标（替代 `textContent = "… →"`：textContent 会把图标当文本清掉）。 */
  function labelWithIcon(button, text, icon) {
    if (!button) return button;
    button.replaceChildren(document.createTextNode(text));
    var node = iconNode(icon);
    if (node) button.appendChild(node);
    return button;
  }
  /* 检查项序号：通过时换成「已完成」图标，否则仍是两位序号（右列状态文字仍由 <b> 承担）。 */
  function checkMark(index, passed) {
    var mark = el("span");
    var ok = passed ? iconNode("check") : null;
    if (ok) { mark.appendChild(ok); return mark; }
    mark.appendChild(document.createTextNode(String(index + 1).padStart(2, "0")));
    return mark;
  }
  function error(message) {
    $("s0Error").replaceChildren();
    if (message) $("s0Error").appendChild(el("div", "alert bad", message));
  }
  var STATUS_TEXT = {
    passed: "已验证", failed: "失败", waiting: "未完成", pending: "进行中",
    active: "已切换", rollback: "已回退", prepared: "已派生",
    awaiting_ports: "待端口确认", ready: "已就绪"
  };
  function statusText(status) {
    if (status === undefined || status === null || status === "") return "—";
    return STATUS_TEXT[status] || String(status);
  }
  function detailError(e) {
    var detail = e && e.body && e.body.detail;
    if (detail && typeof detail === "object") return detail.error || detail.message || "";
    if (typeof detail === "string") return detail;
    return "";
  }
  function joinList(values) {
    return Array.isArray(values) && values.length ? values.join("、") : "—";
  }
  function items(value) { return Array.isArray(value) ? value : []; }
  function formatBytes(value) {
    var n = Number(value);
    if (value === undefined || value === null || value === "" || !isFinite(n) || n < 0) return "—";
    if (n < 1024) return n + " B";
    var units = ["KB", "MB", "GB", "TB"], v = n / 1024, i = 0;
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return v.toFixed(1) + " " + units[i];
  }
  /* 单输入二选一（S0 §9.9 / WEB_UI §15）：只有当前模式的输入 required + 可见 + 可用，
   * 另一个 hidden + disabled + required=false —— 否则 reportValidity() 会被隐藏输入卡住。
   * 判定只看单选值（默认 rtl），不猜路径内容。 */
  function currentMode() {
    var checked = document.querySelector('input[name="s0Mode"]:checked');
    return checked && checked.value === "env" ? "env" : "rtl";
  }
  /* 中性兜底文案：必须与 index.html 的 #s0SubmitHint 首屏文本**逐字相同**
   * （界面文案门 `tests/test_ui_gate_copy.py::test_hint_copy_is_identical_in_html_and_js`
   *  用 `:\s*"…S0-b 接口复核…"\s*;` 抓的就是下面这一行）。模式提示只在其前面加前缀。 */
  function neutralHint(isBusy) {
    return isBusy ? "完整工程复制可能需要较长时间，请保留本页"
                  : "准出与切换由服务端判定；准备完成后仍需 S0-b 接口复核";
  }
  function modeHint(mode) {
    return (mode === "env"
      ? "只发 baseline（环境项目目录，RTL 不替换）；"
      : "只发 rtl_source（环境资产取原始环境根）；") + neutralHint(false);
  }
  function applyMode() {
    var mode = currentMode();
    var rtlPanel = $("s0ModeRtlPanel"), envPanel = $("s0ModeEnvPanel");
    if (rtlPanel) rtlPanel.classList.toggle("hidden", mode !== "rtl");
    if (envPanel) envPanel.classList.toggle("hidden", mode !== "env");
    var rtl = $("s0Rtl"), env = $("s0EnvDir");
    if (rtl) { rtl.required = mode === "rtl"; rtl.disabled = busy || mode !== "rtl"; }
    if (env) { env.required = mode === "env"; env.disabled = busy || mode !== "env"; }
    ["s0ModeRtl", "s0ModeEnv"].forEach(function (id) {
      var radio = $(id);
      if (radio) radio.disabled = busy;
    });
    var hint = $("s0SubmitHint");
    if (hint && !busy) hint.textContent = modeHint(mode);
  }
  function setBusy(value) {
    busy = value;
    $("s0Prepare").disabled = value;
    $("s0Refresh").disabled = value;
    $("s0Rehearsal").disabled = value || rehearsalBusy;
    $("s0SwitchRefresh").disabled = value;
    $("s0CopiesRefresh").disabled = value;
    $("s0Form").setAttribute("aria-busy", String(value));
    if (value) $("s0Prepare").textContent = "正在派生与校验…";
    else labelWithIcon($("s0Prepare"), "派生并校验 ", "next");
    ["s0Version", "s0Work"].forEach(function (id) { $(id).disabled = value; });
    applyMode();
    if (value) $("s0SubmitHint").textContent = neutralHint(true);
    $("s0History").querySelectorAll("button").forEach(function (b) { b.disabled = value; });
  }
  function render(record) {
    selected = record.id;
    current = record;
    var readiness = $("s0Readiness");
    readiness.replaceChildren(el("span", "dot " + (record.ready_for_execution ? "" : "warn")),
      document.createTextNode(record.ready_for_execution ? " 服务端已准出" : " 尚未准出"));
    $("s0PhaseAStatus").textContent = record.status === "prepared" ? "已完成" : "失败";
    $("s0PhaseAStatus").className = "chip " + (record.status === "prepared" ? "ok" : "bad");
    var result = $("s0Result");
    var entryText = record.entry === "env_folder" ? "环境项目入口"
      : (record.entry === "rtl_folder" ? "新版 RTL 入口" : null);
    var label = record.status !== "prepared" ? "准备或重新核验失败"
      : (entryText ? "一键入口（" + entryText + "） · 派生已完成（阶段回执见下）"
        : "S0-a 已完成 / S0-b 尚未完成");
    result.replaceChildren(el("div", "receipt-label", label),
      el("div", "mono receipt-id", record.id || "—"), el("div", "mono receipt-path", record.work_env || "—"));
    if (record.rtl_source) result.appendChild(el("div", "mono tiny muted", "RTL 来源：" + record.rtl_source));
    if (record.rtl_prefix) result.appendChild(el("div", "mono tiny muted", "替换前缀：" + record.rtl_prefix));
    /* §9.9：环境项目入口不替换 RTL —— 明示，而不是把整步藏掉。 */
    if (record.entry === "env_folder") result.appendChild(el("div", "mono tiny muted", "RTL：未替换（环境项目入口）"));
    if (record.smoke_case) result.appendChild(el("div", "mono tiny muted", "冒烟用例：" + record.smoke_case));
    if (record.folder_warning) {
      var warning = record.folder_warning;
      result.appendChild(el("div", "alert warn", "RTL 文件夹告警（只告警不拦截）：同名 " +
        (warning.same === undefined ? "—" : warning.same) + " / 新增 " +
        (warning.added === undefined ? "—" : warning.added) + " / 缺失 " +
        (warning.removed === undefined ? "—" : warning.removed) + "（ratio " +
        (warning.ratio === undefined ? "—" : warning.ratio) + "）"));
    }
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
        item.appendChild(checkMark(index, check.status === "passed"));
        var box = el("div", null, check.label || check.key);
        if (check.reason) box.appendChild(el("small", null, check.reason));
        item.appendChild(box);
        item.appendChild(el("b", null, checkStatusText(check, record)));
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
    /* 阶段回执 / 端口 / 切换：全部只读 record 字段。 */
    renderPhaseFlow(record);
    renderPorts(record);
    renderSwitch();
    maybeAutoActivate(record);
  }
  /* ---------------------------------------------------------------- 阶段回执 */
  function checkStatus(record, key) {
    var checks = record.checks || [];
    for (var i = 0; i < checks.length; i++) {
      if (checks[i] && checks[i].key === key) return checks[i].status;
    }
    return null;
  }
  /* skipped 只按服务端 status 渲染：env_folder 的 `rtl` 显示「未替换（环境项目入口）」，
   * 其余 skipped（尤其 rtl_folder 入口）一律按“未通过”显示，不掩盖异常（§9.9-2/9.9-4）。 */
  function checkStatusText(check, record) {
    if (check.status === "skipped") {
      return check.key === "rtl" && record && record.entry === "env_folder"
        ? "未替换（环境项目入口）" : "skipped（不当作通过）";
    }
    return {passed: "已验证", failed: "失败", waiting: "未完成"}[check.status] || check.status;
  }
  /* 只把服务端 check.status 归并成一行展示；不引入阈值、不猜结论。
   * skipped 的唯一中性例外 = env_folder 的 rtl（§9.9-4）；其它非 passed 一律不算通过。 */
  function aggregateStatus(record, keys) {
    var seen = 0, failed = false, allPassed = true;
    var envEntry = record.entry === "env_folder";
    keys.forEach(function (key) {
      var status = checkStatus(record, key);
      if (status === null || status === undefined) return;
      if (status === "skipped" && envEntry && key === "rtl") return;
      seen++;
      if (status === "failed") failed = true;
      if (status !== "passed") allPassed = false;
    });
    return failed ? "failed" : (seen && allPassed ? "passed" : "waiting");
  }
  function copyPlanText(plan) {
    if (!plan) return "";
    var parts = ["复制 " + items(plan.copied).length + " 项"];
    var excluded = items(plan.excluded_roots);
    if (excluded.length) parts.push("排除 " + excluded.length + " 项（" + excluded.join("、") + "）");
    var skipped = items(plan.skipped);
    if (skipped.length) {
      var reasons = {};
      skipped.forEach(function (row) {
        var reason = (row && row.reason) || "未知";
        reasons[reason] = (reasons[reason] || 0) + 1;
      });
      parts.push("跳过 " + skipped.length + " 项（" + Object.keys(reasons).map(function (key) {
        return key + " " + reasons[key];
      }).join("、") + "）");
    }
    return parts.join(" · ");
  }
  function stageRows(record) {
    var ports = record.ports || {};
    var smoke = record.smoke || {};
    var sw = record.env_switch || {};
    var rows = [];
    var deriveDetail = [];
    var rtlCheck = null;
    (record.checks || []).forEach(function (check) { if (check && check.key === "rtl") rtlCheck = check; });
    if (record.entry === "env_folder") {
      /* §9.9-3：RTL 未替换要显式写在派生阶段，不隐藏这一步、也不显示成通过。 */
      deriveDetail.push("RTL 未替换（环境项目入口）" +
        (rtlCheck && rtlCheck.reason ? "：" + rtlCheck.reason : ""));
    } else if (record.rtl_prefix) {
      deriveDetail.push("RTL 前缀 " + record.rtl_prefix);
    }
    var planText = copyPlanText(record.copy_plan);
    if (planText) deriveDetail.push(planText);
    if (record.folder_warning) {
      var warning = record.folder_warning;
      deriveDetail.push("目录告警：同名 " + (warning.same === undefined ? "—" : warning.same) +
        " / 新增 " + (warning.added === undefined ? "—" : warning.added) +
        " / 缺失 " + (warning.removed === undefined ? "—" : warning.removed) + "（只告警不拦截）");
    }
    if (record.status === "failed" && record.error) deriveDetail.push(record.error);
    rows.push({ label: "派生副本", status: record.status === "failed" ? "failed" : aggregateStatus(record, ["copy", "rtl", "non_rtl"]),
      detail: deriveDetail.join("；") });
    rows.push({ label: "端口确认", status: ports.status || "waiting",
      detail: ports.reason || (record.auto && record.auto.phase === "awaiting_ports" ? PORTS_HINT : "") });
    rows.push({ label: "三库冒烟", status: smoke.status || "waiting",
      detail: smoke.reason || (record.smoke_case ? "冒烟用例 " + record.smoke_case + "（尚未执行）" : "") });
    rows.push({ label: "准出", status: record.ready_for_execution ? "passed" : "waiting",
      detail: record.ready_for_execution ? "服务端 ready_for_execution=true" : "尚未准出（判据在服务端 checks/ports/smoke）" });
    rows.push({ label: "切换环境", status: sw.status === "active" ? "passed" : (sw.status === "rollback" ? "failed" : "waiting"),
      detail: sw.reason || (sw.status ? "切换状态 " + sw.status : "尚未切换") });
    rows.push({ label: "到运行配置", status: sw.status === "active" ? "passed" : "waiting",
      detail: sw.status === "active" ? "已切换到派生环境 · 去新建运行" : "切换成功后自动预填运行配置" });
    return rows;
  }
  function renderPhaseFlow(record) {
    var host = $("s0PhaseFlow");
    host.replaceChildren();
    stageRows(record).forEach(function (row, index) {
      var item = el("li", row.status === "passed" ? "check-passed" : (row.status === "failed" ? "check-failed" : ""));
      item.appendChild(checkMark(index, row.status === "passed"));
      var box = el("div");
      box.appendChild(el("b", null, row.label));
      if (row.detail) box.appendChild(el("small", null, row.detail));
      item.appendChild(box);
      item.appendChild(el("b", "flow-status", statusText(row.status)));
      host.appendChild(item);
    });
  }
  /* ---------------------------------------------------------------- 端口差异 */
  var PORT_KIND_TEXT = { module: "模块接口变更", module_added: "新增模块", module_removed: "删除模块" };
  function renderPorts(record) {
    var host = $("s0Ports");
    host.replaceChildren();
    var ports = record.ports;
    if (!ports) {
      host.appendChild(el("div", "receipt-empty", "服务端尚未返回端口核对结论（ports）。"));
      return;
    }
    var head = el("div", "s0-ports-head");
    head.appendChild(el("span", "chip " + (ports.status === "passed" ? "ok" : (ports.status === "failed" ? "bad" : "warn")),
      statusText(ports.status)));
    head.appendChild(el("span", "muted tiny", ports.reason || "服务端未给出原因"));
    host.appendChild(head);
    var table = items(ports.table);
    if (table.length) {
      var wrap = el("div", "s0-table-wrap");
      var tableNode = el("table", "s0-table");
      var headRow = el("tr");
      ["类型", "模块", "新增端口", "移除端口", "变更端口"].forEach(function (text) {
        headRow.appendChild(el("th", null, text));
      });
      var thead = el("thead");
      thead.appendChild(headRow);
      tableNode.appendChild(thead);
      var tbody = el("tbody");
      table.forEach(function (row) {
        var line = el("tr");
        line.appendChild(el("td", null, PORT_KIND_TEXT[row.kind] || String(row.kind || "—")));
        line.appendChild(el("td", "mono", row.module || "—"));
        line.appendChild(el("td", "mono", joinList(row.added)));
        line.appendChild(el("td", "mono", joinList(row.removed)));
        line.appendChild(el("td", "mono", joinList(row.changed)));
        tbody.appendChild(line);
      });
      tableNode.appendChild(tbody);
      wrap.appendChild(tableNode);
      host.appendChild(wrap);
    } else {
      host.appendChild(el("p", "muted tiny", "服务端 table 为空：未发现模块接口差异（不代表已处置，结论以 status 为准）。"));
    }
    if (ports.status === "waiting") {
      host.appendChild(el("div", "alert warn", PORTS_HINT + "；处置后点「继续冒烟」由服务端复核。"));
      var actions = el("div", "s0-form-actions");
      var button = labelWithIcon(el("button", "btn"), "继续冒烟 ", "next");
      button.type = "button";
      button.id = "s0Advance";
      button.disabled = advanceBusy;
      button.addEventListener("click", advance);
      actions.appendChild(el("span", "muted tiny", "服务端校验 ports=passed 才跑冒烟；未处置会拒绝并返回原文。"));
      actions.appendChild(button);
      host.appendChild(actions);
    }
  }
  async function advance() {
    if (!current || !current.id || advanceBusy || busy) return;
    advanceBusy = true;
    var token = ++selection;
    var button = $("s0Advance");
    if (button) { button.disabled = true; button.textContent = "正在继续冒烟…"; }
    try {
      var record = await api("/api/s0/" + encodeURIComponent(current.id) + "/advance", {method: "POST", body: {}}, 0);
      if (token === selection) render(record);
      try { await loadIndex(); } catch (e) { /* 列表刷新失败不吞记录结论 */ }
    } catch (e) {
      if (token === selection) {
        var text = detailError(e) || e.message;
        error(text);
        var host = $("s0Ports");
        host.appendChild(el("div", "alert bad", "继续冒烟被拒绝：" + text));
      }
    } finally {
      advanceBusy = false;
      var again = $("s0Advance");
      if (again) { again.disabled = false; labelWithIcon(again, "继续冒烟 ", "next"); }
    }
  }
  /* ---------------------------------------------------------------- 环境切换 */
  function switchMsg(message, kind) {
    switchState = { message: message || "", kind: kind || "" };
    var node = $("s0SwitchMsg");
    if (node) {
      node.textContent = switchState.message;
      node.className = "s0-switch-msg" + (switchState.kind ? " s0-switch-msg-" + switchState.kind : "");
    }
  }
  function envSwitchOf(record) {
    if (record && record.env_switch) return record.env_switch;
    if (envState && envState.switch) return envState.switch;
    return null;
  }
  function renderSwitch() {
    var host = $("s0Switch");
    if (!host) return;
    host.replaceChildren();
    var state = envState || {};
    [["当前环境根", state.env_root], ["环境 ID", state.env_id], ["原始环境根", state.origin_env_root],
     ["基线来源", state.baseline_source]].forEach(function (pair) {
      var row = el("div", "kv");
      row.appendChild(el("span", null, pair[0]));
      row.appendChild(el("b", "mono", pair[1] === undefined || pair[1] === null || pair[1] === "" ? "—" : String(pair[1])));
      host.appendChild(row);
    });
    if (envError) host.appendChild(el("div", "alert warn", "环境状态不可用（GET /api/env/state）：" + envError));
    var sw = envSwitchOf(current);
    if (sw) {
      var row = el("div", "kv");
      row.appendChild(el("span", null, "切换状态"));
      row.appendChild(el("b", null, statusText(sw.status) + (sw.reason ? "（" + sw.reason + "）" : "")));
      host.appendChild(row);
    }
    var message = el("div", "s0-switch-msg" + (switchState.kind ? " s0-switch-msg-" + switchState.kind : ""),
      switchState.message || "尚未请求切换。");
    message.id = "s0SwitchMsg";
    message.setAttribute("aria-live", "polite");
    host.appendChild(message);
    var actions = el("div", "s0-form-actions");
    actions.appendChild(el("span", "muted tiny", "切回与切换走同一套状态机（POST /api/env/switch-back）；有活跃运行时服务端会拒绝。"));
    var back = el("button", "btn", "切回原环境");
    back.type = "button";
    back.id = "s0SwitchBack";
    back.disabled = switchBackBusy;
    back.addEventListener("click", switchBack);
    actions.appendChild(back);
    host.appendChild(actions);
    if (current && current.ready_for_execution && switchDone !== current.id &&
        !(sw && (sw.status === "active" || sw.status === "pending"))) {
      var retry = el("button", "btn btn-sm", "请求切换到派生环境");
      retry.type = "button";
      retry.id = "s0Activate";
      retry.disabled = activateBusy;
      retry.addEventListener("click", function () { activate(current.id, true); });
      var retryBar = el("div", "s0-switch-retry");
      retryBar.appendChild(el("span", "muted tiny", "已准出但切换未完成：可重试（服务端仍会校验活跃运行与切换状态）。"));
      retryBar.appendChild(retry);
      host.appendChild(retryBar);
    }
  }
  async function loadEnvState() {
    try {
      var state = await api("/api/env/state", {}, 8000);
      envState = state && typeof state === "object" ? state : null;
      envError = state && state.ok === false ? "服务端未提供环境状态（GET /api/env/state 返回 ok=false，端点可能尚未接入）" : null;
    } catch (e) {
      envState = null;
      envError = e.status === 404 ? "服务端未提供 /api/env/state（404）" : e.message;
    }
    renderSwitch();
  }
  function maybeAutoActivate(record) {
    if (!record || !record.id || !record.ready_for_execution) return;
    var sw = record.env_switch || {};
    if (sw.status === "active" || sw.status === "pending") return;  /* 已切换/切换中：不重复提交 */
    if (activateTried[record.id]) return;
    activateTried[record.id] = true;                                 /* 同一条记录只自动提交一次 */
    activate(record.id, false);
  }
  function activate(recordId, manual) {
    if (!recordId || activateBusy) return;
    activateBusy = true;
    switchMsg("准出已满足，正在请求切换环境（POST /api/s0/" + recordId + "/activate）…", "warn");
    var button = $("s0Activate");
    if (button) { button.disabled = true; button.textContent = "正在请求切换…"; }
    api("/api/s0/" + encodeURIComponent(recordId) + "/activate", {method: "POST", body: {}}, 0).then(function (body) {
      var sw = (body && body.switch) || {};
      var target = sw.target_env_root || sw.env_root || (current && current.work_env) || "";
      switchMsg("切换进行中：以派生环境根重启服务，健康检查通过后自动进入运行配置。" +
        (sw.reason ? "（" + sw.reason + "）" : ""), "warn");
      startSwitchPoll(target, function (health) { switchSucceeded(recordId, target, health); });
    }).catch(function (e) {
      var text = detailError(e) || e.message;
      switchMsg((manual ? "切换请求失败：" : "切换请求被拒绝：") + text, "bad");
      activateTried[recordId] = false;   /* 人工可重试；自动不会在无渲染触发时重发 */
      var retry = $("s0Activate");
      if (retry) { retry.disabled = false; retry.textContent = "请求切换到派生环境"; }
    }).finally(function () { activateBusy = false; });
  }
  function startSwitchPoll(target, onSuccess) {
    var token = ++switchPollToken, attempts = 0;
    if (switchPoll) { clearTimeout(switchPoll); switchPoll = null; }
    function stop() { switchPoll = null; }
    function next() {
      if (token !== switchPollToken) return;
      if (attempts >= SWITCH_POLL_MAX) {
        stop();
        switchMsg("健康检查仍未确认切换结论；请刷新环境状态（GET /api/env/state）核对。", "warn");
        renderSwitch();
        return;
      }
      switchPoll = setTimeout(step, SWITCH_POLL_MS);
    }
    function rollback(sw) {
      stop();
      switchMsg("切换已回退（rollback）：" + ((sw && sw.reason) || "服务端未给出原因"), "bad");
      loadEnvState();
    }
    function step() {
      if (token !== switchPollToken) return;
      attempts++;
      if (target) {
        api("/api/health", {}, 5000).then(function (health) {
          if (token !== switchPollToken) return;
          var summary = health && health.switch;
          if (summary && summary.status === "rollback") { rollback(summary); return; }
          if (health && String(health.env_root || "") === String(target)) {
            stop();
            onSuccess({ env_root: target, health: health });
            return;
          }
          next();
        }).catch(next);   /* 切换期服务可能短暂不可达：允许失败，继续轮询 */
      } else {
        /* 目标根未知（切回未回传 target）：只认服务端 /api/env/state 的结论，不自己比根。 */
        api("/api/env/state", {}, 8000).then(function (state) {
          if (token !== switchPollToken) return;
          envState = state && typeof state === "object" ? state : envState;
          var summary = (envState && envState.switch) || {};
          if (summary.status === "rollback") { rollback(summary); return; }
          if (summary.status === "active") {
            stop();
            onSuccess({ env_root: (envState && envState.env_root) || "", state: envState });
            return;
          }
          next();
        }).catch(next);
      }
    }
    switchPoll = setTimeout(step, SWITCH_POLL_MS);  /* 先等一个周期，给旧进程退出留时间 */
  }
  function switchSucceeded(recordId, target, result) {
    var record = current || {};
    var baseline = record.baseline_version || record.baseline || "";
    /* 裁决 1（2026-10-30）：prefill 记录切换成功时的实际环境根，运行配置据此判定
     * “本次运行位于经 S0 派生的环境”，不再拿 baseline_version 去撞基线列表。 */
    var envRoot = String((result && result.env_root) || target || "");
    var prefill = {s0_record_id: recordId, baseline: String(baseline), env_root: envRoot};
    try { sessionStorage.setItem(PREFILL_KEY, JSON.stringify(prefill)); }
    catch (e) { /* 隐私模式/禁用存储：预填不可用不影响切换结论本身 */ }
    switchDone = recordId;
    switchMsg("已切换到派生环境 · 去新建运行（环境根 " + (target || "—") + "）", "ok");
    renderSwitch();
    var host = $("s0Switch");
    if (host) {
      var actions = el("div", "s0-form-actions");
      actions.appendChild(el("span", "muted tiny", "已把 s0_record_id 与推荐基线写入本标签页预填（sessionStorage）。"));
      var go = labelWithIcon(el("button", "btn btn-primary"), "去新建运行 ", "next");
      go.type = "button";
      go.id = "s0GoSetup";
      go.addEventListener("click", goSetup);
      actions.appendChild(go);
      host.appendChild(actions);
    }
    loadEnvState();
    goSetup();
  }
  function clearPrefill() {
    try {
      if (window.sessionStorage) sessionStorage.removeItem(PREFILL_KEY);
    } catch (e) { /* 隐私模式：清不掉也不影响切回结论 */ }
  }
  function goSetup() {
    try {
      window.dispatchEvent(new CustomEvent("loop:navigate", {detail: {view: "setup"}}));
    } catch (e) { /* 老浏览器：留在本页，页内按钮仍可用 */ }
  }
  function switchBack() {
    if (switchBackBusy) return;
    switchBackBusy = true;
    switchMsg("正在请求切回原环境（POST /api/env/switch-back）…", "warn");
    var target = (envState && envState.origin_env_root) || (current && current.origin_env_root) || "";
    api("/api/env/switch-back", {method: "POST", body: {}}, 0).then(function (body) {
      var sw = (body && body.switch) || {};
      var next = sw.target_env_root || sw.env_root || target;
      switchMsg("切回进行中：以原始环境根重启服务；健康检查通过后本页显示当前根。" +
        (sw.reason ? "（" + sw.reason + "）" : ""), "warn");
      startSwitchPoll(next, function (result) {
        switchMsg("已切回原始环境（环境根 " + ((result && result.env_root) || next || "—") + "）", "ok");
        /* 已不在派生环境：清掉预填，避免回原环境后的运行仍挂旧 s0_record_id。 */
        clearPrefill();
        loadEnvState();
      });
    }).catch(function (e) {
      /* 失败展示服务端原文（含活跃运行拒绝的 rollback 理由），不吞。 */
      switchMsg("切回失败：" + (detailError(e) || e.message), "bad");
    }).finally(function () { switchBackBusy = false; });
  }
  /* ---------------------------------------------------------------- 副本清单 */
  function renderCopies() {
    var host = $("s0Copies");
    if (!host) return;
    host.replaceChildren();
    if (copiesMessage.text) {
      host.appendChild(el("div", "alert " + (copiesMessage.kind === "ok" ? "ok" : (copiesMessage.kind === "bad" ? "bad" : "warn")),
        copiesMessage.text));
    }
    if (copiesError) {
      host.appendChild(el("div", "alert warn", "副本清单不可用：" + copiesError));
      return;
    }
    if (!copies.length) {
      host.appendChild(el("div", "muted tiny", "服务端未返回派生副本。每次派生都新建并保留副本，需手动清理。"));
      return;
    }
    copies.forEach(function (copy) {
      var row = el("div", "s0-copy");
      var head = el("div", "s0-copy-head");
      head.appendChild(el("b", "mono", copy.id || "—"));
      head.appendChild(el("span", "chip " + (copy.exists ? "ok" : "bad"), copy.exists ? "存在" : "缺失"));
      head.appendChild(el("span", "chip " + (copy.ready_for_execution ? "ok" : "warn"),
        copy.ready_for_execution ? "已准出" : "未准出"));
      row.appendChild(head);
      row.appendChild(el("div", "mono tiny", copy.work_env || "—"));
      var meta = el("div", "s0-copy-meta");
      meta.appendChild(el("span", "muted tiny", "大小 " + formatBytes(copy.bytes)));
      if (copy.rtl_prefix) meta.appendChild(el("span", "muted tiny", "RTL 前缀 " + copy.rtl_prefix));
      if (copy.status) meta.appendChild(el("span", "muted tiny", "status = " + copy.status));
      row.appendChild(meta);
      var remove = el("button", "btn btn-ghost btn-sm", "删除副本");
      remove.type = "button";
      remove.addEventListener("click", function () { deleteCopy(copy, remove); });
      row.appendChild(remove);
      host.appendChild(row);
    });
  }
  async function loadCopies() {
    try {
      var body = await api("/api/s0/copies", {}, 15000);
      copies = items(body.copies);
      copiesError = body.ok === false ? "服务端未提供副本清单（GET /api/s0/copies 返回 ok=false，端点可能尚未接入）" : null;
    } catch (e) {
      copies = [];
      copiesError = e.status === 404 ? "服务端未提供 /api/s0/copies（404）" : e.message;
    }
    renderCopies();
  }
  async function deleteCopy(copy, button) {
    if (!copy || !copy.id || (button && button.disabled)) return;
    var message = "删除派生副本 " + copy.id + "？\n路径：" + (copy.work_env || "—") +
      "\n删除的是副本目录（即派生环境的数据根）及其运行产物，不可恢复；" +
      "准备记录与报告保留，原始环境不受影响。";
    /* 二次确认：取消 ⇒ 不发任何写请求。 */
    if (typeof window.confirm !== "function" || !window.confirm(message)) return;
    if (button) { button.disabled = true; button.textContent = "删除中…"; }
    copiesMessage = { text: "", kind: "" };
    try {
      var body = await api("/api/s0/" + encodeURIComponent(copy.id) + "/copy?confirm=true", {method: "DELETE"}, 0);
      copiesMessage = { text: "已删除副本：" + (body.work_env || copy.work_env || copy.id) +
        "（服务端 deleted=" + String(body.deleted) + "）", kind: "ok" };
    } catch (e) {
      copiesMessage = { text: "删除失败：" + (detailError(e) || e.message), kind: "bad" };
      if (button) { button.disabled = false; button.textContent = "删除副本"; }
    }
    await loadCopies();
  }
  /* ---------------------------------------------------------------- S0-rehearsal */
  // 演练只证明 copy→replace→核验链路；结果独立成块，准备记录轮询/刷新不会清掉它。
  var REHEARSAL_SCOPE = "演练：只证明 copy→replace→核验链路，不是环境就绪、不是 S0-b。";
  function checkRows(record) {
    var list = el("ol", "s0-checks s0-rehearsal-checks");
    (record.checks || []).forEach(function (check, index) {
      var item = el("li", check.status === "passed" ? "check-passed" : "");
      item.appendChild(checkMark(index, check.status === "passed"));
      item.appendChild(el("div", null, check.label || check.key));
      item.appendChild(el("b", null, {passed: "已验证", failed: "失败", waiting: "未完成"}[check.status] || check.status));
      list.appendChild(item);
    });
    return list;
  }
  function setRehearsalBusy(value) {
    rehearsalBusy = value;
    $("s0Rehearsal").disabled = value;
    $("s0Rehearsal").setAttribute("aria-busy", String(value));
    $("s0Rehearsal").textContent = value ? "演练运行中…" : "运行 S0 演练（临时小基线）";
    $("s0RehearsalHint").textContent = value ? "正在复制与核验，请保留本页" : "只验证链路，不代表环境就绪";
  }
  function renderRehearsal(record) {
    var prepared = record.status === "prepared";
    var box = $("s0RehearsalResult");
    box.replaceChildren(
      el("div", "receipt-label", prepared ? "演练记录 · S0-a 链路已走通（S0-b 不参与演练）" : "演练失败（记录已保留，未删除）"),
      el("div", "mono receipt-id", record.id || "—"),
      el("div", "mono tiny muted", "status = " + (record.status || "—")),
      el("div", "mono receipt-path", "副本：" + (record.work_env || "—")));
    if (record.error) box.appendChild(el("div", "alert bad", record.error));
    if (Array.isArray(record.checks) && record.checks.length) {
      box.appendChild(checkRows(record));
      box.appendChild(el("p", "muted tiny", "四项（copy/rtl/non_rtl/baseline）通过；端口确认与三库冒烟由本页一键入口承接，演练不签准出。"));
    }
    box.appendChild(el("p", "s0-rehearsal-scope", REHEARSAL_SCOPE));
  }
  async function rehearse() {
    if (rehearsalBusy || busy) return;
    setRehearsalBusy(true);
    $("s0RehearsalError").replaceChildren();
    try {
      // 演练不接受任何客户端路径（防任意写）：只发空 body，输入由服务端在软件 state 下自造。
      var record = await api("/api/s0/rehearsal", {method: "POST", body: {}}, 0);
      renderRehearsal(record);
      try { await loadIndex(); } catch (e) {
        $("s0RehearsalError").replaceChildren(el("div", "alert bad", "读取准备记录失败：" + e.message));
      }
    } catch (e) {
      // 失败展示服务端 detail.error 原文；有 failed 记录时一并显示，便于复核。
      var detail = e.body && e.body.detail;
      $("s0RehearsalError").replaceChildren(el("div", "alert bad", (detail && detail.error) || e.message));
      if (detail && detail.record) renderRehearsal(detail.record);
    } finally {
      setRehearsalBusy(false);
    }
  }
  async function loadIndex() {
    var data = await api("/api/s0");
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
    /* 二选一（S0 §9.9 / WEB_UI §15）：按模式只发当前那一格；高级键非空才发。
     * 空值不发 —— 默认值由服务端决定（§9.1）。 */
    var mode = currentMode();
    var payload = {};
    if (mode === "env") {
      var envDir = $("s0EnvDir").value.trim();
      if (envDir) payload.baseline = envDir;
    } else {
      var rtlSource = $("s0Rtl").value.trim();
      if (rtlSource) payload.rtl_source = rtlSource;
    }
    [["baseline_version", "s0Version"], ["work_env", "s0Work"]].forEach(function (pair) {
      var value = $(pair[1]).value.trim();
      if (value) payload[pair[0]] = value;
    });
    var token = ++selection;
    error("");
    switchMsg("", "");
    codesReset();
    setBusy(true);
    try {
      // 工程复制不套用普通 GET 的短超时；断连后用户可从准备记录重新查询。
      var record = await api("/api/s0/from-rtl", {method: "POST", body: payload}, 0);
      if (token === selection) render(record);
    } catch (e) {
      if (token === selection) {
        error((detailError(e) || e.message) + (e.status === 0 ? "；服务端操作可能仍在进行，请刷新准备记录确认，勿覆盖目标。" : ""));
        var failed = e.body && e.body.detail && e.body.detail.record;
        if (failed) render(failed);
      }
    } finally {
      setBusy(false);
      try { await loadIndex(); } catch (e) { error("读取准备记录失败：" + e.message); }
      loadCopies();
    }
  }
  /* 新一次提交前清掉上一条记录的切换/副本提示，避免把旧结论当成本次结论。 */
  function codesReset() {
    switchPollToken++;
    if (switchPoll) { clearTimeout(switchPoll); switchPoll = null; }
    switchState = { message: "", kind: "" };
    switchDone = null;
    copiesMessage = { text: "", kind: "" };
  }
  return {init: function (request) {
    api = request;
    $("s0Form").addEventListener("submit", submit);
    ["s0ModeRtl", "s0ModeEnv"].forEach(function (id) {
      var radio = $(id);
      if (!radio) return;
      radio.addEventListener("change", function () {
        error("");
        applyMode();     /* 只切换显隐/required/disabled；已填内容不因切模式被清空 */
      });
    });
    applyMode();
    $("s0Rehearsal").addEventListener("click", rehearse);
    $("s0Refresh").addEventListener("click", async function () {
      if (busy) return;
      try { await loadIndex(); if (selected) await loadRecord(selected); }
      catch (e) { error("读取准备记录失败：" + e.message); }
      loadEnvState();
      loadCopies();
    });
    $("s0SwitchRefresh").addEventListener("click", function () { loadEnvState(); });
    $("s0CopiesRefresh").addEventListener("click", function () { loadCopies(); });
    loadIndex().catch(function (e) { error("环境准备服务暂不可用：" + e.message); });
    loadEnvState();
    loadCopies();
  }};
})();
