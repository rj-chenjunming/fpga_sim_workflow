"""五个模型节点的输出契约（Pydantic）。

为什么用 Pydantic 而不是 YAML 里的 `{字段: [类型, 说明]}`：
YAML **没有元组**，`["str", "说明"]` 会被解析成列表 —— Agently 会把整个字段当成
"一个列表输出"。实测后果：模型把标量返回成单元素列表
（`verdict=['rework']`、`assessment=[...3 项]`），`counts_quoted` 变成空字典。

技能 `agently-request/references/output-control.md` 的首选就是
`.output(ModelClass, format="json")`，理由正是类型/必填/枚举/范围都能被精确声明。
因此：

- **字段形状**（本文件，代码所有）—— 类型、枚举、必填；
- **行为规则**（`prompts/loop_nodes.yaml`）—— info / instruct 散文；
- **确定性验收**（`workflows/chunks/model_steps.py::_validate`）—— Host 所有。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------- N3


class N3Group(BaseModel):
    segment: str = Field(
        description=("段基址，必须是 input.offered_segments 中的值；"
                     "offered_segments 为空时留空字符串（不要编段）")
    )
    kind: str = Field(description="变更种类")
    diff_ids: list[str] = Field(description="本组包含的 diff 条目 id，只能取自 input.diffs")
    why: str = Field(description="为什么归为一组")


class N3Output(BaseModel):
    summary: str = Field(
        description=("一到三句中文：**先说改了什么（白话，具体到文件与行为），再说影响面**；"
                     "不得只写统计句")
    )
    groups: list[N3Group] = Field(
        description=("分组结果；input.offered_segments 为空时返回空列表"
                     "（本轮没有段信息，不硬分组）")
    )
    risky_points: list[str] = Field(
        description="需要人工重点确认的点，逐条「一句风险 + 依据」（不得只写技术名词）"
    )


# ---------------------------------------------------------------- N6


class N6Edit(BaseModel):
    """一条**可机械施加**的文本修订。

    `old` 必须在目标文件里唯一命中（Host 逐条校验，命中 0 次或多次即失败，不猜）；
    `line` 是 input.targets[].excerpt 中给出的行号（1-based），仅用于溯源与 N8 复核。
    """

    line: int = Field(description="源文件中 1-based 行号（取自 input.targets[].excerpts 对应片段）")
    old: str = Field(description="必须逐字复制的原文片段；Host 要求它在文件里唯一命中")
    new: str = Field(description="替换后的片段；只做最小改动")
    basis: str = Field(description="依据：差异条目 id / 文档位定义 / 偏移 / 卡点A 检索结论")


class N6Revision(BaseModel):
    case: str = Field(description="目标用例名，必须取自 input.targets[].case")
    edits: list[N6Edit] = Field(description="该用例的全部修订；至少一条，Host 会逐条施加")
    rationale: str = Field(description="这批修订为什么能满足新 RTL/文档；引用 input 中的具体事实")


class N6ObservationPoint(BaseModel):
    """一条**观测点印记**声明（P-25 方案 A：作者让用例自己打印实际读回值）。

    为什么要有：真实轮 N10 的 I3 要求「期望观测点留下通过印记」，而基线用例本身不打印
    `[N6_...] OK ...` ⇒ 真实轮必然过不了。改为由作者在用例里加一行 UVM_INFO 打印**实际值**，
    Host/N10 仍按文档索引校验（不信任模型给的值）。

    Host 的跨字段校验（`workflows/chunks/model_steps.py::_validate`，fail-closed）：
    每个 `input.targets[].case` 至少一条；`marker` 全局唯一；`marker` 字符串必须出现在
    **同用例** `revisions[].edits[].new` 里（防"只列不写"）。
    """

    case: str = Field(description="目标用例名，必须取自 input.targets[].case")
    marker: str = Field(
        pattern=r"^N6_[A-Za-z0-9_]+$",
        description=("印记名，形如 N6_<检查点名>；只允许字母/数字/下划线，"
                     "且必须逐字出现在该用例 edits[].new 的 UVM_INFO 行里"),
    )
    addr: str = Field(
        pattern=r"^0x[0-9A-Fa-f]+$",
        description="十六进制字面量（如 0x0000），取自 input.targets[].revision_points 的 segment",
    )
    offset: str = Field(
        pattern=r"^0x[0-9A-Fa-f]+$",
        description="十六进制字面量（如 0x04），取自 input.targets[].revision_points 的 offset",
    )
    expected_value: str = Field(
        pattern=r"^0x[0-9A-Fa-f]+$",
        description="期望读回值的十六进制字面量（如 0x20260708），取自 rtl_change/doc_bitdef",
    )
    basis: str = Field(
        description="依据：引 input 的 revision_points / rtl_change / doc_bitdef 具体事实；不得空泛"
    )


class N6EditRef(BaseModel):
    model_config = ConfigDict(extra='forbid')
    case: str
    edit_index: int = Field(ge=0, strict=True, description="本次 revisions 同 case 的 edits 索引，从 0 起")


class N6IssueResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')
    issue_id: str = Field(description="逐字引用 rework_assignment.issues[].issue_id，每项恰好一次")
    target_sha256: str = Field(description="逐字引用 rework_assignment.target_sha256")
    disposition: Literal['addressed', 'blocked', 'not_applicable']
    explanation: str = Field(min_length=1, description="处理依据、阻塞或不适用理由；作者不能关闭问题")
    edit_refs: list[N6EditRef] = Field(description="addressed 必须引用本次候选修改；其余为空")


class N6Output(BaseModel):
    revisions: list[N6Revision] = Field(description="每个目标用例恰好一条")
    observation_points: list[N6ObservationPoint] = Field(
        description=("每个目标用例**至少一条**观测点印记（P-25）：用例里必须真的打印它，"
                     "且 marker 必须出现在该用例 edits[].new 里；Host 逐条校验，缺/非法即拒")
    )
    rework_resolution: list[str] = Field(description="上一轮每条退回意见如何处理；无返工则空列表")
    issue_responses: list[N6IssueResponse] = Field(
        default_factory=list, description="对 rework_assignment 每个问题逐项回应；无问题为空")
    notes: list[str] = Field(description="其他限制或不确定性")


# ---------------------------------------------------------------- N8


class N8Finding(BaseModel):
    item: str = Field(description="被复核的检查项")
    result: str = Field(description="pass 或 fail")
    basis: str = Field(description="可核依据（文件:行 或 具体规则）；不得空泛")


class IssueReview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    issue_id: str = Field(description="本节点 review_assignment.issues 中的 ID，每项恰好一条")
    review_context_sha256: str = Field(description="逐字引用本次 review_assignment.review_context_sha256")
    outcome: Literal['closed', 'open']
    rationale: str = Field(min_length=1, description="依据 acceptance 的具体核验理由，不以作者声明代替复核")
    evidence_refs: list[str] = Field(min_length=1, description="当前输入事实的非重复 JSON Pointer，必须存在且值非空；closed 须引用本节点主材料")
    rework_index: int | None = Field(ge=0, strict=True, description="open 对应原始 must_fix/rework_requests 列表的有效整数索引，不能为布尔值；closed 为 null")


class N8Output(BaseModel):
    verdict: Literal["pass", "rework"] = Field(description="全部通过=pass；有必须修复项=rework")
    findings: list[N8Finding] = Field(description="逐项复核结果")
    must_fix: list[str] = Field(description="必须修复项；pass 时为空列表")
    issue_reviews: list[IssueReview] = Field(default_factory=list, description="逐项复核 review_assignment；无问题为空")


# ---------------------------------------------------------------- N11


class N11ReworkRequest(BaseModel):
    case: str = Field(description="需要返工的用例名")
    what: str = Field(description="改什么")
    basis: str = Field(description="依据（引 input 中的具体事实）")


class N11Output(BaseModel):
    chain: Literal["intact", "broken"] = Field(
        description="证据链结论：身份四方同值且证据可解析=intact；任一不一致/不可解析=broken"
    )
    reasons: list[str] = Field(description="逐条引用 input.identity / input.evidence / input.case_states 的事实")
    rework_requests: list[N11ReworkRequest] = Field(description="不成链时的返工请求；intact 时为空列表")
    caveats: list[str] = Field(description="不确定性与未闭环项")
    issue_reviews: list[IssueReview] = Field(default_factory=list, description="逐项复核 review_assignment；无问题为空")


# ---------------------------------------------------------------- N12


class N12Section(BaseModel):
    heading: str = Field(description="章节标题")
    body_md: str = Field(description="章节正文（Markdown）")
    refs: list[str] = Field(description="本章引用的产物路径或证据引用")


class N12Output(BaseModel):
    title: str = Field(description="报告标题")
    sections: list[N12Section] = Field(description="报告章节")
    counts_quoted: dict[str, object] = Field(
        default_factory=dict,
        description="逐字引用的两套口径；键为 koutou1 / koutou2。**Host 会与权威值逐值比对**",
    )
    claimed_verdict: Literal["passed", "not_passed", "undetermined"] = Field(
        description="结构化结论：必须与 Host 提供的 input.verdict.passed 一致；不得用文字模糊"
    )
    open_items: list[str] = Field(description="未闭环项与冲突")


# ---------------------------------------------------------------- N10（仅分类，数字由 Host 抽）


class N10Item(BaseModel):
    bucket_id: str = Field(description="必须逐字引用 input.buckets 里的 bucket_id")
    classification: Literal["既有缺陷", "本轮引入", "待裁决"] = Field(description="该桶的归类")
    basis: str = Field(description="依据；不得空泛。判「本轮引入」必须说明它落在哪个修订点上")


class N10Output(BaseModel):
    items: list[N10Item] = Field(description="input.buckets 里**每个** bucket_id 恰好一条")
    summary: str = Field(description="一两句中文总结：这批失败的性质")
    unclassified: list[str] = Field(description="无法归类的 bucket_id；没有则空列表")


#: 节点 → 输出模型（`_validate` 的 kind 用同一批键）
SCHEMAS: dict[str, type[BaseModel]] = {
    "n3": N3Output,
    "n6": N6Output,
    "n8": N8Output,
    "n11": N11Output,
    "n12": N12Output,
    "n10": N10Output,
}

__all__ = [
    "SCHEMAS",
    "N3Output", "N3Group",
    "N6Output", "N6Revision", "N6Edit", "N6ObservationPoint",
    "N8Output", "N8Finding",
    "N11Output", "N11ReworkRequest",
    "N12Output", "N12Section",
    "N10Output", "N10Item",
]
