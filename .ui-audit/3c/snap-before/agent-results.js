/* SPEC-09: presentation of stored facts, without business validation or I/O. */
"use strict";
window.AgentResults = (function () {
  var roles = {
    N3: ["差异分析", "把原始差异整理为变更分组与需要人工关注的问题。"],
    N6: ["用例修订", "依据已确认差异，为目标用例提出候选修订。"],
    N8: ["静态复核", "检查修订后的用例，给出检查依据与必须修复项。"],
    N10: ["失败分类", "核对失败分类与依据；业务计数以 Host 为准。"],
    N11: ["证据守护", "检查证据链并提出返工建议；完整性由 Host 判定。"],
    N12: ["评估报告", "整理本轮报告与尚未闭环的问题。"]
  };
  function object(value) { return value && typeof value === "object" && !Array.isArray(value) ? value : null; }
  function text(value) {
    return value === undefined || value === null || value === "" ? "未记录"
      : typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
  }
  function rows(value) { return Array.isArray(value) ? value : []; }
  function historical(view) {
    return !!(view.live && Number(view.selected_attempt) !== Number(view.live.attempt));
  }
  function present(node, view) {
    var role = roles[node] || [node, "查看实际调用记录。"];
    var result = object(view.result), payload = result && object(result.payload);
    var validation = result && object(result.validation);
    var standin = !!(result && result.status === "standin" || payload && payload.standin === true);
    var validated = !!(result && result.status === "validated" && validation && validation.ok === true && !standin);
    var accepted = validated && object(validation.accepted);
    var data = accepted && Object.keys(accepted).length ? accepted : payload && object(payload.data);
    var fields = {N3: ["summary", "groups", "risky_points"], N6: ["revisions", "observation_points", "rework_resolution", "notes"], N8: ["verdict", "findings", "must_fix"]};
    if (data && fields[node] && !fields[node].some(function (field) { return Object.prototype.hasOwnProperty.call(data, field); })) data = null;
    var sections = [];
    function section(heading, lines, edits) { sections.push({heading: heading, lines: lines, edits: edits || []}); }
    function list(heading, items) {
      section(heading, rows(items).length ? rows(items).map(text) : ["未记录条目；以原始输出为准。"]);
    }
    var label = !result ? "系统校验状态未确认" : standin ? "演练替身；不作为真实模型校验结论"
      : validated ? "系统校验通过；业务放行另行判定"
        : result.status === "validation_failed" ? "候选未通过系统校验"
          : "系统校验状态未确认 · " + text(result.status);
    var mode = standin ? "演练替身" : payload && payload.standin === false ? "真实模型" : "执行方式未记录";
    if (result && !validated && !standin) section("候选 / 未通过校验", ["此处返回不作为已接受成果。"]);
    if (validation && rows(validation.problems).length) list("系统校验问题", validation.problems);
    if (result && result.error) section("执行错误", [text(result.error)]);
    if (payload && payload.error) section("模型调用错误", [text(payload.error)]);
    if (!result) {
      section("当前成果", [!view.request ? "暂无可读取记录，执行状态未确认"
        : historical(view) ? "所选历史尝试尚无结果；不能代表当前执行。"
          : view.live ? "该尝试尚无结果；当前执行状态请看上方。"
            : "该尝试尚无结果；无活跃请求，执行状态未确认。"]);
    } else if (!data) {
      section("当前成果", [standin ? "该记录为演练替身，请查看原始输出。" : "结构未识别，请查看原始输出"]);
    } else if (node === "N3") {
      section("变更摘要", [text(data.summary)]);
      section("变更分组", rows(data.groups).length ? rows(data.groups).map(function (g) {
        g = object(g) || {};
        return "段：" + text(g.segment) + " · 类型：" + text(g.kind) + "\n差异：" + text(g.diff_ids) + "\n依据：" + text(g.why);
      }) : ["未记录分组。"]);
      list("需要人工关注", data.risky_points);
    } else if (node === "N6") {
      section("候选修订", ["候选编辑；实际写入状态请查看节点执行详情"]);
      rows(data.revisions).forEach(function (revision) {
        revision = object(revision) || {};
        section("用例：" + text(revision.case), ["修订理由：" + text(revision.rationale)], rows(revision.edits).map(function (edit) {
          edit = object(edit) || {};
          return {line: text(edit.line), old: text(edit.old), next: text(edit.new), basis: text(edit.basis)};
        }));
      });
      if (!rows(data.revisions).length) section("候选编辑", ["未记录修订；原始输出仍可查看。"]);
      section("观测点声明", rows(data.observation_points).length ? rows(data.observation_points).map(function (p) {
        p = object(p) || {};
        return "用例：" + text(p.case) + " · marker：" + text(p.marker) + "\n地址：" + text(p.addr) +
          " · 偏移：" + text(p.offset) + " · 期望值：" + text(p.expected_value) + "\n依据：" + text(p.basis);
      }) : ["未记录观测点声明；不据此推断已写入或仿真通过。"]);
      list("返工处理", data.rework_resolution);
      list("限制与不确定性", data.notes);
    } else if (node === "N8") {
      section("AI 建议：" + ({pass: "通过", rework: "返工"}[data.verdict] || text(data.verdict)), ["AI 建议不等于系统校验或人工放行。"]);
      section("检查项与依据", rows(data.findings).length ? rows(data.findings).map(function (f) {
        f = object(f) || {};
        return text(f.item) + " · " + text(f.result) + "\n依据：" + text(f.basis);
      }) : ["未记录检查项。"]);
      list("必须修复", data.must_fix);
    } else {
      section("当前成果", ["此角色的专用成果展示待扩展，请查看原始输出。"]);
    }
    return {title: role[0] + " · " + node, task: role[1], mode: mode, validation: label, sections: sections};
  }
  return {present: present, historical: historical};
})();
