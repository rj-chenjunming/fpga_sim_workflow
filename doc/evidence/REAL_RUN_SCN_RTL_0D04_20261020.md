# 真实环境跑通记录：SCN_RTL_0D04（2026-10-20）

> **性质**：第一次在**真实环境副本 + real 模式 + 真实 LLM + 真实编译**上跑 `change-impact-loop`
> 的验收证据（只增不改）。不是 drill 夹具。
> **结论先行**：**N0→N8 真实跑通**（N2/N5 与预登记答案完全一致；N7 五个用例真实编译 5/5 rc=0；
> N8 真实模型 pass）。真实 N9 全跑按用户选择的范围，在作业提交后立即取消（run 显式 failed）。
> 本轮暴露并修复了 4 个软件缺陷（见 §4）。

- 场景工程（库外）：`/home/work/chenjunming/FPGA_SIM/SCN_RTL_0D04/`
- 场景环境副本：`SCN_RTL_0D04/env`；数据根：`SCN_RTL_0D04/workspace`（自建 v0）
- 权威 ENV_ROOT：**只读**；setup 对 `RTL`、`TB`、`PKG`、`TESTLIB` 4491 条 md5 见证前后一致
- 变更：`RTL/SRC/imports/SRC/pcie_controller/pcie_register.v` 0x0d04 由 32 位读写收窄为 `[15:0]`；
  md5 `d560f2ff15388aad16dc64431d67a617` → `50e4ca25f384d0ee384252b34f30e760`
- 人类 actor：`human:chenjunming`；模型：`origin-deepseek-v4-1-flash`（live）

---

## 1 成功轮（RUN-20261020-111000）

| 节点 | 证据 |
|---|---|
| N1 | `n1_snapshot.py stage --run RUN-20261020-111000 --parent v0`（无 staged，用环境现态），rc=0 |
| N2 | 差异 2 条：同一文件的 `allfile` + `rtl_file`（hunk 行 171-172、offset `0xd04`），与预登记 `expected/n2_expected.json` 一致 |
| N3 | live 模型 ok（`n3_digest.md` 落盘） |
| N4 | G1 `confirmed` + `entry_decisions` 覆盖全部差异条目（real I1 要求） |
| N5 | **5 个必须用例与答案完全一致**：`tc_cpu_i2c_03 / tc_pcie_rw_02 / tc_pcie_rw_smoke / tc_rtc_05 / tc_rtc_10`；entry `0x0d00#0x0d04`；站点 B1 |
| N6 | live；5 用例各 1 条 edit；`n6_apply` 落 `sandbox/TESTLIB` 并冻结 md5 |
| N7 | `run_guarded.sh --mode compile-only` ×5，**全部 rc=0**（证据日志在 run/evidence） |
| N8 | live 模型 **pass**（findings：地址未改 / 期望值与 rtl_change 一致 / doc_out_of_sync 记录 / 既有裸 wait 按“仅本轮改动”N/A） |
| N9 | 真实全跑作业 `JOB-c9d19d437668` 已提交；按范围立即取消 ⇒ run 显式 `failed`（“作业被取消 ⇒ 无法满足 I3”） |

节点历史：`N0 N1 N2 N3 N3_model N3_request N4 N5 N6 N6_model N6_request N6_apply N7 N8 N8_model N8_request N9_submit`。

## 2 N6 与答案键的逐用例比对

| 用例 | 答案键（预登记） | 实测 | 判定 |
|---|---|---|---|
| tc_pcie_rw_smoke | `32'h12345678` → `32'h0000_5678` | `32'h00005678` | 语义等价（少一个 `_`） |
| tc_rtc_05 | 同上 | `32'h00005678` | 语义等价 |
| tc_rtc_10 | 同上 | `32'h00005678` | 语义等价 |
| tc_pcie_rw_02 | `32'hffff_ffff` → `32'h0000_ffff`（data_expmask） | 改为 `32'h0000_0000` → `32'h0000_ffff`（initial_dat） | **不符合** |
| tc_cpu_i2c_03 | 同上 | 同上 | **不符合** |

> **根因**：`reg_field_test(addr, data_expmask, initial_dat='0, only_r=0)` 的第 2 个数据参数是
> **期望掩码**，第 3 个是初始值；模型把两者弄反。N7 只抓语法（该改动能编译），抓不到语义；
> 设计上应由 **N9 全跑证据**（0xd04 仍出 `*E`）触发返工——本轮 N9 按范围未跑。
> 这是本轮留下的**已知质量 finding**，不是静默通过。

## 3 失败重试轨迹（全部真实运行，未回改期望）

| run | 结果 | 真实原因 |
|---|---|---|
| RUN-20261020-103000 | N6 failed | N6 取不到文档位定义（RTL-only 变更时 `_doc_bitdef_from_diff` 只认 doc_entry） |
| RUN-20261020-104000 | N7 failed | 新环境无 `SIMLIB_RUN/` ⇒ `run_guarded.sh` 把 `mkdir` 父目录缺失误判成陈旧锁（rc=3） |
| RUN-20261020-104500 | N7 failed | N6 产出 `0x0d00+0xd04` 非法 SV 字面量 ⇒ TB 编译 rc=1 |
| RUN-20261020-105000 | N8 escalated（3 轮） | N8 以“文档未同步”反复退回，且把既有代码的裸 wait 当本轮问题 |
| RUN-20261020-110000 | N8 escalated（3 轮） | 同上（既有 `wait(test_done)`） |
| **RUN-20261020-111000** | **N0→N8 pass；N9 提交后取消** | 最终成功轮 |

## 4 本轮修复（代码 + 回归测试）

| # | 缺陷 | 修复 | 回归 |
|---|---|---|---|
| 1 | N6 在 RTL-only 变更下拿不到 `doc_bitdef` | `_doc_bitdef_from_snapshot()` 从本轮 `bundle/doc_entries.jsonl` 取；仍 fail closed | `tests/test_fix_real_chain.py::test_n6_doc_bitdef_falls_back_to_run_snapshot_for_rtl_only_diff` / `test_n6_missing_doc_bitdef_still_fails_closed` |
| 2 | N6 输入缺 RTL 新行为，prompt 误导地址改写 | targets 增加 `rtl_change`（hunk/行/offset）；prompt 明确地址实参不动、期望值跟 `rtl_change`、SV 十六进制用 `'h` | 同上（断言 `rtl_change` 含 `dcb_wdata[15:0]`） |
| 3 | N8 以文档未同步/既有代码问题反复退回 | prompt：`rtl_change` 优先、`doc_out_of_sync` 记 finding 不退回；checklist 只判 `applied_edits` 触及的行（N8 输入新增 `applied_edits`） | 既有 N8 测试（drill/real standin fail-closed） |
| 4 | `run_guarded.sh` 新环境（无 `SIMLIB_RUN/`）误判锁 | `acquire_lock` 前 `mkdir -p "$ROOT/SIMLIB_RUN"` | `tests/test_fix_kbtools.py::test_run_guarded_fresh_env_without_simlib_run_acquires_lock` |
| 5 | 验收 A51 在 drill 作业瞬间完成时窗口竞态 | A51 改为校验**当前**停放中断的快照（JOB 已消费则校验下一闸门），不放松“干净可恢复”要求 | 端到端 phase1 A51 |

## 5 复跑

```bash
# 场景准备（只动场景副本）
cd /home/work/chenjunming/FPGA_SIM/SCN_RTL_0D04
KB_STRICT=1 bash scripts/setup.sh
python3 scripts/apply_change.py

# real 服务（不设 LOOP_LLM_MODE）
cd /home/work/chenjunming/change-impact-loop/loop
LOOP_ENV_ROOT=/home/work/chenjunming/FPGA_SIM/SCN_RTL_0D04/env \
LOOP_WORKSPACE=/home/work/chenjunming/FPGA_SIM/SCN_RTL_0D04/workspace \
LOOP_PORT=8099 nohup ./run.sh > /tmp/loop_real.out 2>&1 &

# 建 run → G1（human + entry_decisions）→ 轮询；N9 后按范围取消
curl -s -X POST localhost:8099/api/runs -H 'Content-Type: application/json' \
  -d '{"baseline":"v0","mode":"real","scenario":"happy","project":".../SCN_RTL_0D04/env"}'
```

> 场景侧完整记录（含每次重试/时间线）：`SCN_RTL_0D04/results/REAL_RUN_20261020.md`
