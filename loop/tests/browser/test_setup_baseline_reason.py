"""配置视图「无可用基线」必须给原因（WEB_UI_SPEC §3.1 / 计划 U1–U5）。

受控替身：`ui` fixture 先挂通用 `/api/**` 路由，本文件在**其后**用 `page.route` 覆盖
`/api/baselines`（Playwright 后注册优先），再点 `#segSetup` + `#btnRefreshBaselines`，
让断言走真实前端渲染路径（`loadBaselines` → `renderBaselineSelect` → `renderBaselineMeta`）。

判据（与 doc/plans/2026-10-29-derived-root-admission-and-ui-reason.md §4 同名同号）：
- U1 全部不可用：chip `0 个可用 / 1 个`；下拉项 `v0（不可用）` 且 disabled。
- U2 meta 渲染首个不可用条目的字段 + 「没有可用基线版本」 + `missing`/`errors` 原文，
  不再只显示「未选择基线」。
- U3 `#btnStart` 仍 disabled，hint 含「请选择有效基线」。
- U4 1280×720 无水平溢出（`test_web_layout.assert_fits` 判据形态）。
- U5 混合 1 valid + 1 invalid：选中 valid ⇒ meta 含 `manifest 有效`；项目校验通过后
  `#btnStart` 可用（不因存在不可用条目而阻断）。

缺 Chromium 属环境缺件：`test_run_sessions` 已 `importorskip("playwright.sync_api")`，
不加 `pytest.skip` 兜底，避免把缺件当成通过。
"""
from __future__ import annotations


from test_run_sessions import pw, ui, static_url  # noqa: F401
from test_web_layout import assert_fits

# 与 8199 实测形状一致（2026-10-29 派生数据根）：`valid=false`、六件 missing，
# created_at/parent/cases/rtl_snapshot_bytes 仍由服务端下发。
INVALID = {
    "id": "v0",
    "valid": False,
    "created_at": "2026-10-15T12:05:00",
    "parent": None,
    "cases": 162,
    "rtl_snapshot_bytes": 2570240,
    "missing": ["rtl_snapshot", "allfiles_manifest", "cases_freeze",
                "conflicts_snapshot", "doc_fingerprint", "evidence_index"],
    "errors": [],
}

# U4 用来证明长原因可换行、不撑破视口：missing 原文带声明路径（服务端形态）。
INVALID_LONG_REASON = {
    "id": "v0",
    "valid": False,
    "created_at": "2026-10-15T12:05:00",
    "parent": "v-1",
    "cases": 162,
    "rtl_snapshot_bytes": 2570240,
    "missing": ["rtl_snapshot: 'kb/baselines/v0/rtl_snapshot.tar'",
                "allfiles_manifest: 'kb/baselines/v0/allfiles_manifest.json'",
                "cases_freeze: 'kb/baselines/v0/cases_freeze.json'",
                "conflicts_snapshot: 'kb/baselines/v0/conflicts_snapshot.json'",
                "doc_fingerprint: 'kb/baselines/v0/doc_fingerprint.json'",
                "evidence_index: 'kb/baselines/v0/evidence_index.json'"],
    "errors": ["manifest 不合 schema：/fixture/kb/baselines/v0/manifest.json → "
               "'rtl_snapshot_sha256' 缺失"],
}

VALID = {
    "id": "v1.2-stable",
    "valid": True,
    "created_at": "2026-10-20T09:30:00",
    "parent": "v1.1",
    "cases": 162,
    "rtl_snapshot_bytes": 2570240,
    "missing": [],
    "errors": [],
}

ENV_OK = {
    "ok": True, "matches_current_process": True, "path": "/fixture", "registered": True,
    "env_id": "TCS9620", "plugin_missing": [], "workspace_missing": [],
    "counts": {"rtl_files": 1210, "cases": 162},
}


def open_setup(page, baselines):
    """在 `ui` fixture 之后覆盖基线列表，再经「运行配置」+「刷新」触发一次真实渲染。"""
    page.route("**/api/baselines", lambda route: route.fulfill(json={"baselines": baselines}))
    page.locator("#segSetup").click()
    page.locator("#btnRefreshBaselines").click()


def test_u1_all_unavailable_chip_and_disabled_option(ui):
    page, api = ui
    open_setup(page, [INVALID])
    pw.expect(page.locator("#setupBaselineChip")).to_have_text("0 个可用 / 1 个")
    option = page.locator('#setupBaseline option[value="v0"]')
    pw.expect(option).to_have_text("v0（不可用）")
    pw.expect(option).to_be_disabled()
    assert not api["posts"]


def test_u2_meta_gives_first_unavailable_entry_and_reasons(ui):
    page, api = ui
    open_setup(page, [INVALID])
    meta = page.locator("#setupBaselineMeta")
    pw.expect(page.locator("#setupBaselineChip")).to_have_text("0 个可用 / 1 个")
    pw.expect(meta).to_contain_text("没有可用基线版本")
    text = meta.inner_text()
    # 首个不可用条目的字段照旧显示（created_at / parent / 用例 / RTL 快照）
    assert "2026-10-15 12:05" in text, text
    assert "parent" in text, text
    assert "162" in text, text
    assert "RTL" in text, text
    # missing / errors 是服务端原文，前端不猜、不合成
    assert "rtl_snapshot" in text, text
    assert "evidence_index" in text, text
    # 不再只显示「未选择基线」
    assert "未选择基线" not in text, text
    assert not api["posts"]


def test_u3_start_stays_disabled_with_explicit_hint(ui):
    page, api = ui
    open_setup(page, [INVALID])
    pw.expect(page.locator("#setupBaselineChip")).to_have_text("0 个可用 / 1 个")
    pw.expect(page.locator("#btnStart")).to_be_disabled()
    pw.expect(page.locator("#btnStartHint")).to_contain_text("请选择有效基线")
    assert not api["posts"]


def test_u4_reason_meta_fits_acceptance_viewport(ui):
    page, api = ui
    page.set_viewport_size({"width": 1280, "height": 720})
    open_setup(page, [INVALID_LONG_REASON])
    pw.expect(page.locator("#setupBaselineMeta")).to_contain_text("没有可用基线版本")
    pw.expect(page.locator("#setupBaselineMeta")).to_contain_text("rtl_snapshot")
    # 长原因必须可换行（span.muted），不撑破 step-card / 视口（判据同 test_web_layout）
    assert_fits(page, "#viewSetup .input, #viewSetup .btn, #setupBaselineMeta span")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    assert not api["posts"]


def test_u5_valid_entry_keeps_meta_and_allows_start_after_check(ui):
    page, api = ui
    page.route("**/api/env/check?**", lambda route: route.fulfill(json=ENV_OK))
    # 不可用条目排在前面：默认选中必须跳过它，选第一个 valid
    open_setup(page, [INVALID, VALID])
    pw.expect(page.locator("#setupBaselineChip")).to_have_text("1 个可用 / 2 个")
    pw.expect(page.locator("#setupBaseline")).to_have_value("v1.2-stable")
    meta = page.locator("#setupBaselineMeta")
    pw.expect(meta).to_contain_text("manifest 有效")
    assert "没有可用基线版本" not in meta.inner_text()
    page.locator("#setupCheck").click()
    pw.expect(page.locator("#setupProjectMeta")).to_contain_text("校验通过")
    pw.expect(page.locator("#btnStart")).to_be_enabled()
    assert not api["posts"]
