"""U7（SPEC-REV-08）：会话深链编解码的纯函数受控断言（node 驱动）。

`web/session-url.js` 只做 URL 深链的编码/解码：run 选择与当前视图持久到 hash，
启动时恢复。app.js 仍是唯一会话协调 owner（replaceState/init 恢复/hashchange）。
本文件不证明浏览器恢复行为，只证明编解码口径与容错。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
WEB = Path(__file__).resolve().parents[1] / "web"
MODULE = WEB / "session-url.js"

pytestmark = pytest.mark.skipif(NODE is None, reason="本机无 node，跳过纯函数受控断言")


def _eval(expr: str):
    script = (
        "const U = require(" + json.dumps(str(MODULE)) + ");\n"
        "process.stdout.write(JSON.stringify(" + expr + "));\n"
    )
    proc = subprocess.run([NODE, "-e", script], cwd=str(WEB.parent),
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("node 执行失败：\n" + proc.stderr)
    return json.loads(proc.stdout)


def test_encode_run_and_view():
    assert _eval("U.encode('RUN-1', 'gate')") == "#run=RUN-1&view=gate"


def test_encode_run_only():
    assert _eval("U.encode('RUN-1', null)") == "#run=RUN-1"


def test_encode_view_only():
    assert _eval("U.encode(null, 'setup')") == "#view=setup"


def test_encode_empty_is_null():
    assert _eval("U.encode(null, null)") is None
    assert _eval("U.encode('', '')") is None


def test_decode_round_trip():
    assert _eval("U.decode(U.encode('RUN-2026-x_1', 'run'))") == {
        "runId": "RUN-2026-x_1", "view": "run"}


def test_decode_plain_hash_is_empty():
    assert _eval("U.decode('#')") == {"runId": None, "view": None}
    assert _eval("U.decode('')") == {"runId": None, "view": None}


def test_decode_unknown_keys_ignored():
    assert _eval("U.decode('#foo=1&run=R1&view=gate')") == {
        "runId": "R1", "view": "gate"}


def test_decode_invalid_view_dropped():
    assert _eval("U.decode('#run=R1&view=admin')") == {"runId": "R1", "view": None}


def test_decode_garbage_safe():
    assert _eval("U.decode('#%%%&=&=x')") == {"runId": None, "view": None}


def test_decode_url_encoded_run_id():
    assert _eval("U.decode(U.encode('RUN a&b', 'run'))") == {
        "runId": "RUN a&b", "view": "run"}
