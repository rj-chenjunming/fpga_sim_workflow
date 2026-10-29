# 附录 A · 冻结完整性、门数字对照、材料面复算

> 复核对象：`7b38c0e` 的 S7 最终树 + 四份冻结证据档。本附录全部是**命令原始输出**或**由 raw 件复算**。
> 报告正文：[AUDIT-20261029-s7.md](../AUDIT-20261029-s7.md)。

## 1 冻结完整性（开工提示词 §5.1-1，**校验失败即停手**）

```text
$ cd doc/evidence && for f in A B C D; do md5sum -c DSH_S7${f}_20261029.md5; echo rc=$?; done
$ md5sum -c DSH_S7A_20261029.md5
DSH_S7A_20261029/raw/attempts_corrections.jsonl: OK
DSH_S7A_20261029/raw/attempts.jsonl: OK
DSH_S7A_20261029/raw/material_face_before_after.md: OK
DSH_S7A_20261029/raw/n6_attempt_record_summary.json: OK
DSH_S7A_20261029/raw/n6_selfcheck_summary.json: OK
DSH_S7A_20261029/raw/n6_session_summary.json: OK
DSH_S7A_20261029/raw/probe_s7a.py: OK
DSH_S7A_20261029/raw/s7a_dry_run.json: OK
DSH_S7A_20261029/raw/s7a-gate1-unit.log: OK
DSH_S7A_20261029/raw/s7a-gate2-kb.log: OK
DSH_S7A_20261029/raw/s7a-gate3-e2e.log: OK
DSH_S7A_20261029/raw/s7a-gate4-doc.log: OK
DSH_S7A_20261029/raw/s7a_live_RUN-20261029-100500.json: OK
DSH_S7A_20261029/raw/s7a_offline_chain.json: OK
DSH_S7A_20261029/raw/s7a_replay_apply_RUN-20261029-100500.json: OK
DSH_S7A_20261029/README.md: OK
DSH_S7A_20261029/red-green.md: OK
rc=0
$ md5sum -c DSH_S7B_20261029.md5
DSH_S7B_20261029/raw/attempts.jsonl: OK
DSH_S7B_20261029/raw/boot2_echo.json: OK
DSH_S7B_20261029/raw/boot2_request_tools.json: OK
DSH_S7B_20261029/raw/boot3_echo.json: OK
DSH_S7B_20261029/raw/boot3_request_tools.json: OK
DSH_S7B_20261029/raw/dsh_py_wiring.diff: OK
DSH_S7B_20261029/raw/n6_request_tools.json: OK
DSH_S7B_20261029/raw/n6_selfcheck_allowlist.json: OK
DSH_S7B_20261029/raw/n6_tool_calls.json: OK
DSH_S7B_20261029/raw/README.txt: OK
DSH_S7B_20261029/raw/s7a_live_RUN-20261029-103000.json: OK
DSH_S7B_20261029/raw/s7b-gate1-unit.log: OK
DSH_S7B_20261029/raw/s7b-gate2-kb.log: OK
DSH_S7B_20261029/raw/s7b-gate3-e2e.log: OK
DSH_S7B_20261029/raw/s7b-gate4-doc.log: OK
DSH_S7B_20261029/raw/submit_result_dispatch.json: OK
DSH_S7B_20261029/README.md: OK
DSH_S7B_20261029/red-green.md: OK
rc=0
$ md5sum -c DSH_S7C_20261029.md5
DSH_S7C_20261029/raw/b_anon_api.txt: OK
DSH_S7C_20261029/raw/b_anon_index.txt: OK
DSH_S7C_20261029/raw/b_api_auth.txt: OK
DSH_S7C_20261029/raw/b_mux_noupgrade.txt: OK
DSH_S7C_20261029/raw/EVIDENCE.md: OK
DSH_S7C_20261029/raw/h_anon_api.txt: OK
DSH_S7C_20261029/raw/h_anon_index.txt: OK
DSH_S7C_20261029/raw/h_api_auth.txt: OK
DSH_S7C_20261029/raw/h_asset_anon.txt: OK
DSH_S7C_20261029/raw/h_asset_auth.txt: OK
DSH_S7C_20261029/raw/h_index_auth.txt: OK
DSH_S7C_20261029/raw/h_manifest.txt: OK
DSH_S7C_20261029/raw/h_mint.txt: OK
DSH_S7C_20261029/raw/h_mux_noupgrade.txt: OK
DSH_S7C_20261029/raw/iframe.png: OK
DSH_S7C_20261029/raw/probe2_report.txt: OK
DSH_S7C_20261029/raw/probe3_iframe.py: OK
DSH_S7C_20261029/raw/probe3_report.txt: OK
DSH_S7C_20261029/raw/probe_s7c_wired.py: OK
DSH_S7C_20261029/raw/proxy_top.png: OK
DSH_S7C_20261029/raw/s7c-gate1-unit.log: OK
DSH_S7C_20261029/raw/s7c-gate2-kb.log: OK
DSH_S7C_20261029/raw/s7c-gate3-e2e.log: OK
DSH_S7C_20261029/raw/s7c-gate4-doc.log: OK
DSH_S7C_20261029/raw/s7c-gate5-browser.log: OK
DSH_S7C_20261029/raw/version.txt: OK
DSH_S7C_20261029/raw/wired_report.json: OK
DSH_S7C_20261029/README.md: OK
DSH_S7C_20261029/red-green.md: OK
rc=0
$ md5sum -c DSH_S7D_20261029.md5
DSH_S7D_20261029/raw/s7d-gate1-unit.log: OK
DSH_S7D_20261029/raw/s7d-gate2-kb.log: OK
DSH_S7D_20261029/raw/s7d-gate3-e2e.log: OK
DSH_S7D_20261029/raw/s7d-gate4-doc.log: OK
DSH_S7D_20261029/raw/s7d-gate5-browser.log: OK
DSH_S7D_20261029/README.md: OK
rc=0
```

**汇总（由上面的输出计数，不是手算猜的）**

| 档 | 校验行 | OK | FAILED | rc |
|---|---|---|---|---|
| `DSH_S7A_20261029.md5` | 17 | 17 | 0 | 0 |
| `DSH_S7B_20261029.md5` | 18 | 18 | 0 | 0 |
| `DSH_S7C_20261029.md5` | 29 | 29 | 0 | 0 |
| `DSH_S7D_20261029.md5` | 6 | 6 | 0 | 0 |
| **合计** | **70** | **70** | **0** | **0** |

⇒ 与交接说明「共 70 件、`md5sum -c` 全绿」一致；**校验通过，按纪律继续复核**。

## 2 四片门日志 ↔ STATUS 数字对照

命令：`tail -3 raw/<门日志>`（数字从日志尾行复制；STATUS 见 §118.4/§119.4/§120.4/§121.4）

| 门 | 冻结日志原文（尾行） | STATUS 声称 | 一致？ |
|---|---|---|---|
| S7a 单测 | `3 failed, 1655 passed, 1 warning, 137 errors in 396.97s (0:06:36)` | 同 | ✅ |
| S7b 单测 | `3 failed, 1716 passed, 1 warning, 137 errors in 401.43s (0:06:41)` | 同 | ✅ |
| S7c 单测 | `3 failed, 1766 passed, 1 warning, 140 errors in 430.39s (0:07:10)` | 同 | ✅ |
| S7d 单测 | `3 failed, 1770 passed, 1 warning, 141 errors in 431.96s (0:07:11)` | 同 | ✅ |
| S7a 文档 | `65 passed in 2.44s` | 65 passed | ✅ |
| S7b 端到端 | `phase 5    rc=0` / `=> ALL PASS` | ALL PASS | ✅ |
| S7c 浏览器 | `141 passed in 148.08s (0:02:28)` | 141 passed | ✅ |
| S7d 浏览器 | `142 passed in 150.19s (0:02:30)` | 142 passed | ✅ |

3 条 `failed` 的身份（`grep '^FAILED' s7d-gate1-unit.log`）：

```text
FAILED tests/test_archive_e2.py::test_guard_compile_only_archives_evidence_readonly
FAILED tests/test_archive_e2.py::test_guard_archive_is_bounded_and_excludes_guard_log
FAILED tests/test_projection_and_frozen.py::test_frozen_witness_before_after_drill_run
```

与 kb 门日志里登记的环境层用例一致（`test_archive_e2 ×2、test_projection_and_frozen ×1`），
kb 门尾行：`3 passed, 24 deselected in 16.08s` + `[info] 原 ENV_ROOT 零写入（find -newer 命中 0）`
+ `PASS=10 / PASS=9 / PASS=28`（`FAIL=0`）⇒ 与 STATUS 一致。

## 3 材料面数字复算（P1-1 的依据）

### 3.1 证据档里的两个数（互相矛盾）

```text
$ python3 -c "import json;d=json.load(open('doc/evidence/DSH_S7A_20261029/raw/s7a_dry_run.json'));print(d['target'], d['material_face']['total_bytes'], [(s['name'],s['size']) for s in d['material_face']['staged']])"
tc_bmc_i2c_03 16757 [('TESTLIB/tc_bmc_i2c_03.sv', 15470), ('n6_impact_summary.json', 1287)]
```

```text
$ python3 -c "import json;d=json.load(open('doc/evidence/DSH_S7A_20261029/raw/n6_attempt_record_summary.json'));m=d['attempt_workspace']['materials'];print('staged count =',len(m));print('total bytes =',sum(x['size'] for x in m));print([(x['name'],x['size']) for x in m])"
staged count = 6
total bytes = 100368
[('n6_impact_summary.json', 1287), ('TESTLIB/tc_bmc_i2c_03.sv', 15470), ('TESTLIB/tc_bmc_i2c_04_dfx.sv', 24985), ('TESTLIB/tc_bmc_spi_03.sv', 17214), ('TESTLIB/tc_cpu_i2c_03.sv', 21282), ('TESTLIB/tc_pcie_rw_02.sv', 20130)]
```

一次性工作区实测（同一次真机 attempt 的 `input/` 原始目录）：

```text
$ find loop/.logs/s7a/ws/runs/RUN-20261029-100500/agent_workspaces/N6/attempt-000001/input -type f -printf "%s\n" | paste -sd+ | bc
100368
```

⇒ **16757 是单目标 dry-run 的数；真机 `input/` 是 100368 B。** 生产侧会 stage 全部 target
（`workflows/chunks/model_request.py:98-120` 遍历 `targets`；同一真机 `targets` 为 5 个，
见 `n6_attempt_record_summary.json.targets`）。

### 3.2 复算

```text
$ python3 -c "
before=528122; summary=1287; testlib=15470+24985+17214+21282+20130; real=summary+testlib
print('run-artifact portion: %d -> %d = %.2f%% reduction' % (before, summary, (1-summary/before)*100))
print('TESTLIB staged (5 files) =', testlib, '| real input/ =', real)
print('like-for-like before =', before+testlib, '| reduction = %.2f%%' % ((1-real/(before+testlib))*100))
print('claimed 16757 = %.2f%% from 528122' % ((1-16757/before)*100))"
run-artifact portion: 528122 -> 1287 = 99.76% reduction
TESTLIB staged (5 files) = 99081 | real input/ = 100368
like-for-like before = 627203 | reduction = 84.00%
claimed 16757 = 96.83% from 528122
```

⇒ 「−96.8%」只在「单目标 dry-run 的 after / 不含 TESTLIB 的 before」这一错配口径下成立。

### 3.3 派生摘要不含原文（正面结论的证据）

```text
$ python3 -c "import json;s=json.load(open('loop/.logs/s7a/ws/runs/RUN-20261029-100500/agent_workspaces/N6/attempt-000001/input/n6_impact_summary.json'));print(sorted(s));print(sorted(s['cases'][0]))"
['cases', 'must_change_count', 'schema', 'source', 'version']
['case', 'entry_id', 'file', 'line', 'offset', 'rtl_files', 'segment']
```

源件 `n5_impact.json` 的 `must_change[0]` 字段为
`['accessed_at','basis','case','entry_id','evidence_chain','file','line','offset','rtl_files','segment','site_bucket','why']`
（实测），其中 `basis`/`evidence_chain`/`why`/`accessed_at`（含 `callee`/`addr` 等业务正文）**均未投影**。

## 4 真机 attempt 记账（只增不改核对）

```text
$ cat doc/evidence/DSH_S7A_20261029/raw/attempts.jsonl
{"attempt_key": "RUN-20261029-100500/N6/1", "exit": "completed", "wall_s": 127.234, "usage": {"inputTokens": 176, "outputTokens": 651, "totalTokens": 72379, "cacheReadTokens": 71552}, "session_id": "session-3f1df466-cab1-4c83-b45e-369d5f37e30a", "attempt_record": "agent_calls/N6/attempt-000001", "stop_confirmed": "stopped", "validation_ok": true, "apply_status": "failed", "error": null}

$ cat doc/evidence/DSH_S7A_20261029/raw/attempts_corrections.jsonl
{"attempt_key":"RUN-20261029-100500/N6/1","field":"apply_status","observed":"applied","reason":"探针 bug：live 模式只把 1 个 target 喂给 n6_apply，而 n6_author 按夹具构建全部 5 个目标并产出 5 份候选 ⇒ Host 正确 fail-closed（revision 含非目标用例）。按同一次真实 attempt 的候选与封存输出重放 n6_apply ⇒ applied（raw/s7a_replay_apply_RUN-20261029-100500.json）。原行不回填。","path":"agent_workspaces/N6/attempt-000001/work/candidate/TESTLIB/"}
```

⇒ 原行 `apply_status: failed` **未被回填**，更正另起一行 ⇒ 只增不改成立（与 STATUS §118.3 的限定一致）。
`DSH_S7B_20261029/raw/attempts.jsonl` 同样 1 行（`apply_status: applied`，`wall_s 164.266`）。

## 5 S7b 请求体层面证据（关键 raw 原文）

```text
$ python3 -c "import json;d=json.load(open('doc/evidence/DSH_S7B_20261029/raw/n6_request_tools.json'));print(d['tools_count'], d['tools'])"
7 ['bash', 'edit', 'glob', 'grep', 'read', 'submit_result', 'write']

$ python3 -c "
import json
d=json.load(open('doc/evidence/DSH_S7B_20261029/raw/n6_selfcheck_allowlist.json'))
def find(o):
    if isinstance(o,dict):
        if 'allowlist' in o: return o
        for v in o.values():
            r=find(v)
            if r: return r
    return None
al=find(d)['allowlist']
print('allowed =', len(al['allowed']), al['allowed'])
print('effective =', len(al['effective']), al['effective'])
print('agentScope.names =', len(al['agentScope']['names']))
print('denied =', len(al['denied']))
print('unknownAllowed =', al.get('unknownAllowed'))
print('probe =', json.dumps(al['probe'], ensure_ascii=False))
"
allowed = 7 ['read', 'write', 'edit', 'glob', 'grep', 'bash', 'submit_result']
effective = 7 ['bash', 'edit', 'glob', 'grep', 'read', 'submit_result', 'write']
agentScope.names = 7
denied = 19
unknownAllowed = []
probe = {"attempted": true, "name": "job_list", "denied": true, "code": "TOOL_NOT_ALLOWLISTED", "reason": "工具 \"job_list\" 不在本 attempt 的工具白名单内；允许的工具：read, write, edit, glob, grep, bash, submit_result。请改用允许的工具完成任务。", "at": "2026-10-29T02:23:45.940Z"}

$ python3 -c "import json;d=json.load(open('doc/evidence/DSH_S7B_20261029/raw/boot3_request_tools.json'));print('boot3 toolCount =', d['requestHeaders'][0]['toolCount'])"
boot3 toolCount = 26
```

⇒ 「26 → 7」是**请求体 / 自检回显**层面的事实；回退档（boot3）请求体仍是 26 项。

## 6 文档门（仓库级断链扫描）实测

S7 四片收口记录里的「文档门 = `65 passed`」跑的是 `pytest tests/test_doc_links.py`，那是**检查器分类逻辑**
的表驱动用例（65 条），**不做全库扫描**。按 STATUS 自己的门定义（§0 表 / §5 表：`python3 doc/audit/check_doc_links.py`
⇒ `missing=0`）实际运行仓库级扫描：

```text
$ python3 doc/audit/check_doc_links.py
checked=2783 skipped=39520 historical=857 known_missing=12 env_missing=33 missing=3
[MISSING] doc/STATUS.md:4913  loop/.dev-ws
[MISSING] doc/agents/开工提示词_S7-暴露面收敛与真机收口.md:96  doc/evidence/DSH_S7_20261029/
[MISSING] doc/audit/AUDIT-20261026-a-group.md:298  kb/tools/__pycache__/kb_lib.cpython-38.pyc
```

- 第 2 条是 **S7 交接件引入**的（`git show 7b38c0e:"doc/agents/开工提示词_S7-…md" | sed -n '96p'` 可见原文
  「证据目录 `doc/evidence/` + `DSH_S7_20261029`（或 S7a 单独）」；该目录从未存在，实际交付是四份
  `DSH_S7{A,B,C,D}_20261029/`）；
- 第 1、3 条为既有（前者是 gitignored 数据根路径，后者是旧的 `__pycache__` 路径）。

> 上表是**复核时（2026-10-29）快照**；P2-13 已移交 Lead 修，断链数会随 Lead 的修复变化，
> 本附录不追踪「修复后」的数字（本报告只记录复核时事实）。

⇒ 登记 P2-13；**不据此否定 S7 四片的门数字**（它们报的「65 passed」确实是该命令的真实输出），
但「文档门」若按 STATUS 自己的定义验收，当前不是 0 断链。
