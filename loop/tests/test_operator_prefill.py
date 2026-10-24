"""U1-c（SPEC-REV-07）：操作者身份预填的纯函数受控断言（node 驱动）。

`web/operator.js` 只做记忆与预填判定：只记 `human:<非空>`；预填只填「空/默认值」，
绝不覆盖已填值；存储不可用（localStorage 抛错/被禁）时静默降级为无记忆。
权威仍以 gates.json 的 human_signed 为准——本模块不参与任何提交校验。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
WEB = Path(__file__).resolve().parents[1] / "web"
MODULE = WEB / "operator.js"

pytestmark = pytest.mark.skipif(NODE is None, reason="本机无 node，跳过纯函数受控断言")


def _eval(expr: str):
    script = (
        "const O = require(" + json.dumps(str(MODULE)) + ");\n"
        "process.stdout.write(JSON.stringify(" + expr + "));\n"
    )
    proc = subprocess.run([NODE, "-e", script], cwd=str(WEB.parent),
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("node 执行失败：\n" + proc.stderr)
    return json.loads(proc.stdout)


def _storage(expr="({getItem:()=>null,setItem:()=>{}})"):
    return expr


def test_remember_and_recall_valid_operator():
    out = _eval(
        "(function(){const s={m:{},getItem(k){return this.m[k]??null},setItem(k,v){this.m[k]=v}};"
        "const ok=O.remember(' human:chen ',s);"
        "return [ok,O.recall(s)];})()"
    )
    assert out == [True, "human:chen"]


def test_remember_rejects_default_and_non_human():
    out = _eval(
        "(function(){const s={m:{},getItem(k){return this.m[k]??null},setItem(k,v){this.m[k]=v}};"
        "return [O.remember('human:',s),O.remember('model:n3',s),O.remember('',s),O.recall(s)];})()"
    )
    assert out == [False, False, False, ""]


def test_apply_fills_only_default_or_empty():
    remembered = "human:chen"
    assert _eval(f"O.apply('human:', {json.dumps(remembered)})") == "human:chen"
    assert _eval(f"O.apply('', {json.dumps(remembered)})") == "human:chen"


def test_apply_never_overrides_typed_value():
    """已填值（含输入到一半的 human:jo）必须原样保留，预填不与输入打架。"""
    remembered = "human:chen"
    assert _eval(f"O.apply('human:other', {json.dumps(remembered)})") == "human:other"
    assert _eval(f"O.apply('human:jo', {json.dumps(remembered)})") == "human:jo"


def test_apply_ignores_invalid_remembered():
    assert _eval("O.apply('human:', 'human: ')") == "human:"
    assert _eval("O.apply('human:', 'model:x')") == "human:"


def test_storage_failures_degrade_to_no_memory():
    """localStorage 抛错/被禁：不炸、返回未记忆。"""
    out = _eval(
        "(function(){const bad={getItem(){throw new Error('denied')},"
        "setItem(){throw new Error('denied')}};"
        "return [O.remember('human:chen',bad),O.recall(bad)];})()"
    )
    assert out == [False, ""]


def test_corrupt_stored_value_is_not_recalled():
    """存过的不合规值（手改 localStorage）不得被召回当预填。"""
    out = _eval(
        "(function(){const s={m:{'loop.operator.name':'<script>'},"
        "getItem(k){return this.m[k]??null},setItem(k,v){this.m[k]=v}};"
        "return O.recall(s);})()"
    )
    assert out == ""
