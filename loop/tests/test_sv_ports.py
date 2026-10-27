"""S0-b D1：`host/sv_ports.py` 的判据（确定性、只读、不猜）。

契约：`doc/spec/S0_ENVIRONMENT_SPEC.md` §8.2-1（Q1 = Host 确定性派生，2026-10-27 裁决）。
这些用例只钉四件事，不测"差异表长得好看"：

1. 解析：ANSI 端口表（含 `#(...)` 参数、注释、多位宽）能正确抽出方向与位宽；
2. **不猜**：非 ANSI / 端口项缺方向 / 同名模块重复 ⇒ 进 `unparsed` 且 `derive_port_diff().ok is False`；
3. **确定性**：同一输入两次派生 `md5` 相同（表本身可复算）；
4. **无副作用**：派生前后输入树内容指纹不变。
"""
from __future__ import annotations

from pathlib import Path

from host import sv_ports


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


ANSI_TOP = """\
// 注释里的 module fake 不应被当成模块
module dut_top #(
    parameter W = 8,
    parameter D = 4
) (
    input               clk,
    input               rst_n,
    input  [W-1:0]      din,     // 数据
    output reg [D-1:0]  dout,
    inout  wire         pad,
    output              done
);
    /* module not_a_module; */
endmodule
"""


def test_ansi_ports_with_params_comments_and_widths(tmp_path: Path) -> None:
    _write(tmp_path, "dut.v", ANSI_TOP)
    modules, unparsed = sv_ports.parse_module_ports((tmp_path / "dut.v").read_text(encoding="utf-8"))
    assert unparsed == []
    assert set(modules) == {"dut_top"}
    ports = {p.name: p for p in modules["dut_top"]}
    assert [ports[n].direction for n in ("clk", "din", "dout", "pad", "done")] == [
        "input", "input", "output", "inout", "output"]
    assert ports["din"].width == "[W-1:0]"
    assert ports["dout"].width == "[D-1:0]"
    assert ports["clk"].width == ""


def test_non_ansi_port_list_is_unparsed_not_guessed(tmp_path: Path) -> None:
    """老式 `module m(a, b); input a;` 不算"无差异"，必须进 unparsed（fail-closed）。"""
    _write(tmp_path, "old.v", "module old_style(a, b);\n  input a;\n  output b;\nendmodule\n")
    modules, unparsed = sv_ports.parse_module_ports((tmp_path / "old.v").read_text(encoding="utf-8"))
    assert modules == {}
    assert unparsed == ["old_style"]


def test_port_item_without_direction_is_unparsed(tmp_path: Path) -> None:
    """ANSI 里的续行写法（`input [7:0] a, b`）不猜语义，整模块记 unparsed。"""
    _write(tmp_path, "cont.v", "module cont(input [7:0] a, b);\nendmodule\n")
    modules, unparsed = sv_ports.parse_module_ports((tmp_path / "cont.v").read_text(encoding="utf-8"))
    assert modules == {}
    assert unparsed == ["cont"]


def test_duplicate_module_identical_ports_is_not_an_ambiguity(tmp_path: Path) -> None:
    """厂商库里同名同端口的重复定义很常见 ⇒ 计数，不算歧义（否则真实树全判 unparsed）。"""
    _write(tmp_path, "a.v", "module dup(input a);\nendmodule\n")
    _write(tmp_path, "b.v", "module dup(input a);\nendmodule\n")
    scan = sv_ports.scan_tree(tmp_path)
    assert scan["files"] == 2
    assert scan["duplicates"] == 1
    assert scan["unparsed"] == []


def test_duplicate_module_different_ports_is_reported(tmp_path: Path) -> None:
    """同名但端口不同 = 真歧义 ⇒ 必须进 unparsed（不静默取其一）。"""
    _write(tmp_path, "a.v", "module dup(input a);\nendmodule\n")
    _write(tmp_path, "b.v", "module dup(input a, input b);\nendmodule\n")
    scan = sv_ports.scan_tree(tmp_path)
    assert any(entry.startswith("dup@") for entry in scan["unparsed"])


def test_derive_is_deterministic(tmp_path: Path) -> None:
    base, cand = tmp_path / "base", tmp_path / "cand"
    _write(base, "dut.v", ANSI_TOP)
    _write(cand, "dut.v", ANSI_TOP.replace("output              done",
                                           "output              done,\n    output [3:0]        extra"))
    first = sv_ports.derive_port_diff(base, cand)
    second = sv_ports.derive_port_diff(base, cand)
    assert first["md5"] == second["md5"]
    assert first == second


def test_derive_has_no_side_effect_on_input_trees(tmp_path: Path) -> None:
    base, cand = tmp_path / "base", tmp_path / "cand"
    _write(base, "dut.v", ANSI_TOP)
    _write(cand, "dut.v", ANSI_TOP)
    before = (sv_ports.tree_md5(base), sv_ports.tree_md5(cand))
    sv_ports.derive_port_diff(base, cand)
    assert (sv_ports.tree_md5(base), sv_ports.tree_md5(cand)) == before


def test_derive_reports_add_remove_and_change(tmp_path: Path) -> None:
    base, cand = tmp_path / "base", tmp_path / "cand"
    _write(base, "dut.v", """\
module dut_top(
    input        clk,
    input  [7:0] din,
    output       old_out,
    inout        pad
);
endmodule
""")
    _write(cand, "dut.v", """\
module dut_top(
    input        clk,
    input  [15:0] din,
    output       new_out,
    inout        pad
);
endmodule
""")
    diff = sv_ports.derive_port_diff(base, cand)
    assert diff["ok"] is True
    assert diff["added_modules"] == [] and diff["removed_modules"] == []
    assert [row["module"] for row in diff["changed"]] == ["dut_top"]
    row = diff["changed"][0]
    assert row["added"] == ["new_out"]
    assert row["removed"] == ["old_out"]
    assert row["changed"] == [{"name": "din",
                               "before": {"name": "din", "direction": "input", "width": "[7:0]"},
                               "after": {"name": "din", "direction": "input", "width": "[15:0]"}}]


def test_unparsed_module_makes_derive_not_ok(tmp_path: Path) -> None:
    base, cand = tmp_path / "base", tmp_path / "cand"
    _write(base, "dut.v", ANSI_TOP)
    _write(cand, "dut.v", ANSI_TOP)
    _write(cand, "legacy.v", "module legacy(a);\n  input a;\nendmodule\n")
    diff = sv_ports.derive_port_diff(base, cand)
    assert diff["ok"] is False
    assert "legacy" in diff["candidate"]["unparsed"]


def test_missing_input_tree_is_not_ok(tmp_path: Path) -> None:
    base = tmp_path / "base"
    _write(base, "dut.v", ANSI_TOP)
    diff = sv_ports.derive_port_diff(base, tmp_path / "does-not-exist")
    assert diff["ok"] is False
    assert diff["candidate"]["exists"] is False


def test_unparsed_but_identical_between_sides_is_not_a_blocker(tmp_path: Path) -> None:
    """两侧都解析不了、但源文件一模一样 ⇒ 语义未变，不影响差异判定（真实树有 52 个这种老式模块）。"""
    legacy = "module legacy(a);\n  input a;\nendmodule\n"
    base, cand = tmp_path / "base", tmp_path / "cand"
    _write(base, "legacy.v", legacy)
    _write(cand, "legacy.v", legacy)
    _write(base, "dut.v", ANSI_TOP)
    _write(cand, "dut.v", ANSI_TOP.replace("output              done",
                                           "output              done,\n    output [1:0]       extra"))
    diff = sv_ports.derive_port_diff(base, cand)
    assert diff["ok"] is True
    assert diff["unparsed_drift"] == [] and diff["unparsed_ambiguity"] == []
    assert "legacy" in diff["baseline"]["unparsed"]


def test_unparsed_module_that_really_changed_blocks_the_derivation(tmp_path: Path) -> None:
    """解析不了又**内容变了** ⇒ 可能改了端口，必须 fail-closed（不许当作无差异）。"""
    base, cand = tmp_path / "base", tmp_path / "cand"
    _write(base, "legacy.v", "module legacy(a);\n  input a;\nendmodule\n")
    _write(cand, "legacy.v", "module legacy(a, b);\n  input a;\n  output b;\nendmodule\n")
    diff = sv_ports.derive_port_diff(base, cand)
    assert diff["ok"] is False
    assert [row["module"] for row in diff["unparsed_drift"]] == ["legacy"]


def test_modules_filter_limits_comparison(tmp_path: Path) -> None:
    base, cand = tmp_path / "base", tmp_path / "cand"
    _write(base, "a.v", "module keep(input a);\nendmodule\n")
    _write(base, "b.v", "module ignore_me(input b);\nendmodule\n")
    _write(cand, "a.v", "module keep(input a, input a2);\nendmodule\n")
    _write(cand, "b.v", "module ignore_me(input b, input b2);\nendmodule\n")
    diff = sv_ports.derive_port_diff(base, cand, modules=["keep"])
    assert diff["modules_filter"] == ["keep"]
    assert [row["module"] for row in diff["changed"]] == ["keep"]
    assert diff["changed"][0]["added"] == ["a2"]


def test_empty_port_list_module_is_parsed_as_no_ports(tmp_path: Path) -> None:
    _write(tmp_path, "e.v", "module empty_mod();\nendmodule\n")
    modules, unparsed = sv_ports.parse_module_ports((tmp_path / "e.v").read_text(encoding="utf-8"))
    assert modules == {"empty_mod": []} and unparsed == []


def test_preprocessor_uses_compile_time_defines(tmp_path: Path) -> None:
    """真实 DUT 顶层就有 `` `ifndef SIMULATION ``：宏定了，端口集才是"编译时看到的那个"。"""
    source = """\
module dut_top(
    input  wire clk,
`ifndef SIMULATION
    output wire pci_exp_txp,
    input  wire pcie_refclk_p,
`else
    input  wire pcie_user_clk,
    input  wire [7:0] fc_ph,
`endif
    output wire done
);
endmodule
"""
    with_sim = sv_ports.parse_module_ports(source, frozenset({"SIM", "SIMULATION"}))
    assert with_sim[1] == []
    names = [p.name for p in with_sim[0]["dut_top"]]
    assert "pcie_user_clk" in names and "fc_ph" in names
    assert "pci_exp_txp" not in names and "pcie_refclk_p" not in names

    without = sv_ports.parse_module_ports(source, frozenset())
    names2 = [p.name for p in without[0]["dut_top"]]
    assert "pci_exp_txp" in names2 and "pcie_user_clk" not in names2


def test_load_defines_reads_all_define_file(tmp_path: Path) -> None:
    path = tmp_path / "all_define.txt"
    path.write_text("-define   SIM\n-define   SIMULATION\n//-define   VENDOR_XILINX\n",
                    encoding="utf-8")
    assert sv_ports.load_defines(path) == frozenset({"SIM", "SIMULATION"})


def test_scan_prefers_filelist_when_present(tmp_path: Path) -> None:
    """有 `rtl_dir_pango.txt` 时只扫清单里的文件（与编译一致）。"""
    rtl = tmp_path / "RTL"
    _write(rtl, "SRC/inside.v", "module inside(input a);\nendmodule\n")
    _write(rtl, "SRC/outside.v", "module outside(input a);\nendmodule\n")
    _write(rtl, "rtl_dir_pango.txt", "+incdir+./RTL/SRC\n./RTL/SRC/inside.v\n")
    scan = sv_ports.scan_tree(rtl)
    assert scan["from_filelist"] is True
    assert list(scan["modules"]) == ["inside"]
