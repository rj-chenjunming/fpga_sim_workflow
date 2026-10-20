#!/usr/bin/env bash
# run_guarded.sh —— 卡点B/D 安全包装（spec §9/§10.6；kb/README.md §4 决策 K2）
#
# **不修改** `doc/tools/run_local.sh`（冻结资产，原文件 md5 必须不变）。本脚本在包装层补齐三件事：
#   ① 运行日志头写身份：case_name / case md5 / case bytes / seed / run_id / 启动时刻 / 命令原文
#   ② 先归档再删：run_local.sh:325 会 `rm SIMLIB_RUN/log/${tc}_${seed}_c*.log`，本包装
#      先做归档快照（跑前 sweep + 运行中轮询 sweep），归档件带时间戳、只增不改、绝不先删
#   ③ 中止自愈（trap EXIT/INT/TERM/QUIT）：还原 `uvs.setup` 到夹具 md5
#      `a80f7b6ca48a7961a107bbe871af761d`、清理 `.compile_only.lock`、报告 rc
# 另加：**串行纪律**（同一工作区互斥，`uvs.setup` 是全局单文件）+ 沙箱工作树 + 卡点B 只编译模式。
#
# 三种模式
#   --mode forward        （默认）**纯转发** `doc/tools/run_local.sh`（行为与原来一致）
#   --mode compile-only   只跑 uvlan 两段（≈2s，卡点B），编译选项逐字复制 run_local.sh
#   --mode full           完整三步（uvlan rtl/tb + uvs elaborate + 跑 sim，≈50min，卡点D）
#
# 用例来源（N6 修订件在沙箱里，不动冻结的 TESTLIB/）
#   --case-file PATH      默认 TESTLIB/<case>.sv；compile-only/full 直接用这个路径编译
#   --case-name NAME      -c / +UVM_TESTNAME / -define TEST_NAME 用名（默认取 case-file 基名去 .sv）
#   --sandbox-root DIR    在 DIR 下建**最小工作树**（RTL/TB/PKG/TESTLIB/all_define.txt/input.tcl
#                         只读软链 + 自己的 uvs.setup/SIMLIB_RUN/cases），仓库根的 uvs.setup 与
#                         SIMLIB_RUN/ 完全不动；做不到（如软链失败）则退化到仓库根跑，但 trap 自愈保护
#
# 编译选项的**唯一来源**（逐字复制，不许增删；行号 = doc/tools/run_local.sh）
#   :302 wave_cmd（-do input.tcl；包装层用 build_wave_cmd 显式重建）
#   :308 uvs_opt（-ddb -debug -logfile … -j32 -o <wave>/UVS_<tc>_<seed> -deposit_initval randomxz=<seed>；
#        包装层用 build_uvs_opt 显式重建，并在执行前用 assert_uvs_opt 机器自检 -o/-logfile/逐字选项）
#   :306 tb_dir（+incdir+… 全串）           :307 vlan_opt（-f all_define.txt）
#   :308 uvs_opt（-ddb -debug -logfile … -j32 -o … -deposit_initval randomxz=<seed>）
#   :309 all_opt（-uvm1.2 … cgresolve_partial_assign:0）
#   :310 rtl_filelist（./RTL/rtl_dir_pango.txt；:312 为 xilinx 变体）
#   :317 xli_lib uvlan（仅 VENDOR_XILINX=1）  :318 uvlan -work rtl  :319 uvlan -work tb
#   :321 uvs elaborate                       :338 跑 sim 二进制
# 唯一的包装层增量：`-logfile` / `-o` / wave 目录指向 `kb/runs/<run_id>/evidence/`（时间戳命名），
# 以及当用例不在 ./TESTLIB 时追加 `+incdir+<用例目录>`（否则沙箱用例编译不过）。
#
# 用法
#   bash kb/tools/run_guarded.sh -c tc_bmc_i2c_01 -d 1                  # 纯转发（默认）
#   bash kb/tools/run_guarded.sh --case-file kb/runs/<id>/sandbox/tc_x.sv --mode compile-only \
#        --sandbox-root kb/runs/<id>/sandbox --run RUN-20261015-130000
#
# 退出码：0 成功 / 2 用法 / 3 拒绝（并发/陈旧锁）/ 其他 = run_local.sh 或 uvlan/uvs 的原样 rc
set -u
umask 022

ORIG_ARGS=("$@")
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
TOOL_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
# 环境（插件）根：拆仓后软件不在环境仓内，必须由 LOOP_ENV_ROOT 给出。
# 向后兼容：若软件仍在环境仓内（拆仓前布局，TOOL_ROOT 下有 TESTLIB/），回落为 TOOL_ROOT。
ROOT="${LOOP_ENV_ROOT:-}"
if [ -z "$ROOT" ] && [ -d "$TOOL_ROOT/TESTLIB" ]; then
  # 向后兼容：软件仍在环境仓内（拆仓前布局）
  ROOT="$TOOL_ROOT"
fi
if [ -z "$ROOT" ]; then
  # 与其它脚本**同一个**解析器（kb_lib）：口径只有一份，包装脚本不许自己再定一套。
  # 读的是软件仓根的 environments.json（不依赖任何环境变量）。
  ROOT="$("${PYTHON:-python3}" -c \
    "import sys; sys.path.insert(0, \"$TOOL_ROOT/kb/tools\"); sys.dont_write_bytecode = True; \
     import kb_lib; print(kb_lib.ENV_ROOT)" 2>/dev/null)"
fi
if [ -n "${LOOP_ENV_ROOT:-}" ] && [ ! -d "$LOOP_ENV_ROOT" ]; then
  # 区分"没给"与"给了但指错" —— 两者的处置完全不同，错误信息必须说清
  echo "[guard] [FAIL] \$LOOP_ENV_ROOT=$LOOP_ENV_ROOT 不是一个目录" >&2
  exit 2
fi
if [ -z "$ROOT" ] || [ ! -d "$ROOT" ]; then
  echo "[guard] [FAIL] 无法确定环境根 ENV_ROOT：既没有 \$LOOP_ENV_ROOT，" >&2
  echo "               $TOOL_ROOT/environments.json 里也没有可用条目" >&2
  echo "               （见 doc/spec/ENV_PLUGIN_SPEC.md §1）" >&2
  exit 2
fi
cd "$ROOT" || exit 2

FIXTURE="$ROOT/doc/_run_artifacts/uvs.setup.orig"
EXPECTED_SETUP_MD5="a80f7b6ca48a7961a107bbe871af761d"
INNER_DEFAULT="$ROOT/doc/tools/run_local.sh"

# ---------------- 逐字复制自 doc/tools/run_local.sh 的选项（见文件头行号） ----------------
TB_FILE="TB"                                                                     # run_local.sh:12
# :302 / :308 的表达式在编译/执行前按 run_local.sh 的写法**显式重建**（不再用占位符全字替换：
# 历史 blocker 就是 UVS___TC___SEED__ 少一划 ⇒ __SEED__ 匹配不到、seed 从未进入 -o 输出名）
TB_DIR='+incdir+./TESTLIB,./TB/LIBS/SVX-LIB/version,./TB/LIBS/SVX-LIB/linked,./TB/LIBS/SVX-LIB/lexer,./TB/LIBS/SVX-LIB/iterators,./TB/LIBS/SVX-LIB/containers,./TB/LIBS/SVX-LIB/behaviors,./TB/LIBS/SV-LIB/src/dpi,./TB/LIBS/SV-LIB/src,./TB/LIBS/PKT-LIB/pkt_head_lib,./TB/LIBS/PKT-LIB/pkt_head_lib,./TB/LIBS/SV-LIB,./TB/LIBS/SVSTRING-LIB,./TB/LIBS/SVX-LIB,./TB/LIBS/MEM-MGR-LIB,./TB/LIBS/PKT-LIB,./TB/LIBS/SQL-LIB,./TB/LIBS/ASSERT-LIB,./TB/LIBS/DSCRAMBLER-LIB,./TB/LIBS/CBB-LIB,./TB/AGENTS/CRG-Agent,./TB/AGENTS/MDIO-Agent,./TB/AGENTS/UART-Agent,./TB/AGENTS/I2C-Agent,./TB/AGENTS/FAN-Agent,./TB/AGENTS/PCIE-Agent,./TB/AGENTS/SPI-Agent,./TB/AGENTS/dcb_agent,./TB/MODEL,./TB'   # :306
VLAN_OPT='-f all_define.txt '                                                    # :307
ALL_OPT='-uvm1.2 -sv -debug_cell -usdb -uvs_xlrm MacroConcatEarly -Xair yxxie.fix_fatal_empty_fmt -Xair yxxie.allow_compatible_copy  -Xair xb.always_opt_with_pda_signal -Xair hhlin.fix_final_finish -Xopts sva_fix_AIR_12100 -Xopts sva_fix_AIR_12098 -Xair be.air12017_containerTy_castexpr -Xopts later_bind_param_opt=0 -timescale 1ns/1ns -fly_Nopts cgresolve_partial_assign:0 '   # :309
RTL_FILELIST='./RTL/rtl_dir_pango.txt'                                           # :310
RTL_FILELIST_XILINX='./RTL/rtl_dir_xilinx.txt'                                   # :312
build_uvs_opt() {  # 参数：ELAB_LOG WAVE_DIR CASE_NAME SEED
  printf -- '-ddb -debug  -logfile %s  -j32  -o %s/UVS_%s_%s -deposit_initval randomxz=%s ' \
         "$1" "$2" "$3" "$4" "$4"
}

build_wave_cmd() {  # 参数：WAVE_DIR CASE_NAME SEED（run_local.sh:302）
  printf -- '-usdb=all,cell +usdbfile=%s/%s_%s.usdb -cli -do input.tcl' "$1" "$2" "$3"
}

assert_uvs_opt() {  # $1=UVS_OPT 串 $2=期望 -logfile $3=期望 -o token；失败 rc=3
  local opt="$1" want_log="$2" want_o="$3"
  local -a toks=(); read -r -a toks <<< "$opt"
  local o="" lg="" dep="" i
  for ((i = 0; i < ${#toks[@]}; i++)); do
    case "${toks[$i]}" in
      -o) o="${toks[$((i + 1))]:-}" ;;
      -logfile) lg="${toks[$((i + 1))]:-}" ;;
      -deposit_initval) dep="${toks[$((i + 1))]:-}" ;;
    esac
  done
  {
    echo "[assert] uvs_opt 展开后 token 自检（对照 doc/tools/run_local.sh:308）"
    echo "[assert]   -o          = $o"
    echo "[assert]   -o   期望   = $want_o"
    echo "[assert]   -logfile    = $lg"
    echo "[assert]   -logfile 期望= $want_log"
    echo "[assert]   -deposit_initval = $dep （期望 randomxz=$SEED）"
  } | tee -a "$GUARD_LOG"
  local bad=0
  [ "$o" = "$want_o" ] || { echo "[FAIL] uvs -o token 不等于期望（实际 $o，期望 $want_o）" >&2; bad=1; }
  [ "$lg" = "$want_log" ] || { echo "[FAIL] uvs -logfile token 不是期望证据路径（$lg != $want_log）" >&2; bad=1; }
  [ "$dep" = "randomxz=$SEED" ] || { echo "[FAIL] -deposit_initval 不是 randomxz=$SEED（实际 $dep）" >&2; bad=1; }
  local k
  for k in -ddb -debug -j32; do
    printf '%s\n' "${toks[@]}" | grep -qx -- "$k" || { echo "[FAIL] uvs_opt 少了逐字复制的选项 $k" >&2; bad=1; }
  done
  [ "$bad" = 0 ] || return 3
  return 0
}

usage() {
  cat <<'EOF'
run_guarded.sh —— 包装 doc/tools/run_local.sh（不改冻结文件），补日志头/先归档再删/中止自愈/串行互斥

用法: bash kb/tools/run_guarded.sh [选项]

用例与模式
  -c, --case NAME        用例名（forward 模式透传给 run_local.sh 的 -c；默认由 --case-file 推导）
  --case-file PATH       用例源文件（沙箱修订件），默认 TESTLIB/<case>.sv
  --case-name NAME       显式用例名（用于 -c / +UVM_TESTNAME / -define TEST_NAME）
  -d, --seed N           seed（默认 1）
  --mode MODE            forward（默认，纯转发 run_local.sh）| compile-only（卡点B，只编译）| full（卡点D，全跑）
  --inner PATH           被转发的脚本（默认 doc/tools/run_local.sh；自测可换桩，md5 记入日志头）
  --sandbox-root DIR     在 DIR 下建最小工作树：RTL/TB/PKG/TESTLIB/BIN/all_define.txt/input.tcl 只读软链，
                         自建 uvs.setup 与 SIMLIB_RUN/，**不动仓库根的 uvs.setup 与 SIMLIB_RUN/**；
                         用例文件复制为 DIR/cases/<name>.sv。软链失败则退化到仓库根跑（trap 仍自愈）
  --python-cmd CMD       保留项：打印用（默认 python3）

证据与身份
  --run RUN_ID           run_id；证据落 kb/runs/<run_id>/evidence/（默认 RUN-<当前时刻>）
  --evidence-dir DIR     直接指定证据目录（覆盖 --run 推导）
  --lock-timeout SEC     等待互斥锁秒数（默认 0 = 有并发立即拒绝）
  --break-stale-lock [SEC]  配合"owner PID 已不存在"判定陈旧锁时使用的年龄兜底阈值（默认 3600）；
                         **PID 存活一律判真并发、绝不自动清**；默认关闭
  --ignore-stale-lock    对 `.compile_only.lock` 与 `.run_guarded.lock` 同时生效：
                         **仅当 owner 记录的 PID 已不存在**才清；真并发（PID 存活）仍 rc=3 且不清

行为开关
  --dry-run              只打印纪要与将执行的命令原文，不执行、不写盘
  -h, --help             本帮助

安全保证（逐条可验）
  ① 运行日志头：case_name / case md5 / case bytes / seed / run_id / 启动时刻 / 命令原文
     → `kb/runs/<run_id>/evidence/<时间戳>_<case>_<seed>_guard.log`
  ② 先归档再删：run_local.sh:325 的 `rm SIMLIB_RUN/log/${tc}_${seed}_c*.log` 无法拦停（文件冻结），
     本包装在跑前 + 运行中（0.5s 轮询）+ 收尾三次把匹配件复制进 `evidence/archive/`（带时间戳、不移动原件）
  ③ trap EXIT INT TERM QUIT：还原 uvs.setup 到夹具 md5 a80f7b6ca48a7961a107bbe871af761d、
     清理 .compile_only.lock、报告 rc
  ④ 串行：`SIMLIB_RUN/.run_guarded.lock`（mkdir 原子）+ 启动时检查 .compile_only.lock
  ⑤ 冻结纪律：本脚本不写 doc/、TESTLIB/、RTL/、TB/、PKG/；只在 kb/runs/<run_id>/evidence/ 与
     （compile-only/full）沙箱或 SIMLIB_RUN/ 下工作

退出码：0 成功 / 2 用法 / 3 拒绝（并发或陈旧锁）/ 其他 = 内部脚本原样 rc
EOF
}

# ---------------- 参数 ----------------
CASE=""; CASE_FILE=""; CASE_NAME=""; SEED=1; MODE="forward"; INNER="$INNER_DEFAULT"
SANDBOX_ROOT=""; RUN_ID=""; EVIDENCE_DIR=""; LOCK_TIMEOUT=0; DRY_RUN=0; IGNORE_STALE_LOCK=0
BREAK_STALE_LOCK=0
PASSTHRU=()
while [ $# -gt 0 ]; do
  case "$1" in
    -c|--case) CASE="${2:-}"; shift 2 ;;
    --case-file) CASE_FILE="${2:-}"; shift 2 ;;
    --case-name) CASE_NAME="${2:-}"; shift 2 ;;
    -d|--seed) SEED="${2:-}"; shift 2 ;;
    --mode) MODE="${2:-}"; shift 2 ;;
    --inner) INNER="${2:-}"; shift 2 ;;
    --sandbox-root) SANDBOX_ROOT="${2:-}"; shift 2 ;;
    --run) RUN_ID="${2:-}"; shift 2 ;;
    --evidence-dir) EVIDENCE_DIR="${2:-}"; shift 2 ;;
    --lock-timeout) LOCK_TIMEOUT="${2:-}"; shift 2 ;;
    --break-stale-lock) BREAK_STALE_LOCK="${2:-3600}"; shift 2 ;;
    --ignore-stale-lock) IGNORE_STALE_LOCK=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --python-cmd) shift 2 ;;
    -h|--help) usage; exit 0 ;;
    --) shift; PASSTHRU+=("$@"); break ;;
    *) PASSTHRU+=("$1"); shift ;;
  esac
done

case "$MODE" in forward|compile-only|full) ;; *) echo "[FAIL] --mode 只支持 forward|compile-only|full" >&2; exit 2 ;; esac
if [ -z "$CASE_FILE" ]; then
  [ -n "$CASE" ] || { echo "[FAIL] 需要 -c <case> 或 --case-file <path>" >&2; exit 2; }
  CASE_FILE="TESTLIB/${CASE}.sv"
fi
[ -f "$CASE_FILE" ] || { echo "[FAIL] 用例文件不存在：$CASE_FILE" >&2; exit 2; }
if [ -z "$CASE_NAME" ]; then
  CASE_NAME=$(basename "$CASE_FILE"); CASE_NAME="${CASE_NAME%.sv}"
fi
[ -n "$CASE" ] || CASE="$CASE_NAME"
[ -n "$RUN_ID" ] || RUN_ID="RUN-$(date +%Y%m%d-%H%M%S)"
[ -n "$EVIDENCE_DIR" ] || EVIDENCE_DIR="$ROOT/kb/runs/$RUN_ID/evidence"
# 证据目录一律转为**绝对路径**：compile-only/full 会 cd 进沙箱，相对路径会被 cd 带偏
if [ "$DRY_RUN" = 0 ]; then mkdir -p "$EVIDENCE_DIR" 2>/dev/null || true; fi
if [ -d "$EVIDENCE_DIR" ]; then EVIDENCE_DIR=$(cd "$EVIDENCE_DIR" && pwd); fi
STAMP=$(date +%Y%m%d-%H%M%S)
CASE_MD5=$(md5sum "$CASE_FILE" | awk '{print $1}')
CASE_BYTES=$(stat -c %s "$CASE_FILE")
INNER_MD5=$([ -f "$INNER" ] && md5sum "$INNER" | awk '{print $1}' || echo "N/A(不存在)")
START_TS=$(date '+%Y-%m-%dT%H:%M:%S%z')
# task-15（W-1）：把**包装层自身**的 md5 固定下来，事后可判定"这次跑的是哪一版 run_guarded.sh"
WRAPPER_MD5=$(md5sum "$SCRIPT_DIR/run_guarded.sh" 2>/dev/null | awk '{print $1}')
CMD_TEXT="$(basename "$0") ${ORIG_ARGS[*]}"

# ---------------- 目录与锁 ----------------
LOCKDIR="$ROOT/SIMLIB_RUN/.run_guarded.lock"
COMPILE_LOCK="$ROOT/.compile_only.lock"
LOCK_CREATED=0
POLLER_PID=""
POLL_FLAG=""
ARCHIVE=""
GUARD_LOG=""

md5_of() { [ -f "$1" ] && md5sum "$1" 2>/dev/null | awk '{print $1}' || echo MISSING; }

lock_owner_field() {  # $1=KEY -> 值（owner 形如 KEY=VAL 空格分隔）
  [ -f "$LOCKDIR/owner" ] || { echo ""; return; }
  tr ' ' '\n' < "$LOCKDIR/owner" 2>/dev/null | awk -F= -v k="$1" '$1==k{print $2}' | head -1
}

lock_pid_alive() {   # 回显 yes / no / unknown
  local pid; pid=$(lock_owner_field PID)
  case "$pid" in
    ''|*[!0-9]*) echo unknown; return ;;
  esac
  if kill -0 "$pid" 2>/dev/null; then echo yes; else echo no; fi
}

release_lock() {
  if [ -d "$LOCKDIR" ]; then
    if [ ! -f "$LOCKDIR/owner" ] || \
       [ "$(lock_owner_field STAMP)" = "$STAMP" ] || \
       grep -q " ${STAMP}$" "$LOCKDIR/owner" 2>/dev/null; then
      rm -rf "$LOCKDIR" 2>/dev/null        # rm -rf：目录里混入别的文件时 rmdir 会静默失败
    else
      echo "[WARN] 互斥量已被他人接管，本进程不删除：$LOCKDIR/owner=$(cat "$LOCKDIR/owner" 2>/dev/null)" >&2
    fi
  fi
  LOCK_CREATED=0
}

lock_age_sec() {   # 互斥量 owner 文件的年龄（秒）；无法判断时回显 -1
  [ -f "$LOCKDIR/owner" ] || { echo -1; return; }
  local now m; now=$(date +%s); m=$(stat -c %Y "$LOCKDIR/owner" 2>/dev/null) || { echo -1; return; }
  [ -n "$m" ] || { echo -1; return; }
  echo $((now - m))
}

acquire_lock() {
  local waited=0 age=0 pid_alive="" owner=""
  # 新环境/首次跑：`SIMLIB_RUN/` 可能尚不存在。`mkdir "$LOCKDIR"` 会因**父目录缺失**失败，
  # 旧逻辑随即把"没有 owner 文件"误判成"旧格式/未知锁"并 rc=3（实测 2026-10-20 real 首跑：
  # 场景环境副本不含 SIMLIB_RUN/ ⇒ N7 compile-only 直接死在"互斥量 owner 无法解析"）。
  mkdir -p "$ROOT/SIMLIB_RUN" 2>/dev/null
  while true; do
    if mkdir "$LOCKDIR" 2>/dev/null; then
      LOCK_CREATED=1
      # task-15：owner 带 PID + 启动时刻 + run_id + case/seed（陈旧判据可复算）
      printf 'VER=2 PID=%s START=%s RUN=%s CASE=%s SEED=%s STAMP=%s\n' \
             "$$" "$(date '+%Y-%m-%dT%H:%M:%S%z')" "${RUN_ID:-N/A}" "$CASE" "$SEED" "$STAMP" \
             > "$LOCKDIR/owner" 2>/dev/null
      # task-16：冻结件身份落到锁目录（与 _guard.log 头同源）
      printf '%s  %s\n' "$CASE_MD5" "$CASE_FILE" > "$LOCKDIR/case.md5" 2>/dev/null
      return 0
    fi
    owner=$(cat "$LOCKDIR/owner" 2>/dev/null | tr -d '\n')
    pid_alive=$(lock_pid_alive)
    age=$(lock_age_sec)
    # 陈旧 = owner 记录的 PID 已不存在（首要判据）；**PID 存活一律判真并发，绝不自动清**
    # N9-3：owner 无法解析（旧格式/无 PID/VER 不认识）⇒ 一律"未知 ⇒ 不清、rc=3 并打印 owner 原文"
    local over; over=$(lock_owner_field VER)
    if [ "$pid_alive" = "unknown" ] || [ -z "$over" ] || [ "$over" != "2" ]; then
      echo "[FAIL] 互斥量 owner 无法解析/旧格式（VER=${over:-缺}，PID=$(lock_owner_field PID)）⇒ 按**未知**处理：**不清锁**、rc=3（宁可拒绝也不误清活跃锁，N9-3）。" >&2
      echo "       owner 原文=[$owner]" >&2
      echo "       人工确认锁已死后再清理：rm -rf $LOCKDIR" >&2
      return 3
    fi
    if [ "$pid_alive" = "no" ]; then
      if [ "$IGNORE_STALE_LOCK" = 1 ] || \
         { [ "$BREAK_STALE_LOCK" -gt 0 ] && [ "$age" -ge 0 ] && [ "$age" -ge "$BREAK_STALE_LOCK" ]; }; then
        echo "[warn] 陈旧锁（PID $(lock_owner_field PID) 已不存在，锁龄 ${age}s）⇒ 清除：$LOCKDIR"
        echo "[warn]   原 owner=[$owner]（该进程已死；uvs.setup 由下次运行的 trap 兜底还原）"
        rm -rf "$LOCKDIR"
        continue
      fi
      echo "[FAIL] 互斥量疑似**陈旧锁**（PID $(lock_owner_field PID) 已不存在，锁龄 ${age}s）⇒ 上一次 run_guarded **可能**被信号杀死/SIGKILL，trap 未执行或未完成（不是必然：SIGTERM 走 on_signal+EXIT 双保险，只有 SIGKILL 等不可捕获情形才必然滞留）。" >&2
      echo "       owner=[$owner]" >&2
      echo "       一键清锁：rm -rf $LOCKDIR    （或重跑时加 --ignore-stale-lock；年龄兜底 --break-stale-lock ${BREAK_STALE_LOCK:-未启用}）" >&2
      return 3
    fi
    if [ "$waited" -ge "$LOCK_TIMEOUT" ]; then
      echo "[FAIL] 真并发：另一 run_guarded 正在跑且**进程存活**（PID $(lock_owner_field PID)，case=$(lock_owner_field CASE)，run=$(lock_owner_field RUN)）。" >&2
      echo "       owner=[$owner]；锁目录 $LOCKDIR —— **不要删**（这是活跃锁）。" >&2
      echo "       串行纪律：uvs.setup 是全局单文件，禁止并发（doc/AGENTS.md 红线 7）" >&2
      return 3
    fi
    sleep 1; waited=$((waited+1))
  done
}

# ---------------- 归档（只增不改；归档件置只读） ----------------
# 候选路径取自**三条真实产物位置**（E-2 的机制教训，见 REHEARSAL_REPORT.md E-2）：
#   ① `$ROOT/SIMLIB_RUN/log/<case>_<seed>_*`：forward / 仓库根模式。inner `run_local.sh:325`
#      会删这些件 ⇒ 必须靠 0.5s 轮询抢在删除前归档。名字**无** STAMP。
#   ② `$EVIDENCE_DIR/<stamp>_<case>_<seed>_*`：compile-only / full 模式的全部日志直接写这里
#      （见本文件 `LOG_DIR="$EVIDENCE_DIR"` 与 `*_LOG=...` 赋值）。
#      **早先只 glob ①，于是这两个模式下 `archive/` 永远为空 —— 这就是 E-2 的机制原因。**
#   ③ `$SANDBOX_ROOT/SIMLIB_RUN/log/*`：给了 `--sandbox-root` 时 inner 的落点。
# **刻意不归档 `_guard.log`**：它是本次运行的主证据原件，且收尾仍在追加；
# 复制进自己的 archive/ 只能得到半截副本，与"可回放"相反。
ARCHIVE_SIG_DIR=""

archive_sig_dir() {
  [ -n "$ARCHIVE_SIG_DIR" ] || ARCHIVE_SIG_DIR="$EVIDENCE_DIR/.archive_sig"
  mkdir -p "$ARCHIVE_SIG_DIR" 2>/dev/null
  printf '%s' "$ARCHIVE_SIG_DIR"
}

# 稳定性判定：同一 (size, mtime) **连续两次** sweep 相同才归档。
# 否则每 0.5s 就会给一份仍在增长的日志多留一个副本 ——
# 那不是"只增不改"，而是一堆无法回放的半截件。
archive_is_stable() {   # $1=file
  local f="$1" dir sig marker prev
  dir="$(archive_sig_dir)"
  [ -n "$dir" ] || return 1
  sig="$(stat -c '%s %Y' "$f" 2>/dev/null)" || return 1
  marker="$dir/$(printf '%s' "$f" | md5sum | cut -c1-16)"
  prev="$(cat "$marker" 2>/dev/null)"
  printf '%s\n' "$sig" > "$marker" 2>/dev/null
  [ -n "$prev" ] && [ "$prev" = "$sig" ]
}

archive_put() {         # $1=源文件或目录  $2=归档基名
  local src="$1" b="$2" dst d2 n base
  # 源名可能**已带** STAMP（compile-only/full 模式的证据件就是这样）；
  # 再前缀一次会得到 `20261015-143020_20261015-143020_...` 这种双时间戳。
  case "$b" in
    "${STAMP}_"*) base="$b" ;;
    *)            base="${STAMP}_${b}" ;;
  esac
  dst="$ARCHIVE/$base"
  if [ ! -e "$dst" ]; then
    if [ -d "$src" ]; then
      cp -r -p "$src" "$dst" 2>/dev/null || return 0
      chmod -R a-w "$dst" 2>/dev/null
    else
      cp -p "$src" "$dst" 2>/dev/null || return 0
      chmod 444 "$dst" 2>/dev/null
    fi
    echo "[archive] $src -> ${dst#$ROOT/}（只读）" >> "$GUARD_LOG"
    return 0
  fi
  if [ -f "$src" ] && [ -f "$dst" ] && ! cmp -s "$src" "$dst"; then
    # 同名不同内容：归档名再带一次序号，**绝不覆盖**（F3 同源教训）
    n=1; d2="${dst}.${n}"
    while [ -e "$d2" ]; do n=$((n+1)); d2="${dst}.${n}"; done
    if cp -p "$src" "$d2" 2>/dev/null; then
      chmod 444 "$d2" 2>/dev/null
      echo "[archive] 同名不同内容 -> ${d2#$ROOT/}（只读）" >> "$GUARD_LOG"
    fi
  fi
}

archive_sweep() {
  [ -n "$ARCHIVE" ] || return 0
  mkdir -p "$ARCHIVE"
  local dirs=( "$ROOT/SIMLIB_RUN/log" "$EVIDENCE_DIR" )
  if [ -n "$SANDBOX_ROOT" ] && [ "$SANDBOX_ROOT" != "$ROOT" ]; then
    dirs+=( "$SANDBOX_ROOT/SIMLIB_RUN/log" )
  fi
  # 无 STAMP（模式①③；inner 会删，靠轮询抢时间）
  local bare=(
    "${CASE}_${SEED}_c_rtl.log"
    "${CASE}_${SEED}_c_tb.log"
    "${CASE}_${SEED}_c_xli_lib.log"
    "${CASE}_${SEED}_c_uvs.log"
    "${CASE}_${SEED}_run.log"
    "${CASE}_${SEED}.log"
  )
  # 带 STAMP（模式②；E-2 缺的就是这一组）
  local stamped=(
    "${STAMP}_${CASE_NAME}_${SEED}_c_rtl.log"
    "${STAMP}_${CASE_NAME}_${SEED}_c_tb.log"
    "${STAMP}_${CASE_NAME}_${SEED}_c_xli_lib.log"
    "${STAMP}_${CASE_NAME}_${SEED}_c_uvs.log"
    "${STAMP}_${CASE_NAME}_${SEED}_run.log"
    "${STAMP}_${CASE_NAME}_${SEED}_run.log.guarded"
    "${STAMP}_${CASE_NAME}_${SEED}.invalidated"
  )
  local d b f
  for d in "${dirs[@]}"; do
    for b in "${bare[@]}" "${stamped[@]}"; do
      case "$b" in *_guard.log) continue ;; esac   # 主证据原件，不自我归档
      f="$d/$b"
      [ -f "$f" ] || continue
      archive_is_stable "$f" || continue
      archive_put "$f" "$b"
    done
  done
  # TC/output/<case>_<seed>（目录）：`-e dst` 守卫本身就是只写一次，无需稳定判定
  local tcd="$ROOT/TC/output/${CASE}_${SEED}"
  [ -d "$tcd" ] && archive_put "$tcd" "${CASE}_${SEED}"
}

poller() {
  while [ -f "$POLL_FLAG" ]; do archive_sweep; sleep 0.5; done
}

stop_poller() {
  [ -n "$POLL_FLAG" ] && rm -f "$POLL_FLAG"
  if [ -n "$POLLER_PID" ] && kill -0 "$POLLER_PID" 2>/dev/null; then kill "$POLLER_PID" 2>/dev/null; fi
  POLLER_PID=""
}

# ---------------- 自愈 ----------------
INVALIDATED=0
COMPILED_CASE=""

mark_invalidated() {   # $1=phase $2=detail
  INVALIDATED=1
  local marker="$EVIDENCE_DIR/${STAMP}_${CASE_NAME}_${SEED}.invalidated"
  {
    echo "invalidated=true"
    echo "phase=$1"
    echo "$2"
    echo "case_file=$CASE_FILE md5_start=$CASE_MD5 md5_now=$(md5_of "$CASE_FILE")"
    echo "compiled_case=$COMPILED_CASE md5_now=$(md5_of "${COMPILED_CASE:-/nonexistent}")"
    echo "run_id=${RUN_ID:-N/A} case=$CASE_NAME seed=$SEED stamp=$STAMP phase_time=$(date '+%Y-%m-%dT%H:%M:%S%z')"
  } > "$marker"
  echo "[identity] INVALIDATED=true（phase=$1）：$2" | tee -a "$GUARD_LOG" >&2
  echo "[identity] 本次证据作废（rc=3），旁挂标记：${marker#$ROOT/}" | tee -a "$GUARD_LOG" >&2
}

identity_check() {     # $1=phase；--case-file / 被编译件 双复检；不一致 ⇒ invalidated + rc=3
  local phase="$1" now compiled
  if [ "$DRY_RUN" = 1 ]; then
    echo "[identity] dry-run：跳过 ${phase} 复检（不写盘）"
    return 0
  fi
  now=$(md5_of "$CASE_FILE")
  if [ "$now" != "$CASE_MD5" ]; then
    mark_invalidated "$phase" "case-file md5 变了：start=$CASE_MD5 now=$now path=$CASE_FILE"
    exit 3
  fi
  if [ -n "$COMPILED_CASE" ]; then
    compiled=$(md5_of "$COMPILED_CASE")
    if [ "$compiled" != "$CASE_MD5" ]; then
      mark_invalidated "$phase" "被编译件 md5 != --case-file：compiled=$compiled start=$CASE_MD5 path=$COMPILED_CASE"
      exit 3
    fi
  fi
  echo "[identity] case md5 一致：$CASE_MD5（phase=$phase，case_file=$CASE_FILE${COMPILED_CASE:+，compiled=$COMPILED_CASE}）" | tee -a "$GUARD_LOG"
}

CLEANUP_RC=0
on_exit() {
  local rc=$?
  stop_poller
  # 终态 sweep 必须跑**两次**：稳定判定需要连续两次观测，
  # 而 `*.guarded` / `*.invalidated` 这类件是运行收尾才出现的。
  archive_sweep; archive_sweep
  # 稳定判定的 scratch 目录必须无条件清理：它多半是在**轮询子 shell** 里被创建的，
  # 主 shell 的 `$ARCHIVE_SIG_DIR` 仍是空串，用 `-n` 守卫会漏掉（实测漏过）。
  [ -n "$EVIDENCE_DIR" ] && rm -rf "$EVIDENCE_DIR/.archive_sig" 2>/dev/null
  # 还原 uvs.setup（仓库根口径：夹具 md5 必须回到 a80f7b6c…）
  if [ -f "$FIXTURE" ]; then
    chmod u+w "$ROOT/uvs.setup" 2>/dev/null
    cp -p "$FIXTURE" "$ROOT/uvs.setup" 2>/dev/null
    chmod 444 "$ROOT/uvs.setup" 2>/dev/null
    local now; now=$(md5sum "$ROOT/uvs.setup" 2>/dev/null | awk '{print $1}')
    if [ "$now" != "$EXPECTED_SETUP_MD5" ]; then
      echo "[FAIL] uvs.setup 还原后 md5=$now != 夹具 $EXPECTED_SETUP_MD5" | tee -a "$GUARD_LOG" >&2
      CLEANUP_RC=3
    else
      echo "[heal] uvs.setup 已还原到夹具 md5 $EXPECTED_SETUP_MD5" | tee -a "$GUARD_LOG"
    fi
  else
    echo "[WARN] 夹具不存在，无法还原 uvs.setup：$FIXTURE" | tee -a "$GUARD_LOG" >&2
  fi
  # 清理 .compile_only.lock（本脚本持有串行互斥量 ⇒ 运行结束后残留的锁视为本轮遗留）
  if [ -f "$COMPILE_LOCK" ]; then
    rm -f "$COMPILE_LOCK" && echo "[heal] 已清理 .compile_only.lock" | tee -a "$GUARD_LOG"
  fi
  release_lock
  echo "[guard] rc=$rc（证据：${EVIDENCE_DIR#$ROOT/}）" | tee -a "$GUARD_LOG"
  [ "$CLEANUP_RC" = 0 ] || exit "$CLEANUP_RC"
  exit "$rc"
}
on_signal() {
  echo "[guard] 收到信号 $1 ⇒ 中止并自愈（停子进程 → 释放互斥量 → EXIT 自愈）" | tee -a "$GUARD_LOG" >&2
  [ -n "${CHILD_PID:-}" ] && kill "$CHILD_PID" 2>/dev/null
  stop_poller
  release_lock
  exit 130
}

# ---------------- 子进程执行（信号可达） ----------------
CHILD_PID=""
RUN_TEE_RC=0
run_tee() {   # 用法：run_tee <cmd> <args...>   rc 经 RUN_TEE_RC 返回
  # 关键：**不要把长命令放在前台**。bash 在等待前台子进程时会推迟陷阱处理 ⇒
  # SIGTERM 下 trap 不执行、锁泄漏（task-15 实测形态）。改成后台 + wait，陷阱即可即时生效。
  "$@" > >(tee -a "$GUARD_LOG") 2>&1 &
  CHILD_PID=$!
  wait "$CHILD_PID"
  RUN_TEE_RC=$?
  CHILD_PID=""
}

# ---------------- 沙箱 ----------------
SANDBOX_USED="no"
setup_sandbox() {
  local sb="$1"
  mkdir -p "$sb" || return 1
  local link
  for link in RTL TB PKG TESTLIB BIN all_define.txt input.tcl; do
    [ -e "$ROOT/$link" ] || continue
    if [ -e "$sb/$link" ] || [ -L "$sb/$link" ]; then continue; fi
    ln -s "$ROOT/$link" "$sb/$link" 2>/dev/null || return 1
  done
  mkdir -p "$sb/SIMLIB_RUN/log" "$sb/SIMLIB_RUN/wave" "$sb/cases" || return 1
  cp -p "$CASE_FILE" "$sb/cases/${CASE_NAME}.sv" || return 1
  return 0
}

write_sandbox_uvs_setup() {   # 与 run_local.sh:284-296 的 uvs.setup 结构一致（路径按工作根相对）
  local work="$1"; local tc="$2"; local seed="$3"
  rm -f "$work/uvs.setup" 2>/dev/null   # 既有 uvs.setup 可能是 444（夹具口径），先删再写
  cat <<EOF > "$work/uvs.setup"
DEFAULT: ./work
rtl:     ./SIMLIB_RUN/${tc}_${seed}/rtl
tb:      ./SIMLIB_RUN/${tc}_${seed}/tb

usim: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/usim
pciegen2: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/pciegen2
vsim: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/vsim
ipal_e2: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/ipal_e2
ipal_e5: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/ipal_e5
hsstlp_lane: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/hsstlp_lane
hsstlp_pll: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/hsstlp_pll
oserdes_e2: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/oserdes_e2
iserdes_e2: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/iserdes_e2
ddrs: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/ddrs
ppm: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/ppm
ddc_e2: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/ddc_e2
dll_e2: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/dll_e2
adc_e2: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/adc_e2
ddrs_dft: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/ddrs_dft
iolhr_dft: ./PKG/pango_uvs_lib/pango_sim_libraries/uvs/iolhr_dft
EOF
}

# ---------------- 主流程 ----------------
if [ "$DRY_RUN" = 1 ]; then
  echo "[guard] --dry-run：只打印计划，不执行、不写盘"
fi

ARCHIVE="$EVIDENCE_DIR/archive"
GUARD_LOG="$EVIDENCE_DIR/${STAMP}_${CASE_NAME}_${SEED}_guard.log"
POLL_FLAG="$EVIDENCE_DIR/.polling.$$"
if [ "$DRY_RUN" = 1 ]; then
  GUARD_LOG=/dev/null          # --dry-run：不写盘（头只打到 stdout）
else
  mkdir -p "$EVIDENCE_DIR" 2>/dev/null
  acquire_lock || exit $?
  trap on_exit EXIT
  trap 'on_signal INT' INT
  trap 'on_signal TERM' TERM
  trap 'on_signal QUIT' QUIT
  trap 'on_signal HUP' HUP
  if [ -f "$COMPILE_LOCK" ]; then
    if [ "$IGNORE_STALE_LOCK" = 1 ]; then
      echo "[warn] 清理陈旧 .compile_only.lock（--ignore-stale-lock）"
      rm -f "$COMPILE_LOCK"
    else
      echo "[FAIL] 发现 .compile_only.lock（$COMPILE_LOCK）⇒ 视为有并发/上次崩溃残留，拒绝启动。" >&2
      echo "       确认无并发后用 --ignore-stale-lock 重跑。" >&2
      exit 3
    fi
  fi
fi

# 日志头（spec §10.6 身份字段）
emit_header() {
  echo "==================== run_guarded.sh 运行日志头 ===================="
  echo "case_name        : $CASE_NAME"
  echo "case_file        : $CASE_FILE"
  echo "case md5         : $CASE_MD5"
  echo "case bytes       : $CASE_BYTES"
  echo "seed             : $SEED"
  echo "run_id           : $RUN_ID"
  echo "启动时刻         : $START_TS"
  echo "mode             : $MODE"
  echo "inner script     : $INNER （md5=$INNER_MD5）"
  echo "wrapper script   : kb/tools/run_guarded.sh （md5=$WRAPPER_MD5；build_uvs_opt/build_wave_cmd/assert_uvs_opt 均定义于此文件）"
  echo "命令原文         : $CMD_TEXT"
  echo "uvs.setup 夹具   : $FIXTURE （期望 md5=$EXPECTED_SETUP_MD5）"
  echo "uvs.setup 运行前 : $([ -f "$ROOT/uvs.setup" ] && md5sum "$ROOT/uvs.setup" | awk '{print $1}' || echo MISSING)"
  echo "compiled case     : ${COMPILED_CASE:-（未复制，仓库根/透传模式）}"
  echo "identity policy   : --case-file 与沙箱被编译件在 start / before-sim / end 各复检一次；"
  echo "                    不一致 ⇒ invalidated=true + rc!=0（task-16）"
  echo "锁身份(owner)      : PID \$\$ START … RUN … CASE … SEED …（task-15 陈旧判据）"
  echo "证据目录         : ${EVIDENCE_DIR#$ROOT/}"
  echo "=================================================================="
}
if [ "$DRY_RUN" = 1 ]; then
  emit_header
else
  emit_header | tee "$GUARD_LOG" >/dev/null
fi

identity_check "start"

if [ "$DRY_RUN" = 1 ]; then
  echo
  echo "[guard] 将执行（--mode $MODE）："
  if [ "$MODE" = "forward" ]; then
    echo "  $INNER -c $CASE -d $SEED ${PASSTHRU[*]:-}"
  else
    echo "  uvlan -work rtl -filelist $RTL_FILELIST $VLAN_OPT $ALL_OPT -logfile <evidence>/<stamp>_${CASE_NAME}_${SEED}_c_rtl.log \\"
    echo "        +incdir+./RTL/SRC/imports/SRC/pcie_controller +incdir+./BIN"
    echo "  uvlan -work tb ./$TB_FILE/tbtop.sv <case-file> $VLAN_OPT $ALL_OPT -logfile <evidence>/<stamp>_${CASE_NAME}_${SEED}_c_tb.log \\"
    echo "        $TB_DIR -define TEST_NAME=$CASE_NAME"
    [ "$MODE" = "full" ] && {
      dry_wave="${SANDBOX_ROOT:-$ROOT}/SIMLIB_RUN/wave/${CASE_NAME}_${SEED}"
      dry_elab="${EVIDENCE_DIR}/<stamp>_${CASE_NAME}_${SEED}_c_uvs.log"
      dry_run_log="${EVIDENCE_DIR}/<stamp>_${CASE_NAME}_${SEED}_run.log"
      echo "  uvs -top tbtop,glbl -debug f $(build_uvs_opt "$dry_elab" "$dry_wave" "$CASE_NAME" "$SEED") $ALL_OPT"
      echo "  ${dry_wave}/UVS_${CASE_NAME}_${SEED} -fixed_seed $SEED +UVM_TESTNAME=$CASE_NAME -logfile $dry_run_log +UVM_VERBOSITY=UVM_LOW $(build_wave_cmd "$dry_wave" "$CASE_NAME" "$SEED")"
    }
    echo "  工作根：${SANDBOX_ROOT:-$ROOT}（--sandbox-root 未给则仓库根，受 trap 自愈保护）"
  fi
  echo "[guard] 归档：跑前 sweep → 运行中 0.5s 轮询 sweep → 收尾 sweep，落 $ARCHIVE（只增不改）"
  exit 0
fi

cd "$ROOT" || exit 2
case "$MODE" in
  forward)
    # 纯转发：行为与直接跑 run_local.sh 一致；额外做归档 + 自愈
    archive_sweep
    touch "$POLL_FLAG"
    poller & POLLER_PID=$!
    echo "[guard] 转发执行：$INNER -c $CASE -d $SEED ${PASSTHRU[*]:-}" | tee -a "$GUARD_LOG"
    # forward：run_local.sh 内部硬编码 ./TESTLIB/<case>.sv；默认 --case-file 同路径，复检其 md5
    COMPILED_CASE="$CASE_FILE"
    run_tee "$INNER" -c "$CASE" -d "$SEED" ${PASSTHRU[@]+"${PASSTHRU[@]}"}
    rc=$RUN_TEE_RC
    stop_poller
    # 收尾 sweep 两次（稳定判定需要连续两次观测；`*.guarded` 就在上面几行才写出）
    archive_sweep; archive_sweep
    identity_check "end"
    # 运行日志带身份的归并件（不移动原件）：head + run.log
    if [ -f "$ROOT/SIMLIB_RUN/log/${CASE}_${SEED}_run.log" ]; then
      {
        sed -n '1,40p' "$GUARD_LOG"
        echo "==================== 原 run.log 起 ===================="
        cat "$ROOT/SIMLIB_RUN/log/${CASE}_${SEED}_run.log"
      } > "$EVIDENCE_DIR/${STAMP}_${CASE_NAME}_${SEED}_run.log.guarded"
      echo "[guard] 已生成带身份的运行日志：${EVIDENCE_DIR#$ROOT/}/${STAMP}_${CASE_NAME}_${SEED}_run.log.guarded" | tee -a "$GUARD_LOG"
    fi
    ;;
  compile-only|full)
    # 归档腿与 forward 一致：跑前 sweep + 运行中 0.5s 轮询。
    # E-2：本分支原先**根本没有启动轮询**，而它恰恰是最需要归档的两个模式。
    archive_sweep
    touch "$POLL_FLAG"
    poller & POLLER_PID=$!
    WORK="$ROOT"
    if [ -n "$SANDBOX_ROOT" ]; then
      if setup_sandbox "$SANDBOX_ROOT"; then
        WORK="$SANDBOX_ROOT"; SANDBOX_USED="yes"
      else
        echo "[WARN] 沙箱工作树创建失败 ⇒ 退化到仓库根运行（仍受 trap 自愈保护）" | tee -a "$GUARD_LOG" >&2
        SANDBOX_USED="no-fallback-reporoot"
      fi
    fi
    echo "[guard] 工作根：$WORK（sandbox=$SANDBOX_USED）" | tee -a "$GUARD_LOG"
    if [ "$SANDBOX_USED" = "yes" ]; then
      CASE_ARG="./cases/${CASE_NAME}.sv"
      COMPILED_CASE="$WORK/cases/${CASE_NAME}.sv"
      LOG_DIR="$EVIDENCE_DIR"
      WAVE_DIR="$WORK/SIMLIB_RUN/wave/${CASE_NAME}_${SEED}"
      write_sandbox_uvs_setup "$WORK" "$CASE_NAME" "$SEED"
    else
      CASE_ARG="$CASE_FILE"
      COMPILED_CASE="$CASE_FILE"
      LOG_DIR="$EVIDENCE_DIR"
      WAVE_DIR="$WORK/SIMLIB_RUN/wave/${CASE_NAME}_${SEED}"
      # 仓库根模式：同样不碰冻结件，只创建自己的 wave 目录与 uvs.setup（运行后由 trap 还原）
      mkdir -p "$WAVE_DIR" "$WORK/SIMLIB_RUN/log"
      write_sandbox_uvs_setup "$WORK" "$CASE_NAME" "$SEED"
    fi
    mkdir -p "$LOG_DIR" "$WAVE_DIR"
    # VENDOR_XILINX 判定（run_local.sh:63-77 同口径）
    VENDOR_XILINX=0
    if [ -f "$WORK/all_define.txt" ] && \
       grep -Eq '^[[:space:]]*-define[[:space:]]+["'\'']?VENDOR_XILINX["'\'']?([[:space:]]|$)' "$WORK/all_define.txt"; then
      VENDOR_XILINX=1; RTL_FILELIST="$RTL_FILELIST_XILINX"
    fi
    INCDIR_EXTRA=""
    CASE_DIR_REL=$(dirname "$CASE_ARG")
    if [ "$CASE_DIR_REL" != "./TESTLIB" ] && [ "$CASE_DIR_REL" != "TESTLIB" ]; then
      INCDIR_EXTRA="+incdir+${CASE_DIR_REL}"
      echo "[guard] 追加 +incdir+${CASE_DIR_REL}（用例不在 ./TESTLIB，唯一的包装层增量）" | tee -a "$GUARD_LOG"
    fi
    RTL_LOG="$LOG_DIR/${STAMP}_${CASE_NAME}_${SEED}_c_rtl.log"
    TB_LOG="$LOG_DIR/${STAMP}_${CASE_NAME}_${SEED}_c_tb.log"
    XLI_LOG="$LOG_DIR/${STAMP}_${CASE_NAME}_${SEED}_c_xli_lib.log"
    ELAB_LOG="$LOG_DIR/${STAMP}_${CASE_NAME}_${SEED}_c_uvs.log"
    RUN_LOG="$LOG_DIR/${STAMP}_${CASE_NAME}_${SEED}_run.log"
    # :308 / :302 按 run_local.sh 的表达式显式重建（唯一偏离：-logfile 指向证据目录）
    UVS_OPT="$(build_uvs_opt "$ELAB_LOG" "$WAVE_DIR" "$CASE_NAME" "$SEED")"
    WAVE_CMD_R="$(build_wave_cmd "$WAVE_DIR" "$CASE_NAME" "$SEED")"
    UVS_CMD_STR="uvs -top tbtop,glbl -debug f $UVS_OPT $ALL_OPT"
    RUN_CMD_STR="$WAVE_DIR/UVS_${CASE_NAME}_${SEED} -fixed_seed $SEED +UVM_TESTNAME=$CASE_NAME -logfile $RUN_LOG +UVM_VERBOSITY=UVM_LOW $WAVE_CMD_R"
    # 机器自检：-o / -logfile / 逐字选项不合格 ⇒ rc=3（不靠"看着对"）
    assert_uvs_opt "$UVS_OPT" "$ELAB_LOG" "$WAVE_DIR/UVS_${CASE_NAME}_${SEED}" || exit 3
    {
      echo "[guard] uvs 命令行原文（elaborate）：$UVS_CMD_STR"
      echo "[guard] 仿真命令行原文（run）      ：$RUN_CMD_STR"
    } | tee -a "$GUARD_LOG"
    cd "$WORK" || { echo "[FAIL] 无法进入工作根 $WORK" | tee -a "$GUARD_LOG" >&2; exit 3; }
    read -r -a _vlan <<< "$VLAN_OPT"
    read -r -a _all <<< "$ALL_OPT"
    if [ "$VENDOR_XILINX" = 1 ]; then
      _xli_argv=(uvlan -work xli_lib -filelist ./PKG/xilinx_lib/lib.txt "${_vlan[@]}" "${_all[@]}" -logfile "$XLI_LOG")
      echo "[guard] 执行：${_xli_argv[*]}" | tee -a "$GUARD_LOG"
      run_tee "${_xli_argv[@]}"
      echo "[guard] uvlan -work xli_lib rc=$RUN_TEE_RC" | tee -a "$GUARD_LOG"
    fi
    _rtl_argv=(uvlan -work rtl -filelist "$RTL_FILELIST" "${_vlan[@]}" "${_all[@]}" -logfile "$RTL_LOG" \
               +incdir+./RTL/SRC/imports/SRC/pcie_controller +incdir+./BIN)
    echo "[guard] 执行：${_rtl_argv[*]}" | tee -a "$GUARD_LOG"
    run_tee "${_rtl_argv[@]}"
    rc_rtl=$RUN_TEE_RC
    echo "[guard] 卡点B uvlan -work rtl rc=$rc_rtl（日志 ${RTL_LOG#$ROOT/}）" | tee -a "$GUARD_LOG"
    _tb_argv=(uvlan -work tb "./$TB_FILE/tbtop.sv" "$CASE_ARG" "${_vlan[@]}" "${_all[@]}" -logfile "$TB_LOG" \
              $TB_DIR)
    [ -n "$INCDIR_EXTRA" ] && _tb_argv+=("$INCDIR_EXTRA")
    _tb_argv+=(-define "TEST_NAME=$CASE_NAME")
    echo "[guard] 执行：${_tb_argv[*]}" | tee -a "$GUARD_LOG"
    run_tee "${_tb_argv[@]}"
    rc_tb=$RUN_TEE_RC
    echo "[guard] 卡点B uvlan -work tb rc=$rc_tb（日志 ${TB_LOG#$ROOT/}）" | tee -a "$GUARD_LOG"
    rc=$rc_rtl; [ "$rc_tb" != 0 ] && rc=$rc_tb
    if [ "$MODE" = "full" ] && [ "$rc" = 0 ]; then
      identity_check "before-sim"
      _uvs_argv=(); read -r -a _uvs_argv <<< "$UVS_CMD_STR"
      run_tee "${_uvs_argv[@]}"
      rc_uvs=$RUN_TEE_RC
      echo "[guard] uvs elaborate rc=$rc_uvs" | tee -a "$GUARD_LOG"
      rc=$rc_uvs
      if [ "$rc" = 0 ]; then
        if [ -f "$WAVE_DIR/UVS_${CASE_NAME}_${SEED}" ]; then
          echo "[guard] 可执行存在：$(ls -l "$WAVE_DIR/UVS_${CASE_NAME}_${SEED}")" | tee -a "$GUARD_LOG"
          _run_argv=(); read -r -a _run_argv <<< "$RUN_CMD_STR"
          run_tee "${_run_argv[@]}"
          rc=$RUN_TEE_RC
        else
          echo "[FAIL] 找不到 $WAVE_DIR/UVS_${CASE_NAME}_${SEED}（uvs elaborate 未产出可执行）" | tee -a "$GUARD_LOG" >&2
          rc=3
        fi
      fi
    fi
    cd "$ROOT" || true
    identity_check "end"
    ;;
esac
if [ "${INVALIDATED:-0}" = 1 ]; then
  echo "[identity] INVALIDATED=true ⇒ 强制 rc=3（本次证据作废）" | tee -a "$GUARD_LOG" >&2
  exit 3
fi
exit "${rc:-0}"
