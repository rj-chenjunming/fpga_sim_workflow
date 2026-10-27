#!/usr/bin/env bash
# 冲突清单 72 条裁决 · 一键签署脚本（C10-b，2026-10-27）
#
# 分工：**判据与命令由 Lead 准备；执行（= 签字）必须由人来做**。
#   `kb/tools/adjudicate_conflicts.py` 强制 `--actor human:<name>`，拒绝 model:/host:；
#   schema 原文：conflicts 的 status「由人裁决推进；模型只能写 open 或提出建议，不能自封 ruled」。
#   所以本脚本不内置任何名字：你不给 ACTOR，它什么都不写。
#
# 用法：
#   # 1) 先空跑（不写任何文件，只打印将写什么）
#   ACTOR=human:<你的名字> OUTDIR=<可写数据根的 conflicts 目录> bash conflicts_sign_20261027.sh --dry-run
#   # 2) 确认无误后真签
#   ACTOR=human:<你的名字> OUTDIR=<可写数据根的 conflicts 目录> bash conflicts_sign_20261027.sh
#   # 3) 若由他人代录（人已批示、Host 执行），必须写清代录事实：
#   ACTOR=human:<批示人> NOTE_SUFFIX="（人工批示，Host 工具代录 2026-10-27）" OUTDIR=... bash ...
#
# OUTDIR 示例：
#   * 演练（派生副本，不碰真实环境）：OUTDIR="/path/to/repo/.env-copy/kb/conflicts"
#     （副本由 `loop/spikes/run_env_layer_checks.sh` 预置，2.6 GB，只在副本上写）
#   * 正式生效：指向**有写权**的数据根 conflicts/（本机 <ENV_ROOT>/kb 只读，不能直接写）
#
# 裁决内容来源：doc/evidence/CONFLICTS_SIGNING_20261027.md（68 条批量分组 + 4 条 core 定值），
# 分组判据原文照抄 <ENV_ROOT>/kb/adjudication/C_conflicts_triage.md §4.1（md5 bc862a68…）。
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
TOOL="$REPO/kb/tools/adjudicate_conflicts.py"
OUTDIR="${OUTDIR:-}"
ACTOR="${ACTOR:-}"
#: 代录时必须显式标注（亲笔签署时留空）
NOTE_SUFFIX="${NOTE_SUFFIX:-}"
DRY=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    -h|--help) sed -n '2,26p' "$0"; exit 0 ;;
    *) echo "[FAIL] 未知参数：$a" >&2; exit 2 ;;
  esac
done

if [ -z "$OUTDIR" ] || [ ! -d "$OUTDIR" ]; then
  echo "[FAIL] 需要 OUTDIR=<已存在的 conflicts 目录>（当前：'${OUTDIR}'）" >&2
  exit 2
fi
if [ -z "$ACTOR" ]; then
  echo "[FAIL] 需要 ACTOR=human:<你的名字>（这是「谁签的字」，不替你填）" >&2
  exit 2
fi
case "$ACTOR" in
  human:?*) : ;;
  *) echo "[FAIL] ACTOR 必须以 human: 开头（当前 '$ACTOR'）" >&2; exit 2 ;;
esac
[ -x "$REPO/loop/.venv/bin/python" ] && PY="$REPO/loop/.venv/bin/python" || PY="python3"

adj () {  # adj <ids> <resolution>
  local ids="$1" res="$2${NOTE_SUFFIX}" extra=()
  [ "$DRY" = "1" ] && extra=(--dry-run)
  "$PY" -B "$TOOL" --outdir "$OUTDIR" --actor "$ACTOR" --ids "$ids" --status ruled \
    --resolution "$res" "${extra[@]}" || { echo "[FAIL] 该组签署失败：$ids" >&2; exit 1; }
}

echo "== 68 条批量（triage G1–G9；一条 id 只入一组）=="
adj "C19,C23,C28,C32,C33,C35,C36,C37,C41,C46,C48,C68" \
    "地址以文档自洽一方为准（段头∨总表∨实际占用取一致者），登记文档勘误；G1 批量裁决（triage G1）"
adj "C1,C3,C15,C70" \
    "Reset 以位定义表为准，汇总表值登记勘误；G2 批量裁决（triage G2）"
adj "C4,C8,C16,C43,C44,C49,C69" \
    "R/W 以位定义表为准（状态类应只读，不做写回比对）；G3 批量裁决（triage G3）"
adj "C7,C9,C18,C25,C27,C39" \
    "位段按同表规律修正（重叠与跳空按笔误处理）；G4 批量裁决（triage G4）"
adj "C5,C6,C12,C14,C31,C40,C42,C52,C54,C64" \
    "以位定义表补全汇总与位定义；无定义者（C42）用例按已定义范围裁剪并显式标注未覆盖；G5 批量裁决（triage G5）"
adj "C10,C13,C17,C24,C26,C45,C51,C59,C60,C62" \
    "命名以位定义表/字段名为准，汇总侧拼写登记勘误；用例按 entry_id 关联而非 name；G6 批量裁决（triage G6）"
adj "C20,C21,C22,C29,C30,C47,C53,C61,C65,C66,C67,C71,C72" \
    "编号与格式勘误，不改变寄存器语义；用例引用一律带行号；G7 批量裁决（triage G7）"
adj "C34,C50,C55,C63" \
    "以位定义表可枚举范围为准写入索引，文档口径差异登记，用例矩阵按已定义范围；G8 批量裁决（triage G8）"
adj "C56,C57" \
    "模板/元信息残留，无寄存器语义；G9 批量裁决（triage G9）"

echo "== 4 条 Tier B-core（2026-10-27 人已定值）=="
adj "C2" \
    "以位定义表为准：0x0004 fpga_date Reset = 2023_0911；汇总表 0x2023_0804 登记勘误（2026-10-27 人裁决）"
adj "C11" \
    "以位定义表为准：0x0080 fpga_test Reset = 0x0；汇总表 0x5555aaaa（自测图案）登记勘误（2026-10-27 人裁决）"
adj "C38" \
    "以位定义表逐位推导为准：i2c_polling_cfg Reset = 0xF0（bit7:4=0xf、bit0=0）；汇总表 0x10 登记勘误（2026-10-27 人裁决）"
adj "C58" \
    "以 DFX_VERSION=0x25092913（≈2025-09-29）为当前版本/日期基准；0x0004 fpga_date 的 2023 值登记为历史遗留（2026-10-27 人裁决）"

if [ "$DRY" = "1" ]; then
  echo "== dry-run 结束：没有写任何文件；去掉 --dry-run 即为真签 =="
  exit 0
fi

echo "== 签署后核对 =="
"$PY" -B "$TOOL" --outdir "$OUTDIR" --list
"$PY" -B "$TOOL" --outdir "$OUTDIR" --verify
echo "== 如仍阻断数 > 0，请把上面的 --list 输出发给 Lead 核对 =="
