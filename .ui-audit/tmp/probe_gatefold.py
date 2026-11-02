from __future__ import annotations
import sys
from pathlib import Path
B = Path(__file__).resolve().parents[2] / "loop" / "tests" / "browser"
sys.path.insert(0, str(B))
import pytest
from test_run_sessions import pw, static_url, ui  # noqa
from test_web_layout import populate  # noqa

def test_gate_y(ui):
    page, api = ui
    page.set_viewport_size({"width": 1440, "height": 900})
    populate(api)
    page.locator(".run-item").first.click()
    pw.expect(page.locator("#viewGate")).to_be_visible()
    for sel in ("#gateMaterial", "#gatePanel"):
        b = page.locator(sel).bounding_box()
        print(f"[gate 1440x900] {sel:14s} y={b['y']:.1f} h={b['height']:.1f} 可见比例={max(0,(min(b['y']+b['height'],900)-max(b['y'],0)))/b['height']:.2f}")
    print("[gate 1440x900] scrollY =", page.evaluate("() => scrollY"))
