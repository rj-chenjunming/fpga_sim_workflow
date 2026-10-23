/* 节点执行详情面板（SPEC-04 §4.2.1；SPEC-REV-02 R1「人话优先」/ R2 闸门二级清单 / §4 前端渲染约定）。
 *
 * 边界：
 *   · 独立 <dialog>，自带状态；执行视图每 1.5 s 全量重建 #stages 不会清掉本面板。
 *   · 只读投影：不做判定、不排序材料、不隐藏缺失；状态显示服务端原值，不折算成"完成/失败"。
 *   · 数据唯一来源 GET /api/runs/{run_id}/nodes/{node}；响应对不上当前身份时拒绝渲染。
 *   · 首屏读「这一步做什么 / 结果 / 关键数字 / 过程」；`seq` 只在默认收起的「原始记录」里，
 *     并在该区顶部解释它是事件流水号（只用于排序/排查，不是业务状态）。
 *   · 证据只做存在性探测（GET .../evidence/exists），不在页面打开文件正文；
 *     唯一的文件正文例外是 P-28 的报告只读视图（GET .../report，白名单 + 只读 + 有上限）。
 *   · 闸门逐条处置只写共享 gate-session 草稿（window.GateDraftBridge），本面板绝不发 POST；
 *     提交入口仍只有闸门视图表单（SPEC-REV-02 §R2.2）。
 *   · 差异对比浮窗用页内 overlay；报告全文浮窗用公共 report-viewer.js 的独立 <dialog>
 *     （N12 面板与 G2 材料共用一次点击入口）。Esc 只关上层、焦点回到触发按钮；窄屏全屏。
 *   · 并发/过期回包用 epoch + request 双守卫；切换节点或关闭窗口后旧回包一律丢弃。
 */
"use strict";
window.NodeDetail = (function () {
  var api = null;
  var s = {
    open: false, epoch: 0, request: 0, target: null, data: null, trigger: null,
    gateBridge: null, overlay: null, overlayTrigger: null, overlaySeq: 0
  };

  /* 执行方式：服务端 source 原值 + 一句中文说明（展示映射，不改原值）。 */
  var SOURCE_LABELS = {
    kb_tool: "真实工具",
    drill_fixture: "drill 演示数据（不碰真实环境）",
    model_live: "模型（真实调用）",
    model_standin: "模型（替身）",
    human_gate: "人工签署",
    framework: "框架自动"
  };

  /* 展示名（服务端枚举/决策原值仍逐字保留）。 */
  var DISPOSITION_LABELS = { confirmed: "已确认", ignored: "忽略", disputed: "有疑义" };
  var DECISION_LABELS = {
    confirmed: "差异确认", ignored: "忽略", disputed: "有疑义",
    accept: "接受", rework: "返工",
    full_now: "全量回归", subset_only: "子集回归", milestone_only: "仅里程碑", defer: "暂缓"
  };
  var CHANGE_LABELS = { modified: "修改", added: "新增", deleted: "删除", created: "新增", removed: "删除" };
  var DEFAULT_DISPOSITIONS = [
    { value: "confirmed", label: "已确认" },
    { value: "ignored", label: "忽略" },
    { value: "disputed", label: "有疑义" }
  ];

  function $(id) { return document.getElementById(id); }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function clear(node) { if (node) node.replaceChildren(); }

  function enc(v) { return encodeURIComponent(v === undefined || v === null ? "" : String(v)); }

  function pad(n, width) {
    var out = String(n);
    while (out.length < width) out = "0" + out;
    return out;
  }

  function isMissing(v) { return v === null || v === undefined; }

  function textOf(v) {
    if (isMissing(v)) return null;
    if (typeof v === "string") return v;
    if (typeof v === "number" || typeof v === "boolean") return String(v);
    try { return JSON.stringify(v, null, 2); } catch (e) { return String(v); }
  }

  function plain(v) { return !!v && typeof v === "object" && !Array.isArray(v); }

  function parseTs(v) {
    if (isMissing(v) || v === "") return null;
    if (typeof v === "number") {
      var byNumber = new Date(v * 1000);
      return isNaN(byNumber.getTime()) ? null : byNumber;
    }
    var raw = String(v).trim();
    var nonIso = raw.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})([+-]\d{2})(\d{2})$/);
    if (nonIso) {
      var fixed = new Date(nonIso[1] + "-" + nonIso[2] + "-" + nonIso[3] + "T" +
        nonIso[4] + ":" + nonIso[5] + ":" + nonIso[6] + nonIso[7] + ":" + nonIso[8]);
      if (!isNaN(fixed.getTime())) return fixed;
    }
    var parsed = new Date(raw);
    return isNaN(parsed.getTime()) ? null : parsed;
  }

  function fmtTs(v) {
    var d = parseTs(v);
    if (!d) return isMissing(v) || v === "" ? null : String(v);
    return d.getFullYear() + "-" + pad(d.getMonth() + 1, 2) + "-" + pad(d.getDate(), 2) + " " +
      pad(d.getHours(), 2) + ":" + pad(d.getMinutes(), 2) + ":" + pad(d.getSeconds(), 2);
  }

  function fmtClock(v) {
    var d = parseTs(v);
    if (!d) return null;
    return pad(d.getHours(), 2) + ":" + pad(d.getMinutes(), 2) + ":" + pad(d.getSeconds(), 2);
  }

  function fmtDuration(started, finished) {
    var a = parseTs(started);
    var b = parseTs(finished);
    if (!a || !b) return null;
    var seconds = Math.max(0, Math.round((b.getTime() - a.getTime()) / 1000));
    if (seconds < 60) return "用时 " + seconds + " 秒";
    var minutes = Math.floor(seconds / 60);
    if (minutes < 60) return "用时 " + minutes + " 分 " + (seconds % 60) + " 秒";
    var hours = Math.floor(minutes / 60);
    return "用时 " + hours + " 小时 " + (minutes % 60) + " 分";
  }

  function sourceLabel(source) {
    if (isMissing(source) || source === "") return null;
    var key = String(source);
    return SOURCE_LABELS[key] ? SOURCE_LABELS[key] + "（" + key + "）" : key;
  }

  function isFixtureSource(source) {
    return !isMissing(source) && /drill|fixture|standin/i.test(String(source));
  }

  function errText(e) {
    if (!e) return "未知错误";
    var status = e.status ? "HTTP " + e.status + "：" : "";
    return status + (e.message ? String(e.message) : String(e));
  }

  function isCurrent(token) {
    return s.open && !!s.target && s.epoch === token && $("nodeDetail") && $("nodeDetail").open;
  }

  function setText(id, text) {
    var node = $(id);
    if (node) node.textContent = text === undefined || text === null ? "" : String(text);
  }

  function showError(message) {
    var host = $("ndError");
    if (!host) return;
    clear(host);
    if (!message) return;
    var box = el("div", "alert bad");
    box.appendChild(el("b", null, "节点详情读取失败："));
    box.appendChild(document.createTextNode(String(message)));
    host.appendChild(box);
    var hint = el("div", "tiny muted");
    hint.textContent = "面板只消费 GET /api/runs/{run_id}/nodes/{node}（SPEC-04 §6.7）；不回退为前端自行拼装投影。";
    host.appendChild(hint);
  }

  function setLoading(loading) {
    var loadingEl = $("ndLoading");
    var contentEl = $("ndContent");
    if (loadingEl) loadingEl.classList.toggle("hidden", !loading);
    if (contentEl) contentEl.classList.toggle("hidden", loading);
    var refresh = $("ndRefresh");
    if (refresh) refresh.disabled = !!loading;
  }

  function failStatus(message) {
    setLoading(false);
    setText("ndStatus", "读取失败");
    var statusEl = $("ndStatus");
    if (statusEl) statusEl.className = "chip bad";
    showError(message);
  }

  /* ---------------- 服务端展示字段（story）读取与状态释义 ---------------- */

  function storyOf(view) {
    return view && view.story && typeof view.story === "object" && !Array.isArray(view.story) ? view.story : {};
  }

  function glossaryOf(view) {
    var g = storyOf(view).status_glossary;
    return g && typeof g === "object" && !Array.isArray(g) ? g : null;
  }

  /* 状态原值逐字保留；中文释义只追加，不替换（P-07）。 */
  function statusText(view, status) {
    var raw = isMissing(status) || status === "" ? "未下发" : String(status);
    if (raw === "未下发") return raw;
    var note = null;
    if (view) {
      var story = storyOf(view);
      if (!isMissing(story.status_note) && story.status_note !== "") note = String(story.status_note);
    }
    if (!note) {
      var glossary = glossaryOf(view);
      if (glossary && !isMissing(glossary[raw]) && glossary[raw] !== "") note = String(glossary[raw]);
    }
    return note ? raw + " " + note : raw;
  }

  function stepStatusText(view, status) {
    var raw = isMissing(status) || status === "" ? "未下发" : String(status);
    var glossary = glossaryOf(view);
    var note = glossary && !isMissing(glossary[raw]) && glossary[raw] !== "" ? String(glossary[raw]) : null;
    return note ? raw + " " + note : raw;
  }

  function labelOf(map, value) {
    var raw = String(value);
    return map[raw] ? map[raw] + "（" + raw + "）" : raw;
  }

  function changeLabel(value) {
    var raw = String(value);
    return CHANGE_LABELS[raw] ? CHANGE_LABELS[raw] + "（" + raw + "）" : raw;
  }

  function linesText(lines) {
    var arr = Array.isArray(lines) ? lines.filter(function (v) { return typeof v === "number"; }) : [];
    if (!arr.length) return null;
    if (arr.length === 2 && arr[1] === arr[0] + 1) return "第 " + arr[0] + "–" + arr[1] + " 行";
    return "第 " + arr.join("、") + " 行";
  }

  /* ---------------- 浮窗（页内 overlay）通用管理 ---------------- */

  function openOverlay(id, trigger) {
    var overlay = $(id);
    if (!overlay) return false;
    s.overlay = id;
    s.overlayTrigger = trigger || document.activeElement || null;
    s.overlaySeq = (s.overlaySeq || 0) + 1;
    overlay.classList.remove("hidden");
    var closeBtn = overlay.querySelector(".nd-overlay-close");
    if (closeBtn) { try { closeBtn.focus(); } catch (e) { /* focus 失败不阻断 */ } }
    return true;
  }

  function closeOverlay(restoreFocus) {
    var id = s.overlay;
    if (!id) return;
    var overlay = $(id);
    if (overlay) overlay.classList.add("hidden");
    s.overlay = null;
    s.overlaySeq = (s.overlaySeq || 0) + 1;
    var trigger = s.overlayTrigger;
    s.overlayTrigger = null;
    if (restoreFocus !== false && trigger && trigger.isConnected) {
      try { trigger.focus(); } catch (e) { /* 保留当前焦点 */ }
    }
  }

  /* ---------------- 打开 / 读取 / 关闭 ---------------- */

  function open(options) {
    var dialog = $("nodeDetail");
    if (!dialog || !options || !options.runId || !options.node) return;
    s.epoch++;
    s.request++;
    s.open = true;
    s.data = null;
    s.gateBridge = options.gateBridge || null;
    s.target = {
      runId: String(options.runId),
      node: String(options.node),
      fallback: options.fallback || null,
      agent: options.agent || null,
      gate: !!options.gate,
      onGate: typeof options.onGate === "function" ? options.onGate : null
    };
    s.trigger = options.trigger || document.activeElement || null;

    closeOverlay(false);
    setText("ndTitle", s.target.node + (s.target.fallback && s.target.fallback.name ? " " + s.target.fallback.name : ""));
    setText("ndSub", s.target.runId + " / " + s.target.node + " · 只读投影（authority=projection）");
    setText("ndPath", "GET /api/runs/" + s.target.runId + "/nodes/" + s.target.node);
    var statusEl = $("ndStatus");
    if (statusEl) {
      statusEl.className = "chip";
      statusEl.textContent = "加载中";
    }
    clear($("ndError"));
    clear($("ndMeta"));
    clear($("ndPurpose"));
    clear($("ndModeNote"));
    clear($("ndHeadline"));
    clear($("ndNote"));
    clear($("ndReport"));
    clear($("ndGate"));
    clear($("ndKey"));
    clear($("ndSteps"));
    clear($("ndIdentity"));
    clear($("ndAgentJump"));
    clear($("ndEvents"));
    clear($("ndSummaryRaw"));
    clear($("ndDetailBody"));
    clear($("ndRefs"));
    clear($("ndFailure"));
    clear($("ndMissing"));
    var gateBlock = $("ndGateBlock");
    if (gateBlock) gateBlock.classList.add("hidden");
    var raw = $("ndRaw");
    if (raw) raw.open = false;
    setLoading(true);

    if (!dialog.open) {
      try { dialog.showModal(); } catch (e) { dialog.setAttribute("open", "open"); }
    }
    load();
  }

  async function load() {
    if (!s.open || !s.target) return;
    var token = s.epoch;
    var sequence = ++s.request;
    var target = s.target;
    setLoading(true);
    showError("");
    setText("ndStatus", "加载中");
    try {
      var response = await api("/api/runs/" + enc(target.runId) + "/nodes/" + enc(target.node));
      if (!isCurrent(token) || sequence !== s.request) return;
      if (response && response.run_id && String(response.run_id) !== target.runId) {
        failStatus("响应身份不符：请求 " + target.runId + "，回包 " + response.run_id + "（已拒绝渲染）。");
        return;
      }
      if (response && response.node && String(response.node) !== target.node) {
        failStatus("响应节点不符：请求 " + target.node + "，回包 " + response.node + "（已拒绝渲染）。");
        return;
      }
      s.data = response || {};
      render(s.data);
      setLoading(false);
    } catch (e) {
      if (!isCurrent(token) || sequence !== s.request) return;
      s.data = null;
      failStatus(errText(e));
    }
  }

  function focusChip(node) {
    if (s.trigger && s.trigger.isConnected) {
      try { s.trigger.focus(); return; } catch (e) { /* fall through */ }
    }
    var candidates = document.querySelectorAll("[data-node-chip]");
    for (var i = 0; i < candidates.length; i++) {
      if (candidates[i].getAttribute("data-node-chip") !== node) continue;
      if (!candidates[i].getClientRects().length) continue;
      try { candidates[i].focus(); return; } catch (e2) { /* keep looking */ }
    }
  }

  function close() {
    var dialog = $("nodeDetail");
    var node = s.target ? s.target.node : null;
    closeOverlay(false);
    s.epoch++;
    s.request++;
    s.open = false;
    s.data = null;
    s.target = null;
    s.gateBridge = null;
    if (dialog && dialog.open) dialog.close();
    s.trigger = null;
    if (node) focusChip(node);
  }

  /* ---------------- 渲染：一句话 → 结果 → 差异清单 → 关键数字 → 过程 → 证据 → 原始记录 ---------------- */

  function statusChip(view) {
    var raw = isMissing(view.status) || view.status === "" ? "未下发" : String(view.status);
    var chip = el("span", "chip mono" + (isMissing(view.status) || view.status === "" ? " warn" : ""),
      statusText(view, view.status));
    chip.title = "服务端原值：" + raw + "；中文只是释义，原值逐字保留。";
    return chip;
  }

  function metaChip(text, cls, title) {
    var chip = el("span", "chip" + (cls ? " " + cls : ""), text);
    if (title) chip.title = title;
    return chip;
  }

  function renderMeta(view) {
    var host = $("ndMeta");
    if (!host) return;
    var owner = view.owner || (s.target && s.target.fallback ? s.target.fallback.owner : null);
    if (owner) host.appendChild(metaChip("owner：" + String(owner)));
    var source = sourceLabel(view.source);
    var terminal = (Array.isArray(view.events) ? view.events : []).some(function (event) {
      return event && (event.kind === "node_finished" || event.kind === "node_failed");
    });
    if (source) {
      host.appendChild(metaChip(
        "执行方式：" + source,
        isFixtureSource(view.source) ? "warn" : "",
        isFixtureSource(view.source)
          ? "执行来源含夹具/替身标记：不是真实环境实测结论。"
          : "执行来源（服务端下发原值 + 中文说明）。"
      ));
    } else if (terminal) {
      host.appendChild(metaChip("执行方式：未下发", "warn"));
    } else {
      host.appendChild(metaChip("执行方式：等节点收尾后下发"));
    }
    if (!isMissing(view.run_status) && view.run_status !== "") {
      var finishedRun = view.run_terminal === true;
      host.appendChild(metaChip(
        "运行状态：" + String(view.run_status) + (finishedRun ? "（已终态）" : "（未终态）"),
        finishedRun ? "" : "warn",
        "服务端 run_status 原值；run_terminal 表示运行是否已到终态。"
      ));
    }
    var duration = fmtDuration(view.started_at, view.finished_at);
    if (duration) host.appendChild(metaChip(duration));
    var started = fmtClock(view.started_at);
    var finished = fmtClock(view.finished_at);
    if (started) host.appendChild(metaChip("开始 " + started));
    if (finished) host.appendChild(metaChip("结束 " + finished));
    if (isFixtureSource(view.source)) {
      host.appendChild(metaChip("夹具/替身：不是真机实测", "warn"));
    }
  }

  function renderPurpose(view) {
    var host = $("ndPurpose");
    if (!host) return;
    var story = storyOf(view);
    var purpose = story.purpose;
    if (isMissing(purpose) || purpose === "") {
      host.appendChild(el("div", "nd-empty", view.known === false
        ? "服务端未登记这个节点（known=false），没有一句话用途；下面只展示它的事件记录。"
        : "服务端未下发一句话用途（界面不补默认文案）。"));
      return;
    }
    host.appendChild(el("p", "nd-purpose-text", String(purpose)));
  }

  function renderModeNote(view) {
    var host = $("ndModeNote");
    if (!host) return;
    var source = String(view.source || "");
    var mode = String(view.mode || "");
    var drill = /drill|fixture/i.test(source) || mode === "drill";
    if (!drill) return;
    host.appendChild(el("div", "nd-mode-note",
      "演示（drill）运行：节点结果来自预置数据（夹具），不碰真实环境，也不验证环境搭建（S0）。" +
      "要验证环境搭建，请用左侧「环境准备」视图。"));
  }

  /* ---------------- 结果：story.headline + 黄条 + 报告只读入口（P-09/P-10/P-28） ---------------- */

  /* R3-08 兜底：只有服务端未下发 story.headline 时才用这句；文案本身不承诺"会跑完"。 */
  function notReachedHeadline(view) {
    var status = isMissing(view.run_status) || view.run_status === "" ? "未下发" : String(view.run_status);
    return "本轮没有走到这个节点（运行停在 " + status + "）。";
  }

  /* R3-12：headline_source 的授权消费者（summary → 原文摘要；missing → 未下发；template 不显示）。 */
  var HEADLINE_SRC_LABELS = { summary: "（原文摘要）", missing: "（未下发）" };

  function headlineSrcText(story) {
    if (!story || typeof story !== "object") return null;
    var raw = story.headline_source;
    if (isMissing(raw) || String(raw) === "") return null;
    var key = String(raw);
    return HEADLINE_SRC_LABELS[key] || null;
  }

  function renderResult(view) {
    var host = $("ndHeadline");
    if (!host) return;
    var story = storyOf(view);
    var headline = story.headline;
    var fromFallback = false;
    if (story.not_reached === true && (isMissing(headline) || String(headline) === "")) {
      headline = notReachedHeadline(view);
      fromFallback = true;
    }
    if (isMissing(headline) || String(headline) === "") {
      host.appendChild(el("div", "nd-empty", "结果一句话未下发（服务端未提供 story.headline；界面不补默认文案）。"));
    } else {
      var line = el("p", "nd-headline", String(headline));
      /* 只有服务端真下发了 headline 时才标注来源；兜底文案不冒充"原文摘要/未下发"。 */
      var src = fromFallback ? null : headlineSrcText(story);
      if (src) {
        var badge = el("span", "nd-headline-src", src);
        badge.title = "story.headline_source=" + String(story.headline_source) + "（服务端下发；template 时不显示）";
        line.appendChild(badge);
      }
      host.appendChild(line);
    }
    var noteHost = $("ndNote");
    if (noteHost) {
      var note = story.note;
      if (note && typeof note === "object" && !isMissing(note.text) && String(note.text) !== "") {
        var level = note.level === "info" ? "info" : "warn";
        noteHost.appendChild(el("div", "nd-note nd-note-" + level, String(note.text)));
      }
    }
    renderReportEntry(view);
  }

  function renderReportEntry(view) {
    var host = $("ndReport");
    if (!host) return;
    var report = view.report;
    if (!report || typeof report !== "object") return;  // 非 N12 不下发 report 块
    if (report.available !== true) {
      host.appendChild(el("div", "nd-empty", "本轮没有报告文件" +
        (!isMissing(report.file) && report.file !== "" ? "（" + String(report.file) + "）" : "") + "。"));
      return;
    }
    var button = el("button", "btn btn-sm nd-report-open", "查看报告全文");
    button.type = "button";
    button.setAttribute("aria-haspopup", "dialog");
    button.setAttribute("aria-label", "打开报告全文只读浮窗");
    button.addEventListener("click", function () { openReport(button); });
    host.appendChild(button);
    if (!isMissing(report.bytes)) host.appendChild(el("span", "tiny muted", " · " + String(report.bytes) + " B"));
    host.appendChild(el("div", "tiny muted", "只读；白名单仅本 run 的 n12_report.md（不接受任意路径）。"));
  }

  /* 报告全文浮窗由公共模块承载（P-28 / 裁决 #8）：N12 面板与 G2 材料共用一次点击入口。 */
  function openReport(trigger) {
    if (!s.open || !s.target) return;
    if (window.ReportViewer) {
      window.ReportViewer.open(s.target.runId, api, trigger);
      return;
    }
    var host = $("ndReport");
    if (host) host.appendChild(el("div", "alert bad", "报告浮窗模块未加载（report-viewer.js）。"));
  }

  /* ---------------- 闸门二级清单（P-15/P-17/P-18/P-29；SPEC-REV-02 §R2） ---------------- */

  function gateOf(view) {
    return view && view.gate && typeof view.gate === "object" && !Array.isArray(view.gate) ? view.gate : null;
  }

  function entryList(gate) {
    var entries = gate && Array.isArray(gate.entries) ? gate.entries : [];
    return entries.filter(function (entry) { return entry && typeof entry === "object"; });
  }

  function bridge() {
    return s.gateBridge || (typeof window.GateDraftBridge !== "undefined" ? window.GateDraftBridge : null);
  }

  function bridgeReady() {
    var b = bridge();
    if (!b || typeof b.required !== "function") return false;
    try { return !!b.required(); } catch (e) { return false; }
  }

  function bridgeGet(id) {
    var b = bridge();
    if (!b || typeof b.get !== "function") return null;
    try { return b.get(String(id)); } catch (e) { return null; }
  }

  function bridgeSet(id, decision, reason) {
    var b = bridge();
    if (!b || typeof b.set !== "function") return null;
    try { return b.set(String(id), decision, reason); } catch (e) { return null; }
  }

  function draftDecision(entry) {
    var got = bridgeGet(entry && entry.entry_id !== undefined ? entry.entry_id : "");
    return got && got.decision ? String(got.decision) : null;
  }

  function allowedDispositions() {
    var b = bridge();
    var offered = [];
    if (b && typeof b.options === "function") {
      try { offered = b.options() || []; } catch (e) { offered = []; }
    }
    if (!Array.isArray(offered) || !offered.length) return DEFAULT_DISPOSITIONS.map(function (d) { return { value: d.value, label: d.label }; });
    var out = [];
    DEFAULT_DISPOSITIONS.forEach(function (item) {
      for (var i = 0; i < offered.length; i++) {
        if (offered[i] && String(offered[i].value) === item.value) {
          out.push({ value: item.value, label: item.label });
          return;
        }
      }
    });
    if (out.length) return out;
    return offered.map(function (option) {
      return { value: String(option.value), label: String(option.label || option.value) };
    });
  }

  function entryMetaText(entry) {
    var parts = [];
    if (entry.entry_id) parts.push(baseName(String(entry.entry_id)));
    var lines = linesText(entry.lines);
    if (lines) parts.push(lines);
    if (!isMissing(entry.offset) && entry.offset !== "") parts.push("偏移 " + String(entry.offset));
    if (!isMissing(entry.change) && entry.change !== "") parts.push("变更 " + changeLabel(entry.change));
    if (Array.isArray(entry.kinds) && entry.kinds.length) parts.push(entry.kinds.map(String).join(" + "));
    return parts.join(" · ");
  }

  /* G2/G3 只读「待确认项」清单（裁决 #2）：只有清单，没有 disposition、没有勾选、不可改。
   * `gate.items` 由服务端给（G2=报告未闭环项+当前阻断项；G3=回归选集用例+未清冲突摘要）。 */
  var ITEM_KIND_LABELS = { blocker: "阻断", open_item: "未闭环", case: "用例", conflict: "冲突" };

  function gateIsG1(gate) {
    return !!gate && String(gate.gate || "") === "G1_diff_confirm";
  }

  function expectsReadOnlyItems() {
    var node = s.target ? String(s.target.node || "") : "";
    return node === "N13" || node === "N14";
  }

  function gateItemList(gate) {
    var items = gate && Array.isArray(gate.items) ? gate.items : [];
    return items.filter(function (item) { return item && typeof item === "object"; });
  }

  function renderGateItems(host, items) {
    var box = el("div", "nd-items");
    box.appendChild(el("div", "nd-items-head", "待确认项（只读，" + items.length + " 条）"));
    items.forEach(function (item) {
      var row = el("div", "nd-item");
      if (!isMissing(item.id) && item.id !== "") row.setAttribute("data-item-id", String(item.id));
      var kind = !isMissing(item.kind) && String(item.kind) !== "" ? String(item.kind) : null;
      if (kind) row.appendChild(el("span", "chip nd-item-kind", ITEM_KIND_LABELS[kind] || kind));
      var body = el("div", "nd-item-body");
      var title = !isMissing(item.title) && String(item.title).trim() !== "" ? String(item.title) : null;
      if (title) {
        body.appendChild(el("div", "nd-item-title", title));
      } else {
        body.appendChild(el("div", "nd-item-title missing", "未下发一句话（服务端未给 title；界面不编）"));
      }
      if (!isMissing(item.detail) && item.detail !== null && String(item.detail).trim() !== "") {
        body.appendChild(el("div", "nd-item-detail", String(item.detail)));
      }
      row.appendChild(body);
      if (!isMissing(item.severity) && item.severity !== null && String(item.severity) !== "") {
        var severity = String(item.severity);
        var cls = severity === "blocker" ? "bad" : severity === "warning" ? "warn" : "";
        row.appendChild(el("span", "chip nd-item-severity" + (cls ? " " + cls : ""), severity));
      }
      box.appendChild(row);
    });
    host.appendChild(box);
  }

  function appendGateJump(foot) {
    var jump = el("button", "btn btn-sm nd-gate-jump", "去闸门视图确认并提交 →");
    jump.type = "button";
    jump.setAttribute("aria-label", "关闭节点面板并跳到闸门视图（提交入口只有那里）");
    jump.addEventListener("click", goGateView);
    foot.appendChild(jump);
  }

  function summaryText(counts) {
    return "共 " + counts.total + " 条修订点，已处置 " + counts.disposed + " 条";
  }

  function gateCounts(view, gate) {
    var entries = entryList(gate);
    var total = entries.length;
    var rc = gate && gate.counts && typeof gate.counts === "object" ? gate.counts : {};
    if (typeof rc.revision_points === "number") total = rc.revision_points;
    var disposed = 0;
    if (gate.state === "waiting") {
      var b = bridge();
      var fromBridge = false;
      if (bridgeReady() && b && typeof b.counts === "function") {
        var counted = null;
        try { counted = b.counts(); } catch (e) { counted = null; }
        if (counted && typeof counted.disposed === "number") {
          disposed = counted.disposed;
          fromBridge = true;
        }
      }
      if (!fromBridge) {
        entries.forEach(function (entry) { if (draftDecision(entry)) disposed++; });
      }
    } else if (typeof rc.disposed === "number") {
      disposed = rc.disposed;
    } else {
      entries.forEach(function (entry) {
        if (entry.disposition && entry.disposition.decision) disposed++;
      });
    }
    return { total: total, disposed: disposed, entries: entries };
  }

  function fillRowState(gate, entry, cell, editable) {
    if (!cell) return;
    var value = editable
      ? draftDecision(entry)
      : (entry.disposition && entry.disposition.decision ? String(entry.disposition.decision) : null);
    if (value) {
      cell.className = "chip nd-gate-state";
      cell.textContent = labelOf(DISPOSITION_LABELS, value);
    } else {
      cell.className = "chip muted nd-gate-state";
      cell.textContent = "未处置";
    }
  }

  function renderGateRow(host, view, gate, entry, editable) {
    var id = String(entry.entry_id === undefined || entry.entry_id === null ? "" : entry.entry_id);
    var row = el("div", "nd-gate-row");
    row.setAttribute("data-entry-id", id);

    var checkLabel = el("label", "nd-gate-check");
    checkLabel.title = editable
      ? "勾选 = 已确认；忽略 / 有疑义请点「查看前后对比」逐条处置"
      : "已决策/只读：闸门权威只增不改，不能改判";
    var box = el("input");
    box.type = "checkbox";
    box.setAttribute("data-entry-check", id);
    box.setAttribute("aria-label", "处置条目 " + (entry.title ? String(entry.title) : id));
    if (editable) {
      box.checked = !!draftDecision(entry);
      var ready = bridgeReady();
      box.disabled = !ready;
      if (!ready) box.title = "当前运行没有待决策闸门：无法写入共享草稿";
      box.addEventListener("change", function () {
        if (!bridgeReady()) { box.checked = !box.checked; return; }
        var current = bridgeGet(id) || { decision: null, reason: "" };
        bridgeSet(id, box.checked ? "confirmed" : null, current.reason || "");
        updateGateSummary();
      });
    } else {
      box.checked = !!(entry.disposition && entry.disposition.decision);
      box.disabled = true;
    }
    checkLabel.appendChild(box);
    row.appendChild(checkLabel);

    var body = el("div", "nd-gate-body");
    if (isMissing(entry.title) || String(entry.title) === "") {
      body.appendChild(el("div", "nd-gate-title missing", "缺一句话说明（服务端未下发 title；界面不编）"));
    } else {
      body.appendChild(el("div", "nd-gate-title", String(entry.title)));
    }
    var metaLine = el("div", "nd-gate-meta");
    var metaText = entryMetaText(entry);
    if (metaText) metaLine.appendChild(el("span", null, metaText));
    if (entry.unresolved) {
      var badge = el("span", "chip warn nd-gate-unresolved", "未决");
      if (typeof entry.unresolved === "string") badge.title = entry.unresolved;
      else if (entry.unresolved_reason) badge.title = String(entry.unresolved_reason);
      metaLine.appendChild(badge);
    }
    var attached = Array.isArray(entry.attached) ? entry.attached : [];
    if (attached.length) {
      metaLine.appendChild(el("span", "tiny muted", "另有整文件指纹 " + attached.length + " 条（不计入修订点）"));
    }
    var state = el("span", "chip muted nd-gate-state", "未处置");
    metaLine.appendChild(state);
    body.appendChild(metaLine);
    row.appendChild(body);

    var openBtn = el("button", "btn btn-sm nd-gate-open", "查看前后对比 ↗");
    openBtn.type = "button";
    openBtn.setAttribute("data-entry-open", id);
    openBtn.setAttribute("aria-label", "查看条目 " + (entry.title || id) + " 的前后对比");
    openBtn.addEventListener("click", function () { openDiff(entry, openBtn); });
    row.appendChild(openBtn);

    host.appendChild(row);
    fillRowState(gate, entry, state, editable);
  }

  function renderHardBlocks(host, gate) {
    var blocks = Array.isArray(gate.hard_block) ? gate.hard_block.filter(function (b) { return !!b; }) : [];
    if (!blocks.length) return;
    var box = el("div", "nd-hardblock");
    box.appendChild(el("div", "nd-hardblock-head", "硬阻断（由服务端给出；下面先写白话，代号只作小字附注）"));
    blocks.forEach(function (block) {
      var item = el("div", "nd-hb-item");
      var title = !isMissing(block.title) && String(block.title).trim() !== "" ? String(block.title) : null;
      var message = !isMissing(block.message) && String(block.message).trim() !== "" ? String(block.message) : null;
      var code = !isMissing(block.code) && String(block.code).trim() !== "" ? String(block.code) : null;
      if (title) item.appendChild(el("b", "nd-hb-title", title));
      if (message && message !== title) item.appendChild(el("div", "nd-hb-msg", message));
      if (!title && !message) {
        item.appendChild(el("div", "nd-hb-msg", "服务端未下发这条阻断的白话说明（只有代号）；请到闸门视图看逐条材料。"));
      }
      if (code) item.appendChild(el("div", "nd-hb-code", "代号（附注）：" + code));
      box.appendChild(item);
    });
    host.appendChild(box);
  }

  function decisionText(gate, value) {
    var raw = isMissing(value) || value === "" ? "未下发" : String(value);
    if (raw === "未下发") return raw;
    var options = gate && Array.isArray(gate.decision_options) ? gate.decision_options : [];
    var label = null;
    for (var i = 0; i < options.length; i++) {
      if (options[i] && String(options[i].value) === raw) { label = String(options[i].label || raw); break; }
    }
    if ((!label || label === raw) && DECISION_LABELS[raw]) label = DECISION_LABELS[raw];
    return label && label !== raw ? label + "（" + raw + "）" : raw;
  }

  function renderDecidedSummary(foot, gate) {
    var decision = gate.decision && typeof gate.decision === "object" ? gate.decision : null;
    foot.appendChild(el("div", "nd-gate-progress", "已决策（只读）"));
    if (!decision) {
      foot.appendChild(el("div", "nd-gate-hint", "服务端未下发整门决策记录（gate.decision 为空）；界面不猜。"));
      if (gate.note) foot.appendChild(el("div", "tiny muted", String(gate.note)));
      return;
    }
    var box = el("div", "nd-decided");
    var line = el("div", "nd-decided-line");
    line.appendChild(el("b", null, "整门决策："));
    line.appendChild(el("span", null, decisionText(gate, decision.decision)));
    box.appendChild(line);
    box.appendChild(el("div", "nd-decided-line", "签署人：" +
      (isMissing(decision.actor) || decision.actor === "" ? "未下发" : String(decision.actor))));
    var signed = fmtTs(decision.signed_at);
    box.appendChild(el("div", "nd-decided-line", "签署时间：" +
      (signed || (isMissing(decision.signed_at) || decision.signed_at === "" ? "未下发" : String(decision.signed_at)))));
    box.appendChild(el("div", "nd-decided-line", "理由：" +
      (isMissing(decision.reason) || decision.reason === "" ? "未填写（原记录无理由）" : String(decision.reason))));
    if (gate.note) box.appendChild(el("div", "tiny muted", String(gate.note)));
    box.appendChild(el("div", "nd-gate-hint", "已决策：只读展示；闸门权威只增不改（不允许改判）。"));
    foot.appendChild(box);
  }

  /* G1 的处置 footer（等待：进度+提示+跳转；已决策：只读决策信息）。 */
  function fillGateFoot(foot, view, gate, counts) {
    if (gate.state === "decided") {
      renderDecidedSummary(foot, gate);
      return;
    }
    if (gate.state !== "waiting") {
      foot.appendChild(el("div", "nd-gate-hint", "服务端 gate.state=" + String(gate.state) +
        "：只读展示，不提供处置入口。"));
      return;
    }
    foot.appendChild(el("div", "nd-gate-progress", "已处置 " + counts.disposed + " / " + counts.total));
    var ready = bridgeReady();
    if (!ready) {
      foot.appendChild(el("div", "nd-gate-hint warn",
        "当前运行没有待决策闸门：勾选与理由无法写入共享草稿；到闸门视图再处置。"));
    } else if (counts.total === 0) {
      foot.appendChild(el("div", "nd-gate-hint warn",
        "服务端未下发修订点条目：这里只显示服务端给出的材料，不编条目；请到闸门视图看逐条材料。"));
    } else if (counts.disposed < counts.total) {
      foot.appendChild(el("div", "nd-gate-hint warn",
        "还有 " + (counts.total - counts.disposed) + " 条未处置：闸门视图的提交按钮会保持禁用，处置完再提交。"));
    } else {
      var b = bridge();
      var checked = null;
      if (b && typeof b.counts === "function") {
        try { checked = b.counts(); } catch (e) { checked = null; }
      }
      if (checked && checked.complete === false && checked.error) {
        foot.appendChild(el("div", "nd-gate-hint warn", "闸门视图提交前校验未通过：" + String(checked.error)));
      } else {
        foot.appendChild(el("div", "nd-gate-hint", "全部已处置：可以到闸门视图确认并提交。"));
      }
    }
    appendGateJump(foot);
  }

  function renderGate(view) {
    var host = $("ndGate");
    if (!host) return;
    clear(host);
    var gate = gateOf(view);
    if (!gate) return;
    var state = String(gate.state || "");
    var isG1 = gateIsG1(gate);
    /* G1 修订点清单 + 逐条处置控件只在 waiting/decided 出现（裁决：read_only 只展示 items）。 */
    var showRevision = isG1 && (state === "waiting" || state === "decided");
    var items = gateItemList(gate);
    var counts = showRevision ? gateCounts(view, gate) : null;

    if (showRevision) {
      var summary = el("div", "nd-gate-summary");
      summary.id = "ndGateSummaryLine";
      summary.textContent = summaryText(counts);
      host.appendChild(summary);
      if (gate.note) host.appendChild(el("div", "nd-gate-note tiny muted", String(gate.note)));
      var b = bridge();
      if (state === "waiting" && bridgeReady() && b && typeof b.counts === "function") {
        var bridged = null;
        try { bridged = b.counts(); } catch (e) { bridged = null; }
        if (bridged && typeof bridged.entries === "number" && bridged.entries !== counts.total) {
          host.appendChild(el("div", "nd-gate-hint warn",
            "面板清单 " + counts.total + " 条与闸门表单 " + bridged.entries + " 条不一致：以闸门视图（服务端材料）为准。"));
        }
      }
    } else if (gate.note) {
      host.appendChild(el("div", "nd-gate-note tiny muted", String(gate.note)));
    }

    /* 硬阻断只在等待态出现（read_only 不写"现在不能接受"，P-29）。 */
    if (state === "waiting") renderHardBlocks(host, gate);

    if (showRevision) {
      var entries = counts.entries;
      if (!entries.length) {
        host.appendChild(el("div", "nd-empty", "服务端未下发修订点条目（gate.entries 为空）；不编条目。"));
      } else {
        entries.forEach(function (entry) {
          renderGateRow(host, view, gate, entry, state === "waiting");
        });
      }
    }

    /* G2/G3 只读待确认项：任何 state（waiting/decided/read_only）都显示；缺失/空给降级说明。 */
    if (items.length) {
      renderGateItems(host, items);
    } else if (expectsReadOnlyItems()) {
      host.appendChild(el("div", "nd-empty", "服务端未下发待确认项（来源未定）"));
    }

    if (showRevision) {
      var foot = el("div", "nd-gate-foot");
      foot.id = "ndGateFoot";
      host.appendChild(foot);
      fillGateFoot(foot, view, gate, counts);
    } else if (state === "decided") {
      var decidedFoot = el("div", "nd-gate-foot");
      decidedFoot.id = "ndGateFoot";
      renderDecidedSummary(decidedFoot, gate);
      host.appendChild(decidedFoot);
    } else if (state === "waiting") {
      var waitingFoot = el("div", "nd-gate-foot");
      waitingFoot.id = "ndGateFoot";
      waitingFoot.appendChild(el("div", "nd-gate-hint",
        "本门没有逐条处置项：待确认项见上方只读清单；决策在闸门视图提交。"));
      appendGateJump(waitingFoot);
      host.appendChild(waitingFoot);
    } else if (state === "read_only") {
      var readOnlyFoot = el("div", "nd-gate-foot");
      readOnlyFoot.id = "ndGateFoot";
      readOnlyFoot.appendChild(el("div", "nd-gate-hint",
        "只读：服务端未下发这个门的处置项或决策记录；面板不提供处置入口（没有可处置项）。"));
      host.appendChild(readOnlyFoot);
    }

    host.appendChild(el("div", "foot-note",
      "清单只读投影；" + (showRevision ? "勾选/理由写入共享闸门草稿；" : "") +
      "本面板不发 POST；提交入口只有闸门视图表单。"));
  }

  function updateGateSummary() {
    if (!s.open || !s.data) return;
    var view = s.data;
    var gate = gateOf(view);
    if (!gate || !gateIsG1(gate) || gate.state !== "waiting") return;
    var counts = gateCounts(view, gate);
    var summary = $("ndGateSummaryLine");
    if (summary) summary.textContent = summaryText(counts);
    var foot = $("ndGateFoot");
    if (foot) {
      clear(foot);
      fillGateFoot(foot, view, gate, counts);
    }
    syncGateRowStates(view, gate);
  }

  function syncGateRowStates(view, gate) {
    var host = $("ndGate");
    if (!host) return;
    var editable = gateIsG1(gate) && gate.state === "waiting";
    var rows = host.querySelectorAll(".nd-gate-row");
    for (var i = 0; i < rows.length; i++) {
      var id = rows[i].getAttribute("data-entry-id");
      var entry = null;
      var entries = entryList(gate);
      for (var j = 0; j < entries.length; j++) {
        if (String(entries[j].entry_id === undefined || entries[j].entry_id === null ? "" : entries[j].entry_id) === id) {
          entry = entries[j];
          break;
        }
      }
      if (!entry) continue;
      fillRowState(gate, entry, rows[i].querySelector(".nd-gate-state"), editable);
      var box = rows[i].querySelector('input[type="checkbox"]');
      if (box && editable) box.checked = !!draftDecision(entry);
    }
  }

  function goGateView() {
    var callback = s.target && s.target.onGate ? s.target.onGate : null;
    var b = bridge();
    close();
    if (b && typeof b.openGateView === "function") b.openGateView();
    else if (callback) callback();
  }

  function renderGateBlock(view) {
    var block = $("ndGateBlock");
    if (!block) return;
    var gate = gateOf(view);
    /* G2/G3 在 no_material 时仍要显示"服务端未下发待确认项（来源未定）"；G1 保持隐藏。 */
    var show = !!gate && (gate.state !== "no_material" || expectsReadOnlyItems());
    block.classList.toggle("hidden", !show);
    clear($("ndGate"));
    if (show) renderGate(view);
  }

  /* ---------------- 前后对比浮窗：两栏 before/after + hunk 行号 + 逐条处置 ---------------- */

  function baseName(path) {
    var text = String(path);
    var parts = text.split("/");
    return parts[parts.length - 1] || text;
  }

  function safeName(value) {
    return String(value).replace(/[^A-Za-z0-9_-]+/g, "_");
  }

  function parseDiffHunks(text) {
    var lines = String(text).replace(/\r\n?/g, "\n").split("\n");
    if (lines.length && lines[lines.length - 1] === "") lines.pop();  // 末尾换行不是 hunk 行
    var hunks = [];
    var hunk = null;
    var oldNo = 0;
    var newNo = 0;
    lines.forEach(function (line) {
      var head = line.match(/^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@(.*)$/);
      if (head) {
        hunk = { header: line, oldStart: parseInt(head[1], 10), newStart: parseInt(head[3], 10), rows: [] };
        hunks.push(hunk);
        oldNo = hunk.oldStart;
        newNo = hunk.newStart;
        return;
      }
      if (!hunk) return;
      if (/^\\ No newline/.test(line)) return;
      if (line === "") {
        hunk.rows.push({ kind: "context", text: "", oldNo: oldNo++, newNo: newNo++ });
        return;
      }
      var mark = line.charAt(0);
      var bodyText = line.slice(1);
      if (mark === "-") {
        hunk.rows.push({ kind: "del", text: bodyText, oldNo: oldNo++, newNo: null });
      } else if (mark === "+") {
        hunk.rows.push({ kind: "add", text: bodyText, oldNo: null, newNo: newNo++ });
      } else {
        hunk.rows.push({ kind: "context", text: mark === " " ? bodyText : line, oldNo: oldNo++, newNo: newNo++ });
      }
    });
    return hunks;
  }

  function hunkColumns(hunks) {
    var wrap = el("div", "nd-hunks");
    var legend = el("div", "nd-hunk-legend");
    legend.appendChild(el("span", "nd-hunk-legend-before", "before（旧）"));
    legend.appendChild(el("span", "nd-hunk-legend-after", "after（新）"));
    wrap.appendChild(legend);
    hunks.forEach(function (hunk) {
      var box = el("div", "nd-hunk");
      box.appendChild(el("div", "nd-hunk-head mono", hunk.header));
      var grid = el("div", "nd-hunk-grid");
      hunk.rows.forEach(function (row) {
        var before = el("div", "nd-hunk-cell before" + (row.oldNo === null ? " empty" : "") + (row.kind === "del" ? " del" : ""));
        if (row.oldNo !== null) {
          before.appendChild(el("span", "nd-hunk-no", String(row.oldNo)));
          before.appendChild(el("span", "nd-hunk-text", row.text));
        }
        var after = el("div", "nd-hunk-cell after" + (row.newNo === null ? " empty" : "") + (row.kind === "add" ? " add" : ""));
        if (row.newNo !== null) {
          after.appendChild(el("span", "nd-hunk-no", String(row.newNo)));
          after.appendChild(el("span", "nd-hunk-text", row.text));
        }
        grid.appendChild(before);
        grid.appendChild(after);
      });
      box.appendChild(grid);
      wrap.appendChild(box);
    });
    return wrap;
  }

  function pairValueText(node, label) {
    var pane = el("div", "diff-pane " + label);
    var head = el("div", "diff-pane-head");
    head.appendChild(el("span", null, label === "before" ? "before（旧）" : "after（新）"));
    pane.appendChild(head);
    if (isMissing(node)) {
      pane.appendChild(el("div", "diff-missing", "未下发"));
      return pane;
    }
    var pre = el("pre", "diff-text");
    pre.textContent = textOf(node);
    pane.appendChild(pre);
    return pane;
  }

  function pairChanges(before, after) {
    var keys = [];
    Object.keys(before).forEach(function (key) { if (keys.indexOf(key) < 0) keys.push(key); });
    Object.keys(after).forEach(function (key) { if (keys.indexOf(key) < 0) keys.push(key); });
    var changed = [];
    var unchanged = [];
    keys.forEach(function (key) {
      var same = false;
      try { same = JSON.stringify(before[key]) === JSON.stringify(after[key]); } catch (e) { same = String(before[key]) === String(after[key]); }
      if (same) unchanged.push(key); else changed.push(key);
    });
    return { changed: changed, unchanged: unchanged };
  }

  function renderValuePair(entry) {
    var before = entry.before;
    var after = entry.after;
    if (isMissing(before) && isMissing(after)) return null;
    if (plain(before) && plain(after)) {
      var box = el("div", "nd-pair-fields");
      box.appendChild(el("div", "diff-fields-head", "变化字段（before → after）；其余字段折叠"));
      var diff = pairChanges(before, after);
      var table = el("table", "diff-fields");
      var tbody = el("tbody");
      var headRow = el("tr");
      headRow.appendChild(el("th", null, "字段"));
      headRow.appendChild(el("th", null, "before"));
      headRow.appendChild(el("th", null, "after"));
      tbody.appendChild(headRow);
      diff.changed.forEach(function (key) {
        var tr = el("tr");
        tr.appendChild(el("th", null, key));
        tr.appendChild(el("td", null, isMissing(before[key]) ? "未下发" : textOf(before[key])));
        tr.appendChild(el("td", null, isMissing(after[key]) ? "未下发" : textOf(after[key])));
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      box.appendChild(table);
      if (diff.unchanged.length) {
        var det = el("details", "diff-unchanged nd-pair-unchanged");
        det.appendChild(el("summary", null, "其余字段未变（" + diff.unchanged.length + " 项）"));
        var unchangedTable = el("table", "diff-fields");
        var unchangedBody = el("tbody");
        diff.unchanged.forEach(function (key) {
          var tr = el("tr");
          tr.appendChild(el("th", null, key));
          tr.appendChild(el("td", null, isMissing(before[key]) ? "未下发" : textOf(before[key])));
          unchangedBody.appendChild(tr);
        });
        unchangedTable.appendChild(unchangedBody);
        det.appendChild(unchangedTable);
        box.appendChild(det);
      }
      return box;
    }
    var pair = el("div", "diff-pair");
    pair.appendChild(pairValueText(before, "before"));
    pair.appendChild(pairValueText(after, "after"));
    return pair;
  }

  function noHunkReason(entry) {
    var candidates = [entry.no_hunk_reason, entry.note, entry.reason, entry.unresolved_reason];
    for (var i = 0; i < candidates.length; i++) {
      if (!isMissing(candidates[i]) && String(candidates[i]).trim() !== "") return String(candidates[i]);
    }
    var encoding = !isMissing(entry.encoding) && entry.encoding !== "" ? String(entry.encoding) : null;
    if (encoding && !/utf-?8/i.test(encoding)) {
      return "服务端未下发原因（本条编码 " + encoding + "；旧版正文缺失 / 非 UTF-8 / 二进制都可能，界面不猜）";
    }
    return "服务端未下发原因（旧版正文缺失 / 非 UTF-8 / 二进制都可能，界面不猜）";
  }

  function alternativeEvidence(entry) {
    var parts = [];
    var arr = Array.isArray(entry.lines) ? entry.lines.filter(function (v) { return typeof v === "number"; }) : [];
    if (arr.length) parts.push("行号 " + arr.join("、"));
    if (!isMissing(entry.offset) && entry.offset !== "") parts.push("偏移 " + String(entry.offset));
    if (!isMissing(entry.encoding) && entry.encoding !== "") parts.push("编码 " + String(entry.encoding));
    if (!isMissing(entry.evidence) && entry.evidence !== "") parts.push("证据 " + String(entry.evidence));
    if (!isMissing(entry.before) && !isMissing(entry.after) &&
        typeof entry.before === "string" && typeof entry.after === "string") {
      parts.push("before → after：" + entry.before + " → " + entry.after);
    }
    var attached = Array.isArray(entry.attached) ? entry.attached : [];
    attached.forEach(function (item) {
      if (!item || typeof item !== "object") return;
      var text = "整文件指纹（附证据，不计入）";
      if (!isMissing(item.before) && !isMissing(item.after)) text += "：" + String(item.before) + " → " + String(item.after);
      if (!isMissing(item.evidence) && item.evidence !== "") text += " · 证据 " + String(item.evidence);
      if (!isMissing(item.note) && String(item.note).trim() !== "") text += " · 说明 " + String(item.note);
      parts.push(text);
    });
    return parts.join("；");
  }

  function renderDiffMeta(host, entry) {
    if (!host) return;
    clear(host);
    if (entry.entry_id) host.appendChild(metaChip("文件：" + String(entry.entry_id), "mono"));
    var lines = linesText(entry.lines);
    if (lines) host.appendChild(metaChip(lines));
    if (!isMissing(entry.offset) && entry.offset !== "") host.appendChild(metaChip("偏移：" + String(entry.offset), "mono"));
    if (!isMissing(entry.encoding) && entry.encoding !== "") host.appendChild(metaChip("编码：" + String(entry.encoding)));
    if (!isMissing(entry.change) && entry.change !== "") host.appendChild(metaChip("变更：" + changeLabel(entry.change)));
    if (!isMissing(entry.evidence) && entry.evidence !== "") host.appendChild(metaChip("证据：" + String(entry.evidence), "mono"));
    if (entry.drill_fixture === true) host.appendChild(metaChip("drill 夹具（不碰真实环境）", "warn"));
    var attached = Array.isArray(entry.attached) ? entry.attached : [];
    if (attached.length) {
      host.appendChild(metaChip("另有整文件指纹 " + attached.length + " 条（不计入修订点）"));
    }
  }

  function dispositionSection(entry, gate, editable) {
    var wrap = el("div", "nd-dispose");
    var id = String(entry.entry_id === undefined || entry.entry_id === null ? "" : entry.entry_id);
    var disposition = entry.disposition && typeof entry.disposition === "object" ? entry.disposition : null;
    if (!editable) {
      wrap.appendChild(el("div", "nd-dispose-head", "逐条处置（已决策 / 只读）"));
      if (!disposition || !disposition.decision) {
        wrap.appendChild(el("div", "nd-dispose-readonly muted", "服务端未下发这一条的处置记录" +
          (gate && gate.note ? "（" + String(gate.note) + "）" : "") + "；界面不猜。"));
        return wrap;
      }
      wrap.appendChild(el("div", "nd-dispose-readonly", "处置：" + labelOf(DISPOSITION_LABELS, disposition.decision)));
      wrap.appendChild(el("div", "nd-dispose-reason", "理由：" +
        (isMissing(disposition.reason) || disposition.reason === "" ? "未填写（原记录无理由）" : String(disposition.reason))));
      return wrap;
    }

    wrap.appendChild(el("div", "nd-dispose-head", "逐条处置（只写共享草稿；提交入口只有闸门视图）"));
    var ready = bridgeReady();
    var current = (ready && bridgeGet(id)) || { decision: null, reason: "" };
    var chosen = { value: current.decision || null };
    var options = allowedDispositions();
    var group = "nd-dispose-" + safeName(id);
    var optionsBox = el("div", "nd-dispose-options");
    options.forEach(function (option) {
      var label = el("label", "option");
      var input = el("input");
      input.type = "radio";
      input.name = group;
      input.value = option.value;
      input.checked = chosen.value === option.value;
      input.disabled = !ready;
      label.appendChild(input);
      label.appendChild(el("span", "radio"));
      label.appendChild(el("span", null, option.label + (option.value === "confirmed" ? "" : "（理由必填）")));
      input.addEventListener("change", function () {
        chosen.value = option.value;
        bridgeSet(id, option.value, reasonInput.value);
        updateDisposeHint();
        updateGateSummary();
      });
      optionsBox.appendChild(label);
    });
    wrap.appendChild(optionsBox);

    var reasonInput = el("input", "input mono nd-dispose-reason-input");
    reasonInput.type = "text";
    reasonInput.value = current.reason || "";
    reasonInput.placeholder = "本条理由（忽略 / 有疑义必填）";
    reasonInput.setAttribute("aria-label", "条目 " + (entry.title || id) + " 的理由");
    reasonInput.disabled = !ready;
    reasonInput.addEventListener("input", function () {
      bridgeSet(id, chosen.value, reasonInput.value);
      updateDisposeHint();
      updateGateSummary();
    });
    wrap.appendChild(reasonInput);

    var hint = el("div", "nd-dispose-hint tiny muted");
    wrap.appendChild(hint);
    function updateDisposeHint() {
      if (!ready) {
        hint.textContent = "当前运行没有待决策闸门：无法写入共享草稿；到闸门视图再处置。";
        return;
      }
      var needsReason = chosen.value === "ignored" || chosen.value === "disputed";
      var hasReason = String(reasonInput.value || "").trim() !== "";
      hint.textContent = needsReason && !hasReason
        ? "忽略 / 有疑义必须填理由：现在闸门视图的提交按钮会保持禁用。"
        : "已写入共享草稿（不落盘、不发请求）；到闸门视图确认并提交。";
    }
    updateDisposeHint();
    return wrap;
  }

  /* R3-12：`gate.entries[].attached[]` 是同一文件的附证据（md5-only）。
   * 行内只显示"另有整文件指纹 N 条"，展开/浮窗必须逐条显示服务端 `note`
   * （附证据区，不计入修订点），不能只给条数。 */
  function renderAttachedEvidence(host, entry) {
    var attached = Array.isArray(entry.attached) ? entry.attached.filter(function (item) { return !!item; }) : [];
    if (!attached.length) return;
    var box = el("div", "nd-attached");
    box.appendChild(el("div", "nd-attached-head",
      "附证据（同一文件的整文件指纹，" + attached.length + " 条；不计入修订点）"));
    attached.forEach(function (item, index) {
      if (!item || typeof item !== "object") return;
      var row = el("div", "nd-attached-item");
      row.setAttribute("data-attached-index", String(index));
      var kind = !isMissing(item.kind) && String(item.kind).trim() !== "" ? String(item.kind) : null;
      row.appendChild(el("div", "nd-attached-meta",
        (kind || "附证据") +
        (!isMissing(item.redundant_of) && String(item.redundant_of) !== "" ? " · 对应 " + String(item.redundant_of) : "") +
        (!isMissing(item.before) && !isMissing(item.after)
          ? " · " + String(item.before) + " → " + String(item.after) : "") +
        (!isMissing(item.evidence) && String(item.evidence) !== "" ? " · 证据 " + String(item.evidence) : "")));
      var note = !isMissing(item.note) && String(item.note).trim() !== "" ? String(item.note) : null;
      row.appendChild(el("div", "nd-attached-note" + (note ? "" : " muted"),
        note || "服务端未下发这条附证据的说明（界面不补默认值）"));
      box.appendChild(row);
    });
    box.appendChild(el("div", "nd-attached-hint tiny muted",
      "附证据只作参考：md5-only，指向主条目 redundant_of；不单独成行、不计入「共 N 条修订点」。"));
    host.appendChild(box);
  }

  function openDiff(entry, trigger) {
    if (!s.open || !s.data) return;
    var gate = gateOf(s.data);
    if (!gate) return;
    if (!openOverlay("ndDiffOverlay", trigger)) return;
    var editable = gate.state === "waiting";
    setText("ndDiffTitle", entry.title ? String(entry.title) : String(entry.entry_id || "条目"));
    renderDiffMeta($("ndDiffMeta"), entry);
    var body = $("ndDiffBody");
    if (!body) return;
    clear(body);
    var hunkText = typeof entry.diff_hunk === "string" ? entry.diff_hunk.trim() : "";
    var hunks = hunkText ? parseDiffHunks(hunkText) : [];
    if (hunks.length) {
      body.appendChild(el("div", "nd-hunk-caption",
        "行级 hunk（按 @@ -a,b +c,d @@ 解析成两栏；行号取自 hunk 头；纯展示，不判定）"));
      body.appendChild(hunkColumns(hunks));
    } else {
      if (hunkText) {
        body.appendChild(el("div", "nd-hunk-caption",
          "服务端下发了 diff_hunk，但没有可解析的 @@ 行号（下面保留原文，不猜测）"));
        var raw = el("pre", "nd-pre");
        raw.textContent = hunkText;
        body.appendChild(raw);
      }
      var pair = renderValuePair(entry);
      if (pair) body.appendChild(pair);
      var nohunk = el("div", "nd-nohunk");
      nohunk.appendChild(el("b", null, "无行级 hunk（只说明，不判定）"));
      nohunk.appendChild(el("div", null, "原因：" + noHunkReason(entry)));
      var alternative = alternativeEvidence(entry);
      if (alternative) nohunk.appendChild(el("div", null, "替代证据：" + alternative));
      body.appendChild(nohunk);
    }
    renderAttachedEvidence(body, entry);
    body.appendChild(dispositionSection(entry, gate, editable));
    body.appendChild(el("div", "foot-note", "浮窗只做前后对照与草稿输入；不改判、不提交、不打开其它文件。"));
  }

  /* ---------------- 关键数字 / 观测点（R3-03） / 过程 / 证据 ---------------- */

  /* R3-03：`story.observation_points`（仅 N6 下发；服务端确定性透传，前端不推断）。
   *   · 字段不存在 ⇒ 不渲染（非 N6 节点）
   *   · null        ⇒ "未下发（旧 run 或替身，模型未产出观测点）"
   *   · []          ⇒ 下发了但 0 条（不冒充"未下发"）
   *   · 数组        ⇒ 可折叠「观测点（N 条）」列表，默认收起
   * 注意：null 与 [] 是两种事实（契约 §1.1），不得互相替代。 */
  function observationPointsOf(view) {
    var story = storyOf(view);
    if (!Object.prototype.hasOwnProperty.call(story, "observation_points")) return undefined;
    var raw = story.observation_points;
    if (raw === null) return null;
    return Array.isArray(raw) ? raw : undefined;
  }

  function obsAddrText(point) {
    var addr = !isMissing(point.addr) && String(point.addr).trim() !== "" ? String(point.addr) : null;
    var offset = !isMissing(point.offset) && String(point.offset).trim() !== "" ? String(point.offset) : null;
    if (addr === null && offset === null) return null;
    return (addr === null ? "未下发" : addr) + "+" + (offset === null ? "未下发" : offset);
  }

  function obsCell(label, value) {
    var cell = el("div", "nd-obs-cell");
    cell.appendChild(el("span", "nd-obs-label", label));
    var hasValue = !isMissing(value) && String(value).trim() !== "";
    cell.appendChild(el("span", "nd-obs-value mono" + (hasValue ? "" : " muted"), hasValue ? String(value) : "未下发"));
    return cell;
  }

  function renderObservationPoints(view, host) {
    if (!host) return;
    var points = observationPointsOf(view);
    if (points === undefined) return;
    if (points === null) {
      host.appendChild(el("div", "nd-obs-missing",
        "观测点未下发（旧 run 或替身，模型未产出观测点）"));
      return;
    }
    var box = el("div", "nd-obs");
    var det = el("details", "nd-obs-details");
    det.setAttribute("data-observation-points", String(points.length));
    var summary = el("summary", "nd-obs-summary", "观测点（" + points.length + " 条）");
    det.appendChild(summary);
    det.appendChild(el("span", "nd-obs-hint", "默认收起；每条：用例 / marker / addr+off / 期望值（服务端原值，界面不推断）"));
    if (!points.length) {
      det.appendChild(el("div", "nd-obs-empty", "服务端下发的是空列表：本轮 0 条观测点（空列表不等于未下发）。"));
    } else {
      var list = el("div", "nd-obs-list");
      points.forEach(function (point, index) {
        if (!point || typeof point !== "object") return;
        var row = el("div", "nd-obs-row");
        row.setAttribute("data-obs-index", String(index));
        row.appendChild(obsCell("用例", point.case));
        row.appendChild(obsCell("marker", point.marker));
        row.appendChild(obsCell("addr+off", obsAddrText(point)));
        row.appendChild(obsCell("期望值", point.expected_value));
        list.appendChild(row);
      });
      det.appendChild(list);
    }
    box.appendChild(det);
    host.appendChild(box);
  }

  function renderKeyResults(view) {
    var host = $("ndKey");
    if (!host) return;
    var story = storyOf(view);
    var rows = Array.isArray(story.key_results) ? story.key_results : [];
    var detail = view.detail && typeof view.detail === "object" && !Array.isArray(view.detail) ? view.detail : null;
    if (detail && !Object.keys(detail).length && view.known !== false) {
      host.appendChild(el("div", "nd-empty", story.not_reached === true
        ? "本轮没有走到这个节点，所以没有关键数字。"
        : story.not_executed === true
          ? "本轮未执行，所以没有关键数字。"
          : "该节点还没有收尾记录（detail 为空），关键数字未下发。"));
      renderObservationPoints(view, host);
      return;
    }
    if (!rows.length) {
      host.appendChild(el("div", "nd-empty", view.known === false
        ? "服务端未登记该节点，没有逐节点关键字段；完整 detail 见「原始记录」。"
        : "服务端未下发关键数字（界面不猜字段）。"));
      renderObservationPoints(view, host);
      return;
    }
    rows.forEach(function (row) {
      if (!row || typeof row !== "object") return;
      var wt = el("div", "nd-key-row" + (row.missing ? " missing" : ""));
      wt.appendChild(el("span", "nd-key-label", row.label || row.field));
      var value = el("span", "nd-key-value mono", isMissing(row.text) || row.text === "" ? "未下发" : String(row.text));
      wt.appendChild(value);
      host.appendChild(wt);
    });
    renderObservationPoints(view, host);
  }

  function renderSteps(view) {
    var host = $("ndSteps");
    if (!host) return;
    var story = storyOf(view);
    var steps = Array.isArray(story.steps) ? story.steps : [];
    if (!steps.length) {
      host.appendChild(el("li", "nd-empty", story.not_reached === true
        ? "本轮没有走到这个节点（没有这个节点的过程事件）。"
        : "服务端未下发这个节点的事件步骤（events 为空）。"));
      return;
    }
    var failed = false;
    steps.forEach(function (step, index) {
      if (!step || typeof step !== "object") return;
      var li = el("li", "nd-step");
      if (step.kind === "node_failed") { li.classList.add("failed"); failed = true; }
      var clock = fmtClock(step.at);
      li.appendChild(el("span", "nd-step-no", String(index + 1)));
      var body = el("div", "nd-step-body");
      var head = el("div", "nd-step-head");
      head.appendChild(el("span", "nd-step-text", step.text || step.kind || "未下发"));
      if (!isMissing(step.status) && step.status !== "") {
        var chip = el("span", "chip mono nd-step-status", stepStatusText(view, step.status));
        chip.title = "服务端原值 " + String(step.status) + "；中文只是释义。";
        head.appendChild(chip);
      }
      if (clock) head.appendChild(el("span", "nd-step-time", clock));
      body.appendChild(head);
      li.appendChild(body);
      host.appendChild(li);
    });
    if (failed) host.classList.add("has-failure"); else host.classList.remove("has-failure");
  }

  function kvRow(dl, label, content) {
    dl.appendChild(el("dt", null, label));
    var dd = el("dd");
    if (content === null || content === undefined || content === "") {
      dd.className = "muted";
      dd.textContent = "未下发";
    } else if (content instanceof Node) {
      dd.appendChild(content);
    } else {
      dd.textContent = String(content);
    }
    dl.appendChild(dd);
  }

  function renderIdentity(view) {
    var host = $("ndIdentity");
    if (!host) return;
    var target = s.target;
    var name = view.name || (target && target.fallback ? target.fallback.name : null);
    var owner = view.owner || (target && target.fallback ? target.fallback.owner : null);
    kvRow(host, "节点", el("span", "mono", String(view.node || (target ? target.node : "—"))));
    kvRow(host, "名称", name ? el("span", null, String(name)) : null);
    kvRow(host, "owner", owner ? el("span", null, String(owner)) : null);
    kvRow(host, "状态（原值）", statusChip(view));
    kvRow(host, "来源 source", isMissing(view.source) || view.source === "" ? null : el("span", "mono", String(view.source)));
    kvRow(host, "开始时间", fmtTs(view.started_at));
    kvRow(host, "结束时间", fmtTs(view.finished_at));
    kvRow(host, "服务端已登记", view.known === true ? "是（known=true）" : view.known === false ? "否（known=false：空投影 + 原始事件）" : null);
    kvRow(host, "投影标识", view.authority ? String(view.authority) : null);
    kvRow(host, "运行模式", isMissing(view.mode) || view.mode === "" ? null : String(view.mode));
    kvRow(host, "运行状态", isMissing(view.run_status) || view.run_status === "" ? null : String(view.run_status));
    kvRow(host, "运行是否终态", isMissing(view.run_terminal) ? null : (view.run_terminal === true ? "是（run_terminal=true）" : "否"));
    kvRow(host, "节点开始事件", isMissing(view.node_started_present) ? null : (view.node_started_present === true ? "有（node_started_present=true）" : "无"));
    kvRow(host, "S0 来源", isMissing(view.s0_record_id) || view.s0_record_id === "" ? null : String(view.s0_record_id));

    var actions = $("ndAgentJump");
    if (actions) {
      clear(actions);
      if (target && target.gate && target.onGate) {
        var gateJump = el("button", "btn btn-sm nd-agent-jump", "查看闸门材料（同源）→");
        gateJump.type = "button";
        gateJump.setAttribute("aria-label", "打开闸门视图查看同源材料");
        gateJump.addEventListener("click", function () {
          var callback = target.onGate;
          close();
          callback();
        });
        actions.appendChild(gateJump);
      }
      if (target && target.agent && window.AgentWindow) {
        var jump = el("button", "btn btn-sm nd-agent-jump", "打开 Agent 工作窗口 ↗");
        jump.type = "button";
        jump.setAttribute("aria-label", "打开 " + target.agent.name + " 工作窗口");
        jump.addEventListener("click", function () {
          window.AgentWindow.open({
            runId: target.runId,
            name: target.agent.name,
            nodes: target.agent.nodes,
            node: target.node
          });
        });
        actions.appendChild(jump);
      }
    }
  }

  function renderEvents(view) {
    var host = $("ndEvents");
    if (!host) return;
    var events = Array.isArray(view.events) ? view.events.slice() : [];
    if (!events.length) {
      host.appendChild(el("div", "nd-empty", "服务端未下发该节点的事件切片（events 为空）。"));
      return;
    }
    events.sort(function (a, b) {
      var sa = a && typeof a.seq === "number" ? a.seq : null;
      var sb = b && typeof b.seq === "number" ? b.seq : null;
      if (sa === null || sb === null) return 0;
      return sb - sa;
    });
    var note = el("div", "tiny muted");
    note.textContent = "共 " + events.length + " 条；按 seq 从新到旧（最近一条在前）。";
    host.appendChild(note);
    events.forEach(function (event) {
      if (!event || typeof event !== "object") return;
      var row = el("div", "nd-event");
      var head = el("div", "nd-event-head");
      head.appendChild(el("span", "nd-seq", event.seq === undefined || event.seq === null ? "seq —" : "#" + String(event.seq)));
      head.appendChild(el("span", "chip mono", event.kind || "未下发 kind"));
      head.appendChild(el("span", "chip", event.status === undefined || event.status === null ? "status 未下发" : String(event.status)));
      var when = fmtTs(event.ts);
      if (when) head.appendChild(el("span", "tiny muted", when));
      if (event.node) head.appendChild(el("span", "tiny muted mono", String(event.node)));
      row.appendChild(head);
      var detailText = textOf(event.detail);
      if (detailText !== null && detailText !== "" && detailText !== "{}") {
        var pre = el("pre", "nd-event-detail");
        pre.textContent = detailText;
        row.appendChild(pre);
      }
      if (Array.isArray(event.refs) && event.refs.length) {
        var refs = el("div", "tiny muted mono nd-event-refs");
        refs.textContent = "refs：" + event.refs.map(String).join(" · ");
        row.appendChild(refs);
      }
      host.appendChild(row);
    });
  }

  function renderDetail(view) {
    var detailHost = $("ndDetailBody");
    if (!detailHost) return;
    var detail = view.detail;
    if (isMissing(detail)) {
      detailHost.appendChild(el("div", "nd-empty", "结构化 detail 未下发。"));
      return;
    }
    if (typeof detail !== "object" || Array.isArray(detail)) {
      var raw = el("pre", "nd-pre");
      raw.textContent = textOf(detail);
      detailHost.appendChild(raw);
      return;
    }
    if (!Object.keys(detail).length) {
      detailHost.appendChild(el("div", "nd-empty", "detail 为空（该节点还没有收尾事件）。"));
      return;
    }
    var table = el("table", "nd-detail-table");
    var tbody = el("tbody");
    Object.keys(detail).forEach(function (key) {
      var tr = el("tr");
      tr.appendChild(el("th", null, key));
      var td = el("td");
      var value = detail[key];
      if (isMissing(value)) {
        td.className = "muted";
        td.textContent = "未下发";
      } else if (typeof value === "object") {
        var cellPre = el("pre", "nd-cell-pre");
        cellPre.textContent = textOf(value);
        td.appendChild(cellPre);
      } else {
        td.textContent = String(value);
      }
      tr.appendChild(td);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    detailHost.appendChild(table);
    var rawBox = el("details", "nd-raw-json");
    rawBox.appendChild(el("summary", null, "原始 detail JSON（只读，未改写）"));
    var rawPre = el("pre", null);
    rawPre.textContent = JSON.stringify(detail, null, 2);
    rawBox.appendChild(rawPre);
    detailHost.appendChild(rawBox);
  }

  function renderSummaryRaw(view) {
    var host = $("ndSummaryRaw");
    if (!host) return;
    var detail = view.detail && typeof view.detail === "object" && !Array.isArray(view.detail) ? view.detail : {};
    var summary = view.summary;
    var fromDetail = false;
    if ((isMissing(summary) || summary === "") && !isMissing(detail.summary) && detail.summary !== "") {
      summary = detail.summary;
      fromDetail = true;
    }
    if (isMissing(summary) || summary === "") {
      host.appendChild(el("span", "muted", "未下发"));
      return;
    }
    host.appendChild(document.createTextNode(String(summary)));
    if (fromDetail) host.appendChild(el("span", "tiny muted", "（取自 detail.summary；顶层 summary 未下发）"));
  }

  function probeRef(ref, button, output) {
    if (!api || !s.target) return;
    var runId = s.target.runId;
    var token = s.epoch;
    button.disabled = true;
    output.className = "nd-probe";
    output.textContent = "探测中…";
    api("/api/runs/" + enc(runId) + "/evidence/exists?ref=" + enc(ref)).then(function (body) {
      if (token !== s.epoch || !s.open) return;
      if (body && body.exists === true) {
        var extra = "";
        if (!isMissing(body.bytes)) extra = " · " + body.bytes + " B";
        if (!isMissing(body.entries)) extra = " · 目录 " + body.entries + " 项";
        output.className = "nd-probe ok";
        output.textContent = "存在" + extra;
      } else if (body && body.exists === null) {
        output.className = "nd-probe";
        output.textContent = "不按文件路径探测：" + (body.note || "服务端未返回存在性");
      } else {
        output.className = "nd-probe bad";
        output.textContent = "证据缺失（E-2）：" + ((body && body.note) || "文件不存在");
      }
    }).catch(function (e) {
      if (token !== s.epoch || !s.open) return;
      output.className = "nd-probe bad";
      output.textContent = "探测失败：" + errText(e);
    }).then(function () {
      if (token === s.epoch) button.disabled = false;
    });
  }

  function refsOmittedText(omitted) {
    if (!omitted) return "";
    return "另有 " + omitted + " 条运行目录外引用未展示（服务端只计数、不给路径；§6.7 安全边界）。";
  }

  function agentJumpNode(prefix) {
    if (!(s.target && s.target.agent && window.AgentWindow)) return null;
    var wrap = el("div", "nd-evidence-agent");
    if (prefix) wrap.appendChild(el("span", "tiny muted", prefix));
    var jump = el("button", "btn btn-sm", "打开 Agent 工作窗口 ↗");
    jump.type = "button";
    jump.setAttribute("aria-label", "打开 " + s.target.agent.name + " 工作窗口");
    jump.addEventListener("click", function () {
      window.AgentWindow.open({
        runId: s.target.runId,
        name: s.target.agent.name,
        nodes: s.target.agent.nodes,
        node: s.target.node
      });
    });
    wrap.appendChild(jump);
    return wrap;
  }

  /* R3-06：`story.evidence_groups` 的三种事实（契约 §1.2），前端只做展示分流：
   *   · null / 字段不存在 ⇒ 维持现状平铺 view.refs
   *   · []                ⇒ 无法分组：显示服务端 evidence_groups_note，refs 仍平铺（不丢证据）
   *   · [{case, refs[], note}] ⇒ 按用例分组；refs 为空的组显示服务端 note（不留空白）
   * 组头只取服务端 case 原值；不推断用例名、不新建组。 */
  function evidenceGroupsOf(story) {
    if (!story || typeof story !== "object") return null;
    var raw = story.evidence_groups;
    if (isMissing(raw)) return null;
    return Array.isArray(raw) ? raw : null;
  }

  function refRow(ref) {
    var row = el("div", "nd-ref");
    var path = el("span", "mono", baseName(ref));
    path.title = String(ref);
    row.appendChild(path);
    var button = el("button", "btn btn-sm", "探测存在性");
    button.type = "button";
    var output = el("span", "nd-probe", "未探测");
    button.addEventListener("click", function () { probeRef(String(ref), button, output); });
    row.appendChild(button);
    row.appendChild(output);
    return row;
  }

  function renderRefRows(host, refs) {
    refs.forEach(function (ref) {
      if (isMissing(ref)) return;
      host.appendChild(refRow(ref));
    });
  }

  function groupRefs(group) {
    return Array.isArray(group.refs) ? group.refs.filter(function (ref) { return !isMissing(ref); }) : [];
  }

  function renderEvidenceGroups(host, groups) {
    var wrap = el("div", "nd-ref-groups");
    groups.forEach(function (group, index) {
      if (!group || typeof group !== "object") return;
      var box = el("div", "nd-ref-group");
      box.setAttribute("data-evidence-group", String(index));
      var caseName = !isMissing(group.case) && String(group.case).trim() !== "" ? String(group.case) : null;
      if (caseName === null) box.classList.add("no-case");
      var head = el("div", "nd-ref-group-head");
      head.appendChild(el("span", "nd-ref-group-case mono", caseName === null ? "用例名未下发" : caseName));
      var refs = groupRefs(group);
      head.appendChild(el("span", "nd-ref-group-count tiny muted", refs.length + " 条证据"));
      box.appendChild(head);
      if (refs.length) {
        renderRefRows(box, refs);
      } else {
        /* 空组不许留空白：优先用服务端 note（如"本轮未执行/无证据"），没有就说未下发说明。 */
        var note = !isMissing(group.note) && String(group.note).trim() !== "" ? String(group.note) : null;
        box.appendChild(el("div", "nd-ref-group-note" + (note ? "" : " muted"),
          note || "服务端未下发这一组的证据与说明（界面不补默认值）"));
      }
      wrap.appendChild(box);
    });
    host.appendChild(wrap);
  }

  /* R3-07：N9 的 `detail.example_line`（默认收起；null / 空 ⇒ 不渲染该块）。 */
  function exampleLineOf(view) {
    var detail = view.detail && typeof view.detail === "object" && !Array.isArray(view.detail) ? view.detail : null;
    if (!detail) return null;
    var raw = detail.example_line;
    if (isMissing(raw)) return null;
    var text = String(raw);
    return text.trim() === "" ? null : text;
  }

  function renderExampleLine(view, host) {
    var text = exampleLineOf(view);
    if (text === null) return;
    var det = el("details", "nd-example");
    det.setAttribute("data-example-line", "1");
    det.appendChild(el("summary", "nd-example-summary", "看一行示例"));
    det.appendChild(el("div", "nd-example-hint", "默认收起；下面是服务端 detail.example_line 原文（只读，不改写）"));
    var pre = el("pre", "nd-example-line");
    pre.textContent = text;
    det.appendChild(pre);
    host.appendChild(det);
  }

  function renderEvidence(view) {
    var host = $("ndRefs");
    if (!host) return;
    var story = storyOf(view);
    var note = story.evidence_note && typeof story.evidence_note === "object" ? story.evidence_note : null;
    var noteText = note && !isMissing(note.text) && String(note.text) !== "" ? String(note.text) : null;
    var noteKind = note && !isMissing(note.kind) && note.kind !== "" ? String(note.kind) : null;
    if (noteText) {
      host.appendChild(el("div", "nd-evidence-note" + (noteKind === "not_executed" ? " muted" : ""), noteText));
    }
    var agentLink = noteKind === "agent_calls" ? agentJumpNode("") : null;
    var refs = Array.isArray(view.refs) ? view.refs : [];
    var omitted = Number(view.refs_omitted || 0);
    var groups = evidenceGroupsOf(story);
    var groupsNote = !isMissing(story.evidence_groups_note) && String(story.evidence_groups_note).trim() !== ""
      ? String(story.evidence_groups_note) : null;

    renderExampleLine(view, host);

    if (groups !== null && groups.length) {
      renderEvidenceGroups(host, groups);
      if (omitted > 0) host.appendChild(el("div", "foot-note", refsOmittedText(omitted)));
      if (agentLink) host.appendChild(agentLink);
      host.appendChild(el("div", "foot-note", "按服务端用例分组（group.case）；只做存在性探测（GET …/evidence/exists），不在页面打开文件正文。"));
      return;
    }
    if (groups !== null && !groups.length && groupsNote) {
      /* 无法分组：服务端给了原因，照原文显示；refs 仍平铺，不吞证据。 */
      host.appendChild(el("div", "nd-evidence-groups-note", groupsNote));
    }

    if (!refs.length) {
      var detail = view.detail && typeof view.detail === "object" && !Array.isArray(view.detail) ? view.detail : {};
      var terminal = (Array.isArray(view.events) ? view.events : []).some(function (event) {
        return event && (event.kind === "node_finished" || event.kind === "node_failed");
      });
      var pendingNote = view.known !== false && !terminal && !Object.keys(detail).length;
      var text = null;
      if (noteText || (groupsNote && groups !== null && !groups.length)) {
        text = null;  // 服务端已给证据说明：不得再报"证据缺失"（P-20/P-23/P-27）
      } else if (story.not_executed === true || noteKind === "not_executed") {
        text = "本轮未执行（无证据）。";
      } else if (story.not_reached === true) {
        text = "本轮没有走到这个节点，没有证据文件。";
      } else if (omitted) {
        text = refsOmittedText(omitted);
      } else if (pendingNote) {
        text = "节点还没收尾：refs 会随 node_finished / node_failed 一起下发（本面板不猜证据位置）。";
      } else if (noteKind === "agent_calls") {
        text = "证据在 Agent 调用记录 / 工作窗口（本面板不打开正文）。";
      } else {
        text = "证据缺失：服务端未下发 refs（本面板不猜证据位置）。";
      }
      if (text) host.appendChild(el("div", "nd-empty", text));
      if (agentLink) host.appendChild(agentLink);
      return;
    }
    renderRefRows(host, refs);
    if (omitted > 0) {
      host.appendChild(el("div", "foot-note", refsOmittedText(omitted)));
    }
    if (agentLink) host.appendChild(agentLink);
    host.appendChild(el("div", "foot-note", "只做存在性探测（GET …/evidence/exists）；不在页面打开文件正文。"));
  }

  function failureTexts(view) {
    var events = Array.isArray(view.events) ? view.events : [];
    var failures = events.filter(function (event) { return event && event.kind === "node_failed"; });
    var errors = [];
    failures.forEach(function (event) {
      var detail = event.detail && typeof event.detail === "object" ? event.detail : {};
      if (detail.error) errors.push(String(detail.error));
      else if (detail.message) errors.push(String(detail.message));
    });
    var viewDetail = view.detail && typeof view.detail === "object" ? view.detail : {};
    if (viewDetail.error) errors.push(String(viewDetail.error));
    if (view.error) errors.push(String(view.error));
    if (view.last_error) errors.push(String(view.last_error));
    errors = errors.filter(function (text, index) { return errors.indexOf(text) === index; });
    return { failures: failures, errors: errors };
  }

  function renderFailure(view) {
    var host = $("ndFailure");
    if (!host) return;
    var found = failureTexts(view);
    var block = $("ndFailureBlock");
    var hasAnything = found.failures.length > 0 || found.errors.length > 0;
    if (block) block.classList.toggle("hidden", !hasAnything);
    if (!hasAnything) return;
    var box = el("div", "nd-failure");
    box.appendChild(el("b", null, "节点失败（node_failed）"));
    if (found.errors.length) {
      var pre = el("pre");
      pre.textContent = found.errors.join("\n\n");
      box.appendChild(pre);
    } else {
      box.appendChild(el("div", null, "服务端下发了 node_failed 事件，但未下发 error 原文（缺口，不补写）。"));
    }
    var last = found.failures.length ? found.failures[found.failures.length - 1] : null;
    if (last) {
      var echo = el("div", "tiny");
      echo.textContent = "最后事件：#" + (isMissing(last.seq) ? "—" : String(last.seq)) + " " +
        (last.kind || "") + " · " + (isMissing(last.status) ? "status 未下发" : String(last.status)) +
        (fmtTs(last.ts) ? " · " + fmtTs(last.ts) : "");
      box.appendChild(echo);
    }
    host.appendChild(box);
  }

  function renderMissing(view) {
    var host = $("ndMissing");
    if (!host) return;
    var missing = Array.isArray(view.missing_fields) ? view.missing_fields.filter(function (m) { return m !== null && m !== undefined; }) : [];
    if (!missing.length) {
      host.appendChild(el("div", "tiny muted", "该节点的必含字段已全部下发（missing_fields 为空）。"));
      return;
    }
    var box = el("div", "nd-missing");
    box.appendChild(el("b", null, "未下发字段："));
    box.appendChild(document.createTextNode(missing.map(String).join("、")));
    box.appendChild(el("div", "tiny", "服务端缺失由 missing_fields 显式列出；界面不猜、不补默认值；历史 run 不回填。"));
    host.appendChild(box);
  }

  function render(view) {
    clear($("ndError"));
    setText("ndStatus", statusText(view, view.status));
    var statusEl = $("ndStatus");
    if (statusEl) {
      var hasFailure = (Array.isArray(view.events) ? view.events : []).some(function (event) {
        return event && event.kind === "node_failed";
      });
      statusEl.className = "chip mono" + (hasFailure ? " bad" : "");
      statusEl.title = "服务端 status 原值；中文只是释义，原值逐字保留，不折算成完成/失败。";
    }
    var name = view.name || (s.target && s.target.fallback ? s.target.fallback.name : null);
    setText("ndTitle", String(view.node || (s.target ? s.target.node : "节点")) + (name ? " " + name : ""));
    setText("ndSub", s.target.runId + " / " + s.target.node + " · 只读投影（" +
      (view.authority ? String(view.authority) : "projection") + "）");

    if (view.known === false) {
      var warn = el("div", "alert warn");
      warn.textContent = "服务端未登记该节点（known=false）：以下为该节点在事件流中的原始记录与空投影；" +
        "「未登记」不等于「未执行」，也不据此判定失败。";
      $("ndError").appendChild(warn);
    }

    renderMeta(view);
    renderPurpose(view);
    renderModeNote(view);
    renderResult(view);
    renderGateBlock(view);
    renderKeyResults(view);
    renderSteps(view);
    renderEvidence(view);
    renderFailure(view);
    renderIdentity(view);
    renderEvents(view);
    renderDetail(view);
    renderSummaryRaw(view);
    renderMissing(view);
  }

  function init(requestApi) {
    api = requestApi;
    var dialog = $("nodeDetail");
    if (!dialog) return;
    var closeBtn = $("ndClose");
    if (closeBtn) closeBtn.addEventListener("click", close);
    var refreshBtn = $("ndRefresh");
    if (refreshBtn) refreshBtn.addEventListener("click", function () {
      if (s.open) load();
    });
    dialog.addEventListener("cancel", function (event) {
      event.preventDefault();
      if (s.overlay) { closeOverlay(); return; }  // Esc 只关上层
      close();
    });
    dialog.addEventListener("close", function () {
      closeOverlay(false);
      if (s.open) {
        s.epoch++;
        s.request++;
        s.open = false;
        s.data = null;
        s.target = null;
        s.gateBridge = null;
      }
    });
    var diffClose = $("ndDiffClose");
    if (diffClose) diffClose.addEventListener("click", function () { closeOverlay(); });
    /* 报告浮窗是独立 <dialog>（report-viewer.js 自管 Esc/焦点/遮罩），这里不再绑定。 */
    var diffOverlay = $("ndDiffOverlay");
    if (diffOverlay) {
      diffOverlay.addEventListener("click", function (event) {
        if (event.target === diffOverlay) closeOverlay();
      });
    }
  }

  return { open: open, close: close, init: init };
})();
