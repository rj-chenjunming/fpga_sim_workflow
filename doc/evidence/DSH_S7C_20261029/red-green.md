# S7c RED → GREEN 与真机发现（数字从命令输出复制）

> 片：S7c（DSH Web 实例落账 + 同源反代真机）。三个用例文件：
> `test_dsh_web_instance.py`（30）、`test_instance_proxy.py`（S4 45 + S7c 8 + token 脱敏 3）、
> `test_web_instance_ctl.py`（9）、`tests/browser/test_s4_projection_ui.py`（+3）。
> 纪律：先失败用例再实现；反代 R1–R20 判据**一处未放宽**。

## 1 `dsh_web_instance`（模块）

| 阶段 | 命令 | 结果 |
|---|---|---|
| RED | `pytest -q tests/test_dsh_web_instance.py` | `1 error during collection`（`ImportError: cannot import name 'dsh_web_instance'`） |
| GREEN 第 1 轮 | 同上 | `1 failed, 29 passed` —— 失败为**配置期未校验 host/port**（真缺陷）⇒ 加 `validate_values()` |
| GREEN 终 | 同上 | **30 passed in 2.49s** |

## 2 `instance_proxy`（可用性字段 + token 脱敏）

| 阶段 | 命令 | 结果 |
|---|---|---|
| RED（`stream` 字段） | `pytest -q tests/test_instance_proxy.py -k s7c_availability` | `1 failed`（`no attribute 'STREAM_HTTP_ONLY'`） |
| GREEN 中间 | `pytest -q tests/test_instance_proxy.py` | 52 passed（另一条失败是**用例自身断言写错**：Origin 应为 `http://authority`） |
| GREEN 终 | 同上 | **53 passed**（S4 原 45 例**零回归**，+8 例） |

## 3 `web_instance_ctl`（Lead 接线层）

| 阶段 | 命令 | 结果 |
|---|---|---|
| 首跑 | `pytest -q tests/test_web_instance_ctl.py` | `2 failed, 7 passed` —— 两条**真机**用例失败，原因是**用例夹具**把 `bin` 指向了 `SETTINGS.yaml`（不是 dsh 安装树）⇒ `exited_before_launch rc=1`；换成仓内真实 `node`/`bin`/指纹后通过（**修夹具，不是放宽断言**） |
| GREEN | 同上 | **9 passed in 10.58s**（含 2 条真机用例：起实例→落账→读者读回→停后降级；换 attempt 替换实例） |

## 4 真机发现（P2）：uvicorn access log 记录首跳 `?token=`

**怎么发现的**：接线后整链真机复核（`probe_s7c_wired.py`）末尾有一条硬断言
「token 不得出现在看板日志」，**首次为红**：

```
AssertionError: token 出现在看板日志里
```

根因：uvicorn 的 access log 打印完整 request line，而首跳就是
`GET /instance/<run>/<node>/<n>/?token=<43 chars>`（REV-16 §5.4 设计的交换入口）。
§5.4 同时要求 token **永不出现在本服务日志** ⇒ 真机缺陷。

**修复**：`services/instance_proxy.py` 新增 `TokenRedactFilter`（import 即生效、幂等），把
`token=<值>` 渲染成 `token=<redacted>`；**只改日志文本**，请求/响应/元数据不变。
**修复后**同一断言转绿：`token_in_dashboard_log=0`。

**用例**（finding-driven，先有红断言后有实现，照实说明顺序）：

| 阶段 | 命令 | 结果 |
|---|---|---|
| 首跑 | `pytest -q tests/test_instance_proxy.py` | `3 failed, 53 passed` —— 3 条失败是**用例自身**写错模块别名（`IP.` 而非 `instance_proxy.`），不是实现缺陷 |
| GREEN | 同上 | **56 passed** |

## 5 浏览器（改了界面 ⇒ 必跑）

| 阶段 | 命令 | 结果 |
|---|---|---|
| 单文件（`s7c-proxy`） | `pytest -q tests/browser/test_s4_projection_ui.py` | `27 passed in 30.33s`（原 24 + 3） |
| 单文件（`s7c-proxy`） | `pytest -q tests/browser/test_agent_window.py` | `9 passed in 11.10s` |
| **全量浏览器门（Lead 独占）** | 见 STATUS §120.4 | **141 passed in 148.08s**（S4 收口 138 + 3） |

## 6 数据根污染（一次假红，照实登记）

S7c 单测门首跑出现 `72 failed, 1691 passed, 6 skipped, 140 errors`，根因是
**`.dev-ws` 数据根被前面的探针留成半成品**（drill 夹具 `RUN-20261015-120626` 缺件 ⇒
`drill 夹具不完整`；连带 17 个 `test_flow`/15 个 `test_fix_lifecycle` 与浏览器用例集体红）。
`provision_dev_workspace.sh --cleanup` 后重建再跑即恢复 —— 与代码无关，**不是回归**。
（§8 已知坑同类：假红要用**全新数据根单独复跑**取证后再定性。）
