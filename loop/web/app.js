/* 变更影响闭环 · 运营台 v1（app.js）
 *
 * 定位（spec §1 / §9）：界面投影服务端状态并传输操作，不持有业务判据。
 *   · 数据只消费：/api/health、/api/runs、/api/runs/{id}、/api/runs/{id}/nodes/{node}、
 *     /api/baselines、/api/env/check、/api/fs/dirs、POST /api/runs、闸门决策、job 取消、证据存在性探测。
 *   · 闸门决策枚举、blockers、counts、stage_map、agents 全部由服务端下发；本文件不手抄枚举。
 *   · 渲染单向：state → render；所有服务端字符串走 textContent / replaceChildren，不拼 innerHTML。
 *   · 零外部依赖；后端未就绪时用 try/catch + 顶部横幅 + 局部空态降级，绝不白屏。
 */
"use strict";

(function () {
  var POLL_MS = 1500;
  var HIDDEN_POLL_MS = 10000;

  /* ------------------------------------------------------------------ *
   * 展示契约（spec §4.2 / §4.3）：节点中文名 / owner / 角色卡标题。
   * 只用于「怎么显示」，绝不参与判定；状态与数据一律取自服务端响应。
   * ------------------------------------------------------------------ */
  var NODE_META = {
    N0: { name: "基线", owner: "Host" },
    N1: { name: "摄取", owner: "Host" },
    N2: { name: "diff", owner: "Host" },
    N3: { name: "总结", owner: "analyst" },
    N4: { name: "闸门1", owner: "人", gate: true },
    N5: { name: "影响", owner: "Host" },
    N6: { name: "修订", owner: "author" },
    N7: { name: "编译", owner: "Host" },
    N8: { name: "复核", owner: "checker" },
    N9: { name: "全跑", owner: "Host" },
    N10: { name: "对账", owner: "checker" },
    N11: { name: "守护", owner: "guardian" },
    N12: { name: "报告", owner: "reporter" },
    N13: { name: "闸门2", owner: "人", gate: true },
    N14: { name: "闸门3", owner: "人", gate: true },
    N15: { name: "回归", owner: "TriggerFlow" },
    N16: { name: "晋升", owner: "Host" }
  };

  /* 仅在服务端未下发 stage_map 时使用的展示兜底（spec §4.2 的展示契约）。 */
  var STAGE_FALLBACK = [
    { key: "ingest", name: "摄取", nodes: ["N0", "N1", "N2", "N3", "N4"] },
    { key: "revise", name: "修订", nodes: ["N5", "N6", "N7", "N8"] },
    { key: "verify", name: "验证", nodes: ["N9", "N10", "N11", "N12"] },
    { key: "decide", name: "决策", nodes: ["N13", "N14", "N15", "N16"] }
  ];

  var AGENT_DEFS = [
    { role: "analyst", name: "simenv-analyst", nodes: ["N3"], desc: "差异语义总结", avatar: "析", cls: "a1" },
    { role: "author", name: "simenv-author", nodes: ["N6"], desc: "用例修订 / 补充", avatar: "作", cls: "a2" },
    { role: "checker", name: "simenv-checker", nodes: ["N8", "N10"], desc: "静态复核 / 结果对账", avatar: "检", cls: "a3" },
    { role: "guardian", name: "simenv-guardian", nodes: ["N11"], desc: "证据守护", avatar: "守", cls: "a4" },
    { role: "reporter", name: "simenv-reporter", nodes: ["N12"], desc: "评估报告", avatar: "报", cls: "a5" }
  ];

  /* 闸门标题仅作展示；节点也优先取服务端 payload.gate_node。 */
  var GATE_TITLES = {
    G1_diff_confirm: { label: "闸门 1 · 差异确认", node: "N4" },
    G2_report_accept: { label: "闸门 2 · 报告验收", node: "N13" },
    G3_regression_decision: { label: "闸门 3 · 回归决策", node: "N14" }
  };

  /* 事件流白名单：只显示这些 kind（spec §4.4 第 5 条）。 */
  var EVENT_WHITELIST = {
    run_started: 1, run_finished: 1,
    node_started: 1, node_finished: 1, node_failed: 1,
    gate_pending: 1, gate_decided: 1,
    job_submitted: 1, job_progress: 1, job_finished: 1, dead_job: 1,
    admission_granted: 1, admission_refused: 1, admission_queued: 1,
    warning: 1
  };
  var EVENT_DETAIL_FIELDS = ["gate", "decision", "cycle", "message", "model", "mode", "rc", "diff_count"];

  var STATUS_LABEL = {
    running: "执行中",
    waiting_gate: "等待人工",
    waiting_job: "等待作业",
    waiting_slot: "排队等单槽",
    finished: "已结束",
    failed: "失败"
  };

  var VIEW_META = {
    s0: ["环境准备", "从只读基线派生工作副本，让每一次验证都有据可查"],
    setup: ["运行配置", "选择基线与项目，核对运行选项，启动现有闭环"],
    run: ["运行监控", "跟踪流程进度、Agent 任务与实际运行证据"],
    gate: ["人工闸门", "依据差异与证据逐条复核；闸门状态以服务端记录为准"]
  };

  /* ------------------------------------------------------------------ *
   * 状态：单向数据流，轮询只更新数据，不重建带输入的 DOM 子树。
   * ------------------------------------------------------------------ */
  var state = {
    health: null,
    healthError: null,
    runs: [],
    runsError: null,
    runId: null,
    selectionEpoch: 0,
    detailRequest: 0,
    viewData: null,
    viewError: null,
    /* F13：当前选择的「上次成功时间」与在途标记；切换运行必须同时清空成功时间。 */
    viewLastOkAt: null,
    viewRequesting: false,
    /* U2-a（SPEC-04 §7.3）：当前选择的 SSE 流状态；非业务状态，判定/草稿/提交不读它。 */
    streamState: "stopped",
    /* U5（SPEC-REV-07）：事件流客户端过滤；null = 不过滤（全部）。 */
    eventFilter: null,
    view: "s0",
    baselines: [],
    baselinesLoading: false,
    baselinesError: null,
    baselineRoot: null,
    setup: {
      baseline: "",
      project: "",
      check: null,
      checking: false,
      checkError: null,
      mode: "drill",
      scenario: "happy",
      now: "",
      submitting: false,
      error: null
    },
    picker: null,
    gateDraft: { key: null, gate: null, decision: null, actor: "human:", reason: "", submitting: false, error: null, blockers: null, note: null },
    gateSubmissions: Object.create(null),
    stageOverride: "auto",
    connError: null,
    lastOkAt: null,
    lastPollAt: 0,
    polling: false
  };

  /* ------------------------------------------------------------------ *
   * 基础工具
   * ------------------------------------------------------------------ */
  function $(id) { return document.getElementById(id); }

  function h(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clearEl(node) { if (node) node.replaceChildren(); }

  function setText(id, text) {
    var node = $(id);
    if (node) node.textContent = text === undefined || text === null ? "" : String(text);
  }

  function enc(v) { return encodeURIComponent(v === undefined || v === null ? "" : String(v)); }

  function pad(n, width) {
    var s = String(n);
    while (s.length < width) s = "0" + s;
    return s;
  }

  function addKV(host, label, value) {
    var row = h("div", "kv");
    row.appendChild(h("span", null, label));
    row.appendChild(h("b", null, value === undefined || value === null || value === "" ? "—" : String(value)));
    host.appendChild(row);
    return row;
  }

  function spanKV(label, value) {
    var span = h("span");
    span.appendChild(document.createTextNode(label + " "));
    span.appendChild(h("b", null, value === undefined || value === null || value === "" ? "—" : String(value)));
    return span;
  }

  function chipEl(text, cls) {
    return h("span", "chip" + (cls ? " " + cls : ""), text);
  }

  function errText(e) {
    if (!e) return "未知错误";
    var prefix = e.path ? e.path + " → " : "";
    return prefix + (e.message || String(e)) + errDetailText(e);
  }

  // 基线拒绝的结构化字段（Web UI §6.4）：missing=缺件，errors=schema/身份/指纹/链违规。
  // 只展示服务端下发内容，不在前端重新推导或猜测原因。
  function errDetailText(e) {
    var d = e && e.body && e.body.detail;
    if (!d || typeof d !== "object") return "";
    var parts = [];
    if (Array.isArray(d.missing) && d.missing.length) {
      parts.push("缺件：" + d.missing.join("、"));
    }
    if (Array.isArray(d.errors) && d.errors.length) {
      var shown = d.errors.slice(0, 3).join("、");
      if (d.errors.length > 3) shown += " …（共 " + d.errors.length + " 条）";
      parts.push("违规：" + shown);
    }
    return parts.length ? "（" + parts.join("；") + "）" : "";
  }

  /* ------------------------------------------------------------------ *
   * HTTP：统一错误形态；超时/断连都转成可展示的错误，不吞异常。
   * ------------------------------------------------------------------ */
  async function api(path, opts, timeoutMs) {
    if (timeoutMs === undefined) timeoutMs = 15000;
    var init = Object.assign({ headers: { "Content-Type": "application/json" } }, opts || {});
    if (init.body && typeof init.body !== "string") init.body = JSON.stringify(init.body);
    var ctrl = null;
    var timer = null;
    if (typeof AbortController === "function") {
      ctrl = new AbortController();
      init.signal = ctrl.signal;
      if (timeoutMs) timer = setTimeout(function () { ctrl.abort(); }, timeoutMs);
    }
    var res;
    try {
      res = await fetch(path, init);
    } catch (e) {
      var msg = (e && e.name === "AbortError")
        ? "请求超时（" + (timeoutMs / 1000) + " s）：" + path
        : "网络不可达：" + (e && e.message ? e.message : String(e));
      throw Object.assign(new Error(msg), { status: 0, path: path, body: null });
    } finally {
      if (timer) clearTimeout(timer);
    }
    var text = "";
    try { text = await res.text(); } catch (e2) { text = ""; }
    var body = null;
    if (text) {
      try { body = JSON.parse(text); } catch (e3) { body = null; }
    }
    if (!res.ok) {
      var detail = body && body.detail;
      var dm = "";
      if (detail && typeof detail === "object") {
        dm = detail.error || detail.message || "";
      } else if (typeof detail === "string") {
        dm = detail;
      }
      if (!dm) dm = text ? text.slice(0, 300) : ("HTTP " + res.status);
      var err = new Error(dm);
      err.status = res.status;
      err.path = path;
      err.body = body;
      throw err;
    }
    return body || {};
  }

  /* ------------------------------------------------------------------ *
   * 时间格式化（时间字段是唯一允许的非确定性）
   * ------------------------------------------------------------------ */
  function parseTs(v) {
    if (v === null || v === undefined || v === "") return null;
    if (typeof v === "number") {
      var dNum = new Date(v * 1000);
      return isNaN(dNum.getTime()) ? null : dNum;
    }
    var s = String(v).trim();
    var nonIso = s.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})([+-]\d{2})(\d{2})$/);
    if (nonIso) {
      var d2 = new Date(nonIso[1] + "-" + nonIso[2] + "-" + nonIso[3] + "T" + nonIso[4] + ":" +
        nonIso[5] + ":" + nonIso[6] + nonIso[7] + ":" + nonIso[8]);
      if (!isNaN(d2.getTime())) return d2;
    }
    var trimmed = s.replace(/^(.*\.\d{3})\d+/, "$1");
    var d = new Date(trimmed);
    if (!isNaN(d.getTime())) return d;
    var d3 = new Date(s);
    return isNaN(d3.getTime()) ? null : d3;
  }

  function fmtClock(ts) {
    var d = ts instanceof Date ? ts : new Date(ts);
    if (isNaN(d.getTime())) return "—";
    return pad(d.getHours(), 2) + ":" + pad(d.getMinutes(), 2) + ":" + pad(d.getSeconds(), 2);
  }

  function fmtDateTime(v) {
    var d = parseTs(v);
    if (!d) return v ? String(v) : "—";
    return d.getFullYear() + "-" + pad(d.getMonth() + 1, 2) + "-" + pad(d.getDate(), 2) + " " +
      pad(d.getHours(), 2) + ":" + pad(d.getMinutes(), 2);
  }

  function relTime(v) {
    var d = parseTs(v);
    if (!d) return "—";
    var s = Math.floor((Date.now() - d.getTime()) / 1000);
    if (s < 0) s = 0;
    if (s < 5) return "刚刚";
    if (s < 60) return s + " 秒前";
    if (s < 3600) return Math.floor(s / 60) + " 分钟前";
    if (s < 86400) return Math.floor(s / 3600) + " 小时前";
    return Math.floor(s / 86400) + " 天前";
  }

  function fmtDuration(sec) {
    if (sec === null || sec === undefined || isNaN(sec)) return "—";
    sec = Math.max(0, Math.floor(Number(sec)));
    if (sec >= 3600) {
      return Math.floor(sec / 3600) + ":" + pad(Math.floor((sec % 3600) / 60), 2) + ":" + pad(sec % 60, 2);
    }
    return pad(Math.floor(sec / 60), 2) + ":" + pad(sec % 60, 2);
  }

  function elapsedText(v) {
    if (!v) return "—";
    var start = parseTs(v.created_at);
    if (!start) return "—";
    var end = (v.status === "finished" || v.status === "failed")
      ? (parseTs(v.updated_at) || new Date())
      : new Date();
    return fmtDuration((end.getTime() - start.getTime()) / 1000);
  }

  function bytesText(n) {
    if (n === null || n === undefined) return "—";
    var v = Number(n);
    if (!isFinite(v)) return String(n);
    if (v < 1024) return v + " B";
    if (v < 1024 * 1024) return (v / 1024).toFixed(1) + " KB";
    return (v / 1024 / 1024).toFixed(2) + " MB";
  }

  function shortPath(p) {
    var s = String(p || "");
    if (s.length <= 48) return s;
    var parts = s.split("/");
    var tail = parts.slice(-2).join("/");
    return "…/" + tail;
  }

  function shortRef(ref) {
    var s = String(ref || "");
    return s.length <= 34 ? s : s.slice(0, 31) + "…";
  }

  /* ------------------------------------------------------------------ *
   * toast / 横幅
   * ------------------------------------------------------------------ */
  var toastTimer = null;
  function toast(msg) {
    var el = $("toast");
    if (!el) return;
    el.textContent = String(msg);
    el.classList.add("show");
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { el.classList.remove("show"); }, 3200);
  }

  function renderBanners() {
    var host = $("banners");
    if (!host) return;
    clearEl(host);
    if (!state.connError) return;
    var text = "轮询连接失败：" + state.connError;
    if (state.lastOkAt) text += " · 最近一次轮询成功 " + fmtClock(state.lastOkAt);
    host.appendChild(h("div", "banner bad", text));
  }

  /* ------------------------------------------------------------------ *
   * 状态标签
   * ------------------------------------------------------------------ */
  function statusLabel(s) {
    if (!s) return "未知";
    return STATUS_LABEL[s] || String(s);
  }

  function statusKind(s) {
    if (s === "running") return "run";
    if (s === "waiting_gate" || s === "waiting_job" || s === "waiting_slot") return "wait";
    if (s === "finished") return "done";
    if (s === "failed") return "fail";
    return "run";
  }

  function dotClass(s) {
    if (s === "running") return "";
    if (s === "waiting_gate" || s === "waiting_job" || s === "waiting_slot") return "warn";
    if (s === "failed") return "bad";
    return "idle";
  }

  /* ------------------------------------------------------------------ *
   * 数据加载
   * ------------------------------------------------------------------ */
  async function loadHealth(silent) {
    try {
      var x = await api("/api/health");
      state.health = x;
      state.healthError = null;
      // 事件白名单以服务端为准（SPEC-02 §9）：静态表只是首屏兜底，收到 health 后覆盖。
      if (x && Array.isArray(x.event_kinds) && x.event_kinds.length) {
        var next = {};
        x.event_kinds.forEach(function (kind) { if (kind) next[String(kind)] = 1; });
        EVENT_WHITELIST = next;
      }
      if (!state.setup.project && x && x.env_root) state.setup.project = String(x.env_root);
    } catch (e) {
      state.healthError = errText(e);
      if (!silent) toast("健康检查失败：" + e.message);
    }
    renderHeader();
    renderSetup();
    renderHealthCard();
  }

  async function loadRuns() {
    var body = await api("/api/runs");
    state.runs = Array.isArray(body.runs) ? body.runs : [];
    state.runsError = null;
    notifyOnRuns();
    renderSidebar();
  }

  async function loadBaselines(manual) {
    state.baselinesLoading = true;
    renderSetup();
    try {
      var body = await api("/api/baselines");
      state.baselines = Array.isArray(body.baselines) ? body.baselines : [];
      state.baselineRoot = body.workspace_root
        ? String(body.workspace_root).replace(/\/$/, "") + "/baselines"
        : null;
      state.baselinesError = null;
      if (!findValidBaseline(state.setup.baseline)) {
        var first = null;
        for (var i = 0; i < state.baselines.length; i++) {
          if (state.baselines[i] && state.baselines[i].valid) { first = state.baselines[i]; break; }
        }
        state.setup.baseline = first ? first.id : "";
      }
      if (manual) toast("基线已刷新：" + state.baselines.length + " 个版本");
    } catch (e) {
      state.baselinesError = errText(e);
      if (manual) toast("刷新基线失败：" + e.message);
    } finally {
      state.baselinesLoading = false;
      renderSetup();
    }
  }

  function findBaseline(id) {
    if (!id) return null;
    for (var i = 0; i < state.baselines.length; i++) {
      if (state.baselines[i] && state.baselines[i].id === id) return state.baselines[i];
    }
    return null;
  }

  async function checkProject(silent) {
    var path = String(state.setup.project || "").trim();
    state.setup.check = null;
    state.setup.checkError = null;
    if (!path) {
      state.setup.checkError = "尚未选择项目目录";
      renderSetup();
      return;
    }
    state.setup.checking = true;
    renderSetup();
    try {
      state.setup.check = await api("/api/env/check?path=" + enc(path));
    } catch (e) {
      state.setup.check = null;
      state.setup.checkError = errText(e);
      if (!silent) toast("环境校验失败：" + e.message);
    } finally {
      state.setup.checking = false;
      renderSetup();
    }
  }

  /* 当前运行详情请求的展示判据（唯一实现：web/run-view-state.js，Web UI §7.2）。 */
  function deriveView() {
    return window.RunViewState.derive({
      hasData: !!state.viewData,
      error: state.viewError,
      requesting: state.viewRequesting,
      lastSuccessAt: state.viewLastOkAt
    });
  }

  /* 面板占位同样只消费 deriveView()：首次失败时不得再出现「加载中」占位。 */
  function panelHint() {
    return deriveView().kind === "first_error"
      ? "读取失败，暂无数据（可点「重新读取」）"
      : "运行视图加载中…";
  }

  async function fetchRunView() {
    if (!state.runId) return false;
    var token = { runId: state.runId, epoch: state.selectionEpoch, request: ++state.detailRequest };
    function current() {
      return window.RunViewState.isCurrent(token, {
        runId: state.runId, epoch: state.selectionEpoch, request: state.detailRequest
      });
    }
    state.viewRequesting = true;
    try {
      var view = await api("/api/runs/" + enc(token.runId));
      if (!current()) return false;
      state.viewData = view;
      state.viewError = null;
      state.viewLastOkAt = Date.now();
      return true;
    } catch (e) {
      if (!current()) return false;
      state.viewError = errText(e);
      throw e;
    } finally {
      if (current()) state.viewRequesting = false;
    }
  }

  /* 轮询：单个来源失败不覆盖其它来源；失败保留最近成功数据并出横幅。 */
  async function poll() {
    if (state.polling) return;
    state.polling = true;
    var firstErr = null;
    try {
      try {
        await loadRuns();
      } catch (e1) {
        state.runsError = errText(e1);
        firstErr = firstErr || e1;
      }
      /* U2-a（§7.3）：流处于 open 时详情由推送驱动，主轮询跳过（不双通道并发写）。 */
      if (state.runId && state.streamState !== "open") {
        try {
          await fetchRunView();
        } catch (e2) {
          firstErr = firstErr || e2;
        }
      }
      if (!state.health) {
        try { await loadHealth(true); } catch (e3) { /* loadHealth 内部已记录 */ }
      }
    } finally {
      state.polling = false;
      state.lastPollAt = Date.now();
      if (firstErr) {
        state.connError = errText(firstErr);
      } else {
        state.connError = null;
        state.lastOkAt = Date.now();
      }
      renderLive();
    }
  }

  /* ------------------------------------------------------------------ *
   * 视图切换
   * ------------------------------------------------------------------ */
  /* U7（SPEC-REV-08 / SPEC-04 §7.4）：会话深链同步。
   * 纯编解码在 web/session-url.js；这里只做 replaceState 同步（不产生历史项）。
   * run/gate 视图携带 run 段；其余视图不带（深链恢复时不自动重开运行）。 */
  function syncLocationHash() {
    if (!window.RunSessionUrl || !window.history) return;
    var runId = (state.view === "run" || state.view === "gate") ? state.runId : null;
    var hash = window.RunSessionUrl.encode(runId, state.view);
    if (location.hash === (hash || "")) return;
    try {
      history.replaceState(null, "", location.pathname + location.search + (hash || ""));
    } catch (e) { /* 老浏览器/隐私模式：深链不可用不影响功能 */ }
  }

  function showView(v) {
    if (!VIEW_META[v]) v = "setup";
    state.view = v;
    ["s0", "setup", "run", "gate"].forEach(function (k) {
      var section = $("view" + k.charAt(0).toUpperCase() + k.slice(1));
      if (section) section.classList.toggle("hidden", k !== v);
    });
    var segs = document.querySelectorAll("#viewSeg button");
    for (var i = 0; i < segs.length; i++) {
      segs[i].classList.toggle("on", segs[i].getAttribute("data-view") === v);
      segs[i].setAttribute("aria-selected", segs[i].getAttribute("data-view") === v ? "true" : "false");
      segs[i].tabIndex = segs[i].getAttribute("data-view") === v ? 0 : -1;
    }
    setText("pageTitle", VIEW_META[v][0]);
    setText("pageSub", VIEW_META[v][1]);
    setText("pageCrumb", VIEW_META[v][0]);
    setText("pageIndex", {s0: "S0", setup: "01", run: "02", gate: "03"}[v]);
    renderLive();
    if (v === "setup") renderSetup();
    try { window.scrollTo({ top: 0 }); } catch (e) { /* 老浏览器忽略 */ }
    syncLocationHash();
  }

  async function openRun(id) {
    if (!id) return;
    if (window.AgentWindow) window.AgentWindow.close();
    state.runId = String(id);
    state.selectionEpoch++;
    state.viewData = null;
    state.viewError = null;
    /* F13：新选择不得继承上一运行的成功数据或成功时间。 */
    state.viewLastOkAt = null;
    /* 先置在途标记再渲染：慢请求期间顶栏与面板都只能看到「加载中」，不会出现「尚未读取」。 */
    state.viewRequesting = true;
    state.stageOverride = "auto";
    resetGateDraft();
    showView("run");
    restartRunStream();
    try {
      if (!await fetchRunView()) return;
    } catch (e) {
      toast("打开运行失败：" + e.message);
    }
    var st = state.viewData ? state.viewData.status : null;
    showView(st === "waiting_gate" ? "gate" : "run");
    renderLive();
  }

  /* ------------------------------------------------------------------ *
   * 顶栏 / 左栏 / 配置
   * ------------------------------------------------------------------ */
  function renderHeader() {
    setText("hdrAddr", window.location.host || "127.0.0.1");
    var dotCls = "idle";
    var envText = "环境未就绪";
    var healthText = "健康检查中…";
    var healthTitle = "";
    if (state.health) {
      envText = state.health.env_id || state.health.env_root || "环境未就绪";
      var pm = (state.health.plugin_missing || []).length;
      var wm = (state.health.workspace_missing || []).length;
      dotCls = pm || wm ? "warn" : "";
      healthText = (pm ? "插件缺 " + pm + " 项" : "插件面齐全") +
        (wm ? " · 数据缺 " + wm + " 项" : "") +
        " · agently " + (state.health.agently || "?");
      healthTitle = "ENV_ROOT：" + (state.health.env_root || "—") +
        "\nWORKSPACE_ROOT：" + (state.health.workspace_root || "—");
    } else if (state.healthError) {
      dotCls = "bad";
      healthText = "健康检查失败";
      healthTitle = state.healthError;
    }
    var dot = $("hdrDot");
    if (dot) dot.className = "dot " + dotCls;
    setText("hdrEnvText", envText);
    var envPill = $("hdrEnv");
    if (envPill) envPill.title = envText;
    var hdrHealth = $("hdrHealth");
    if (hdrHealth) {
      hdrHealth.textContent = healthText;
      hdrHealth.title = healthTitle || healthText;
    }
    renderRailFoot();
  }

  function renderRailFoot() {
    var x = state.health;
    var tool = $("railToolRoot");
    var ws = $("railWorkspaceRoot");
    var model = $("railModel");
    if (tool) {
      var t = x && x.tool_root ? String(x.tool_root) : "—";
      tool.textContent = "TOOL_ROOT · " + t;
      tool.title = t;
    }
    if (ws) {
      var w = x && x.workspace_root ? String(x.workspace_root) : "—";
      ws.textContent = "数据根 · " + w;
      ws.title = w;
    }
    if (model) {
      var m = x && x.llm && x.llm.model ? String(x.llm.model) : "—";
      model.textContent = "模型 · " + m;
      model.title = m;
    }
  }

  /* 列表重建守卫（WEB_UI_SPEC §2「重建策略」2026-10-26）：轮询 1.5 s 一拍，
     内容没变就别重建 DOM —— 每拍 clearEl + 重建会让点击目标反复被替换，
     真实浏览器里表现为 `element was detached from the DOM`（UI 竞态用例超时）。
     签名只覆盖列表实际渲染所用的状态：运行数组、选中项、错误串。 */
  var sidebarSig = null;

  function renderSidebar() {
    renderWaitCenter();
    var host = $("runList");
    if (!host) return;
    var sig = JSON.stringify([state.runId, state.runsError, state.runs]);
    if (sig === sidebarSig) return;
    sidebarSig = sig;
    clearEl(host);
    if (!state.runs.length) {
      if (state.runsError) {
        host.appendChild(h("div", "run-empty", "读取运行列表失败：" + state.runsError));
      } else {
        host.appendChild(h("div", "run-empty", "暂无运行记录。点「＋ 新建运行」创建第一条。"));
      }
      return;
    }
    state.runs.forEach(function (r) {
      if (!r) return;
      var btn = h("button", "run-item" + (r.run_id === state.runId ? " active" : ""));
      btn.type = "button";
      var rid = h("div", "rid");
      rid.appendChild(h("span", "dot " + dotClass(r.status)));
      rid.appendChild(h("span", "mono", r.run_id || "—"));
      btn.appendChild(rid);
      var meta = h("div", "meta");
      meta.appendChild(h("span", null, r.mode || "—"));
      meta.appendChild(h("span", null, "·"));
      meta.appendChild(h("span", null, statusLabel(r.status) + (r.current_node ? " · " + r.current_node : "")));
      meta.appendChild(h("span", null, "·"));
      meta.appendChild(h("span", null, relTime(r.updated_at)));
      btn.appendChild(meta);
      btn.title = (r.run_id || "") + " · " + (r.status || "");
      btn.addEventListener("click", function () { openRun(r.run_id); });
      host.appendChild(btn);
    });
    if (state.runsError && state.runs.length) {
      host.appendChild(h("div", "run-empty", "连接异常，列表可能过期：" + state.runsError));
    }
  }

  /* ---------------- U1 等待送达（SPEC-REV-07，2026-10-24） ----------------
   * 提醒是投影的又一个消费者：判定口径在 web/wait-center.js（纯函数），
   * 这里只承担 DOM / Notification / 标题三路呈现与计时器；不携带判定、不可回放。
   * 通知被拒绝或浏览器不支持 Notification ⇒ 标题徽标 + 后台闪烁兜底（始终可用）。 */
  var BASE_TITLE = document.title;
  var waitPrev = null; /* 上一拍 runs 数组；null = 首拍不提醒（没有「从什么跃迁」） */
  var flashTimer = null;

  function notifyOnRuns() {
    if (!window.WaitCenter) return;
    var alerts = window.WaitCenter.deriveAlerts(waitPrev, state.runs);
    if (!flashTimer) {
      document.title = window.WaitCenter.badgeTitle(
        BASE_TITLE, window.WaitCenter.attentionCount(state.runs));
    }
    waitPrev = state.runs;
    alerts.forEach(fireAlert);
  }

  var ALERT_TEXT = {
    gate: { label: "等待人工决策", body: "闸门等待签署；打开人工闸门视图处理。" },
    failed: { label: "运行失败", body: "运行已失败；查看失败原因与事件流。" },
    job_done: { label: "作业已结束", body: "长作业已结束，流程继续推进。" }
  };

  function fireAlert(alert) {
    var text = ALERT_TEXT[alert.kind] || { label: String(alert.to || ""), body: "" };
    if (window.Notification && Notification.permission === "granted") {
      try {
        var n = new Notification(alert.run_id + " · " + text.label, {
          body: text.body, tag: alert.run_id + ":" + alert.kind
        });
        n.onclick = function () {
          window.focus();
          openRun(alert.run_id);
          try { n.close(); } catch (e) { /* 已关 */ }
        };
        setTimeout(function () { try { n.close(); } catch (e) { /* 已关 */ } }, 10000);
      } catch (e) { /* 通知构造失败：标题徽标仍在 */ }
    }
    if (document.hidden) startFlash();
  }

  function startFlash() {
    if (flashTimer || !window.WaitCenter) return;
    var on = false;
    flashTimer = setInterval(function () {
      on = !on;
      var count = window.WaitCenter.attentionCount(state.runs);
      document.title = on
        ? "● " + window.WaitCenter.badgeTitle(BASE_TITLE, count)
        : window.WaitCenter.badgeTitle(BASE_TITLE, count);
    }, 1000);
  }

  function stopFlash() {
    if (!flashTimer) return;
    clearInterval(flashTimer);
    flashTimer = null;
    document.title = window.WaitCenter
      ? window.WaitCenter.badgeTitle(BASE_TITLE, window.WaitCenter.attentionCount(state.runs))
      : BASE_TITLE;
  }

  /* U1-b：「在等我」行动条（只读聚合，点击直达；条目判定在 wait-center.js）。 */
  function renderWaitCenter() {
    var host = $("actionBar");
    if (!host || !window.WaitCenter) return;
    clearEl(host);
    var actions = window.WaitCenter.deriveActions(state.runs);
    if (!actions.length) {
      host.appendChild(h("div", "action-empty", "无待办"));
      return;
    }
    actions.forEach(function (a) {
      var btn = h("button", "action-item");
      btn.type = "button";
      btn.appendChild(h("span", "dot " + (a.kind === "gate" ? "warn" : "bad")));
      var box = h("span", "action-text");
      box.appendChild(h("b", "mono", a.run_id));
      box.appendChild(h("small", null, a.kind === "gate" ? "等待人工决策" : "运行失败"));
      btn.appendChild(box);
      btn.title = a.run_id + " · " + (a.kind === "gate" ? "等待人工决策" : "运行失败");
      btn.addEventListener("click", function () { openRun(a.run_id); });
      host.appendChild(btn);
    });
  }

  /* U1-a：通知开关（只请求权限；被拒绝 ⇒ 禁用并显示已拒绝，标题兜底不受影响）。 */
  function renderNotifyButton() {
    var btn = $("btnNotify");
    if (!btn || !window.Notification) return;
    var p = Notification.permission;
    btn.textContent = p === "granted" ? "通知 已开启"
      : p === "denied" ? "通知 已拒绝" : "开启等待通知";
    btn.disabled = p === "denied";
  }

  /* ---------------- U2-a SSE 传输（SPEC-REV-07 / SPEC-04 §7.3，2026-10-24） ----------------
   * 当前选择的运行详情优先走流；状态机在 web/run-stream.js（计时器注入的纯模块）。
   * open 态主轮询跳过详情请求（列表/健康照常轮询）；回退态回到既有轮询路径——
   * 不双通道并发写（§7.3）。每次选择运行重建控制器（stop 为终态）。 */
  var runStream = null;

  function streamStateText(s) {
    return { connecting: "连接中", open: "实时", fallback: "轮询回退", stopped: "—" }[s] || "—";
  }

  function renderStreamState() {
    setText("streamState", state.runId ? streamStateText(state.streamState) : "—");
  }

  function restartRunStream() {
    if (runStream) { runStream.stop(); runStream = null; }
    state.streamState = "stopped";
    renderStreamState();
    /* 浏览器不支持 EventSource ⇒ 直接轮询（§7.3），不报错、不建流。 */
    if (!state.runId || !window.RunStream || typeof window.EventSource !== "function") return;
    runStream = window.RunStream.createRunStream({
      url: "/api/runs/" + enc(state.runId) + "/stream",
      EventSource: window.EventSource,
      onEvent: function (name, view) {
        if (name !== "run_view" || !view) return;
        /* §7.2 代次判定思想：旧推送不得覆盖新选择（与 fetchRunView 同一守卫）。 */
        if (!state.runId || view.run_id !== state.runId) return;
        state.viewData = view;
        state.viewError = null;
        state.viewLastOkAt = Date.now();
        renderLive();
      },
      onStateChange: function (s) {
        state.streamState = s;
        renderStreamState();
      },
      retryMs: 15000
    });
    runStream.start();
  }

  function renderSetup() {
    renderBaselineSelect();
    renderBaselineMeta();
    var projectInput = $("setupProject");
    if (projectInput) {
      projectInput.value = state.setup.project || "";
      projectInput.title = state.setup.project || "";
    }
    renderProjectMeta();
    var modeSel = $("setupMode");
    if (modeSel) modeSel.value = state.setup.mode;
    var scenarioSel = $("setupScenario");
    if (scenarioSel) {
      scenarioSel.value = state.setup.scenario;
      scenarioSel.disabled = state.setup.mode === "real";
    }
    var nowInput = $("setupNow");
    if (nowInput) nowInput.value = state.setup.now;
    var realWarn = $("realWarn");
    if (realWarn) realWarn.classList.toggle("hidden", state.setup.mode !== "real");
    setText("sumBaseline", state.setup.baseline || "—");
    setText("sumEnv", (state.setup.check && (state.setup.check.env_id || state.setup.check.path)) || state.setup.project || "—");
    setText("sumMode", state.setup.mode);

    var alerts = $("setupAlerts");
    if (alerts) {
      clearEl(alerts);
      if (state.setup.error) alerts.appendChild(h("div", "alert bad", "启动失败：" + state.setup.error));
      if (state.baselinesError) {
        alerts.appendChild(h("div", "alert warn",
          "基线接口不可用（/api/baselines）：" + state.baselinesError + "。可点「刷新」重试；配置视图其余部分仍可用。"));
      }
      if (state.setup.checkError) {
        alerts.appendChild(h("div", "alert bad", "环境校验失败（/api/env/check）：" + state.setup.checkError));
      }
    }

    var startBtn = $("btnStart");
    if (startBtn) {
      startBtn.disabled = !canStart() || state.setup.submitting;
      startBtn.textContent = state.setup.submitting ? "启动中…" : "确认并启动";
    }
    setText("btnStartHint", startHint());
    renderHealthCard();
  }

  function renderBaselineSelect() {
    var sel = $("setupBaseline");
    if (!sel) return;
    clearEl(sel);
    if (state.baselinesLoading && !state.baselines.length) {
      var loading = h("option", null, "加载基线…");
      loading.value = "";
      sel.appendChild(loading);
      sel.disabled = true;
      return;
    }
    if (!state.baselines.length) {
      var empty = h("option", null, state.baselinesError ? "（基线接口不可用）" : "（没有基线）");
      empty.value = "";
      sel.appendChild(empty);
      sel.disabled = true;
      setText("setupBaselineChip", "暂无可用基线");
      return;
    }
    sel.disabled = false;
    var valid = [];
    var invalid = [];
    state.baselines.forEach(function (b) {
      if (!b) return;
      if (b.valid) valid.push(b); else invalid.push(b);
    });
    valid.forEach(function (b) {
      var opt = h("option", null, b.id + (b.created_at ? " · " + fmtDateTime(b.created_at) : ""));
      opt.value = b.id;
      sel.appendChild(opt);
    });
    invalid.forEach(function (b) {
      var opt = h("option", null, b.id + "（不可用）");
      opt.value = b.id;
      opt.disabled = true;
      sel.appendChild(opt);
    });
    if (!state.setup.baseline || !findValidBaseline(state.setup.baseline)) {
      state.setup.baseline = valid.length ? valid[0].id : "";
    }
    sel.value = state.setup.baseline;
    setText("setupBaselineChip", valid.length + " 个可用 / " + state.baselines.length + " 个");
  }

  function findValidBaseline(id) {
    var b = findBaseline(id);
    return b && b.valid ? b : null;
  }

  // 一个 valid 项都没有时，返回首个不可用条目供 meta 给原因（WEB_UI_SPEC §3.1，
  // 2026-10-29 裁决）；列表里存在 valid 项时返回 null —— 原因分支只在「无可用项」可达。
  function firstUnavailableWhenNoValid() {
    var fallback = null;
    for (var i = 0; i < state.baselines.length; i++) {
      var b = state.baselines[i];
      if (!b) continue;
      if (b.valid) return null;
      if (!fallback) fallback = b;
    }
    return fallback;
  }

  function renderBaselineMeta() {
    var host = $("setupBaselineMeta");
    if (!host) return;
    clearEl(host);
    if (state.baselinesError) {
      host.appendChild(h("span", "muted", "基线接口不可用（见上方提示）"));
      return;
    }
    if (!state.baselines.length) {
      host.appendChild(h("span", "muted", state.baselinesLoading ? "加载中…" : "没有可用基线版本"));
      return;
    }
    // 没有可被选中的 valid 项时，用首个不可用条目渲染：字段照旧 + 显式「没有可用基线版本」
    // + 服务端 missing/errors 原文。前端不猜、不合成、不改写路径原文。
    var b = findValidBaseline(state.setup.baseline) || firstUnavailableWhenNoValid();
    if (!b) {
      host.appendChild(h("span", "muted", "未选择基线"));
      return;
    }
    host.appendChild(spanKV("manifest.created_at", b.created_at ? fmtDateTime(b.created_at) : "—"));
    host.appendChild(spanKV("parent", b.parent || "—"));
    host.appendChild(spanKV("用例", b.cases !== undefined && b.cases !== null ? b.cases : "?"));
    host.appendChild(spanKV("RTL 快照", bytesText(b.rtl_snapshot_bytes)));
    if (b.valid) {
      host.appendChild(chipEl("manifest 有效", "ok"));
      return;
    }
    host.appendChild(chipEl("没有可用基线版本", "bad"));
    var missing = b.missing || [];
    var errors = b.errors || [];
    if (missing.length) host.appendChild(h("span", "muted", "missing：" + missing.join("、")));
    if (errors.length) host.appendChild(h("span", "muted", "errors：" + errors.join("；")));
  }

  function renderProjectMeta() {
    var host = $("setupProjectMeta");
    if (!host) return;
    clearEl(host);
    if (state.setup.checking) {
      host.appendChild(h("span", "muted", "校验中…"));
      return;
    }
    if (state.setup.checkError) {
      host.appendChild(h("span", "muted", "校验失败（见上方提示）"));
      return;
    }
    var c = state.setup.check;
    if (!c) {
      host.appendChild(h("span", "muted", "未校验"));
      return;
    }
    host.appendChild(spanKV("env_id", c.env_id || "—"));
    host.appendChild(spanKV("registered", c.registered ? "是" : "否"));
    host.appendChild(spanKV("RTL", c.counts && c.counts.rtl_files !== undefined ? c.counts.rtl_files + " 文件" : "?"));
    host.appendChild(spanKV("TESTLIB", c.counts && c.counts.cases !== undefined ? c.counts.cases + " 用例" : "?"));
    host.appendChild(chipEl(c.ok ? "校验通过" : "校验未通过", c.ok ? "ok" : "bad"));
    var pm = c.plugin_missing || [];
    host.appendChild(pm.length ? chipEl("插件缺：" + pm.join("、"), "bad") : chipEl("插件面齐全", "ok"));
    if (c.matches_current_process === true) {
      host.appendChild(chipEl("与当前进程环境一致", "ok"));
    } else if (c.matches_current_process === false) {
      host.appendChild(chipEl("需以该环境重启服务", "bad"));
    } else {
      host.appendChild(chipEl("matches_current_process 未下发", "warn"));
    }
    if (c.writable) {
      var frozen = c.writable.frozen ? "可写" : "只读";
      var simW = c.writable.sim_workdir ? "可写" : "不可写";
      host.appendChild(chipEl("冻结面 " + frozen + " · SIMLIB_RUN " + simW, c.writable.frozen ? "warn" : ""));
    }
    (c.warnings || []).forEach(function (w) {
      host.appendChild(chipEl(String(w), "warn"));
    });
    if (checkStale(c)) host.appendChild(chipEl("项目目录已变更，需重新校验", "warn"));
  }

  function checkStale(c) {
    return !!(c && c.path && state.setup.project && String(c.path) !== String(state.setup.project));
  }

  function canStart() {
    var b = findValidBaseline(state.setup.baseline);
    if (!b) return false;
    if (!state.setup.project) return false;
    var c = state.setup.check;
    if (!c || !c.ok) return false;
    if (c.plugin_missing && c.plugin_missing.length) return false;
    if (c.matches_current_process !== true) return false;
    if (checkStale(c)) return false;
    return true;
  }

  function startHint() {
    if (state.setup.submitting) return "启动中…";
    if (!findValidBaseline(state.setup.baseline)) return "请选择有效基线";
    if (!state.setup.project) return "请选择项目目录";
    var c = state.setup.check;
    if (!c) return "请先点「校验」";
    if (checkStale(c)) return "项目目录已变更，请重新校验";
    if (!c.ok) return "校验未通过，不能启动";
    if (c.plugin_missing && c.plugin_missing.length) return "插件面缺项：" + c.plugin_missing.join("、");
    if (c.matches_current_process !== true) return "需以该环境重启服务（matches_current_process≠true）";
    if (state.setup.mode === "real") return "real 模式：结果不得当作真机结论";
    return "校验通过，可启动";
  }

  function renderHealthCard() {
    var host = $("healthBody");
    if (!host) return;
    clearEl(host);
    var x = state.health;
    if (!x) {
      if (state.healthError) {
        host.appendChild(h("div", "alert bad", "读取 /api/health 失败：" + state.healthError));
      } else {
        host.appendChild(h("div", "muted tiny", "健康检查中…"));
      }
      return;
    }
    addKV(host, "ENV_ROOT", x.env_root || "—");
    addKV(host, "WORKSPACE_ROOT", x.workspace_root || "—");
    var pm = x.plugin_missing || [];
    var wm = x.workspace_missing || [];
    var pmRow = addKV(host, "plugin_missing", pm.length ? pm.join("、") : "[]");
    pmRow.lastChild.className = pm.length ? "chip bad" : "chip ok";
    var wmRow = addKV(host, "workspace_missing", wm.length ? wm.join("、") : "[]");
    wmRow.lastChild.className = wm.length ? "chip bad" : "chip ok";
    addKV(host, "agently / python", (x.agently || "?") + " / " + (x.python || "?"));
    var llm = x.llm || {};
    addKV(host, "模型", llm.model || "—");
    var chips = h("div", "chips");
    chips.appendChild(chipEl(pm.length || wm.length ? "环境面有缺项" : "环境面齐全", pm.length || wm.length ? "warn" : "ok"));
    chips.appendChild(chipEl(llm.available ? "模型可用" : "模型不可用", llm.available ? "ok" : "bad"));
    chips.appendChild(chipEl(llm.has_api_key ? "key 就绪" : "无 key", llm.has_api_key ? "ok" : "warn"));
    host.appendChild(chips);
    if (llm.reason) host.appendChild(h("div", "alert warn", "模型说明：" + llm.reason));
  }

  /* ------------------------------------------------------------------ *
   * 提交运行
   * ------------------------------------------------------------------ */
  /* POST /api/runs 在 real 模式下会**同步**跑 N0–N3（真实模型，几分钟），
     客户端 15 s 超时 ≠ 服务端没建 run。超时后按运行列表核对并接入，
     避免把"已启动"显示成"启动失败"（SPEC-04 §7.2，2026-10-23）。 */
  async function recoverRunAfterTimeout(knownIds) {
    for (var i = 0; i < 120; i++) {
      await new Promise(function (resolve) { setTimeout(resolve, 2000); });
      try {
        var body = await api("/api/runs");
        var runs = (body && body.runs) || [];
        for (var j = 0; j < runs.length; j++) {
          var id = runs[j] && runs[j].run_id;
          if (id && knownIds.indexOf(id) < 0) return id;
        }
      } catch (e) {
        /* 轮询失败继续，最终按超时报错 */
      }
    }
    return null;
  }

  async function submitSetup() {
    if (state.setup.submitting || !canStart()) return;
    state.setup.submitting = true;
    state.setup.error = null;
    var knownIds = (state.runs || []).map(function (r) { return r && r.run_id; });
    renderSetup();
    try {
      var body = {
        baseline: state.setup.baseline,
        project: state.setup.project,
        mode: state.setup.mode,
        scenario: state.setup.scenario
      };
      var now = String(state.setup.now || "").trim();
      if (now) body.now = now;
      var run = await api("/api/runs", { method: "POST", body: body }, 20000);
      if (!run || !run.run_id) throw new Error("服务端未返回 run_id");
      toast("已创建运行：" + run.run_id);
      try { await loadRuns(); } catch (eLoad) { /* 列表刷新失败不阻断进入运行视图 */ }
      await openRun(run.run_id);
    } catch (e) {
      var timedOut = /请求超时/.test(String(e && e.message));
      if (timedOut) {
        toast("启动请求超时，正在核对服务端是否已创建运行…");
        var recovered = await recoverRunAfterTimeout(knownIds);
        if (recovered) {
          state.setup.submitting = false;
          renderSetup();
          toast("运行已在服务端启动：" + recovered + "（客户端超时，已自动接入）");
          try { await loadRuns(); } catch (eLoad2) { /* 同上 */ }
          await openRun(recovered);
          return;
        }
      }
      state.setup.error = errText(e);
      toast("启动失败：" + e.message);
    } finally {
      state.setup.submitting = false;
      renderSetup();
    }
  }

  /* ------------------------------------------------------------------ *
   * 运行视图：流程 / agent / 右列
   * ------------------------------------------------------------------ */
  function renderRun() {
    var hasRun = !!state.runId;
    var emptyBox = $("runEmpty");
    var bodyBox = $("runBody");
    if (emptyBox) emptyBox.classList.toggle("hidden", hasRun);
    if (bodyBox) bodyBox.classList.toggle("hidden", !hasRun);
    if (!hasRun) {
      if (emptyBox) {
        clearEl(emptyBox);
        var empty = h("div", "empty");
        empty.appendChild(h("div", "empty-title", state.runs.length ? "从左侧选择一条运行记录" : "还没有运行记录"));
        empty.appendChild(h("div", "muted", state.runs.length
          ? "选中后可查看四段流程、agent 工作状态与闸门。"
          : "点「＋ 新建运行」配置基线版本与项目目录，确认启动闭环。"));
        if (state.runsError) empty.appendChild(h("div", "banner bad", "读取运行列表失败：" + state.runsError));
        emptyBox.appendChild(empty);
      }
      return;
    }
    var v = state.viewData;
    renderRunHead(v);
    renderRunAlerts(v);
    renderStagesInto($("stages"), v);
    renderAgents(v);
    renderGateCard(v);
    renderCounts(v);
    renderBlockers(v);
    renderJob(v);
    renderEvents(v);
  }

  /* SPEC-04 §4.5 环境来源徽标：只读投影 s0_record_id；空值不得说成"环境就绪"。 */
  function s0SourceChip(v) {
    var raw = v ? v.s0_record_id : null;
    var hasRecord = raw !== null && raw !== undefined && String(raw) !== "";
    var drill = !!(v && v.mode === "drill");
    var chip = h("span", "chip s0-source" + (hasRecord ? " mono" : " warn"),
      hasRecord ? "S0 记录 " + String(raw) : (drill ? "未经 S0 派生（drill 不覆盖 S0）" : "未经 S0 派生"));
    chip.title = hasRecord
      ? "运行文档 s0_record_id=" + String(raw) + "：输入目录来自 S0 派生副本；徽标只是只读投影，不证明环境已就绪。"
      : "运行文档 s0_record_id 为空：本运行未从 S0 派生副本启动；drill 不覆盖 S0，也不代表环境就绪。";
    return chip;
  }

  function renderRunHead(v) {
    var host = $("runHead");
    if (!host) return;
    clearEl(host);
    host.appendChild(h("span", "rid mono", state.runId));
    if (!v) {
      var d = deriveView();
      var pill = h("span", "status-pill " + (d.kind === "first_error" ? "fail" : "run"), d.headStatusText);
      if (state.viewError) pill.title = "读取运行视图失败：" + state.viewError;
      host.appendChild(pill);
      return;
    }
    var pill = h("span", "status-pill " + statusKind(v.status));
    if (v.status === "running") pill.appendChild(h("span", "spinner"));
    if (v.status === "waiting_gate" || v.status === "waiting_job" || v.status === "waiting_slot") {
      pill.appendChild(h("span", "pulse"));
    }
    pill.appendChild(document.createTextNode(" " + statusLabel(v.status) + (v.current_node ? " · " + v.current_node : "")));
    if (v.status === "waiting_gate") {
      pill.title = "执行停在人工闸门（durable interrupt）：可安全重启，闸门态权威在 gates.json。";
    } else if (v.status === "waiting_job") {
      pill.title = "执行停在外部长任务（JOB 中断）：作业在跑，图已停放，可安全重启后重新附着。";
    } else if (v.status === "waiting_slot") {
      pill.title = "执行停在单槽排队（SLOT 中断）：队首释放后会被唤醒（审计 C2/B2 已修）。";
    }
    host.appendChild(pill);
    host.appendChild(h("span", "chip", v.mode || "—"));
    host.appendChild(s0SourceChip(v));
    if (v.baseline) host.appendChild(h("span", "chip", "基线 " + v.baseline));
    if (v.project) {
      var projectChip = h("span", "chip mono", shortPath(v.project));
      projectChip.title = v.project;
      host.appendChild(projectChip);
    }
    host.appendChild(h("span", "run-meta", "已用 " + elapsedText(v) + " · 更新于 " + relTime(v.updated_at)));
    host.appendChild(h("span", "spacer"));

    var refresh = h("button", "btn btn-sm", "刷新");
    refresh.type = "button";
    refresh.addEventListener("click", async function () {
      refresh.disabled = true;
      await poll();
      refresh.disabled = false;
    });
    host.appendChild(refresh);

    var job = v.job;
    var activeJob = !!(job && job.phase === "running");
    var cancel = h("button", "btn btn-sm", "取消作业");
    cancel.type = "button";
    cancel.disabled = !activeJob;
    cancel.title = activeJob
      ? "POST /api/runs/" + state.runId + "/jobs/" + job.job_id + "/cancel"
      : "当前没有活动作业（running）";
    cancel.addEventListener("click", function () {
      if (cancel.disabled) return;
      cancelJob(job, cancel, refresh);
    });
    host.appendChild(cancel);
  }

  async function cancelJob(job, cancelBtn, refreshBtn) {
    if (!job || !job.job_id) return;
    /* 取消是**终态**（等价失败分支）：服务端 N9/N15 读到 phase=cancelled 就按失败收敛，没有续跑入口。
       所以确认框必须**先说后果**，不能只说"确认取消？"（对齐 AI_WORK_PANEL_SPEC U08 的"终止前显示影响"；
       口径见 LOOP_ORCHESTRATION_SPEC §6 第 9 条 / WEB_UI_SPEC §4.1）。 */
    var ok = true;
    try {
      ok = window.confirm(
        "确认取消作业 " + job.job_id + "？\n\n" +
        "取消后本轮按失败收敛、不能续跑；要重跑需要新建一轮。");
    } catch (e) { ok = true; }
    if (!ok) return;
    if (cancelBtn) cancelBtn.disabled = true;
    if (refreshBtn) refreshBtn.disabled = true;
    try {
      await api("/api/runs/" + enc(state.runId) + "/jobs/" + enc(job.job_id) + "/cancel", { method: "POST" });
      toast("已请求取消作业 " + job.job_id + "（本轮将按失败收敛）");
      await poll();
    } catch (e) {
      toast("取消失败：" + e.message);
    } finally {
      if (refreshBtn) refreshBtn.disabled = false;
    }
  }

  /* F13：手动重新读取当前运行详情（只发详情 GET，不重建闸门表单、不清草稿）。 */
  async function retryView() {
    if (!state.runId) return;
    try {
      await fetchRunView();
    } catch (e) {
      /* 错误由 deriveView() 统一展示；这里不吞成成功。 */
    }
    renderLive();
  }

  /* 首次/陈旧失败共用的「重新读取」入口：只发详情 GET，点击即禁用防重复。 */
  function retryButton() {
    var d = deriveView();
    var retry = h("button", "btn btn-sm", d.stale ? "重新读取（数据可能已过期）" : "重新读取");
    retry.type = "button";
    retry.disabled = !!state.viewRequesting;
    retry.addEventListener("click", function () {
      if (retry.disabled) return;
      retry.disabled = true;
      retryView();
    });
    return retry;
  }

  function renderRunAlerts(v) {
    var host = $("runAlerts");
    if (!host) return;
    clearEl(host);
    var d = deriveView();
    if (d.alertText) {
      var failBox = h("div", "alert bad");
      failBox.appendChild(document.createTextNode(d.alertText));
      if (d.showRetry) {
        var retry = retryButton();
        retry.id = "runRetry";
        failBox.appendChild(document.createTextNode(" "));
        failBox.appendChild(retry);
      }
      host.appendChild(failBox);
    }
    if (!v) return;
    if (v.error) {
      var box = h("div", "alert bad");
      box.appendChild(h("b", null, "运行失败："));
      box.appendChild(document.createTextNode(String(v.error)));
      host.appendChild(box);
    } else if (v.status === "failed") {
      host.appendChild(h("div", "alert warn", "status=failed 但服务端未给出 error —— 这是缺口，不得只显示「失败」。"));
    }
    if (v.notes && v.notes.length) {
      var det = h("details", "adv");
      det.appendChild(h("summary", null, "运行备注（notes · " + v.notes.length + " 条）"));
      var ul = h("ul", "tiny");
      ul.style.margin = "6px 0 0";
      ul.style.paddingLeft = "18px";
      v.notes.forEach(function (n) { ul.appendChild(h("li", null, String(n))); });
      det.appendChild(ul);
      host.appendChild(det);
    }
  }

  /* ---------------- 四段流程 ---------------- */
  function stageList(v) {
    if (v && Array.isArray(v.stage_map) && v.stage_map.length) return v.stage_map;
    return STAGE_FALLBACK;
  }

  /* 待处理中断的统一投影。两种类型必须分开（2026-10-23）：
   *   gate_decision → 有待决策闸门（gate 有值，可提交）；
   *   job_done      → 在等外部长任务（gate 为空、node=作业节点，**不是闸门**）。
   * 早先把 job_done 的 id 前缀 `JOB` 当成 gate，导致「人工闸门」渲染出一个
   * 「服务端未下发决策选项 ⇒ 不可提交」的假表单。gate 只认 payload.gate。 */
  function pendingInfo(v) {
    var raw = v && v.pending_interrupt;
    if (!raw || typeof raw !== "object") return null;
    var payload = raw.payload && typeof raw.payload === "object" ? raw.payload : {};
    var kind = raw.type === "job_done" ? "job" : (raw.type === "gate_decision" ? "gate" : "");
    var gate = payload.gate ? String(payload.gate) : "";
    var node = payload.gate_node || (gate ? nodeOfGate(gate) : "") || payload.node || "";
    if (!gate && !node && !kind) return null;
    if (kind === "gate" && !gate) return null;
    return {
      raw: raw,
      kind: kind || (gate ? "gate" : "job"),
      gate: gate,
      node: node ? String(node) : "",
      payload: payload,
      cycle: payload.cycle !== undefined && payload.cycle !== null ? payload.cycle : null,
      id: raw.id || null
    };
  }

  function nodeOfGate(gate) {
    var meta = GATE_TITLES[gate];
    return meta && meta.node ? meta.node : "";
  }

  function gateTitle(gate) {
    var meta = GATE_TITLES[gate];
    return meta ? meta.label : "闸门 · " + gate;
  }

  function historyOf(v, node) {
    var arr = (v && v.node_history) || [];
    for (var i = 0; i < arr.length; i++) {
      if (arr[i] && arr[i].node === node) return arr[i];
    }
    return null;
  }

  function agentForNode(v, node) {
    var arr = (v && v.agents) || [];
    for (var i = 0; i < arr.length; i++) {
      var a = arr[i];
      if (a && Array.isArray(a.nodes) && a.nodes.indexOf(node) >= 0) return a;
    }
    return null;
  }

  function nodeState(v, node) {
    var pending = pendingInfo(v);
    if (pending && pending.node === node) return "wait";
    var row = historyOf(v, node);
    if (row) {
      if (row.kind === "node_failed" || row.status === "failed" ||
        row.status === "escalated" || row.status === "halted") return "fail";
      if (row.kind === "node_started") return "active";
    }
    var agent = agentForNode(v, node);
    if (agent) {
      if (agent.status === "failed") return "fail";
      if (agent.status === "working") return "active";
      if (agent.status === "waiting") return "wait";
      if (agent.status === "done") return "done";
    }
    if (row && row.kind === "node_finished") return "done";
    if (v && v.job && v.job.phase === "running" && node === "N9") return "active";
    return "";
  }

  function nodeIcon(st) {
    if (st === "done") return "✓";
    if (st === "wait") return "!";
    if (st === "active") return "…";
    if (st === "fail") return "✕";
    return "";
  }

  function stageAgg(stage, v) {
    var nodes = (stage && stage.nodes) || [];
    var done = 0;
    var fail = false;
    var wait = false;
    var active = false;
    nodes.forEach(function (node) {
      var st = nodeState(v, node);
      if (st === "done") done += 1;
      if (st === "fail") fail = true;
      if (st === "wait") wait = true;
      if (st === "active") active = true;
    });
    var total = nodes.length || 1;
    if (fail) return { cls: "fail", label: "失败", done: done, total: total };
    if (wait) return { cls: "wait", label: "等待人工", done: done, total: total };
    if (nodes.length && done === nodes.length) return { cls: "done", label: "完成", done: done, total: total };
    if (active) return { cls: "active", label: "进行中", done: done, total: total };
    if (done) return { cls: "", label: done + "/" + nodes.length, done: done, total: total };
    return { cls: "", label: "待开始", done: done, total: total };
  }

  function stageRange(stage) {
    var nodes = (stage && stage.nodes) || [];
    if (!nodes.length) return "";
    if (nodes.length === 1) return nodes[0];
    return nodes[0] + "–" + nodes[nodes.length - 1];
  }

  function stageOfNode(stages, node) {
    for (var i = 0; i < stages.length; i++) {
      if ((stages[i].nodes || []).indexOf(node) >= 0) return stages[i].key;
    }
    return null;
  }

  function latestNode(v) {
    var arr = (v && v.events) || [];
    for (var i = arr.length - 1; i >= 0; i--) {
      var e = arr[i];
      if (e && e.node && (e.kind === "node_started" || e.kind === "node_finished" || e.kind === "node_failed")) {
        return e.node;
      }
    }
    return null;
  }

  function autoStageKey(v) {
    var stages = stageList(v);
    if (!stages.length) return null;
    var pending = pendingInfo(v);
    if (pending && pending.node) {
      var byGate = stageOfNode(stages, pending.node);
      if (byGate) return byGate;
    }
    var current = (v && v.current_node) || latestNode(v);
    if (current) {
      var byNode = stageOfNode(stages, current);
      if (byNode) return byNode;
    }
    for (var i = 0; i < stages.length; i++) {
      if (stageAgg(stages[i], v).cls !== "done") return stages[i].key;
    }
    return stages[stages.length - 1].key;
  }

  function effectiveOpenStage(v) {
    if (state.stageOverride === null) return null;
    if (typeof state.stageOverride === "string" && state.stageOverride !== "auto") {
      var stages = stageList(v);
      var found = false;
      for (var i = 0; i < stages.length; i++) {
        if (stages[i].key === state.stageOverride) { found = true; break; }
      }
      if (found) return state.stageOverride;
    }
    return autoStageKey(v);
  }

  function toggleStage(key) {
    var open = effectiveOpenStage(state.viewData);
    state.stageOverride = open === key ? null : key;
    renderStagesInto($("stages"), state.viewData);
    renderStagesInto($("stagesGate"), state.viewData);
  }

  function renderStagesInto(host, v) {
    if (!host) return;
    clearEl(host);
    var stages = stageList(v);
    var open = effectiveOpenStage(v);
    stages.forEach(function (stage, idx) {
      host.appendChild(stageEl(stage, idx, open, v));
    });
    var known = {};
    stages.forEach(function (stage) {
      (stage.nodes || []).forEach(function (n) { known[n] = true; });
    });
    var extra = [];
    ((v && v.node_history) || []).forEach(function (row) {
      if (row && row.node && !known[row.node] && extra.indexOf(row.node) < 0) extra.push(row.node);
    });
    if (extra.length) {
      var box = h("div", "unknown-nodes");
      box.appendChild(h("div", "tiny warn", "未纳入四段展示的节点（按 node_history 显式列出，不隐藏；全部可点）："));
      var chips = h("div", "chips");
      extra.forEach(function (n) {
        var chip = h("button", "chip warn chip-btn", n);
        chip.type = "button";
        chip.setAttribute("data-node-chip", n);
        chip.setAttribute("aria-haspopup", "dialog");
        chip.setAttribute("aria-label", "节点 " + n + "（四段外/未知节点）；打开执行详情");
        chip.title = "查看节点 " + n + " 执行详情（只读投影）";
        chip.addEventListener("click", function () { openNodeDetail(n, null, chip); });
        chips.appendChild(chip);
      });
      box.appendChild(chips);
      host.appendChild(box);
    }
  }

  function stageEl(stage, idx, openKey, v) {
    var agg = stageAgg(stage, v);
    var open = openKey === stage.key;
    var wrap = h("div", "stage " + agg.cls + (open ? " open" : ""));
    var head = h("button", "stage-head");
    head.type = "button";
    head.setAttribute("aria-expanded", open ? "true" : "false");
    head.appendChild(h("div", "stage-idx", agg.cls === "done" ? "✓" : String(idx + 1)));
    var titleBox = h("div");
    titleBox.appendChild(h("div", "stage-name", stage.name || stage.key || "段"));
    titleBox.appendChild(h("div", "stage-range", stageRange(stage)));
    head.appendChild(titleBox);
    var sum = h("div", "stage-sum");
    var bar = h("span", "stage-bar");
    var fill = h("i");
    fill.style.width = Math.round((agg.done / Math.max(1, agg.total)) * 100) + "%";
    bar.appendChild(fill);
    sum.appendChild(bar);
    sum.appendChild(h("span", null, agg.label));
    sum.appendChild(h("span", "stage-chev", "▸"));
    head.appendChild(sum);
    head.addEventListener("click", function () { toggleStage(stage.key); });
    wrap.appendChild(head);

    var body = h("div", "stage-body");
    var nodes = h("div", "snodes");
    (stage.nodes || []).forEach(function (nodeId) { nodes.appendChild(nodeEl(nodeId, v)); });
    body.appendChild(nodes);
    wrap.appendChild(body);
    return wrap;
  }

  function nodeEl(nodeId, v) {
    var st = nodeState(v, nodeId);
    var meta = NODE_META[nodeId] || { name: "未知节点", owner: "—" };
    /* 全节点可点（SPEC-04 §4.2.1）：用原生 button，Enter/Space 天然可达；
     * 弹层独立于 #stages，1.5 s 全量重建不会清掉面板。 */
    var wrap = h("button", "snode" + (meta.gate ? " gate" : "") + (st ? " " + st : ""));
    wrap.type = "button";
    wrap.setAttribute("data-node-chip", nodeId);
    wrap.setAttribute("aria-haspopup", "dialog");
    wrap.setAttribute("aria-label", "节点 " + nodeId + " " + (meta.name || "") +
      "，owner " + (meta.owner || "—") + "，状态 " + (st || "待开始") + "；打开任务详情");
    var bubble = h("div", "sb");
    bubble.appendChild(h("span", null, nodeIcon(st)));
    var txt = h("div", "st");
    txt.appendChild(h("b", null, nodeId + " " + (meta.name || "")));
    txt.appendChild(h("span", "own", meta.owner || "—"));
    wrap.appendChild(bubble);
    wrap.appendChild(txt);
    wrap.title = nodeId + " " + (meta.name || "") + " · owner=" + (meta.owner || "—") +
      " · 状态=" + (st || "待开始") + " · 点击查看节点执行详情";
    wrap.addEventListener("click", function () { openNodeDetail(nodeId, meta, wrap); });
    return wrap;
  }

  /* 打开节点详情弹层：身份兜底名/owner 仅用于显示，服务端下发优先（节点面板内标注）。 */
  function openNodeDetail(nodeId, meta, trigger, forceDetails) {
    if (!state.runId) {
      toast("尚未选择运行");
      return;
    }
    if (!window.NodeDetail) {
      toast("节点详情模块未加载（node-detail.js）");
      return;
    }
    var agent = null;
    AGENT_DEFS.forEach(function (def) {
      if (!agent && (def.nodes || []).indexOf(nodeId) >= 0) {
        agent = { name: def.name, nodes: (def.nodes || []).slice(), node: nodeId };
      }
    });
    if (agent && !forceDetails && window.AgentWindow) {
      openAgentPanel(state.runId, agent.name, agent.nodes, nodeId, trigger);
      return;
    }
    window.NodeDetail.open({
      runId: state.runId,
      node: nodeId,
      fallback: meta ? { name: meta.name, owner: meta.owner } : null,
      agent: agent,
      onAgent: agent ? function () { openAgentPanel(state.runId, agent.name, agent.nodes, nodeId, trigger); } : null,
      gate: !!(meta && meta.gate),
      onGate: function () { showView("gate"); },
      trigger: trigger || null
    });
  }

  function openAgentPanel(runId, name, nodes, node, trigger) {
    if (!window.AgentWindow || !runId) return;
    window.AgentWindow.open({runId: runId, name: name, nodes: nodes, node: node, trigger: trigger,
      onDetails: function (selected) {
        if (state.runId !== runId) return;
        var chip = Array.from(document.querySelectorAll("[data-node-chip]")).find(function (item) { return item.dataset.nodeChip === selected; });
        openNodeDetail(selected, NODE_META[selected], chip || trigger, true);
      }});
  }

  /* ---------------- Agent 卡 ---------------- */
  function renderAgents(v) {
    var host = $("agents");
    if (!host) return;
    clearEl(host);
    if (!v) {
      host.appendChild(h("div", "muted tiny", panelHint()));
      return;
    }
    var serverAgents = v && Array.isArray(v.agents) ? v.agents : null;
    var byRole = {};
    (serverAgents || []).forEach(function (a) {
      if (!a) return;
      var key = a.role || a.name;
      if (key) byRole[key] = a;
    });
    AGENT_DEFS.forEach(function (def) {
      host.appendChild(agentCard(def, byRole[def.role] || null, v, !serverAgents));
    });
    (serverAgents || []).forEach(function (a) {
      if (!a) return;
      var matched = false;
      for (var i = 0; i < AGENT_DEFS.length; i++) {
        if (AGENT_DEFS[i].role === a.role || AGENT_DEFS[i].name === a.name) { matched = true; break; }
      }
      if (matched) return;
      host.appendChild(agentCard({
        role: a.role || a.name || "role",
        name: a.name || a.role || "角色",
        nodes: a.nodes || [],
        desc: "服务端下发角色",
        avatar: "•",
        cls: "a6"
      }, a, v, false));
    });
    renderHostRow(v, !serverAgents);
  }

  function statusChip(status, elapsed) {
    var cls = status === "done" ? "ok"
      : status === "working" ? "primary"
        : status === "waiting" ? "warn"
          : status === "failed" ? "bad" : "";
    var label = { idle: "待命", working: "工作中", paused: "已暂停", interrupting: "干预处理中", waiting: "等待", done: "完成", failed: "失败" }[status] || status || "待命";
    var text = label + (elapsed !== null && elapsed !== undefined ? " · " + elapsed + " s" : "");
    return h("span", "chip" + (cls ? " " + cls : ""), text);
  }

  function agentCard(def, a, v, derived) {
    var status = a ? (a.status || "idle") : deriveAgentStatus(def, v);
    if (a && a.live_control && ["paused", "interrupting"].indexOf(a.live_control.state) >= 0) status = a.live_control.state;
    var card = h("div", "agent " + (status === "working" ? "working" : status === "waiting" ? "waiting" : status === "failed" ? "failed" : ""));
    var head = h("div", "agent-head");
    head.appendChild(h("div", "avatar " + (def.cls || "a6"), def.avatar || "•"));
    var nameBox = h("div");
    var name = a && a.name ? a.name : def.name;
    var open = h("button", "agent-name agent-open", name + " ↗");
    open.type = "button";
    open.setAttribute("data-agent-node", (def.nodes || [])[0] || "");
    open.setAttribute("aria-label", "打开 " + name + " 工作窗口");
    nameBox.appendChild(open);
    var nodes = a && Array.isArray(a.nodes) && a.nodes.length ? a.nodes : (def.nodes || []);
    var runId = state.runId;
    function openWindow() {
      openAgentPanel(runId, name, nodes,
        a && a.active_node && nodes.indexOf(a.active_node) >= 0 ? a.active_node : nodes[0], open);
    }
    open.addEventListener("click", openWindow);
    card.classList.add("agent-clickable");
    card.addEventListener("click", function (event) {
      if (!event.target.closest("button, a, input, textarea, select")) openWindow();
    });
    nameBox.appendChild(h("div", "agent-role", nodes.join(" / ") + " · " + (def.desc || "")));
    head.appendChild(nameBox);
    head.appendChild(h("div", "spacer"));
    head.appendChild(statusChip(status, a ? a.elapsed_s : deriveAgentElapsed(def, v)));
    card.appendChild(head);

    var body = h("div", "agent-body");
    var lastAction = a ? (a.last_action || "—") : deriveLastAction(def, v);
    if (status === "working") {
      var line = h("div");
      line.appendChild(h("span", "spinner"));
      line.appendChild(document.createTextNode(" "));
      line.appendChild(h("b", null, lastAction));
      body.appendChild(line);
    } else {
      body.appendChild(h("div", "agent-action", lastAction));
    }
    var summary = a ? a.summary : "—";
    body.appendChild(h("div", null, summary ? "摘要：" + summary : "摘要：产物未生成"));
    var note = a ? a.note : deriveNote(def, status);
    if (note) body.appendChild(h("div", "agent-note", String(note)));
    /* S4（SPEC-REV-16 §2/§3）：角色卡与窗口读同一份服务端 `progress` 投影；
     * 无进展只告警不收敛，文案里不出现"在等人工/等待人工"类措辞（§3.3）。 */
    var progress = a && a.progress ? a.progress : null;
    var progressLine = window.S4View ? window.S4View.cardLine(progress) : "";
    if (progressLine) {
      var stalled = !!(progress && progress.no_progress && progress.no_progress.state === "warn");
      body.appendChild(h("div", "agent-note" + (stalled ? " bad" : ""), progressLine));
    }
    var facts = window.Capabilities ? window.Capabilities.line(a && a.capabilities) : "";
    if (facts) body.appendChild(h("div", "agent-note", facts));
    card.appendChild(body);

    var foot = h("div", "agent-foot");
    foot.appendChild(h("span", null, "模式 " + (a ? (a.mode || "—") : deriveMode(def, v))));
    var evidence = a && Array.isArray(a.evidence) ? a.evidence : [];
    if (evidence.length) {
      evidence.forEach(function (ref) {
        var btn = h("button", "linkbtn", "证据：" + shortRef(ref));
        btn.type = "button";
        btn.title = "GET /api/runs/" + state.runId + "/evidence/exists?ref=" + String(ref);
        btn.addEventListener("click", function () { probeEvidence(ref, btn); });
        foot.appendChild(btn);
      });
    } else {
      foot.appendChild(h("span", null, "无证据入口"));
    }
    foot.appendChild(h("span", null, "投影，非权威"));
    card.appendChild(foot);
    return card;
  }

  async function probeEvidence(ref, btn) {
    if (!state.runId) return;
    if (btn) btn.disabled = true;
    try {
      var body = await api("/api/runs/" + enc(state.runId) + "/evidence/exists?ref=" + enc(ref));
      if (body.exists === true) {
        var extra = "";
        if (body.bytes !== undefined && body.bytes !== null) extra = " · " + body.bytes + " B";
        if (body.entries !== undefined && body.entries !== null) extra = " · 目录 " + body.entries + " 项";
        toast("证据存在：" + (body.path || ref) + extra);
      } else if (body.exists === null) {
        toast("提示：" + (body.note || "不按文件路径探测") + "：" + (body.path || ref));
      } else {
        toast("证据缺失（E-2）：" + (body.path || ref) + " — " + (body.note || "文件不存在"));
      }
    } catch (e) {
      toast("探测证据失败：" + e.message);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function deriveAgentEvents(def, v) {
    var nodes = (def && def.nodes) || [];
    var out = [];
    ((v && v.events) || []).forEach(function (e) {
      if (!e || nodes.indexOf(e.node) < 0) return;
      if (e.kind === "node_started" || e.kind === "node_finished" || e.kind === "node_failed") out.push(e);
    });
    return out;
  }

  function deriveAgentStatus(def, v) {
    var evs = deriveAgentEvents(def, v);
    if (!evs.length) return "idle";
    var pending = pendingInfo(v);
    if (pending && (def.nodes || []).indexOf(pending.node) >= 0) return "waiting";
    var failed = false;
    evs.forEach(function (e) {
      if (e.kind === "node_failed" || e.status === "failed" || e.status === "escalated" || e.status === "halted") failed = true;
    });
    if (failed) return "failed";
    var last = evs[evs.length - 1];
    if (last.kind === "node_started") return "working";
    return "done";
  }

  function deriveAgentElapsed(def, v) {
    var evs = deriveAgentEvents(def, v);
    if (!evs.length) return null;
    var start = null;
    var end = null;
    evs.forEach(function (e) {
      if (e.kind === "node_started" && start === null) start = e.ts;
      if (e.kind === "node_finished" || e.kind === "node_failed") end = e.ts;
    });
    if (start === null) return null;
    if (end === null) return Math.max(0, Math.round(Date.now() / 1000 - Number(start)));
    return Math.max(0, Math.round(Number(end) - Number(start)));
  }

  function deriveLastAction(def, v) {
    var evs = deriveAgentEvents(def, v);
    if (!evs.length) return "—";
    var e = evs[evs.length - 1];
    return (e.kind || "?") + "(" + (e.status || "?") + ")";
  }

  function deriveMode(def, v) {
    var mode = "—";
    deriveAgentEvents(def, v).forEach(function (e) {
      var detail = e.detail || {};
      if (detail.mode) mode = String(detail.mode);
      else if (detail.model) mode = String(detail.model);
    });
    return mode;
  }

  function deriveNote(def, status) {
    // 能力事实一律以服务端 capabilities 为准（Spec §4.3 F02）；本地派生卡不得断言
    // 「未实现」或其它能力结论，idle 也不等于未实现。
    return "该角色未出现在服务端 agents 投影中：本卡由 event / node_history 本地派生（非权威），能力事实未知。";
  }

  function renderHostRow(v, derived) {
    var host = $("hostRow");
    if (!host) return;
    clearEl(host);
    host.appendChild(h("span", "dot idle"));
    var box = h("div");
    box.appendChild(h("b", null, "Host 确定性侧"));
    box.appendChild(document.createTextNode(" N0 / N1 / N2 / N5 / N7 / N9 / N15 / N16 · 确定性步骤 / 长任务看护（不占 agent 卡）"));
    box.appendChild(h("div", "tiny", "N9 全跑由 job_runner 看护：提交 → 停放 → 完成事件 resume"));
    var job = v && v.job;
    if (job) {
      var line = h("div", "tiny");
      line.style.marginTop = "4px";
      line.appendChild(h("span", "chip", "作业 " + (job.job_id || "—") + " · " + (job.phase || "—")));
      if (job.elapsed_s !== undefined && job.elapsed_s !== null) {
        line.appendChild(h("span", "chip", "已用 " + fmtDuration(job.elapsed_s)));
      }
      box.appendChild(line);
    }
    if (derived) {
      box.appendChild(h("div", "tiny warn", "服务端 agents 投影未就绪：上方 agent 卡由 event / node_history 本地派生（非权威）。"));
    }
    host.appendChild(box);
  }

  /* ---------------- 右列 ---------------- */
  function renderGateCard(v) {
    var card = $("gateCard");
    var body = $("gateCardBody");
    if (!card || !body) return;
    var pending = pendingInfo(v);
    if (!pending || pending.kind !== "gate" || !pending.gate) {
      card.classList.add("hidden");
      clearEl(body);
      body.removeAttribute("data-gate-key");
      return;
    }
    card.classList.remove("hidden");
    setText("gateCardTitle", gateTitle(pending.gate));
    setText("gateCardSub", "等待人工" + (pending.cycle !== null ? " · 轮次 " + pending.cycle : ""));
    ensureGateForm(body, pending, true);
    updateGateForm(body, pending);
  }

  function renderCounts(v) {
    var host = $("countsBody");
    if (!host) return;
    clearEl(host);
    if (!v) {
      host.appendChild(h("div", "muted tiny", panelHint()));
      return;
    }
    var counts = v && v.counts;
    if (!counts) {
      host.appendChild(h("div", "alert warn", "无全跑证据：两套口径均无法取数（I3 / E-2）。"));
      return;
    }
    var k1 = counts.koutou1 || {};
    var k2 = counts.koutou2 || {};
    var grid = h("div", "counts");
    grid.appendChild(countBox(k1.zero ? "ok" : "bad", countValue(k1.value), k1.label || "口径一"));
    grid.appendChild(countBox(k2.zero ? "ok" : "bad", countValue(k2.value), k2.label || "口径二"));
    host.appendChild(grid);
    host.appendChild(h("div", "foot-note", "两者都归零才可判绿；两者并列同权，不换算。" + (counts.note ? " " + counts.note : "")));
  }

  function countBox(cls, value, label) {
    var box = h("div", "count-box" + (cls ? " " + cls : ""));
    box.appendChild(h("div", "n", value === undefined || value === null ? "—" : String(value)));
    box.appendChild(h("div", "l", label));
    return box;
  }

  function countValue(value) {
    if (value === null || value === undefined) return "—";
    if (typeof value === "number") return String(value);
    if (typeof value === "object") {
      var parts = [];
      Object.keys(value).forEach(function (k) { parts.push(k + "=" + String(value[k])); });
      return parts.join(" / ");
    }
    return String(value);
  }

  function renderBlockers(v) {
    var host = $("blockersBody");
    if (!host) return;
    clearEl(host);
    if (!v) {
      host.appendChild(h("div", "muted tiny", panelHint()));
      return;
    }
    var items = v && Array.isArray(v.blockers) ? v.blockers : [];
    if (!items.length) {
      host.appendChild(h("div", "muted tiny", "服务端未下发阻断项（这不等于判绿；判据仍以服务端 can 字段与 gates.json 为准）。"));
      return;
    }
    var rank = { blocker: 0, defect: 1, info: 2 };
    items.slice().sort(function (a, b) {
      var ra = rank[a && a.severity] !== undefined ? rank[a.severity] : 3;
      var rb = rank[b && b.severity] !== undefined ? rank[b.severity] : 3;
      return ra - rb;
    }).forEach(function (b) {
      if (!b) return;
      var sev = b.severity || "info";
      var row = h("div", "blocker");
      row.appendChild(h("span", "sev " + (sev === "info" ? "info" : "hard"), sev));
      var box = h("div");
      box.appendChild(h("b", null, b.code || "（无 code）"));
      box.appendChild(document.createElement("br"));
      box.appendChild(h("span", "muted tiny", (b.title ? b.title + " · " : "") + (b.message || "")));
      if (b.refs && b.refs.length) {
        box.appendChild(h("div", "refs", b.refs.slice(0, 3).map(String).join(" · ")));
      }
      row.appendChild(box);
      host.appendChild(row);
    });
  }

  function renderJob(v) {
    var host = $("jobBody");
    if (!host) return;
    clearEl(host);
    if (!v) {
      host.appendChild(h("div", "muted tiny", panelHint()));
      return;
    }
    var job = v && v.job;
    if (!job) {
      /* U9（SPEC-REV-08）：空态区分「无作业记录」与「已完成/死亡归档」——
       * 判定在 web/job-status.js（纯消费事件流），不新增判据。 */
      var jobHint = window.JobStatus ? window.JobStatus.emptyText((v && v.events) || []) : null;
      host.appendChild(h("div", "muted tiny", jobHint || "当前没有作业记录（N9 全跑尚未提交或未启动）。"));
      return;
    }
    addKV(host, "job_id", job.job_id || "—");
    addKV(host, "节点 / 用例", (job.node || "—") + " / " + (job.tc || "—"));
    addKV(host, "phase", job.phase || "—");
    addKV(host, "rc", job.rc !== undefined && job.rc !== null ? String(job.rc) : "—");
    addKV(host, "已用", job.elapsed_s !== undefined && job.elapsed_s !== null ? fmtDuration(job.elapsed_s) : "—");
    addKV(host, "ETA", job.eta_human || "—");
    if (job.note) host.appendChild(h("div", "alert warn", String(job.note)));
    var det = h("details", "adv");
    det.appendChild(h("summary", null, "日志尾部（只读 · 最多 12 行）"));
    var pre = h("pre", "log-pre");
    var tail = Array.isArray(job.log_tail) ? job.log_tail : (typeof job.log_tail === "string" ? [job.log_tail] : []);
    pre.textContent = tail.length ? tail.join("\n") : "（日志为空或不可读）";
    det.appendChild(pre);
    host.appendChild(det);
  }

  function renderEvents(v) {
    var list = $("eventList");
    if (!list) return;
    clearEl(list);
    renderEventFilter(v);
    if (!v) {
      setText("eventsSummary", "事件流 · " + panelHint());
      return;
    }
    var all = ((v && v.events) || []).filter(function (e) { return e && EVENT_WHITELIST[e.kind]; });
    var filtered = window.EventFilter
      ? window.EventFilter.applyFilter(all, state.eventFilter) : all;
    setText("eventsSummary", "事件流 · " + (filtered.length === all.length
      ? all.length + " 条白名单事件"
      : filtered.length + " / " + all.length + " 条（已按 kind 过滤）")
      + "（seq 递增 · 只读 · 折叠）");
    var shown = filtered.slice(-60).reverse();
    shown.forEach(function (e) {
      var row = h("div", "ev-row");
      row.appendChild(h("span", "k", "#" + (e.seq !== undefined && e.seq !== null ? pad(e.seq, 3) : "?")));
      row.appendChild(h("span", "n", e.node || "—"));
      row.appendChild(h("span", "d", eventText(e)));
      list.appendChild(row);
    });
  }

  /* U5：kind 过滤 chips（纯客户端；判定在 web/event-filter.js，这里只渲染与转发点击）。 */
  function renderEventFilter(v) {
    var host = $("eventFilter");
    if (!host || !window.EventFilter) return;
    clearEl(host);
    var all = ((v && v.events) || []).filter(function (e) { return e && EVENT_WHITELIST[e.kind]; });
    if (!all.length) return;
    var kinds = window.EventFilter.kindsOf(all);
    var active = state.eventFilter;
    var allChip = h("button", "chip ev-chip" + (active ? "" : " on"), "全部");
    allChip.type = "button";
    allChip.addEventListener("click", function () {
      state.eventFilter = null;
      renderEvents(v);
    });
    host.appendChild(allChip);
    kinds.forEach(function (kind) {
      var on = !!active && active.indexOf(kind) >= 0;
      var chip = h("button", "chip ev-chip" + (on ? " on" : ""), kind);
      chip.type = "button";
      chip.addEventListener("click", function () {
        state.eventFilter = window.EventFilter.toggleKind(state.eventFilter, kind);
        renderEvents(v);
      });
      host.appendChild(chip);
    });
  }

  function eventText(e) {
    var parts = [e.kind || "?"];
    if (e.status) parts.push("· " + e.status);
    var detail = e.detail || {};
    var kv = [];
    EVENT_DETAIL_FIELDS.forEach(function (k) {
      if (detail[k] !== undefined && detail[k] !== null && typeof detail[k] !== "object") {
        kv.push(k + "=" + String(detail[k]));
      }
    });
    if (kv.length) parts.push("· " + kv.join(" "));
    return parts.join(" ");
  }

  /* ------------------------------------------------------------------ *
   * 闸门视图 + 表单（运行视图右列与闸门视图共用同一份 draft）
   * ------------------------------------------------------------------ */
  function renderGate() {
    var v = state.viewData;
    renderGateHead(v);
    var alerts = $("gateAlerts");
    if (alerts) {
      clearEl(alerts);
      if (!state.runId) alerts.appendChild(h("div", "alert info", "尚未选择运行。请先在左侧选择一条运行记录。"));
      var alertInfo = deriveView();
      if (alertInfo.alertText) {
        var gateFail = h("div", "alert bad", alertInfo.alertText);
        if (alertInfo.showRetry) {
          var gateRetry = retryButton();
          gateRetry.id = "gateRetry";
          gateFail.appendChild(document.createTextNode(" "));
          gateFail.appendChild(gateRetry);
        }
        alerts.appendChild(gateFail);
      }
    }
    renderStagesInto($("stagesGate"), v);
    renderGateMaterial(v);
    renderGatePanel(v);
  }

  function renderGateHead(v) {
    var host = $("gateHead");
    if (!host) return;
    clearEl(host);
    if (!state.runId) {
      host.appendChild(h("span", "muted tiny", "未选择运行"));
      return;
    }
    host.appendChild(h("span", "rid mono", state.runId));
    if (!v) {
      var gateD = deriveView();
      var gatePill = h("span", "status-pill " + (gateD.kind === "first_error" ? "fail" : "run"),
        gateD.headStatusText);
      if (state.viewError) gatePill.title = "读取运行视图失败：" + state.viewError;
      host.appendChild(gatePill);
      return;
    }
    var pending = pendingInfo(v);
    var isGate = !!(pending && pending.kind === "gate" && pending.gate);
    var isJob = !!(pending && pending.kind === "job");
    var pill = h("span", "status-pill " + (pending ? "wait" : statusKind(v.status)));
    if (pending) pill.appendChild(h("span", "pulse"));
    pill.appendChild(document.createTextNode(" " + (isGate
      ? "等待人工 · " + gateTitle(pending.gate)
      : (isJob ? "等待外部作业 · " + (pending.node || "长任务") : statusLabel(v.status)))));
    host.appendChild(pill);
    host.appendChild(h("span", "chip", v.mode || "—"));
    host.appendChild(s0SourceChip(v));
    if (v.baseline) host.appendChild(h("span", "chip", "基线 " + v.baseline));
    if (v.project) {
      var projectChip = h("span", "chip mono", shortPath(v.project));
      projectChip.title = v.project;
      host.appendChild(projectChip);
    }
    host.appendChild(h("span", "run-meta", pending
      ? "执行处于 interrupt，可安全重启；闸门态权威在 gates.json"
      : "当前没有待决策闸门"));
    host.appendChild(h("span", "spacer"));
    var detail = h("button", "btn btn-sm", "查看执行详情");
    detail.type = "button";
    detail.addEventListener("click", function () { showView("run"); });
    host.appendChild(detail);
    var refresh = h("button", "btn btn-sm", "刷新");
    refresh.type = "button";
    refresh.addEventListener("click", async function () {
      refresh.disabled = true;
      await poll();
      refresh.disabled = false;
    });
    host.appendChild(refresh);
  }

  /* ------------------------------------------------------------------ *
   * N2 差异清单（G1 逐条核对材料；投影字段：difference_items）
   * 只渲染服务端字段，不判定；未决条目单独标色，避免"空口确认"。
   * ------------------------------------------------------------------ */
  function diffPayloadOf(pending) {
    var m = pending && pending.payload ? pending.payload : {};
    var d = m.difference_items;
    return d && typeof d === "object" ? d : null;
  }

  function diffSummaryText(pending) {
    var d = diffPayloadOf(pending);
    if (!d) return "N2 差异清单（服务端未下发）";
    var n = d.count !== undefined && d.count !== null
      ? d.count : (Array.isArray(d.entries) ? d.entries.length : 0);
    var u = d.unresolved_count !== undefined && d.unresolved_count !== null
      ? d.unresolved_count
      : (Array.isArray(d.unresolved_ids) ? d.unresolved_ids.length : 0);
    return "N2 差异清单 · " + n + " 条" + (u ? " · 未决 " + u + " 条" : " · 无未决");
  }

  /* ---------------- G1 材料可判（SPEC-04 §4.4/§5；SPEC-REV-01 R2） ----------------
   * 每条差异：before/after 双栏 + diff_hunk 行级（标行号）+ 无 hunk 原因 + encoding 标注；
   * doc_entry 先列变化字段（其余字段折叠，不隐藏）；drill 夹具带徽标；
   * 材料区另给 n3_digest / Host 留痕入口（只做存在性探测，不打开正文）。
   * 本段只做展示对照，不判定、不排序、不隐藏服务端条目。
   * ------------------------------------------------------------------------ */
  function isMissingValue(v) { return v === null || v === undefined; }

  function displayValue(v) {
    if (isMissingValue(v)) return null;
    if (typeof v === "string") return v;
    if (typeof v === "number" || typeof v === "boolean") return String(v);
    try { return JSON.stringify(v, null, 2); } catch (e) { return String(v); }
  }

  function sameValue(a, b) {
    try { return JSON.stringify(a) === JSON.stringify(b); } catch (e) { return String(a) === String(b); }
  }

  function isPlainObject(v) {
    return !!v && typeof v === "object" && !Array.isArray(v);
  }

  function entryEncoding(e) {
    if (typeof e.encoding === "string" && e.encoding) return e.encoding;
    if (e.encoding && typeof e.encoding === "object") {
      return String(e.encoding.name || e.encoding.codec || "") || null;
    }
    return null;
  }

  function hunkTextOf(hunk) {
    if (typeof hunk === "string") return hunk.trim() ? hunk : "";
    if (Array.isArray(hunk)) return hunk.length ? hunk.join("\n") : "";
    if (hunk && typeof hunk === "object") {
      if (typeof hunk.text === "string" && hunk.text.trim()) return hunk.text;
      if (Array.isArray(hunk.lines) && hunk.lines.length) return hunk.lines.join("\n");
    }
    return "";
  }

  function diffPane(kind, label, value) {
    var box = h("div", "diff-pane " + kind);
    var head = h("div", "diff-pane-head");
    head.appendChild(h("span", null, label));
    var text = displayValue(value);
    if (text === null) head.appendChild(chipEl("未下发", "warn"));
    box.appendChild(head);
    if (text === null) {
      box.appendChild(h("div", "diff-missing", "服务端未下发该字段；界面不补默认值。"));
    } else {
      var pre = h("pre", "diff-text");
      pre.textContent = text;
      box.appendChild(pre);
    }
    return box;
  }

  /* doc_entry 变化字段：优先服务端 changed_fields；否则按 before/after 对照（展示用途）。 */
  function diffFieldRows(e) {
    if (!isPlainObject(e.before) || !isPlainObject(e.after)) return null;
    var changed = [];
    var serverSupplied = Array.isArray(e.changed_fields);
    if (serverSupplied) {
      e.changed_fields.forEach(function (item) {
        var key = typeof item === "string" ? item : (item && (item.field || item.key));
        if (key && changed.indexOf(key) < 0) changed.push(String(key));
      });
    }
    var all = [];
    Object.keys(e.before).concat(Object.keys(e.after)).forEach(function (key) {
      if (all.indexOf(key) < 0) all.push(key);
    });
    if (!serverSupplied) {
      changed = all.filter(function (key) { return !sameValue(e.before[key], e.after[key]); });
    }
    var unchanged = all.filter(function (key) { return changed.indexOf(key) < 0; });
    return { changed: changed, unchanged: unchanged, serverSupplied: serverSupplied };
  }

  function fieldTable(keys, e) {
    var table = h("table", "diff-fields");
    var thead = h("thead");
    var hr = h("tr");
    ["字段", "变更前 before", "变更后 after"].forEach(function (label) {
      hr.appendChild(h("th", null, label));
    });
    thead.appendChild(hr);
    table.appendChild(thead);
    var tbody = h("tbody");
    keys.forEach(function (key) {
      var tr = h("tr");
      tr.appendChild(h("td", "mono", key));
      ["before", "after"].forEach(function (side) {
        var value = e[side] && typeof e[side] === "object" ? e[side][key] : undefined;
        var text = displayValue(value);
        tr.appendChild(h("td", "mono" + (text === null ? " muted" : ""), text === null ? "未下发" : text));
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    return table;
  }

  function diffLineRow(kind, oldNo, newNo, text) {
    var row = h("span", "dh-row" + (kind ? " dh-" + kind : ""));
    row.appendChild(h("span", "dh-no", oldNo === null ? "" : String(oldNo)));
    row.appendChild(h("span", "dh-no", newNo === null ? "" : String(newNo)));
    row.appendChild(h("span", "dh-txt", text));
    return row;
  }

  function hunkEl(text) {
    var pre = h("pre", "diff-hunk");
    var lines = String(text).replace(/\r\n?/g, "\n").split("\n");
    if (lines.length && lines[lines.length - 1] === "") lines.pop();
    var unified = lines.some(function (line) { return /^@@\s/.test(line); });
    var oldNo = 0;
    var newNo = 0;
    lines.forEach(function (line, idx) {
      if (!unified) {
        pre.appendChild(diffLineRow("raw", null, idx + 1, line));
        return;
      }
      var header = /^@@\s*-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?/.exec(line);
      if (header) {
        oldNo = parseInt(header[1], 10);
        newNo = parseInt(header[2], 10);
        pre.appendChild(diffLineRow("hunk", null, null, line));
        return;
      }
      if (/^---\s/.test(line) || /^\+\+\+\s/.test(line)) {
        pre.appendChild(diffLineRow("meta", null, null, line));
        return;
      }
      if (line.charAt(0) === "\\") {
        pre.appendChild(diffLineRow("meta", null, null, line));
        return;
      }
      if (line.charAt(0) === "+") {
        pre.appendChild(diffLineRow("add", null, newNo, line));
        newNo++;
        return;
      }
      if (line.charAt(0) === "-") {
        pre.appendChild(diffLineRow("del", oldNo, null, line));
        oldNo++;
        return;
      }
      pre.appendChild(diffLineRow("ctx", oldNo, newNo, line));
      oldNo++;
      newNo++;
    });
    return pre;
  }

  function noHunkReason(e) {
    var explicit = e.no_hunk_reason || e.hunk_reason || e.diff_hunk_reason || e.reason;
    if (explicit) return String(explicit);
    var encoding = entryEncoding(e);
    if (encoding && !/^utf-?8$/i.test(encoding)) {
      return "源文件编码为 " + encoding + "（非 UTF-8），本轮未产出可读行级 hunk";
    }
    if (e.binary) return "源文件被视为二进制，无文本行级 hunk";
    if (e.legacy_drill_fixture) return "drill 历史夹具条目，服务端未下发行级 hunk";
    if (e.drill_fixture) return "drill 夹具条目，服务端未下发行级 hunk";
    if (e.unresolved) return "未决：" + String(e.unresolved);
    if (Array.isArray(e.lines) && e.lines.length) {
      return "服务端只下发行号证据（lines " + e.lines.join(", ") + "），未下发行级 hunk";
    }
    return "服务端未下发行级 hunk（diff_hunk 为空）";
  }

  function renderDiffEntry(e) {
    var unresolved = !!e.unresolved;
    var item = h("div", "diff-item" + (unresolved ? " unresolved" : ""));
    var line = h("div", "diff-line");
    line.appendChild(h("span", "diff-id", e.entry_id ? String(e.entry_id) : "（无 entry_id）"));
    if (e.kind) line.appendChild(h("span", "chip", String(e.kind)));
    if (e.change) line.appendChild(h("span", "chip", String(e.change)));
    if (e.drill_fixture) {
      var drillChip = chipEl("drill_fixture", "warn");
      drillChip.title = "本次运行来自 drill 夹具，不是真实环境实测";
      line.appendChild(drillChip);
    }
    if (e.legacy_drill_fixture) line.appendChild(chipEl("drill 历史夹具", ""));
    var encoding = entryEncoding(e);
    if (encoding) {
      var utf8 = /^utf-?8$/i.test(encoding);
      line.appendChild(chipEl("编码 " + encoding + (utf8 ? "" : "（解码后对比）"), utf8 ? "" : "warn"));
    }
    if (unresolved) line.appendChild(chipEl("未决", "warn"));
    item.appendChild(line);

    var meta = [];
    if (e.segment) meta.push("segment " + String(e.segment));
    if (e.offset) meta.push("offset " + String(e.offset));
    if (Array.isArray(e.lines) && e.lines.length) meta.push("lines " + e.lines.join(", "));
    if (meta.length) item.appendChild(h("div", "diff-meta", meta.join(" · ")));

    if (String(e.kind || "") === "doc_entry") {
      var rows = diffFieldRows(e);
      if (rows && rows.changed.length) {
        item.appendChild(h("div", "diff-fields-head", "变化字段（先看这里；" +
          (rows.serverSupplied ? "服务端下发 changed_fields" : "客户端对照 before/after，非权威") + "）"));
        item.appendChild(fieldTable(rows.changed, e));
        if (rows.unchanged.length) {
          var unchanged = h("details", "diff-det diff-unchanged");
          unchanged.appendChild(h("summary", null, "其余字段未变（" + rows.unchanged.length + " 项）"));
          unchanged.appendChild(fieldTable(rows.unchanged, e));
          item.appendChild(unchanged);
        }
      } else if (rows) {
        item.appendChild(h("div", "diff-meta",
          "before/after 中未发现变化字段（" + rows.unchanged.length + " 项未变；原始对照见下）。"));
      }
    }

    var pair = h("div", "diff-pair");
    pair.appendChild(diffPane("before", "变更前 before", e.before));
    pair.appendChild(diffPane("after", "变更后 after", e.after));
    item.appendChild(pair);

    var hunk = hunkTextOf(e.diff_hunk);
    if (hunk) {
      item.appendChild(h("div", "diff-hunk-head", "行级差异 diff_hunk（行号按原文件）"));
      item.appendChild(hunkEl(hunk));
    } else {
      var reasonBox = h("div", "diff-nohunk");
      reasonBox.appendChild(h("b", null, "无行级 hunk"));
      reasonBox.appendChild(document.createTextNode("：原因：" + noHunkReason(e)));
      if (isMissingValue(e.before) && isMissingValue(e.after)) {
        reasonBox.appendChild(document.createTextNode("（before/after 也未下发）"));
      }
      item.appendChild(reasonBox);
    }
    if (unresolved) {
      item.appendChild(h("div", "diff-unresolved", "未决原因：" + String(e.unresolved)));
    }
    item.appendChild(h("div", "diff-ev" + (e.evidence ? "" : " muted"),
      e.evidence ? String(e.evidence) : "（无 evidence）"));
    return item;
  }

  /* 证据入口的存在性探测：结果就地显示，不打开文件正文。 */
  async function probeInto(ref, btn, out) {
    if (!state.runId) return;
    var runId = state.runId;
    btn.disabled = true;
    if (out) {
      out.className = "nd-probe";
      out.textContent = "探测中…";
    }
    try {
      var body = await api("/api/runs/" + enc(runId) + "/evidence/exists?ref=" + enc(ref));
      if (state.runId !== runId) return;
      if (!out) return;
      if (body.exists === true) {
        var extra = "";
        if (body.bytes !== undefined && body.bytes !== null) extra = " · " + body.bytes + " B";
        if (body.entries !== undefined && body.entries !== null) extra = " · 目录 " + body.entries + " 项";
        out.className = "nd-probe ok";
        out.textContent = "存在" + extra;
      } else if (body.exists === null) {
        out.className = "nd-probe";
        out.textContent = "不按文件路径探测：" + (body.note || "服务端未返回存在性");
      } else {
        out.className = "nd-probe bad";
        out.textContent = "未生成（证据缺失 E-2）：" + (body.note || "文件不存在");
      }
    } catch (e) {
      if (!out) return;
      out.className = "nd-probe bad";
      out.textContent = "探测失败：" + errText(e);
    } finally {
      btn.disabled = false;
    }
  }

  function materialExtraRow(label, entry) {
    var row = h("div", "material-extra");
    row.appendChild(h("b", null, label));
    var info = entry;
    if (typeof entry === "string") info = { path: entry };
    var path = info && (info.path || info.file);
    if (!info) {
      row.appendChild(chipEl("未生成", "warn"));
      row.appendChild(h("span", "muted", "服务端未下发该入口"));
      return row;
    }
    if (path) {
      var mono = h("span", "mono", String(path));
      mono.title = String(path);
      row.appendChild(mono);
    } else {
      row.appendChild(h("span", "muted", "路径未下发"));
    }
    var serverExists = info.exists;
    var status = h("span", "nd-probe" + (serverExists === true ? " ok" : serverExists === false ? " bad" : ""),
      serverExists === true ? "存在" : serverExists === false ? "未生成" : "未探测");
    row.appendChild(status);
    if (path) {
      var btn = h("button", "btn btn-sm", "探测存在性");
      btn.type = "button";
      btn.title = "GET /api/runs/" + state.runId + "/evidence/exists?ref=" + String(path);
      btn.addEventListener("click", function () { probeInto(String(path), btn, status); });
      row.appendChild(btn);
    }
    return row;
  }

  function hostTraceTable(changes) {
    var wrap = h("div", "table-scroll");
    var table = h("table", "host-trace-table");
    var thead = h("thead");
    var hr = h("tr");
    ["变更", "old → new", "line_before / line_after", "rationale", "evidence"].forEach(function (label) {
      hr.appendChild(h("th", null, label));
    });
    thead.appendChild(hr);
    table.appendChild(thead);
    var tbody = h("tbody");
    changes.forEach(function (change) {
      if (!change || typeof change !== "object") return;
      var tr = h("tr");
      var idCell = h("td", "mono");
      idCell.appendChild(document.createTextNode(String(change.id || "—")));
      if (change.kind) idCell.appendChild(h("span", "chip", String(change.kind)));
      if (change.encoding) idCell.appendChild(h("span", "chip", "编码 " + String(change.encoding)));
      tr.appendChild(idCell);
      var pair = h("td", "mono");
      var oldText = isMissingValue(change.old) ? "未下发" : displayValue(change.old);
      var newValue = change.new === undefined ? change.after : change.new;
      var newText = isMissingValue(newValue) ? "未下发" : displayValue(newValue);
      pair.textContent = oldText + " → " + newText;
      tr.appendChild(pair);
      var lines = h("td", "mono", (isMissingValue(change.line_before) ? "—" : String(change.line_before)) +
        " / " + (isMissingValue(change.line_after) ? "—" : String(change.line_after)));
      tr.appendChild(lines);
      tr.appendChild(h("td", null, isMissingValue(change.rationale) ? "未下发" : String(change.rationale)));
      tr.appendChild(h("td", "mono", isMissingValue(change.evidence) ? "未下发" : String(change.evidence)));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    wrap.appendChild(table);
    return wrap;
  }

  /* 材料入口：N3 摘要 + Host 留痕（mock_change_applied.json）。 */
  function renderMaterialExtras(host, pending) {
    var payload = pending && pending.payload ? pending.payload : {};
    var extras = h("div", "material-extras");
    extras.appendChild(h("div", "diff-fields-head", "材料入口（只做存在性探测；不打开文件正文）"));
    var n3 = payload.n3_digest;
    if (!n3) {
      extras.appendChild(materialExtraRow("N3 摘要 n3_digest.md", null));
    } else {
      extras.appendChild(materialExtraRow("N3 摘要 n3_digest.md", n3));
    }
    /* P-28 + 裁决 #8：G2 是"人验收报告"，人必须能从材料区**一次点击**打开本 run 的报告全文。
     * 只读：交给公共 report-viewer.js（独立只读浮窗，GET …/report 白名单），
     * 不在闸门视图复制第二套取正文逻辑，也不新增任何写动作。 */
    var reportInfo = payload.report && payload.report.n12_report;
    if (reportInfo) {
      var reportRow = materialExtraRow(
        "N12 报告全文（只读浮窗）",
        reportInfo.report_path ? { path: String(reportInfo.report_path) } : null
      );
      var openReportBtn = h("button", "btn btn-sm", "查看报告全文");
      openReportBtn.type = "button";
      openReportBtn.title = "只读：白名单仅本 run 的 n12_report.md（SPEC-04 §6.8）";
      openReportBtn.addEventListener("click", function () {
        if (window.ReportViewer) {
          window.ReportViewer.open(state.runId, api, openReportBtn);
          return;
        }
        toast("报告浮窗模块未加载（report-viewer.js）");
      });
      reportRow.appendChild(openReportBtn);
      extras.appendChild(reportRow);
    }
    var host2 = payload.host_trace;
    if (!host2) {
      extras.appendChild(materialExtraRow("Host 留痕", null));
    } else {
      extras.appendChild(materialExtraRow("Host 留痕", host2));
      var changes = host2 && Array.isArray(host2.changes) ? host2.changes : [];
      if (changes.length) {
        extras.appendChild(h("div", "diff-fields-head", "Host 留痕 changes（old→new / 行号 / 理由 / 证据）"));
        extras.appendChild(hostTraceTable(changes));
      } else {
        extras.appendChild(h("div", "muted tiny", "Host 留痕未下发 changes。"));
      }
    }
    host.appendChild(extras);
  }

  /* ---------------- 逐条处置控件（SPEC-04 §4.4，2026-10-23 增补） ----------------
   * 每个唯一 entry_id 一组处置单选 + 本条理由；选项一律取服务端 decision_options。
   * 整门决策由逐条处置推导（gate-session.deriveEntryDecision，口径同 gates.py）；
   * 覆盖不全/取值非法由服务端 I1 最终判定，前端只做提交前提示。
   * 本段不判定、不排序、不隐藏条目。
   * ------------------------------------------------------------------------ */
  function entryDecisionsRequired(pending) {
    var p = pending && pending.payload ? pending.payload : {};
    return p.entry_decisions_required === true;
  }

  /* 「哪道门要逐条处置」的判据**唯一在服务端**（WEB_UI_SPEC §4.4「判据归属」）：
     服务端只对 G1 置 `entry_decisions_required=true`，real 严格、drill 为假。
     2026-10-26（R1+R2）：前端曾自判 `pending.gate === "G1_diff_confirm"`，结果控件渲染、
     就绪判定、紧凑卡引导、节点面板 bridge 各写一套判据，还出现"引导用户去没有控件的地方"
     的死角 —— 现已删除，只消费上面这个 flag（红线 8 口径唯一）。 */

  function entryRows(pending) {
    var d = diffPayloadOf(pending);
    var entries = d && Array.isArray(d.entries) ? d.entries : [];
    var order = [];
    var byId = {};
    entries.forEach(function (e) {
      if (!e || !e.entry_id) return;
      var id = String(e.entry_id);
      if (!byId[id]) { byId[id] = { id: id, kinds: [], unresolved: false }; order.push(byId[id]); }
      var row = byId[id];
      if (e.kind && row.kinds.indexOf(String(e.kind)) < 0) row.kinds.push(String(e.kind));
      if (e.unresolved) row.unresolved = true;
    });
    return order;
  }

  function entryOptionLabel(options, value) {
    for (var i = 0; i < (options || []).length; i++) {
      if (options[i] && String(options[i].value) === String(value)) {
        return String(options[i].label || options[i].value);
      }
    }
    return String(value);
  }

  function entryDraftOf(id) {
    if (!state.gateDraft.entryDecisions) state.gateDraft.entryDecisions = {};
    var cur = state.gateDraft.entryDecisions[id];
    if (!cur || typeof cur !== "object") cur = { decision: null, reason: "" };
    if (typeof cur.reason !== "string") cur.reason = cur.reason == null ? "" : String(cur.reason);
    state.gateDraft.entryDecisions[id] = cur;
    return cur;
  }

  function derivedEntryDecision(pending) {
    var rows = entryRows(pending);
    return window.GateSession.deriveEntryDecision(rows.map(function (r) {
      return entryDraftOf(r.id).decision || null;
    }));
  }

  /* U8-b（SPEC-REV-08）：整门理由复用预填——判定在 gate-session.reusableReason；
   * 这里只在整门理由为空时预填，用户已输入（含输入到一半）不覆盖。 */
  function maybePrefillGateReason(pending, derived) {
    if (!derived || !window.GateSession || !window.GateSession.reusableReason) return;
    if (String(state.gateDraft.reason || "").trim()) return;
    var reuse = window.GateSession.reusableReason(
      state.gateDraft.entryDecisions, derived, gateOptionsFor(pending));
    if (reuse) state.gateDraft.reason = reuse;
  }

  function setEntryDecision(id, value) {
    entryDraftOf(id).decision = value;
    var pending = pendingInfo(state.viewData) || {};
    var derived = derivedEntryDecision(pending);
    if (derived) state.gateDraft.decision = derived;
    maybePrefillGateReason(pending, derived);
    syncGateForms();
  }

  function renderEntryDecisionControls(container, pending, options) {
    clearEl(container);
    if (!entryDecisionsRequired(pending)) return;
    var rows = entryRows(pending);
    var values = (options || []).map(function (o) { return String(o.value); });
    if (!rows.length || !values.length) return;  // 无法生成控件：材料区给 API 提示
    var box = h("div", "gate-entries-box");
    box.appendChild(h("div", "gate-entries-head", "逐条处置（I1：覆盖全部 " + rows.length + " 个条目）"));
    box.appendChild(h("div", "muted tiny",
      "每条选一个处置；ignored / disputed 必须写理由。整门决策由此推导，最终由服务端判定。"));
    var groupId = container.id || "entries";
    rows.forEach(function (row) {
      var line = h("div", "gate-entry");
      line.setAttribute("data-entry-id", row.id);
      var head = h("div", "gate-entry-head");
      head.appendChild(h("b", "mono", row.id));
      if (row.kinds.length) head.appendChild(h("span", "muted tiny", " · " + row.kinds.join(" + ")));
      if (row.unresolved) head.appendChild(chipEl("未决", "warn"));
      line.appendChild(head);
      var opts = h("div", "gate-entry-options");
      values.forEach(function (value) {
        var label = h("label", "option");
        var input = h("input");
        input.type = "radio";
        input.name = "entry-" + groupId + "-" + row.id;
        input.value = value;
        input.addEventListener("change", function () { setEntryDecision(row.id, value); });
        label.appendChild(input);
        label.appendChild(h("span", "radio"));
        label.appendChild(h("span", null, entryOptionLabel(options, value)));
        opts.appendChild(label);
      });
      line.appendChild(opts);
      var reason = h("input", "input mono gate-entry-reason");
      reason.placeholder = "本条理由（ignored / disputed 必填）";
      reason.setAttribute("aria-label", "条目理由 " + row.id);
      reason.addEventListener("input", function () {
        entryDraftOf(row.id).reason = reason.value;
        /* U8-b：条目理由补齐时，整门理由仍为空则预填复用（判定在 reusableReason）。 */
        var pendingNow = pendingInfo(state.viewData) || {};
        maybePrefillGateReason(pendingNow, derivedEntryDecision(pendingNow));
        syncGateForms();
      });
      line.appendChild(reason);
      box.appendChild(line);
    });
    container.appendChild(box);
  }

  function syncEntryDecisionControls(container, pending) {
    if (!entryDecisionsRequired(pending)) return;
    var d = state.gateDraft;
    var lines = container.querySelectorAll(".gate-entry");
    for (var i = 0; i < lines.length; i++) {
      var id = lines[i].getAttribute("data-entry-id");
      var cur = (d.entryDecisions && d.entryDecisions[id]) || {};
      var inputs = lines[i].querySelectorAll('input[type="radio"]');
      for (var j = 0; j < inputs.length; j++) {
        var on = String(inputs[j].value) === String(cur.decision || "");
        inputs[j].checked = on;
        inputs[j].disabled = d.submitting;
        if (inputs[j].parentNode) inputs[j].parentNode.classList.toggle("on", on);
      }
      var reason = lines[i].querySelector(".gate-entry-reason");
      if (reason) {
        if (reason.value !== String(cur.reason || "")) reason.value = String(cur.reason || "");
        reason.disabled = d.submitting;
      }
    }
  }

  function renderDiffEntries(host, pending, opts) {
    if (!host) return;
    var o = opts || {};
    var d = diffPayloadOf(pending);
    if (!d) {
      host.appendChild(h("div", "alert warn", "服务端未下发 N2 差异清单（difference_items 缺失）。"));
      renderMaterialExtras(host, pending);
      return;
    }
    var entries = Array.isArray(d.entries) ? d.entries : [];
    if (!o.hideHead) {
      var head = h("div", "diff-head");
      head.appendChild(h("b", null, diffSummaryText(pending)));
      if (d.has_change === false) head.appendChild(chipEl("无变更", "ok"));
      if (d.self_check_ok === true) head.appendChild(chipEl("self_check_ok", "ok"));
      else if (d.self_check_ok === false) head.appendChild(chipEl("self_check 未通过", "warn"));
      if (d.mode === "drill") {
        var drillHead = chipEl("drill_fixture", "warn");
        drillHead.title = "difference_items.mode=drill：本轮材料来自 drill 夹具，不是真实环境实测";
        head.appendChild(drillHead);
      } else if (d.mode) {
        head.appendChild(chipEl(String(d.mode), ""));
      }
      if (d.drill_fixture) head.appendChild(chipEl("drill_fixture", "warn"));
      if (d.legacy_drill_fixture) head.appendChild(chipEl("drill 历史夹具", ""));
      host.appendChild(head);
    }
    if (d.error) {
      host.appendChild(h("div", "alert bad", "差异清单解析失败：" + String(d.error)));
    }
    if (d.present === false) {
      host.appendChild(h("div", "alert warn", "N2 产物缺失：无法逐条核对，不得确认。"));
      renderMaterialExtras(host, pending);
      return;
    }
    if (!entries.length) {
      host.appendChild(h("div", "muted tiny", "本轮没有差异条目。"));
      renderMaterialExtras(host, pending);
      return;
    }

    var payload = pending && pending.payload ? pending.payload : {};
    var fromPayload = Array.isArray(payload.unresolved_entries) ? payload.unresolved_entries : [];
    var unresolvedIds = Array.isArray(d.unresolved_ids) && d.unresolved_ids.length
      ? d.unresolved_ids : fromPayload;
    if (unresolvedIds.length) {
      var chips = h("div", "chips");
      unresolvedIds.forEach(function (id) {
        chips.appendChild(chipEl(
          "未决：" + (id === null || id === undefined ? "（无 entry_id）" : String(id)), "bad"));
      });
      host.appendChild(chips);
    }

    var list = h("div", "diff-list");
    entries.forEach(function (e) {
      if (!e || typeof e !== "object") return;
      list.appendChild(renderDiffEntry(e));
    });
    host.appendChild(list);
    if (d.path) host.appendChild(h("div", "foot-note mono", String(d.path)));
    renderMaterialExtras(host, pending);
  }

  /* ---------------- 双栏独立滚动：重绘协调（WEB_UI_SPEC §5 / A11，2026-10-29） ----------------
   * 人反馈「闸门材料 / 闸门操作 要能分别上下滚动，方便对照处理」。CSS 只给上限与 overflow；
   * 真正成立的前提是**跨重绘保持**：每 1.5 s 一次 `renderLive()` 会 `clearEl` 重建材料栏，
   * 不保持就会每 1.5 s 把人滚回顶部（等于功能不成立）。
   * 判定（身份/该回填到哪/是否真溢出）唯一在 `web/pane-scroll.js`；这里只持有 DOM 与
   * 每栏的 `{identity, top}` 记忆、包两个渲染入口、回填 scrollTop 并同步 Tab 停靠点。
   * 身份 = run_id + 闸门 + 轮次：同身份保持位置，换身份回顶。视图隐藏时（clientHeight=0、
   * scrollTop 会被钳 0）只记位置不采信实时值，切回来再回填。
   * ------------------------------------------------------------------------ */
  var paneMemory = Object.create(null);
  var paneWired = Object.create(null);

  function paneMemoryOf(hostId) {
    if (!paneMemory[hostId]) paneMemory[hostId] = {identity: null, top: 0};
    return paneMemory[hostId];
  }

  function paneIdentityFor(pending) {
    if (!window.PaneScroll) return "";
    return pending
      ? window.PaneScroll.identity(state.runId, pending.gate, pending.cycle)
      : window.PaneScroll.identity(state.runId, null, null);
  }

  function wirePane(host, hostId) {
    if (!host || paneWired[hostId]) return;
    paneWired[hostId] = true;
    /* 用户用滚轮/键盘滚动时同步记忆；否则「隐藏→可见」回来时只剩渲染时刻的旧值。 */
    host.addEventListener("scroll", function () {
      paneMemoryOf(hostId).top = host.scrollTop || 0;
    });
  }

  function syncPaneTabStop(host) {
    if (!host) return;
    var scrollable = window.PaneScroll
      ? window.PaneScroll.isScrollable(host.scrollHeight, host.clientHeight) : false;
    /* 可滚动区域必须能用键盘滚（§5 第 4 条）：只在**实际溢出**时给 Tab 停靠点。 */
    if (scrollable) host.setAttribute("tabindex", "0");
    else host.removeAttribute("tabindex");
  }

  function renderPanePreservingScroll(hostId, pending, paint) {
    var host = $(hostId);
    if (!host) { paint(); return; }
    wirePane(host, hostId);
    var key = paneIdentityFor(pending);
    var mem = paneMemoryOf(hostId);
    if (host.clientHeight > 0) mem.top = host.scrollTop || 0;
    var top = window.PaneScroll
      ? window.PaneScroll.restore({identity: mem.identity, top: mem.top}, key) : 0;
    paint();
    mem.identity = key;
    host.scrollTop = top;
    if (host.clientHeight > 0) mem.top = host.scrollTop || 0;
    syncPaneTabStop(host);
  }

  function renderGateMaterial(v) {
    renderPanePreservingScroll("gateMaterial", pendingInfo(v), function () { paintGateMaterial(v); });
  }

  function paintGateMaterial(v) {
    var host = $("gateMaterial");
    if (!host) return;
    clearEl(host);
    if (!state.runId) {
      host.appendChild(h("div", "muted tiny", "尚未选择运行。"));
      return;
    }
    if (!v) {
      host.appendChild(h("div", "muted tiny", panelHint()));
      return;
    }
    var pending = pendingInfo(v);
    if (pending && pending.kind === "job") {
      /* 长任务停放（job_done 中断）：不是闸门，不得渲染决策表单。 */
      addKV(host, "运行状态", statusLabel(v.status));
      if (pending.node) addKV(host, "作业节点", pending.node);
      if (pending.payload && pending.payload.job_id) addKV(host, "作业", String(pending.payload.job_id));
      host.appendChild(h("div", "alert warn",
        "当前运行在等待外部作业完成（" + (pending.node || "长任务") + "），不是人工闸门；作业结束后会自动继续。"));
      return;
    }
    if (!pending) {
      host.appendChild(h("div", "muted tiny", "当前运行没有待决策的闸门。"));
      addKV(host, "运行状态", statusLabel(v.status));
      if (v.gate_history && v.gate_history.length) {
        var det = h("details", "adv");
        det.appendChild(h("summary", null, "已发生的闸门决策（事件流投影，非权威）"));
        v.gate_history.forEach(function (g) {
          var row = h("div", "kv");
          row.appendChild(h("span", null, String((g && g.gate) || "—")));
          row.appendChild(h("b", null, String((g && g.decision) || "—") + " · " + String((g && g.actor) || "—")));
          det.appendChild(row);
        });
        host.appendChild(det);
      }
      return;
    }
    var m = pending.payload || {};
    /* U10-a（SPEC-REV-08）：材料行显示人话标题（与头部 pill 同口径），原始 id 移入悬停提示。 */
    var gateRow = addKV(host, "闸门", gateTitle(pending.gate));
    gateRow.title = pending.gate;
    addKV(host, "节点", m.gate_node || pending.node || "—");
    addKV(host, "轮次", pending.cycle !== null ? String(pending.cycle) : "—");
    addKV(host, "冲突快照", conflictsText(m.conflicts));
    addKV(host, "返工轮次", reworkText(m.rework));
    addKV(host, "硬阻断", codesText(m.hard_block));
    addKV(host, "缺陷", codesText(m.defects));
    var diffBox = h("div", "diff-block");
    renderDiffEntries(diffBox, pending, {});
    host.appendChild(diffBox);
    addKV(host, "权威枚举", enumsText(m.authority_enums, pending.gate));
    var options = gateOptionsFor(pending);
    addKV(host, "服务端决策选项", options.length ? options.length + " 个" : "未下发（不可提交）");
    if (m.counts) addKV(host, "双口径", countsText(m.counts));
    if (m.invariant_note) host.appendChild(h("div", "alert info", String(m.invariant_note)));
    if (m.actor_policy) host.appendChild(h("div", "foot-note", String(m.actor_policy)));
    host.appendChild(h("div", "foot-note", "材料与选项均来自服务端；界面不参与判定，也不持有「已通过」。"));
  }

  function conflictsText(c) {
    if (!c) return "—";
    return "共 " + (c.total !== undefined ? c.total : "?") +
      " · open " + (c.open !== undefined ? c.open : "?") +
      " · blocks_release " + (c.blocks_release !== undefined ? c.blocks_release : "?");
  }

  function reworkText(r) {
    if (!r) return "—";
    return "n6_n8_cycles " + (r.n6_n8_cycles !== undefined ? r.n6_n8_cycles : "?") +
      " / 上限 " + (r.limit !== undefined && r.limit !== null ? r.limit : "—");
  }

  function codesText(items) {
    if (!items || !items.length) return "无";
    return items.map(function (item) {
      if (!item) return "?";
      return typeof item === "string" ? item : (item.code || "?");
    }).join("、");
  }

  function enumsText(authorityEnums, gate) {
    if (authorityEnums && authorityEnums[gate] && authorityEnums[gate].length) {
      return authorityEnums[gate].join(" / ");
    }
    var options = gateOptionsFor({ gate: gate, payload: state.viewData && state.viewData.pending_interrupt ? state.viewData.pending_interrupt.payload : null });
    if (options.length) return options.map(function (o) { return o.value; }).join(" / ");
    return "服务端未下发";
  }

  function countsText(counts) {
    var k1 = counts.koutou1 || {};
    var k2 = counts.koutou2 || {};
    return "口径一 " + countValue(k1.value) + " · 口径二 " + countValue(k2.value);
  }

  function gateOptionsFor(pending) {
    if (!pending) return [];
    var v = state.viewData;
    /* 只认运行视图**每次重算**的 gate_options（判据随本轮事实变化：G2 报告结论、
       drill G1 attestation）。中断载荷里的 decision_options 是中断创建时的快照，
       可能来自升级前或快照恢复 ⇒ 不得作为界面判据（WEB_UI_SPEC §5）。 */
    var options = (v && v.gate_options && v.gate_options[pending.gate]) || null;
    if (!Array.isArray(options)) return [];
    return options.filter(function (o) { return o && o.value !== undefined && o.value !== null; });
  }

  function renderGatePanel(v) {
    renderPanePreservingScroll("gatePanel", pendingInfo(v), function () { paintGatePanel(v); });
  }

  function paintGatePanel(v) {
    var host = $("gatePanel");
    if (!host) return;
    if (!state.runId) {
      clearEl(host);
      host.removeAttribute("data-gate-key");
      host.appendChild(h("div", "muted tiny", "尚未选择运行。"));
      return;
    }
    if (!v) {
      clearEl(host);
      host.removeAttribute("data-gate-key");
      host.appendChild(h("div", "muted tiny", panelHint()));
      return;
    }
    var pending = pendingInfo(v);
    if (pending && pending.kind === "job") {
      clearEl(host);
      host.removeAttribute("data-gate-key");
      host.appendChild(h("div", "muted tiny", "当前运行在等待外部作业（" +
        (pending.node || "长任务") + "），没有待决策闸门。"));
      return;
    }
    if (!pending || pending.kind !== "gate" || !pending.gate) {
      clearEl(host);
      host.removeAttribute("data-gate-key");
      host.appendChild(h("div", "muted tiny", "当前运行没有待决策闸门。"));
      if (v.gate_history && v.gate_history.length) {
        var det = h("details", "adv");
        det.appendChild(h("summary", null, "已发生的闸门决策（事件流投影，非权威）"));
        v.gate_history.forEach(function (g) {
          det.appendChild(h("div", "kv", String((g && g.gate) || "—") + " · " + String((g && g.decision) || "—")));
        });
        host.appendChild(det);
      }
      return;
    }
    ensureGateForm(host, pending, false);
    updateGateForm(host, pending);
  }

  /* 闸门会话判定唯一实现在 web/gate-session.js（纯函数）；这里只做状态装配。 */
  function ensureDraft(pending) {
    var result = window.GateSession.reconcile(state.gateDraft, {
      runId: state.runId,
      pending: pending,
      options: gateOptionsFor(pending)
    });
    state.gateDraft = result.draft;
  }

  function ensureGateForm(container, pending, compact) {
    ensureDraft(pending);
    var key = window.GateSession.sessionKey(state.runId, pending) + "|" + JSON.stringify(gateOptionsFor(pending));
    if (container.getAttribute("data-gate-key") === key) return;
    container.setAttribute("data-gate-key", key);
    clearEl(container);

    var form = h("div", "gate-form");
    if (compact) {
      var materialBox = h("div");
      var m = pending.payload || {};
      addKV(materialBox, "闸门", pending.gate);
      if (pending.cycle !== null) addKV(materialBox, "轮次", String(pending.cycle));
      addKV(materialBox, "冲突快照", conflictsText(m.conflicts));
      addKV(materialBox, "硬阻断", codesText(m.hard_block));
      form.appendChild(materialBox);

      var diffDet = h("details", "adv diff-det");
      diffDet.appendChild(h("summary", null, diffSummaryText(pending)));
      renderDiffEntries(diffDet, pending, { hideHead: true });
      form.appendChild(diffDet);
      /* U8-c（SPEC-REV-08）：逐条处置控件只在闸门视图——紧凑卡必须给出去处，
       * 否则用户在此提交只会收到「未覆盖全部条目」的无去向错误。 */
      if (entryDecisionsRequired(pending)) {
        var guide = h("div");
        guide.style.marginTop = "8px";
        guide.appendChild(h("div", "muted tiny", "本闸门需逐条处置全部差异条目（I1）；逐条控件在「人工闸门」视图。"));
        var go = h("button", "btn btn-sm", "去人工闸门视图逐条处置 →");
        go.type = "button";
        go.addEventListener("click", function () { showView("gate"); });
        guide.appendChild(go);
        form.appendChild(guide);
      }
    }

    var options = gateOptionsFor(pending);
    /* 「接受未通过报告必须理由」的判据**只在服务端**（contracts.decision_requires_reason →
       选项 requires_reason=true）。这里只读该 flag 决定是否提示，不自己判「本轮是否
       not_passed」，否则又是一套前置（红线 8）。 */
    var acceptOption = null;
    for (var ai = 0; ai < options.length; ai++) {
      if (options[ai] && options[ai].value === "accept") { acceptOption = options[ai]; break; }
    }
    var n12 = (((pending.payload || {}).report || {}).n12_report || {});
    if (acceptOption && acceptOption.requires_reason === true) {
      form.appendChild(h("div", "alert warn",
        (n12.claimed_verdict ? "本轮报告结论：" + String(n12.claimed_verdict) + "。" : "") +
        "接受未通过报告必须填写理由；接受不等于判据通过，N16 仍被 I3/I4 阻断。"));
    }
    /* 复核建议 A（2026-10-26）：结论**来源**必须可见。drill 夹具的报告常没有
       claimed_verdict 行（判据口径为 None），界面若不标来源，人会看到"未通过"却
       不知道为什么选项说无需理由；两来源冲突时也要摆出来，不得静默择一。
       本行只在异常来源/分歧时出现，正常（报告落盘且一致）不额外渲染，避免噪音。 */
    if (n12.claimed_verdict
        && (n12.claimed_verdict_source === "state_facts"
            || n12.claimed_verdict_diverged === true)) {
      var srcText = n12.claimed_verdict_source === "state_facts"
        ? "结论来自执行记录；报告未落盘，不作为判据依据。" : "";
      var divergeText = n12.claimed_verdict_diverged === true
        ? "报告与执行记录结论不一致：报告=" + String(n12.claimed_verdict_decision) +
          "，记录=" + String(n12.claimed_verdict_facts) + "。"
        : "";
      form.appendChild(h("div", "alert info", srcText + divergeText));
    }
    /* G1 逐条处置（SPEC-04 §4.4 2026-10-23）：先逐条选，再整门提交。
       紧凑卡片只放材料摘要，逐条控件放在完整闸门视图，避免两处重复渲染。 */
    if (!compact) {
      var entryHost = h("div", "gate-entries-host");
      entryHost.id = "gateEntries";
      renderEntryDecisionControls(entryHost, pending, options);
      if (entryHost.childNodes.length) form.appendChild(entryHost);
    }
    var list = h("div", "gate-options");
    if (!options.length) {
      list.appendChild(h("div", "alert bad", "服务端未下发决策选项（run_view.gate_options 缺失）⇒ 不可提交。"));
    } else {
      var groupName = "gate-decision-" + (container.id || "x");
      options.forEach(function (opt) {
        var label = h("label", "option");
        var input = h("input");
        input.type = "radio";
        input.name = groupName;
        input.value = String(opt.value);
        if (state.gateDraft.decision === opt.value) input.checked = true;
        input.addEventListener("change", function () {
          state.gateDraft.decision = opt.value;
          syncGateForms();
        });
        label.appendChild(input);
        label.appendChild(h("span", "radio"));
        var box = h("div");
        box.appendChild(h("b", null, opt.label || String(opt.value)));
        box.appendChild(h("span", null, "值 " + opt.value + (opt.requires_reason ? " · 必须填写理由" : "")));
        label.appendChild(box);
        list.appendChild(label);
      });
    }
    form.appendChild(list);

    var actorRow = h("div", "field-row");
    actorRow.style.marginTop = "10px";
    var actorInput = h("input", "input mono");
    actorInput.placeholder = "human:your-name";
    /* U1-c：仅在空/默认前缀时预填上一次的合规操作者；已填值（含输入到一半）原样保留。 */
    if (window.Operator) {
      var prefilled = window.Operator.apply(state.gateDraft.actor, window.Operator.recall());
      if (prefilled !== state.gateDraft.actor) state.gateDraft.actor = prefilled;
    }
    actorInput.value = state.gateDraft.actor;
    actorInput.setAttribute("aria-label", "actor");
    actorInput.style.maxWidth = "220px";
    actorInput.addEventListener("input", function () {
      state.gateDraft.actor = actorInput.value;
      /* 记忆只存合规 human:<name>；不合规输入不记（判定在 operator.js）。 */
      if (window.Operator) window.Operator.remember(actorInput.value);
      syncGateForms();
    });
    actorRow.appendChild(actorInput);
    form.appendChild(actorRow);
    form.appendChild(h("div", "foot-note", "actor 必须以 human 开头（I6）；模型/替身 actor 会被服务端拒绝。"));

    var reason = h("textarea", "input");
    reason.rows = 3;
    reason.placeholder = "裁决理由（ignored / rework / disputed 必填）";
    reason.value = state.gateDraft.reason;
    reason.style.marginTop = "8px";
    reason.setAttribute("aria-label", "裁决理由");
    reason.addEventListener("input", function () {
      state.gateDraft.reason = reason.value;
      syncGateForms();
    });
    form.appendChild(reason);

    var errorBox = h("div", "gate-error");
    errorBox.setAttribute("data-gate-error", "1");
    form.appendChild(errorBox);

    var submit = h("button", "btn btn-primary btn-block", "提交闸门决策");
    submit.type = "button";
    submit.style.marginTop = "10px";
    submit.setAttribute("data-gate-submit", "1");
    submit.addEventListener("click", function () { submitGate(); });
    form.appendChild(submit);

    /* U8-a（SPEC-REV-08）：缺项就地提示挂载点（内容在 updateGateForm 实时刷新）。 */
    var entryHint = h("div");
    entryHint.setAttribute("data-gate-entry-hint", "1");
    entryHint.style.marginTop = "6px";
    form.appendChild(entryHint);

    container.appendChild(form);
  }

  function updateGateForm(container, pending) {
    var form = container.querySelector(".gate-form");
    if (!form) return;
    var options = gateOptionsFor(pending);
    var d = state.gateDraft;
    d.submitting = window.GateSession.isSubmitting(state.gateSubmissions, d.key);
    /* 只同步整门决策单选；逐条处置单选由 syncEntryDecisionControls 单独同步，
       避免两套 radio 互相覆盖（SPEC-04 §4.4 2026-10-23）。 */
    var labels = form.querySelectorAll(".gate-options .option");
    for (var i = 0; i < labels.length; i++) {
      var input = labels[i].querySelector("input");
      var on = !!(input && d.decision === input.value);
      labels[i].classList.toggle("on", on);
      if (input) {
        input.checked = on;
        input.disabled = d.submitting;
      }
    }
    var actor = form.querySelector('[aria-label="actor"]');
    var reason = form.querySelector('[aria-label="裁决理由"]');
    if (actor && actor.value !== d.actor) actor.value = d.actor;
    if (reason && reason.value !== d.reason) reason.value = d.reason;
    if (actor) actor.disabled = d.submitting;
    if (reason) reason.disabled = d.submitting;
    var submit = form.querySelector("[data-gate-submit]");
    /* 就绪判定与控件渲染必须同一口径：都只看服务端下发的 entry_decisions_required
       （判据唯一在服务端，只对 G1 为真；WEB_UI_SPEC §4.4「判据归属」）。
       上游（SPEC-REV-08 U8-a）把这两行上提到 if (submit) 之外，供缺项提示块复用。 */
    var needEntries = entryDecisionsRequired(pending) && entryRows(pending).length > 0;
    var entriesReady = !needEntries || !!derivedEntryDecision(pending);
    if (submit) {
      var offered = options.some(function (o) { return o.value === d.decision; });
      submit.disabled = !offered || d.submitting || !entriesReady;
      submit.textContent = d.submitting ? "提交中…"
        : (!entriesReady ? "请先逐条处置全部条目" : "提交闸门决策");
    }
    /* U8-a（SPEC-REV-08）：未就绪时把缺项说清楚——直接消费 validateEntryDecisions
     * 的 error（含缺失 entry_id 清单）；判定零新增，就绪即清空。 */
    var entryHintEl = form.querySelector("[data-gate-entry-hint]");
    if (entryHintEl) {
      clearEl(entryHintEl);
      if (needEntries && !entriesReady) {
        var missingIds = entryRows(pending).map(function (r) { return r.id; });
        var allowedValues = options.map(function (o) { return String(o.value); });
        var check = window.GateSession.validateEntryDecisions(d.entryDecisions, missingIds, allowedValues);
        if (!check.ok) entryHintEl.appendChild(h("div", "alert warn", check.error));
      }
    }
    var errorBox = form.querySelector("[data-gate-error]");
    if (errorBox) {
      clearEl(errorBox);
      if (d.error) {
        errorBox.appendChild(h("div", "alert bad", String(d.error)));
        if (d.note) errorBox.appendChild(h("div", "muted tiny", String(d.note)));
        if (d.blockers && d.blockers.length) {
          var list = h("div", "gate-blockers");
          list.appendChild(h("b", null, "服务端 blockers（原样）："));
          var ul = h("ul");
          d.blockers.forEach(function (b) {
            var text = b && typeof b === "object"
              ? ((b.code || b.severity || "blocker") + (b.message ? "：" + b.message : ""))
              : String(b);
            ul.appendChild(h("li", null, text));
          });
          list.appendChild(ul);
          errorBox.appendChild(list);
        }
      }
    }
    syncEntryDecisionControls(form, pending);
  }

  function syncGateForms() {
    var pending = pendingInfo(state.viewData);
    if (!pending) return;
    ["gateCardBody", "gatePanel"].forEach(function (id) {
      var el = $(id);
      if (el && el.getAttribute("data-gate-key")) updateGateForm(el, pending);
    });
  }

  function resetGateDraft() {
    state.gateDraft = window.GateSession.freshDraft(null, null);
    ["gateCardBody", "gatePanel"].forEach(function (id) {
      var el = $(id);
      if (el) {
        el.removeAttribute("data-gate-key");
        clearEl(el);
      }
    });
  }

  async function submitGate() {
    var pending = pendingInfo(state.viewData);
    if (!pending || pending.kind !== "gate" || !pending.gate) {
      toast("当前没有待决策闸门");
      return;
    }
    ensureDraft(pending);
    var d = state.gateDraft;
    if (window.GateSession.isSubmitting(state.gateSubmissions, d.key)) return;
    var options = gateOptionsFor(pending);
    var selected = null;
    for (var i = 0; i < options.length; i++) {
      if (options[i].value === d.decision) { selected = options[i]; break; }
    }
    if (!selected) {
      d.error = "请先选择一个决策（选项由服务端下发）。";
      d.blockers = null;
      d.note = null;
      syncGateForms();
      return;
    }
    if (selected && selected.requires_reason && !String(d.reason || "").trim()) {
      d.error = "该决策必须填写理由（" + d.decision + "）。";
      d.blockers = null;
      d.note = null;
      syncGateForms();
      return;
    }
    /* R3（2026-10-26）：原先这里还有一段「G2 accept + not_passed ⇒ 必须理由」的自写前置，
       现已删除——该规则由服务端选项的 requires_reason 承载（上一条检查即可覆盖），
       避免界面与服务端各判一套（红线 8）。 */
    if (!String(d.actor || "").trim()) {
      d.error = "必须填写 actor（且以 human 开头）。";
      syncGateForms();
      return;
    }
    var requestBody = {
      decision: d.decision,
      actor: String(d.actor || "").trim(),
      reason: String(d.reason || "").trim() || null
    };
    /* G1 逐条处置：覆盖全部唯一 entry_id 才提交；覆盖不全/理由缺失就地拦下，
       仍以服务端 I1 判定为权威（SPEC-04 §4.4 2026-10-23）。 */
    if (entryDecisionsRequired(pending)) {
      var entryList = entryRows(pending);
      if (entryList.length) {
        var checkedEntries = window.GateSession.validateEntryDecisions(
          d.entryDecisions,
          entryList.map(function (r) { return r.id; }),
          options.map(function (o) { return String(o.value); })
        );
        if (!checkedEntries.ok) {
          d.error = checkedEntries.error;
          d.blockers = null;
          d.note = null;
          syncGateForms();
          return;
        }
        var derivedDecision = derivedEntryDecision(pending);
        if (derivedDecision && derivedDecision !== d.decision) {
          d.error = "逐条处置推导出的整门决策是 " + derivedDecision
            + "，与当前选择 " + d.decision + " 不一致；请调整后重试。";
          d.blockers = null;
          d.note = null;
          syncGateForms();
          return;
        }
        requestBody.entry_decisions = checkedEntries.entry_decisions;
      }
    }
    d.submitting = true;
    state.gateSubmissions = window.GateSession.beginSubmission(state.gateSubmissions, d.key).ledger;
    d.error = null;
    d.blockers = null;
    d.note = null;
    syncGateForms();
    var runId = state.runId;
    var epoch = state.selectionEpoch;
    function sameSelection() { return state.runId === runId && state.selectionEpoch === epoch; }
    function currentSubmission() {
      var current = pendingInfo(state.viewData);
      return sameSelection() && state.gateDraft === d && current && window.GateSession.sessionKey(state.runId, current) === d.key;
    }
    try {
      await api("/api/runs/" + enc(runId) + "/gates/" + enc(pending.gate) + "/decision", {
        method: "POST",
        body: requestBody
      });
      if (!currentSubmission()) return;
      toast("闸门决策已提交：" + pending.gate + " · " + d.decision);
      resetGateDraft();
      await poll();
      if (sameSelection()) showView("run");
    } catch (e) {
      if (!currentSubmission()) return;
      d.error = errText(e);
      var detail = e.body && e.body.detail;
      if (detail && typeof detail === "object") {
        if (Array.isArray(detail.blockers)) d.blockers = detail.blockers;
        if (detail.note) d.note = String(detail.note);
      }
      toast("闸门提交被拒：" + e.message);
      syncGateForms();
    } finally {
      state.gateSubmissions = window.GateSession.endSubmission(state.gateSubmissions, d.key);
      d.submitting = false;
      if (state.gateDraft.key === d.key) syncGateForms();
    }
  }

  /* ------------------------------------------------------------------ *
   * 目录浏览器（基线与项目共用）
   * ------------------------------------------------------------------ */
  function baselineRootPath() {
    if (state.baselineRoot) return state.baselineRoot;
    if (state.health && state.health.workspace_root) {
      return String(state.health.workspace_root).replace(/\/$/, "") + "/baselines";
    }
    return "";
  }

  function joinPath(base, name) {
    var b = String(base || "").replace(/\/$/, "");
    return b + "/" + String(name || "");
  }

  function shortRootLabel(path) {
    var parts = String(path || "").split("/");
    return parts[parts.length - 1] || path || "根";
  }

  function openDirPicker(kind) {
    var host = $(kind === "baseline" ? "pickerHostBaseline" : "pickerHostProject");
    var picker = $("dirPicker");
    if (!host || !picker) return;
    host.replaceChildren(picker);
    picker.classList.remove("hidden");
    setText("dirHint", kind === "baseline"
      ? "只列基线版本；不可用的版本置灰（manifest 缺失/不可解析）"
      : "只列目录、不读文件内容；越界路径由服务端 403 拒绝");
    setText("btnDirChoose", kind === "baseline" ? "选择基线版本" : "选择此目录");
    var btnChoose = $("btnDirChoose");
    if (btnChoose) btnChoose.disabled = true;
    if (kind === "baseline") {
      state.picker = {
        kind: kind,
        path: baselineRootPath(),
        parent: null,
        roots: [],
        entries: (state.baselines || []).map(function (b) { return { name: b.id, base: b }; }),
        error: null,
        loading: false
      };
      renderPicker();
      return;
    }
    state.picker = {
      kind: kind,
      path: state.setup.project || (state.health && state.health.env_root) || "",
      parent: null,
      roots: [],
      entries: [],
      error: null,
      loading: true
    };
    renderPicker();
    loadDirs(state.picker.path);
  }

  async function loadDirs(path) {
    if (!state.picker) return;
    if (!path) {
      state.picker.loading = false;
      state.picker.error = "没有可浏览的起始目录";
      renderPicker();
      return;
    }
    state.picker.loading = true;
    state.picker.error = null;
    renderPicker();
    try {
      var body = await api("/api/fs/dirs?path=" + enc(path));
      if (!state.picker) return;
      state.picker.path = body.path || path;
      state.picker.parent = body.parent || null;
      state.picker.roots = Array.isArray(body.roots) ? body.roots : [];
      state.picker.entries = Array.isArray(body.entries) ? body.entries : [];
      state.picker.error = null;
    } catch (e) {
      if (!state.picker) return;
      state.picker.error = errText(e);
      state.picker.entries = [];
    } finally {
      if (state.picker) {
        state.picker.loading = false;
        renderPicker();
      }
    }
  }

  function renderPicker() {
    var picker = state.picker;
    var box = $("dirPicker");
    if (!box) return;
    if (!picker) {
      box.classList.add("hidden");
      return;
    }
    box.classList.remove("hidden");
    renderPickerCrumb(picker);
    renderPickerRoots(picker);
    var list = $("dirList");
    if (!list) return;
    clearEl(list);
    var up = $("btnDirUp");
    if (up) up.disabled = picker.kind === "baseline" || !picker.parent || !!picker.loading;
    var choose = $("btnDirChoose");
    if (choose) {
      choose.disabled = picker.kind === "baseline" || !!picker.loading || !picker.path || !!picker.error;
    }
    if (picker.loading) {
      list.appendChild(h("div", "dp-note", "加载中…"));
      return;
    }
    if (picker.error) {
      var errBox = h("div", "alert bad", picker.error);
      errBox.style.margin = "10px 12px";
      list.appendChild(errBox);
      return;
    }
    if (picker.kind === "baseline") {
      if (!picker.entries.length) {
        list.appendChild(h("div", "dp-note", "没有可用的基线目录。基线由 N16 晋升产生。"));
        return;
      }
      picker.entries.forEach(function (ent) {
        var b = ent.base || {};
        var row = h("button", "dp-item" + (b.valid ? "" : " disabled"));
        row.type = "button";
        row.appendChild(h("span", "dp-icon", b.valid ? "▣" : "▢"));
        row.appendChild(h("b", null, b.id || ent.name || "—"));
        var meta = h("span", "dp-meta");
        if (b.created_at) meta.appendChild(h("span", null, fmtDateTime(b.created_at)));
        if (b.parent) meta.appendChild(h("span", null, "parent=" + b.parent));
        if (b.cases !== undefined && b.cases !== null) meta.appendChild(h("span", null, b.cases + " 用例"));
        if (b.rtl_snapshot_bytes !== undefined && b.rtl_snapshot_bytes !== null) {
          meta.appendChild(h("span", null, bytesText(b.rtl_snapshot_bytes)));
        }
        if (b.valid) {
          meta.appendChild(h("span", "chip ok", "manifest 有效"));
        } else {
          var missing = b.missing && b.missing.length ? "缺 " + b.missing.join("、") : "不可用";
          if (b.errors && b.errors.length) missing += "（" + b.errors.join("；") + "）";
          meta.appendChild(h("span", "chip bad", missing));
        }
        row.appendChild(meta);
        if (!b.valid) {
          row.disabled = true;
        } else {
          row.addEventListener("click", function () {
            state.setup.baseline = b.id;
            closeDirPicker();
            renderSetup();
            toast("已选择基线 " + b.id);
          });
        }
        list.appendChild(row);
      });
      return;
    }
    if (!picker.entries.length) {
      list.appendChild(h("div", "dp-note", "这一层没有可列出的目录。"));
      return;
    }
    picker.entries.forEach(function (ent) {
      if (!ent) return;
      var row = h("button", "dp-item");
      row.type = "button";
      row.appendChild(h("span", "dp-icon", "▸"));
      row.appendChild(h("b", null, ent.name || "(未命名)"));
      var meta = h("span", "dp-meta");
      if (ent.is_env) {
        meta.appendChild(h("span", "chip ok", "环境仓" + (ent.env_id ? " · " + ent.env_id : "")));
      }
      (ent.markers || []).slice(0, 4).forEach(function (marker) {
        meta.appendChild(h("span", "chip", String(marker)));
      });
      row.appendChild(meta);
      var target = joinPath(picker.path, ent.name);
      row.addEventListener("click", function () { loadDirs(target); });
      list.appendChild(row);
    });
  }

  function renderPickerCrumb(picker) {
    var crumb = $("dirCrumb");
    if (!crumb) return;
    clearEl(crumb);
    var path = picker.path || "";
    if (!path) {
      crumb.textContent = "—";
      return;
    }
    if (picker.kind === "baseline") {
      crumb.textContent = path;
      return;
    }
    var roots = picker.roots || [];
    var root = null;
    roots.forEach(function (r) {
      var rs = String(r).replace(/\/$/, "");
      if (path === rs || path.indexOf(rs + "/") === 0) {
        if (!root || rs.length > root.length) root = rs;
      }
    });
    if (!root) {
      crumb.textContent = path;
      return;
    }
    var rootBtn = h("button", "crumb-seg", shortRootLabel(root));
    rootBtn.type = "button";
    rootBtn.title = root;
    rootBtn.addEventListener("click", function () { loadDirs(root); });
    crumb.appendChild(rootBtn);
    var rest = path.slice(root.length).replace(/^\//, "");
    if (!rest) return;
    var parts = rest.split("/");
    parts.forEach(function (part, idx) {
      var target = root + "/" + parts.slice(0, idx + 1).join("/");
      crumb.appendChild(h("span", null, "/"));
      var seg = h("button", "crumb-seg", part);
      seg.type = "button";
      seg.title = target;
      seg.addEventListener("click", function () { loadDirs(target); });
      crumb.appendChild(seg);
    });
  }

  function renderPickerRoots(picker) {
    var host = $("dirRoots");
    if (!host) return;
    clearEl(host);
    if (picker.kind === "baseline") return;
    (picker.roots || []).forEach(function (root) {
      var btn = h("button", "btn btn-ghost btn-sm", "根：" + shortRootLabel(root));
      btn.type = "button";
      btn.title = "允许根：" + root;
      btn.addEventListener("click", function () { loadDirs(root); });
      host.appendChild(btn);
    });
  }

  function dirUp() {
    if (!state.picker || !state.picker.parent) return;
    loadDirs(state.picker.parent);
  }

  function chooseDir() {
    var picker = state.picker;
    if (!picker) return;
    if (picker.kind === "baseline") {
      toast("请点选一个基线版本");
      return;
    }
    if (!picker.path) return;
    state.setup.project = picker.path;
    state.setup.check = null;
    state.setup.checkError = null;
    closeDirPicker();
    renderSetup();
    checkProject(false);
  }

  function closeDirPicker() {
    state.picker = null;
    var box = $("dirPicker");
    if (box) box.classList.add("hidden");
    var list = $("dirList");
    if (list) clearEl(list);
    var roots = $("dirRoots");
    if (roots) clearEl(roots);
    setText("dirCrumb", "—");
  }

  /* ------------------------------------------------------------------ *
   * 渲染调度
   * ------------------------------------------------------------------ */
  function renderAll() {
    renderHeader();
    renderSidebar();
    renderSetup();
    renderRun();
    renderGate();
    renderBanners();
    renderPicker();
  }

  function renderLive() {
    renderHeader();
    renderSidebar();
    renderRun();
    renderGate();
    renderBanners();
    renderStreamState();
  }

  /* ------------------------------------------------------------------ *
   * 静态绑定与启动
   * ------------------------------------------------------------------ */
  function bindStatic() {
    $("btnS0").addEventListener("click", function () { showView("s0"); });
    var btnNew = $("btnNew");
    if (btnNew) btnNew.addEventListener("click", function () { showView("setup"); });

    var segs = document.querySelectorAll("#viewSeg button");
    for (var i = 0; i < segs.length; i++) {
      (function (btn) {
        btn.addEventListener("click", function () { showView(btn.getAttribute("data-view")); });
        btn.addEventListener("keydown", function (event) {
          var step = event.key === "ArrowDown" || event.key === "ArrowRight" ? 1 :
            event.key === "ArrowUp" || event.key === "ArrowLeft" ? -1 : 0;
          if (!step && event.key !== "Home" && event.key !== "End") return;
          event.preventDefault();
          var index = Array.prototype.indexOf.call(segs, btn);
          var next = event.key === "Home" ? 0 : event.key === "End" ? segs.length - 1 :
            (index + step + segs.length) % segs.length;
          segs[next].focus();
          showView(segs[next].getAttribute("data-view"));
        });
      })(segs[i]);
    }

    var baselineSel = $("setupBaseline");
    if (baselineSel) {
      baselineSel.addEventListener("change", function () {
        state.setup.baseline = baselineSel.value;
        renderSetup();
      });
    }
    var btnRefreshBaselines = $("btnRefreshBaselines");
    if (btnRefreshBaselines) btnRefreshBaselines.addEventListener("click", function () { loadBaselines(true); });
    var btnBaselineBrowse = $("btnBaselineBrowse");
    if (btnBaselineBrowse) btnBaselineBrowse.addEventListener("click", function () {
      if (!state.baselines.length && !state.baselinesLoading) loadBaselines(false);
      openDirPicker("baseline");
    });
    var btnProjectBrowse = $("btnProjectBrowse");
    if (btnProjectBrowse) btnProjectBrowse.addEventListener("click", function () { openDirPicker("project"); });
    var setupCheckBtn = $("setupCheck");
    if (setupCheckBtn) setupCheckBtn.addEventListener("click", function () { checkProject(false); });

    var modeSel = $("setupMode");
    if (modeSel) {
      modeSel.addEventListener("change", function () {
        state.setup.mode = modeSel.value;
        renderSetup();
      });
    }
    var scenarioSel = $("setupScenario");
    if (scenarioSel) {
      scenarioSel.addEventListener("change", function () { state.setup.scenario = scenarioSel.value; });
    }
    var nowInput = $("setupNow");
    if (nowInput) nowInput.addEventListener("input", function () { state.setup.now = nowInput.value; });

    var btnStart = $("btnStart");
    if (btnStart) btnStart.addEventListener("click", submitSetup);

    var btnDirUp = $("btnDirUp");
    if (btnDirUp) btnDirUp.addEventListener("click", dirUp);
    var btnDirClose = $("btnDirClose");
    if (btnDirClose) btnDirClose.addEventListener("click", closeDirPicker);
    var btnDirChoose = $("btnDirChoose");
    if (btnDirChoose) btnDirChoose.addEventListener("click", chooseDir);

    /* U1-a：通知开关（浏览器不支持时保持隐藏，标题徽标/闪烁兜底不受影响）。 */
    var btnNotify = $("btnNotify");
    if (btnNotify && window.Notification) {
      btnNotify.classList.remove("hidden");
      btnNotify.addEventListener("click", function () {
        if (Notification.permission === "granted") return;
        try {
          var result = Notification.requestPermission();
          if (result && typeof result.then === "function") result.then(renderNotifyButton);
        } catch (e) { renderNotifyButton(); }
      });
      renderNotifyButton();
    }
  }

  /* ---------------- 节点面板 ↔ 闸门草稿桥（SPEC-REV-04 §4，2026-10-23 新增） ----------------
   * 唯一职责：让节点面板把逐条勾选/理由写进**同一份** state.gateDraft.entryDecisions，
   * 供闸门视图现有表单提交（提交入口只有那里）。桥本身不判定、不发请求、不复制提交逻辑；
   * 覆盖与推导复用 GateSession.validateEntryDecisions / deriveEntryDecision（口径同 gates.py）。
   * 本段只新增，不改动既有闸门逻辑/样式/渲染路径。
   * ------------------------------------------------------------------------ */
  function bridgePending() {
    var pending = pendingInfo(state.viewData);
    if (!pending || pending.kind !== "gate" || !pending.gate) return null;
    ensureDraft(pending);
    return pending;
  }

  window.GateDraftBridge = {
    required: function () {
      var pending = pendingInfo(state.viewData);
      return !!(pending && pending.kind === "gate" && entryDecisionsRequired(pending));
    },
    options: function () {
      var pending = pendingInfo(state.viewData);
      if (!pending || pending.kind !== "gate") return [];
      return gateOptionsFor(pending).map(function (option) {
        return {
          value: String(option.value),
          label: String(option.label || option.value),
          requires_reason: option.requires_reason === true
        };
      });
    },
    rows: function () {
      var pending = pendingInfo(state.viewData);
      if (!pending || pending.kind !== "gate") return [];
      return entryRows(pending).map(function (row) {
        return { id: row.id, kinds: row.kinds.slice(), unresolved: !!row.unresolved };
      });
    },
    get: function (id) {
      var store = state.gateDraft && state.gateDraft.entryDecisions ? state.gateDraft.entryDecisions : {};
      var current = store[String(id)];
      return current && typeof current === "object"
        ? { decision: current.decision || null, reason: current.reason || "" }
        : { decision: null, reason: "" };
    },
    set: function (id, decision, reason) {
      var pending = bridgePending();
      if (!pending) return null;
      var current = entryDraftOf(String(id));
      current.decision = decision === null || decision === undefined || decision === "" ? null : String(decision);
      current.reason = reason === null || reason === undefined ? "" : String(reason);
      var derived = derivedEntryDecision(pending);
      if (derived) state.gateDraft.decision = derived;
      maybePrefillGateReason(pending, derived); /* U8-b：桥写入同样参与理由复用 */
      syncGateForms();
      return window.GateDraftBridge.get(id);
    },
    counts: function () {
      var pending = bridgePending();
      var store = state.gateDraft && state.gateDraft.entryDecisions ? state.gateDraft.entryDecisions : {};
      if (!pending) return { entries: 0, disposed: 0, complete: false, error: "当前没有待决策闸门" };
      var ids = entryRows(pending).map(function (row) { return row.id; });
      var allowed = gateOptionsFor(pending).map(function (option) { return String(option.value); });
      var disposed = 0;
      ids.forEach(function (id) {
        var current = store[id];
        if (current && allowed.indexOf(String(current.decision || "")) >= 0) disposed++;
      });
      var check = window.GateSession.validateEntryDecisions(store, ids, allowed);
      return {
        entries: ids.length,
        disposed: disposed,
        complete: !!(check && check.ok),
        error: check ? check.error : null
      };
    },
    openGateView: function () { showView("gate"); }
  };

  async function init() {
    /* U7（SPEC-REV-08）：先取深链，再让 showView 用 replaceState 改写 hash。 */
    var deep = window.RunSessionUrl ? window.RunSessionUrl.decode(location.hash) : { runId: null, view: null };
    bindStatic();
    renderAll();
    showView("s0");
    if (window.S0Workbench) window.S0Workbench.init(api);
    if (window.AgentWindow) window.AgentWindow.init(api);
    if (window.NodeDetail) window.NodeDetail.init(api);
    await Promise.allSettled([loadHealth(false), loadBaselines(false)]);
    try {
      await loadRuns();
    } catch (e) {
      state.runsError = errText(e);
      state.connError = errText(e);
    }
    if (state.setup.project) await checkProject(true);
    /* U7：深链恢复——openRun 会在等闸门时自动落闸门视图；深链显式 view=gate 则强制之。 */
    if (deep.runId) {
      await openRun(deep.runId);
      if (deep.view === "gate") showView("gate");
    } else if (deep.view && VIEW_META[deep.view] && deep.view !== "s0") {
      showView(deep.view);
    }
    renderAll();
    poll();
    setInterval(function () {
      if (document.hidden) {
        if (Date.now() - state.lastPollAt >= HIDDEN_POLL_MS) poll();
      } else {
        poll();
      }
    }, POLL_MS);
    /* U7：手动改 hash / 外部跳深链时与当前状态比对后执行（replaceState 不触发本事件，无回环）。 */
    window.addEventListener("hashchange", function () {
      if (!window.RunSessionUrl) return;
      var d = window.RunSessionUrl.decode(location.hash);
      if (d.runId && d.runId !== state.runId) { openRun(d.runId); return; }
      if (d.view && d.view !== state.view) showView(d.view);
    });
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) { stopFlash(); poll(); }
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
