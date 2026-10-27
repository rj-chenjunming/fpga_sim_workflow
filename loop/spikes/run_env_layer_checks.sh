#!/usr/bin/env bash
# 环境层（`@pytest.mark.env_layer`）用例的可运行入口：在**派生 ENV_ROOT 副本**上跑，原环境零写入。
#
# 为什么需要（C 组 C13，2026-10-27）：
#   这 3 条用例（`test_archive_e2` ×2、`test_projection_and_frozen` ×1）要写 ENV_ROOT 下的
#   `SIMLIB_RUN/`、归档与数据根，而本机 ENV_ROOT 是**只读**挂载 ⇒ 直接跑必然红，长期只能
#   "登记为环境缺件"（`spikes/run_software_checks.sh` 默认 `-m "not env_layer"` 排除它们）。
#   红线 11 禁止写**原** ENV_ROOT，但不禁止在**派生副本**上验证（与 S0 派生副本同一原则）。
#   实测（2026-10-27）：派生副本上 3 条全过，原 ENV_ROOT `find -newer` 命中数 = 0。
#
# 用法：
#   bash spikes/run_env_layer_checks.sh              # 建/复用派生副本并跑 3 条
#   bash spikes/run_env_layer_checks.sh --reuse      # 复用已有副本（跳过 2.6 GB 复制）
#   bash spikes/run_env_layer_checks.sh --cleanup    # 删除派生副本
#   COPY=/some/path bash spikes/run_env_layer_checks.sh
#   bash spikes/run_env_layer_checks.sh tests/test_archive_e2.py -q   # 追加 pytest 参数
#
# 约束：
#   1. **只读源**：脚本只从 ENV_ROOT 复制，绝不写原目录；跑完用 `find -newer` 断言零写入。
#   2. 副本默认落在 <repo>/.env-copy（2.6 GB，仓库本地 .git/info/exclude 忽略）。
#   3. 副本与软件层影子根分开：环境层用例需要"数据根位于 ENV_ROOT 之内"的布局
#      （`test_projection_and_frozen` 的 `relative_to(ENV_ROOT)`），影子根不满足。
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$REPO/loop/.venv/bin/python"
COPY="${COPY:-$REPO/.env-copy}"
CLEANUP=0
REUSE=0
PASSTHRU=()
for arg in "$@"; do
  case "$arg" in
    --cleanup) CLEANUP=1 ;;
    --reuse) REUSE=1 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) PASSTHRU+=("$arg") ;;
  esac
done

if [ "$CLEANUP" = "1" ]; then
  if [ -d "$COPY" ]; then
    chmod -R u+w "$COPY" 2>/dev/null
    rm -rf "$COPY" || { echo "[FAIL] 删除失败：$COPY" >&2; exit 1; }
    echo "[OK] 已删除派生 ENV_ROOT：$COPY"
  else
    echo "[OK] 不存在，无需删除：$COPY"
  fi
  exit 0
fi

if [ ! -x "$PY" ]; then
  echo "[FAIL] 找不到 $PY（先按 README 建 venv）" >&2
  exit 2
fi

# 环境根的唯一解析器是 kb_lib（不在这里重复实现路径规则）。
read -r ENV_ROOT < <(REPO0="$REPO" PYTHONDONTWRITEBYTECODE=1 "$PY" -B - <<'PYEOF'
import os
import sys
sys.dont_write_bytecode = True          # 不往冻结的 kb/tools 写 __pycache__（红线 11）
sys.path.insert(0, os.path.join(os.environ["REPO0"], "kb", "tools"))
import kb_lib as K
print(K.ENV_ROOT)
PYEOF
) || { echo "[FAIL] kb_lib 解析失败" >&2; exit 2; }
[ -n "${ENV_ROOT:-}" ] && [ -d "$ENV_ROOT" ] || {
  echo "[FAIL] 环境根不存在：${ENV_ROOT:-<空>}" >&2; exit 2; }

if [ "$REUSE" = "1" ] && [ -d "$COPY" ]; then
  echo "[info] 复用派生 ENV_ROOT：$COPY" >&2
else
  if [ -d "$COPY" ]; then
    chmod -R u+w "$COPY" 2>/dev/null
    rm -rf "$COPY"
  fi
  echo "[..] 复制派生 ENV_ROOT（约 2.6 GB，只在副本上写）：$ENV_ROOT → $COPY" >&2
  cp -a --reflink=auto "$ENV_ROOT" "$COPY" || { echo "[FAIL] 派生副本复制失败" >&2; exit 1; }
  chmod -R u+w "$COPY" || { echo "[FAIL] 副本 chmod 失败" >&2; exit 1; }
fi

# 零写入见证：marker 在**跑测试之前**创建，跑完检查原 ENV_ROOT 是否有比它新的文件。
MARKER="$(mktemp "${TMPDIR:-/tmp}/env-layer-marker-XXXXXX")"
trap 'rm -f "$MARKER"' EXIT

echo "[info] 环境层用例：3 项（test_archive_e2 ×2、test_projection_and_frozen ×1）" >&2
echo "[info] 数据根 = 副本内的 kb（满足『数据根位于 ENV_ROOT 之内』的布局要求）" >&2
cd "$REPO/loop"
set -o pipefail
LOOP_ENV_ROOT="$COPY" LOOP_WORKSPACE="$COPY/kb" LOOP_LLM_MODE="${LOOP_LLM_MODE:-standin}" \
  "$PY" -m pytest -q -m env_layer \
  tests/test_archive_e2.py tests/test_projection_and_frozen.py "${PASSTHRU[@]}"
RC=$?

# 红线 11 见证：原 ENV_ROOT 必须零写入。
TOUCHED="$(find "$ENV_ROOT" -newer "$MARKER" 2>/dev/null | head -20)"
if [ -n "$TOUCHED" ]; then
  echo "[FAIL] 原 ENV_ROOT 出现新写入（红线 11）：" >&2
  printf '%s\n' "$TOUCHED" >&2
  exit 3
fi
echo "[info] 原 ENV_ROOT 零写入（find -newer 命中 0）" >&2
exit "$RC"
