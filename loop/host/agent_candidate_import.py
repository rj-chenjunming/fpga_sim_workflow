"""S6 候选导入判据（DS-06；REV-13 §5.4、REV-14 B1/B3·D04、SPEC-08 §4 D04）。

**纯判据**：只读候选目录与入参，产出结构化结论；**不写任何业务件、不施加 edits、
不判 `old` 是否唯一命中**（apply 判据的唯一实现仍是
`workflows/chunks/host_steps.apply_edits`，红线 8：不出现第二套同判据实现）。

契约要点（SPEC-08 §4）：
- 候选导入**必须在确认执行停止后**发生：本模块只**消费**停止结论（`execution_state`），
  不自己再判"进程是否停了"（红线 8；停止事实的归属在 `agent_control`/进程层，S5 落地）。
  C1 阶段的停止事实由调用方以入参给出；S5 落地后换来源、本模块判据不变。
- 用**不可变快照**核对：清单（相对路径 → `md5`/`size`）、大小上限、路径、源版本（基线 md5）。
  拒绝：绝对路径、路径穿越、链接逃逸、特殊文件、额外未授权文件、源版本漂移、校验后换件。
- 拒绝一律带**可判 reason 枚举**且**不留半件**（本模块零写入 ⇒ 天然满足）。
- 大小上限是**显式常量**，超限**拒绝**（不截断）。

清单形状（Lead 冻结，G1）：`{rel_path: {"md5": <hex>, "size": <int>}}`，
`rel_path` 相对 `candidate_root`（POSIX 风格）；用例名由 `rel_path` 的 stem 给出
（`TESTLIB/tc_demo.sv` ⇒ `tc_demo`），目标覆盖按 stem 判（R17）。
`baseline`（可选）是 Host 在起资源时封存的 `{rel_path: md5}`：给了就必须与
`baseline_current`（调用方现算的源件 md5）逐项一致，否则判源漂移（R16）。
"""
from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

#: 白名单后缀（**显式常量**，不是"默认允许其它"）。大小写不敏感比较。
ALLOWED_SUFFIXES: frozenset[str] = frozenset({".sv", ".svh", ".v", ".vh", ".md", ".txt"})

#: 单候选文件大小上限（字节）：超限**拒绝**，绝不截断。
MAX_CANDIDATE_BYTES: int = 256 * 1024
#: 候选总大小上限（字节）：超限拒绝。
MAX_CANDIDATE_TOTAL_BYTES: int = 1024 * 1024

#: 唯一能放行导入的执行状态（已确认停止）。其它状态一律拒绝。
STOPPED = "stopped"
#: "明确还在跑"的状态 ⇒ R1（等停止后新尝试，不重发本次结果）。
NOT_STOPPED_STATES: frozenset[str] = frozenset({"prepared", "starting", "running"})


class RejectReason(str, Enum):
    """可判拒绝原因（逐条对应失败用例 R1–R19；字符串值进事件/payload，可直接断言）。"""

    EXECUTION_NOT_STOPPED = "execution_not_stopped"
    EXECUTION_UNKNOWN = "execution_unknown"
    CANDIDATE_ROOT_MISSING = "candidate_root_missing"
    CANDIDATE_ROOT_UNSAFE = "candidate_root_unsafe"
    MANIFEST_MISSING = "manifest_missing"
    MANIFEST_MALFORMED = "manifest_malformed"
    PATH_ABSOLUTE = "path_absolute"
    PATH_ESCAPE = "path_escape"
    PATH_SYMLINK = "path_symlink"
    NOT_REGULAR_FILE = "not_regular_file"
    SUFFIX_NOT_ALLOWED = "suffix_not_allowed"
    FILE_TOO_LARGE = "file_too_large"
    TOTAL_TOO_LARGE = "total_too_large"
    SIZE_MISMATCH = "size_mismatch"
    HASH_MISMATCH = "hash_mismatch"
    EXTRA_FILE = "extra_file"
    CANDIDATE_MISSING = "candidate_missing"
    SOURCE_DRIFT = "source_drift"
    TARGET_COVERAGE = "target_coverage"
    UNREADABLE = "unreadable"
    #: 由 `n6_apply` 在**施加阶段**判定（候选内容 != apply(基线, edits)）：不属于导入阶段，
    #: 但用同一枚举保证"候选不能绕过 edits 校验"这条防线只有一个可判值。
    EDITS_MISMATCH = "candidate_edits_mismatch"


@dataclass(frozen=True)
class CandidatePolicy:
    """导入策略（常量可注入，测试用小上限；生产用模块级常量）。"""

    allowed_suffixes: frozenset[str] = ALLOWED_SUFFIXES
    max_file_bytes: int = MAX_CANDIDATE_BYTES
    max_total_bytes: int = MAX_CANDIDATE_TOTAL_BYTES


@dataclass(frozen=True)
class ImportedCandidate:
    """一件**已核验**的候选：内容是校验时读到的同一份字节（不可变快照）。

    只保留有消费者的字段：`text`/`md5` 供 `n6_apply` 核对"候选 == apply(基线, edits)"，
    `case` 做业务键，`size`/`baseline_md5` 进 payload 与证据。
    """

    path: str                     # 相对 candidate_root 的 POSIX 路径
    case: str                     # 用例名（= path 的 stem）
    md5: str                      # 复算 md5（== 清单声明；换件即拒，不会走到这里）
    size: int
    text: str                     # UTF-8 文本内容
    baseline_md5: str | None = None


@dataclass(frozen=True)
class ImportResult:
    """结构化导入结论；`ok=False` 时 `reason` 必非空、`candidates` 必为空。"""

    ok: bool
    reason: RejectReason | None = None
    detail: str = ""
    candidates: tuple[ImportedCandidate, ...] = ()
    problems: tuple[str, ...] = ()
    total_bytes: int = 0
    execution_state: Any = None
    #: 停止未确认/仍在跑 ⇒ False（禁止自动重发，DS-05）；其它拒绝默认 True。
    resend_allowed: bool = True
    #: 是否真的做了"源版本漂移"核对（未给封存基线 ⇒ False，如实标，不冒充已核对）。
    drift_checked: bool = False

    @property
    def reason_value(self) -> str | None:
        return self.reason.value if self.reason is not None else None

    def by_case(self) -> dict[str, ImportedCandidate]:
        return {candidate.case: candidate for candidate in self.candidates}

    def record(self) -> dict[str, Any]:
        """进 payload/证据的投影（不含正文，避免把候选内容塞进状态）。"""
        return {
            "ok": self.ok,
            "reason": self.reason_value,
            "detail": self.detail,
            "execution_state": self.execution_state,
            "resend_allowed": self.resend_allowed,
            "drift_checked": self.drift_checked,
            "total_bytes": self.total_bytes,
            "files": [{"path": c.path, "case": c.case, "md5": c.md5, "size": c.size,
                       "baseline_md5": c.baseline_md5} for c in self.candidates],
            "problems": list(self.problems),
        }


def md5_hex(data: bytes) -> str:
    """字节 → md5（本模块唯一的哈希实现；调用方不再自拼）。"""
    return hashlib.md5(data).hexdigest()


def _norm_md5(value: Any) -> str | None:
    """规范 md5 声明：32 位十六进制（大小写不敏感）；不合规 ⇒ None（判缺件）。"""
    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if len(text) != 32 or any(ch not in "0123456789abcdef" for ch in text):
        return None
    return text


def _reject(reason: RejectReason, detail: str, *, execution_state: Any = None,
            resend_allowed: bool = True,
            problems: Iterable[str] = ()) -> ImportResult:
    return ImportResult(ok=False, reason=reason, detail=detail,
                        problems=tuple(problems), execution_state=execution_state,
                        resend_allowed=resend_allowed)


# ---------------------------------------------------------------- 清单


def _normalize_manifest(raw: Any) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """把 `{rel_path: {md5, size}}` 规范成 `{normalized_path: {"md5", "size"}}`。

    路径键先做 POSIX 规范化（`a//b`、`a/./b` ⇒ `a/b`）：否则"额外文件"扫描出的规范路径
    与清单原始键对不上，会把**合法**候选误判成 R14。两个原始键规范化后撞车 ⇒ 清单坏。
    """
    problems: list[str] = []
    if not isinstance(raw, Mapping):
        return {}, ["候选清单必须是 mapping（rel_path → {md5, size}）"]
    normalized: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            problems.append("候选清单的路径键必须是非空字符串（%r）" % (key,))
            continue
        try:
            path_key = PurePosixPath(key.strip()).as_posix()
        except (OSError, ValueError) as exc:
            problems.append("候选清单路径键不合规（%r）：%s" % (key, exc))
            continue
        if path_key in normalized:
            problems.append("候选清单重复声明同一路径（规范化后）：%r" % (path_key,))
            continue
        if not isinstance(value, Mapping):
            problems.append("候选清单条目 %r 必须是对象 {md5, size}" % (key,))
            continue
        md5 = _norm_md5(value.get("md5"))
        size = value.get("size")
        if md5 is None:
            problems.append("候选清单条目 %r 缺合法 md5（32 位十六进制）" % (key,))
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            problems.append("候选清单条目 %r 缺合法 size（非负整数）" % (key,))
        normalized[path_key] = {"md5": md5, "size": size}
    return normalized, problems


def _split_rel(rel: str) -> tuple[RejectReason | None, tuple[str, ...], str]:
    """切分并检查**声明**路径（纯字符串判定，未触盘）。"""
    text = rel.strip()
    if not text:
        return RejectReason.MANIFEST_MALFORMED, (), "候选清单里的相对路径为空"
    if "\x00" in text:
        return RejectReason.MANIFEST_MALFORMED, (), "候选清单的相对路径含 NUL"
    if PurePosixPath(text).is_absolute():
        return RejectReason.PATH_ABSOLUTE, (), "候选路径是绝对路径：%r" % (rel,)
    parts = PurePosixPath(text).parts
    if any(part == ".." for part in parts):
        return RejectReason.PATH_ESCAPE, (), "候选路径含 `..`：%r" % (rel,)
    cleaned = tuple(part for part in parts if part not in ("", "."))
    if not cleaned:
        return RejectReason.PATH_ESCAPE, (), "候选路径解析为空：%r" % (rel,)
    return None, cleaned, ""


# ---------------------------------------------------------------- 触盘检查


def _resolve_root(candidate_root: Any, attempt_root: Any) -> tuple[Path | None, ImportResult | None]:
    """候选根：必须存在、是真实目录、**在 attempt 根之内**、自身不是链接。"""
    if candidate_root is None or str(candidate_root).strip() == "":
        return None, _reject(RejectReason.CANDIDATE_ROOT_MISSING, "未声明候选根（candidate_root）")
    try:
        root = Path(str(candidate_root))
    except (OSError, ValueError) as exc:  # NUL 等非法路径
        return None, _reject(RejectReason.CANDIDATE_ROOT_UNSAFE, "候选根不是合法路径：%s" % exc)
    if not root.is_absolute():
        return None, _reject(RejectReason.CANDIDATE_ROOT_UNSAFE,
                             "候选根必须是绝对路径：%r" % (str(root),))
    if attempt_root is None or str(attempt_root).strip() == "":
        # 不能证明"在 attempt 根内"⇒ 失败安全
        return None, _reject(RejectReason.CANDIDATE_ROOT_UNSAFE,
                             "未给 attempt 根，无法证明候选根在 attempt 内")
    try:
        attempt = Path(str(attempt_root))
    except (OSError, ValueError) as exc:
        return None, _reject(RejectReason.CANDIDATE_ROOT_UNSAFE, "attempt 根不是合法路径：%s" % exc)
    if not attempt.is_absolute():
        return None, _reject(RejectReason.CANDIDATE_ROOT_UNSAFE,
                             "attempt 根必须是绝对路径：%r" % (str(attempt),))
    if root.is_symlink():
        return None, _reject(RejectReason.CANDIDATE_ROOT_UNSAFE,
                             "候选根本身是符号链接：%s" % (root,))
    if not root.exists():
        return None, _reject(RejectReason.CANDIDATE_ROOT_MISSING, "候选根不存在：%s" % (root,))
    if not root.is_dir():
        return None, _reject(RejectReason.CANDIDATE_ROOT_UNSAFE, "候选根不是目录：%s" % (root,))
    try:
        resolved_root, resolved_attempt = root.resolve(), attempt.resolve()
    except OSError as exc:
        return None, _reject(RejectReason.UNREADABLE, "候选根/attempt 根无法解析：%s" % exc)
    if not resolved_root.is_relative_to(resolved_attempt):
        return None, _reject(RejectReason.CANDIDATE_ROOT_UNSAFE,
                             "候选根在 attempt 根之外：%s ∉ %s" % (resolved_root, resolved_attempt))
    return root, None


def _check_one(root: Path, rel: str, entry: Mapping[str, Any],
               policy: CandidatePolicy) -> tuple[ImportedCandidate | None, ImportResult | None]:
    """逐件检查：路径安全 → 后缀 → 链接/普通文件 → 大小 → 哈希 → 文本。"""
    reason, parts, detail = _split_rel(rel)
    if reason is not None:
        return None, _reject(reason, detail if detail else rel, problems=[rel])

    suffix = PurePosixPath(*parts).suffix.lower()
    if suffix not in policy.allowed_suffixes:
        return None, _reject(
            RejectReason.SUFFIX_NOT_ALLOWED,
            "后缀 %r 不在白名单 %s（%r）" % (suffix, sorted(policy.allowed_suffixes), rel),
            problems=[rel])

    current = root
    for index, part in enumerate(parts):
        current = current / part
        if current.is_symlink():
            return None, _reject(
                RejectReason.PATH_SYMLINK,
                "候选路径含符号链接（第 %d 段）：%s" % (index + 1, current),
                problems=[rel])
        if index < len(parts) - 1:
            if not current.exists():
                return None, _reject(RejectReason.CANDIDATE_MISSING,
                                     "候选父目录不存在：%s" % (current,), problems=[rel])
            if not current.is_dir():
                return None, _reject(RejectReason.NOT_REGULAR_FILE,
                                     "候选路径的父段不是目录：%s" % (current,), problems=[rel])

    if not current.exists():
        return None, _reject(RejectReason.CANDIDATE_MISSING, "清单声明但候选件不存在：%s" % (current,),
                             problems=[rel])
    try:
        info = os.lstat(current)
    except OSError as exc:
        return None, _reject(RejectReason.UNREADABLE, "候选件无法 stat：%s（%s）" % (current, exc),
                             problems=[rel])
    if stat.S_ISLNK(info.st_mode):
        return None, _reject(RejectReason.PATH_SYMLINK, "候选件是符号链接：%s" % (current,),
                             problems=[rel])
    if not stat.S_ISREG(info.st_mode):
        return None, _reject(
            RejectReason.NOT_REGULAR_FILE,
            "候选件不是普通文件（mode=%o）：%s" % (stat.S_IMODE(info.st_mode), current),
            problems=[rel])

    if info.st_size > policy.max_file_bytes:
        return None, _reject(
            RejectReason.FILE_TOO_LARGE,
            "候选件超过单文件上限 %d 字节：%s 实际 %d（超限拒绝，不截断）"
            % (policy.max_file_bytes, rel, info.st_size),
            problems=[rel])
    declared_size = entry.get("size")
    if isinstance(declared_size, int) and not isinstance(declared_size, bool) \
            and declared_size != info.st_size:
        return None, _reject(
            RejectReason.SIZE_MISMATCH,
            "候选件大小与清单不符：%s 声明 %d 实际 %d" % (rel, declared_size, info.st_size),
            problems=[rel])

    try:
        data = current.read_bytes()
    except OSError as exc:
        return None, _reject(RejectReason.UNREADABLE, "候选件无法读取：%s（%s）" % (current, exc),
                             problems=[rel])
    digest = md5_hex(data)
    declared_md5 = entry.get("md5")
    if declared_md5 is None or digest != declared_md5:
        # 校验后换件：导入前复算与清单声明不符 ⇒ 拒（不是"以现读为准"）
        return None, _reject(
            RejectReason.HASH_MISMATCH,
            "候选件 md5 与清单声明不符（校验后换件）：%s 声明 %s 复算 %s"
            % (rel, declared_md5, digest),
            problems=[rel])
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return None, _reject(RejectReason.UNREADABLE,
                             "候选件不是 UTF-8 文本：%s（%s）" % (rel, exc), problems=[rel])

    case = PurePosixPath(*parts).stem
    return ImportedCandidate(path=PurePosixPath(*parts).as_posix(), case=case, md5=digest,
                             size=info.st_size, text=text), None


def _scan_entries(root: Path) -> set[str]:
    """列出候选根下所有**非目录**条目（相对 root 的 POSIX 路径；不跟随链接）。"""
    found: set[str] = set()
    stack: list[tuple[Path, tuple[str, ...]]] = [(root, ())]
    while stack:
        directory, prefix = stack.pop()
        with os.scandir(directory) as listing:
            entries = sorted(
                ((item.name, item.path, item.is_symlink(), item.is_dir()) for item in listing),
                key=lambda row: row[0])
        for name, path, is_link, is_dir in entries:
            parts = prefix + (name,)
            if is_link or not is_dir:
                found.add(PurePosixPath(*parts).as_posix())
            else:
                stack.append((Path(path), parts))
    return found


def _normalized_md5_map(raw: Any) -> Any:
    """把 `{rel_path: md5}` 的键做与清单相同的 POSIX 规范化（否则漂移核对会假阴性）。"""
    if raw is None or not isinstance(raw, Mapping):
        return raw
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            continue
        try:
            out[PurePosixPath(key.strip()).as_posix()] = value
        except (OSError, ValueError):
            out[key] = value
    return out


def _check_drift(entries: Mapping[str, Mapping[str, Any]], baseline: Any,
                 baseline_current: Any) -> tuple[bool, str | None, str]:
    """源漂移（R16）：封存基线 vs 现算基线逐项一致；给了封存基线但缺项 ⇒ 无法证明 ⇒ 拒。"""
    if not isinstance(baseline, Mapping):
        return False, RejectReason.MANIFEST_MALFORMED.value, "baseline 必须是 rel_path → md5"
    current_map: Mapping[str, Any] = baseline_current if isinstance(baseline_current, Mapping) else {}
    for rel in sorted(entries):
        declared = _norm_md5(baseline.get(rel))
        current = _norm_md5(current_map.get(rel))
        if declared is None:
            return (False, RejectReason.SOURCE_DRIFT.value,
                    "封存基线缺该候选的 md5（无法证明无漂移）：%s" % rel)
        if current is None:
            return (False, RejectReason.SOURCE_DRIFT.value,
                    "现算基线缺该候选的 md5（无法证明无漂移）：%s" % rel)
        if declared != current:
            return (False, RejectReason.SOURCE_DRIFT.value,
                    "源版本漂移：%s 封存基线 %s ≠ 当前基线 %s" % (rel, declared, current))
    return True, None, ""


# ---------------------------------------------------------------- 入口


def import_candidates(
    candidate_root: Path | str | None,
    *,
    manifest: Any,
    execution_state: Any,
    attempt_root: Path | str | None = None,
    baseline: Mapping[str, Any] | None = None,
    baseline_current: Mapping[str, Any] | None = None,
    expected_cases: Iterable[str] | None = None,
    policy: CandidatePolicy | None = None,
) -> ImportResult:
    """按白名单 + 哈希 + 停止确认核验一次候选导入；返回结构化结论（**零写入**）。

    参数（G1 冻结键由 `n6_apply` 的 resolver 从 `n6_author` 读出后传入）：
    - `candidate_root`：attempt 内的候选目录（绝对路径；必须落在 `attempt_root` 内）；
    - `manifest`：`{rel_path: {"md5", "size"}}`（**缺清单 ⇒ 拒**，否则无法判换件）；
    - `baseline`：起资源时封存的 `{rel_path: md5}`（可选；**给了就逐项核对**，缺项 ⇒ 源漂移）；
    - `baseline_current`：调用方**现算**的 `{rel_path: md5}`（源件当前内容）；
    - `execution_state`：**只允许 `"stopped"`**（已确认停止）。`prepared/starting/running`
      ⇒ R1；其它/缺失/`unknown`/`execution_unknown` ⇒ R2，且 `resend_allowed=False`
      （停止未知禁止自动重发，DS-05）。
    - `expected_cases`：本轮目标用例集合（按 `rel_path` 的 stem 判目标覆盖，R17）。

    停止事实的归属：本函数**不判**进程/会话是否已停（红线 8）。它只消费调用方给出的
    "已确认停止"结论；S5 落地后该结论来自 `agent_control` 的封存事实，本函数判据不变。

    返回值 `ImportResult`：`ok=False` 时 `reason` 可判、`candidates` 为空；
    `ok=True` 时 `candidates` 是**校验时读到的那份字节**（不可变快照），供 `n6_apply`
    核对"候选内容 == apply(基线, edits)"后再写沙箱。
    """
    active_policy = policy or CandidatePolicy()
    # 基线/现算基线的键与清单同规范化，否则"封存基线缺项"会把合法候选误判成源漂移
    baseline_map = _normalized_md5_map(baseline)
    current_map = _normalized_md5_map(baseline_current)

    # R1/R2：停止确认先于一切文件操作
    state = execution_state if isinstance(execution_state, str) else None
    if state != STOPPED:
        if state in NOT_STOPPED_STATES:
            return _reject(
                RejectReason.EXECUTION_NOT_STOPPED,
                "执行状态 %r 不是已停止 ⇒ 禁止导入候选（先停止并确认，再新尝试）" % (state,),
                execution_state=execution_state, resend_allowed=False)
        return _reject(
            RejectReason.EXECUTION_UNKNOWN,
            "执行停止状态未知（%r）⇒ 不导入、不重发（DS-05 execution_unknown）"
            % (execution_state,),
            execution_state=execution_state, resend_allowed=False)

    # R3/R4：候选根
    root, rejected = _resolve_root(candidate_root, attempt_root)
    if rejected is not None:
        return rejected
    assert root is not None

    # R5：清单
    if manifest is None:
        return _reject(RejectReason.MANIFEST_MISSING,
                       "缺候选清单（无法核对文件清单/大小/哈希，也就无法判换件）")
    entries, problems = _normalize_manifest(manifest)
    if problems:
        return _reject(RejectReason.MANIFEST_MALFORMED, "候选清单形状不合规",
                       problems=problems, execution_state=state)
    if not entries:
        return _reject(RejectReason.MANIFEST_MISSING, "候选清单为空")

    # R17：目标覆盖（按 stem）
    declared_cases = [PurePosixPath(rel.strip()).stem for rel in entries]
    duplicates = sorted({case for case in declared_cases if declared_cases.count(case) > 1})
    if duplicates:
        return _reject(RejectReason.TARGET_COVERAGE,
                       "候选清单对同一用例声明了多件：%s" % duplicates,
                       problems=duplicates, execution_state=state)
    if expected_cases is not None:
        expected = {str(case) for case in expected_cases}
        missing = sorted(expected - set(declared_cases))
        extra = sorted(set(declared_cases) - expected)
        if missing or extra:
            return _reject(
                RejectReason.TARGET_COVERAGE,
                "候选清单与目标用例集不一致：缺 %s / 多 %s" % (missing, extra),
                problems=missing + extra, execution_state=state)

    # 逐件检查（R6–R11/R13/R15/R19）
    imported: list[ImportedCandidate] = []
    total_bytes = 0
    for rel in sorted(entries):
        candidate, rejected = _check_one(root, rel, entries[rel], active_policy)
        if rejected is not None:
            return rejected
        assert candidate is not None
        declared = (_norm_md5(baseline_map.get(rel))
                    if isinstance(baseline_map, Mapping) else None)
        imported.append(ImportedCandidate(
            path=candidate.path, case=candidate.case, md5=candidate.md5,
            size=candidate.size, text=candidate.text, baseline_md5=declared))
        total_bytes += candidate.size

    # R14：额外文件（候选根下清单未声明的非目录条目）
    try:
        scanned = _scan_entries(root)
    except OSError as exc:
        return _reject(RejectReason.UNREADABLE, "候选目录无法遍历：%s" % exc)
    extra = sorted(scanned - set(entries))
    if extra:
        return _reject(RejectReason.EXTRA_FILE,
                       "候选目录含清单未声明的额外文件：%s" % extra,
                       problems=extra, execution_state=state)

    # R12：总量上限（拒绝，不截断）
    if total_bytes > active_policy.max_total_bytes:
        return _reject(
            RejectReason.TOTAL_TOO_LARGE,
            "候选总量超过上限 %d 字节：实际 %d（超限拒绝，不截断）"
            % (active_policy.max_total_bytes, total_bytes),
            execution_state=state)

    # R16：源漂移（仅在给了封存基线时核对；未给则如实标 drift_checked=False）
    drift_checked = False
    if baseline is not None:
        drift_checked, reason_value, detail = _check_drift(entries, baseline_map, current_map)
        if reason_value == RejectReason.MANIFEST_MALFORMED.value:
            return _reject(RejectReason.MANIFEST_MALFORMED, detail, execution_state=state)
        if reason_value is not None:
            return _reject(RejectReason.SOURCE_DRIFT, detail, execution_state=state)

    return ImportResult(ok=True, candidates=tuple(imported), total_bytes=total_bytes,
                        execution_state=state, drift_checked=drift_checked)


# ---------------------------------------------------------------- 停止后快照（S6 生产接线）


def snapshot_candidate_manifest(candidate_root: Path | str | None,
                                expected_paths: Iterable[str]) -> dict[str, dict[str, Any]]:
    """**停止后快照**：把"合同期望路径 + 现算 md5/size"做成候选清单（G1 的 `candidate_manifest`）。

    为什么是"合同键"而不是"扫到什么算什么"：清单若由扫描目录得到，`EXTRA_FILE`（扫描-清单差）
    与 `HASH_MISMATCH`（快照 vs 导入复算）在真机上就恒假，DS-06 的拒绝矩阵会变成空转。
    所以键只来自调用方给的**合同路径**（N6 = `TESTLIB/<case>.sv`），本函数只填值。

    本函数**只读**、不写盘、不施加 edits；判据仍在 `import_candidates`：
    - 合同路径不存在 / 是链接 / 非普通文件 / 读不到 ⇒ **不进清单**（由导入判据显式拒绝，
      不在快照阶段另立一套判定）；
    - 快照与导入之间文件被换 ⇒ 导入时复算 md5 不符（`hash_mismatch`）。
    """
    if candidate_root is None or str(candidate_root).strip() == "":
        return {}
    try:
        root = Path(str(candidate_root))
    except (OSError, ValueError):
        return {}
    if not root.is_absolute() or root.is_symlink() or not root.is_dir():
        return {}
    manifest: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for raw in expected_paths:
        if not isinstance(raw, str):
            continue
        reason, parts, _detail = _split_rel(raw)
        if reason is not None or not parts:
            continue
        rel = PurePosixPath(*parts).as_posix()
        if rel in seen:
            continue
        seen.add(rel)
        path = root
        unsafe = False
        for index, part in enumerate(parts):
            path = path / part
            if path.is_symlink():
                unsafe = True
                break
            if index < len(parts) - 1 and not path.is_dir():
                unsafe = True
                break
        if unsafe or not path.is_file():
            continue
        try:
            info = os.lstat(path)
            if not stat.S_ISREG(info.st_mode):
                continue
            data = path.read_bytes()
        except OSError:
            continue
        manifest[rel] = {"md5": md5_hex(data), "size": info.st_size}
    return manifest
