/* 变更影响闭环 · 运营台 v1（app.js）
 *
 * 定位（spec §1 / §9）：界面投影服务端状态并传输操作，不持有业务判据。
 *   · 数据只消费：/api/health、/api/runs、/api/runs/{id}、/api/baselines、
 *     /api/env/check、/api/fs/dirs、POST /api/runs、闸门决策、job 取消、证据存在性探测。
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
    run_started: 1, run_finished: 1, run_failed: 1,
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

  // 基线拒绝的结构化字段（Web UI §9）：missing=缺件，errors=schema/身份/指纹/链违规。
  // 只展示服务端下发内容，不在前端重新推导或猜测原因。
  function errDetailText(e) {
    var d = e && e.body && e.body.detail;
    if (!d || typeof d !== "object") return "";
    var parts = [];
    if (Array.isArray(d.missing) && d.missing.length) {
      parts.push("缺件：" + d.missing.join("、"));
    }
    if (Array.isArray(d.errors) && d.errors.length) {
      parts.push("违规：" + d.errors.slice(0, 3).join("、"));
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
    var text = "连接失败：" + state.connError;
    if (state.lastOkAt) text += " · 最后成功 " + fmtClock(state.lastOkAt);
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

  async function fetchRunView() {
    if (!state.runId) return false;
    var runId = state.runId;
    var epoch = state.selectionEpoch;
    var request = ++state.detailRequest;
    function current() {
      return state.runId === runId && state.selectionEpoch === epoch && state.detailRequest === request;
    }
    try {
      var view = await api("/api/runs/" + enc(runId));
      if (!current()) return false;
      state.viewData = view;
      state.viewError = null;
      return true;
    } catch (e) {
      if (!current()) return false;
      state.viewError = errText(e);
      throw e;
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
      if (state.runId) {
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
  }

  async function openRun(id) {
    if (!id) return;
    if (window.AgentWindow) window.AgentWindow.close();
    state.runId = String(id);
    state.selectionEpoch++;
    state.viewData = null;
    state.viewError = null;
    state.stageOverride = "auto";
    resetGateDraft();
    showView("run");
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

  function renderSidebar() {
    var host = $("runList");
    if (!host) return;
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

  function renderBaselineMeta() {
    var host = $("setupBaselineMeta");
    if (!host) return;
    clearEl(host);
    if (state.baselinesError) {
      host.appendChild(h("span", "muted", "基线接口不可用（见上方提示）"));
      return;
    }
    if (!state.baselines.length) {
      host.appendChild(h("span", "muted", state.baselinesLoading ? "加载中…" : "没有可用的基线版本"));
      return;
    }
    var b = findBaseline(state.setup.baseline);
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
    } else {
      var missing = b.missing && b.missing.length ? "：" + b.missing.join("、") : "";
      var why = b.errors && b.errors.length ? "（" + b.errors.join("；") + "）" : "";
      host.appendChild(chipEl("manifest 不可用" + missing + why, "bad"));
    }
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
  async function submitSetup() {
    if (state.setup.submitting || !canStart()) return;
    state.setup.submitting = true;
    state.setup.error = null;
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
      var run = await api("/api/runs", { method: "POST", body: body });
      if (!run || !run.run_id) throw new Error("服务端未返回 run_id");
      toast("已创建运行：" + run.run_id);
      try { await loadRuns(); } catch (eLoad) { /* 列表刷新失败不阻断进入运行视图 */ }
      await openRun(run.run_id);
    } catch (e) {
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

  function renderRunHead(v) {
    var host = $("runHead");
    if (!host) return;
    clearEl(host);
    host.appendChild(h("span", "rid mono", state.runId));
    if (!v) {
      host.appendChild(h("span", "status-pill run", "加载中…"));
      if (state.viewError) host.appendChild(h("span", "chip bad", "读取失败"));
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
    var ok = true;
    try { ok = window.confirm("确认取消作业 " + job.job_id + "？"); } catch (e) { ok = true; }
    if (!ok) return;
    if (cancelBtn) cancelBtn.disabled = true;
    if (refreshBtn) refreshBtn.disabled = true;
    try {
      await api("/api/runs/" + enc(state.runId) + "/jobs/" + enc(job.job_id) + "/cancel", { method: "POST" });
      toast("已请求取消作业 " + job.job_id);
      await poll();
    } catch (e) {
      toast("取消失败：" + e.message);
    } finally {
      if (refreshBtn) refreshBtn.disabled = false;
    }
  }

  function renderRunAlerts(v) {
    var host = $("runAlerts");
    if (!host) return;
    clearEl(host);
    if (state.viewError) {
      host.appendChild(h("div", "alert bad", "读取运行视图失败：" + state.viewError + "（当前显示最近一次成功的数据）"));
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

  function pendingInfo(v) {
    var raw = v && v.pending_interrupt;
    if (!raw || typeof raw !== "object") return null;
    var payload = raw.payload && typeof raw.payload === "object" ? raw.payload : {};
    var gate = payload.gate || (typeof raw.id === "string" ? raw.id.split(":")[0] : "");
    if (!gate) return null;
    var node = payload.gate_node || nodeOfGate(gate);
    return {
      raw: raw,
      gate: String(gate),
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
      box.appendChild(h("div", "tiny warn", "未纳入四段展示的节点（按 node_history 显式列出，不隐藏）："));
      var chips = h("div", "chips");
      extra.forEach(function (n) { chips.appendChild(h("span", "chip warn", n)); });
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
    var wrap = h("div", "snode" + (meta.gate ? " gate" : "") + (st ? " " + st : ""));
    var bubble = h("div", "sb");
    bubble.appendChild(h("span", null, nodeIcon(st)));
    var txt = h("div", "st");
    txt.appendChild(h("b", null, nodeId + " " + (meta.name || "")));
    txt.appendChild(h("span", "own", meta.owner || "—"));
    wrap.appendChild(bubble);
    wrap.appendChild(txt);
    wrap.title = nodeId + " " + (meta.name || "") + " · owner=" + (meta.owner || "—") + " · 状态=" + (st || "待开始");
    return wrap;
  }

  /* ---------------- Agent 卡 ---------------- */
  function renderAgents(v) {
    var host = $("agents");
    if (!host) return;
    clearEl(host);
    if (!v) {
      host.appendChild(h("div", "muted tiny", "运行视图加载中…"));
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
      if (window.AgentWindow && runId) window.AgentWindow.open({runId: runId, name: name, nodes: nodes,
        node: a && a.active_node && nodes.indexOf(a.active_node) >= 0 ? a.active_node : nodes[0]});
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
    var facts = capabilityLine(a && a.capabilities);
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

  function capabilityLine(c) {
    if (!c) return "";
    var impl = c.implemented === true ? "已实现" : (c.implemented === false ? "未实现" : "未知");
    var dep = c.dependencies_ready === true ? "齐备" : (c.dependencies_ready === false ? "缺失" : "未知");
    var execMap = { not_started: "未开始", standin: "替身", real: "真实", unknown: "未知" };
    var exec = execMap[c.execution] || "未知";
    var scope = c.verification_scope ? String(c.verification_scope) : "未知";
    return "能力 实现 " + impl + " · 依赖 " + dep + " · 本次 " + exec + " · 验证范围 " + scope;
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
    if (!pending || !pending.gate) {
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
      host.appendChild(h("div", "muted tiny", "运行视图加载中…"));
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
      host.appendChild(h("div", "muted tiny", "运行视图加载中…"));
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
      host.appendChild(h("div", "muted tiny", "运行视图加载中…"));
      return;
    }
    var job = v && v.job;
    if (!job) {
      host.appendChild(h("div", "muted tiny", "当前没有作业记录（N9 全跑尚未提交或未启动）。"));
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
    if (!v) {
      setText("eventsSummary", "事件流 · 运行视图加载中…");
      return;
    }
    var all = ((v && v.events) || []).filter(function (e) { return e && EVENT_WHITELIST[e.kind]; });
    setText("eventsSummary", "事件流 · " + all.length + " 条白名单事件（seq 递增 · 只读 · 折叠）");
    var shown = all.slice(-60).reverse();
    shown.forEach(function (e) {
      var row = h("div", "ev-row");
      row.appendChild(h("span", "k", "#" + (e.seq !== undefined && e.seq !== null ? pad(e.seq, 3) : "?")));
      row.appendChild(h("span", "n", e.node || "—"));
      row.appendChild(h("span", "d", eventText(e)));
      list.appendChild(row);
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
      if (state.viewError) alerts.appendChild(h("div", "alert bad", "读取运行视图失败：" + state.viewError));
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
      host.appendChild(h("span", "status-pill run", "加载中…"));
      return;
    }
    var pending = pendingInfo(v);
    var pill = h("span", "status-pill " + (pending ? "wait" : statusKind(v.status)));
    if (pending) pill.appendChild(h("span", "pulse"));
    pill.appendChild(document.createTextNode(" " + (pending ? "等待人工 · " + gateTitle(pending.gate) : statusLabel(v.status))));
    host.appendChild(pill);
    host.appendChild(h("span", "chip", v.mode || "—"));
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

  function renderDiffEntries(host, pending, opts) {
    if (!host) return;
    var o = opts || {};
    var d = diffPayloadOf(pending);
    if (!d) {
      host.appendChild(h("div", "alert warn", "服务端未下发 N2 差异清单（difference_items 缺失）。"));
      return;
    }
    var entries = Array.isArray(d.entries) ? d.entries : [];
    if (!o.hideHead) {
      var head = h("div", "diff-head");
      head.appendChild(h("b", null, diffSummaryText(pending)));
      if (d.has_change === false) head.appendChild(chipEl("无变更", "ok"));
      if (d.self_check_ok === true) head.appendChild(chipEl("self_check_ok", "ok"));
      else if (d.self_check_ok === false) head.appendChild(chipEl("self_check 未通过", "warn"));
      if (d.mode) head.appendChild(chipEl(String(d.mode), ""));
      host.appendChild(head);
    }
    if (d.error) {
      host.appendChild(h("div", "alert bad", "差异清单解析失败：" + String(d.error)));
    }
    if (d.present === false) {
      host.appendChild(h("div", "alert warn", "N2 产物缺失：无法逐条核对，不得确认。"));
      return;
    }
    if (!entries.length) {
      host.appendChild(h("div", "muted tiny", "本轮没有差异条目。"));
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
      var unresolved = !!e.unresolved;
      var item = h("div", "diff-item" + (unresolved ? " unresolved" : ""));
      var line = h("div", "diff-line");
      line.appendChild(h("span", "diff-id",
        e.entry_id ? String(e.entry_id) : "（无 entry_id）"));
      if (e.kind) line.appendChild(h("span", "chip", String(e.kind)));
      if (e.change) line.appendChild(h("span", "chip", String(e.change)));
      if (unresolved) line.appendChild(chipEl("未决", "warn"));
      if (e.legacy_drill_fixture) line.appendChild(chipEl("drill 历史夹具", ""));
      item.appendChild(line);

      var meta = [];
      if (e.segment) meta.push("segment " + String(e.segment));
      if (e.offset) meta.push("offset " + String(e.offset));
      if (Array.isArray(e.lines) && e.lines.length) meta.push("lines " + e.lines.join(", "));
      if (meta.length) item.appendChild(h("div", "diff-meta", meta.join(" · ")));
      if (unresolved) {
        item.appendChild(h("div", "diff-unresolved", "未决原因：" + String(e.unresolved)));
      }
      item.appendChild(h("div", "diff-ev" + (e.evidence ? "" : " muted"),
        e.evidence ? String(e.evidence) : "（无 evidence）"));
      list.appendChild(item);
    });
    host.appendChild(list);
    if (d.path) host.appendChild(h("div", "foot-note mono", String(d.path)));
  }

  function renderGateMaterial(v) {
    var host = $("gateMaterial");
    if (!host) return;
    clearEl(host);
    if (!state.runId) {
      host.appendChild(h("div", "muted tiny", "尚未选择运行。"));
      return;
    }
    if (!v) {
      host.appendChild(h("div", "muted tiny", "加载中…"));
      return;
    }
    var pending = pendingInfo(v);
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
    addKV(host, "闸门", pending.gate);
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
    var options = (v && v.gate_options && v.gate_options[pending.gate]) || null;
    if (!options && pending.payload && pending.payload.decision_options) {
      options = pending.payload.decision_options;
    }
    if (!Array.isArray(options)) return [];
    return options.filter(function (o) { return o && o.value !== undefined && o.value !== null; });
  }

  function renderGatePanel(v) {
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
      host.appendChild(h("div", "muted tiny", "加载中…"));
      return;
    }
    var pending = pendingInfo(v);
    if (!pending || !pending.gate) {
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

  function gateSessionKey(pending) {
    return JSON.stringify([state.runId, pending.id, pending.gate, pending.cycle]);
  }

  function ensureDraft(pending) {
    var key = gateSessionKey(pending);
    if (state.gateDraft.key === key) {
      if (!gateOptionsFor(pending).some(function (o) { return o.value === state.gateDraft.decision; })) {
        state.gateDraft.decision = null;
      }
      return;
    }
    state.gateDraft = {
      key: key,
      gate: pending.gate,
      decision: null,
      actor: "human:",
      reason: "",
      submitting: false,
      error: null,
      blockers: null,
      note: null
    };
  }

  function ensureGateForm(container, pending, compact) {
    ensureDraft(pending);
    var key = gateSessionKey(pending) + "|" + JSON.stringify(gateOptionsFor(pending));
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
    }

    var options = gateOptionsFor(pending);
    var list = h("div", "gate-options");
    if (!options.length) {
      list.appendChild(h("div", "alert bad", "服务端未下发决策选项（gate_options / decision_options 缺失）⇒ 不可提交。"));
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
    actorInput.value = state.gateDraft.actor;
    actorInput.setAttribute("aria-label", "actor");
    actorInput.style.maxWidth = "220px";
    actorInput.addEventListener("input", function () {
      state.gateDraft.actor = actorInput.value;
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

    container.appendChild(form);
  }

  function updateGateForm(container, pending) {
    var form = container.querySelector(".gate-form");
    if (!form) return;
    var options = gateOptionsFor(pending);
    var d = state.gateDraft;
    d.submitting = !!state.gateSubmissions[d.key];
    var labels = form.querySelectorAll(".option");
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
    if (submit) {
      var offered = options.some(function (o) { return o.value === d.decision; });
      submit.disabled = !offered || d.submitting;
      submit.textContent = d.submitting ? "提交中…" : "提交闸门决策";
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
    state.gateDraft = {
      key: null, gate: null, decision: null, actor: "human:", reason: "",
      submitting: false, error: null, blockers: null, note: null
    };
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
    if (!pending || !pending.gate) {
      toast("当前没有待决策闸门");
      return;
    }
    ensureDraft(pending);
    var d = state.gateDraft;
    if (state.gateSubmissions[d.key]) return;
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
    if (!String(d.actor || "").trim()) {
      d.error = "必须填写 actor（且以 human 开头）。";
      syncGateForms();
      return;
    }
    d.submitting = true;
    state.gateSubmissions[d.key] = true;
    d.error = null;
    d.blockers = null;
    d.note = null;
    syncGateForms();
    var runId = state.runId;
    var epoch = state.selectionEpoch;
    function sameSelection() { return state.runId === runId && state.selectionEpoch === epoch; }
    function currentSubmission() {
      var current = pendingInfo(state.viewData);
      return sameSelection() && state.gateDraft === d && current && gateSessionKey(current) === d.key;
    }
    try {
      await api("/api/runs/" + enc(runId) + "/gates/" + enc(pending.gate) + "/decision", {
        method: "POST",
        body: {
          decision: d.decision,
          actor: String(d.actor || "").trim(),
          reason: String(d.reason || "").trim() || null
        }
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
      delete state.gateSubmissions[d.key];
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
  }

  async function init() {
    bindStatic();
    renderAll();
    showView("s0");
    if (window.S0Workbench) window.S0Workbench.init(api);
    if (window.AgentWindow) window.AgentWindow.init(api);
    await Promise.allSettled([loadHealth(false), loadBaselines(false)]);
    try {
      await loadRuns();
    } catch (e) {
      state.runsError = errText(e);
      state.connError = errText(e);
    }
    if (state.setup.project) await checkProject(true);
    renderAll();
    poll();
    setInterval(function () {
      if (document.hidden) {
        if (Date.now() - state.lastPollAt >= HIDDEN_POLL_MS) poll();
      } else {
        poll();
      }
    }, POLL_MS);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) poll();
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
