# 上游 latest 集成与编号归一（2026-10-23 深夜）

基线：`origin/main` = `47893ce`（含 `356dc7c` 引用边界修复、`d1b5ae9` SPEC-08 DSH 草案、
`47893ce` SPEC-09 AI 面板草案）；本地 `33d8530` + 未提交 WIP。同一执行者实施与验证，**无独立终验**。

集成先在独立 worktree/分支完成，随后按用户要求**直接快进合入 `main`**：`main` 从 `33d8530`
快进到合并点 `317df8c`（后续 `ae7e24c` 仅补本文档记录），工作树干净；合并用的 worktree/分支已删除。`18098`/`8099` 服务实例与停在
`waiting_gate` 的 `RUN-20261023-213737` 未重启、未改写。

## 1 同步事实

- `git fetch origin`：首次经代理 503，重试成功；`origin/main` 由 `f69fe46` 前进到 `47893ce`（+3 提交、16 文件、+931/−57）。
- 本地：`main` 在 `33d8530`（ahead 1 / behind 3）；工作树 33 个已跟踪修改 + 17 项未跟踪（节点面板 R3 线）。
- 提交级 `git merge-tree` 无冲突；带 WIP 合并冲突仅 3 个文档：`doc/README.md`、`doc/STATUS.md`、
  `doc/spec/WEB_UI_SPEC.md`。`loop/services/node_view.py` 自动合并，上游 `_slice(events, run_dir)`
  与本地 `story` 投影共存。

## 2 编号裁定（方案①）

- 上游已发布 `SPEC-REV-02`（DSH）与 `SPEC-REV-03`（AI 面板），两者保持不动。
- 本地节点面板修订线 `SPEC-REV-02` → **`SPEC-REV-04`**；文件 `doc/spec/SPEC-REV-02-20261023.md`
  → `doc/spec/SPEC-REV-04-20261023.md`。原内容 md5 `32edea0699123f51bc6aebe4da3b3d4f`；
  改名后除编号替换外正文未改（迁移记录写在文件头）。
- STATUS：上游 §44（集成）/§45（DSH）/§46（AI 面板）保留；本地原 §44、§45、§47–§50
  顺延为 **§47、§48、§49–§52**；原预留 S0-a 的 §53 让位给本节，S0-a 改为 **§54**。
- 引用更新：本地线 22 个文件、92 处 `SPEC-REV-02` 引用（其中 `SPEC-REV-01` 的“后续依次 REV-02”
  通用提示保留不动）；STATUS 节号与子节号同步。

## 3 冲突解决

| 文件 | 处理 |
|---|---|
| `doc/README.md` | 编号块合并为 REV-04（节点面板）/03（AI 面板）/02（DSH）/01（已生效），后续依次 05 |
| `doc/STATUS.md` | 上游 §44–46 在前，本地 §47–52 顺延在后；无重号 |
| `doc/spec/WEB_UI_SPEC.md` | 保留上游 SPEC-09 提示与 §6.7 逐事件引用边界；来源行改为 REV-04；样例补 `events[].refs/refs_omitted` |
| `loop/services/node_view.py` | 自动合并：上游边界修复 + 本地 `story/gate/report` 均保留 |

## 4 语义接线

1. 上游新增 `loop/tests/test_node_detail_refs.py` 的端到端用例使用 `SimpleNamespace` 假 manager，
   而本地 `api.get_node_detail` 会调用 `manager.run_view(run_id)`；夹具补 `run_view=lambda _id: None`。
2. 前端 `loop/web/node-detail.js` 原来只渲染 `event.refs`、不读 `refs_omitted`，合并后目录外引用会静默消失；
   现在逐事件显示「另有 N 条运行目录外引用未展示」（只给条数，不给路径）。

## 5 验证（本 worktree，命令输出复制）

| 检查 | 结果 / 边界 |
|---|---|
| `pytest -q tests/test_node_detail_refs.py tests/test_node_story.py tests/test_node_registry.py` | **113 passed**, 1 warning, 1.12s |
| 浏览器 `tests/browser/test_node_detail.py`（系统 Chrome） | **43 passed**, 54.76s |
| `pytest -q tests/test_web_smoke.py tests/test_node_registry.py` | **8 passed**, 0.78s |
| `pytest -q tests/test_node_detail_projection.py` | 41 passed, **20 failed**：全部 `OSError [Errno 30]` 写默认数据根只读，环境限制 |
| `pytest -q tests/test_api_ui_contract.py` | 7 passed, **2 failed**：同因只读数据根 |
| `python3 doc/audit/check_doc_links.py` | `checked=1791 skipped=22621 historical=857 known_missing=10 env_missing=19 missing=22`，exit=1；22 条全部为 worktree 缺少的数据根路径（workspaces 运行目录与工具缓存），**无本仓文档断链** |
| `git diff --check` | 通过 |
| **合入 main 后复跑**：定向单测 | **113 passed**, 1 warning, 1.12s |
| **合入 main 后复跑**：节点详情浏览器 | **43 passed**, 55.29s |
| **合入 main 后**：`python3 doc/audit/check_doc_links.py` | `checked=1807 skipped=22704 historical=857 known_missing=10 env_missing=19 missing=0`，exit=0 |

未运行：完整软件层、kb gate schema/N5 自测、端到端、真实模型/仿真、真 DSH 接入。
已推送 `origin/main`（合并点 `317df8c`）；环境未发布。

## 6 落地结果与剩余事项

- 已直接快进合入：`main` = `317df8c`（`e7528fe` 保全 WIP → `4b3995c` 编号归一 → `f59be22` 合入
  `47893ce` → `317df8c` 接线+证据）。合并前核对：33 个已跟踪修改与 31 个未跟踪文件逐文件哈希一致；
  原 WIP 完整在 main 历史中。
- 合并用的临时 worktree `.tmp/integration-20261023` 与分支 `integration/20261023-specmerge` 已删除；
  `.tmp/restart_watch.log` 在合并后仍写 `new_code=NO`，服务端口未变化，run 仍 `waiting_gate`。
- 已推送 `origin/main`（`47893ce..0ed54d6 main -> main`，快进成功）。仍待补：完整软件层、kb 自测、
  端到端、真实模型/仿真与真 DSH 接入（内网数据根就绪时）。
