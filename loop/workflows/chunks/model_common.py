"""模型节点共享小工具（F06）：提示词读取与 run 目录读写。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..context import RunCtx

import yaml

PROMPTS_FILE = Path(__file__).resolve().parents[2] / "prompts" / "loop_nodes.yaml"


def load_prompts() -> dict[str, Any]:
    doc = yaml.safe_load(PROMPTS_FILE.read_text(encoding="utf-8"))
    return doc if isinstance(doc, dict) else {}


def read_json(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def artifact(ctx: RunCtx, name: str) -> Path:  # noqa: F821 - 仅类型标注，避免循环导入
    return ctx.run_dir / name


def case_edits_from_output(data: dict[str, Any] | None) -> list[dict[str, Any]] | None:
    """N6 模型输出 → 逐用例修改摘要（P-20/P-21 的**唯一投影实现**）。

    形状（契约 §3）：`[{case, edit_count, edits:[{line, old, new}]}]`。
    `edits` 逐字取自 Host 已校验的 `revisions[].edits`，**不重算、不猜**；
    没有模型输出（standin/drill）⇒ `None`（显式"未下发"，不是空列表冒充"0 处修改"）。
    N6（模型节点）与 N6_apply（Host 落盘）共用本函数 ⇒ 两处清单同源。
    """
    if not isinstance(data, dict):
        return None
    revisions = data.get("revisions")
    if not isinstance(revisions, list):
        return None
    out: list[dict[str, Any]] = []
    for rev in revisions:
        if not isinstance(rev, dict):
            continue
        edits = [
            {"line": e.get("line"), "old": e.get("old"), "new": e.get("new")}
            for e in (rev.get("edits") or [])
            if isinstance(e, dict)
        ]
        out.append({"case": str(rev.get("case") or ""), "edit_count": len(edits),
                    "edits": edits})
    return out


def _num(value: Any) -> str:
    """数字缺失一律写"未下发"（不猜、不补 0）。"""
    return "未下发" if value is None else str(value)


def counts_text(counts: dict[str, Any] | None) -> str:
    """并列双口径的一行文本。**只做格式化**：数字全部取自传入的 counts，不重算。"""
    doc = counts or {}
    k1 = doc.get("koutou1") or {}
    k2 = doc.get("koutou2") or {}
    value2 = k2.get("value")
    if isinstance(value2, dict):
        second = f"UVM_ERROR={_num(value2.get('UVM_ERROR'))}/UVM_FATAL={_num(value2.get('UVM_FATAL'))}"
    elif value2 is None:
        second = "口径二=未下发"
    else:
        second = f"口径二={value2}"
    return f"口径一={_num(k1.get('value'))}，{second}"
