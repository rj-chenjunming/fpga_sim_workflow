# T2 跑前快照（卡点 B 前置只读准备）

- 角色：`simenv-runner`（用例执行）
- 共享任务：`task-2`（rev=2，`blockedBy=[task-1]`，`ready=false`）
- 快照时刻：2026-10-13（会话内实测）
- 结论：**只读准备完成；用例文件尚未产出（task-1 未完成）→ 未执行编译，等待 Lead 放行**

## 1 环境事实（命令输出原文）

| 项 | 命令 | 结果 |
|---|---|---|
| 工具路径 | `command -v uvlan uvs` | `/home/soft/UNIVISTA/20260917/UVS/bin/uvlan`、`/home/soft/UNIVISTA/20260917/UVS/bin/uvs`（rc=0，与角色定义 §1 一致） |
| 脚本语法 | `bash -n doc/tools/compile_only.sh` | rc=0（语法 OK） |
| 脚本用法 | `./doc/tools/compile_only.sh -h` | 正常打印 usage 段（rc=1 系 `usage()` 内 `exit 1` 的设计行为，非报错） |
| VENDOR 宏 | `grep -nE 'VENDOR_[A-Z]+' all_define.txt` | 第 3 行 `-define   VENDOR_PANGO`（第 4 行 `VENDOR_XILINX` 已注释）✅ |
| 磁盘 | `df -h .` | 22T 总量 / 19T 可用（12% 使用）✅ |

## 2 uvs.setup 现状（全局单文件，串行关键）

```
diff uvs.setup doc/_run_artifacts/uvs.setup.orig   → diff_rc=0（完全一致）
md5sum doc/_run_artifacts/uvs.setup.orig           → a80f7b6ca48a7961a107bbe871af761d
md5sum uvs.setup                                   → a80f7b6ca48a7961a107bbe871af761d
```

## 3 基线产物

```
stat -c'%s %y %n' LOG/tc_dom_polling_new_01_1_run.log
→ 220150 2026-10-10 10:58:46.208001995 +0800 LOG/tc_dom_polling_new_01_1_run.log

ls LOG/ | wc -l            → 78
ls SIMLIB_RUN/log/         → tc_dom_polling_new_01_1_run.log   （仅 1 个文件）
```

与 Lead 给的基线（220150 字节 / 10-10 10:58）**一致** ✅

## 4 串行确认（卡点 D 前置）

```
ps -ef | grep -E "uvlan|uvs |run_local|compile_only" | grep -v grep
→ 无输出（grep_rc=1）⇒ 当前无任何编译/仿真在跑，可独占 uvs.setup
```

## 5 RTL 库复用性核查（结论：**当前脚本下不可复用**）

- 现存 rtl 库仅有：`SIMLIB_RUN/tc_dom_polling_new_01_1/rtl`（3.6M，mtime 2026-10-10 13:50:06）
- 目标路径 `SIMLIB_RUN/tc_rtc_blk_reset_chk_01_1/rtl` **不存在**（ls rc=2）
- 从原理上 RTL 段与用例无关（`uvlan -work rtl -filelist ./RTL/rtl_dir_pango.txt` 只依赖 RTL 列表 + 宏 + 选项），
  库内容是 tc 无关的，**理论上可复用**；但 `compile_only.sh` 无法利用：
  ```bash
  63: rm -rf "${OUT}/${tc}_${seed}"; mkdir -p "${OUT}/${tc}_${seed}"
  64: if [ "$keep" = 1 ] && [ -d "${OUT}/${tc}_${seed}" ]; then :; fi   # ← 恒为死代码
  ```
  第 63 行无条件 `rm -rf` 先于 `-k` 判断，⇒ **`-k`（保留旧库/增量）实为 no-op**，旧库必被删且不会被复用。
  且 `compile_only.sh` 不在本任务写权内，runner **不得改脚本**。
- ⇒ 预计仍需付完整 **≈4 分钟**（RTL ≈3 min + TB ≈1 min）。
- **待 Lead 决策（三选一）**：① 接受 4 分钟直接跑；② Lead 自行修 `compile_only.sh:63-64`（让 `-k` 真正生效）；
  ③ Lead 显式授权 runner 手工把 `tc_dom_polling_new_01_1/rtl` 复制进 `tc_rtc_blk_reset_chk_01_1/rtl` 并只跑 tb 段
  （省 ≈3 分钟，但属偏离脚本的动作，需授权留痕）。

## 6 阻塞事实

```
ls doc/agents/_demo/TESTLIB_sandbox/    → 空目录（仅 . 与 ..）
ls -l .../tc_rtc_blk_reset_chk_01.sv    → No such file or directory (rc=2)
```

⇒ task-1 尚未产出用例，**卡点 B 无输入，未开跑**。收到 Lead「task-1 完成」后方执行 `task-2`（claim → 编译 → 采证 → complete）。
