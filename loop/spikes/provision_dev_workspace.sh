#!/usr/bin/env bash
# 预置「可写开发数据根」：把 drill 夹具与 kb 小数据复制到仓内可写目录。
#
# 为什么需要：
#   kb_lib 的数据根（WORKSPACE_ROOT）默认 = ENV_ROOT/kb，本机该目录**只读**
#   （软件层测试要写 runs/、slot、events、recovery 等）。用 `$LOOP_WORKSPACE` 指到
#   可写目录即可，但必须把 drill 夹具与 baseline/index/conflicts 带过去，否则大量用例
#   会因「drill 夹具不完整 / 基线为空」失败 —— 那不是代码缺陷（见 STATUS §71.5）。
#
# 用法：
#   bash spikes/provision_dev_workspace.sh            # 建到 <repo>/.dev-ws 并打印用法
#   bash spikes/provision_dev_workspace.sh --cleanup   # 删除该目录
#   bash spikes/provision_dev_workspace.sh --force     # 已存在也重建
#   DEST=/some/path bash spikes/provision_dev_workspace.sh
#
# 之后跑测试：
#   LOOP_WORKSPACE=<repo>/.dev-ws LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q
#
# 重要约束：
#   1. 目录在仓库内 ⇒ `doc/audit/check_doc_links.py` 会把拷贝来的环境文档一起扫（会多出
#      missing）。**文档门请在 --cleanup 之后、或预置之前跑**。
#   2. 只读源：脚本只从 ENV_ROOT 复制，绝不写入环境仓（红线 11）；目标是**派生副本**。
#   3. 目录不入库：默认落在 <repo>/.dev-ws，仓库通过本仓本地 .git/info/exclude 忽略。
#   4. 数据根解析**复用 kb_lib**（唯一解析器），脚本内不另写一套路径规则。
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$REPO/loop/.venv/bin/python"
DEST="${DEST:-$REPO/.dev-ws}"
FORCE=0
CLEANUP=0
for arg in "$@"; do
  case "$arg" in
    --cleanup) CLEANUP=1 ;;
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "[FAIL] 未知参数：$arg（用 --help）" >&2; exit 2 ;;
  esac
done

if [ "$CLEANUP" = "1" ]; then
  if [ -d "$DEST" ]; then
    chmod -R u+w "$DEST" 2>/dev/null
    rm -rf "$DEST" || { echo "[FAIL] 删除失败：$DEST" >&2; exit 1; }
    echo "[OK] 已删除可写数据根：$DEST"
  else
    echo "[OK] 不存在，无需删除：$DEST"
  fi
  exit 0
fi

if [ ! -x "$PY" ]; then
  echo "[FAIL] 找不到 $PY（先按 README 建 venv）" >&2
  exit 2
fi

# 数据根/环境根的唯一解析器是 kb_lib（不在这里重复实现路径规则）。
read -r ENV_ROOT SRC_ROOT < <("$PY" - <<'PYEOF'
import sys
sys.path.insert(0, "kb/tools")
import kb_lib as K
print(K.ENV_ROOT, K.WORKSPACE_ROOT)
PYEOF
) || { echo "[FAIL] kb_lib 解析失败" >&2; exit 2; }
[ -n "${ENV_ROOT:-}" ] && [ -n "${SRC_ROOT:-}" ] || { echo "[FAIL] 空解析结果" >&2; exit 2; }

if [ -d "$DEST" ] && [ "$FORCE" != "1" ]; then
  echo "[OK] 已存在：$DEST（重建用 --force）"
  echo "     LOOP_WORKSPACE=$DEST"
  exit 0
fi
[ -d "$DEST" ] && { chmod -R u+w "$DEST" 2>/dev/null; rm -rf "$DEST"; }

FIXTURE="$SRC_ROOT/runs/RUN-20261015-120626"
if [ ! -d "$FIXTURE" ]; then
  echo "[FAIL] 只读数据根里没有 drill 夹具：$FIXTURE" >&2
  exit 1
fi

mkdir -p "$DEST/runs" || exit 1
echo "[..] 复制 drill 夹具（约 733 MB）：$FIXTURE"
cp -a "$FIXTURE" "$DEST/runs/" || { echo "[FAIL] 夹具复制失败" >&2; exit 1; }

for d in baselines index conflicts adjudication; do
  if [ -d "$SRC_ROOT/$d" ]; then
    cp -a "$SRC_ROOT/$d" "$DEST/" || { echo "[FAIL] 复制 $d 失败" >&2; exit 1; }
  fi
done
[ -f "$SRC_ROOT/FIXTURE_IDENTITY.md" ] && cp -a "$SRC_ROOT/FIXTURE_IDENTITY.md" "$DEST/"

# 自检：夹具关键件必须齐（缺件时本地 R2 的启动期校验会显式失败，这里提前说清楚）。
MISSING=()
for f in n1_manifest_new.json n2_diff.json n5_impact.json n12_report.md evidence; do
  [ -e "$DEST/runs/RUN-20261015-120626/$f" ] || MISSING+=("$f")
done
if [ ${#MISSING[@]} -gt 0 ]; then
  echo "[FAIL] 夹具缺件：${MISSING[*]}" >&2
  exit 1
fi

echo "[OK] 可写数据根就绪：$DEST"
echo "     跑测试："
echo "       cd $REPO/loop && LOOP_WORKSPACE=$DEST LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q"
echo "     用完清理（跑文档门前必须）："
echo "       bash $REPO/loop/spikes/provision_dev_workspace.sh --cleanup"
