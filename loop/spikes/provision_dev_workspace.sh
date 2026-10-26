#!/usr/bin/env bash
# 构造「可写数据根」的唯一实现（持久副本 / 一次性影子，两种模式一个脚本）。
#
# 为什么需要：
#   kb_lib 的数据根（WORKSPACE_ROOT）默认 = ENV_ROOT/kb，本机该目录**只读**
#   （软件层测试要写 runs/、slot、events、recovery 等）。用 `$LOOP_WORKSPACE` 指到
#   可写目录即可，但必须把 drill 夹具与 baseline/index/conflicts 带过去，否则大量用例
#   会因「drill 夹具不完整 / 基线为空」失败 —— 那不是代码缺陷（见 STATUS §71.5）。
#
# 两种模式（2026-10-26 A2：此前 `run_software_checks.sh` 自带一份几乎相同的构造逻辑，
# 两份脚本各写一遍「复制哪些目录、夹具在不在」，口径容易漂；现在只剩这一份实现）：
#   * 持久副本（默认）：`<repo>/.dev-ws`，drill 夹具**复制**（约 733 MB），供 e2e/手工演示；
#   * 一次性影子（`--link-fixture`）：调用方给 `DEST`（通常 mktemp -d），drill 夹具与
#     `baselines/` 用**符号链接**（不复制 733 MB），供软件层单测，用完删除。
#
# 用法：
#   bash spikes/provision_dev_workspace.sh                    # 持久副本到 <repo>/.dev-ws
#   bash spikes/provision_dev_workspace.sh --cleanup          # 删除该目录
#   bash spikes/provision_dev_workspace.sh --force            # 已存在也重建
#   DEST=$(mktemp -d) bash spikes/provision_dev_workspace.sh --link-fixture --force --quiet
#   DEST=/some/path bash spikes/provision_dev_workspace.sh
#
# 之后跑测试：
#   LOOP_WORKSPACE=<DEST> LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q
# 或直接用封装入口：`bash spikes/run_software_checks.sh`
#
# 重要约束：
#   1. 目录在仓库内 ⇒ `doc/audit/check_doc_links.py` 会把拷贝来的环境文档一起扫（会多出
#      missing）。**文档门请在 --cleanup 之后、或预置之前跑**。
#   2. 只读源：脚本只从 ENV_ROOT 复制/链接，绝不写入环境仓（红线 11）；目标是**派生副本**。
#   3. 目录不入库：默认落在 <repo>/.dev-ws，仓库通过本仓本地 .git/info/exclude 忽略。
#   4. 数据根解析**复用 kb_lib**（唯一解析器），脚本内不另写一套路径规则。
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$REPO/loop/.venv/bin/python"
DEST="${DEST:-$REPO/.dev-ws}"
FORCE=0
CLEANUP=0
LINK_FIXTURE=0
QUIET=0
TOLERATE_MISSING=0
for arg in "$@"; do
  case "$arg" in
    --cleanup) CLEANUP=1 ;;
    --force) FORCE=1 ;;
    --link-fixture) LINK_FIXTURE=1 ;;
    --quiet) QUIET=1 ;;
    --tolerate-missing-fixture) TOLERATE_MISSING=1 ;;
    -h|--help) sed -n '2,33p' "$0"; exit 0 ;;
    *) echo "[FAIL] 未知参数：$arg（用 --help）" >&2; exit 2 ;;
  esac
done

say () { [ "$QUIET" = "1" ] || echo "$@"; }
note () { [ "$QUIET" = "1" ] || echo "$@" >&2; }

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
# 导入路径按**本脚本所在的仓库根**解析：脚本既可从 `loop/` 也能从仓根执行，
# 不能依赖调用者 cwd（2026-10-26 实测：在 `loop/` 下按文件头用法执行会因相对路径
# `kb/tools` 找不到 `kb_lib` 而直接失败）。
read -r ENV_ROOT SRC_ROOT < <(REPO0="$REPO" "$PY" - <<'PYEOF'
import os
import sys
sys.path.insert(0, os.path.join(os.environ["REPO0"], "kb", "tools"))
import kb_lib as K
print(K.ENV_ROOT, K.WORKSPACE_ROOT)
PYEOF
) || { echo "[FAIL] kb_lib 解析失败" >&2; exit 2; }
[ -n "${ENV_ROOT:-}" ] && [ -n "${SRC_ROOT:-}" ] || { echo "[FAIL] 空解析结果" >&2; exit 2; }

if [ -d "$DEST" ] && [ "$FORCE" != "1" ]; then
  say "[OK] 已存在：$DEST（重建用 --force）"
  say "     LOOP_WORKSPACE=$DEST"
  exit 0
fi
[ -d "$DEST" ] && { chmod -R u+w "$DEST" 2>/dev/null; rm -rf "$DEST"; }

FIXTURE_RUN="RUN-20261015-120626"
FIXTURE="$SRC_ROOT/runs/$FIXTURE_RUN"
if [ ! -d "$FIXTURE" ]; then
  if [ "$TOLERATE_MISSING" = "1" ]; then
    note "[warn] 缺 drill 夹具轮 $FIXTURE_RUN；依赖它的用例会失败（不是软件层缺陷）"
  else
    echo "[FAIL] 只读数据根里没有 drill 夹具：$FIXTURE" >&2
    exit 1
  fi
fi

mkdir -p "$DEST/runs" || exit 1
if [ "$LINK_FIXTURE" = "1" ]; then
  # 一次性影子：夹具 733 MB 只读，链接即可（软件层用例不写夹具轮内文件）。
  note "[..] 链接 drill 夹具（不复制）：$FIXTURE"
  [ -d "$FIXTURE" ] && { ln -s "$FIXTURE" "$DEST/runs/$FIXTURE_RUN" || exit 1; }
else
  note "[..] 复制 drill 夹具（约 733 MB）：$FIXTURE"
  [ -d "$FIXTURE" ] && { cp -a "$FIXTURE" "$DEST/runs/" || { echo "[FAIL] 夹具复制失败" >&2; exit 1; }; }
fi

for d in index conflicts adjudication; do
  if [ -d "$SRC_ROOT/$d" ]; then
    cp -a "$SRC_ROOT/$d" "$DEST/" || { echo "[FAIL] 复制 $d 失败" >&2; exit 1; }
  fi
done
if [ -d "$SRC_ROOT/baselines" ]; then
  if [ "$LINK_FIXTURE" = "1" ]; then
    ln -s "$SRC_ROOT/baselines" "$DEST/baselines" || exit 1   # 只读基线：用例只读，链接省 3 MB
  else
    cp -a "$SRC_ROOT/baselines" "$DEST/" || { echo "[FAIL] 复制 baselines 失败" >&2; exit 1; }
  fi
fi
[ -f "$SRC_ROOT/FIXTURE_IDENTITY.md" ] && cp -a "$SRC_ROOT/FIXTURE_IDENTITY.md" "$DEST/"

# 自检：夹具关键件必须齐（缺件时本地 R2 的启动期校验会显式失败，这里提前说清楚）。
MISSING=()
for f in n1_manifest_new.json n2_diff.json n5_impact.json n12_report.md evidence; do
  [ -e "$DEST/runs/$FIXTURE_RUN/$f" ] || MISSING+=("$f")
done
if [ ${#MISSING[@]} -gt 0 ]; then
  if [ "$TOLERATE_MISSING" = "1" ]; then
    note "[warn] 夹具缺件：${MISSING[*]}（依赖这些材料的用例会失败）"
  else
    echo "[FAIL] 夹具缺件：${MISSING[*]}" >&2
    exit 1
  fi
fi

say "[OK] 可写数据根就绪：$DEST"
if [ "$LINK_FIXTURE" != "1" ]; then
  say "     跑测试："
  say "       cd $REPO/loop && LOOP_WORKSPACE=$DEST LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q"
  say "     用完清理（跑文档门前必须）："
  say "       bash $REPO/loop/spikes/provision_dev_workspace.sh --cleanup"
fi
exit 0
