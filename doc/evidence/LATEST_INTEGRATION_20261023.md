# 最新代码集成验证记录

日期：2026-10-23。基线：`f69fe46d12ee225ab0a4d01e22a3f068cce4158f`。
同一执行者实现和验证，无独立终验。汇总与未完成项见 [STATUS §44](../STATUS.md)。

## 同步事实

执行 `git fetch origin` 后，`git rev-list --left-right --count HEAD...origin/main` 输出 `0 41`。
`git merge --ff-only origin/main` 成功，从 `8816dbc` 快进到上述基线，无冲突。
同步前工作树干净，当前分支为 `work`；未改写旧提交历史。

四份 `/workspace/scratch/fpga-*.patch` 中的交付证据文件可追溯到祖先 `17650b6`，
该提交祖先检查成功；不重放这些已被后续版本修订的旧补丁。
`git cat-file -t 080c60f7076427f8dd5e083d4cd082a010de9177` 失败，指定 bundle 路径不存在。
用户确认该旧任务修订属于本轮范围；明确待恢复，不以远端全节点面板代替该提交。

## 修复与复现

问题：节点详情汇总 `refs` 已过滤目录外引用，但 `events[].refs` 仍原样返回。
修复仅让事件切片复用 `_split_refs`，增加逐事件 `refs_omitted`；原始事件文件不改写。

新增用例（修复前）命令：

```bash
loop/.venv/bin/python -m pytest -q loop/tests/test_node_detail_refs.py --tb=short
```

原始摘要：`4 failed, 1 passed, 1 warning in 0.79s`。
失败覆盖绝对路径、相对越界、符号链接逃逸，以及真实 API 响应；
独立不传 run_dir 的特征用例通过。

受影响用例（修复后）命令：

```bash
loop/.venv/bin/python -m pytest -q \
  loop/tests/test_node_detail_refs.py loop/tests/test_node_detail_projection.py \
  -k 'not test_endpoint_unknown_node and not test_drill_full_chain and not test_halt_node_projection and not test_g1_material_entries and not test_n0_copies and not test_s0_record_id_roundtrip and not test_s0_record_id_defaults and not test_s0_record_id_survives' \
  --tb=short
```

原始摘要：`32 passed, 8 deselected, 1 warning in 0.91s`。
排除项依赖缺失的内网数据根/drill 夹具；修复前对原文件直接执行实测为
`8 failed, 27 passed, 1 warning in 4.10s`，失败均在创建默认内网数据根时发生。
这些排除项未被认定为通过。

## 集成检查

```bash
LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium loop/.venv/bin/python -m pytest -q \
  loop/tests/browser/test_node_detail.py --tb=short
# 14 passed in 30.24s

loop/.venv/bin/python -m pytest -q \
  loop/tests/test_admission_and_jobs.py::test_job_command_ending_with_exit_still_writes_rc \
  loop/tests/test_api_ui_contract.py::test_frontend_event_whitelist_matches_server_authority --tb=short
# 2 passed, 1 warning in 1.00s

loop/.venv/bin/python kb/tools/_selftest_n2_encoding.py
# PASS 37/37
```

浏览器使用真实静态页与受控 API，未连接真实 provider/仿真器。
warning 为已有 Starlette/httpx 弃用提示；本轮未安装或更新依赖。

## 环境限制与文档门

`bash loop/spikes/run_software_checks.sh --ignore=tests/browser` 在数据根检查处退出，
输出 `[FAIL] 数据根不存在`；该入口无法启动测试，不声称全软件层通过。
完整端到端、gate schema 与 N5 历史夹具自测、真实模型和仿真验收未运行。

`python3 doc/audit/check_doc_links.py` 未通过，原始摘要：
`checked=1633 skipped=20339 historical=857 known_missing=10 env_missing=318 missing=122`。
使用同一检查器、同一三根配置扫描远端基线的所有 Markdown 与当前文档，
路径清单按 Git NUL 分隔读取以保留中文文件名，输出：

```text
missing baseline=122 current=122 added=0
env_missing baseline=318 current=318 added=0
PASS: no added missing or env_missing findings against fetched HEAD
```

首次临时对照脚本使用 Git 默认带引号的文件名清单，遗漏中文路径而误报新增；
已改用 NUL 分隔，以上为纠正后的实际结果。本轮不修改检查器，也不隐藏既有缺件。
本记录写入前的全库诊断计数仅作原始采样；最终状态以 STATUS 中的最终检查为准。

未推送、未发布环境。旧任务提交和完整内网验收仍待补齐。
