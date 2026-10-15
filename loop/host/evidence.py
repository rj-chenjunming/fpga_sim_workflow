"""证据抽取：两套口径与观测印记。

规格依据：`doc/spec/LOOP_ORCHESTRATION_SPEC.md` §2 的 I3。

**红线**：这里的每个数字都必须由**文件内容数出来**，不得由任何地方手算或写死
（`doc/AGENTS.md` §5 红线 10）。抽取器自带对夹具的自证断言。

两套口径在真实日志里**本来就可以不一致**：本工程实测到
`*E` 文本 1687 条而 UVM 汇总 `UVM_ERROR = 0 / UVM_FATAL = 0`，
因为失败走的是 `uvm_info` 而非 `` `uvm_error ``。
⇒ 两套口径**分别取、分别存、并列展示，永不互相替代**。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: 口径二的汇总项。注意真实日志用 `UVM_ERROR :    0`（冒号后有空格对齐）。
_SEVERITY_RE = re.compile(r"^UVM_(INFO|WARNING|ERROR|FATAL)\s*:\s*(\d+)\s*$")
_ID_COUNT_RE = re.compile(r"^\[([^\]]+)\]\s+(\d+)\s*$")
#: 观测印记：`UVM_INFO <file>(<line>) @ <sim_time> us [<MARKER>] <text>`
#: `sim_time` 必须**非贪婪吃到 `[` 之前**：真实形态是 `@ 141.913 us [N6_...]`，
#: 若用 `\S+` 只吃到 `141.913`，后面就撞上单位 `us` 而匹配失败。
_IMPRINT_RE = re.compile(
    r"^UVM_INFO\s+(?P<file>\S+)\((?P<line>\d+)\)\s+@\s+(?P<sim_time>.+?)\s+"
    r"\[(?P<marker>[^\]]+)\]\s*(?P<text>.*)$"
)

#: 已知的期望印记（地址 → 期望值）。权威是接口文档位定义表，不是 RTL。
EXPECTED_IMPRINTS: dict[str, dict[str, str]] = {
    "N6_FPGA_DATE_PCIE": {"address": "0x0000+0x04", "value": "0x20260708"},
}


@dataclass
class Counts:
    """两套口径，缺一不可。"""

    koutou1: int
    koutou2: dict[str, int]
    koutou1_refs: list[str] = field(default_factory=list)
    koutou2_refs: list[str] = field(default_factory=list)

    @property
    def koutou1_zero(self) -> bool:
        return self.koutou1 == 0

    @property
    def koutou2_zero(self) -> bool:
        err = self.koutou2.get("UVM_ERROR")
        fatal = self.koutou2.get("UVM_FATAL")
        return err == 0 and fatal == 0

    @property
    def both_zero(self) -> bool:
        return self.koutou1_zero and self.koutou2_zero

    def as_dict(self) -> dict[str, Any]:
        return {
            "koutou1": {
                "label": "口径一（`*E` 文本行数）",
                "value": self.koutou1,
                "zero": self.koutou1_zero,
                "refs": self.koutou1_refs,
            },
            "koutou2": {
                "label": "口径二（UVM Report Summary）",
                "value": self.koutou2,
                "zero": self.koutou2_zero,
                "refs": self.koutou2_refs,
            },
            "both_zero": self.both_zero,
            "note": "两套口径分别取、分别存，不得互相替代（doc/AGENTS.md 红线 3 / spec I3）。",
        }


def _lines(text: str) -> list[str]:
    return text.splitlines()


def count_koutou1(text: str) -> tuple[int, list[str]]:
    """口径一 = 含 `*E` 的**行数**（与 `grep -c '\\*E'` 同口径）。

    返回 (行数, 前若干条参考位置)。计数与 `grep` 对齐是刻意的：
    换口径就等于换结论，必须能和既有证据对得上。
    """
    hits = [(i + 1, line) for i, line in enumerate(_lines(text)) if "*E" in line]
    refs = [f"line {lineno}: {line.strip()[:160]}" for lineno, line in hits[:5]]
    return len(hits), refs


def parse_koutou2(text: str) -> tuple[dict[str, int], list[str]]:
    """口径二 = UVM Report Summary 的 severity 计数。"""
    out: dict[str, int] = {}
    refs: list[str] = []
    for i, line in enumerate(_lines(text)):
        m = _SEVERITY_RE.match(line.strip())
        if m:
            out[f"UVM_{m.group(1)}"] = int(m.group(2))
            refs.append(f"line {i + 1}: {line.strip()}")
    return out, refs


def parse_report_ids(text: str) -> dict[str, int]:
    """UVM 汇总的 by-id 段：`[N6_FPGA_DATE_PCIE]     1`。"""
    ids: dict[str, int] = {}
    lines = _lines(text)
    start = None
    for i, line in enumerate(lines):
        if "Report counts by id" in line:
            start = i
            break
    if start is None:
        return ids
    for line in lines[start + 1 :]:
        if line.startswith("---"):
            break
        m = _ID_COUNT_RE.match(line.strip())
        if m:
            ids[m.group(1)] = int(m.group(2))
    return ids


def find_imprints(text: str, marker_filter: str | None = None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, line in enumerate(_lines(text)):
        m = _IMPRINT_RE.match(line.strip())
        if not m:
            continue
        marker = m.group("marker")
        if marker_filter and marker != marker_filter:
            continue
        out.append(
            {
                "line": i + 1,
                "file": m.group("file"),
                "src_line": int(m.group("line")),
                "sim_time": m.group("sim_time"),
                "marker": marker,
                "text": m.group("text").strip(),
                "ref": f"{m.group('file')}:{m.group('line')}",
            }
        )
    return out


def imprint_consistency(text: str, marker: str) -> dict[str, Any]:
    """观测印记的**三向一致**校验（spec I3 最后一项）。

    三向 = ① 日志里出现该印记行；② 汇总 by-id 段计数 ≥1；③ 印记的地址/值与期望一致。
    """
    expected = EXPECTED_IMPRINTS.get(marker, {})
    imprints = find_imprints(text, marker)
    ids = parse_report_ids(text)
    id_count = ids.get(marker, 0)

    observed_addr = None
    observed_value = None
    for imp in imprints:
        text_body = imp["text"]
        parts = text_body.split()
        for token in parts:
            if re.fullmatch(r"0x[0-9a-fA-F]{4}\+0x[0-9a-fA-F]{2}", token):
                observed_addr = token
            if token.startswith("="):
                continue
        m = re.search(r"=\s*(0x[0-9a-fA-F]+)", text_body)
        if m:
            observed_value = m.group(1)

    checks = {
        "imprint_present": len(imprints) > 0,
        "id_count_present": id_count >= 1,
        "address_matches_expected": observed_addr == expected.get("address") if expected else None,
        "value_matches_expected": observed_value == expected.get("value") if expected else None,
    }
    verified = [k for k, v in checks.items() if v is True]
    failed = [k for k, v in checks.items() if v is False]
    return {
        "marker": marker,
        "observed": {
            "imprint": imprints[0] if imprints else None,
            "address": observed_addr,
            "value": observed_value,
            "id_count": id_count,
        },
        "expected": expected,
        "checks": checks,
        "verified_count": len(verified),
        "failed_count": len(failed),
        "consistent": not failed,
        "refs": [imp["ref"] for imp in imprints[:3]],
    }


def evidence_view(log_path: Path) -> dict[str, Any]:
    """一个日志文件的完整证据视图。数字全部来自文件内容。"""
    path = Path(log_path)
    if not path.is_file():
        return {
            "path": str(path),
            "present": False,
            "defect": "E-2：证据文件缺失 ⇒ 不得展示为可用证据（UI 必须显式标注而非 404）。",
        }
    text = path.read_text(encoding="utf-8", errors="replace")
    k1, k1_refs = count_koutou1(text)
    k2, k2_refs = parse_koutou2(text)
    counts = Counts(koutou1=k1, koutou2=k2, koutou1_refs=k1_refs, koutou2_refs=k2_refs)
    return {
        "path": str(path),
        "present": True,
        "bytes": path.stat().st_size,
        "counts": counts.as_dict(),
        "imprints": {
            marker: imprint_consistency(text, marker) for marker in EXPECTED_IMPRINTS
        },
        "has_report_summary": "UVM Report Summary" in text,
        "verdict": _verdict(counts, text),
    }


def _verdict(counts: Counts, text: str) -> dict[str, Any]:
    """判据：PASS ⟺ 两套口径皆 0 ∧ 出现 UVM Report Summary（对齐 spec I3）。"""
    reasons: list[str] = []
    if "UVM Report Summary" not in text:
        reasons.append("缺少 UVM Report Summary（全跑证据不完整）")
    if not counts.koutou1_zero:
        reasons.append(f"口径一 = {counts.koutou1} ≠ 0")
    if not counts.koutou2_zero:
        reasons.append(f"口径二 UVM_ERROR={counts.koutou2.get('UVM_ERROR')} / UVM_FATAL={counts.koutou2.get('UVM_FATAL')}")
    passed = not reasons
    return {
        "passed": passed,
        "reasons": reasons,
        "criterion": "PASS ⟺ 两套口径皆 0 ∧ UVM Report Summary 出现",
        "must_not": "口径二为 0 不足以判绿：口径一非 0 时**不得**判跑通。",
    }


#: 口径一的逐地址分解：`UVM_INFO ... [PCIE_REG_RD@3DW] *E @ADDR[0x84] -> DATA[0x0] != EXP[0xffffffff]`
_FAIL_ADDR_RE = re.compile(r"\*E\s+@ADDR\[(0x[0-9a-fA-F]+)\]")


def fail_address_table(text: str) -> dict[str, Any]:
    """把口径一（`*E`）分解到**逐地址**，全部由 Host 确定性抽取。

    为什么这一步不能交给模型：这是**计数与算术**（红线 3 / 红线 10），
    也是"本轮引入 vs 既有缺陷"判定的**事实底座**。模型只负责在上层做语义分类。

    返回 `{addresses: [{address, count, sample_ref, sample}], total_entries,
    matched_entries, unmatched_lines, distinct_addresses}`。
    其中 `unmatched_lines` 是含 `*E` 但不含 `@ADDR[...]` 的行数 ——
    非零就必须显式报告，不能静默当成 0。
    """
    counts: dict[str, int] = {}
    samples: dict[str, tuple[int, str]] = {}
    fail_lines = 0
    matched = 0
    for i, line in enumerate(_lines(text)):
        if "*E" not in line:
            continue
        fail_lines += 1
        m = _FAIL_ADDR_RE.search(line)
        if not m:
            continue
        matched += 1
        addr = m.group(1).lower()
        counts[addr] = counts.get(addr, 0) + 1
        samples.setdefault(addr, (i + 1, line.strip()[:200]))

    addresses = [
        {
            "address": addr,
            "count": counts[addr],
            "sample_line": samples[addr][0],
            "sample_ref": f"line {samples[addr][0]}",
            "sample": samples[addr][1],
        }
        for addr in sorted(counts, key=lambda a: int(a, 16))
    ]
    return {
        "addresses": addresses,
        "total_entries": fail_lines,
        "matched_entries": matched,
        "unmatched_lines": fail_lines - matched,
        "distinct_addresses": len(addresses),
        "extraction_owner": "host:host/evidence.py（确定性；不经模型）",
    }


def normalize_address(token: str) -> int | None:
    """把 `0x84` / `0x0000+0x04` / `0x84` 统一成段内偏移整数，用于与修订点比对。"""
    value = str(token).strip().lower()
    if "+" in value:
        value = value.split("+", 1)[1]
    if value.startswith("0x"):
        try:
            return int(value, 16)
        except ValueError:
            return None
    return None


def revision_points(diffs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """本轮修订点（取自 N2 差异条目），Host 确定性。

    用于交叉核对模型的分类：判为「本轮引入」的地址**必须**落在某个修订点上，
    否则 Host 必须标记冲突（模型不能凭空说"这是这轮引入的"）。
    """
    out: list[dict[str, Any]] = []
    for d in diffs:
        seg = str(d.get("segment") or "")
        offset = str(d.get("offset") or "")
        entry_id = str(d.get("entry_id") or d.get("id") or "")
        norm = normalize_address(offset)
        if norm is None:
            continue
        out.append({"entry_id": entry_id, "segment": seg, "offset": offset,
                    "offset_int": norm, "display": f"{seg}+{offset}" if seg and "+" not in offset else offset})
    return out


#: 分桶上限：超过则把尾部合并进 `其他`，并**显式报告**合并了多少（不静默丢信息）。
MAX_FAIL_BUCKETS = 24


def fail_buckets(text: str, diffs: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """把逐地址失败**分桶**，供模型做有界语义分类。

    分工（技能 `agently-request`：模型给"有界任务相关事实 + 一个 host 签发的 key"，
    身份在 Host 侧重构）：
    - **Host**：抽地址、计数、按 `通道 + 段内高字节` 分桶、算是否落在本轮修订点上；
    - **模型**：只对每个桶判 {既有缺陷 / 本轮引入 / 待裁决} 并给依据；
    - **Host**：校验覆盖性与枚举，并把分类**回填到该桶的全部地址**（模型从不逐地址说话）。

    逐地址整体发给模型是不可行的（实测 1622 个不同地址）。
    """
    table = fail_address_table(text)
    channel_re = re.compile(r"\[([A-Z][A-Z0-9_@]*)\]")
    revs = revision_points(diffs or [])
    rev_set = {r["offset_int"] for r in revs}

    buckets: dict[str, dict[str, Any]] = {}
    for item in table["addresses"]:
        addr_int = normalize_address(item["address"]) or 0
        m = channel_re.search(item["sample"])
        channel = m.group(1) if m else "(unknown)"
        key = f"{channel}|0x{addr_int >> 8:02x}xx"
        b = buckets.setdefault(key, {
            "bucket_id": key, "channel": channel,
            "range": f"0x{addr_int >> 8:02x}00-0x{addr_int >> 8:02x}ff",
            "addresses": [], "entry_count": 0,
        })
        b["addresses"].append(item["address"])
        b["entry_count"] += item["count"]

    ordered = sorted(buckets.values(), key=lambda b: -b["entry_count"])
    merged_note = None
    if len(ordered) > MAX_FAIL_BUCKETS:
        head, tail = ordered[: MAX_FAIL_BUCKETS - 1], ordered[MAX_FAIL_BUCKETS - 1 :]
        merged = {
            "bucket_id": "(merged)", "channel": "(mixed)",
            "range": f"其余 {len(tail)} 个桶", "addresses": [],
            "entry_count": sum(b["entry_count"] for b in tail),
        }
        for b in tail:
            merged["addresses"].extend(b["addresses"])
        merged_note = {"merged_buckets": len(tail), "merged_entries": merged["entry_count"]}
        ordered = head + [merged]

    for b in ordered:
        overlaps = [a for a in b["addresses"] if (normalize_address(a) or -1) in rev_set]
        b["address_count"] = len(b["addresses"])
        b["overlaps_revision_point"] = bool(overlaps)
        b["overlapping_addresses"] = overlaps[:5]
        b["sample_addresses"] = b["addresses"][:6]
        del b["addresses"]

    return {
        "buckets": ordered,
        "bucket_count": len(ordered),
        "merged_note": merged_note,
        "revision_points": revs,
        # Host 算出的总事实：本轮失败里**有没有**任何地址落在修订点上。
        # 这是"本轮引入 vs 既有缺陷"的确定性底座，模型不得改写。
        "any_bucket_overlaps_revision_point": any(b["overlaps_revision_point"] for b in ordered),
        "coverage": {
            "distinct_addresses": table["distinct_addresses"],
            "addresses_in_buckets": sum(b["address_count"] for b in ordered),
            "entries_in_buckets": sum(b["entry_count"] for b in ordered),
            "total_entries": table["total_entries"],
        },
        "extraction_owner": "host:host/evidence.py（分桶与修订点交集均为确定性）",
    }
