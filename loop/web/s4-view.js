/* S4（SPEC-REV-16 §2 / §3 / §6.3）只读投影的**展示层纯函数**。
 *
 * 不读全局、不发请求、不写 DOM：只把服务端下发的字段整理成可读文本，
 * 供 Agent 窗口（agent-window.js）与角色卡（app.js）共用同一份格式化实现。
 *
 * 红线 8：所有判断值都由服务端给出 —— 无进展 `state`/`silence_s`/`threshold_s`、
 * 压缩次数与来源、指令 `accepted/applied/effective` 三态、WM 可用性与原因、
 * 经验采用/拒用。本层**只做取整与标签映射**，不重算阈值、不推断状态、不合并三态。
 * 未知枚举保留服务端原值，未知数字显示「未知」，绝不折算成 0。
 */
(function (root) {
  "use strict";

  /* 服务端枚举 → 中文标签。未登记的枚举原样显示（不猜语义）。 */
  var EXECUTION = { real: "真实执行", standin: "替身（演练）", unknown: "未知（未记录）", not_started: "未开始" };
  var STATE = { idle: "待命", working: "运行中", waiting: "等待", done: "完成", failed: "失败" };
  /* §3.1：`unknown` 必须说"未知（缺时间/记录）"，不得显示成正常。 */
  var NO_PROGRESS = { ok: "正常", warn: "告警", unknown: "无进展未知（缺时间/记录）",
    "n/a": "不适用（非运行中）" };
  var ACCEPTED = { accepted: "已接收", rejected: "未接收", pending: "待接收", unknown: "未知" };
  var APPLIED = { applied: "已应用", not_applied: "未应用", pending: "待应用", unknown: "未知" };
  var EFFECTIVE = { effective: "当前生效", not_effective: "未生效", expired: "已过期", unknown: "未知" };
  var WM_AVAIL = { verified: "可用（已核验）", unavailable: "不可用", unknown: "可用性未知" };
  var REASON = {
    target_missing: "目标实例缺失（Host 尚未落账）",
    target_not_loopback: "目标不是本机回环地址",
    target_invalid: "目标地址非法",
    upstream_unreachable: "上游实例不可达",
    upstream_timeout: "上游实例超时",
    upstream_auth: "上游鉴权失败（401/403）",
    health_unknown: "实例健康状态未知",
    metadata_unavailable: "可用性元数据读取失败",
    proxy_unreachable: "同源反代不可达",
    embedded_load_failed: "内嵌加载失败（CSP/响应头变化）",
    embed_timeout: "内嵌加载超时"
  };
  /* §6.2 会话副本专用的 reason 族（REV-16 §9-16：此前前端只映射代理 8 枚举，`session_*` 直接显示英文枚举）。
   * 只做文案映射，未知 reason 原样显示 —— 前端不重算"能不能导出"。 */
  var SESSION_REASON = {
    session_metadata_missing: "会话元数据缺失（Host 尚未落账实例）",
    session_metadata_invalid: "会话元数据损坏或字段非法",
    session_owner_mismatch: "该会话不属于本节点/本 attempt（不跨 attempt 借用）",
    session_log_missing: "元数据未声明会话日志（Host 未落账 session_log）",
    session_log_invalid: "会话日志路径非法（越界或符号链接）",
    session_log_unavailable: "会话日志当前不可读（缺解码器或文件缺失）"
  };

  /* §6.1（S7c 只增）`stream` = 反代的**传输能力事实**：只透传 HTTP，WebSocket 升级不通（§9-2）。
   * 前端只渲染服务端下发的值；旧服务端没下发就不显示这一行（不自己推断"有没有实时流"）。 */
  var STREAM = {
    http_only: "实时事件流走 WebSocket，反代暂不支持升级（REV-16 §9-2）：页面可打开、"
      + "可读快照，实时更新可能停；需要实时请用「在新标签页打开」。"
  };
  var UNSET = "未记录";

  function has(map, key) {
    return Object.prototype.hasOwnProperty.call(map, key);
  }

  function label(map, value, fallback) {
    if (value === null || value === undefined || value === "") return fallback;
    var key = String(value);
    return has(map, key) ? map[key] : key;
  }

  function present(value) {
    return value !== null && value !== undefined && value !== "";
  }

  /* 时间只用服务端给的 epoch 秒格式化；不取墙钟、不比较字符串。 */
  function clock(ts) {
    if (typeof ts !== "number" || !isFinite(ts)) return "时间未知";
    try {
      return new Date(ts * 1000).toLocaleTimeString();
    } catch (e) {
      return "时间未知";
    }
  }

  function seconds(value) {
    if (typeof value !== "number" || !isFinite(value) || value < 0) return "未知";
    return Math.floor(value) + " s";
  }

  /* 分钟只做取整展示：N 分钟由服务端 `silence_s` 得出，判据不在前端。 */
  function minutes(value) {
    if (typeof value !== "number" || !isFinite(value) || value < 0) return null;
    return Math.floor(value / 60);
  }

  function eventLine(event) {
    if (!event || typeof event !== "object") return UNSET;
    var parts = [present(event.kind) ? String(event.kind) : "未知事件"];
    if (present(event.status)) parts.push(String(event.status));
    if (typeof event.age_s === "number" && isFinite(event.age_s)) {
      parts.push("距读取 " + seconds(event.age_s));
    }
    parts.push(clock(event.ts));
    return parts.join(" · ");
  }

  /* §2.2：压缩次数只认服务端来源；`count=null` 必须显示「未知」，不得显示 0。 */
  function compactionLine(compaction) {
    var block = compaction && typeof compaction === "object" ? compaction : {};
    var source = present(block.source) ? String(block.source) : "unknown";
    if (block.count === null || block.count === undefined) {
      var text = source === "unknown"
        ? "未知（无 session log 来源）"
        : "未知（来源 " + source + " 未给出次数）";
      if (present(block.error)) text += " · 解析错误：" + String(block.error);
      return text;
    }
    var line = String(block.count) + " 次（来源 " + source + "）";
    if (present(block.error)) line += " · 解析错误：" + String(block.error);
    return line;
  }

  /* §2.1 运行摘要：一个字段一行，未知一律「未记录」/「未知」。 */
  function summary(progress) {
    if (!progress || typeof progress !== "object") return null;
    var identity = progress.identity && typeof progress.identity === "object" ? progress.identity : {};
    var np = progress.no_progress && typeof progress.no_progress === "object" ? progress.no_progress : {};
    var action = progress.current_action;
    var tool = progress.last_tool;
    var error = progress.last_error;
    var npParts = [label(NO_PROGRESS, np.state, "未知")];
    if (typeof np.silence_s === "number" && isFinite(np.silence_s)) {
      npParts.push("静默 " + seconds(np.silence_s));
    }
    if (typeof np.threshold_s === "number" && isFinite(np.threshold_s)) {
      npParts.push("阈值 " + String(np.threshold_s) + " s");
    }
    return {
      state: label(STATE, progress.state, "未知"),
      action: action && typeof action === "object"
        ? [present(action.kind) ? String(action.kind) : "未知动作",
          present(action.status) ? String(action.status) : "状态未知",
          clock(action.ts)].join(" · ")
        : UNSET,
      lastEvent: eventLine(progress.last_event),
      lastTool: tool && typeof tool === "object"
        ? [present(tool.name) ? String(tool.name) : "未知工具",
          present(tool.status) ? String(tool.status) : "状态未知",
          clock(tool.ts)].join(" · ")
        : UNSET,
      lastError: error && typeof error === "object"
        ? [present(error.message) ? String(error.message) : "错误内容未记录",
          "来源 " + (present(error.source) ? String(error.source) : "未知"),
          clock(error.ts)].join(" · ")
        : "无错误记录",
      compaction: compactionLine(progress.compaction),
      identity: [
        present(identity.run_id) ? String(identity.run_id) : "运行未知",
        present(identity.node) ? String(identity.node) : "节点未知",
        "尝试 " + (identity.attempt === null || identity.attempt === undefined
          ? "未知" : "#" + String(identity.attempt)),
        "会话 " + (present(identity.session_id) ? String(identity.session_id) : "未知")
      ].join(" / "),
      execution: label(EXECUTION, progress.execution, "未知"),
      noProgress: npParts.join(" · ") + (present(np.reason) ? " · " + String(np.reason) : ""),
      elapsed: typeof progress.elapsed_s === "number" && isFinite(progress.elapsed_s)
        ? seconds(progress.elapsed_s) : "未知",
      authority: progress.authority === "projection" ? "投影，非权威" : "来源未标注"
    };
  }

  /* §3.3：只有服务端 `no_progress.state === "warn"` 才出红字；N 分钟从 `silence_s` 取整。 */
  function noProgressBanner(progress) {
    var np = progress && progress.no_progress && typeof progress.no_progress === "object"
      ? progress.no_progress : null;
    if (!np || np.state !== "warn") return { visible: false, text: "" };
    var count = minutes(np.silence_s);
    var parts = ["无进展 " + (count === null ? "分钟未知" : count + " 分钟")];
    if (typeof np.threshold_s === "number" && isFinite(np.threshold_s)) {
      parts.push("服务端阈值 " + String(np.threshold_s) + " s");
    }
    parts.push("最后事件：" + eventLine(progress.last_event));
    var error = progress.last_error;
    parts.push("最后错误：" + (error && present(error.message)
      ? String(error.message) : "无错误记录"));
    if (present(np.reason)) parts.push("判据说明：" + String(np.reason));
    return { visible: true, text: parts.join(" · ") };
  }

  /* §6.3 指令三态：每行三列分别来自 `state_accepted` / `state_applied` / `state_effective`，
   * 不互相推导（回执 ≠ 生效）。 */
  function instructions(explain) {
    var block = explain && explain.instructions;
    if (!block || typeof block !== "object") return null;
    var items = Array.isArray(block.items) ? block.items : [];
    return {
      revision: present(block.revision) ? String(block.revision) : "未知",
      source: present(block.source) ? String(block.source) : "未知",
      rows: items.map(function (item) {
        var row = item && typeof item === "object" ? item : {};
        var accepted = label(ACCEPTED, row.state_accepted, "未知");
        if (present(row.accepted_at)) accepted += " · " + String(row.accepted_at);
        var applied = label(APPLIED, row.state_applied, "未知");
        if (present(row.applied_attempt)) applied += " · 尝试 #" + String(row.applied_attempt);
        /* `applied_ref` 是附加字段（非契约必需）：有就补节点身份，没有就不猜。 */
        var ref = row.applied_ref && typeof row.applied_ref === "object" ? row.applied_ref : null;
        if (ref && present(ref.node)) applied += " · 节点 " + String(ref.node);
        var effective = label(EFFECTIVE, row.state_effective, "未知");
        if (present(row.effective_attempt)) effective += " · 尝试 #" + String(row.effective_attempt);
        if (present(row.unavailable_reason)) effective += "（原因：" + String(row.unavailable_reason) + "）";
        return {
          id: present(row.id) ? String(row.id) : "未知指令",
          scope: present(row.scope) ? String(row.scope) : "作用域未知",
          preview: present(row.text_preview) ? String(row.text_preview) : "（无正文预览）",
          accepted: accepted,
          applied: applied,
          effective: effective
        };
      })
    };
  }

  /* §6.3 `scope_expiry`：未判定就写「未判定」，不得显示成"仍生效"。 */
  function scopeExpiry(explain) {
    var block = explain && explain.scope_expiry;
    if (!block || typeof block !== "object") return "到期判定：未记录";
    if (block.determined === true) {
      return "到期判定：服务端已判定（" + (present(block.state) ? String(block.state) : "状态未知") + "）"
        + (present(block.note) ? " · " + String(block.note) : "");
    }
    return "到期判定：未判定"
      + (present(block.note) ? " · " + String(block.note) : "")
      + (present(block.state) ? "（state=" + String(block.state) + "）" : "");
  }

  /* §6.3 WM：只读可用性与原因，缺原因也如实说缺。 */
  function workingMemoryLines(explain) {
    var block = explain && explain.working_memory;
    if (!block || typeof block !== "object") return null;
    var items = Array.isArray(block.items) ? block.items : [];
    if (!items.length) return ["服务端未下发工作记忆条目（空集）"];
    return items.map(function (item) {
      var row = item && typeof item === "object" ? item : {};
      var line = (present(row.id) ? String(row.id) : "未知条目")
        + " · " + (present(row.kind) ? String(row.kind) : "种类未知")
        + " · " + label(WM_AVAIL, row.availability, "可用性未知");
      if (row.availability && row.availability !== "verified") {
        line += "（原因：" + (present(row.unavailable_reason)
          ? String(row.unavailable_reason) : "服务端未给原因") + "）";
      }
      if (present(row.source_ref)) line += " · 来源 " + String(row.source_ref);
      return line;
    });
  }

  /* §6.3 EXP：采用/拒用只读展示，不重算适用性、不写回经验。 */
  function experienceLines(explain) {
    var block = explain && explain.experiences;
    if (!block || typeof block !== "object") return null;
    var lines = [];
    (Array.isArray(block.selected) ? block.selected : []).forEach(function (item) {
      var row = item && typeof item === "object" ? item : {};
      lines.push("采用 · " + (present(row.id) ? String(row.id) : "未知条目")
        + (present(row.reason) ? " · " + String(row.reason) : ""));
    });
    (Array.isArray(block.rejected) ? block.rejected : []).forEach(function (item) {
      var row = item && typeof item === "object" ? item : {};
      lines.push("拒用 · " + (present(row.id) ? String(row.id) : "未知条目")
        + " · " + (present(row.reason) ? String(row.reason) : "服务端未给原因"));
    });
    return lines.length ? lines : ["服务端未选择任何经验（selected/rejected 为空）"];
  }

  /* §5.5 不可用原因：只做文案映射，未知 reason 原样显示。 */
  function instanceReason(reason) {
    if (!present(reason)) return "原因未知（服务端未给 reason）";
    var key = String(reason);
    if (has(REASON, key)) return REASON[key] + "（" + key + "）";
    /* 反代拒绝/未就绪时只有 HTTP 码（如 400 `X-Instance-Proxy: rejected`）：如实显示，不改写成人工介入。 */
    var code = /^http_(\d{3})$/.exec(key);
    if (code) return "反代返回 HTTP " + code[1] + "（请求被拒绝或实例未就绪）";
    return key;
  }

  /* §6.2 会话副本 reason：只做文案映射；未知 reason 原样显示（不折叠成"不可用"这种模糊说法）。 */
  function sessionReason(reason) {
    if (!present(reason)) return "原因未知（服务端未给 reason）";
    var key = String(reason);
    if (has(SESSION_REASON, key)) return SESSION_REASON[key] + "（" + key + "）";
    return key;
  }

  /* §6.1 `stream` 的能力说明：未下发 ⇒ 空串（界面不显示、不猜）。
   * 未知枚举原样显示，不折算成"正常"。 */
  function streamNote(stream) {
    if (!present(stream)) return "";
    var key = String(stream);
    if (has(STREAM, key)) return STREAM[key];
    return "实时流能力：" + key + "（服务端未登记该值的含义）";
  }

  /* 角色卡一行摘要：与窗口同一份投影字段，不另算判据。 */
  function cardLine(progress) {
    if (!progress || typeof progress !== "object") {
      return "运行摘要：未记录（旧记录或服务端未投影）";
    }
    var np = progress.no_progress && typeof progress.no_progress === "object"
      ? progress.no_progress : {};
    var parts = [];
    if (np.state === "warn") {
      var count = minutes(np.silence_s);
      parts.push("无进展 " + (count === null ? "分钟未知" : count + " 分钟"));
    }
    parts.push("当前动作：" + (progress.current_action && present(progress.current_action.kind)
      ? String(progress.current_action.kind) : UNSET));
    parts.push("最后事件：" + (progress.last_event && present(progress.last_event.kind)
      ? String(progress.last_event.kind) : UNSET));
    parts.push("压缩 " + compactionLine(progress.compaction));
    parts.push("方式 " + label(EXECUTION, progress.execution, "未知"));
    return parts.join(" · ");
  }

  var api = {
    label: label,
    clock: clock,
    seconds: seconds,
    minutes: minutes,
    eventLine: eventLine,
    compactionLine: compactionLine,
    summary: summary,
    noProgressBanner: noProgressBanner,
    instructions: instructions,
    scopeExpiry: scopeExpiry,
    workingMemoryLines: workingMemoryLines,
    experienceLines: experienceLines,
    instanceReason: instanceReason,
    sessionReason: sessionReason,
    streamNote: streamNote,
    cardLine: cardLine
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.S4View = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
