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
