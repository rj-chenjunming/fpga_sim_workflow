/* 每个窗口绑定运行/节点/会话；输入 DOM 不参与轮询重建。 */
"use strict";
window.AgentWindow = (function () {
  var api, target = null, epoch = 0, request = 0, data = null, attempt = "", counter = 0;
  var pending = Object.create(null), draftRequest = null, sessionSeen = null;
  var nodes = ["N3", "N6", "N8", "N10", "N11", "N12"];
  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }
  function key(live) { return JSON.stringify([target.runId, target.node, live.session_id]); }
  function error(message) {
    $("awError").replaceChildren();
    if (message) $("awError").appendChild(el("div", "alert bad", message));
  }
  function isCurrent(token) { return target && $("agentWindow").open && epoch === token; }
  function base() { return "/api/runs/" + encodeURIComponent(target.runId) + "/agents/" + encodeURIComponent(target.node); }
  function controls() {
    var live = data && data.live;
    var historical = live && attempt && Number(attempt) !== live.attempt;
    var busy = live && pending[key(live)];
    var actions = live && !historical && !busy ? (live.available_actions || []) : [];
    [["awSteer", "steer"], ["awPause", "pause"], ["awResume", "resume"], ["awTerminate", "terminate"]].forEach(function (pair) {
      $(pair[0]).disabled = actions.indexOf(pair[1]) < 0;
    });
    $("awSteer").textContent = busy ? "提交中…" : live && live.state === "paused" ? "发送并恢复" : "补充指令并重跑";
    $("awActor").disabled = !!busy;
    $("awMessage").disabled = !!busy;
    $("awControlHint").textContent = historical ? "正在查看历史尝试；切回最新后才能干预当前请求。"
      : !live ? "没有活跃请求，历史窗口只读。"
        : busy || !actions.length ? "命令或请求正在收敛，请等待服务端更新。"
          : live.state === "paused" ? "请求已暂停。恢复或发送新指令后，将发起新的调用尝试。"
            : "可向当前请求补充指令、暂停，或终止该节点。";
  }
  function render(view) {
    if (view.run_id !== target.runId || view.node !== target.node) throw new Error("Agent 响应身份与当前窗口不一致，拒绝启用控制。");
    var live = view.live;
    if (live && sessionSeen && live.session_id !== sessionSeen) {
      epoch++;
      $("awMessage").value = "";
      $("awReceipt").textContent = "调用会话已切换，旧草稿已清空。";
      draftRequest = null;
      error("");
    }
    if (live) sessionSeen = live.session_id;
    data = view;
    $("awIdentity").textContent = target.runId + " / " + target.node + (live ? " / " + live.session_id : " / 历史记录");
    var capsText = window.Capabilities ? window.Capabilities.line(view.capabilities) : "";
    $("awCapabilities").textContent = capsText || "能力事实未知（非模型角色节点或服务端未投影）";
    // 只读展示失败不得阻断基本观察（输入/输出/时间线仍要渲染）。
    try {
      explain(view);
    } catch (e) {
      if ($("awAttempts")) $("awAttempts").textContent = "解释展示失败：" + (e && e.message ? e.message : e);
    }
    var status = live ? {working: "运行中", paused: "已暂停", interrupting: "干预处理中", starting: "正在启动"}[live.state] || live.state : "只读 · 无活跃请求";
    $("awStatus").textContent = status;
    $("awStatus").className = "chip " + (live && live.state === "working" ? "primary" : "");
    var options = [{value: "", label: "跟随最新"}].concat((view.attempts || []).map(function (item) {
      return {value: String(item.attempt), label: "#" + item.attempt + " · " + item.status};
    }));
    var signature = JSON.stringify(options);
    if ($("awAttempt").dataset.options !== signature) {
      $("awAttempt").replaceChildren();
      options.forEach(function (item) { var option = el("option", null, item.label); option.value = item.value; $("awAttempt").appendChild(option); });
      $("awAttempt").dataset.options = signature;
      $("awAttempt").value = attempt;
    }
    var req = view.request;
    $("awModel").textContent = req ? (req.model || "替身 / 未配置模型") + " · 尝试 #" + view.selected_attempt : "尚无调用记录";
    $("awInput").textContent = req ? JSON.stringify(req.input, null, 2) : "该节点尚未产生模型输入。";
    $("awPrompt").textContent = req ? JSON.stringify({info: req.info, instruct: req.instruct, schema: req.schema}, null, 2) : "尚无提示词快照。";
    $("awOutput").textContent = view.result ? JSON.stringify(view.result, null, 2) : req ? "该尝试尚无结果；可能正在执行、被中断或服务已重启。以当前会话状态为准。" : "输出尚未生成。";
    $("awResultStatus").textContent = view.result ? view.result.status : "尚无结果";
    var events = (view.events || []).map(function (e) {
      return {at: typeof e.ts === "number" ? new Date(e.ts * 1000).toLocaleTimeString() : "—", label: e.kind + " · " + e.status,
        detail: JSON.stringify(e.detail || {})};
    });
    var labels = {accepted: "命令已接收", applied: "命令已应用", discarded: "旧尝试已作废", state: "会话状态"};
    (view.controls || []).forEach(function (e) {
      events.push({at: e.at || "—", label: (labels[e.type] || e.type) + " · " + (e.action || e.state || "#" + e.attempt),
        detail: [e.actor, e.message, e.request_id].filter(Boolean).join(" · ")});
    });
    var host = $("awTimeline");
    host.replaceChildren();
    if (!events.length) host.appendChild(el("div", "aw-empty", "尚无节点事件。输入、输出将在实际调用后出现。"));
    else {
      host.appendChild(el("div", "aw-log-count", "最近 " + Math.min(60, events.length) + " 条 / 共 " + events.length + " 条；节点事件与控制记录分组显示"));
      events.slice(-60).reverse().forEach(function (e) {
        var row = el("div", "aw-log-row");
        row.appendChild(el("span", "mono", e.at));
        var body = el("div"); body.appendChild(el("b", null, e.label));
        if (e.detail) body.appendChild(el("p", null, e.detail));
        row.appendChild(body); host.appendChild(row);
      });
    }
    controls();
  }
  async function load() {
    if (!target || !$("agentWindow").open) return;
    var token = epoch, sequence = ++request;
    var path = base() + (attempt ? "?attempt=" + encodeURIComponent(attempt) : "");
    try {
      var view = await api(path);
      if (isCurrent(token) && sequence === request) render(view);
    } catch (e) {
      if (isCurrent(token) && sequence === request) {
        data = null; controls(); $("awStatus").textContent = "读取失败"; error(e.message);
      }
    }
  }
  function close() {
    epoch++; request++; target = null; data = null;
    if ($("agentWindow").open) $("agentWindow").close();
  }
  /* F10/F11：只读解释（预算构成/经验原因/尝试摘要/输入差异）；不发请求、不改记录。 */
  function explain(view) {
    var X = window.ContextExplain;
    var request = view.request || null;
    var budgetEl = $("awBudget");
    var summaryEl = $("awBudgetSummary");
    var attemptsEl = $("awAttempts");
    if (!X || !budgetEl || !summaryEl || !attemptsEl) return;
    if (!request) {
      budgetEl.textContent = "无请求记录（历史为空或该尝试不可读）";
      summaryEl.textContent = "—";
    } else {
      /* R5：预算数字全部来自 Host 的 `context_budget`；本函数不求和、不另算占比、不判上限。 */
      var b = X.budget(view.context_budget);
      var lines = [];
      if (!b.measured) {
        lines.push("预算构成: 未知（该记录没有可重算的计费材料，Host 不估算）");
      } else {
        b.rows.forEach(function (row) { lines.push(row.label + ": " + row.bytes + " B"); });
        lines.push("合计（Host 计费）: " + b.totalBytes + " B");
        lines.push("其中序列化开销（键名/标点）: " + b.overheadBytes + " B");
        lines.push("上限: " + (b.limitBytes === null ? "未知" : b.limitBytes + " B") +
          " · 使用率: " + (b.usedPercent === null ? "未知" : b.usedPercent + "%"));
      }
      var stored = [];
      if (b.storage.offeredBytes !== null) stored.push("offered " + b.storage.offeredBytes + " B");
      if (b.storage.scopeBytes !== null) stored.push("scope " + b.storage.scopeBytes + " B");
      if (stored.length) lines.push("记录存储大小（不计费）: " + stored.join(" · "));
      lines.push("token 估算: 未知（未测量）");
      var reasons = X.experience(request);
      if (reasons.length) {
        lines.push("经验采用/拒绝原因:");
        reasons.forEach(function (item) { lines.push("  - " + item.message); });
      }
      budgetEl.textContent = lines.join("\n");
      summaryEl.textContent = !b.measured ? "未知（未测量）"
        : b.totalBytes + " B" + (b.limitBytes === null ? "" : " / " + b.limitBytes + " B");
    }
    var rows = X.attempts(view.attempts || []);
    var attLines = rows.map(function (row) {
      return "#" + row.attempt + " · " + row.status + " · 方式 " + row.model + " · cycle " + row.cycle;
    });
    if (request && request.input) {
      var diff = X.inputDiff(view.previous_input || {}, request.input);
      attLines.push("");
      if (!view.previous_input) {
        attLines.push("输入差异: 无更早的可比较尝试");
      } else if (!diff.changed) {
        attLines.push("输入差异: 与上一尝试无差异");
      } else {
        attLines.push("输入差异（相对上一尝试）:");
        diff.rows.forEach(function (row) {
          attLines.push("  - " + row.key + "：" + row.change + " · " +
            row.fromBytes + " B → " + row.toBytes + " B");
        });
      }
    }
    attemptsEl.textContent = attLines.length ? attLines.join("\n") : "无尝试记录";
  }

  function reset() {
    data = null; attempt = ""; draftRequest = null; sessionSeen = null;
    $("awActor").value = "human:"; $("awMessage").value = "";
    $("awReceipt").textContent = ""; error("");
    $("awStatus").textContent = "加载中";
    $("awAttempt").value = "";
    $("awModel").textContent = "读取中…";
    $("awCapabilities").textContent = "能力事实读取中…";
    if ($("awBudget")) $("awBudget").textContent = "读取中…";
    if ($("awAttempts")) $("awAttempts").textContent = "读取中…";
    $("awResultStatus").textContent = "读取中…";
    $("awIdentity").textContent = target.runId + " / " + target.node;
    ["awInput", "awPrompt", "awOutput"].forEach(function (id) { $(id).textContent = "读取中…"; });
    $("awTimeline").textContent = "读取实际运行记录…";
    controls();
  }
  function open(options) {
    epoch++; request++;
    target = {runId: String(options.runId), name: options.name,
      nodes: options.nodes.filter(function (n) { return nodes.indexOf(n) >= 0; }), node: options.node};
    if (!target.nodes.length) { target = null; return; }
    if (target.nodes.indexOf(target.node) < 0) target.node = target.nodes[0];
    $("awTitle").textContent = options.name || target.node;
    $("awNode").replaceChildren();
    target.nodes.forEach(function (node) { var option = el("option", null, node); option.value = node; $("awNode").appendChild(option); });
    $("awNode").value = target.node;
    reset();
    if (!$("agentWindow").open) $("agentWindow").showModal();
    load();
  }
  async function submit(action) {
    var live = data && data.live;
    if (!target || !live || (attempt && Number(attempt) !== live.attempt)) return;
    var identity = key(live);
    if (pending[identity] || (live.available_actions || []).indexOf(action) < 0) return;
    var actor = $("awActor").value.trim(), message = $("awMessage").value.trim();
    if (!/^human:.+/.test(actor)) { error("请填写 human:<name> 操作者。"); return; }
    if (action === "steer" && !message) { error("请填写给当前 Agent 的补充指令。"); return; }
    var payload = {action: action, actor: actor, session_id: live.session_id, expected_revision: live.revision};
    if (action === "steer") payload.message = message;
    var signature = JSON.stringify(payload);
    if (!draftRequest || draftRequest.signature !== signature) draftRequest = {signature: signature, id: "aw-" + Date.now() + "-" + (++counter)};
    payload.request_id = draftRequest.id;
    var token = epoch, path = base() + "/control";
    pending[identity] = true; error(""); controls();
    try {
      var receipt = await api(path, {method: "POST", body: payload});
      if (isCurrent(token) && data && data.live && key(data.live) === identity) {
        $("awReceipt").textContent = receipt.status === "accepted" ? "命令已接收；实际生效状态请看运行动态。" : "已返回控制回执，请核对运行动态。";
        if (action === "steer") $("awMessage").value = "";
      }
    } catch (e) { if (isCurrent(token)) error(e.message); }
    finally {
      delete pending[identity];
      if (isCurrent(token)) await load();
      if (target) controls();
    }
  }
  return {open: open, close: close, init: function (requestApi) {
    api = requestApi;
    $("awClose").addEventListener("click", close);
    $("agentWindow").addEventListener("cancel", function (event) { event.preventDefault(); close(); });
    $("awRefresh").addEventListener("click", load);
    $("awNode").addEventListener("change", function () { epoch++; request++; target.node = $("awNode").value; reset(); load(); });
    $("awAttempt").addEventListener("change", function () { attempt = $("awAttempt").value; data = null; controls(); load(); });
    [["awSteer", "steer"], ["awPause", "pause"], ["awResume", "resume"], ["awTerminate", "terminate"]].forEach(function (pair) {
      $(pair[0]).addEventListener("click", function () { submit(pair[1]); });
    });
    setInterval(function () { if (!document.hidden && target && $("agentWindow").open) load(); }, 1500);
  }};
})();
