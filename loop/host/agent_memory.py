"""Host 管理的请求记录与人工经验筛选；不写业务状态、不重发请求。"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from host import paths as P

MAX_CONTEXT_BYTES = 120_000
MEMORY_RULE = ("历史 approved_experiences 仅是有来源的参考。当前事实、当前文档和 Host 校验优先；"
               "不得据历史经验签署闸门、忽略 blockers、改写计数或宣称本轮已通过。")


def normalized(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): normalized(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((normalized(v) for v in value), key=lambda v: json.dumps(v, sort_keys=True))
    if isinstance(value, (list, tuple)):
        return [normalized(v) for v in value]
    return value


def encoded(value: Any) -> bytes:
    return json.dumps(normalized(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def fingerprint(value: Any) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def scope_for(ctx, input_data: dict, contract: dict) -> dict:
    try:
        baseline = json.loads((ctx.run_dir / "view.json").read_text()).get("baseline")
    except (OSError, ValueError, AttributeError):
        baseline = None
    facts = {k: v for k, v in input_data.items()
             if k not in {"run_id", "cycle", "rework_reasons", "approved_experiences"}}
    return {"env_id": P.ENV_ID, "baseline": baseline,
            "facts_sha256": fingerprint(facts),
            "prompt_sha256": fingerprint({k: contract[k] for k in ("info", "instruct")}),
            "schema_sha256": fingerprint(contract["schema"])}


def experiences(ctx, scope: dict) -> tuple[list[dict], list[str]]:
    path = ctx.kb.root / "adjudication" / "agent_experiences.json"
    if not path.exists():
        return [], []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict) or doc.get("version") != 1 or not isinstance(doc.get("items"), list):
            raise ValueError("catalog format/version")
        items = doc["items"]
        if len(items) > 10:
            raise ValueError("catalog exceeds ten entries")
        ids = [i.get("id") for i in items if isinstance(i, dict)]
        if len(ids) != len(items) or any(not isinstance(i, str) or not i for i in ids) or len(set(ids)) != len(ids):
            raise ValueError("invalid or duplicate id")
    except (OSError, ValueError, TypeError) as exc:
        return [], [f"experience catalog rejected: {type(exc).__name__}"]
    if not scope.get("baseline"):
        return [], ["experience catalog rejected: current baseline unknown"]
    selected, diagnostics = [], []
    for item in items:
        try:
            actor = item.get("approved_by")
            if item.get("status") != "approved" or not isinstance(actor, str) or not actor.startswith("human:") or not actor[6:].strip():
                raise ValueError("human confirmation missing")
            if item.get("scope") != scope:
                raise ValueError("scope mismatch")
            advice = item.get("advice")
            if not isinstance(advice, str) or not advice.strip() or len(advice) > 4000:
                raise ValueError("invalid advice size")
            source = item.get("source") or {}
            rel = Path(source["path"])
            root = ctx.kb.root.resolve()
            runs = (root / "runs").resolve()
            resolved = (root / rel).resolve()
            if rel.is_absolute() or not rel.parts or rel.parts[0] != "runs" or ".." in rel.parts or not runs.is_relative_to(root) or not resolved.is_relative_to(runs) or not resolved.is_file():
                raise ValueError("source escapes workspace runs or missing")
            sha = hashlib.sha256(resolved.read_bytes()).hexdigest()
            if sha != source.get("sha256"):
                raise ValueError("source fingerprint mismatch")
            selected.append({"id": item["id"], "advice": advice,
                             "source": {"path": rel.as_posix(), "sha256": sha}})
        except (OSError, ValueError, TypeError, KeyError) as exc:
            diagnostics.append(f"{item['id']}: {exc}")
    return selected, diagnostics


def check_budget(input_data: dict, contract: dict) -> int:
    size = len(encoded({"input": input_data, **contract}))
    if size > MAX_CONTEXT_BYTES:
        raise RuntimeError(f"agent context budget exceeded（上下文预算）: {size} > {MAX_CONTEXT_BYTES} bytes")
    return size


def _sync_directory(folder: Path) -> None:
    """同步目录项；不承诺断电持久性（R1 契约只承诺进程终止）。"""
    fd = os.open(folder, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _write_once(path: Path, content: bytes) -> None:
    """把内容**不可覆盖地原子发布**到 `path`（R1，`AGENT_CONTEXT_SPEC` 原子发布条款）。

    私有临时件（同目录）→ `fsync` → `os.link`（已存在则失败）→ 删除临时件 → 同步目录。
    任一点被终止时，最终名下只可能「不存在」或「完整」；临时件名不参与读取扫描。
    本函数仍是「一次写成」，与历史的 `_write_once` 语义一致，只是不再边写边暴露最终名。
    """
    path = Path(path)
    folder = path.parent
    fd, temp_name = tempfile.mkstemp(prefix=".publish-", suffix=".tmp", dir=folder)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fchmod(stream.fileno(), 0o400)
            os.fsync(stream.fileno())
        os.link(temp, path)  # 不可覆盖：已发布的同名记录绝不被改写
    finally:
        with contextlib.suppress(OSError):
            temp.unlink()
        _sync_directory(folder)


def seal_record(path: Path, value: Any) -> None:
    """公开封存接口：写数据 + 校验和（唯一发布点；顺序固定 数据 → 校验和）。"""
    content = encoded(value)
    _write_once(path, content)
    _write_once(path.with_suffix(".sha256"), hashlib.sha256(content).hexdigest().encode("ascii"))


#: 兼容别名（历史调用与测试仍可使用；新代码走 `seal_record`）。
_sealed = seal_record


def record_state(path: Path) -> str:
    """只读诊断一次记录文件：`absent / incomplete / corrupt / committed`（F08）。

    - `absent`：文件不存在；
    - `incomplete`：数据在、校验和缺失（进程在两步之间被终止的典型状态）；
    - `corrupt`：校验和不匹配或 JSON 不可解析；
    - `committed`：内容与校验和一致且可解析。
    本函数不修文件、不删除、不回填。
    """
    path = Path(path)
    digest_path = path.with_suffix(".sha256")
    # 符号链接是安全信号（F08 复核 M1）：显式失败，不得静默降级成普通状态。
    if path.is_symlink() or digest_path.is_symlink():
        raise ValueError("agent record 路径使用符号链接")
    if not path.is_file():
        return "absent"
    if not digest_path.is_file():
        return "incomplete"
    try:
        content = path.read_bytes()
        expected = digest_path.read_text().strip()
    except OSError:
        return "incomplete"
    if hashlib.sha256(content).hexdigest() != expected:
        return "corrupt"
    try:
        json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "corrupt"
    return "committed"


class Attempt:
    def __init__(self, ctx, node: str, request: dict):
        if not re.fullmatch(r"N(?:3|6|8|10|11|12)", node):
            raise ValueError(f"unsupported model node: {node}")
        self.ctx = ctx
        root = ctx.run_dir / "agent_calls" / node
        root.mkdir(parents=True, exist_ok=True)
        sequence = 1
        while True:
            self.path = root / f"attempt-{sequence:06d}"
            try:
                self.path.mkdir()
                break
            except FileExistsError:
                sequence += 1
        self.identity = {"format_version": 1, "run_id": ctx.run_id, "node": node,
                         "attempt": sequence}
        _sealed(self.path / "request.json", {**request, **self.identity,
                "memory_implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})

    def finish(self, status: str, **result) -> None:
        _sealed(self.path / "result.json", {**result, **self.identity, "status": status})

    def refs(self) -> dict:
        return {"request_ref": (self.path / "request.json").relative_to(self.ctx.run_dir).as_posix(),
                "result_ref": (self.path / "result.json").relative_to(self.ctx.run_dir).as_posix()}


def verify_attempt(path: Path) -> dict:
    out = {}
    for name in ("request", "result"):
        target = Path(path) / f"{name}.json"
        if target.is_symlink() or target.with_suffix(".sha256").is_symlink():
            raise ValueError("agent record 路径使用符号链接")
        try:
            content = (path / f"{name}.json").read_bytes()
            expected = (path / f"{name}.sha256").read_text().strip()
        except OSError as exc:
            raise ValueError(f"incomplete agent record: {name}") from exc
        if hashlib.sha256(content).hexdigest() != expected:
            raise ValueError(f"agent record checksum mismatch: {name}")
        out[name] = json.loads(content)
    keys = ("format_version", "run_id", "node", "attempt")
    if any(out["request"].get(k) != out["result"].get(k) for k in keys):
        raise ValueError("agent record identity mismatch")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify agent records without reissuing requests.")
    parser.add_argument("--verify", type=Path, required=True)
    args = parser.parse_args()
    try:
        record = verify_attempt(args.verify)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1
    print(json.dumps({"ok": True, "run_id": record["request"]["run_id"],
                      "node": record["request"]["node"], "attempt": record["request"]["attempt"],
                      "status": record["result"]["status"], "scope": record["request"].get("scope")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
