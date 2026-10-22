/* 节点执行详情面板（SPEC-04 §4.2.1 / §6.7；SPEC-REV-01 R4）。
 *
 * 边界：
 *   · 独立 <dialog>，自带状态；执行视图每 1.5 s 全量重建 #stages 不会清掉本面板。
 *   · 只读投影：不做判定、不排序材料、不隐藏缺失；状态显示服务端原值，不折算成"完成/失败"。
 *   · 数据唯一来源 GET /api/runs/{run_id}/nodes/{node}；响应对不上当前身份时拒绝渲染。
 *   · 证据只做存在性探测（GET .../evidence/exists），不在页面打开文件正文。
 *   · 并发/过期回包用 epoch + request 双守卫；切换节点或关闭窗口后旧回包一律丢弃。
 */
"use strict";
window.NodeDetail = (function () {
  var api = null;
  var s = { open: false, epoch: 0, request: 0, target: null, data: null, trigger: null };

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

  /* ---------------- 打开 / 读取 / 关闭 ---------------- */

  function open(options) {
    var dialog = $("nodeDetail");
    if (!dialog || !options || !options.runId || !options.node) return;
    s.epoch++;
    s.request++;
    s.open = true;
    s.data = null;
    s.target = {
      runId: String(options.runId),
      node: String(options.node),
      fallback: options.fallback || null,
      agent: options.agent || null,
      gate: !!options.gate,
      onGate: typeof options.onGate === "function" ? options.onGate : null
    };
    s.trigger = options.trigger || document.activeElement || null;

    setText("ndTitle", s.target.node + (s.target.fallback && s.target.fallback.name ? " " + s.target.fallback.name : ""));
    setText("ndSub", s.target.runId + " / " + s.target.node + " · 只读投影（authority=projection）");
    setText("ndPath", "GET /api/runs/" + s.target.runId + "/nodes/" + s.target.node);
    var statusEl = $("ndStatus");
    if (statusEl) {
      statusEl.className = "chip";
      statusEl.textContent = "加载中";
    }
    clear($("ndError"));
    clear($("ndIdentity"));
    clear($("ndAgentJump"));
    clear($("ndEvents"));
    clear($("ndSummary"));
    clear($("ndDetailBody"));
    clear($("ndRefs"));
    clear($("ndFailure"));
    clear($("ndMissing"));
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
    s.epoch++;
    s.request++;
    s.open = false;
    s.data = null;
    s.target = null;
    if (dialog && dialog.open) dialog.close();
    s.trigger = null;
    if (node) focusChip(node);
  }

  /* ---------------- 渲染：身份 / 执行 / 结果 / 证据 / 失败 ---------------- */

  function statusChip(status) {
    var text = isMissing(status) || status === "" ? "未下发" : String(status);
    var chip = el("span", "chip mono" + (isMissing(status) || status === "" ? " warn" : ""), text);
    chip.title = "服务端原值；面板不折算成「完成/失败」。";
    return chip;
  }

  function sourceChip(source) {
    if (isMissing(source) || source === "") {
      return el("span", "chip warn", "未下发");
    }
    var raw = String(source);
    var fixture = /drill|fixture|standin/i.test(raw);
    var chip = el("span", "chip mono" + (fixture ? " warn" : ""), raw);
    chip.title = fixture
      ? "执行来源含夹具/替身标记：不是真实环境实测结论。"
      : "执行来源（服务端下发原值）。";
    return chip;
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

  function identityValue(serverValue, fallbackValue) {
    if (!isMissing(serverValue) && serverValue !== "") return { text: String(serverValue), fallback: false };
    if (!isMissing(fallbackValue) && fallbackValue !== "") return { text: String(fallbackValue), fallback: true };
    return null;
  }

  function renderIdentity(view) {
    var host = $("ndIdentity");
    if (!host) return;
    var target = s.target;
    var name = identityValue(view.name, target && target.fallback ? target.fallback.name : null);
    var owner = identityValue(view.owner, target && target.fallback ? target.fallback.owner : null);
    var started = fmtTs(view.started_at);
    var finished = fmtTs(view.finished_at);
    kvRow(host, "节点", el("span", "mono", String(view.node || (target ? target.node : "—"))));
    kvRow(host, "名称", name
      ? el("span", null, name.text + (name.fallback ? "（服务端未下发；前端展示兜底）" : ""))
      : null);
    kvRow(host, "owner", owner
      ? el("span", null, owner.text + (owner.fallback ? "（服务端未下发；前端展示兜底）" : ""))
      : null);
    kvRow(host, "状态（原值）", statusChip(view.status));
    kvRow(host, "来源 source", sourceChip(view.source));
    kvRow(host, "开始时间", started);
    kvRow(host, "结束时间", finished);
    kvRow(host, "服务端已登记", view.known === true ? "是（known=true）" : view.known === false ? "否（known=false：空投影 + 原始事件）" : null);
    kvRow(host, "投影标识", view.authority ? String(view.authority) : null);

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

  function renderResult(view) {
    var summaryHost = $("ndSummary");
    var detailHost = $("ndDetailBody");
    if (!summaryHost || !detailHost) return;
    var detail = view.detail;
    var summary = view.summary;
    var summaryFromDetail = false;
    if ((isMissing(summary) || summary === "") && detail && typeof detail === "object" && !Array.isArray(detail)) {
      summary = detail.summary;
      summaryFromDetail = !isMissing(summary) && summary !== "";
    }
    if (isMissing(summary) || summary === "") {
      summaryHost.appendChild(el("div", "nd-empty", "结果摘要未下发（服务端未提供 summary；界面不补默认值）。"));
    } else {
      var line = el("div", "nd-summary");
      line.textContent = String(summary) + (summaryFromDetail ? "（取自 detail.summary；顶层 summary 未下发）" : "");
      summaryHost.appendChild(line);
    }
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
    var rawBox = el("details", "nd-raw");
    rawBox.appendChild(el("summary", null, "原始 detail JSON（只读，未改写）"));
    var rawPre = el("pre", null);
    rawPre.textContent = JSON.stringify(detail, null, 2);
    rawBox.appendChild(rawPre);
    detailHost.appendChild(rawBox);
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

  function renderEvidence(view) {
    var host = $("ndRefs");
    if (!host) return;
    var refs = Array.isArray(view.refs) ? view.refs : [];
    var omitted = Number(view.refs_omitted || 0);
    if (!refs.length) {
      host.appendChild(el("div", "nd-empty", refsOmittedText(omitted)
        || "证据缺失：服务端未下发 refs（本面板不猜证据位置）。"));
      return;
    }
    refs.forEach(function (ref) {
      if (isMissing(ref)) return;
      var row = el("div", "nd-ref");
      var path = el("span", "mono", String(ref));
      path.title = String(ref);
      row.appendChild(path);
      var button = el("button", "btn btn-sm", "探测存在性");
      button.type = "button";
      var output = el("span", "nd-probe", "未探测");
      button.addEventListener("click", function () { probeRef(String(ref), button, output); });
      row.appendChild(button);
      row.appendChild(output);
      host.appendChild(row);
    });
    if (omitted > 0) {
      host.appendChild(el("div", "foot-note", refsOmittedText(omitted)));
    }
    host.appendChild(el("div", "foot-note", "只做存在性探测（GET …/evidence/exists）；不在页面打开文件正文。"));
  }

  function renderFailure(view) {
    var host = $("ndFailure");
    if (!host) return;
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

    if (!failures.length && !errors.length) {
      host.appendChild(el("div", "nd-empty",
        "没有 node_failed 事件；本区块只在失败时显示 error 原文。当前 status 原值：" +
        (isMissing(view.status) ? "未下发" : String(view.status)) + "。"));
      return;
    }
    var box = el("div", "nd-failure");
    box.appendChild(el("b", null, "节点失败（node_failed）"));
    if (errors.length) {
      var pre = el("pre");
      pre.textContent = errors.join("\n\n");
      box.appendChild(pre);
    } else {
      box.appendChild(el("div", null, "服务端下发了 node_failed 事件，但未下发 error 原文（缺口，不补写）。"));
    }
    var last = failures.length ? failures[failures.length - 1] : null;
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
    if (!missing.length) return;
    var box = el("div", "nd-missing");
    box.appendChild(el("b", null, "未下发字段："));
    box.appendChild(document.createTextNode(missing.map(String).join("、")));
    box.appendChild(el("div", "tiny", "服务端缺失由 missing_fields 显式列出；界面不猜、不补默认值；历史 run 不回填。"));
    host.appendChild(box);
  }

  function render(view) {
    clear($("ndError"));
    setText("ndStatus", isMissing(view.status) ? "status 未下发" : String(view.status));
    var statusEl = $("ndStatus");
    if (statusEl) {
      var hasFailure = (Array.isArray(view.events) ? view.events : []).some(function (event) {
        return event && event.kind === "node_failed";
      });
      statusEl.className = "chip mono" + (hasFailure ? " bad" : "");
      statusEl.title = "服务端 status 原值；不折算成完成/失败。";
    }
    var name = identityValue(view.name, s.target && s.target.fallback ? s.target.fallback.name : null);
    setText("ndTitle", String(view.node || (s.target ? s.target.node : "节点")) + (name ? " " + name.text : ""));
    setText("ndSub", s.target.runId + " / " + s.target.node + " · 只读投影（" +
      (view.authority ? String(view.authority) : "projection") + "）");

    if (view.known === false) {
      var warn = el("div", "alert warn");
      warn.textContent = "服务端未登记该节点（known=false）：以下为该节点在事件流中的原始记录与空投影；" +
        "「未登记」不等于「未执行」，也不据此判定失败。";
      $("ndError").appendChild(warn);
    }

    renderIdentity(view);
    renderEvents(view);
    renderResult(view);
    renderEvidence(view);
    renderFailure(view);
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
      close();
    });
    dialog.addEventListener("close", function () {
      if (s.open) {
        s.epoch++;
        s.request++;
        s.open = false;
        s.data = null;
        s.target = null;
      }
    });
  }

  return { open: open, close: close, init: init };
})();
