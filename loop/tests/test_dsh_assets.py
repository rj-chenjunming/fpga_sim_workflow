"""S2 共享基础：attempt 资产物化（Lead-owned；A/B 片只读用）。

判据（不读实现也应成立）：
- patch 顺序 = 钉死 → 外部 overlay → 插件 insert（插件按给定顺序）；
- 插件源码从仓内 `dsh_plugin/` **复制**进 attempt 目录（包裹内仓内路径不可见）；
- attempt home 带宿主 `settings.yaml`/`.credentials.yaml` ⇒ 显式失败（DS-09）；
- 缺插件源码/缺外部 patch ⇒ 显式失败，不静默跳过。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from host.agent_backends import dsh_assets as A

PLUGIN_BODY = "export const name = 'fixture'\nexport function apply() {}\n"


@pytest.fixture()
def plugin_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把插件源码目录指向临时目录，避免用真插件当夹具（真插件另有自己的用例）。"""
    source = tmp_path / "dsh_plugin_src"
    source.mkdir()
    (source / "probe.mjs").write_text(PLUGIN_BODY, encoding="utf-8")
    monkeypatch.setattr(A, "PLUGIN_SOURCE_DIR", source)
    return source


def _layout(tmp_path: Path) -> A.AttemptLayout:
    return A.AttemptLayout.under(tmp_path / "attempt")


def test_layout_paths_are_under_root(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    layout.prepare()
    for path in (layout.work, layout.home, layout.plugin_dir, layout.patch_dir,
                 layout.selfcheck_dir):
        assert path.is_dir() and layout.root in path.parents
    assert layout.selfcheck_file().name == "selfcheck.json"


def test_materialize_copies_plugin_and_writes_absolute_insert(tmp_path: Path, plugin_dir: Path) -> None:
    layout = _layout(tmp_path)
    assets = A.materialize(layout, plugins=(A.Plugin("s2-probe", "probe.mjs"),))
    (entry, path), = assets.plugins
    assert entry == "s2-probe" and path.is_file() and path.parent == layout.plugin_dir
    assert path.read_text(encoding="utf-8") == PLUGIN_BODY
    patch = assets.patch_files[-1].read_text(encoding="utf-8")
    assert "- insert:" in patch and "id: s2-probe" in patch
    assert str(path) in patch and path.is_absolute()


def test_pins_first_then_extras_then_plugins(tmp_path: Path, plugin_dir: Path) -> None:
    layout = _layout(tmp_path)
    extra = tmp_path / "provider.yml"
    extra.write_text("- id: llm-pi-ai\n  config: {}\n", encoding="utf-8")
    assets = A.materialize(layout, pins=A.Pins(), extra_patches=(extra,),
                           plugins=(A.Plugin("first", "probe.mjs"),
                                    A.Plugin("second", "probe.mjs")))
    assert [p.name for p in assets.patch_files] == [
        "00-pins.yml", "01-extra-provider.yml",
        "10-plugin-first.yml", "10-plugin-second.yml"]
    pins = assets.patch_files[0].read_text(encoding="utf-8")
    assert "sandbox-policy" in pins and "mode: read-only" in pins
    assert "permission" in pins and "defaultPreset: read-only" in pins
    assert assets.pins == A.Pins()


def test_home_with_host_settings_fails(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    layout.prepare()
    (layout.home / "settings.yaml").write_text(
        "permission-presets:\n  defaultPreset: danger-full-access\n", encoding="utf-8")
    with pytest.raises(A.AssetError, match="settings.yaml"):
        A.materialize(layout)


def test_home_with_credentials_fails(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    layout.prepare()
    (layout.home / ".credentials.yaml").write_text("x: y\n", encoding="utf-8")
    assert A.home_problems(layout.home)
    with pytest.raises(A.AssetError):
        A.materialize(layout)


def test_pins_carry_the_full_preset_table(tmp_path: Path, plugin_dir: Path) -> None:
    """B3 实测教训：patch 的 `config` 是**整块替换**，少写 `presets` ⇒ permission 条目激活失败
    （原文 `permission: unknown preset "read-only"`），preset 回显恒为空。"""
    layout = _layout(tmp_path)
    assets = A.materialize(layout, pins=A.Pins())
    pins = assets.patch_files[0].read_text(encoding="utf-8")
    for name, (sandbox, approval) in A.PRESET_TABLE.items():
        assert "%s:" % name in pins
        assert "sandbox: %s" % sandbox in pins and "approval: %s" % approval in pins
    assert "defaultPreset: %s" % A.DEFAULT_PRESET in pins
    assert "mode: %s" % A.DEFAULT_SANDBOX_MODE in pins
    # 钉死值必须与档位表自洽（不允许"钉了一个表里没有的档"）
    assert A.DEFAULT_PRESET in A.PRESET_TABLE
    assert A.PRESET_TABLE[A.DEFAULT_PRESET][0] == A.DEFAULT_SANDBOX_MODE


def test_node_modules_link_is_created_for_plugin_imports(tmp_path: Path, plugin_dir: Path) -> None:
    """插件被复制进 attempt 目录后仍要能 `import '@deepseek-ai/dsh-tools'`。

    实测坑：找不到包 ⇒ `ERR_MODULE_NOT_FOUND` ⇒ 插件 `did not activate`（只 warning），
    工具清单里没有 submit_result。做法是在插件目录放一条指向安装树的 `node_modules` 软链。
    """
    install_nm = tmp_path / "install" / "node_modules"
    install_nm.mkdir(parents=True)
    layout = _layout(tmp_path)
    assets = A.materialize(layout, plugins=(A.Plugin("p", "probe.mjs"),),
                           node_modules=install_nm)
    link = assets.layout.plugin_dir / "node_modules"
    assert link.is_symlink() and link.resolve() == install_nm.resolve()
    assert assets.node_modules == link
    # 幂等：再物化一次不报错、指向不变
    again = A.materialize(layout, plugins=(A.Plugin("p", "probe.mjs"),), node_modules=install_nm)
    assert again.node_modules == link and link.resolve() == install_nm.resolve()


def test_node_modules_for_derives_install_root(tmp_path: Path) -> None:
    bin_path = tmp_path / "versions" / "0.2.1-rc.2" / "node_modules" / "@deepseek-ai" / "dsh" / "lib" / "bin.js"
    bin_path.parent.mkdir(parents=True)
    bin_path.write_text("// stub\n", encoding="utf-8")
    assert A.node_modules_for(bin_path) == bin_path.parents[3]
    assert A.node_modules_for(tmp_path / "no" / "such" / "bin.js") is None


def test_missing_plugin_source_fails(tmp_path: Path, plugin_dir: Path) -> None:
    layout = _layout(tmp_path)
    with pytest.raises(A.AssetError, match="插件源码不存在"):
        A.materialize(layout, plugins=(A.Plugin("nope", "not_there.mjs"),))


def test_missing_extra_patch_fails(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    with pytest.raises(A.AssetError, match="外部 patch 不存在"):
        A.materialize(layout, extra_patches=(tmp_path / "absent.yml",))


def test_clean_home_has_no_problems(tmp_path: Path) -> None:
    layout = _layout(tmp_path)
    layout.prepare()
    assert A.home_problems(layout.home) == []


def test_rematerialize_clears_stale_selfcheck_report(tmp_path: Path, plugin_dir: Path) -> None:
    """独立复核 P1-1：复用 attempt root 时必须清掉上一次的 `selfcheck.json`。

    否则本次 attempt 的 dsh 即使没写报告，Host 也会读到"上一次的事实"并放行。
    """
    layout = _layout(tmp_path)
    A.materialize(layout, plugins=(A.Plugin("p", "probe.mjs"),))
    stale = layout.selfcheck_file()
    stale.write_text('{"plugin":"s2-selfcheck","phase":"deferred"}', encoding="utf-8")
    assert stale.is_file()
    A.materialize(layout, plugins=(A.Plugin("p", "probe.mjs"),))
    assert not stale.exists(), "旧自检报告必须在本次物化时清掉"
