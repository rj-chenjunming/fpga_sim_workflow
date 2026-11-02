# 单一 RTL 文件夹一键派生 · 真实链证据（2026-10-30）

> **本目录只增不改**：内容冻结后 `chmod 444`；md5 账本在目录之外
> [`../RTL_FOLDER_ENTRY_20261030.md5`](../RTL_FOLDER_ENTRY_20261030.md5)。
> 规格：[S0 §9](../../spec/S0_ENVIRONMENT_SPEC.md) · [WEB_UI §13](../../spec/WEB_UI_SPEC.md) ·
> [编排 §13](../../spec/LOOP_ORCHESTRATION_SPEC.md) · [ENV §8](../../spec/ENV_PLUGIN_SPEC.md)。
> 计划：[2026-10-30-rtl-folder-one-click](../../plans/2026-10-30-rtl-folder-one-click.md)。

## 1 这份证据证明什么

在**真实环境根**（ENV_ROOT 只读挂载）上，只给一个完整 RTL 文件夹路径，跑完整条链：

1. `POST /api/s0/from-rtl`：选择性复制 + RTL 根部整棵替换 + 六项检查（`copy/rtl/non_rtl/ports/smoke/baseline`）；
2. `POST /api/s0/{id}/advance`：自动三库编译冒烟（基线侧走**只读软链代理根**，基线零写入）→
   `ready_for_execution=true`；
3. `POST /api/s0/{id}/activate`：自动切换（独立 supervisor 子进程 + `/api/health` 校验 `env_root`)；
4. 切换后 `POST /api/runs`（`mode=real`，带 `s0_record_id`）→ 真实跑到 **G1**（N0–N3，N3 走 live 模型）；
5. 人签 `G1=ignored`（逐条理由）→ 本轮正常收口；
6. `POST /api/env/switch-back` → 切回原始根；切回后 `DELETE /api/s0/{id}/copy?confirm=true` 删除副本
   （准备记录保留）；
7. 全程原 `ENV_ROOT` **零写入**（`find -newer` 命中 0 + 记录 `baseline` 检查 passed）。

复现命令（单次 bash 调用内完成，脚本自己跨重启轮询）：

```bash
cd loop
DEST=$PWD/../.dev-ws-lead bash spikes/provision_dev_workspace.sh --link-fixture --force --quiet
.venv/bin/python spikes/verify_rtl_folder_entry.py        # rc=0, PASS=32 FAIL=0
```

## 2 文件

| 文件 | 是什么 |
|---|---|
| `record.json` | 本次 S0 派生记录（六项 checks、`copy_plan`、`rtl_plan`、`folder_warning`、`smoke_case`；`work_env` 已按验证脚本清理） |
| `smoke.json` | 三库冒烟读数（candidate / baseline 两段：rc、命令、日志、error/warning 计数、warning 增量） |
| `env-switch-active.json` | 切换结论（`status=active`、target/origin、requested/finished 时刻） |
| `env-switch-history.jsonl` | 切换只增审计（pending → active → 切回） |
| `env-switch-origin.json` | 原始根与原始数据根记录（派生源恒为它） |
| `verify.log` | 真实链验证脚本完整输出（32 条断言逐条 `[ok]`，末尾 `=> PASS=32 FAIL=0`） |
| `software-gate.log` | 软件层全量单测门输出（`bash spikes/run_software_checks.sh --ignore=tests/browser`）⇒ `1999 passed` |
| `e2e-accept.log` | 端到端终验（`bash spikes/accept_v1_run.sh`）六相 `rc=0` / `=> ALL PASS` |
| `browser-gate.log` | 浏览器门（`pytest -q tests/browser`）⇒ `166 passed` |
| `env-kb-gate.log` | 环境层 + kb 自测统一入口（`--with-kb-selftests`）⇒ `PASS=10/9/28` + `3 passed` + 原 `ENV_ROOT` 零写入 |

## 3 不声称

- **不声称** G1 之后的 N5–N16 真机全跑：本证据只到 G1（签 `ignored` ⇒ HALT），N9 真机全跑（≈19 min/用例）
  按需另跑；
- **不声称**"零必改用例"的 G1 分流已实现：它需要新增闸门枚举与 N5 后条件分支，
  已在 [编排 §13-4](../../spec/LOOP_ORCHESTRATION_SPEC.md) 登记为**本轮不做**；
- **不声称**副本内 drill/演练可用：夹具不复制（副本只服务真实场景，见 S0 §9.3 / 决定 20）。
