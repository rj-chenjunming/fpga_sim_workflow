"""N0 基线运行初始化。"""
from typing import Any


async def run(data: Any, *, ctx: Any, run_kb_tool: Any, drill_files: Any) -> dict[str, Any]:
    """N0 选基线并建运行目录，同时把**权威闸门态**初始化。

    `gate.py init` 是刻意的一步：不能从夹具拷 `gates.json` 进来，
    否则「闸门已签」会凭空成立（那是本轮演练的教训面）。
    """
    ctx.node_started("N0")
    ctx.run_dir.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []
    if ctx.mode == "drill":
        for name in drill_files():
            dest = ctx.copy_fixture(name)
            if dest is not None:
                copied.append(str(dest))
        ctx.notes.append(f"drill 夹具：{ctx.fixture}")

    gate_init = run_kb_tool("gate.py", ["init", "--run", ctx.run_id])
    if gate_init["rc"] not in (0, 3):
        # rc=3 = 已存在（不覆盖签署），这是合法状态，不当作失败。
        ctx.node_failed("N0", message=f"gate.py init rc={gate_init['rc']}")
        raise RuntimeError(f"gate.py init rc={gate_init['rc']}: {gate_init['stderr_tail'][-300:]}")

    baseline_value = data.input.get("baseline") if isinstance(data.input, dict) else None
    payload = {
        "run_id": ctx.run_id,
        "run_dir": str(ctx.run_dir),
        "mode": ctx.mode,
        "baseline": baseline_value,
        "gate_init_rc": gate_init["rc"],
    }
    await data.async_set_state("run_meta", payload)
    # §10.4：N0 必须给 baseline + source + summary（drill 必须能看出是夹具）。
    if ctx.mode == "drill":
        source = "drill_fixture"
        # 裁决 #6（P-01 A）：新 run 的 drill 措辞改为「预置数据（夹具）初始化」（旧 run 不回填）。
        summary = (f"N0：预置数据（夹具）初始化（复制 {len(copied)} 个夹具文件，"
                   f"复制清单 {len(drill_files())} 项），gate.py init rc={gate_init['rc']}，"
                   f"baseline={baseline_value}")
    else:
        source = "kb_tool"
        summary = (f"N0：真实运行目录初始化（未复制夹具），gate.py init rc={gate_init['rc']}，"
                   f"baseline={baseline_value}")
    ctx.node_finished(
        "N0",
        detail={
            "mode": ctx.mode,
            "fixture_files": len(copied),
            "gate_init_rc": gate_init["rc"],
            "baseline": baseline_value,
            "source": source,
            "summary": summary,
        },
        refs=[str(ctx.run_dir)],
    )
    return payload
