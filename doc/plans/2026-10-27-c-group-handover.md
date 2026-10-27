# C 组交接单（2026-10-27 收尾）

> **一页给你（或下一位接手人/环境 owner）**：C 组八项现在的处置、四道门数字、**环境侧只剩哪几件事**、
> 以及怎么一条命令验证。细节在 `doc/STATUS.md` §83–§89（每节都带命令输出）。

## 1 C 组八项处置

| 项 | 状态 | 一句话 | 位置 |
|---|---|---|---|
| C13 环境层 3 条用例本机跑不了 | ✅ 已解决 | 派生 ENV_ROOT 副本上跑，`find -newer` 自证原环境零写入 | `loop/spikes/run_env_layer_checks.sh`、§83.1 |
| C14 证据时效 | ✅ 已刷新 | kb 自测重跑：`PASS=10` / `PASS=9` | §83.2 |
| C10 I4 72 条冲突 | ✅ 机制+落账完成，⚠️ 真实环境待写权 | human-only 写入器 + 抽取合并 + 72 条已落账（人批示、Host 代录）+ 生效脚本 | §84/§85/§86/§87 |
| C11 取消作业=整轮失败不可续跑 | ✅ 已裁决 | 维持语义；补「取消后按失败收敛、不能续跑」的确认框/弹窗/toast | §88 |
| C12 运行入口不消费 S0 | ✅ 已裁决 | 「传了才校验」：real 必须记录存在且已准出；drill 只校验格式 | §89 |
| C8 缺"通过形态"（passed）真实夹具 | ⛔ 未做 | 需一次真实通过轮或环境写权；**当前只有 fail 形态 + drill 形态** | 计划 §4 |
| C9 S0-b（接口适配 + 三库冒烟）未接入 | ⛔ 环境侧 | D1–D5；`ready_for_execution` 恒 false 的根因 | S0 规格 §8 |
| I4 真实生效 | ⛔ 环境侧 | 本机 `/home` 是 **ro 挂载**，写不进真实数据根 | §87.4 |

## 2 四道门（本轮实测，数字从命令输出复制）

| 门 | 结果 | 命令 |
|---|---|---|
| 软件层 | **979 passed / 3 deselected / 0 failed**（168.64 s） | `cd loop && bash spikes/run_software_checks.sh --ignore=tests/browser` |
| 浏览器（补充门） | **114 passed**（124.80 s） | `cd loop && PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home TMPDIR=<repo>/.chrome-tmp .venv/bin/python -m pytest -q tests/browser` |
| 端到端 | **ALL PASS，117 断言 / 0 FAIL**（phase 1/2/3/4/4b/5 全 rc=0；50/27/18/8/8/6） | `cd loop && bash spikes/accept_v1_run.sh`（先 `provision_dev_workspace.sh` 并指 `LOOP_WORKSPACE`） |
| 文档 | **missing=0，exit=0** | `python3 doc/audit/check_doc_links.py` |
| kb 自测 + 环境层（一个入口） | `_selftest_gate_schema` **10**、`_selftest_n5_reachability` **9**、`_selftest_adjudicate_conflicts` **28**，FAIL 全 0；env_layer **3 passed / 24 deselected** | `cd loop && bash spikes/run_env_layer_checks.sh --with-kb-selftests`（K1 统一入口：两类检查共用同一个派生 ENV_ROOT 副本，原环境零写入，见 STATUS §94） |

## 3 环境侧只剩三件事（都不在本仓写权内）

### ① 让 I4 的 72 条裁决在真实环境生效

本机 `<ENV_ROOT>/kb` 在 `ro,nosuid,nodev` 的挂载上 ⇒ 写不进。任选其一：

```bash
# 方式 1（推荐）：指向一个**可写数据根**，一条命令完成落账+合并+校验+验证
# ⚠️ 2026-10-27 起要带 --snapshot 指向**当前权威快照**（含 4 条作者确认，76 条记录）；
#    不带则仍是 72 条快照。指纹来源优先级：--expect-md5 ＞ 快照自带 md5.txt ＞ 仅默认快照的内置值（STATUS §98.2）
bash loop/spikes/apply_conflict_adjudication.sh --workspace <可写数据根> --snapshot doc/evidence/adjudication_author_confirm_20261027 --dry-run   # 先体检
bash loop/spikes/apply_conflict_adjudication.sh --workspace <可写数据根> --snapshot doc/evidence/adjudication_author_confirm_20261027
```

- 验收：`[after] blocks_release=0`、`[g3] full_now/subset_only 提交前检查：通过`、
  `[n16] I4 在列=False`（§87.3 有 before/after 对照）。
- 方式 2：`mount -o remount,rw /home`（需管理员）后，直接对真实数据根跑上面命令。
- 方式 3：把 `doc/evidence/adjudication_20261027/adjudication.json` 放进目标数据根 `conflicts/`，
  再 `n1_conflicts.py --outdir <该目录>`。

### ② S0-b 接入（D1–D5）

接口适配（`TB/top.sv`）、逐 hunk 登记、三库冒烟 → 让 `ready_for_execution` 能真为 true。
影响面：`S0Store.get()` 目前**归一为 false** ⇒ 做完 S0-b 后 C12 的"允许路径"自然打开、
C8 的"通过形态夹具"才有环境可以产出。

### ③ C8 通过形态夹具

现在只有 fail 形态（`RUN-20261024-002609`）+ drill 演示夹具（`RUN-20261026-135835`）。
要 passed 形态，需要"一次真实通过轮"或"环境写权 + 在派生副本上跑 real"。

## 4 推送（本机出网被代理拦）

本地领先 `origin/main` **25 个提交**；`git push` 在本机报
`Received HTTP code 503 from proxy after CONNECT`（清代理直连也不可达）。请在能出网的机器：

```bash
cd change-impact-loop && git push origin main
```

**凭据提醒**：之前对话里出现过的 PAT 应立即在 GitHub 作废重签（本仓从未把它写进
`.git/config`/`~/.git-credentials`/任何文件，已核过）。

## 5 接手第一小时建议顺序

1. `git log --oneline -30` 看本轮 25 个提交，重点 `doc/STATUS.md` §83–§89；
2. 跑一遍四道门（§2 表格命令），确认基线与本文档一致；
3. 若目标是"跑通到 N16"：先办 §3-①（I4 生效）→ 再确认 G3 `full_now` 可提交 → 余下挡 N16 的是
   `I2_CASES_PENDING` / `I3_EVIDENCE_MISSING` / `E2` 等，不是 I4；
4. 若目标是"演示"：`doc/evidence/DEMO_FIXTURE_20261026.md` 里那套 drill 夹具可直接演四屏；
5. **别踩的坑**：跑文档门前先 `bash loop/spikes/provision_dev_workspace.sh --cleanup`
   并 `bash loop/spikes/run_env_layer_checks.sh --cleanup`（否则派生副本里的环境文档会被算成 missing；
   2026-10-27 已给检查器加跳过规则，且 `.env-copy/` 已按 K3 清理，但重跑环境类检查后仍要清）；
   `loop/.venv/bin/python` 才是带依赖的解释器。

## 6 已知未做（不藏）

- ~~B 组遗留：服务端 403 串仍写"接受失败报告"~~ —— **已关闭（2026-10-27，STATUS §92）**：403 串与成功 warning 统一为"未通过"，判据零变化，证据见 `doc/evidence/SPEC_REV05_RECHECK_20261027.md`。
- `workspaces/real-env-copy/loop/web/index.html` 是 ignored 的旧版派生副本，仍含已删除的
  `GATE_DECISIONS_FALLBACK`；不在产品路径。**2026-10-27 K2 处置**：已在该目录加
  `OBSOLETE-20261027.md`（已过期横幅，带 index.html 的 md5 `6017b1383436d5f99cff41bbfd0f0a10`
  与 2 处行号）；未删除的理由见横幅与 STATUS §94。
- 4 条 Tier B-core 的取值是**人给的方向**（C2/C11/C38 以位定义为准、C58 以 DFX_VERSION 为基准），
  作者若另有口径，按追加改判处理。
- I4 裁决的 actor 是 `human:chenjunming`，但写入由 Host 工具代录（每条 resolution 末尾已注明）；
  要亲笔请在有写权环境按 §3-① 重签（追加记录，不改历史）。
