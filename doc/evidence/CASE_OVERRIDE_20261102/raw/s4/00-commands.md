# S4 界面（用例判据人签覆写，SPEC-REV-20 §8）· 命令与原始输出索引

写域（Lead 2026-11-02 裁定后）：`loop/web/app.js`、`loop/web/index.html`、`loop/web/node-detail.js`
（**仅** N16 面板的豁免清单）、`loop/tests/browser/test_case_override.py`（新）。
本目录只存原始输出；状态数字以 Lead 的 `doc/STATUS.md` 为准。

| # | 文件 | 命令 | 结果（原始输出） |
|---|---|---|---|
| 01 | `01-api-ui-contract-whitelist.log` | `LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q tests/test_api_ui_contract.py` | `2 failed, 7 passed`；白名单那条已绿（`only_server` 为空）；2 条失败=只读 ENV_ROOT 环境缺件 |
| 01b | `01b-whitelist-red-evidence.log` | 同测试的**红证据**（把 git HEAD 版 app.js 喂给同一条断言） | `only_server= ['case_override']` / `equal= False`（修复前必然红） |
| 02 | `02-required-command.log` | `PLAYWRIGHT_BROWSERS_PATH=… HOME=… TMPDIR=… .venv/bin/python -m pytest -q tests/browser/test_case_override.py tests/test_api_ui_contract.py` | `2 failed, 23 passed`（2 条失败=环境缺件，见下） |
| 03 | `03-browser-full.log` | 同上环境变量 + `pytest -q tests/browser` | 见文件尾行（浏览器门；界面改动必须单独跑） |
| 04 | `04-projection-shape-check.log` | 直接调 `services.contracts.case_override_view` 核对前端消费的字段路径 | 顶层 `enabled`/`blocked_reason` 存在；`cases[].actions.<pass\|revoke>` 形状与 `app.js::overrideActionVerdict` 一致 |
| 05 | `05-web-source-guards.log` | 16 个前端源码守卫/契约单测（capability/gate-session/pane-scroll/web_smoke/node_detail_projection…） | `20 failed, 175 passed`；20 条失败**全部**是 `test_node_detail_projection.py` 的只读 ENV_ROOT 环境缺件（逐条含 `OSError: [Errno 30] Read-only file system`） |

### S4 新浏览器用例先红后绿（原始数字）

- 红（实现前，首次运行；**未落盘**，终端输出为证）：`13 failed in 76.88s`，
  全部失败在 `#gateMaterial [data-case-override]` 等尚未存在的元素/交互上。
- 绿（最后一次，见 02/03）：`tests/browser/test_case_override.py` → `16 passed`。

## 环境缺件（AGENTS §4：不得当通过）

`tests/test_api_ui_contract.py::test_create_run_echoes_project` 与
`::test_gate_material_projection_has_diff_entries` 失败原因（原始）：

```
E  OSError: [Errno 30] Read-only file system:
   '/home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES/kb/runs/RUN-…'
```

两条都要 `POST /api/runs`（drill 写真实数据根）⇒ 需要**可写数据根**；本机 `ENV_ROOT` 只读。
与本次界面改动无关（修复前后同样失败）。

## 行为判据（`tests/browser/test_case_override.py`，16 条）

1. 机器原因 `reasons` **原文**整段可见（长文本/中文标点/枚举原值），证据 `path`/`md5` 同屏，
   机器原判（未通过）不被改写；
2. 二次确认弹窗：原文原因 + 证据 path/md5 + 空理由不可提交 + 文案「这是人签例外，会记入台账；
   报告仍显示本轮未通过」；提交体 `{action,cases,actor,reason}` 精确断言；成功关闭 + toast；
3. 400/403/409/404：显示服务端 `detail.error`（409 读 `detail.reason`）原文、403 的
   `detail.blockers[]` 逐条原样列出，且不含「操作失败」；弹窗保留理由、按钮回可用；
4. 缺 `case_override` 投影：明说「服务端未下发可覆写判定 ⇒ 不可提交」、按钮禁用、**零请求**；
5. 顶层 `enabled=false`：用顶层 `blocked_reason` 驱动禁用（不掺例级原因，两者不混用）；
6. 逐例 `actions.<pass|revoke>.available` 驱动各入口；缺本动作条目 ⇒ 禁用并明说（不顶替）；
7. 「人签豁免」徽标（actor+日期）出现在逐用例表、报告横幅、看板、**N16 面板**，机器原判同屏；
8. 撤销入口与覆写同处、撤销也必填理由、提交 `action="revoke"`；
9. 终态 run：按钮禁用并显示服务端 `blocked_reason`（「本轮已结束，不可撤销」），徽标仍在；
10. 轮询把 `enabled` 降级后 ⇒ 按钮立刻禁用（不缓存旧判定）；取消弹窗不发请求、焦点回触发按钮。
