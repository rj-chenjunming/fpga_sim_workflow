#!/usr/bin/env bash
# 把「冲突裁决快照」落到**可写数据根**，让 I4 真正生效（C10-c，2026-10-27）
#
# 为什么需要它：
#   裁决已经由人批示并落成快照（`doc/evidence/adjudication_20261027/`），但本机 `<ENV_ROOT>/kb`
#   是**文件系统级 ro 挂载** ⇒ 写不进真实数据根 ⇒ 真实轮次的 `I4_CONFLICTS_UNCLEARED` 仍在，
#   `G3` 的 `full_now`/`subset_only` 提交前仍被拒、N16 仍不可达。
#   本脚本把「落账 → 合并 → 校验 → I4 读数 → G3 解阻验证」封装成一条命令；
#   只要有一个**可写数据根**（`LOOP_WORKSPACE`），I4 就能真正清零。
#
# 用法：
#   bash spikes/apply_conflict_adjudication.sh --workspace <可写数据根>            # 真写
#   bash spikes/apply_conflict_adjudication.sh --workspace <可写数据根> --dry-run  # 只体检，不写
#   bash spikes/apply_conflict_adjudication.sh --workspace <可写数据根> --snapshot <快照目录>
#   # 2026-10-27（E1 预备）：快照可以换（例如带 4 条作者确认的
#   #   doc/evidence/adjudication_author_confirm_20261027）。指纹来源优先级：
#   #   ① --expect-md5 <adj_md5>:<conf_md5>（调用方显式给登记值）
#   #   ② <快照目录>/md5.txt（冻结快照自带的指纹清单）← 推荐
#   #   ③ 内置登记值（**只对**默认快照目录有效，防止有人拿别的快照绕过核验）
#
# 前置：`<数据根>/conflicts/` 已存在（含 conflicts.json）；`<数据根>/runs/` 里有一个 drill 夹具轮
#       才能做「G3 full_now 解阻」验证（没有则跳过该段并明说）。
# 不改原 ENV_ROOT、不改 `kb/tools/**`；只写目标数据根的 `conflicts/`。
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../.." && pwd)"
PY="$REPO/loop/.venv/bin/python"
[ -x "$PY" ] || { echo "[FAIL] 找不到 $PY（先按 README 建 venv）" >&2; exit 2; }

WS=""
DEFAULT_SNAPSHOT="$REPO/doc/evidence/adjudication_20261027"
SNAPSHOT="$DEFAULT_SNAPSHOT"
EXPECT_OVERRIDE=""
DRY=0
while [ $# -gt 0 ]; do
  case "$1" in
    --workspace) WS="${2:-}"; shift 2 ;;
    --workspace=*) WS="${1#--workspace=}"; shift ;;
    --snapshot) SNAPSHOT="${2:-}"; shift 2 ;;
    --snapshot=*) SNAPSHOT="${1#--snapshot=}"; shift ;;
    --expect-md5) EXPECT_OVERRIDE="${2:-}"; shift 2 ;;
    --expect-md5=*) EXPECT_OVERRIDE="${1#--expect-md5=}"; shift ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,34p' "$0"; exit 0 ;;
    *) echo "[FAIL] 未知参数：$1" >&2; exit 2 ;;
  esac
done
[ -n "$WS" ] && [ -d "$WS" ] || { echo "[FAIL] 需要 --workspace <已存在的可写数据根>" >&2; exit 2; }
WS="$(cd "$WS" && pwd)"          # 统一成绝对路径：下面 probe 在 $REPO/loop 里跑
CONF="$WS/conflicts"
[ -d "$CONF" ] && [ -f "$CONF/conflicts.json" ] || {
  echo "[FAIL] 目标数据根缺 conflicts/conflicts.json：$CONF" >&2; exit 2; }
[ -d "$SNAPSHOT" ] || { echo "[FAIL] 快照目录不存在：$SNAPSHOT" >&2; exit 2; }
SNAPSHOT="$(cd "$SNAPSHOT" && pwd)"
[ -f "$SNAPSHOT/adjudication.json" ] || {
  echo "[FAIL] 快照缺 adjudication.json：$SNAPSHOT" >&2; exit 2; }

# 快照指纹必须可核（红线 10：引用冻结文件必须带 md5）。来源优先级见头部用法 ①②③。
# 历史：这里曾把 72 条快照的 md5 硬编码，导致 E1 拿"带 4 条作者确认的新快照"跑会被误挡（2026-10-27）。
LEGACY_ADJ="d6ec87796f72f40dcfd124cbfc7af991"
LEGACY_CONF="47300360ba208012d262bc673a1d07d9"
EXPECT_ADJ=""
EXPECT_CONF=""
FP_SRC=""
if [ -n "$EXPECT_OVERRIDE" ]; then
  case "$EXPECT_OVERRIDE" in
    *:*) EXPECT_ADJ="${EXPECT_OVERRIDE%%:*}"; EXPECT_CONF="${EXPECT_OVERRIDE##*:}" ;;
    *) echo "[FAIL] --expect-md5 需要 <adj_md5>:<conf_md5>" >&2; exit 2 ;;
  esac
  FP_SRC="--expect-md5（调用方给）"
elif [ -f "$SNAPSHOT/md5.txt" ]; then
  EXPECT_ADJ="$(awk '$2=="adjudication.json"{print $1; exit}' "$SNAPSHOT/md5.txt")"
  EXPECT_CONF="$(awk '$2=="conflicts.json"{print $1; exit}' "$SNAPSHOT/md5.txt")"
  FP_SRC="$SNAPSHOT/md5.txt（快照自带）"
elif [ "$SNAPSHOT" = "$DEFAULT_SNAPSHOT" ]; then
  EXPECT_ADJ="$LEGACY_ADJ"
  EXPECT_CONF="$LEGACY_CONF"
  FP_SRC="脚本内置登记值（默认快照）"
fi
if [ -z "$EXPECT_ADJ" ] || [ -z "$EXPECT_CONF" ]; then
  echo "[FAIL] 快照缺少可核指纹（红线 10）：$SNAPSHOT" >&2
  echo "  要么让快照目录带 md5.txt，要么用 --expect-md5 <adj_md5>:<conf_md5> 给登记值" >&2
  exit 3
fi
got_adj="$(md5sum "$SNAPSHOT/adjudication.json" | awk '{print $1}')"
got_conf="$(md5sum "$SNAPSHOT/conflicts.json" | awk '{print $1}')"
if [ "$got_adj" != "$EXPECT_ADJ" ] || [ "$got_conf" != "$EXPECT_CONF" ]; then
  echo "[FAIL] 快照指纹与登记不符（红线 10）：" >&2
  echo "  adjudication.json 期望 $EXPECT_ADJ 实际 $got_adj" >&2
  echo "  conflicts.json    期望 $EXPECT_CONF 实际 $got_conf" >&2
  exit 3
fi

echo "[info] 目标数据根：$WS"
echo "[info] 快照：$SNAPSHOT（指纹校验通过；来源：$FP_SRC）"

probe () {  # $1 = 标签
  ( cd "$REPO/loop" && LOOP_WORKSPACE="$WS" "$PY" -B - "$WS" "$1" <<'PYEOF'
import sys
sys.path.insert(0, ".")
from pathlib import Path
from services import contracts
ws = Path(sys.argv[1])
kb = contracts.KbSources.from_workspace(ws)
s = contracts._conflict_summary(kb)
print("[%s] I4 读数：conflicts=%d，blocks_release=%d，open=%d"
      % (sys.argv[2], s["total"], s["blocks_release"], s["open"]))
PYEOF
  )
}

g3_probe () {
  ( cd "$REPO/loop" && LOOP_WORKSPACE="$WS" "$PY" -B - "$WS" <<'PYEOF'
import sys
sys.path.insert(0, ".")
from pathlib import Path
from services import contracts
from workflows.chunks.gates import GatePreconditionFailed, precheck_decision
ws = Path(sys.argv[1])
kb = contracts.KbSources.from_workspace(ws)
runs = sorted(p for p in (ws / "runs").glob("RUN-*") if (p / "n2_diff.json").exists())
if not runs:
    print("[g3 ] 跳过：数据根里没有含 n2_diff.json 的 drill 轮")
    raise SystemExit(0)
run = runs[0]
for decision in ("full_now", "subset_only"):
    try:
        precheck_decision(gate="G3_regression_decision", decision=decision,
                          run_dir=run, mode="drill", reason="I4 生效验证", kb=kb)
        print("[g3 ] %-11s 提交前检查：通过（I4 不再阻断）" % decision)
    except GatePreconditionFailed as exc:
        print("[g3 ] %-11s 仍被拒：%s" % (decision, str(exc)[:120]))
PYEOF
  )
}

n16_probe () {
  ( cd "$REPO/loop" && LOOP_WORKSPACE="$WS" "$PY" -B - "$WS" "$1" <<'PYEOF'
import sys
sys.path.insert(0, ".")
from pathlib import Path
from services import contracts
ws = Path(sys.argv[1])
kb = contracts.KbSources.from_workspace(ws)
runs = sorted(p for p in (ws / "runs").glob("RUN-*") if (p / "n2_diff.json").exists())
if not runs:
    print("[n16] 跳过：没有含 n2_diff.json 的轮")
    raise SystemExit(0)
bl = contracts.compute_blockers(run_dir=runs[0], counts=None, kb=kb,
                                slot_status=None, job=None, mode="drill")
codes = [b["code"] for b in bl]
print("[n16] %s blockers=%s；I4 在列=%s"
      % (sys.argv[2], codes, "I4_CONFLICTS_UNCLEARED" in codes))
PYEOF
  )
}

echo "== 1) 生效前 =="
probe before
g3_probe
n16_probe before

if [ "$DRY" = "1" ]; then
  echo "== dry-run：不写任何文件 =="
  exit 0
fi

echo "== 2) 落账：复制 adjudication.json 并重跑抽取合并 =="
cp "$SNAPSHOT/adjudication.json" "$CONF/adjudication.json" || {
  echo "[FAIL] 复制失败（数据根不可写？）" >&2; exit 4; }
"$PY" -B "$REPO/kb/tools/n1_conflicts.py" --outdir "$CONF" 2>&1 | grep -E "^\[merge\]|^\[stat\] conflicts " \
  || { echo "[FAIL] 抽取/合并失败" >&2; exit 5; }
"$PY" -B "$REPO/kb/tools/adjudicate_conflicts.py" --outdir "$CONF" --verify || {
  echo "[FAIL] 裁决与清单一致性校验失败" >&2; exit 6; }

echo "== 3) 生效后 =="
probe after
g3_probe
n16_probe after

cat <<'MSG'

== 下一步（人）==
1) 真实轮次重新走到 G3 时，`full_now/subset_only` 应不再被 I4 拒（闸门仍按其它不变量判）。
2) N16 的前置只剩 I2/I3/I7 等条件；`I4_CONFLICTS_UNCLEARED` 应不再出现。
3) 若要撤销这批裁决：从 `adjudication.json` 删除对应记录或追加改判（不提供静默回滚）。
MSG
