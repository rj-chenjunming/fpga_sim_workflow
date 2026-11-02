#!/usr/bin/env python3
"""F14-a · 改前样式基线采集（只读，不改 loop/web/**）。

用途：为 F14-b 样式收敛固定「改前」可观察事实——截图、关键元素计算样式、
媒体查询生效矩阵、版面几何、交互态（hover / focus-visible / disabled / 告警 /
模态 / toast / 目录选择器 / 旧页）与键盘焦点顺序。

边界（只读）：
- 只启动 127.0.0.1 临时静态服务指向 loop/web/，API 全部由 Playwright route 返回受控替身；
  不连接真实服务、不写 loop/web/**、不写 ENV_ROOT / kb/**。
- 输出只写 `--out` 指定的证据目录（默认本文件所在目录）。

用法（必须在 loop/ 下用 .venv 运行，且 HOME 可写、指定浏览器）：
    cd loop
    mkdir -p /tmp/h
    HOME=/tmp/h XDG_CONFIG_HOME=/tmp/h/.config XDG_CACHE_HOME=/tmp/h/.cache \
      LOOP_BROWSER_EXECUTABLE=/usr/bin/google-chrome \
      .venv/bin/python ../doc/evidence/R_BLOCK_C_20261022/collect_f14a.py \
        --out ../doc/evidence/R_BLOCK_C_20261022

缺 HOME 可写或浏览器路径时 Chrome 启动会失败：是错误，不是 skip。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import platform
import re
import struct
import sys
import threading
import time
import traceback
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

VIEWPORTS = (1280, 1440, 1920)
NARROW = (390, 768)
HEIGHT = 1000
GATE = "G1_diff_confirm"

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
WEB = REPO / "loop" / "web"
SCREENS_DIR = None  # 由 main() 设置：默认 <out>/screens-before，可用 --screens-dir 覆盖


# --------------------------------------------------------------------------- #
# 受控 API 替身（与 loop/tests/browser 的固定数据同形，不连真实服务）
# --------------------------------------------------------------------------- #
def base_view(rid, baseline=None):
    return {
        "run_id": rid,
        "status": "waiting_gate",
        "mode": "drill",
        "baseline": baseline or rid + "-baseline",
        "node_history": [],
        "pending_interrupt": {
            "id": GATE + ":0",
            "type": "gate_decision",
            "payload": {"gate": GATE, "cycle": 0},
        },
        "gate_options": {
            GATE: [
                {"value": "confirmed", "label": "服务端确认"},
                {"value": "ignored", "label": "服务端忽略", "requires_reason": True},
            ]
        },
    }


def populated_view(v):
    """与 tests/browser/test_web_layout.py::populate 相同的受控数据。"""
    v.update(
        project="/simulation/projects/TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES",
        current_node="N4",
        baseline="v1.2-stable",
        node_history=[{"node": "N" + str(n), "status": "done"} for n in range(4)],
        counts={
            "koutou1": {"value": 3, "zero": False, "label": "口径一 · 未收敛项"},
            "koutou2": {"value": 1, "zero": False, "label": "口径二 · 用例状态"},
        },
        blockers=[
            {
                "severity": "blocker",
                "code": "REVIEW_PENDING",
                "message": "接口差异仍有未决条目，请先核对证据。",
            }
        ],
        agents=[
            {
                "role": role,
                "nodes": nodes,
                "capabilities": {
                    "implemented": True,
                    "dependencies_ready": None,
                    "execution": "not_started",
                    "verification_scope": None,
                },
                "status": "done" if role == "analyst" else "idle",
                "last_action": "node_finished(ok)" if role == "analyst" else "等待上游步骤",
                "summary": "已生成接口变更摘要，等待人工复核。" if role == "analyst" else None,
                "mode": "standin",
                "elapsed_s": 12 if role == "analyst" else None,
            }
            for role, nodes in [
                ("analyst", ["N3"]),
                ("author", ["N6"]),
                ("checker", ["N8", "N10"]),
                ("guardian", ["N11"]),
                ("reporter", ["N12"]),
            ]
        ],
    )
    v["pending_interrupt"]["payload"].update(
        difference_items={
            "present": True,
            "entries": [
                {
                    "entry_id": "D-001",
                    "kind": "interface",
                    "change": "modified",
                    "segment": "dma_controller.sv",
                    "lines": [128, 129],
                    "unresolved": "新增端口位宽需要人工核对",
                    "evidence": "input [15:0] transfer_length → input [31:0] transfer_length",
                },
                {
                    "entry_id": "D-002",
                    "kind": "register",
                    "change": "added",
                    "evidence": "新增状态寄存器，需补充边界激励。",
                },
            ],
        },
        unresolved_entries=["D-001"],
    )
    return v


def agent_view(run="A", node="N3", state="working", revision=1):
    return {
        "run_id": run,
        "node": node,
        "live": {
            "session_id": node + ":session-000001",
            "state": state,
            "revision": revision,
            "attempt": 1,
            "available_actions": ["steer", "pause", "terminate"],
        },
        "attempts": [{"attempt": 1, "status": "incomplete", "model": "test-model"}],
        "selected_attempt": 1,
        "request": {
            "input": {"run_id": run, "task": node + " input"},
            "info": "task policy",
            "model": "test-model",
            "instruct": "check facts",
        },
        "result": None,
        "events": [],
        "controls": [],
    }


class MockApi:
    """受控 API：所有 /api/** 由本对象应答；POST 只记录，不落地。"""

    def __init__(self, page):
        self.views = {"A": base_view("A"), "B": base_view("B")}
        self.agent_views = {("A", "N3"): agent_view(), ("A", "N8"): agent_view(node="N8"),
                            ("A", "N10"): agent_view(node="N10"), ("B", "N3"): agent_view("B")}
        self.hold = None
        self.pending = []
        self.posts = []
        self.page_errors = []
        self.request_log = []
        page.route("**/api/**", self._handle)
        page.on("pageerror", lambda error: self.page_errors.append(str(error)))
        page.on("request", lambda req: self.request_log.append(
            (req.method, urlsplit(req.url).path)))

    # -- 路由 ------------------------------------------------------------- #
    def _handle(self, route):
        path = urlsplit(route.request.url).path
        if route.request.method == "POST":
            self.posts.append((path, route.request.post_data_json))
            self.pending.append(route)
            return
        if self.hold and self.hold(path):
            self.pending.append(route)
            return
        route.fulfill(json=self.body_for(path))

    def body_for(self, path):
        if path == "/api/health":
            return {"ok": True, "env_root": "/fixture", "plugin_missing": [],
                    "workspace_missing": []}
        if path == "/api/baselines":
            return {"baselines": [
                {"id": "v1.2-stable", "valid": True, "cases": 162, "parent": "v1.1",
                 "created_at": "2026-10-21T10:00:00"},
                {"id": "v1.1", "valid": True, "cases": 150, "parent": "v1.0",
                 "created_at": "2026-10-19T09:00:00"},
                {"id": "v0", "valid": True, "cases": 132, "parent": None,
                 "created_at": "2026-10-01T08:00:00"},
            ]}
        if path == "/api/runs":
            return {"runs": [{"run_id": rid, "status": "waiting_gate", "mode": "drill"}
                             for rid in self.views]}
        if path == "/api/fs/dirs":
            return {
                "path": "/simulation",
                "parent": "/",
                "roots": ["/simulation", "/projects"],
                "entries": [
                    {"name": "TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES", "is_dir": True,
                     "is_env": True, "markers": ["uvs.setup"], "counts": {"cases": 162}},
                    {"name": "baseline-v1.2", "is_dir": True, "is_baseline": True,
                     "markers": ["manifest.json"]},
                    {"name": "work-v1.3", "is_dir": True, "markers": []},
                ],
            }
        if "/agents/" in path:
            parts = path.split("/")
            try:
                return self.agent_views.get((parts[3], parts[5]), agent_view(parts[3], parts[5]))
            except IndexError:
                return agent_view()
        if path.endswith("/events"):
            return {"events": [], "last_seq": 0}
        if path.endswith("/evidence/exists"):
            return {"exist": False, "path": "run/evidence/n3_digest.md",
                    "note": "文件不存在"}
        if path.startswith("/api/runs/"):
            rid = path.rsplit("/", 1)[1]
            return self.views.get(rid, {"detail": {"error": "unknown run"}})
        return {"ok": False}

    def release(self, page, body, status=200):
        route = self.pending.pop(0)
        route.fulfill(status=status, json=body)
        page.wait_for_timeout(120)


# --------------------------------------------------------------------------- #
# 页面操作辅助
# --------------------------------------------------------------------------- #
class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def serve_web():
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(WEB)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, "http://127.0.0.1:%d" % server.server_port


def tick(page):
    """与测试同口径：推进假时钟 1.6 s 触发一次轮询，再用真实时间等回调。"""
    page.clock.run_for(1600)
    page.wait_for_timeout(90)


def select(page, rid):
    page.locator(".run-item").filter(has_text=rid).click()


def wait_js(page, expr, desc, timeout=5000):
    deadline = time.time() + timeout / 1000.0
    last = None
    while time.time() < deadline:
        try:
            if page.evaluate(expr):
                return True
        except Exception as exc:  # noqa: BLE001 - 采集脚本要如实报告失败
            last = exc
        page.wait_for_timeout(50)
    raise RuntimeError("等待超时：%s（最后异常：%s）" % (desc, last))


def inner_text(page, selector):
    return page.evaluate(
        "sel => { const el = document.querySelector(sel); return el ? el.innerText : null; }",
        selector)


def shot(page, path, full_page=True):
    page.evaluate("() => scrollTo(0, 0)")
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=full_page)
    return str(path)


STYLE_PROPS = [
    "font-family", "font-size", "font-weight", "font-style", "line-height",
    "letter-spacing", "color", "background-color", "background-image",
    "border-top-width", "border-right-width", "border-bottom-width", "border-left-width",
    "border-top-style", "border-top-color", "border-right-color", "border-bottom-color",
    "border-left-color", "border-radius",
    "padding-top", "padding-right", "padding-bottom", "padding-left",
    "margin-top", "margin-right", "margin-bottom", "margin-left",
    "row-gap", "column-gap", "display", "position",
    "overflow-x", "overflow-y", "box-shadow", "outline-width", "outline-style",
    "outline-color", "outline-offset", "text-transform", "opacity", "z-index",
    "transition-duration", "transition-property", "white-space",
]

_JS_STYLE = """
([sel, props]) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  return window.__f14a_style(el, props);
}
"""

_JS_HELPERS = r"""
window.__f14a_style = function (el, props) {
  const cs = getComputedStyle(el);
  const r = el.getBoundingClientRect();
  const out = {
    tag: el.tagName.toLowerCase(),
    id: el.id || null,
    classes: (typeof el.className === 'string' && el.className) || null,
    text: (el.innerText || el.value || '').trim().replace(/\s+/g, ' ').slice(0, 90),
    visible: !!el.getClientRects().length,
    rect: {x: +r.x.toFixed(2), y: +r.y.toFixed(2), w: +r.width.toFixed(2),
           h: +r.height.toFixed(2), right: +r.right.toFixed(2), bottom: +r.bottom.toFixed(2)},
    style: {}
  };
  props.forEach(p => { out.style[p] = cs.getPropertyValue(p); });
  return out;
};
window.__f14a_node_index = function (el) {
  return Array.prototype.indexOf.call(document.querySelectorAll('*'), el);
};
"""


def measure(page, selector, props=None):
    props = props or STYLE_PROPS
    return page.evaluate(_JS_STYLE, [selector, props])


def measure_labeled(page, label, selector, props=None):
    out = measure(page, selector, props)
    if out is None:
        return {"label": label, "selector": selector, "missing": True}
    out["label"] = label
    out["selector"] = selector
    return out


def overflow_report(page):
    return page.evaluate(r"""
() => {
  const vw = innerWidth;
  const isVisible = el => {
    const cs = getComputedStyle(el);
    return el.getClientRects().length && cs.visibility !== 'hidden' && cs.display !== 'none';
  };
  const offenders = [];
  document.querySelectorAll('body *').forEach(el => {
    if (!isVisible(el)) return;
    const r = el.getBoundingClientRect();
    if (r.width > 0 && (r.right > vw + 1 || r.left < -1)) {
      offenders.push({kind: 'viewport', tag: el.tagName.toLowerCase(), id: el.id || null,
        cls: (typeof el.className === 'string' && el.className) || null,
        left: +r.left.toFixed(1), right: +r.right.toFixed(1)});
      return;
    }
    const cs = getComputedStyle(el);
    if (el.scrollWidth > el.clientWidth + 1 && !/(auto|scroll)/.test(cs.overflowX)) {
      offenders.push({kind: 'local-overflow', tag: el.tagName.toLowerCase(), id: el.id || null,
        cls: (typeof el.className === 'string' && el.className) || null,
        clientWidth: el.clientWidth, scrollWidth: el.scrollWidth});
    }
  });
  return {
    viewportWidth: vw,
    documentScrollWidth: document.documentElement.scrollWidth,
    documentClientWidth: document.documentElement.clientWidth,
    bodyScrollWidth: document.body.scrollWidth,
    pageHorizontalOverflow: document.documentElement.scrollWidth > vw + 1,
    offenderCount: offenders.length,
    offenders: offenders.slice(0, 40)
  };
}
""")


def layout_report(page):
    return page.evaluate(r"""
() => {
  const q = s => document.querySelector(s);
  const rect = el => { if (!el) return null; const r = el.getBoundingClientRect();
    return {x: +r.x.toFixed(1), y: +r.y.toFixed(1), w: +r.width.toFixed(1), h: +r.height.toFixed(1)}; };
  const grid = sel => {
    const el = q(sel);
    if (!el) return {selector: sel, missing: true};
    const cs = getComputedStyle(el);
    return {selector: sel, display: cs.display, columns: cs.gridTemplateColumns,
            gap: cs.gap, rect: rect(el)};
  };
  const pad = sel => { const el = q(sel); if (!el) return null; const cs = getComputedStyle(el);
    return [cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft].join(' '); };
  return {
    innerWidth, innerHeight,
    devicePixelRatio: window.devicePixelRatio,
    visualViewportScale: window.visualViewport ? window.visualViewport.scale : null,
    documentScrollWidth: document.documentElement.scrollWidth,
    documentScrollHeight: document.documentElement.scrollHeight,
    header: rect(q('header')),
    sidebar: rect(q('aside#sidebar')),
    main: rect(q('#workspace')),
    shellDisplay: q('.shell') ? getComputedStyle(q('.shell')).display : null,
    shellFlexDirection: q('.shell') ? getComputedStyle(q('.shell')).flexDirection : null,
    mainPadding: pad('#workspace'),
    bodyFont: getComputedStyle(document.body).fontFamily,
    bodyFontSize: getComputedStyle(document.body).fontSize,
    bodyLineHeight: getComputedStyle(document.body).lineHeight,
    monoFont: (() => { const el = q('.mono'); return el ? getComputedStyle(el).fontFamily : null; })(),
    grids: ['.s0-grid', '.s0-phases', '.s0-evidence', '.grid2', '.run-grid',
            '#agents', '.agent-window .aw-layout', '.dirpicker'].map(grid),
    colorSchemes: {prefersDark: matchMedia('(prefers-color-scheme: dark)').matches},
    reducedMotionMatches: matchMedia('(prefers-reduced-motion: reduce)').matches
  };
}
""")


# --------------------------------------------------------------------------- #
# 焦点顺序
# --------------------------------------------------------------------------- #
_JS_ACTIVE = r"""
() => {
  const el = document.activeElement;
  if (!el) return null;
  const info = window.__f14a_style(el, ['outline-width','outline-style','outline-color',
    'outline-offset','box-shadow','background-color','border-color','color','font-size',
    'transition-duration','text-decoration-line']);
  info.nodeIndex = window.__f14a_node_index(el);
  info.role = el.getAttribute('role');
  info.type = el.getAttribute('type');
  info.tabindex = el.getAttribute('tabindex');
  info.ariaLabel = el.getAttribute('aria-label');
  info.focusVisible = el.matches(':focus-visible');
  info.inDialog = !!el.closest('dialog');
  info.disabled = el.disabled === true;
  return info;
}
"""


def focus_walk(page, max_steps=160):
    page.evaluate("""() => {
      if (document.activeElement && document.activeElement.blur) document.activeElement.blur();
      document.body.setAttribute('tabindex', '-1');
      document.body.focus();
    }""")
    steps = []
    seen = set()
    for _ in range(max_steps):
        page.keyboard.press("Tab")
        info = page.evaluate(_JS_ACTIVE)
        if info is None:
            steps.append({"leftDocument": True})
            break
        sig = (info["tag"], info["id"], info["classes"], info["nodeIndex"])
        if sig in seen:
            break
        seen.add(sig)
        steps.append(info)
    page.evaluate("() => document.body.removeAttribute('tabindex')")
    return steps


# --------------------------------------------------------------------------- #
# 元素清单（每个视图一份）
# --------------------------------------------------------------------------- #
COMMON = [
    ("body", "body"),
    ("顶栏 header", "header"),
    ("顶栏品牌 .brand", ".brand"),
    ("顶栏环境胶囊 #hdrEnv", "#hdrEnv"),
    ("顶栏地址胶囊 #hdrAddr", "#hdrAddr"),
    ("顶栏健康胶囊 #hdrHealth", "#hdrHealth"),
    ("旧版入口 #lnkLegacy", "#lnkLegacy"),
    ("跳过导航 .skip-link", ".skip-link"),
    ("左栏 aside#sidebar", "aside#sidebar"),
    ("左栏入口 #btnS0", "#btnS0"),
    ("新建运行 #btnNew", "#btnNew"),
    ("导航 tab 选中 #segS0.on", "#segS0"),
    ("导航 tab 未选 #segSetup", "#segSetup"),
    ("左栏分组标签 .rail-label", ".rail-label"),
    ("运行记录项 .run-item", ".run-item"),
    ("运行记录项选中 .run-item.active", ".run-item.active"),
    ("页标题 #pageTitle", "#pageTitle"),
    ("面包屑 .page-breadcrumb", ".page-breadcrumb"),
    ("页副标题 #pageSub", "#pageSub"),
    ("页编号 .page-edition", ".page-edition"),
    ("卡片 .card", ".card"),
    ("卡片头 .card-head", ".card-head"),
    ("卡片标题 .card-head h2", ".card-head h2"),
    ("卡片副标题 .card-head .sub", ".card-head .sub"),
    ("卡片体 .card-body", ".card-body"),
    ("页脚 .workspace-footer", ".workspace-footer"),
    ("等宽文本 .mono", ".mono"),
]

VIEW_INVENTORY = {
    "s0": [
        ("S0 hero .s0-hero", "#viewS0 .s0-hero"),
        ("S0 hero 标题 h2", "#viewS0 .s0-hero h2"),
        ("S0 hero 正文 p", "#viewS0 .s0-hero p"),
        ("S0 hero 标签 .hero-tags span", "#viewS0 .hero-tags span"),
        ("S0 示意 .hero-diagram", "#viewS0 .hero-diagram"),
        ("S0 阶段卡 .phase-card", "#viewS0 .phase-card"),
        ("S0 阶段序号 .phase-index", "#viewS0 .phase-index"),
        ("S0 阶段 chip 警告", "#s0PhaseB .chip"),
        ("S0 卡片序号 .section-index", "#viewS0 .section-index"),
        ("S0 表单标签 .s0-label", "#s0Form .s0-label"),
        ("S0 输入框 #s0Baseline", "#s0Baseline"),
        ("S0 边界说明 .s0-boundary", "#viewS0 .s0-boundary"),
        ("S0 主按钮 #s0Prepare", "#s0Prepare"),
        ("S0 检查项 .s0-checks li", "#s0Checks li"),
        ("S0 准出状态 #s0Readiness", "#s0Readiness"),
        ("S0 阻断区 .s0-blockers", "#viewS0 .s0-blockers"),
        ("S0 范围说明 .s0-scope", "#viewS0 .s0-scope"),
        ("S0 历史卡 .s0-history", "#viewS0 .s0-history"),
    ],
    "setup": [
        ("配置步骤卡 .step-card", "#viewSetup .step-card"),
        ("步骤序号 .step-no", "#viewSetup .step-no"),
        ("步骤标题 .step-title", "#viewSetup .step-title"),
        ("基线 select #setupBaseline", "#setupBaseline"),
        ("基线 chip #setupBaselineChip", "#setupBaselineChip"),
        ("浏览按钮 #btnBaselineBrowse", "#btnBaselineBrowse"),
        ("项目输入 #setupProject", "#setupProject"),
        ("校验按钮 #setupCheck", "#setupCheck"),
        ("字段说明 .field-meta", "#setupProjectMeta"),
        ("chips 容器 .chips", "#viewSetup .chips"),
        ("chip 普通", "#viewSetup .chips .chip"),
        ("chip 警告", "#viewSetup .chips .chip.warn"),
        ("模式 select #setupMode", "#setupMode"),
        ("选项字段标签 .field-label", "#viewSetup .field-label"),
        ("真实运行告警 #realWarn", "#realWarn"),
        ("高级折叠 summary", "#viewSetup details.adv summary"),
        ("确认条 .confirm-bar", "#viewSetup .confirm-bar"),
        ("确认启动 #btnStart", "#btnStart"),
        ("确认条提示 #btnStartHint", "#btnStartHint"),
        ("health 卡 #healthBody", "#healthBody"),
        ("操作边界 kv .kv", "#viewSetup .kv"),
        ("脚注 .foot-note", "#viewSetup .foot-note"),
    ],
    "run": [
        ("运行头 .run-head", "#runHead"),
        ("运行状态胶囊 .status-pill", "#runHead .status-pill"),
        ("运行元信息 .run-meta", "#runHead .run-meta"),
        ("刷新按钮 #runHead .btn", "#runHead .btn"),
        ("四段容器 .stages", "#stages"),
        ("阶段卡 .stage", "#stages .stage"),
        ("阶段头 .stage-head", "#stages .stage-head"),
        ("阶段序号 .stage-idx", "#stages .stage-idx"),
        ("阶段名 .stage-name", "#stages .stage-name"),
        ("阶段进度 .stage-bar", "#stages .stage-bar"),
        ("阶段汇总 .stage-sum", "#stages .stage-sum"),
        ("阶段展开体 .stage-body", "#stages .stage.open .stage-body"),
        ("节点 chip .snode", "#stages .snode"),
        ("节点标记 .snode .sb", "#stages .snode .sb"),
        ("Agent 容器 #agents", "#agents"),
        ("Agent 卡 .agent", "#agents .agent"),
        ("Agent 名称 .agent-name", "#agents .agent-name"),
        ("Agent 角色 .agent-role", "#agents .agent-role"),
        ("Agent 正文 .agent-body", "#agents .agent-body"),
        ("Agent 动作 .agent-action", "#agents .agent-action"),
        ("Agent 卡脚 .agent-foot", "#agents .agent-foot"),
        ("Host 行 .host-row", "#hostRow"),
        ("闸门卡 #gateCard", "#gateCard"),
        ("计数容器 .counts", "#countsBody .counts"),
        ("计数框 .count-box", "#countsBody .count-box"),
        ("计数数字 .count-box .n", "#countsBody .count-box .n"),
        ("阻断项 .blocker", "#blockersBody .blocker"),
        ("严重度标记 .sev", "#blockersBody .sev"),
        ("长任务区 #jobBody", "#jobBody"),
        ("事件折叠 summary", "#eventsSummary"),
        ("事件列表 .ev-list", "#eventList"),
        ("空态卡 #runEmpty", "#runEmpty"),
    ],
    "gate": [
        ("闸门运行头 #gateHead", "#gateHead"),
        ("闸门告警区 #gateAlerts", "#gateAlerts"),
        ("闸门四段 .stages", "#stagesGate"),
        ("闸门材料区 #gateMaterial", "#gateMaterial"),
        ("差异清单项 .diff-item", "#gateMaterial .diff-item"),
        ("差异未决项 .diff-item.unresolved", "#gateMaterial .diff-item.unresolved"),
        ("闸门操作区 #gatePanel", "#gatePanel"),
        ("决策选项 .option", "#gatePanel .option"),
        ("决策选项单选 .radio", "#gatePanel .option .radio"),
        ("actor 输入", "#gatePanel [aria-label=actor]"),
        ("理由输入", "#gatePanel [aria-label='裁决理由']"),
        ("提交按钮 [data-gate-submit]", "#gatePanel [data-gate-submit]"),
        ("闸门错误区 .gate-error", "#gatePanel .gate-error"),
    ],
    "dirpicker": [
        ("目录选择器 #dirPicker", "#dirPicker"),
        ("目录头 .dp-head", "#dirPicker .dp-head"),
        ("上级按钮 #btnDirUp", "#btnDirUp"),
        ("面包屑 .dp-crumb", "#dirCrumb"),
        ("收起按钮 #btnDirClose", "#btnDirClose"),
        ("根列表 .dp-roots", "#dirRoots"),
        ("目录列表 .dp-list", "#dirList"),
        ("目录项 .dp-item", "#dirList .dp-item"),
        ("目录项名 .dp-item b", "#dirList .dp-item b"),
        ("目录脚 .dp-foot", "#dirPicker .dp-foot"),
        ("选择此目录 #btnDirChoose", "#btnDirChoose"),
        ("目录提示 #dirHint", "#dirHint"),
    ],
    "agent": [
        ("Agent 窗口 dialog", "#agentWindow"),
        ("窗口头 .aw-head", "#agentWindow .aw-head"),
        ("窗口标题 h2", "#awTitle"),
        ("窗口状态 chip #awStatus", "#awStatus"),
        ("关闭按钮 #awClose", "#awClose"),
        ("工具条 .aw-toolbar", "#agentWindow .aw-toolbar"),
        ("身份 #awIdentity", "#awIdentity"),
        ("节点 select #awNode", "#awNode"),
        ("尝试 select #awAttempt", "#awAttempt"),
        ("刷新 #awRefresh", "#awRefresh"),
        ("观察区 .aw-observe", "#agentWindow .aw-observe"),
        ("干预区 .aw-intervene", "#agentWindow .aw-intervene"),
        ("区块标题 .aw-section-head h3", "#agentWindow .aw-section-head h3"),
        ("能力事实 #awCapabilities", "#awCapabilities"),
        ("详情折叠 summary", "#agentWindow .aw-detail summary"),
        ("时间线 .aw-timeline", "#awTimeline"),
        ("输入补全 #awMessage", "#awMessage"),
        ("操作者 #awActor", "#awActor"),
        ("补充指令按钮 #awSteer", "#awSteer"),
        ("暂停/恢复按钮 #awPause", "#awPause"),
        ("终止按钮 #awTerminate", "#awTerminate"),
        ("只读说明 .aw-note", "#agentWindow .aw-note"),
        ("动作行 .aw-action-row", "#agentWindow .aw-action-row"),
    ],
    "legacy": [
        ("旧页 header", "header"),
        ("旧页返回入口 .back-workspace", ".back-workspace"),
        ("旧页权威说明 .authority", ".authority"),
        ("旧页面板 .panel", ".panel"),
        ("旧页面板标题 h2", ".panel>h2"),
        ("旧页状态条 .status-strip", ".status-strip"),
        ("旧页按钮 .btn", ".btn"),
        ("旧页主按钮 .btn-primary", ".btn-primary"),
        ("旧页输入框 input[type=text]", "input[type=text]"),
        ("旧页 textarea", "textarea"),
        ("旧页 select", "select"),
        ("旧页折叠 summary", "details>summary"),
        ("旧页日志 .logtail", "pre.logtail"),
        ("旧页 JSON pre", "pre.json"),
        ("旧页徽章 .badge", ".badge"),
        ("旧页 chip", ".chip"),
    ],
}


# --------------------------------------------------------------------------- #
# 采集主体
# --------------------------------------------------------------------------- #
def collect_page_state(page, outdir, width, state, selectors, screenshot_name=None):
    inventory = [measure_labeled(page, label, sel) for label, sel in selectors]
    data = {
        "state": state,
        "width": width,
        "layout": layout_report(page),
        "overflow": overflow_report(page),
        "inventory": inventory,
        "screenshot": None,
    }
    if screenshot_name:
        path = (SCREENS_DIR or (outdir / "screens-before")) / screenshot_name
        shot(page, path)
        data["screenshot"] = str(path)
    return data


def capture_viewports(pw, outdir, static_url, results):
    browser = pw.chromium.launch(
        **({"executable_path": os.environ["LOOP_BROWSER_EXECUTABLE"]}
           if os.environ.get("LOOP_BROWSER_EXECUTABLE") else {}))
    version = browser.version
    results["meta"]["chrome_version"] = version
    for width in VIEWPORTS:
        context = browser.new_context(viewport={"width": width, "height": HEIGHT},
                                      device_scale_factor=1, reduced_motion="no-preference")
        page = context.new_page()
        page.clock.install()
        api = MockApi(page)
        # 给 S0/配置页需要的只读端点补上固定响应
        page.goto(static_url)
        page.wait_for_selector(".run-item", timeout=10000)
        page.evaluate(_JS_HELPERS)
        # 记录全局环境事实（同一页即可）
        results["env"].setdefault("views", {})[str(width)] = page.evaluate(r"""
() => ({
  innerWidth, innerHeight, outerWidth, outerHeight,
  devicePixelRatio: window.devicePixelRatio,
  visualViewport: window.visualViewport ? {scale: window.visualViewport.scale,
    width: window.visualViewport.width, height: window.visualViewport.height} : null,
  screen: {width: screen.width, height: screen.height, availWidth: screen.availWidth},
  ua: navigator.userAgent, platform: navigator.platform, language: navigator.language,
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  bodyFont: getComputedStyle(document.body).fontFamily,
  bodyFontSize: getComputedStyle(document.body).fontSize,
  monoFont: (() => { const el = document.querySelector('.mono');
    return el ? getComputedStyle(el).fontFamily : null; })(),
  fontsCheck: {inter: document.fonts.check('14px Inter'),
               noto: document.fonts.check('14px "Noto Sans SC"'),
               mono: document.fonts.check('12px ui-monospace')},
  colorScheme: matchMedia('(prefers-color-scheme: dark)').matches,
  reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
  cookieEnabled: navigator.cookieEnabled,
  hasHorizontalScrollbar: document.documentElement.scrollWidth > innerWidth
})
""")

        # --- 空态（未选择运行时的运行视图）------------------------------ #
        page.locator("#segRun").click()
        wait_js(page, "() => document.querySelector('#runEmpty') && "
                      "getComputedStyle(document.querySelector('#runEmpty')).display !== 'none'",
                "空态可见")
        results["pages"].append(collect_page_state(
            page, outdir, width, "run-empty",
            COMMON + [("空态卡 #runEmpty", "#runEmpty"),
                      ("空态标题 .empty-title", "#runEmpty .empty-title"),
                      ("空态正文 .empty .muted", "#runEmpty .muted")],
            "%d-empty.png" % width))

        # --- S0 --------------------------------------------------------- #
        page.locator("#segS0").click()
        page.wait_for_timeout(120)
        results["pages"].append(collect_page_state(
            page, outdir, width, "s0", COMMON + VIEW_INVENTORY["s0"],
            "%d-s0-script.png" % width))
        results["focus"].append({"state": "s0", "width": width, "steps": focus_walk(page)})

        # --- 配置 + 目录浏览器 ----------------------------------------- #
        page.locator("#segSetup").click()
        page.wait_for_timeout(120)
        page.locator("#btnRefreshBaselines").click()
        wait_js(page, "() => document.querySelectorAll('#setupBaseline option').length > 1",
                "基线下拉已填充")
        results["pages"].append(collect_page_state(
            page, outdir, width, "setup", COMMON + VIEW_INVENTORY["setup"], None))
        results["focus"].append({"state": "setup", "width": width, "steps": focus_walk(page)})
        page.locator("#btnBaselineBrowse").click()
        page.wait_for_timeout(150)
        results["pages"].append(collect_page_state(
            page, outdir, width, "dirpicker-baseline",
            COMMON + VIEW_INVENTORY["dirpicker"], "%d-dirpicker-baseline.png" % width))
        page.locator("#btnDirClose").click()
        page.wait_for_timeout(100)
        page.locator("#btnProjectBrowse").click()
        wait_js(page, "() => document.querySelectorAll('#dirList .dp-item').length > 0",
                "项目目录浏览器已加载")
        results["pages"].append(collect_page_state(
            page, outdir, width, "dirpicker-project",
            COMMON + VIEW_INVENTORY["dirpicker"], "%d-dirpicker-project.png" % width))
        results["focus"].append({"state": "dirpicker-project", "width": width,
                                 "steps": focus_walk(page)})
        page.locator("#btnDirClose").click()
        page.wait_for_timeout(100)

        # --- 运行监控（受控数据）--------------------------------------- #
        populated_view(api.views["A"])
        select(page, "A")
        wait_js(page, "() => document.querySelector('#runHead').textContent.includes('v1.2-stable')",
                "运行头已渲染")
        page.locator("#segRun").click()
        page.wait_for_timeout(120)
        results["pages"].append(collect_page_state(
            page, outdir, width, "run", COMMON + VIEW_INVENTORY["run"], None))
        results["focus"].append({"state": "run", "width": width, "steps": focus_walk(page)})

        # 运行失败态（error + notes）
        failed = json.loads(json.dumps(api.views["A"]))
        failed.update(status="failed",
                      error="N7 编译失败：uvs 退出码 1（三库冒烟 2 error）",
                      notes=["N7 日志尾部已截断保存", "需要人工确认 RTL 接口改动"])
        api.views["A"] = failed
        tick(page)
        wait_js(page, "() => document.querySelector('#runAlerts') && "
                      "document.querySelector('#runAlerts').textContent.includes('运行失败')",
                "运行失败提示可见")
        results["pages"].append(collect_page_state(
            page, outdir, width, "run-failed", COMMON + VIEW_INVENTORY["run"],
            "%d-run-failed.png" % width))
        api.views["A"] = populated_view(base_view("A"))

        # 闸门视图 + 被拒态
        select(page, "A")
        page.wait_for_timeout(120)
        page.locator("#segGate").click()
        wait_js(page, "() => document.querySelector('#gatePanel') && "
                      "document.querySelector('#gatePanel [aria-label=\"actor\"]')",
                "闸门表单可见")
        results["pages"].append(collect_page_state(
            page, outdir, width, "gate", COMMON + VIEW_INVENTORY["gate"], None))
        results["focus"].append({"state": "gate", "width": width, "steps": focus_walk(page)})
        page.locator('#gatePanel input[value="confirmed"]').check()
        page.locator('#gatePanel [aria-label="actor"]').fill("human:reviewer")
        page.locator('#gatePanel [aria-label="裁决理由"]').fill("已逐条核对差异与证据")
        page.locator("#gatePanel [data-gate-submit]").evaluate(
            "el => { el.click(); el.click(); }")
        page.wait_for_timeout(150)
        paused = list(api.posts)
        api.release(page, {"detail": {"error": "refused",
                                      "blockers": [{"code": "I4",
                                                    "message": "闸门材料未确认"}],
                                      "note": "gate unchanged；中断未被消耗"}}, 403)
        wait_js(page, "() => document.querySelector('#gatePanel .gate-error') && "
                      "document.querySelector('#gatePanel .gate-error').innerText.length > 0",
                "闸门拒绝提示可见")
        results["pages"].append(collect_page_state(
            page, outdir, width, "gate-rejected", COMMON + VIEW_INVENTORY["gate"],
            "%d-gate-rejected.png" % width))
        results.setdefault("posts", []).append({"width": width, "posts": paused})

        # Agent 工作窗口（先回到运行监控视图，角色卡在 #viewRun 内）
        page.locator("#segRun").click()
        page.wait_for_timeout(150)
        page.route("**/api/runs/*/agents/**", lambda route: route.fulfill(json=agent_view()))
        page.locator("#agents [data-agent-node=\"N3\"]").click()
        wait_js(page, "() => document.querySelector('#agentWindow') && "
                      "document.querySelector('#agentWindow').open",
                "Agent 窗口已打开")
        page.wait_for_timeout(200)
        results["pages"].append(collect_page_state(
            page, outdir, width, "agent", COMMON + VIEW_INVENTORY["agent"], None))
        results["focus"].append({"state": "agent", "width": width,
                                 "steps": focus_walk(page)})
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)

        # 旧页
        page.goto(static_url + "/legacy.html")
        page.wait_for_timeout(200)
        page.evaluate(_JS_HELPERS)
        page.wait_for_timeout(150)
        results["pages"].append(collect_page_state(
            page, outdir, width, "legacy", COMMON + VIEW_INVENTORY["legacy"], None))
        results["focus"].append({"state": "legacy", "width": width,
                                 "steps": focus_walk(page)})

        if api.page_errors:
            results["page_errors"].extend(
                {"width": width, "error": err} for err in api.page_errors)
        context.close()
    return version


def capture_async_states(pw, outdir, static_url, results):
    """空/加载/首次失败/陈旧失败：每次用独立页面，避免选择代次互相干扰。"""
    executable = os.environ.get("LOOP_BROWSER_EXECUTABLE")
    browser = pw.chromium.launch(**({"executable_path": executable} if executable else {}))
    for width in VIEWPORTS:
        # 加载态 + 首次失败态
        context = browser.new_context(viewport={"width": width, "height": HEIGHT},
                                      device_scale_factor=1)
        page = context.new_page()
        page.clock.install()
        api = MockApi(page)
        page.goto(static_url)
        page.wait_for_selector(".run-item", timeout=10000)
        page.evaluate(_JS_HELPERS)
        page.locator("#segRun").click()
        api.hold = lambda path: path == "/api/runs/A"
        select(page, "A")
        wait_js(page, "() => document.querySelector('#runHead') && "
                      "document.querySelector('#runHead').textContent.includes('加载中')",
                "加载态出现")
        results["pages"].append(collect_page_state(
            page, outdir, width, "loading", COMMON, "%d-loading.png" % width))
        wait_js(page, "() => document.querySelector('#runRetry') === null", "重试入口尚未出现")
        api.release(page, {"detail": {"error": "证据读取失败：" +
                                      "/simulation/long-project/" * 12}}, 503)
        wait_js(page, "() => document.querySelector('#runHead') && "
                      "document.querySelector('#runHead').textContent.includes('读取失败')",
                "首次失败态出现")
        results["pages"].append(collect_page_state(
            page, outdir, width, "first-error", COMMON, "%d-error.png" % width))
        context.close()

        # 陈旧失败（已有成功数据 → 轮询失败）
        context = browser.new_context(viewport={"width": width, "height": HEIGHT},
                                      device_scale_factor=1)
        page = context.new_page()
        page.clock.install()
        api = MockApi(page)
        page.goto(static_url)
        page.wait_for_selector(".run-item", timeout=10000)
        page.evaluate(_JS_HELPERS)
        select(page, "A")
        wait_js(page, "() => document.querySelector('#runHead') && "
                      "document.querySelector('#runHead').textContent.includes('A-baseline')",
                "首次读取成功")
        page.locator("#segRun").click()
        api.hold = lambda path: path == "/api/runs/A"
        tick(page)
        api.release(page, {"detail": {"error": "轮询超时"}}, 503)
        wait_js(page, "() => document.querySelector('#runAlerts') && "
                      "document.querySelector('#runAlerts').textContent.includes('数据已过期')",
                "陈旧失败态出现")
        results["pages"].append(collect_page_state(
            page, outdir, width, "stale-error", COMMON, "%d-stale.png" % width))
        context.close()
    browser.close()


def capture_interactive_states(pw, outdir, static_url, results):
    """交互态：hover / focus-visible / disabled / 告警 / 模态 / toast / 旧页。"""
    executable = os.environ.get("LOOP_BROWSER_EXECUTABLE")
    browser = pw.chromium.launch(**({"executable_path": executable} if executable else {}))
    width = 1440
    context = browser.new_context(viewport={"width": width, "height": HEIGHT},
                                  device_scale_factor=1)
    page = context.new_page()
    api = MockApi(page)
    page.goto(static_url)
    page.wait_for_selector(".run-item", timeout=10000)
    page.evaluate(_JS_HELPERS)
    states = results["states"]

    def rec(label, selector, note, props=None):
        out = measure_labeled(page, label, selector, props)
        out["note"] = note
        out["width"] = width
        states.append(out)
        return out

    def rec_active(label, note):
        info = page.evaluate(_JS_ACTIVE)
        info["label"] = label
        info["note"] = note
        info["width"] = width
        states.append(info)
        return info

    def tab_to(target_id, max_steps=80):
        page.evaluate("""() => { if (document.activeElement) document.activeElement.blur();
          document.body.setAttribute('tabindex','-1'); document.body.focus(); }""")
        for _ in range(max_steps):
            page.keyboard.press("Tab")
            if page.evaluate("id => document.activeElement && document.activeElement.id === id",
                             target_id):
                return True
        return False

    # --- 配置页：按钮 / 输入 / chip / 禁用 / 告警 ---------------------- #
    page.locator("#segSetup").click()
    page.locator("#btnRefreshBaselines").click()
    wait_js(page, "() => document.querySelectorAll('#setupBaseline option').length > 1",
            "基线下拉已填充")
    rec("按钮 .btn 默认", "#btnBaselineBrowse", "配置页「浏览…」按钮默认态")
    page.hover("#btnBaselineBrowse")
    page.wait_for_timeout(400)
    rec("按钮 .btn hover", "#btnBaselineBrowse", "hover 后立即读计算样式（等 400 ms 过渡）")
    page.mouse.move(0, 0)
    page.wait_for_timeout(200)
    assert tab_to("btnBaselineBrowse"), "未能在 80 次 Tab 内聚焦 #btnBaselineBrowse"
    rec_active("按钮 .btn :focus-visible", "键盘 Tab 聚焦后立即读 outline")
    rec("主按钮 .btn-primary 默认", "#btnStart", "校验未通过 → disabled 同时是主按钮默认")
    page.select_option("#setupMode", "real")
    page.wait_for_timeout(150)
    rec("告警 .alert.warn", "#realWarn", "选择 real 模式后的风险告警")
    page.select_option("#setupMode", "drill")
    rec("输入框 .input 默认", "#setupBaseline", "基线 select（.input）默认")
    page.focus("#setupBaseline")
    page.wait_for_timeout(120)
    rec("输入框 .input focus", "#setupBaseline", "focus（脚本聚焦，:focus-visible 不成立）")
    rec("chip .chip", "#setupBaselineChip", "基线 chip")
    rec("chip 警告 .chip.warn", "#viewSetup .chips .chip.warn", "冻结面/单槽提示 chip")
    rec("字段标签 .field-label", "#viewSetup .field-label", "选项行标签")
    # toast：手动刷新基线成功 → toast
    page.locator("#btnRefreshBaselines").click()
    wait_js(page, "() => document.querySelector('#toast').classList.contains('show')",
            "toast 出现")
    rec("toast #toast.show", "#toast", "刷新基线成功提示（真实 UI 路径触发）", 
        ["font-size", "font-family", "color", "background-color", "border-radius",
         "padding-top", "padding-left", "box-shadow", "opacity", "transition-duration",
         "position", "right", "bottom", "z-index"])

    # --- 运行页：run-item / 阶段 / Agent 卡 / 计数 / 阻断 --------------- #
    populated_view(api.views["A"])
    select(page, "A")
    wait_js(page, "() => document.querySelector('#runHead').textContent.includes('v1.2-stable')",
            "运行头已渲染")
    page.locator("#segRun").click()
    page.wait_for_timeout(150)
    rec("run-item 默认", ".run-item", "未选中的运行记录")
    rec("run-item 选中", ".run-item.active", "当前选中运行记录")
    page.hover(".run-item:not(.active)")
    page.wait_for_timeout(400)
    rec("run-item hover", ".run-item:not(.active)", "hover 400 ms 后")
    page.mouse.move(0, 0)
    rec("阶段卡 .stage", "#stages .stage", "第一个阶段卡（完成态）")
    rec("阶段头 .stage-head", "#stages .stage .stage-head", "阶段头")
    rec("节点 chip .snode", "#stages .snode", "阶段内节点 chip")
    rec("Agent 卡 .agent", "#agents .agent", "第一张角色卡")
    rec("计数框 .count-box", "#countsBody .count-box", "双口径计数框")
    rec("阻断项 .blocker", "#blockersBody .blocker", "阻断项行")
    rec("严重度 .sev", "#blockersBody .sev", "阻断项严重度标记")
    rec("事件折叠 summary", "#eventsSummary", "事件流折叠头")
    # 运行失败告警
    failed = json.loads(json.dumps(api.views["A"]))
    failed.update(status="failed", error="N7 编译失败：uvs 退出码 1",
                  notes=["需要人工确认 RTL 接口改动"])
    api.views["A"] = failed
    tick(page)
    wait_js(page, "() => document.querySelector('#runAlerts') && "
                  "document.querySelector('#runAlerts').textContent.includes('运行失败')",
            "运行失败告警出现")
    rec("告警 .alert.bad", "#runAlerts .alert.bad", "运行失败 error 原文告警")
    api.views["A"] = populated_view(base_view("A"))
    select(page, "A")
    page.wait_for_timeout(150)

    # --- 闸门页：选项 / 差异项 / 主按钮 / 拒绝告警 ---------------------- #
    page.locator("#segGate").click()
    wait_js(page, "() => document.querySelector('#gatePanel [aria-label=\"actor\"]')",
            "闸门表单可见")
    page.wait_for_timeout(100)
    rec("决策选项 .option", "#gatePanel .option", "决策单选选项")
    rec("差异项 .diff-item", "#gateMaterial .diff-item", "N2 差异清单条目")
    rec("差异未决项 .diff-item.unresolved", "#gateMaterial .diff-item.unresolved",
        "未决差异条目（琥珀边）")
    rec("闸门主按钮 [data-gate-submit]", "#gatePanel [data-gate-submit]",
        "提交按钮默认（禁用，因决策未选）")
    rec("闸门表单 .input", "#gatePanel [aria-label='裁决理由']", "理由输入默认")
    page.locator('#gatePanel input[value="confirmed"]').check()
    page.locator('#gatePanel [aria-label="actor"]').fill("human:reviewer")
    page.locator('#gatePanel [aria-label="裁决理由"]').fill("已逐条核对")
    rec("闸门主按钮 可用", "#gatePanel [data-gate-submit]", "填完后的可提交按钮")
    page.locator("#gatePanel [data-gate-submit]").evaluate("el => el.click()")
    page.wait_for_timeout(120)
    api.release(page, {"detail": {"error": "refused",
                                  "blockers": [{"code": "I4", "message": "闸门材料未确认"}],
                                  "note": "gate unchanged"}}, 403)
    wait_js(page, "() => document.querySelector('#gatePanel .gate-error') && "
                  "document.querySelector('#gatePanel .gate-error').innerText.length > 0",
            "拒绝告警可见")
    rec("闸门拒绝 .gate-error", "#gatePanel .gate-error", "服务端 403 拒绝原文")

    # --- Agent 窗口（模态） ------------------------------------------- #
    page.locator("#segRun").click()
    page.route("**/api/runs/*/agents/**", lambda route: route.fulfill(json=agent_view()))
    page.wait_for_timeout(120)
    page.locator("#agents [data-agent-node=\"N3\"]").click()
    wait_js(page, "() => document.querySelector('#agentWindow') && "
                  "document.querySelector('#agentWindow').open", "Agent 窗口已打开")
    page.wait_for_timeout(200)
    rec("Agent 窗口 dialog", "#agentWindow", "模态工作窗口")
    rec("窗口头 .aw-head", "#agentWindow .aw-head", "窗口头")
    rec("窗口标题 h2", "#awTitle", "窗口标题")
    rec("窗口状态 chip", "#awStatus", "窗口状态 chip")
    rec("窗口工具条", "#agentWindow .aw-toolbar", "窗口工具条")
    rec("观察区 .aw-observe", "#agentWindow .aw-observe", "左列观察区")
    rec("干预区 .aw-intervene", "#agentWindow .aw-intervene", "右列干预区")
    rec("区块标题 h3", "#agentWindow .aw-section-head h3", "区块标题")
    rec("时间线 .aw-timeline", "#awTimeline", "运行时间线")
    rec("补充指令 textarea", "#awMessage", "多行输入")
    rec("主按钮 #awSteer", "#awSteer", "补充指令并重跑（可用态）")
    # 目录浏览器（项目）
    page.keyboard.press("Escape")
    page.locator("#segSetup").click()
    page.wait_for_timeout(100)
    page.locator("#btnProjectBrowse").click()
    wait_js(page, "() => document.querySelectorAll('#dirList .dp-item').length > 0",
            "项目目录浏览器已加载")
    rec("目录选择器 .dirpicker", "#dirPicker", "目录浏览器容器")
    rec("目录头 .dp-head", "#dirPicker .dp-head", "目录头")
    rec("目录项 .dp-item", "#dirList .dp-item", "可点击目录项")
    rec("目录项名 .dp-item b", "#dirList .dp-item b", "目录名")
    rec("目录选择主按钮 #btnDirChoose", "#btnDirChoose", "选择此目录（未选中时禁用）")
    rec("目录面包屑 .dp-crumb", "#dirCrumb", "面包屑")
    rec("目录根 .dp-roots button", "#dirRoots button", "允许根按钮（可能存在）")

    # --- 旧页 --------------------------------------------------------- #
    page.goto(static_url + "/legacy.html")
    page.wait_for_timeout(200)
    page.evaluate(_JS_HELPERS)
    page.wait_for_timeout(150)
    rec("旧页面板 .panel", ".panel", "旧界面面板")
    rec("旧页面板标题", ".panel>h2", "面板标题")
    rec("旧页按钮 .btn", ".btn", "旧界面按钮")
    rec("旧页主按钮 .btn-primary", ".btn-primary", "旧界面主按钮")
    rec("旧页输入 input", "input[type=text]", "旧界面文本输入")
    rec("旧页 textarea", "textarea", "旧界面多行输入")
    rec("旧页 select", "select", "旧界面选择框")
    rec("旧页日志 pre.logtail", "pre.logtail", "日志尾部等宽块")
    rec("旧页折叠 summary", "details>summary", "折叠标题")
    rec("旧页徽章 .badge", ".badge", "状态徽章")
    rec("旧页返回入口 .back-workspace", ".back-workspace", "返回主工作台链接")

    results["page_errors"].extend(
        {"width": width, "error": err} for err in api.page_errors)
    context.close()
    browser.close()


def capture_media(pw, static_url, results):
    executable = os.environ.get("LOOP_BROWSER_EXECUTABLE")
    browser = pw.chromium.launch(**({"executable_path": executable} if executable else {}))
    per_width = {}
    for width in VIEWPORTS:
        context = browser.new_context(viewport={"width": width, "height": HEIGHT},
                                      device_scale_factor=1)
        page = context.new_page()
        page.goto(static_url)
        page.wait_for_timeout(150)
        js_collect = r"""
() => {
  const out = [];
  for (const sheet of document.styleSheets) {
    let rulesList;
    try { rulesList = sheet.cssRules; } catch (e) {
      out.push({href: sheet.href, error: String(e)}); continue;
    }
    const walk = (list, depth) => {
      for (const rule of list) {
        if (rule.type === CSSRule.MEDIA_RULE) {
          out.push({href: sheet.href, condition: rule.conditionText,
                    mediaText: rule.media.mediaText, depth: depth,
                    innerRuleCount: rule.cssRules.length,
                    matches: matchMedia(rule.conditionText).matches});
          walk(rule.cssRules, depth + 1);
        }
      }
    };
    walk(rulesList, 0);
  }
  return out;
}
"""
        rules = page.evaluate(js_collect)
        page.goto(static_url + "/legacy.html")
        page.wait_for_timeout(150)
        rules += page.evaluate(js_collect)
        entries = []
        seen = {}
        for rule in rules:
            if not rule.get("condition"):
                continue
            sheet = Path(rule["href"]).name if rule.get("href") else "(inline style)"
            key = (sheet, rule["condition"])
            seen[key] = seen.get(key, 0) + 1
            entries.append({
                "sheet": sheet, "condition": rule["condition"],
                "occurrence": seen[key], "innerRuleCount": rule["innerRuleCount"],
                "matches": {str(width): rule["matches"]},
            })
        per_width[width] = entries
        context.close()
    browser.close()

    # 以 1280 的 CSSOM 顺序为基准，按 (sheet, condition, 同条件第几次出现) 合并三视口命中结果
    merged = []
    index = {}
    for entry in per_width[VIEWPORTS[0]]:
        key = (entry["sheet"], entry["condition"], entry["occurrence"])
        index[key] = len(merged)
        merged.append(dict(entry))
    for width in VIEWPORTS[1:]:
        for entry in per_width[width]:
            key = (entry["sheet"], entry["condition"], entry["occurrence"])
            if key in index:
                merged[index[key]]["matches"].update(entry["matches"])
            else:
                index[key] = len(merged)
                merged.append(dict(entry))

    # 把 CSSOM 顺序映射回源文件行号（只读解析 loop/web/*.css）
    line_index = {}
    for name in ("tokens.css", "app.css", "legacy.css"):
        path = WEB / name
        lines = path.read_text(encoding="utf-8").splitlines()
        hits = []
        for number, line in enumerate(lines, 1):
            for match in re.finditer(r"@media[^{]*", line):
                hits.append((number, match.group(0).strip()))
        line_index[name] = hits
    order_per_sheet = {}
    for entry in merged:
        sheet = entry["sheet"]
        order = order_per_sheet.get(sheet, 0)
        hits = line_index.get(sheet, [])
        entry["sourceLine"] = hits[order][0] if order < len(hits) else None
        entry["sourceText"] = hits[order][1] if order < len(hits) else None
        entry["sheetOccurrence"] = order + 1
        order_per_sheet[sheet] = order + 1
    results["media"] = {
        "occurrences": merged,
        "unique_conditions": len({(e["sheet"], e["condition"]) for e in merged}),
        "source_counts": {name: len(hits) for name, hits in line_index.items()},
    }


def capture_narrow(pw, static_url, results):
    """窄屏只做溢出检查（F14 计划：390/768 不新增移动产品目标）。"""
    executable = os.environ.get("LOOP_BROWSER_EXECUTABLE")
    browser = pw.chromium.launch(**({"executable_path": executable} if executable else {}))
    for width in NARROW:
        context = browser.new_context(viewport={"width": width, "height": 844},
                                      device_scale_factor=1)
        page = context.new_page()
        page.clock.install()
        api = MockApi(page)
        page.goto(static_url)
        page.wait_for_selector(".run-item", timeout=10000)
        populated_view(api.views["A"])
        for state, action in (
                ("s0", lambda: page.locator("#segS0").click()),
                ("setup", lambda: page.locator("#segSetup").click()),
                ("run", lambda: (select(page, "A"), page.locator("#segRun").click())),
                ("gate", lambda: page.locator("#segGate").click()),
        ):
            action()
            page.wait_for_timeout(180)
            results["narrow"].append({"width": width, "state": state,
                                      "overflow": overflow_report(page)})
        # Agent 窗口
        page.locator("#segRun").click()
        page.route("**/api/runs/*/agents/**", lambda route: route.fulfill(json=agent_view()))
        page.wait_for_timeout(100)
        page.locator('#agents [data-agent-node="N3"]').click()
        wait_js(page, "() => document.querySelector('#agentWindow') && "
                      "document.querySelector('#agentWindow').open", "窄屏 Agent 窗口")
        results["narrow"].append({"width": width, "state": "agent",
                                  "overflow": overflow_report(page)})
        context.close()
    browser.close()


def capture_reduced_motion(pw, static_url, results):
    executable = os.environ.get("LOOP_BROWSER_EXECUTABLE")
    browser = pw.chromium.launch(**({"executable_path": executable} if executable else {}))
    out = {}
    for label, preference in (("no-preference", "no-preference"), ("reduce", "reduce")):
        context = browser.new_context(viewport={"width": 1440, "height": HEIGHT},
                                      device_scale_factor=1, reduced_motion=preference)
        page = context.new_page()
        page.goto(static_url)
        page.wait_for_timeout(150)
        out[label] = page.evaluate(r"""
() => {
  const q = s => document.querySelector(s);
  const cs = el => el ? getComputedStyle(el) : null;
  return {
    mediaMatches: matchMedia('(prefers-reduced-motion: reduce)').matches,
    buttonTransitionDuration: cs(q('#btnNew')) ? cs(q('#btnNew')).transitionDuration : null,
    spinnerAnimation: (() => { const el = document.createElement('span');
      el.className = 'spinner'; document.body.appendChild(el);
      const v = getComputedStyle(el).animationName + ' ' +
                getComputedStyle(el).animationDuration;
      el.remove(); return v; })(),
    htmlScrollBehavior: cs(document.documentElement).scrollBehavior,
    bodyScrollBehavior: cs(document.body).scrollBehavior
  };
}
""")
        context.close()
    browser.close()
    results["reduced_motion"] = out


# --------------------------------------------------------------------------- #
# Markdown 渲染
# --------------------------------------------------------------------------- #
def png_size(path):
    with path.open("rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def md5(path):
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def md_escape(text):
    return str(text).replace("|", "\\|")


def short_style(style, keys):
    return " · ".join("%s=%s" % (key.replace("-", ""), style.get(key, "—")) for key in keys)


def render_markdown(summary, outdir):
    meta = summary["meta"]
    lines = []
    add = lines.append
    add("# F14-a · 改前样式基线（style inventory）")
    add("")
    add("日期：%s（Asia/Shanghai）。采集时仓库 `HEAD=%s`，分支 `%s`，工作树脏文件：`%s`。"
        % (meta["collected_at"], meta["head"], meta["branch"],
           "、".join(meta["dirty"]) if meta["dirty"] else "无"))
    add("")
    add("本文件是 **F14-b 样式收敛的改前对照基线**，由只读采集脚本 "
        "[collect_f14a.py](collect_f14a.py) 与现有 `loop/tests/browser` 生成。"
        "全部页面数据来自 Playwright 受控 API 替身，不是真实模型/内网仿真结果。"
        "同一执行者分阶段采集，不是独立视觉评审；**不声称视觉验收通过**。")
    add("")
    add("## 0 采集环境")
    add("")
    add("| 项 | 值 |")
    add("|---|---|")
    add("| 浏览器 | Chrome `%s`（`%s`） |" % (meta["chrome_version"], meta["browser_executable"]))
    add("| Playwright | `%s` |" % meta["playwright_version"])
    add("| Python | `%s`（`loop/.venv`） |" % meta["python"])
    add("| 操作系统 | `%s` |" % meta["platform"])
    add("| 视口（主验收） | 1280×1000 / 1440×1000 / 1920×1000，`devicePixelRatio=1`、"
        "`visualViewport.scale=1`（**100% 缩放**） |")
    add("| 窄屏（仅溢出检查） | 390×844 / 768×844 |")
    add("| 页面语言 / 时区 | `%s` / `%s` |" % (meta["language"], meta["timezone"]))
    add("| prefers-reduced-motion 对照 | no-preference 与 reduce 各跑一次（见 §7） |")
    add("| 采集命令 | 见 [commands.md](commands.md) |")
    add("")
    views_env = summary.get("env", {}).get("views", {})
    env0 = views_env.get("1280") or (next(iter(views_env.values())) if views_env else None)
    if not env0:
        add("（环境事实采集失败，见 §8；本节缺字体/UA 原始值）")
        add("")
        add("## 1 截图索引（screens-before/）")
        return "\n".join(lines) + "\n"
    add("正文/等宽字体计算值（1280 视口，三视口一致）：")
    add("")
    add("```text")
    add("body font-family: %s" % env0["bodyFont"])
    add("body font-size  : %s" % env0["bodyFontSize"])
    add("mono font-family: %s" % env0["monoFont"])
    add("document.fonts.check('14px Inter')         = %s" % env0["fontsCheck"]["inter"])
    add("document.fonts.check('14px \"Noto Sans SC\"') = %s" % env0["fontsCheck"]["noto"])
    add("document.fonts.check('12px ui-monospace')  = %s" % env0["fontsCheck"]["mono"])
    add("```")
    add("")
    add("> 字体族声明同一份 `--font-sans`/`--font-mono` 令牌，但 `app.css` 多处直接写死"
        "系统字体栈（body、`.mono`、`.stage-range` 等），令牌与硬编码并存，属 F14-b 的收敛对象；"
        "本文件只记录事实。")
    add("")

    # 截图索引
    add("## 1 截图索引（%s/）" % Path(SCREENS_DIR).name if SCREENS_DIR else "## 1 截图索引")
    add("")
    add("| 文件 | 像素 | 状态 | 来源 | MD5 |")
    add("|---|---|---|---|---|")
    for item in summary["screenshots"]:
        path = Path(item["path"])
        size = png_size(path)
        rel = os.path.relpath(path, outdir).replace(os.sep, "/")
        add("| [%s](%s) | %s×%s | %s | %s | `%s` |" % (
            path.name, rel,
            size[0] if size else "?", size[1] if size else "?",
            md_escape(item["state"]), md_escape(item["source"]),
            md5(path) if path.exists() else "missing"))
    add("")
    add("> `loop/tests/browser` 的 `capture()` 在 `LOOP_VISUAL_ARTIFACTS` 下自动落图；"
        "空/加载/失败、目录浏览器、闸门拒绝、失败运行等补充状态由采集脚本落图。"
        "两者都是 `page.screenshot(full_page=True)`（`*-agent` 为视口内截图），未裁切。")
    add("")

    # 断点
    add("## 2 媒体查询与断点生效矩阵")
    add("")
    add("| # | 源文件:行 | 条件 | 内部规则数 | 1280 | 1440 | 1920 |")
    add("|---|---|---|---|---|---|---|")
    for number, rule in enumerate(summary["media"]["occurrences"], 1):
        marks = " | ".join("✅ 命中" if rule["matches"].get(str(w)) else "—"
                           for w in VIEWPORTS)
        add("| %d | `%s:%s` | `%s` | %s | %s |" % (
            number, rule["sheet"], rule.get("sourceLine") or "?", rule["condition"],
            rule.get("innerRuleCount"), marks))
    add("")
    counts = summary["media"]["source_counts"]
    add("源码 `@media` 出现次数（只读解析 `loop/web/*.css`）：`tokens.css=%d`、`app.css=%d`、"
        "`legacy.css=%d`，合计 %d 次；另有 `legacy.html` 内联 `<style>` 2 条"
        "（`max-width:1080px`、`max-width:760px`）。CSSOM 采集到 %d 次出现、%d 个不同条件；"
        "差额即同条件重复（`app.css` 的 `max-width:760px` 与 "
        "`prefers-reduced-motion:reduce` 各出现两次）。行号只对链式样式表有效，"
        "内联样式记为 `(inline style)`。" % (
            counts["tokens.css"], counts["app.css"], counts["legacy.css"],
            counts["tokens.css"] + counts["app.css"] + counts["legacy.css"],
            len(summary["media"]["occurrences"]),
            summary["media"]["unique_conditions"]))
    add("")
    add("> 观察（事实，不是结论）：`760/761`、`1100/1101`、`1180/1200/1390/1550/1600` "
        "构成重叠与交界；两份 `max-width:760px` 与两份 `prefers-reduced-motion:reduce` "
        "内容不同但条件相同。F14-b 合并/收敛时必须逐条核对交界宽度 ±1px。")
    add("")

    # 版面几何
    add("## 3 版面几何（三视口）")
    add("")
    add("| 状态 | 视口 | 文档 scrollWidth | header | 侧栏宽 | 主区宽 | main padding | shell 方向 | .grid2 | .run-grid | #agents |")
    add("|---|---|---|---|---|---|---|---|---|---|---|")
    for page_data in summary["pages"]:
        layout = page_data["layout"]
        grids = {g["selector"]: g for g in layout["grids"]}

        def col(sel):
            entry = grids.get(sel, {})
            return "—" if entry.get("missing") else (entry.get("columns") or "—")

        cells = [
            md_escape(page_data["state"]),
            "%s×%s" % (page_data["width"], layout["innerHeight"]),
            str(layout["documentScrollWidth"]),
            "%s×%s" % (layout["header"]["w"] if layout["header"] else "—",
                       layout["header"]["h"] if layout["header"] else "—"),
            str(layout["sidebar"]["w"]) if layout["sidebar"] else "—",
            str(layout["main"]["w"]) if layout["main"] else "—",
            "`%s`" % (layout["mainPadding"] or "—"),
            "%s / %s" % (layout["shellDisplay"] or "—", layout["shellFlexDirection"] or "—"),
            col(".grid2"), col(".run-grid"), col("#agents"),
        ]
        add("| " + " | ".join(cells) + " |")
    add("")

    # 关键元素
    common_selectors = {sel for _, sel in COMMON}
    main_states = ("s0", "setup", "run", "gate", "dirpicker-project", "agent", "legacy")

    def render_rows(items, state_name):
        add("| 元素 | 选择器 | 字号/行高/字重 | 前景 / 背景 | 边框 / 圆角 | padding（上/左） | margin（上/左） | 盒尺寸 |")
        add("|---|---|---|---|---|---|---|---|")
        for item in items:
            if item.get("missing"):
                add("| %s | `%s` | — | — | — | — | — | **选择器未命中**（%s） |" % (
                    md_escape(item["label"]), md_escape(item["selector"]),
                    md_escape(state_name)))
                continue
            style = item["style"]
            add("| %s | `%s` | %s / %s / %s | `%s` / `%s` | %s `%s` · %s | %s | %s | %s×%s |" % (
                md_escape(item["label"]), md_escape(item["selector"]),
                style["font-size"], style["line-height"], style["font-weight"],
                style["color"], style["background-color"],
                style["border-top-width"], style["border-top-color"],
                style["border-radius"],
                style["padding-top"] + "/" + style["padding-left"],
                style["margin-top"] + "/" + style["margin-left"],
                item["rect"]["w"], item["rect"]["h"]))
        add("")

    add("## 4 关键元素计算样式（每视口）")
    add("")
    add("属性缩写：字号/行高/字重 · 前景/背景 · 边框（上宽 上色）· 圆角 · padding · margin · 盒尺寸。"
        "完整属性集（含 `border-*`、`outline-*`、`transition-*`、`overflow`、`gap`、"
        "`letter-spacing`、`box-shadow`）在 [raw/summary.json](raw/summary.json) 的 "
        "`pages[].inventory[].style`；除下表的 7 个状态外，空/加载/首次失败/陈旧失败/"
        "运行失败/闸门被拒/基线目录浏览器也都在 raw 数据里，未逐行复制到本文件。")
    add("")
    for width in VIEWPORTS:
        add("### %d×%d" % (width, HEIGHT))
        add("")
        by_state = {page_data["state"]: page_data for page_data in summary["pages"]
                    if page_data["width"] == width}
        s0_page = by_state.get("s0")
        add("#### 全局框架（所有页面共用，样本取 S0 页）")
        add("")
        if s0_page:
            render_rows([item for item in s0_page["inventory"]
                         if item["selector"] in common_selectors], "s0")
        else:
            add("（S0 采集失败，见 §8）")
            add("")
        for state in main_states:
            page_data = by_state.get(state)
            if not page_data:
                continue
            view_items = [item for item in page_data["inventory"]
                          if item["selector"] not in common_selectors]
            if not view_items:
                continue
            add("#### %s（%d×%d）" % (state, width, HEIGHT))
            add("")
            render_rows(view_items, state)

    # 焦点顺序
    add("## 6 键盘焦点顺序")
    add("")
    add("从 `document.body`（`tabindex=-1` 程序聚焦）按 `Tab` 逐次记录，遇到重复签名即停止；"
        "记录 `:focus-visible` 是否成立与 outline 值。1280 全量列出；1440/1920 与 1280 的"
        "差异见每节末尾（完整三视口数据在 [raw/focus-order.json](raw/focus-order.json)）。")
    add("")
    focus_by = {}
    for entry in summary["focus"]:
        focus_by[(entry["state"], entry["width"])] = entry["steps"]

    def focus_sig(step):
        if step.get("leftDocument"):
            return ("LEFT",)
        return (step.get("tag"), step.get("id"), step.get("classes"), step.get("nodeIndex"))

    for state in ("s0", "setup", "run", "gate", "dirpicker-project", "agent", "legacy"):
        base_steps = focus_by.get((state, 1280))
        if base_steps is None:
            continue
        add("### %s（1280×%d，%d 站）" % (state, HEIGHT, len(base_steps)))
        add("")
        add("| # | 元素 | 名称/文本 | :focus-visible | outline |")
        add("|---|---|---|---|---|")
        for index, step in enumerate(base_steps, 1):
            if step.get("leftDocument"):
                add("| — | 离开文档 | — | — | — |")
                continue
            name = step.get("ariaLabel") or step.get("text") or ""
            ident = step.get("id") or step.get("classes") or step.get("tag")
            add("| %d | `%s` | %s | %s | %s %s %s offset %s |" % (
                index, md_escape(ident), md_escape(name[:48]),
                "✅" if step.get("focusVisible") else "—",
                step["style"].get("outline-width"), step["style"].get("outline-style"),
                step["style"].get("outline-color"),
                step["style"].get("outline-offset")))
        add("")
        diffs = []
        base_sigs = [focus_sig(step) for step in base_steps]
        for width in (1440, 1920):
            other = focus_by.get((state, width))
            if other is None:
                diffs.append("%d 未采集" % width)
                continue
            other_sigs = [focus_sig(step) for step in other]
            if other_sigs == base_sigs:
                diffs.append("%d 与 1280 完全一致（%d 站）" % (width, len(other_sigs)))
                continue
            first = next((i for i, (a, b) in enumerate(zip(base_sigs, other_sigs)) if a != b),
                         min(len(base_sigs), len(other_sigs)))
            what = other[first] if first < len(other) else {"leftDocument": True}
            ident = (what.get("id") or what.get("classes") or what.get("tag")
                     or "离开文档")
            diffs.append("%d 站数 %d；首个差异在第 %d 站（1280 为 `%s`，%d 为 `%s`）" % (
                width, len(other_sigs), first + 1,
                (base_steps[first].get("id") or base_steps[first].get("classes")
                 or base_steps[first].get("tag")) if first < len(base_steps) else "越过末尾",
                width, ident))
        add("**三视口对照**：" + "；".join(diffs))
        add("")

    # 溢出
    add("## 7 溢出、缩放与 reduced-motion")
    add("")
    add("### 7.1 主验收视口的页面水平溢出")
    add("")
    add("| 状态 | 1280 | 1440 | 1920 |")
    add("|---|---|---|---|")
    by_state = {}
    for page_data in summary["pages"]:
        by_state.setdefault(page_data["state"], {})[page_data["width"]] = page_data
    for state, widths in by_state.items():
        cells = []
        for width in VIEWPORTS:
            data = widths.get(width)
            if not data:
                cells.append("未采集")
            else:
                over = data["overflow"]
                cells.append("%s（scrollWidth %s / %s）" % (
                    "**溢出**" if over["pageHorizontalOverflow"] else "无溢出",
                    over["documentScrollWidth"], over["viewportWidth"]))
        add("| %s | %s |" % (state, " | ".join(cells)))
    add("")
    add("### 7.2 窄屏 390/768（只做溢出检查，不新增移动目标）")
    add("")
    add("| 宽度 | 状态 | 页面水平溢出 | 越界/局部溢出元素数 | 前若干项 |")
    add("|---|---|---|---|---|")
    for item in summary["narrow"]:
        over = item["overflow"]
        sample = "；".join("%s%s" % (o["kind"], "#" + o["id"] if o.get("id") else "")
                           for o in over["offenders"][:4]) or "—"
        add("| %d | %s | %s | %d | %s |" % (
            item["width"], item["state"],
            "是" if over["pageHorizontalOverflow"] else "否",
            over["offenderCount"], md_escape(sample[:120])))
    add("")
    add("### 7.3 prefers-reduced-motion 对照（1440）")
    add("")
    add("| 设置 | matchMedia | 按钮 transition-duration | spinner 动画 | html/body scroll-behavior |")
    add("|---|---|---|---|---|")
    for label, data in summary["reduced_motion"].items():
        add("| %s | %s | `%s` | `%s` | `%s` / `%s` |" % (
            label, data["mediaMatches"], data["buttonTransitionDuration"],
            data["spinnerAnimation"], data["htmlScrollBehavior"], data["bodyScrollBehavior"]))
    add("")

    # 请求与错误
    add("## 8 采集期安全性与失败项")
    add("")
    add("- 采集全程只读：切页、聚焦、hover、打开/关闭目录浏览器与 Agent 窗口；"
        "闸门「提交」仅用于触发被拒态，POST 被 route 拦截并回 403，未发往真实服务。")
    add("- 采集脚本记录的 POST 目的地：%s" % (
        "；".join("%d 视口 `%s`" % (p["width"], p["posts"][0][0]) for p in summary.get("posts", [])
                 if p.get("posts")) or "无"))
    add("- 页面 JS 异常（`pageerror`）：%s" % (
        "、".join(e["error"] for e in summary["page_errors"]) or "无"))
    add("- 脚本采集失败项：%s" % ("、".join(summary["failures"]) or "无"))
    add("")
    add("## 9 未覆盖项与限制")
    add("")
    add("1. **不是视觉验收**：本文件只固定改前可观察事实；是否「视觉等价」需要独立评审按 "
        "screens-after 对比逐条判读，同一执行者不得自证通过。")
    add("2. **API 是受控替身**：基线列表、运行 A/B、Agent 记录、目录列表均为固定响应；"
        "真实服务端数据形状与真实模型/仿真链路未覆盖。")
    add("3. **未测宿主缩放 125%/150%**：本轮记录 100%（`devicePixelRatio=1`、"
        "`visualViewport.scale=1`）。主验收的缩放与键盘可达性复核留到 F14-b 改后阶段。")
    add("4. **窄屏 390/768 只做溢出检查**，不提供截图，也不作为产品目标。")
    add("5. **旧页（legacy.html）只覆盖桌面三视口**；其窄屏兼容沿用既有实现，未新增目标。")
    add("6. **未覆盖**：真实浏览器地址栏/系统字体差异（不同主机字体可能影响换行与高度）、"
        "深色系统主题（页面固定 `color-scheme:light`）、打印样式、150% 以上缩放。")
    add("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(HERE), help="证据输出目录（默认脚本所在目录）")
    parser.add_argument("--skip-narrow", action="store_true", help="跳过 390/768 溢出检查")
    parser.add_argument("--screens-dir", default=None,
                        help="截图输出目录（默认 <out>/screens-before；改后采集可指向 screens-after）")
    parser.add_argument("--no-markdown", action="store_true",
                        help="不写 style-inventory.md（用于改后采集，避免覆盖改前基线）")
    args = parser.parse_args(argv)

    outdir = Path(args.out).resolve()
    global SCREENS_DIR
    SCREENS_DIR = (Path(args.screens_dir).resolve() if args.screens_dir
                   else outdir / "screens-before")
    if not (WEB / "index.html").exists():
        raise SystemExit("找不到 loop/web/index.html：%s" % WEB)

    from playwright.sync_api import sync_playwright

    try:
        from importlib.metadata import version as _pkg_version
        _playwright_version = _pkg_version("playwright")
    except Exception:  # noqa: BLE001
        _playwright_version = "unknown"

    results = {"meta": {}, "env": {}, "pages": [], "focus": [], "states": [],
               "media": {"occurrences": [], "unique_conditions": 0, "source_counts": {}}, "narrow": [],
               "reduced_motion": {}, "page_errors": [], "failures": [],
               "posts": [], "screenshots": []}
    dirty = []
    head = branch = "?"
    try:
        import subprocess
        head = subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
        branch = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--abbrev-ref", "HEAD"],
                                capture_output=True, text=True, check=True).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(REPO), "status", "--porcelain"],
            capture_output=True, text=True, check=True).stdout
        dirty = [line[3:] for line in status.splitlines() if line.strip()]
    except Exception as exc:  # noqa: BLE001 - 元数据采集失败要如实记录
        results["failures"].append("git 元数据读取失败：%s" % exc)

    server, thread, static_url = serve_web()
    try:
        with sync_playwright() as pw:
            results["meta"] = {
                "collected_at": _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z"),
                "head": head, "branch": branch, "dirty": dirty,
                "chrome_version": None,
                "browser_executable": os.environ.get("LOOP_BROWSER_EXECUTABLE", "(默认)"),
                "playwright_version": _playwright_version,
                "python": sys.version.split()[0] + " (" + sys.executable + ")",
                "platform": platform.platform(),
                "language": None, "timezone": None,
            }
            try:
                version = capture_viewports(pw, outdir, static_url, results)
                results["meta"]["chrome_version"] = version
            except Exception as exc:  # noqa: BLE001
                results["failures"].append(
                    "主视口采集失败：%s\n%s" % (exc, traceback.format_exc()))
            for func in (capture_async_states, capture_media,
                         capture_interactive_states, capture_narrow,
                         capture_reduced_motion):
                try:
                    if func is capture_narrow and args.skip_narrow:
                        continue
                    if func is capture_media:
                        func(pw, static_url, results)
                    elif func in (capture_async_states, capture_interactive_states):
                        func(pw, outdir, static_url, results)
                    else:
                        func(pw, static_url, results)
                except Exception as exc:  # noqa: BLE001
                    results["failures"].append(
                        "%s 失败：%s\n%s" % (func.__name__, exc, traceback.format_exc()))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()

    env1280 = results["env"].get("views", {}).get("1280")
    if env1280:
        results["meta"]["language"] = env1280["language"]
        results["meta"]["timezone"] = env1280["timezone"]

    # 截图清单（现有测试落图 + 脚本落图）
    test_states = {
        "environment": "S0 环境准备（loop/tests/browser 落图）",
        "configuration": "运行配置 + 基线目录浏览器（loop/tests/browser 落图）",
        "gate": "人工闸门（loop/tests/browser 落图）",
        "monitor": "运行监控（loop/tests/browser 落图）",
        "agent": "Agent 工作窗口（loop/tests/browser 落图，视口内）",
        "legacy": "旧界面（loop/tests/browser 落图）",
        "s0-script": "S0 环境准备（采集脚本落图，用于状态对照）",
        "empty": "运行视图空态",
        "loading": "首次读取加载态",
        "error": "首次读取失败态",
        "stale": "已有数据但刷新失败（陈旧）",
        "run-failed": "运行失败（error + notes）",
        "dirpicker-baseline": "基线目录浏览器",
        "dirpicker-project": "项目目录浏览器",
        "gate-rejected": "闸门被拒（403 blockers）",
    }
    script_states = {k.replace("-", "-"): v for k, v in test_states.items()}
    for path in sorted((SCREENS_DIR or (outdir / "screens-before")).glob("*.png")):
        stem = path.stem
        match = re.match(r"^(\d+)-(.+)$", stem)
        width = int(match.group(1)) if match else None
        kind = match.group(2) if match else stem
        source = ("loop/tests/browser（LOOP_VISUAL_ARTIFACTS）"
                  if kind in ("environment", "configuration", "gate", "monitor", "agent",
                              "legacy") and stem in (
                      "1280-environment", "1280-configuration", "1280-gate", "1280-monitor",
                      "1280-agent", "1280-legacy", "1440-environment", "1440-configuration",
                      "1440-gate", "1440-monitor", "1440-agent", "1440-legacy",
                      "1920-environment", "1920-configuration", "1920-gate", "1920-monitor",
                      "1920-agent", "1920-legacy", "1440-empty", "1440-loading", "1440-error")
                  else "collect_f14a.py")
        results["screenshots"].append({
            "path": str(path),
            "width": width,
            "state": script_states.get(kind, kind),
            "source": source,
        })

    outdir.mkdir(parents=True, exist_ok=True)
    raw = outdir / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    library = {name: data for name, data in (
        ("chrome_version", results["meta"].get("chrome_version")),
        ("playwright", results["meta"].get("playwright_version")),
    )}
    del library
    if results["failures"]:
        print("采集失败项（先落 raw 供诊断）：")
        for failure in results["failures"]:
            print("----")
            print(failure)
        return 2
    (raw / "summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    (raw / "media-queries.json").write_text(
        json.dumps(results["media"], ensure_ascii=False, indent=2), encoding="utf-8")
    (raw / "focus-order.json").write_text(
        json.dumps(results["focus"], ensure_ascii=False, indent=2), encoding="utf-8")
    (raw / "interactive-states.json").write_text(
        json.dumps(results["states"], ensure_ascii=False, indent=2), encoding="utf-8")
    (raw / "env.json").write_text(
        json.dumps({"meta": results["meta"], "env": results["env"]},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    if not args.no_markdown:
        inventory_md = render_markdown(results, outdir)
        (outdir / "style-inventory.md").write_text(inventory_md, encoding="utf-8")

    print("F14-a 采集完成")
    print("  输出目录：%s" % outdir)
    print("  截图：%d 张（%s）" % (len(results["screenshots"]), Path(SCREENS_DIR).name))
    print("  页面状态：%d 个（含三视口记录）" % len(results["pages"]))
    print("  焦点顺序：%d 份" % len(results["focus"]))
    print("  交互态：%d 项" % len(results["states"]))
    print("  媒体查询：%d 次出现 / %d 个不同条件" % (
        len(results["media"]["occurrences"]), results["media"]["unique_conditions"]))
    print("  浏览器：%s" % results["meta"].get("chrome_version"))
    if results["failures"]:
        print("失败项：%d" % len(results["failures"]))
        for failure in results["failures"]:
            print("  - " + failure.splitlines()[0])
        return 1
    if results["page_errors"]:
        print("页面 JS 异常：%d" % len(results["page_errors"]))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
