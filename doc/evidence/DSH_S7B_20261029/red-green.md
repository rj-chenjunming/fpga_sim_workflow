# S7b RED → GREEN（数字从命令输出复制）

> 片：S7b（tool-allowlist）。用例文件 `loop/tests/test_dsh_tool_allowlist.py`（61 例）。
> 纪律：先写失败用例再实现；判据只加严、不放宽（bwrap/双钉未动，未给 `danger-full-access`，
> 白名单不代替效果隔离）。

## 1 基线（改动前）

```
cd loop && LOOP_WORKSPACE=<repo>/.dev-ws .venv/bin/python -m pytest -q \
  tests/test_dsh_selfcheck.py tests/test_dsh_backend.py tests/test_dsh_admission.py
118 passed in 6.38s
```

## 2 RED

```
cd loop && .venv/bin/python -m pytest -q tests/test_dsh_tool_allowlist.py
ImportError: cannot import name 'dsh_allowlist' from 'host.agent_backends'
1 error in 0.18s
```

## 3 GREEN（逐步）

| 步 | 命令 | 结果 |
|---|---|---|
| Host 判据（插件未写） | `pytest -q tests/test_dsh_tool_allowlist.py -k "not plugin and not real_dsh and not verify_session"` | `31 passed, 16 deselected in 0.66s` |
| 插件（真 `dsh-tools` 内核，离线） | `pytest -q tests/test_dsh_tool_allowlist.py -k plugin` | 首跑 `10 passed, 1 failed` —— 失败是**用例自身的职责放错**（把自检的回显职责写到插件上）；按"插件=判据 / 自检=回显"改正后全绿（**收窄职责，不是放宽判据**） |
| 全文件 | `pytest -q tests/test_dsh_tool_allowlist.py` | **61 passed in 8.47s** |
| 真机三例（不 skip） | `pytest -q tests/test_dsh_tool_allowlist.py -k real_dsh` | `3 passed, 57 deselected in 7.52s` |

## 4 接线后复跑（Lead 接 `dsh.py` + `SETTINGS.yaml` 之后）

| 组 | 命令 | 结果 |
|---|---|---|
| S7b 用例 | `pytest -q tests/test_dsh_tool_allowlist.py` | **61 passed in 8.76s** |
| 三文件回归 | `pytest -q tests/test_dsh_selfcheck.py tests/test_dsh_backend.py tests/test_dsh_admission.py` | **118 passed in 5.98s**（与基线同数） |
| 八个 dsh 文件 | `pytest -q tests/test_dsh_{assets,backend,admission,candidate,process,sdk,selfcheck}.py tests/test_dsh_tool_allowlist.py` | **276 passed in 21.68s** |

## 5 真机（接线后，带模型 1 次）

| 阶段 | 结果 |
|---|---|
| `RUN-20261029-103000/N6/1` | `completed`、wall **164.266 s**、`validation.ok=True`、submit accepted |
| 发给模型的工具 | `request/header.data.header.tools` = **7 项**（`bash, edit, glob, grep, read, submit_result, write`） |
| 模型实际调用 | `bash`×13 / `read`×9 / `submit_result`×1；`tool/result` 23 条、`isError` **0** |
| `n6_apply` | **`applied`**（`submit_result` 在收窄后真的可用） |

## 6 已知的**预存在** flake（非本片引入）

`tests/test_dsh_selfcheck.py::test_on_start_failure_stops_group_and_raises` 在**并发**跑门时偶发单点
`ValueError`（`int(pidfile.read_text())` 读到 stub 尚未写完的空文件）；单跑通过、复跑全绿。
本片未改它（不在本片判据面），照实登记。
