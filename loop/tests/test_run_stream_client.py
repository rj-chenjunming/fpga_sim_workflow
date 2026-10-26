"""U2-a（SPEC-REV-07 / SPEC-04 §7.3）：SSE 客户端降级状态机的受控断言（node 驱动）。

`web/run-stream.js` 只做传输状态机：连接/实时/回退/停止与重试节拍；
不读全局、不写 DOM、不发请求（EventSource 与计时器全部注入）。
回退态**不**自带轮询——运行详情拉取回到 app.js 既有轮询路径（§7.3：与现状逐字一致）。
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

NODE = shutil.which("node")
WEB = Path(__file__).resolve().parents[1] / "web"
MODULE = WEB / "run-stream.js"

pytestmark = pytest.mark.skipif(NODE is None, reason="本机无 node，跳过纯函数受控断言")


def _eval(expr: str):
    script = (
        "const RS = require(" + json.dumps(str(MODULE)) + ");\n"
        + FAKE_HARNESS
        + "process.stdout.write(JSON.stringify(" + expr + "));\n"
    )
    proc = subprocess.run([NODE, "-e", script], cwd=str(WEB.parent),
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise AssertionError("node 执行失败：\n" + proc.stderr)
    return json.loads(proc.stdout)


FAKE_HARNESS = r"""
function fakes() {
  const timers = [];
  const esInstances = [];
  class FakeES {
    constructor(url) { this.url = url; this.readyState = 0; this.closed = false;
      this.listeners = {}; esInstances.push(this); }
    addEventListener(name, fn) { (this.listeners[name] = this.listeners[name] || []).push(fn); }
    fire(name, data) { (this.listeners[name] || []).forEach(fn => fn({data: JSON.stringify(data)})); }
    close() { this.closed = true; this.readyState = 2; }
  }
  const api = {
    setTimeout(fn, ms) { timers.push({fn, ms}); return timers.length; },
    clearTimeout(id) { if (timers[id - 1]) timers[id - 1].fired = true; },
    runTimers() { timers.forEach(t => { if (!t.fired) { t.fired = true; t.fn(); } }); },
  };
  return {timers, esInstances, FakeES, api};
}
"""


def test_start_connecting_then_open():
    out = _eval(
        "(function(){const f=fakes();const c=RS.createRunStream({url:'/s',EventSource:f.FakeES,"
        "onEvent:()=>{},onStateChange:()=>{},setTimeout:f.api.setTimeout,clearTimeout:f.api.clearTimeout});"
        "const s1=c.state();c.start();const s2=c.state();"
        "f.esInstances[0].fire('open');return [s1,s2,c.state()];})()"
    )
    assert out == ["stopped", "connecting", "open"]


def test_run_view_event_dispatches_parsed_payload():
    out = _eval(
        "(function(){const f=fakes();const seen=[];"
        "const c=RS.createRunStream({url:'/s',EventSource:f.FakeES,onEvent:(n,d)=>seen.push([n,d.run_id,d.status]),"
        "onStateChange:()=>{},setTimeout:f.api.setTimeout,clearTimeout:f.api.clearTimeout});"
        "c.start();f.esInstances[0].fire('run_view',{run_id:'A',status:'waiting_gate'});return seen;})()"
    )
    assert out == [["run_view", "A", "waiting_gate"]]


def test_error_degrades_to_fallback_closes_es_and_schedules_retry():
    out = _eval(
        "(function(){const f=fakes();"
        "const c=RS.createRunStream({url:'/s',EventSource:f.FakeES,onEvent:()=>{},"
        "onStateChange:()=>{},retryMs:15000,setTimeout:f.api.setTimeout,clearTimeout:f.api.clearTimeout});"
        "c.start();f.esInstances[0].fire('open');f.esInstances[0].fire('error',{});"
        "return [c.state(),f.esInstances[0].closed,f.timers.map(t=>t.ms)];})()"
    )
    assert out == ["fallback", True, [15000]]


def test_retry_after_fallback_creates_new_connection():
    out = _eval(
        "(function(){const f=fakes();"
        "const c=RS.createRunStream({url:'/s',EventSource:f.FakeES,onEvent:()=>{},"
        "onStateChange:()=>{},retryMs:15000,setTimeout:f.api.setTimeout,clearTimeout:f.api.clearTimeout});"
        "c.start();f.esInstances[0].fire('error',{});f.api.runTimers();"
        "return [c.state(),f.esInstances.length];})()"
    )
    assert out == ["connecting", 2]


def test_open_clears_pending_retry():
    out = _eval(
        "(function(){const f=fakes();"
        "const c=RS.createRunStream({url:'/s',EventSource:f.FakeES,onEvent:()=>{},"
        "onStateChange:()=>{},retryMs:15000,setTimeout:f.api.setTimeout,clearTimeout:f.api.clearTimeout});"
        "c.start();f.esInstances[0].fire('error',{});f.esInstances[0].fire('open');"
        "f.api.runTimers();return [c.state(),f.esInstances.length];})()"
    )
    assert out == ["open", 1]


def test_gone_dispatches_then_degrades():
    out = _eval(
        "(function(){const f=fakes();const seen=[];"
        "const c=RS.createRunStream({url:'/s',EventSource:f.FakeES,onEvent:(n)=>seen.push(n),"
        "onStateChange:()=>{},setTimeout:f.api.setTimeout,clearTimeout:f.api.clearTimeout});"
        "c.start();f.esInstances[0].fire('open');f.esInstances[0].fire('gone',{error:'run disappeared'});"
        "return [seen,c.state(),f.esInstances[0].closed];})()"
    )
    assert out == [["gone"], "fallback", True]


def test_stop_is_terminal_and_idempotent():
    out = _eval(
        "(function(){const f=fakes();"
        "const c=RS.createRunStream({url:'/s',EventSource:f.FakeES,onEvent:()=>{},"
        "onStateChange:()=>{},setTimeout:f.api.setTimeout,clearTimeout:f.api.clearTimeout});"
        "c.start();f.esInstances[0].fire('open');c.stop();c.stop();c.start();"
        "return [c.state(),f.esInstances.length,f.esInstances[0].closed];})()"
    )
    assert out == ["stopped", 1, True]


def test_double_start_creates_single_connection():
    out = _eval(
        "(function(){const f=fakes();"
        "const c=RS.createRunStream({url:'/s',EventSource:f.FakeES,onEvent:()=>{},"
        "onStateChange:()=>{},setTimeout:f.api.setTimeout,clearTimeout:f.api.clearTimeout});"
        "c.start();c.start();return f.esInstances.length;})()"
    )
    assert out == 1


def test_state_change_notifications_fire():
    out = _eval(
        "(function(){const f=fakes();const states=[];"
        "const c=RS.createRunStream({url:'/s',EventSource:f.FakeES,onEvent:()=>{},"
        "onStateChange:(s)=>states.push(s),setTimeout:f.api.setTimeout,clearTimeout:f.api.clearTimeout});"
        "c.start();f.esInstances[0].fire('open');f.esInstances[0].fire('error',{});c.stop();return states;})()"
    )
    assert out == ["connecting", "open", "fallback", "stopped"]


def test_custom_event_name_for_agent_stream():
    """U2-b（§6.10）：agent 流按事件名 agent_view 订阅并派发。"""
    out = _eval(
        "(function(){const f=fakes();const seen=[];"
        "const c=RS.createRunStream({url:'/s',EventSource:f.FakeES,eventName:'agent_view',"
        "onEvent:(n,d)=>seen.push([n,d.node]),onStateChange:()=>{},"
        "setTimeout:f.api.setTimeout,clearTimeout:f.api.clearTimeout});"
        "c.start();f.esInstances[0].fire('agent_view',{run_id:'A',node:'N6'});return seen;})()"
    )
    assert out == [["agent_view", "N6"]]
