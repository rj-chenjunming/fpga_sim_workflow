"""节点详情的人话展示投影（只读、非权威）。

规格依据：`doc/spec/SPEC-REV-02-20261023.md` R1 / §C.2（P-01～P-35）与
`doc/plans/2026-10-23-node-panel-unified-revision-plan.md` §1（S1 接口契约）；
`LOOP_ORCHESTRATION_SPEC.md` §10.4（`story`）；`WEB_UI_SPEC.md` §4.2.1 / §6.7。

边界（比 `node_view.py` 更窄）：

1. **不猜、不补默认值**：只陈述事件/`detail` 里已有的字段；缺字段一律"未下发"，
   不推算业务结论、不手算判据（`status` 原值才是权威，本模块只做展示释义）。
2. **不做业务判定**：不判绿、不判红；闸门三态、未到达/未执行都只是**状态投影**。
3. **不改写原始数据**：`story` 只是展示投影，`summary` / `detail` / `events` / `refs`
   原样保留；本函数不读盘、不写盘、不取墙钟，也不改动入参。
4. **确定性**：同一事件流 + 同一 detail + 同一 run 状态得到逐字节相同的 `story`。

契约要点（plan §1）：

- `headline` / `headline_source`（`template|summary|missing`）——逐节点一句话结果；
- `note`（首屏黄条，`warn|info`）——N2「N 条需要你确认，到 G1 逐条处置」、
  闸门等待态硬阻断白话（P-29）；
- `not_reached`（运行已终态且该节点无事件，P-30）与 `not_executed`
  （drill/演示下确实没执行，P-32/P-33）**必须区分**；
- `observation_points`（R3-03）——**仅 N6 下发该 key**，N6 观测点的确定性透传
  （数组；`null` = 未下发；其余节点没有该键，前端不渲染该块）；
- `evidence_groups` / `evidence_groups_note`（R3-06）——N7/N9 证据按用例分组
  （只从展示 `refs` 取件；`null` = 不分组，前端维持平铺 `refs`）；
- 关键字输入 `run_halted`（R3-10）只影响"未执行"归因文案，**不写进任何投影字段**；
- `evidence_note`（`agent_calls|not_executed|in_events|artifact`）——证据入口，
  避免"没有 refs"被误读成"证据缺失"（P-20/P-21/P-27/P-34/P-35）；
- `status_note` + `status_glossary`——状态的**释义**（原值仍由 `status` 原样下发，P-07）；
- `gate`——S3 的闸门块原样透传（本模块只读 `state`/`hard_block`/`decision`）。
"""

from __future__ import annotations

import re
from typing import Any, Callable, Sequence

# R3-15：闸门节点集合的**唯一来源**是 `services.node_registry`（本模块不再手抄第二份）。
# 保留模块级同名别名（`node_story.GATE_NODES`），`__all__` 不变，外部 import 不破裂。
from .node_registry import GATE_NODES

#: 逐节点「关键数字」：`(detail 里的点号路径, 中文标签)`。
#: 只挑"回答这一步结果如何"的字段（plan §1.2）；完整 detail 仍在「原始记录」里原样可见。
#: 同一标签出现多次时只展示一行（后一个真正下发的字段会替换先前的"未下发"占位行）。
RESULT_FIELDS: dict[str, tuple[tuple[str, str], ...]] = {
    "N0": (
        ("baseline", "基线"),
        ("mode", "运行模式"),
        ("fixture_files", "拷入预置文件"),
        ("gate_init_rc", "闸门初始化退出码"),
    ),
    # P-09：N1 只留两项（sha256 / doc 指纹 / commit / parent 收进「原始记录」）。
    "N1": (
        ("manifest.allfiles_entries", "快照文件数"),
        ("manifest.cases_frozen", "冻结用例数"),
    ),
    # N2 用内容维度（P-12），行由 `_n2_rows` 单独生成（见下）。
    "N2": (),
    # P-13：模型摘要 + 需要人工确认 + 分组数（"0 组"要解释成"没有段信息，无法分组"）。
    "N3": (
        ("provider", "模型提供方"),
        ("digest_confirmations", "需要人工确认"),
        ("groups_count", "分组数"),
    ),
    "N4": (
        ("gate", "闸门"),
        ("decision", "决策"),
        ("actor", "签署人"),
        ("human_signed", "人工已签署"),
    ),
    # P-19：首屏只留"必改 / 待查"（索引缺口/索引完整/gate1_rc 移原始记录）。
    # `to_check_case_count` = 去重用例数（用户要看的就是这个）；`to_check_count` = 条目数（仅在
    # 前者缺失时回退展示；两者都在时不展示条目数，避免"待查 178"这种被条目数放大的数字）。
    "N5": (
        ("must_change_count", "必改"),
        ("to_check_case_count", "待查"),
        ("to_check_count", "待查"),
    ),
    "N6": (
        ("cycle", "修订轮次"),
        ("targets", "目标用例数"),
        ("validation_ok", "输出校验通过"),
        ("mode", "运行模式"),
        ("case_edits", "逐用例修改"),
        # R3-03：观测点条数（逐条内容在 `story.observation_points`，由前端渲染列表）。
        ("observation_points", "观测点"),
    ),
    "N6_apply": (
        ("cases", "写入用例数"),
        ("edits", "施加修改数"),
        ("status", "落盘状态"),
        ("case_edits", "逐用例修改"),
    ),
    # P-22：编译用例（列出名字）+ 失败用例（去掉重复的"全部通过"）。
    "N7": (
        ("case_count", "编译用例"),
        ("failed_cases", "失败用例"),
    ),
    # P-23：检查项 / 必须修改 / 返工轮次（带上限）。
    "N8": (
        ("check_count", "检查项"),
        ("must_fix_count", "必须修改"),
        ("cycle", "返工轮次"),
    ),
    # P-24：口径一/口径二白话标签 + 证据身份一致。
    "N9": (
        ("cases", "用例数"),
        ("koutou1", "日志错误标记行数"),
        ("koutou2.UVM_ERROR", "UVM 报告 UVM_ERROR"),
        ("koutou2.UVM_FATAL", "UVM 报告 UVM_FATAL"),
        ("identity.consistent", "证据身份一致"),
    ),
    "N9_submit": (
        ("job_id", "作业号"),
        ("cases", "覆盖用例数"),
    ),
    # P-26：整轮判定 / 待裁决 / 失败点位。
    "N10": (
        ("verdict_passed", "整轮判定"),
        ("pending", "待裁决项"),
        ("classification.buckets", "失败点位"),
    ),
    # P-27：证据链 / 身份一致 / 用例数 / 返工请求 / 未闭环项。
    "N11": (
        ("chain", "证据链"),
        ("identity.consistent", "身份一致"),
        ("identity_table", "用例数"),
        ("cases", "用例数"),
        ("rework_requests_count", "返工请求"),
        ("unclosed", "未闭环项"),
    ),
    # P-28：报告结论 / 引用证据数 / 可解析引用。
    "N12": (
        ("claimed_verdict", "报告结论"),
        ("ref_count", "引用证据数"),
        ("refs_parseable_count", "可解析引用"),
    ),
    "N13": (
        ("gate", "闸门"),
        ("decision", "决策"),
        ("actor", "签署人"),
        ("human_signed", "人工已签署"),
    ),
    "N14": (
        ("gate", "闸门"),
        ("decision", "决策"),
        ("actor", "签署人"),
        ("human_signed", "人工已签署"),
    ),
    # P-31：选中用例（列出名字）/ G3 决策（中文）/ 本次是否真跑。
    "N15_select": (
        ("count", "选中用例"),
        ("g3", "G3 决策"),
        ("will_really_run", "本次是否真跑"),
    ),
    # P-32：回归用例（名字）/ 本次是否真跑 / 通过数（未执行 ⇒ —（未执行））。
    "N15": (
        ("cases", "回归用例"),
        ("count", "用例数"),
        ("will_really_run", "本次是否真跑"),
        ("passed", "通过数"),
        ("failed_cases", "失败用例"),
    ),
    "N15_submit": (
        ("job_id", "作业号"),
        ("cases", "覆盖用例数"),
    ),
    # P-34：晋升结果（拒绝/成功）/ 本次是否真写 / 触发人。
    "N16": (
        ("status", "晋升结果"),
        ("dry_run", "本次是否真写"),
        ("actor", "触发人"),
    ),
    # P-35：终止原因。
    "HALT": (
        ("reason", "终止原因"),
    ),
}

#: `GATE_NODES`（闸门节点集合）由 `services.node_registry` 单一提供，见文件头 import（R3-15）；
#: 本模块不再写第二份定义，但保留同名模块级别名，外部 `node_story.GATE_NODES` 引用不变。

#: 闸门节点 → (门序号, 门中文名)。面板用"闸门 1/2/3（差异确认/报告验收/回归决策）"，
#: 不用内部 id（`G1_diff_confirm` 只在原始记录里）。
GATE_DISPLAY: dict[str, tuple[int, str]] = {
    "N4": (1, "差异确认"),
    "N13": (2, "报告验收"),
    "N14": (3, "回归决策"),
}

#: 闸门已决策态的动作短语（§1.4.2：人已{确认差异清单|接受报告|决定回归策略}）。
GATE_ACTION: dict[str, str] = {
    "N4": "确认差异清单",
    "N13": "接受报告",
    "N14": "决定回归策略",
}

#: 闸门 id → 短名（P-35/P-16：正文只写"G1/G2/G3"，完整 id 留在原始记录）。
GATE_SHORT: dict[str, str] = {
    "G1_diff_confirm": "G1",
    "G2_report_accept": "G2",
    "G3_regression_decision": "G3",
}


def _gate_short(key: Any) -> str:
    return GATE_SHORT.get(str(key), str(key))

#: 决策值 → 中文展示名（P-15/P-30）。**原值必须保留**（raw 在 `status` / `value` / 括号里）。
DECISION_LABELS: dict[str, str] = {
    "confirmed": "已确认",
    "ignored": "忽略",
    "disputed": "有疑义",
    "accept": "接受",
    "rework": "返工",
    "full_now": "全量回归",
    "subset_only": "子集回归",
    "milestone_only": "仅里程碑",
    "defer": "暂缓",
}

#: `verdict` / `claimed_verdict` 的中文展示名（原值仍进 `value`）。
VERDICT_LABELS: dict[str, str] = {
    "pass": "通过",
    "passed": "通过",
    "fail": "未通过",
    "failed": "未通过",
    "rework": "返工",
    "escalated": "升级人工裁决",
    "intact": "完整",
    "broken": "不完整",
    "not_passed": "未通过",
    "undetermined": "未定",
    "refused": "晋升被拒",
    "ok": "成功",
    "applied": "已写入",
    "drill_fixture": "drill 夹具沙箱件",
    "drill_noop": "drill 未执行",
}

#: P-07：状态**释义**（服务端下发，前端只加在状态原值后面；原值逐字保留、不归一）。
STATUS_GLOSSARY: dict[str, str] = {
    "ok": "通过",
    "fail": "未通过",
    "failed": "失败",
    # R3-08：运行终态的中文释义（`not_reached` headline 的 gloss 也从这里取，不另抄一份）。
    "finished": "已完成",
    "live": "真实模型调用",
    "standin": "替身（非模型结论）",
    "intact": "完整",
    "broken": "不完整",
    "confirmed": "已确认",
    "ignored": "忽略",
    "disputed": "有疑义",
    "accept": "接受",
    "rework": "返工",
    "refused": "晋升被拒",
    "halted": "已终止",
    "applied": "已写入",
    "pass": "通过",
    "waiting": "等待中",
}

#: `run_status` 的终态（P-30：运行已终态且节点无事件 ⇒ `not_reached`）。
TERMINAL_RUN_STATUSES: frozenset[str] = frozenset({"finished", "failed"})

#: 模型节点（P-20/P-23/P-26/P-27/P-28）：证据入口指向 Agent 调用记录，而不是"证据缺失"。
MODEL_NODES: frozenset[str] = frozenset({"N3", "N6", "N8", "N10", "N11", "N12"})

#: drill/演示模式下**确实不执行**、且因此没有事件的节点（P-33：drill 不提交作业）。
#: 只是展示层的"未执行"判定，不改拓扑、不伪造步骤。
DRILL_SKIPPED_NODES: frozenset[str] = frozenset({"N15_submit"})

#: 带"执行/未执行"语义的节点（P-32）：`executed` / `will_really_run` / `simulated` 只对它们生效。
EXECUTION_NODES: frozenset[str] = frozenset({"N15"})

#: 证据可按**用例名**分组的节点（R3-06）：N9 取 `cases_detail[].case`，N7 取 `cases` 名单。
#: 其余节点不给分组（`evidence_groups=null`），前端维持现状平铺 `refs`。
EVIDENCE_GROUP_NODES: frozenset[str] = frozenset({"N7", "N9"})

#: 组内一条证据件都没有时的说明（R3-06）：N9 用例本轮没执行；N7 本轮没有该用例的证据文件。
#: 不得留空白，也不得说"缺失"（那会被误读成证据丢了）。
EVIDENCE_GROUP_EMPTY_NOTE: dict[str, str] = {
    "N9": "本轮未执行/无证据",
    "N7": "本轮没有这个用例的证据文件",
}

_MISSING_TEXT = "未下发"

#: R3-03：观测点未下发的展示文案（`null` = 模型没产出，不是"0 条"）。
_OBSERVATION_POINTS_MISSING = "未下发（旧 run 或替身，模型未产出观测点）"

#: 失败节点全文不得出现"完成"（R1 硬规则）。这里集中给出失败态文案。
_FAILURE_PREFIX = "失败："
_FAILURE_NO_REASON = "原因未下发（原始记录里没有 error/message 字段）"


# ---------------------------------------------------------------- 取值/格式化


def _pick(detail: dict[str, Any], dotted: str) -> tuple[bool, Any]:
    """返回 `(键是否已下发, 值)`；显式 `null` 也算已下发（与 node_view 口径一致）。"""
    cur: Any = detail
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def _str(detail: dict[str, Any], dotted: str) -> str | None:
    present, value = _pick(detail, dotted)
    if not present or not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _int(detail: dict[str, Any], dotted: str) -> int | None:
    present, value = _pick(detail, dotted)
    if not present or isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _bool(detail: dict[str, Any], dotted: str) -> bool | None:
    present, value = _pick(detail, dotted)
    if not present or not isinstance(value, bool):
        return None
    return value


def _list(detail: dict[str, Any], dotted: str) -> list[Any] | None:
    present, value = _pick(detail, dotted)
    if not present or not isinstance(value, list):
        return None
    return value


def _fmt(value: Any) -> str:
    """把 detail 值转成一眼能读的文本（不改数字、不做换算）。"""
    if value is None:
        return _MISSING_TEXT
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return value if value else "（空）"
    if isinstance(value, (list, tuple)):
        if not value:
            return "0 个"
        # 结构化条目（如 N2 的 offsets / cases_table）只报条数：逐项展开属于原始 detail 的职责。
        if any(isinstance(item, (dict, list, tuple)) for item in value):
            return f"{len(value)} 个"
        items = [_fmt_scalar(item) for item in value]
        if len(items) <= 6:
            return f"{len(items)} 个：{'、'.join(items)}"
        return f"{len(items)} 个：{'、'.join(items[:6])} …"
    if isinstance(value, dict):
        if not value:
            return "（空）"
        pairs = [f"{key}={_fmt_scalar(value[key])}" for key in list(value)[:8]]
        return " · ".join(pairs) + (" …" if len(value) > 8 else "")
    return str(value)


def _fmt_scalar(value: Any) -> str:
    if value is None:
        return "未下发"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    try:
        return _fmt(value)
    except Exception:  # pragma: no cover - 防御性，不静默改写值
        return str(value)


def _first_int(text: Any) -> int | None:
    """取一段**服务端已给出**的说明文本里的第一个整数（只用于硬阻断白话的数字）。"""
    match = re.search(r"\d+", str(text or ""))
    return int(match.group()) if match else None


def _basename(entry_id: str) -> str:
    return str(entry_id).rsplit("/", 1)[-1]


def _observation_points(node: str, detail: dict[str, Any]) -> list[Any] | None:
    """R3-03：N6 观测点的**确定性透传**（数组，或 `None` = 未下发）。

    - 键存在且是数组 ⇒ 逐条原样透传（`[]` = 下发了但 0 条，不冒充未下发）；
    - 键缺失 / 显式 `null` / 不是数组 / 非 N6 节点 ⇒ `None`（未下发）。

    只做形状校验与浅拷贝：不改字段名、不补默认值、不推断任何结论。
    """
    if node != "N6":
        return None
    present, value = _pick(detail, "observation_points")
    if not present or not isinstance(value, list):
        return None
    return [dict(item) if isinstance(item, dict) else item for item in value]


def _event_refs(events: Sequence[dict[str, Any]]) -> list[str]:
    """合并事件**顶层** `refs`（去重、保持首次出现顺序；与 `node_view._refs` 同口径）。"""
    out: list[str] = []
    for event in events:
        for ref in event.get("refs") or []:
            text = str(ref)
            if text and text not in out:
                out.append(text)
    return out


def _display_refs(events: Sequence[dict[str, Any]],
                  refs: Sequence[str] | None) -> list[str]:
    """分组用的 refs：调用方给了展示 refs 就**只用它**（已按 run 目录过滤，SPEC-04 §6.7）；
    没给则退回事件顶层 refs 的合并（同 `node_view._refs` 口径）。两者都去重保序。"""
    if refs is None:
        return _event_refs(events)
    out: list[str] = []
    for ref in refs:
        text = str(ref)
        if text and text not in out:
            out.append(text)
    return out


def _group_case_names(node: str, detail: dict[str, Any]) -> list[str]:
    """R3-06：分组用的用例名（只取服务端已下发的 `detail`，取不到就返回空，不编名字）。

    - N9：`detail.cases_detail[].case`（旧 run 没有该字段 ⇒ 空）；
    - N7：`detail.cases`（名字列表；drill 的 `cases` 是对象列表 ⇒ 取其中的 `case`）。
    名字去重且保持下发顺序。
    """
    names: list[str] = []

    def _add(value: Any) -> None:
        if isinstance(value, str) and value.strip() and value.strip() not in names:
            names.append(value.strip())

    if node == "N9":
        rows = detail.get("cases_detail")
        for row in (rows if isinstance(rows, list) else []):
            if isinstance(row, dict):
                _add(row.get("case"))
        return names
    cases = detail.get("cases")
    for item in (cases if isinstance(cases, list) else []):
        _add(item.get("case") if isinstance(item, dict) else item)
    return names


def _evidence_groups(
    node: str, detail: dict[str, Any], events: Sequence[dict[str, Any]],
    refs: Sequence[str] | None = None,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    """R3-06：把证据件按**用例名**分组（只读投影；不读盘、不推断、不补名字）。

    契约（impl plan §1.2）：

    - 只有 N7/N9 参与分组；其余节点 `(None, None)`（前端维持平铺 `refs`）；
    - 用例名不可知，或**一条 ref 都归不到**任何用例 ⇒ `([], 原因说明)`（不编组）；
    - 组内 `refs` 为空 ⇒ 该组 `note` 说明"本轮没有这个用例的证据"（N9/N7 各一句），不留空；
    - `refs` = 该节点事件 `refs` 里 basename 含用例名的件，保持服务端下发顺序；
    - 调用方传入 `refs`（已按 run 目录过滤的展示 refs）时**只从中取**，与面板平铺 refs 同口径
      （SPEC-04 §6.7：组内不得出现面板不展示的目录外路径）。
    """
    if node not in EVIDENCE_GROUP_NODES:
        return None, None
    candidates = _display_refs(events, refs)
    names = _group_case_names(node, detail)
    if not names:
        if candidates:
            return [], "服务端没有列出用例名，无法按用例分组（证据按下发顺序平铺，不编组）。"
        return [], "本轮没有证据文件（服务端未列出用例，也没有可展示的证据件）"
    groups: list[dict[str, Any]] = []
    attributed = 0
    for name in names:
        matched = [ref for ref in candidates if name in _basename(ref)]
        if matched:
            attributed += 1
        groups.append({
            "case": name,
            "refs": matched,
            "note": None if matched else EVIDENCE_GROUP_EMPTY_NOTE[node],
        })
    if not attributed:
        return [], f"本轮没有证据文件（列出的 {len(names)} 个用例都没有可归属的证据件）"
    return groups, None


def _lines_text(lines: Any) -> str | None:
    """行号列表 →「第 171–172 行」；空列表 ⇒ None（不编行号）。"""
    values: list[int] = []
    for item in lines or []:
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            values.append(int(item))
        elif isinstance(item, str) and item.strip().isdigit():
            values.append(int(item.strip()))
    if not values:
        return None
    if len(values) == 1:
        return f"第 {values[0]} 行"
    return f"第 {min(values)}–{max(values)} 行"


def _cycle_text(cycle: int | None, *, plus: int = 0) -> str:
    """返工轮次展示（P-23：通过时用"第 {cycle+1} 次复核"，返工时用已消耗轮次）。"""
    if cycle is None:
        return _MISSING_TEXT
    return str(cycle + plus)


def _decision_text(value: Any) -> str:
    """决策值展示：`已确认（confirmed）`（中文只是展示名，原值必须保留）。"""
    if value is None or value == "":
        return _MISSING_TEXT
    raw = str(value)
    label = DECISION_LABELS.get(raw)
    return f"{label}（{raw}）" if label else raw


def _verdict_text(value: Any) -> str:
    if value is None or value == "":
        return _MISSING_TEXT
    raw = str(value)
    label = VERDICT_LABELS.get(raw)
    return f"{label}（{raw}）" if label else raw


def _row(field: str, label: str, value: Any, text: str, missing: bool = False) -> dict[str, Any]:
    return {"field": field, "label": label, "value": value, "text": text, "missing": missing}


# ---------------------------------------------------------------- N2 内容维度（P-10/P-11/P-12）


def group_diff_entries(diffs: Sequence[Any]) -> list[dict[str, Any]]:
    """按 `entry_id`（缺省 `id`）归并同一文件的多路证据（P-11 同一口径）。

    - 主条目 = 该 id 下第一条**有 `diff_hunk`** 的条目，否则取第一条；
    - 其余同 id 条目是**附证据**（整文件 md5 一类），不重复计数（P-18 方案 b 的展示口径）；
    - 同一组内任一 `unresolved` 非空 ⇒ 该组算"需要人工确认"1 条。

    这是 S1 对 N2 结果/关键数字的唯一计数口径（S3 的闸门清单同口径，见 plan §1.3）。
    """
    order: list[str] = []
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in diffs or []:
        if not isinstance(item, dict):
            continue
        entry_id = item.get("entry_id") or item.get("id")
        if entry_id in (None, ""):
            continue
        key = str(entry_id)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(item)

    out: list[dict[str, Any]] = []
    for key in order:
        items = groups[key]
        hunked = [
            item for item in items
            if isinstance(item.get("diff_hunk"), str) and item["diff_hunk"].strip()
        ]
        main = hunked[0] if hunked else items[0]
        unresolved = [item for item in items if item.get("unresolved")]
        offsets = main.get("offsets") if isinstance(main.get("offsets"), list) else []
        out.append({
            "entry_id": key,
            "main": main,
            "attached": [item for item in items if item is not main],
            "has_hunk": bool(hunked),
            "unresolved": bool(unresolved),
            "unresolved_reason": (unresolved[0].get("unresolved") if unresolved else None),
            "change": main.get("change"),
            "lines": list(main.get("lines") or []),
            # 真实 N2 用 `offsets`（复数）列表、drill 夹具用 `offset`（单数）：只做兼容读取。
            "offset": main.get("offset") or (offsets[0] if offsets else None),
            "has_change_field": any("change" in item for item in items),
        })
    return out


def content_summary(detail: dict[str, Any]) -> dict[str, Any]:
    """N2 的内容维度计数（P-11/P-12）：文件数 / 行级证据处数 / 需要确认条数。

    口径：
    - `files` = 唯一 `entry_id` 数（同一文件的多路证据合并成一组，不重复计数）；
    - `hunks` = 主条目有 `diff_hunk` 的组数（"处"）；
    - `confirm` = 组内任一 `unresolved` 非空的组数（与 G1 `entry_decisions` 的键同口径）；
    - 旧 run 没有 `diffs` ⇒ 三者都未下发，`confirm` 回退 `unresolved_count`（逐路计数）。
    """
    diffs = detail.get("diffs")
    present = isinstance(diffs, list)
    groups = group_diff_entries(diffs if present else [])
    changes = {"new": 0, "deleted": 0, "modified": 0, "unknown": 0}
    for group in groups:
        change = str(group.get("change") or "").strip().lower()
        if change in ("added", "add", "new", "created", "create"):
            changes["new"] += 1
        elif change in ("deleted", "delete", "removed", "remove"):
            changes["deleted"] += 1
        elif change in ("modified", "modify", "changed", "update", "updated"):
            changes["modified"] += 1
        else:
            changes["unknown"] += 1
    return {
        "present": present,
        "has_change": detail.get("has_change"),
        "files": len(groups),
        "hunks": sum(1 for group in groups if group["has_hunk"]),
        "confirm": sum(1 for group in groups if group["unresolved"]),
        "changes": changes,
        "has_change_field": any(group["has_change_field"] for group in groups),
        "groups": groups,
        # 旧 run 的回退口径（逐路计数，与 G1 未决清单同源）
        "fallback_confirm": _int(detail, "unresolved_count"),
    }


def _n2_headline(detail: dict[str, Any]) -> tuple[str | None, str]:
    """N2 结果一句话（P-10/P-12）：以"文件内容有没有改"为主语，md5 不作主角。"""
    info = content_summary(detail)
    if not info["present"]:
        unresolved = info["fallback_confirm"]
        if unresolved is None:
            return "差异清单未下发（旧 run 的 detail 没有逐条清单）。", "missing"
        return (
            "差异清单未下发（旧 run 的 detail 没有逐条清单）；"
            f"按未决条目数，有 {unresolved} 条需要你确认，到 G1 逐条处置。",
            "missing",
        )
    groups = info["groups"]
    if not groups:
        if info["has_change"] is False:
            return "文件内容没有变化。", "template"
        return "逐条差异清单为空（没有比对出条目）。", "template"
    if info["has_change"] is False:
        return "文件内容没有变化。", "template"
    # 单文件 + 有行号 + 有偏移：一句话说清改在哪。
    if len(groups) == 1:
        group = groups[0]
        lines = _lines_text(group["lines"])
        offset = group["offset"]
        if lines and offset not in (None, ""):
            return (
                f"内容有变化：1 个文件改了（{_basename(group['entry_id'])}），"
                f"{lines}，偏移 {offset}。",
                "template",
            )
    names = [_basename(group["entry_id"]) for group in groups]
    shown = "、".join(names[:3]) + ("…" if len(names) > 3 else "")
    headline = (
        f"内容有变化：{info['files']} 个文件改了（{shown}）；"
        f"{info['hunks']} 处有行级证据，{info['confirm']} 条需要你确认"
    )
    # P-12 ②：多文件时也要能看出"改在哪" —— 只补 1 条（优先有 offset 的，其次有行号的），
    # 不把逐条清单铺进首屏（那属于 G1 材料 / 原始记录）。"其中"只保留这句定位。
    locator = _diff_locator(groups)
    if locator:
        headline += "；其中 " + locator
    return headline + "。", "template"


def _diff_locator(groups: Sequence[dict[str, Any]]) -> str | None:
    """挑 1 条最能说明"改在哪"的差异（优先有 offset，其次有行号），不编数字。"""
    chosen: dict[str, Any] | None = None
    for group in groups:
        if group.get("offset") not in (None, ""):
            chosen = group
            break
    if chosen is None:
        for group in groups:
            if group.get("lines"):
                chosen = group
                break
    if chosen is None:
        return None
    extras: list[str] = []
    lines = _lines_text(chosen.get("lines"))
    offset = chosen.get("offset")
    if lines:
        extras.append(lines)
    if offset not in (None, ""):
        extras.append(f"偏移 {offset}")
    if not extras:
        return None
    return f"{_basename(chosen['entry_id'])} " + "、".join(extras)


def _n2_rows(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """N2 关键数字：内容维度（P-12）；md5/路由计数/偏移列表都不进关键数字（P-02 保留）。"""
    info = content_summary(detail)
    rows: list[dict[str, Any]] = []
    if info["present"]:
        suffix = ""
        if info["has_change_field"] and info["files"]:
            suffix = (f"（新增 {info['changes']['new']}、删除 {info['changes']['deleted']}、"
                      f"修改 {info['changes']['modified']}）")
        rows.append(_row("n2.content.files", "改了文件数", info["files"],
                         f"{info['files']} 个{suffix}", False))
        rows.append(_row("n2.content.hunks", "有行级证据的改动", info["hunks"],
                         f"{info['hunks']} 处", False))
        rows.append(_row("n2.content.confirm", "需要你确认", info["confirm"],
                         f"{info['confirm']} 条", False))
    else:
        fallback = info["fallback_confirm"]
        rows.append(_row("n2.content.files", "改了文件数", None, _MISSING_TEXT, True))
        rows.append(_row("n2.content.hunks", "有行级证据的改动", None, _MISSING_TEXT, True))
        rows.append(_row(
            "n2.content.confirm", "需要你确认",
            fallback,
            (_MISSING_TEXT if fallback is None
             else f"{fallback} 条（按未决条目数，旧 run 无逐条清单）"),
            fallback is None,
        ))
    present, value = _pick(detail, "self_check_ok")
    if present:
        rows.append(_row("self_check_ok", "自检通过", value, _fmt(value), value is None))
    else:
        rows.append(_row("self_check_ok", "自检通过", None, _MISSING_TEXT, True))
    return rows


# ---------------------------------------------------------------- 关键数字


def _base_rows(node: str, detail: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    by_label: dict[str, dict[str, Any]] = {}
    for field, label in RESULT_FIELDS.get(node, ()):
        present, value = _pick(detail, field)
        missing = (not present) or value is None
        text = _fmt(value) if present else _MISSING_TEXT
        row = _row(field, label, value, text, missing)
        if label in by_label:
            existing = by_label[label]
            if existing["missing"] and not missing:
                # 用真正下发的字段替换先前"未下发"的占位行（保持原位置）
                index = out.index(existing)
                out[index] = row
                by_label[label] = row
            continue
        by_label[label] = row
        out.append(row)
    return out


def _n6_case_edits_text(items: Any) -> tuple[str, bool]:
    if not isinstance(items, list) or not items:
        return _MISSING_TEXT, True
    parts: list[str] = []
    for item in items[:3]:
        if not isinstance(item, dict):
            continue
        case = item.get("case") or "用例名未下发"
        count = item.get("edit_count")
        if not isinstance(count, int) or isinstance(count, bool):
            edits = item.get("edits")
            count = len(edits) if isinstance(edits, list) else None
        parts.append(f"{case}（{'未下发' if count is None else f'{count} 处'}）")
    if not parts:
        return _MISSING_TEXT, True
    return "、".join(parts) + ("…" if len(items) > 3 else ""), False


def _n7_case_text(row: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    cases = detail.get("cases")
    names: list[str] = []
    if isinstance(cases, list):
        for item in cases:
            if isinstance(item, dict):
                name = item.get("case")
                if name:
                    names.append(str(name))
            elif isinstance(item, str):
                names.append(item)
    if row["missing"] and names:
        return _row(row["field"], row["label"], len(names),
                    f"{len(names)} 个：{'、'.join(names[:6])}", False)
    if not row["missing"] and names:
        return _row(row["field"], row["label"], row["value"],
                    f"{_fmt(row['value'])}：{'、'.join(names[:6])}", False)
    return row


def _n10_buckets_text(detail: dict[str, Any], value: Any) -> tuple[str, bool]:
    if value is None:
        return _MISSING_TEXT, True
    if isinstance(value, bool):
        total = None
    elif isinstance(value, int):
        total = value  # S2 的 `classification.buckets` 是**桶数**（int）
    elif isinstance(value, (list, tuple, dict)):
        total = len(value)
    else:
        total = None
    text = f"{total} 个区间" if total is not None else _fmt(value)
    classification = detail.get("classification")
    if isinstance(classification, dict):
        parts = [f"{label} {classification[key]}"
                 for label, key in (("既有缺陷", "既有缺陷"), ("本轮引入", "本轮引入"),
                                    ("待裁决", "待裁决"))
                 if classification.get(key) is not None]
        if parts:
            text += "（" + "、".join(parts) + "）"
    return text, False


def _n15_will_really_run_text(detail: dict[str, Any], mode: str | None) -> tuple[Any, str, bool]:
    """「本次是否真跑」：以 detail 字段为准；旧 run 没有该字段时按运行模式如实说（不猜）。"""
    value = _bool(detail, "will_really_run")
    if value is True:
        return True, "是", False
    if value is False:
        text = "否（drill 演示模式不真跑）" if mode == "drill" else "否"
        return False, text, False
    if mode == "drill":
        return None, "否（drill 演示模式不真跑）", False
    if mode == "real":
        return None, "是（real 会真跑）", False
    return None, _MISSING_TEXT, True


def _customize_row(node: str, row: dict[str, Any], detail: dict[str, Any],
                   mode: str | None, status: Any) -> dict[str, Any]:
    field = row["field"]
    value = row["value"]
    missing = row["missing"]
    # N0 的预置文件数只对 drill 有意义；real 显示 0 会让人误以为"复制失败"。
    if node == "N0" and field == "fixture_files" and detail.get("mode") == "real":
        return _row(field, row["label"], value, "0（真实运行不复制预置文件）", False)
    if node in GATE_NODES and field == "decision":
        return _row(field, row["label"], value, _decision_text(value), not value)
    # P-13：0 组要解释成"没有段信息、无法分组——不是没分析"。
    if node == "N5" and field == "to_check_count":
        # 回退分支（没有 `to_check_case_count`）：对外仍用稳定字段名"待查"，
        # value 保留 detail 原值（原字段名在原始记录里可见）。
        return _row("to_check_case_count", row["label"], value, row["text"], missing)
    if node == "N3" and field == "groups_count":
        empty_segments = _bool(detail, "offered_segments_empty")
        if value is None:
            return row
        if missing:
            return _row(field, row["label"], value, _MISSING_TEXT, True)
        if empty_segments is True and value == 0:
            return _row(field, row["label"], value,
                        "0（没有段信息，无法分组——不是没分析）", False)
        return _row(field, row["label"], value, _fmt(value), False)
    if node == "N3" and field == "digest_confirmations":
        if missing:
            return row
        if isinstance(value, list):
            return _row(field, row["label"], value, f"{len(value)} 条", False)
        return row
    if node == "N7" and field == "case_count":
        return _n7_case_text(row, detail)
    if node == "N8" and field == "cycle":
        limit = _int(detail, "limit")
        if missing:
            return row
        limit_text = f"（上限 {limit}）" if limit is not None else "（上限未下发）"
        return _row(field, row["label"], value, f"{value}{limit_text}", False)
    if node == "N10" and field == "verdict_passed":
        if missing:
            return row
        if value is True:
            return _row(field, row["label"], value, "通过", False)
        if value is False:
            return _row(field, row["label"], value, "未通过", False)
        return row
    if node == "N10" and field == "classification.buckets":
        text, is_missing = _n10_buckets_text(detail, value)
        return _row(field, row["label"], value, text, is_missing)
    if node == "N11" and field == "chain":
        if missing:
            return row
        return _row(field, row["label"], value, _verdict_text(value), False)
    if node == "N11" and field == "identity.consistent":
        if not missing:
            return row
        # S2 的 N11 detail 用 `host_consistent`（Host 四方同值是否成立，同义）；兼容读取。
        fallback = _bool(detail, "host_consistent")
        if fallback is not None:
            return _row(field, row["label"], fallback, _fmt(fallback), False)
        return row
    if node == "N11" and field == "rework_requests_count":
        if not missing and isinstance(value, int) and not isinstance(value, bool):
            return _row(field, row["label"], value, f"{value} 条", False)
        if not missing:
            return row
        fallback = _int(detail, "rework")  # 旧 run 的同义计数（兼容读取，不新算）
        if fallback is not None:
            return _row(field, row["label"], fallback, f"{fallback} 条", False)
        return row
    if node == "N11" and field == "unclosed":
        if missing:
            return row
        if isinstance(value, list):
            return _row(field, row["label"], value, f"{len(value)} 条", False)
        return row
    if node == "N12" and field == "claimed_verdict":
        if missing:
            return row
        return _row(field, row["label"], value, _verdict_text(value), False)
    if node == "N15_select" and field == "count":
        if missing:
            return row
        cases = _list(detail, "cases")
        names = [str(name) for name in (cases or []) if name]
        text = f"{_fmt(value)}" if not names else f"{_fmt(value)}：{'、'.join(names[:6])}"
        return _row(field, row["label"], value, text, False)
    if node == "N15_select" and field == "g3":
        if missing:
            return row
        label = DECISION_LABELS.get(str(value))
        return _row(field, row["label"], value, f"{label}（{value}）" if label else str(value), False)
    if node in ("N15_select", "N15") and field == "will_really_run":
        raw, text, is_missing = _n15_will_really_run_text(detail, mode)
        return _row(field, row["label"], raw, text, is_missing)
    if node == "N15" and field in ("passed", "failed_cases"):
        executed = not _not_executed(node, detail, (), mode, None)
        if not executed:
            # P-32：没执行就是"未执行"，不写"未下发"。
            return _row(field, row["label"], value, "—（未执行）", False)
        if field == "failed_cases":
            if isinstance(value, list):
                names = [str(name) for name in value if name]
                text = f"{len(names)} 个" + (f"：{'、'.join(names[:6])}" if names else "")
                return _row(field, row["label"], value, text, False)
            return row
        if missing:
            return row
        if isinstance(value, bool):
            # 新 run 的 detail 里 `passed` 是**整轮判定**（bool），逐例通过数不在这里。
            return _row(field, row["label"], value,
                        "是（整轮判定）" if value else "否（整轮判定）", False)
        return row
    if node == "N6_apply" and field == "status":
        if missing:
            return row
        return _row(field, row["label"], value, _verdict_text(value), False)
    if node == "N16" and field == "status":
        raw = detail.get("status", status)
        if raw in (None, ""):
            return _row(field, row["label"], None, _MISSING_TEXT, True)
        return _row(field, row["label"], raw, _verdict_text(raw), False)
    if node == "N16" and field == "dry_run":
        if missing:
            return row
        if value is True:
            return _row(field, row["label"], value, "否（dry-run 试运行，不真正落盘）", False)
        if value is False:
            return _row(field, row["label"], value, "是（会真正写入）", False)
        return row
    if node in ("N6", "N6_apply") and field == "case_edits":
        text, is_missing = _n6_case_edits_text(value)
        return _row(field, row["label"], value, text, is_missing)
    if node == "N6" and field == "observation_points":
        # R3-03：`value` 只给条数或"未下发"（逐条内容在 `story.observation_points` 里）。
        points = _observation_points(node, detail)
        if points is None:
            return _row(field, row["label"], _MISSING_TEXT, _OBSERVATION_POINTS_MISSING, True)
        return _row(field, row["label"], len(points), f"{len(points)} 条（逐条见下）", False)
    return row


def _counts_int(counts: dict[str, Any], key: str) -> int | None:
    value = counts.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _gate_count_row(counts: dict[str, Any], key: str, label: str,
                    text_override: str | None = None) -> dict[str, Any]:
    field = f"gate.counts.{key}"
    value = _counts_int(counts, key)
    if value is None:
        return _row(field, label, None, _MISSING_TEXT, True)
    return _row(field, label, value, text_override if text_override is not None else str(value), False)


def _gate_count_rows(node: str, gate: dict[str, Any] | None) -> list[dict[str, Any]]:
    """P-29 ②：闸门首屏的关键数字（全部来自 S3 的 `gate.counts`；缺就不补 0）。

    - N13/N14：硬阻断 / 待验用例 / 未清冲突（有总数时显示 `{open}/{total}`）；
    - N4：修订点 / 已处置 / 需要你确认。
    """
    counts = gate.get("counts") if isinstance(gate, dict) else None
    counts = counts if isinstance(counts, dict) else {}
    if node == "N4":
        return [
            _gate_count_row(counts, "revision_points", "修订点"),
            _gate_count_row(counts, "disposed", "已处置"),
            _gate_count_row(counts, "unresolved_points", "需要你确认"),
        ]
    if node in ("N13", "N14"):
        open_conflicts = _counts_int(counts, "conflicts_open")
        total_conflicts = _counts_int(counts, "conflicts_total")
        conflicts_text = (f"{open_conflicts}/{total_conflicts}"
                          if open_conflicts is not None and total_conflicts is not None else None)
        return [
            _gate_count_row(counts, "hard_block", "硬阻断"),
            _gate_count_row(counts, "pending_cases", "待验用例"),
            _gate_count_row(counts, "conflicts_open", "未清冲突", conflicts_text),
        ]
    return []


def _with_gate_rows(node: str, rows: list[dict[str, Any]], detail: dict[str, Any],
                    gate: dict[str, Any] | None) -> list[dict[str, Any]]:
    """闸门节点 = 通用行（已决策态）+ P-29 数字行；等待态 detail 为空时只留数字行。"""
    counts = gate.get("counts") if isinstance(gate, dict) else None
    if not isinstance(counts, dict) or not counts:
        return rows
    if not detail:
        # 还没收尾：不逐项堆 gate/decision/actor/human_signed 的"未下发"，只给材料里的数字。
        rows = []
    return rows + _gate_count_rows(node, gate)


def key_results(node: str, detail: dict[str, Any], *, mode: str | None = None,
                status: Any = None, gate: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """逐节点关键数字（plan §1.2）；缺失项 `missing=true` + "未下发"，不补默认值。

    `value` 永远是 detail 原值（或事件 status 原值 / `gate.counts` 原值）；中文/白话只改 `text`。
    `gate` 只用于闸门节点的 P-29 数字行（S3 的闸门块）。
    """
    detail = detail if isinstance(detail, dict) else {}
    if node == "N2":
        return _n2_rows(detail)
    rows = _base_rows(node, detail)
    rows = [_customize_row(node, row, detail, mode, status) for row in rows]
    if node in GATE_NODES:
        rows = _with_gate_rows(node, rows, detail, gate)
    return rows


# ---------------------------------------------------------------- 状态/提示


def _resolve_mode(detail: dict[str, Any], mode: str | None) -> str | None:
    node_mode = _str(detail, "mode")
    if node_mode:
        return node_mode
    return mode if isinstance(mode, str) and mode else None


def _terminal_status(events: Sequence[dict[str, Any]]) -> Any:
    for event in reversed(events):
        if event.get("kind") in ("node_finished", "node_failed"):
            return event.get("status")
    return events[-1].get("status") if events else None


def _node_failed(events: Sequence[dict[str, Any]]) -> bool:
    return any(event.get("kind") == "node_failed" for event in events)


def _not_executed(node: str, detail: dict[str, Any], events: Sequence[dict[str, Any]],
                  mode: str | None, run_status: str | None) -> bool:
    """P-32/P-33：drill/演示下**确实没执行**（与"未下发"/"未到达"区分）。

    只在有**明确证据**时判定：
    - 执行类节点的 detail 明确写 `executed=false` / `will_really_run=false` / `simulated=true`；
    - drill 运行已终态、且该节点在演示模式下**不产生事件**（`N15_submit` 不提交作业）。
    """
    if node in EXECUTION_NODES:
        if detail.get("executed") is False:
            return True
        if detail.get("will_really_run") is False:
            return True
        if detail.get("simulated") is True:
            return True
    if (mode == "drill" and node in DRILL_SKIPPED_NODES and not events
            and run_status in TERMINAL_RUN_STATUSES):
        return True
    return False


def _status_note(status: Any) -> str | None:
    if status in (None, ""):
        return None
    return STATUS_GLOSSARY.get(str(status))


def _hard_block_line(item: dict[str, Any]) -> str:
    """P-29：硬阻断一条 → 一句白话（代号只作小字附注，正文不能只写代号）。"""
    code = str(item.get("code") or "").strip()
    title = str(item.get("title") or "").strip()
    count = _first_int(title)
    if code == "I2_CASES_PENDING":
        body = (f"有 {count} 个用例改完没在全跑里验证通过"
                if count is not None else "有用例改完没在全跑里验证通过")
    elif code == "I3_KOUTOU1_NONZERO":
        body = (f"日志错误标记 {count} 行 ≠ 0（两套口径都要为 0 才算通过）"
                if count is not None else "日志错误标记不为 0（两套口径都要为 0 才算通过）")
    elif code == "I4_CONFLICTS_UNCLEARED":
        body = (f"{count} 条文档/RTL 冲突未清零（未清零不能发版）"
                if count is not None else "还有文档/RTL 冲突没清零（未清零不能发版）")
    elif code == "I1_UNRESOLVED_ENTRIES":
        body = (f"{count} 条差异还没逐条处置" if count is not None else "还有差异没逐条处置")
    elif code == "I3_KOUTOU2_NONZERO":
        body = "UVM 报告里的 UVM_ERROR / UVM_FATAL 不为 0"
    elif code == "I3_EVIDENCE_MISSING":
        body = "没有全跑日志，两套口径都取不到数"
    elif code == "I4_CONFLICTS_MISSING":
        body = "找不到冲突清单，按未清零处理"
    elif code == "I7_REWORK_LIMIT":
        body = (f"返工次数已达/超过上限（{count}）⇒ 必须人工裁决"
                if count is not None else "返工次数已达/超过上限 ⇒ 必须人工裁决")
    else:
        body = title or "服务端未下发这条阻断的说明"
    return f"{code}：{body}" if code else body


def _gate_wait_seconds(events: Sequence[dict[str, Any]]) -> float | None:
    """等人签署的时长 = 本节点 `gate_pending.ts → gate_decided.ts`。

    只有两个事件都在、且时间可比较（数值、非负）时才返回；否则 `None`（不猜）。
    """
    pending_ts: float | None = None
    decided_ts: float | None = None
    for event in events:
        ts = event.get("ts")
        if isinstance(ts, bool) or not isinstance(ts, (int, float)):
            continue
        if event.get("kind") == "gate_pending" and pending_ts is None:
            pending_ts = float(ts)
        elif event.get("kind") == "gate_decided":
            decided_ts = float(ts)  # 取最近一次决策（历史决策以最后一次为准）
    if pending_ts is None or decided_ts is None:
        return None
    delta = decided_ts - pending_ts
    return delta if delta >= 0 else None


def _humanize_wait(seconds: float) -> str:
    """秒 →「X 小时 Y 分」/「Y 分」/「X 秒」（只做单位换算，不改原始时间）。"""
    total = int(round(seconds))
    if total < 60:
        return f"{total} 秒"
    if total < 3600:
        return f"{total // 60} 分"
    hours, remainder = divmod(total, 3600)
    return f"{hours} 小时 {remainder // 60} 分"


def _gate_state(gate: dict[str, Any] | None) -> str | None:
    if not isinstance(gate, dict):
        return None
    state = gate.get("state")
    return state if isinstance(state, str) and state else None


def _gate_decision(gate: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(gate, dict):
        return {}
    decision = gate.get("decision")
    return decision if isinstance(decision, dict) else {}


def _note(node: str, detail: dict[str, Any], gate: dict[str, Any] | None) -> dict[str, str] | None:
    """首屏黄条（plan §1：只写一句 / 硬阻断白话）。"""
    if node == "N2":
        info = content_summary(detail)
        if info["present"]:
            count = info["confirm"]
            if count <= 0:
                return None
            return {"text": f"{count} 条需要你确认，到 G1 逐条处置", "level": "warn"}
        fallback = info["fallback_confirm"]
        if fallback is None or fallback <= 0:
            return None
        return {
            "text": (f"{fallback} 条需要你确认（按未决条目数，旧 run 无逐条清单），"
                     "到 G1 逐条处置"),
            "level": "warn",
        }
    if node in GATE_NODES and _gate_state(gate) == "waiting":
        blocks = gate.get("hard_block") if isinstance(gate, dict) else None
        lines = [_hard_block_line(item) for item in (blocks or []) if isinstance(item, dict)]
        if not lines:
            return None
        return {"text": "；".join(lines) + "。", "level": "warn"}
    return None


def _evidence_note(node: str, detail: dict[str, Any], gate: dict[str, Any] | None,
                   failed: bool, not_executed: bool, *,
                   not_reached: bool = False, has_events: bool = True,
                   wait_seconds: float | None = None,
                   run_halted: bool = False) -> dict[str, str] | None:
    """证据入口（P-20/P-21/P-27/P-34/P-35）：说清证据在哪，别把"没有 refs"当"证据缺失"。"""
    if not_reached:
        # 本轮没走到这个节点 ⇒ 没有任何证据可指，也不说"等它跑完"。
        return None
    if not_executed:
        if node == "N15":
            return {"text": "本轮未执行回归：没有作业、没有日志，也没有证据文件（演示模式）。",
                    "kind": "not_executed"}
        if node in DRILL_SKIPPED_NODES and run_halted:
            # R3-10：运行已提前终止（halt）⇒ 归因是"没有提交记录"，不是"演示模式不提交"。
            return {"text": "本轮未执行这个节点：没有提交记录，因此没有证据文件。",
                    "kind": "not_executed"}
        return {"text": "本轮未执行这个节点：演示模式不提交作业，因此没有证据文件。",
                "kind": "not_executed"}
    if not has_events and _gate_state(gate) not in ("waiting", "decided"):
        # 节点还没有任何事件（没有开始/收尾）⇒ 不承诺"记录在 Agent 工作窗口/事件里"。
        return None
    if failed:
        return None
    source = _str(detail, "source")
    if node in MODEL_NODES:
        if source == "model_standin":
            return {"text": ("这次是替身（standin），没有真实模型调用；"
                             "调用留痕与输入/输出在 Agent 工作窗口（本面板不展开）。"),
                    "kind": "agent_calls"}
        return {"text": "模型调用记录在 Agent 工作窗口（本面板不展开模型输入/输出）。",
                "kind": "agent_calls"}
    if node in GATE_NODES:
        if _gate_state(gate) == "decided":
            decision = _gate_decision(gate)
            signed_at = decision.get("signed_at")
            # P-15：闸门节点的"用时"其实是**等人签署**的时长（不写"用时"）。
            extras: list[str] = []
            if wait_seconds is not None:
                extras.append(f"等待人签署 {_humanize_wait(wait_seconds)}")
            if isinstance(signed_at, str) and signed_at:
                extras.append(f"签署时间 {signed_at}")
            if extras:
                return {"text": "签署记录在 gates.json（" + "；".join(extras) + "）。",
                        "kind": "in_events"}
            return {"text": "签署记录在 gates.json（本面板不读文件正文）。", "kind": "in_events"}
        return {"text": "待决策材料在闸门视图；签署记录会写进 gates.json。", "kind": "in_events"}
    if node == "N15_select":
        # P-31 ④：选集没有独立文件 ⇒ 说明"记在事件里"，不误报"证据缺失"。
        return {"text": "选择结果记在事件里（本轮没有独立的选集文件）。",
                "kind": "in_events"}
    if node == "HALT":
        return {"text": "终止原因与各闸门决策记录在事件里（本面板不读产物文件）。",
                "kind": "in_events"}
    if node == "N16":
        return {"text": ("晋升结果件：n16_result.json / promote_result.json"
                         "（存在即列在证据里；本面板不读正文）。"),
                "kind": "artifact"}
    return None


# ---------------------------------------------------------------- headline（plan §1.1/§1.3/§1.4）


def _headline_gate(node: str, detail: dict[str, Any], gate: dict[str, Any] | None,
                   status: Any) -> tuple[str, str] | None:
    number, gate_name = GATE_DISPLAY.get(node, (None, None))
    state = _gate_state(gate)
    if state == "waiting":
        text = f"等待你处理：本轮停在闸门 {number}（{gate_name}）"
        blocks = gate.get("hard_block") if isinstance(gate, dict) else None
        if node == "N13" and blocks:
            text += "，现在不能接受"
        return text + "。", "template"
    if state == "decided":
        decision = _gate_decision(gate)
        raw = decision.get("decision")
        actor = decision.get("actor")
        reason = decision.get("reason")
        if raw in (None, ""):
            # 块说"已决策"但没有决策值 ⇒ 只用 detail 的整门决策，不编。
            return _detail_decision_headline(node, detail, status)
        label = DECISION_LABELS.get(str(raw))
        # 理由：gate 块来自权威记录；缺失才是"未填写（原记录无理由）"。
        if isinstance(reason, str) and reason.strip():
            reason_text = reason.strip()
        else:
            reason_text = "未填写（原记录无理由）"
        text = (f"人已{GATE_ACTION.get(node, '做决定')}（{raw}"
                f"{' ' + label if label else ''}），签署人 {actor or _MISSING_TEXT}，"
                f"理由：{reason_text}")
        if str(raw) == "milestone_only":
            text += "（按受影响子集跑回归后晋升，不要求冲突清零）"
        elif str(raw) == "defer":
            text += "（本轮显式终止）"
        return text + "。", "template"
    if state == "no_material":
        # 清单材料缺失，但节点 detail 里已有整门决策 ⇒ 先说决策（比"材料未下发"更贴近事实）。
        decided = _detail_decision_headline(node, detail, status)
        if decided is not None:
            return decided
        note = gate.get("note") if isinstance(gate, dict) else None
        if isinstance(note, str) and note.strip():
            return f"闸门材料未下发：{note.strip().rstrip('。')}。", "missing"
        return "闸门材料未下发（服务端没有给出这个闸门的清单材料）。", "missing"
    # gate 块缺失（S3 未注入 / 旧 run）：只按 detail 的整门决策说话，不编理由。
    return _detail_decision_headline(node, detail, status)


def _detail_decision_headline(node: str, detail: dict[str, Any],
                              status: Any) -> tuple[str, str] | None:
    """没有 gate 块时，只按 detail 的整门决策说话（不编理由、不编材料）。"""
    decision_raw = _str(detail, "decision") or (
        str(status) if status not in (None, "") and str(status) in DECISION_LABELS else None)
    actor = _str(detail, "actor")
    if decision_raw is None or decision_raw not in DECISION_LABELS:
        return None
    label = DECISION_LABELS.get(decision_raw, "")
    text = (f"人已{GATE_ACTION.get(node, '做决定')}（{decision_raw} {label}），"
            f"签署人 {actor or _MISSING_TEXT}，理由：{_MISSING_TEXT}")
    if decision_raw == "milestone_only":
        text += "（按受影响子集跑回归后晋升，不要求冲突清零）"
    elif decision_raw == "defer":
        text += "（本轮显式终止）"
    return text + "。", "template"


def _headline_n0(detail: dict[str, Any], mode: str | None) -> str:
    baseline = _str(detail, "baseline")
    run_mode = _resolve_mode(detail, mode)
    return (f"工作目录已准备好：基线 {baseline or _MISSING_TEXT}，"
            f"运行模式 {run_mode or _MISSING_TEXT}。")


def _headline_n1(detail: dict[str, Any]) -> str | None:
    entries = _int(detail, "manifest.allfiles_entries")
    frozen = _int(detail, "manifest.cases_frozen")
    if entries is None:
        # 主数字缺失 ⇒ 不编替代值，交回 summary 降级（旧 run 的 summary 原文仍在）。
        return None
    files_text = f"{entries} 个文件"
    cases_text = f"冻结 {frozen} 个用例" if frozen is not None else "冻结用例数未下发"
    return f"快照完成：{files_text}，{cases_text}。"


def _headline_n3(detail: dict[str, Any]) -> tuple[str, str]:
    digest = _str(detail, "digest_summary")
    if not digest:
        return ("模型摘要未下发（旧 run 的 detail 没有摘要；"
                "正文在证据 n3_digest.md，面板不打开正文）。", "missing")
    text = "模型说：" + digest.rstrip("。") + "。"
    confirmations = _list(detail, "digest_confirmations")
    if confirmations:
        text += f"（另有 {len(confirmations)} 条需要你确认）"
    return text, "template"


def _headline_n5(detail: dict[str, Any]) -> str | None:
    count = _int(detail, "must_change_count")
    cases = _list(detail, "must_change_cases")
    names = "、".join(str(case) for case in (cases or []) if case) or "用例名未下发"
    # P-19（S2 定稿口径）：首屏看**去重用例数**；只有它缺失时才回退条目数（旧 run）。
    to_check = _int(detail, "to_check_case_count")
    if to_check is None:
        to_check = _int(detail, "to_check_count")
    if count is None:
        return None
    if to_check is None:
        return f"必改 {count} 个用例：{names}；另有待查（数量未下发）。"
    return (f"必改 {count} 个用例：{names}；另有 {to_check} 个待查"
            "（可能受影响，需人工确认）。")


def _headline_n6(detail: dict[str, Any]) -> str | None:
    targets = _int(detail, "targets")
    edits_text, edits_missing = _n6_case_edits_text(detail.get("case_edits"))
    validation = _bool(detail, "validation_ok")
    check = ("通过" if validation is True
             else "未通过" if validation is False else "未下发")
    if targets is None:
        return None
    if not edits_missing:
        return f"改了 {targets} 个用例：{edits_text}；输出校验{check}。"
    return (f"本轮修订目标 {targets} 个用例；逐用例修改未下发"
            f"（旧 run 的 detail 没有逐用例清单）；输出校验{check}。")


def _headline_n6_apply(detail: dict[str, Any]) -> str | None:
    cases = _int(detail, "cases")
    edits = _int(detail, "edits")
    status = _str(detail, "status")
    if status == "applied" and cases is not None and edits is not None:
        return (f"{cases} 个用例共 {edits} 处修改已写入沙箱；"
                "每条都在原文里唯一命中，改完的文件指纹已记录。")
    if cases is not None:
        source = _str(detail, "source")
        if source == "drill_fixture":
            return (f"{cases} 个用例写入沙箱；本次没有施加新的逐条修改"
                    "（drill 夹具直接采用现成沙箱件）。")
        return f"{cases} 个用例写入沙箱；逐条修改处数未下发。"
    return None


def _headline_n7(detail: dict[str, Any]) -> str | None:
    failed_cases = _list(detail, "failed_cases")
    case_count = _int(detail, "case_count")
    if case_count is None:
        cases = _list(detail, "cases")
        case_count = len(cases) if cases is not None else None
    if failed_cases:
        return f"{len(failed_cases)} 个用例编译失败。"
    if case_count is not None:
        return f"{case_count} 个用例都编译通过（失败 0）。"
    return None


def _headline_n8(detail: dict[str, Any], status: Any) -> str | None:
    verdict = _str(detail, "verdict") or (str(status) if status not in (None, "") else None)
    cycle = _int(detail, "cycle")
    limit = _int(detail, "limit")
    check = _int(detail, "check_count")
    must_fix = _int(detail, "must_fix_count")
    limit_text = f"返工上限 {limit}" if limit is not None else "返工上限未下发"
    if verdict == "pass":
        check_text = f"检查了 {check} 项" if check is not None else "检查项数未下发"
        return (f"复核通过：{check_text}，没有必须修改的地方"
                f"（第 {_cycle_text(cycle, plus=1)} 次复核，{limit_text}）。")
    if verdict in ("rework", "escalated"):
        cycle_text = _cycle_text(cycle)
        if verdict == "escalated":
            return (f"复核不通过：返工已达上限（第 {cycle_text} 次复核，"
                    f"{limit_text}）⇒ 升级人工裁决。")
        must_fix_text = f"{must_fix} 项" if must_fix is not None else "必须修改项数未下发"
        return (f"复核不通过：{must_fix_text}必须修改"
                f"（第 {cycle_text} 次复核，{limit_text}）。")
    return None


def _n9_source_sentence(detail: dict[str, Any]) -> str:
    """P-24 ③：口径一非零时的来源说明（只在 Host 下发了 `koutou1_by_case` 时才说）。

    - 恰好一个用例非零 ⇒ `（{n} 行全部来自 {case}）`；
    - 多个用例非零 ⇒ `（分布在 {k} 个用例：{case1}、{case2}…）`；
    - `koutou1_by_case` 未下发 / 没有非零用例 ⇒ 空串（不加）。
    """
    by_case = detail.get("koutou1_by_case")
    if not isinstance(by_case, dict):
        return ""
    nonzero: list[tuple[str, int]] = []
    for case, value in by_case.items():
        if isinstance(value, bool) or not isinstance(value, int) or value == 0:
            continue
        nonzero.append((str(case), value))
    if not nonzero:
        return ""
    if len(nonzero) == 1:
        case, value = nonzero[0]
        return f"（{value} 行全部来自 {case}）"
    names = "、".join(case for case, _ in nonzero[:3]) + ("…" if len(nonzero) > 3 else "")
    return f"（分布在 {len(nonzero)} 个用例：{names}）"


def _headline_n9(detail: dict[str, Any], status: Any) -> str:
    k1 = _int(detail, "koutou1")
    uvm_error = _int(detail, "koutou2.UVM_ERROR")
    uvm_fatal = _int(detail, "koutou2.UVM_FATAL")
    if status == "pass":
        verdict_text, passed_text = "判通过", "通过"
    elif status in ("fail", "failed"):
        verdict_text, passed_text = "判失败", "失败"
    else:
        verdict_text, passed_text = "结论未下发", "结论未下发"
    headline = (f"全跑{passed_text}：口径一（日志错误标记行数）{_fmt(k1)}，"
                f"口径二（UVM 报告）UVM_ERROR {_fmt(uvm_error)} / UVM_FATAL {_fmt(uvm_fatal)}；"
                f"两套口径都要为 0 才算通过 ⇒ {verdict_text}。")
    return headline + _n9_source_sentence(detail)


def _headline_submit(detail: dict[str, Any], kind: str) -> str | None:
    job = _str(detail, "job_id")
    if not job:
        return None
    cases = _int(detail, "cases")
    if cases is None:
        cases_list = _list(detail, "cases")
        cases = len(cases_list) if cases_list is not None else None
    tail = "等待作业完成" if kind == "N9" else "等待"
    cases_text = f"覆盖 {cases} 个用例" if cases is not None else "覆盖用例数未下发"
    return (f"已提交{'全跑' if kind == 'N9' else '回归'}作业 {job}，"
            f"{cases_text}；流程转入{tail}。")


def _headline_n10(detail: dict[str, Any]) -> str:
    passed = _bool(detail, "verdict_passed")
    pending = _int(detail, "pending")
    table = _list(detail, "cases_table")
    verdict_text = ("通过" if passed is True else "未通过" if passed is False else "未下发")
    if not table:
        if passed is None:
            return ("整轮判定未下发（本节点 detail 没有 verdict_passed）；"
                    "逐用例原因未下发（旧 run 的 detail 没有这张表）。")
        return (f"判定{verdict_text}（verdict_passed="
                f"{'true' if passed else 'false'}）；"
                "逐用例原因未下发（旧 run 的 detail 没有这张表）。")
    parts: list[str] = []
    for row in table:
        if not isinstance(row, dict):
            continue
        case = str(row.get("case") or "用例名未下发")
        reasons = row.get("reasons")
        reason_text = ("、".join(str(r) for r in reasons[:3])
                       if isinstance(reasons, list) and reasons else "原因未下发")
        if row.get("passed") is True:
            parts.append(f"{case} 通过")
        elif row.get("passed") is False:
            parts.append(f"{case} 未通过（{reason_text}）")
        else:
            parts.append(f"{case} 判定未下发（{reason_text}）")
    summary = "；".join(parts[:4]) + ("…" if len(parts) > 4 else "")
    pending_text = f"待裁决 {pending} 项" if pending is not None else "待裁决项数未下发"
    prefix = f"整轮{verdict_text}" if passed is not None else "整轮判定未下发"
    return f"{prefix}：{summary}；{pending_text}。"


def _headline_n11(detail: dict[str, Any]) -> str:
    chain = _str(detail, "chain")
    identity_table = _list(detail, "identity_table")
    cases = _int(detail, "cases")
    if cases is None and identity_table is not None:
        cases = len(identity_table)
    # S2 给 `rework_requests_count`；旧 run 的 detail 用 `rework`（同义计数）或列表。
    rework = _int(detail, "rework_requests_count")
    if rework is None:
        rework = _int(detail, "rework")
    if rework is None:
        requests = _list(detail, "rework_requests")
        rework = len(requests) if requests is not None else None
    inconsistent = sum(
        1 for row in (identity_table or [])
        if isinstance(row, dict) and row.get("consistent") is False
    )
    host_consistent = _bool(detail, "host_consistent")
    rework_text = f"返工请求 {rework} 条" if rework is not None else "返工请求条数未下发"
    if chain == "intact" and inconsistent == 0 and host_consistent is not False:
        cases_text = f"{cases} 个用例身份" if cases is not None else "各用例身份"
        return (f"证据链完整：{cases_text}四处一致"
                f"（run_id / 用例名 / 审的 md5 / 跑的 md5），{rework_text}。")
    bad = inconsistent if inconsistent else cases
    bad_text = f"{bad} 个用例身份对不上" if bad is not None else "用例身份对不上"
    return (f"证据链不完整：{bad_text}"
            f"（run_id / 用例名 / 审的 md5 / 跑的 md5），{rework_text}。")


def _headline_n12(detail: dict[str, Any]) -> str:
    claimed = _str(detail, "claimed_verdict")
    claimed_text = (VERDICT_LABELS.get(claimed, claimed) if claimed else _MISSING_TEXT)
    ref_count = _int(detail, "ref_count")
    parseable = _int(detail, "refs_parseable_count")
    open_items = _list(detail, "open_items")
    if ref_count is None:
        refs_clause = f"引用证据数{_MISSING_TEXT}"
    elif parseable is None:
        refs_clause = f"引用 {ref_count} 条证据（不可解析条数未下发）"
    else:
        refs_clause = f"引用 {ref_count} 条证据（不可解析 {ref_count - parseable} 条）"
    open_text = (f"未闭环 {len(open_items)} 项" if open_items is not None
                 else "未闭环项数未下发")
    return f"报告结论：{claimed_text}；{refs_clause}；{open_text}。"


def _headline_n15_select(detail: dict[str, Any], mode: str | None) -> str | None:
    g3 = _str(detail, "g3")
    g3_text = DECISION_LABELS.get(g3, g3) if g3 else "未签署"
    cases = _list(detail, "cases")
    names = [str(name) for name in (cases or []) if name]
    count = _int(detail, "count")
    if count is None and names:
        count = len(names)
    if count is None:
        return None
    subset = "按受影响子集" if g3 != "full_now" else "按全量回归集"
    names_text = f"（{'、'.join(names)}）" if names else ""
    _, will_text, _ = _n15_will_really_run_text(detail, mode)
    if will_text.startswith("否"):
        run_text = "演示模式不真跑"
    elif will_text.startswith("是"):
        run_text = f"会真跑这 {count} 个"
    else:
        run_text = "本次是否真跑未下发"
    return (f"本轮 G3={g3_text}：{subset}选出 {count} 个回归用例"
            f"{names_text}；{run_text}。")


def _headline_n15(detail: dict[str, Any], mode: str | None) -> tuple[str, str] | None:
    cases = _list(detail, "cases")
    names = [str(name) for name in (cases or []) if name]
    names_text = f"（{'、'.join(names)}）" if names else ""
    count = _int(detail, "count")
    if count is None and names:
        count = len(names)
    if count is None:
        return None
    if _not_executed("N15", detail, (), mode, None):
        return (f"演示模式：不真跑回归。本轮回归集 = {count} 个受影响用例"
                f"{names_text}。", "template")
    passed = detail.get("passed")
    failed_cases = _list(detail, "failed_cases")
    if isinstance(passed, bool):
        names = [str(name) for name in (failed_cases or []) if name]
        text = f"回归跑完：{count} 个用例，整轮判定{'通过' if passed else '未通过'}"
        if names:
            text += f"；失败 {len(names)} 个（{'、'.join(names[:6])}）"
        elif failed_cases is not None:
            text += "；失败 0 个"
        else:
            text += "；失败用例未下发（旧 run 的 detail 只有整轮判定）"
        return text + "。", "template"
    failed = _int(detail, "failed")
    if failed is None and failed_cases is not None:
        failed = len(failed_cases)
    passed_text = f"通过 {passed}" if passed is not None else "通过数未下发"
    failed_text = f"失败 {failed}" if failed is not None else "失败数未下发"
    return (f"回归跑完：{count} 个用例，{passed_text}，{failed_text}。", "template")


def _headline_n16(detail: dict[str, Any], status: Any) -> str:
    raw = detail.get("status", status)
    reason = _str(detail, "reason_line")
    dry_run = _bool(detail, "dry_run")
    trial = ("本次是试运行（dry-run），没有真正落盘。"
             if dry_run is not False else "本次是真实写入尝试。")
    reason_text = reason.rstrip("。") if reason else "拒绝原因未下发（原文在原始记录的 stderr 段）"
    if raw == "refused":
        return f"晋升被拒：{reason_text}。{trial}"
    if raw == "ok":
        return f"晋升成功（试运行）：{reason_text}。{trial}"
    if raw in (None, ""):
        return f"晋升结果未下发。{trial}"
    return f"晋升失败（{raw}）：{reason_text}。{trial}"


def _headline_halt(detail: dict[str, Any]) -> str:
    reason = _str(detail, "reason")
    if reason:
        return f"本轮已终止：{reason.rstrip('。')}。这是合法终点，不是失败。"
    # 旧 run 的 HALT detail 只有 `{闸门: 决策}`：用各门决策中文化，不编原因。
    decisions = [
        (_gate_short(key), str(value))
        for key, value in detail.items()
        if isinstance(value, str) and value in DECISION_LABELS
    ]
    if decisions:
        text = "、".join(f"{key}={DECISION_LABELS[value]}（{value}）"
                        for key, value in decisions)
        return f"本轮已终止：{text}。这是合法终点，不是失败。"
    return ("本轮已终止：终止原因未下发（原记录没有 reason 字段；"
            "各闸门决策在原始记录里）。这是合法终点，不是失败。")


def _headline_failed(detail: dict[str, Any]) -> str:
    message = _str(detail, "message") or _str(detail, "error")
    return _FAILURE_PREFIX + ((message.rstrip("。") + "。") if message else _FAILURE_NO_REASON)


#: 逐节点 headline 模板（拿到数据时）。返回 `(文案, headline_source)`；`None` ⇒ 走通用降级。
def _maybe(text: str | None) -> tuple[str, str] | None:
    return None if text is None else (text, "template")


_TEMPLATES: dict[str, Callable[..., tuple[str, str] | None]] = {
    "N0": lambda detail, mode, status, gate: (_headline_n0(detail, mode), "template"),
    "N1": lambda detail, mode, status, gate: _maybe(_headline_n1(detail)),
    "N2": lambda detail, mode, status, gate: _n2_headline(detail),
    "N3": lambda detail, mode, status, gate: _headline_n3(detail),
    "N5": lambda detail, mode, status, gate: _maybe(_headline_n5(detail)),
    "N6": lambda detail, mode, status, gate: _maybe(_headline_n6(detail)),
    "N6_apply": lambda detail, mode, status, gate: _maybe(_headline_n6_apply(detail)),
    "N7": lambda detail, mode, status, gate: _maybe(_headline_n7(detail)),
    "N8": lambda detail, mode, status, gate: _maybe(_headline_n8(detail, status)),
    "N9": lambda detail, mode, status, gate: (_headline_n9(detail, status), "template"),
    "N9_submit": lambda detail, mode, status, gate: _maybe(_headline_submit(detail, "N9")),
    "N10": lambda detail, mode, status, gate: (_headline_n10(detail), "template"),
    "N11": lambda detail, mode, status, gate: (_headline_n11(detail), "template"),
    "N12": lambda detail, mode, status, gate: (_headline_n12(detail), "template"),
    "N15_select": lambda detail, mode, status, gate: _maybe(_headline_n15_select(detail, mode)),
    "N15": lambda detail, mode, status, gate: _headline_n15(detail, mode),
    "N15_submit": lambda detail, mode, status, gate: _maybe(_headline_submit(detail, "N15")),
    "N16": lambda detail, mode, status, gate: (_headline_n16(detail, status), "template"),
    "HALT": lambda detail, mode, status, gate: (_headline_halt(detail), "template"),
}


def _template_headline(node: str, detail: dict[str, Any], mode: str | None,
                       status: Any, gate: dict[str, Any] | None) -> tuple[str, str] | None:
    template = _TEMPLATES.get(node)
    if template is None:
        return None
    return template(detail, mode, status, gate)


def _run_status_gloss(run_status: Any) -> str | None:
    """R3-08：运行状态的中文释义（与 `status_glossary` 同一份表，不另写一套）。"""
    if run_status in (None, ""):
        return None
    return STATUS_GLOSSARY.get(str(run_status))


def _headline(node: str, detail: dict[str, Any], *, events: Sequence[dict[str, Any]],
              run_status: str | None, mode: str | None, gate: dict[str, Any] | None,
              status: Any, failed: bool, not_reached: bool,
              not_executed: bool, has_terminal: bool,
              run_halted: bool = False) -> tuple[str, str]:
    """结果一句话：状态优先（未执行 / 未到达 / 失败），再按节点模板，最后 summary 降级。"""
    if not_executed:
        if node in DRILL_SKIPPED_NODES and run_halted:
            # R3-10：drill 提前终止（运行已 halt）⇒ 中性归因，不把"没走到"说成"演示模式不提交"。
            return "本轮未执行这个节点（没有提交记录）。", "template"
        if node == "N15_submit":
            return "演示模式下不提交作业：本轮这个节点没有执行。", "template"
        if node == "N15":
            result = _headline_n15(detail, mode)
            if result is not None:
                return result
        return "演示模式下这个节点没有执行。", "template"
    if not_reached:
        # R3-08：`{run_status}` 原值必须保留；有释义就补中文 gloss，没有就不硬加。
        gloss = _run_status_gloss(run_status)
        if gloss:
            return f"本轮没有走到这个节点（运行停在 {run_status}，{gloss}）。", "missing"
        return f"本轮没有走到这个节点（运行停在 {run_status}）。", "missing"
    if failed:
        return _headline_failed(detail), "template"
    if node in GATE_NODES:
        gate_headline = _headline_gate(node, detail, gate, status)
        if gate_headline is not None:
            return gate_headline
        # 闸门块缺失（S3 未接入 / 事件流是唯一事实）时，只用事件说"在等人工"。
        if any(event.get("kind") == "gate_pending" for event in events):
            number, gate_name = GATE_DISPLAY.get(node, (None, None))
            return f"等待你处理：本轮停在闸门 {number}（{gate_name}）。", "template"
    if not detail and not has_terminal:
        # 还没收尾（没有 node_finished/node_failed，detail 为空）⇒ 不逐节点编"未下发"结论。
        return "这个节点还没有收尾记录（detail 为空），结果等它跑完再看。", "missing"
    templated = _template_headline(node, detail, mode, status, gate)
    if templated is not None:
        return templated
    summary = _str(detail, "summary")
    if summary:
        return summary, "summary"
    if not detail:
        return "这个节点还没有收尾记录（detail 为空），结果等它跑完再看。", "missing"
    return "结果未下发（服务端没有这个节点的结论字段）。", "missing"


# ---------------------------------------------------------------- steps（过程，P-04/P-07/P-16/P-19/P-24/P-33）


def _step_text(node: str, kind: str, status: Any, detail: dict[str, Any],
               mode: str | None = None) -> str:
    """一条事件 → 一句人话。只陈述事件里已有的字段；失败措辞不含"完成"。"""
    if kind == "node_started":
        return "开始执行"
    if kind == "node_finished":
        return _finished_text(node, status, detail, mode)
    if kind == "node_failed":
        reason = detail.get("error") or detail.get("message")
        return _FAILURE_PREFIX + (str(reason) if reason else _FAILURE_NO_REASON)
    if kind == "gate_pending":
        options = detail.get("decision_options")
        # 事件里的选项是原值列表；S3 闸门块里是 {value,label} 对象 —— 两种都能读。
        labels = [
            _decision_text(item.get("value") if isinstance(item, dict) else item)
            for item in (options or [])
        ]
        return "等待人工决策" + (f"（可选：{' / '.join(labels)}）" if labels else "")
    if kind == "gate_decided":
        decision = detail.get("decision") or status
        actor = detail.get("actor")
        text = "人工已决策：" + _decision_text(decision)
        return text + (f"，签署人 {actor}" if actor else "")
    if kind == "job_submitted":
        job = detail.get("job_id")
        cases = detail.get("cases")
        count = len(cases) if isinstance(cases, (list, tuple)) else None
        text = "提交作业" + (f" {job}" if job else "")
        if count is not None:
            text += f"，覆盖 {count} 个用例"
        return text
    if kind == "job_finished":
        job = detail.get("job_id")
        text = "作业结束" + (f"（{job}）" if job else "")
        k1 = detail.get("koutou1")
        if k1 is not None:
            text += f"：日志错误标记 {k1} 行"
        return text
    if kind == "job_progress":
        return "作业进行中"
    if kind == "admission_granted":
        job = detail.get("job_id")
        return "拿到执行槽位" + (f"（作业 {job}）" if job else "")
    if kind == "admission_queued":
        return "排队等待执行槽位"
    if kind == "admission_refused":
        return "执行槽位被拒绝"
    if kind == "warning":
        message = detail.get("message")
        return "警告：" + (str(message) if message else "详见原始记录")
    return f"事件：{kind or '未下发'}"


def _finished_text(node: str, status: Any, detail: dict[str, Any], mode: str | None = None) -> str:
    """`node_finished` 的收尾句：按节点语义说结论，status 原值仍由 chip 显示。"""
    if node in GATE_NODES:
        decision = detail.get("decision")
        text = "闸门结论：" + _decision_text(decision if decision is not None else status)
        if detail.get("human_signed") is True:
            text += "，人工已签署"
        return text
    if node == "N0":
        return ("工作目录已准备好（基线 "
                f"{_str(detail, 'baseline') or _MISSING_TEXT}，"
                f"模式 {_resolve_mode(detail, mode) or _MISSING_TEXT}）")
    if node == "N1":
        return (f"快照完成：{_fmt(_int(detail, 'manifest.allfiles_entries'))} 个文件，"
                f"冻结 {_fmt(_int(detail, 'manifest.cases_frozen'))} 个用例")
    if node == "N2":
        info = content_summary(detail)
        if info["present"] and info["has_change"] is False:
            return "比对结束：文件内容没有变化"
        if info["present"]:
            return (f"比对结束：{info['files']} 个文件有内容变化，"
                    f"{info['confirm']} 条需要确认")
        return "比对结束：逐条差异清单未下发"
    if node == "N3":
        return "模型摘要已生成（正文在证据 n3_digest.md，面板不打开正文）"
    if node == "N5":
        return f"影响分析完成：必改 {_fmt(_int(detail, 'must_change_count'))} 个用例"
    if node == "N6":
        validation = _bool(detail, "validation_ok")
        return (f"修订轮次收尾：目标 {_fmt(_int(detail, 'targets'))} 个用例，"
                f"输出校验{'通过' if validation is True else '未通过' if validation is False else '未下发'}")
    if node == "N6_apply":
        edits = _int(detail, "edits")
        return (f"{_fmt(_int(detail, 'cases'))} 个用例写入沙箱"
                + (f"（共 {edits} 处修改）" if edits is not None else ""))
    if node == "N7":
        failed_cases = _list(detail, "failed_cases")
        if failed_cases:
            return f"{len(failed_cases)} 个用例编译失败"
        return f"{_fmt(_int(detail, 'case_count'))} 个用例编译通过（失败 0）"
    if node == "N8":
        verdict = _str(detail, "verdict") or (str(status) if status not in (None, "") else None)
        return "复核结论：" + _verdict_text(verdict)
    if node == "N9":
        return ("作业结束：日志错误标记 "
                f"{_fmt(_int(detail, 'koutou1'))} 行 ⇒ "
                + ("判通过" if status == "pass" else
                   "判失败" if status in ("fail", "failed") else "结论未下发"))
    if node == "N9_submit":
        return (_headline_submit(detail, "N9") or "已提交全跑作业，流程转入等待作业完成").rstrip("。")
    if node == "N10":
        passed = _bool(detail, "verdict_passed")
        return ("整轮对账："
                + ("通过" if passed is True else "未通过" if passed is False else "判定未下发")
                + f"（待裁决 {_fmt(_int(detail, 'pending'))} 项）")
    if node == "N11":
        chain = _str(detail, "chain")
        return "证据链：" + ("完整" if chain == "intact" else
                             "不完整" if chain == "broken" else _MISSING_TEXT)
    if node == "N12":
        claimed = _str(detail, "claimed_verdict")
        return (f"报告结论：{VERDICT_LABELS.get(claimed, claimed) if claimed else _MISSING_TEXT}；"
                f"引用 {_fmt(_int(detail, 'ref_count'))} 条证据")
    if node == "N15_select":
        return f"选出 {_fmt(_int(detail, 'count'))} 个回归用例"
    if node == "N15":
        if _not_executed(node, detail, (), mode, None):
            return "演示模式：不真跑回归"
        passed = detail.get("passed")
        return ("回归跑完："
                f"{_fmt(_int(detail, 'count'))} 个用例，"
                + ("判定通过" if passed is True else
                   "判定未通过" if passed is False else f"通过 {_fmt(passed)}"))
    if node == "N15_submit":
        return (_headline_submit(detail, "N15") or "已提交回归作业，流程转入等待").rstrip("。")
    if node == "N16":
        raw = detail.get("status", status)
        return "晋升结束：" + _verdict_text(raw)
    if node == "HALT":
        reason = _str(detail, "reason")
        if reason:
            return "流程终止：" + reason.rstrip("。")
        decisions = [
            (_gate_short(key), str(value))
            for key, value in detail.items()
            if isinstance(value, str) and value in DECISION_LABELS
        ]
        if decisions:
            return "流程终止：" + "、".join(
                f"{key}={DECISION_LABELS[value]}（{value}）" for key, value in decisions)
        return "流程终止：终止原因未下发"
    return "结束，状态 " + _fmt_scalar(status)


# ---------------------------------------------------------------- 投影入口


def build_story(
    node: str,
    *,
    events: Sequence[dict[str, Any]],
    detail: dict[str, Any],
    purpose: str | None,
    run_status: str | None = None,
    mode: str | None = None,
    gate: dict[str, Any] | None = None,
    run_halted: bool = False,
    refs: Sequence[str] | None = None,
) -> dict[str, Any]:
    """生成 `story` 展示投影（plan §1）。

    `events` 必须已按 `seq` 升序且**只含该节点**的事件（调用方负责切片）；
    本函数不读盘、不取墙钟、不改输入。`run_status` / `mode` / `gate` 都是可选只读输入：
    - `run_status`：运行状态（`finished|failed` 才可能 `not_reached`）；
    - `mode`：运行模式（drill/real；用于"本次是否真跑"的口径）；
    - `gate`：S3 的闸门块（§2.4），原样透传并用于闸门三态 headline；
    - `run_halted`：运行是否已提前终止（由调用方从全量事件算出）。**只**影响
      `DRILL_SKIPPED_NODES` 的"未执行"归因文案（R3-10），不写进任何投影字段；
    - `refs`：**展示用** refs（调用方已按 run 目录过滤，SPEC-04 §6.7；与面板平铺 refs 同口径）。
      给了就只从这里给证据分组取件；不给则退回事件顶层 `refs` 合并（旧行为）。
    """
    event_list = [event for event in events if isinstance(event, dict)]
    node_detail = detail if isinstance(detail, dict) else {}
    gate_block = gate if isinstance(gate, dict) else None
    status = _terminal_status(event_list)
    failed = _node_failed(event_list)
    has_terminal = any(
        event.get("kind") in ("node_finished", "node_failed") for event in event_list
    )
    resolved_mode = _resolve_mode(node_detail, mode)
    state = _gate_state(gate_block)
    not_executed = _not_executed(node, node_detail, event_list, resolved_mode, run_status)
    # 闸门块已有材料/决策 ⇒ 节点确实走过，事件缺失是数据缺口，不谎报"没走到"。
    gate_has_material = state in ("waiting", "decided")
    # P-29 ②：闸门材料里的数字（S3 gate.counts）本身就是关键数字，等待态也要能看到。
    gate_counts_present = bool(
        node in GATE_NODES and isinstance(gate_block, dict)
        and isinstance(gate_block.get("counts"), dict) and gate_block["counts"]
    )
    not_reached = bool(
        not not_executed
        and run_status in TERMINAL_RUN_STATUSES
        and not event_list
        and not gate_has_material
    )
    headline, source = _headline(
        node, node_detail, events=event_list, run_status=run_status,
        mode=resolved_mode, gate=gate_block, status=status, failed=failed,
        not_reached=not_reached, not_executed=not_executed, has_terminal=has_terminal,
        run_halted=run_halted,
    )
    steps = [
        {
            "seq": event.get("seq"),
            "at": event.get("ts"),
            "kind": event.get("kind"),
            "status": event.get("status"),
            "text": _step_text(
                node, event.get("kind"), event.get("status"),
                event.get("detail") if isinstance(event.get("detail"), dict) else {},
                resolved_mode,
            ),
        }
        for event in event_list
    ]
    # R3-06：证据按用例分组（仅 N7/N9；`None` ⇒ 前端维持平铺 `refs`，不得报错）。
    # 展示 refs（若调用方已按 run 目录过滤）优先：组内不得出现面板不展示的目录外路径。
    evidence_groups, evidence_groups_note = _evidence_groups(
        node, node_detail, event_list, refs=refs)
    story: dict[str, Any] = {
        "purpose": purpose,
        "headline": headline,
        "headline_source": source,
        "note": _note(node, node_detail, gate_block),
        # P-30：运行已终态且该节点没有任何事件（闸门块也没有材料/决策）。
        "not_reached": not_reached,
        # P-32/P-33：drill/演示下确实没执行（有明确证据；与"未下发"区分）。
        "not_executed": not_executed,
        "evidence_note": _evidence_note(
            node, node_detail, gate_block, failed, not_executed,
            not_reached=not_reached, has_events=bool(event_list),
            wait_seconds=_gate_wait_seconds(event_list) if node in GATE_NODES else None,
            run_halted=run_halted),
        # R3-06：`[{case, refs, note}]`，每组 `note` 只在组内没有证据件时给一句说明；
        # `null` ⇒ 这个节点不分组（前端维持平铺 `refs`）。
        "evidence_groups": evidence_groups,
        "evidence_groups_note": evidence_groups_note,
        # P-07：只给释义，原值仍在 `status`（端点原样下发）。
        "status_note": _status_note(status),
        "status_glossary": dict(STATUS_GLOSSARY),
        "steps": steps,
        # 未走到 / 确实没执行 / 还没收尾的节点不逐项堆"未下发"（结果一句话已说清状态；
        # 前端对"detail 为空还没有收尾记录"另有固定提示，见 SPEC-REV-02 R1 / P-06）。
        "key_results": (
            [] if (not_reached or (not_executed and not event_list)
                   or (not node_detail and not has_terminal and not gate_counts_present))
            else key_results(node, node_detail, mode=resolved_mode, status=status,
                             gate=gate_block)
        ),
        # S3 的闸门块原样透传（前端渲染二级清单用；本模块不解释 entries）。
        "gate": gate_block,
    }
    # R3-03：**仅 N6 下发** `observation_points` 这个 key（N6 无该 detail 字段时给 `null`，
    # 用于旧 run/替身）；其余节点**不出现该键** —— 前端按"字段不存在 ⇒ 不渲染"判断，
    # 否则每个节点都会冒出一行"观测点未下发"的噪声（`[]` = 下发了但 0 条）。
    if node == "N6":
        story["observation_points"] = _observation_points(node, node_detail)
    return story


__all__ = [
    "DECISION_LABELS",
    "GATE_DISPLAY",
    "GATE_NODES",
    "MODEL_NODES",
    "RESULT_FIELDS",
    "STATUS_GLOSSARY",
    "TERMINAL_RUN_STATUSES",
    "VERDICT_LABELS",
    "build_story",
    "content_summary",
    "group_diff_entries",
    "key_results",
]
