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
