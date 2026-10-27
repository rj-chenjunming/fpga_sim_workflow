#!/usr/bin/env bash
# 环境类检查的**统一入口**：在**派生 ENV_ROOT 副本**上跑，原环境零写入。
#
# 覆盖两类「需要可写环境/数据根」的检查（K1，2026-10-27）：
#   ① 3 条 `@pytest.mark.env_layer` 用例（`test_archive_e2` ×2、`test_projection_and_frozen` ×1）—— 默认跑；
#   ② 3 个 kb 自测（`_selftest_gate_schema` / `_selftest_n5_reachability` /
#      `_selftest_adjudicate_conflicts`）—— 加 `--with-kb-selftests` 才跑。
#
# 为什么需要（C 组 C13 + K1）：
#   这些检查要写 ENV_ROOT 下的 `SIMLIB_RUN/`、归档与数据根，而本机 ENV_ROOT 是**只读**挂载 ⇒ 直接跑必然红，
#   长期只能"登记为环境缺件"（`spikes/run_software_checks.sh` 默认 `-m "not env_layer"` 排除它们）。
#   红线 11 禁止写**原** ENV_ROOT，但不禁止在**派生副本**上验证（与 S0 派生副本同一原则）。
#   kb 自测此前要**手拼** `LOOP_ENV_ROOT`/`LOOP_WORKSPACE` 指向派生副本：忘了指就在只读真实根上失败，
#   指错根则数字不可比（K1 的问题陈述）。本脚本把两类检查挂到**同一个**副本上，一条命令跑完。
#   实测（2026-10-27）：3 条 env_layer 全过 + `PASS=10` / `PASS=9` / `PASS=28`；原 ENV_ROOT `find -newer` 命中 0。
#
# 用法：
#   bash spikes/run_env_layer_checks.sh                       # 只跑 env_layer 3 条
#   bash spikes/run_env_layer_checks.sh --with-kb-selftests   # 3 条 env_layer + 3 个 kb 自测（一条命令跑完）
#   bash spikes/run_env_layer_checks.sh --with-kb-selftests --reuse   # 复用已有副本（跳过 2.6 GB 复制）
#   bash spikes/run_env_layer_checks.sh --dry-run --with-kb-selftests # 只打印计划：不复制、不执行、不删除
#   bash spikes/run_env_layer_checks.sh --cleanup             # 删除派生副本
#   COPY=/some/path bash spikes/run_env_layer_checks.sh
#   bash spikes/run_env_layer_checks.sh tests/test_archive_e2.py -q   # 追加 pytest 参数
#
# 约束：
#   1. **只读源**：脚本只从 ENV_ROOT 复制，绝不写原目录；跑完用 `find -newer` 断言零写入（两类检查都覆盖）。
#   2. 副本默认落在 <repo>/.env-copy（2.6 GB，仓库本地 .git/info/exclude 忽略）。
#   3. 副本与软件层影子根分开：环境层用例需要"数据根位于 ENV_ROOT 之内"的布局
#      （`test_projection_and_frozen` 的 `relative_to(ENV_ROOT)`），影子根不满足。
#   4. kb 自测必须带 `-B` + `PYTHONDONTWRITEBYTECODE=1`：`kb/tools/**` 是冻结目录，不许写 `__pycache__`
#      （红线 11 / STATUS 登记的第 5 条）。**打印的计划与真执行的命令是同一个数组**，不会各写一遍。
#   5. 失败显式：kb 自测要求 `rc=0` + 有汇总行 + `FAIL=0` + **通过条数等于验收数字**（`KB_EXPECT_PASS`），
#      任一不满足 ⇒ 整条命令非 0；`PASS=0 FAIL=0` 这类退化也会红。不许把跳过当通过。
#   6. `--dry-run` 是**零副作用**模式：只打印计划，不复制、不执行、**不删除**（`--cleanup` 与它同时给时只打印）。
set -uo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$REPO/loop/.venv/bin/python"
COPY="${COPY:-$REPO/.env-copy}"
CLEANUP=0
REUSE=0
DRY_RUN=0
WITH_KB=0
PASSTHRU=()
#: kb 自测清单（唯一来源：本数组；顺序即执行顺序）。
KB_SELFTESTS=(
  "_selftest_gate_schema.py"
  "_selftest_n5_reachability.py"
  "_selftest_adjudicate_conflicts.py"
)
#: 验收数字（K1 判据，落账于 doc/STATUS.md §94）：与上面清单**逐项对应**。
#: 自测新增/删除断言时，两处必须同时改，否则本入口会红 —— 这是有意的（防止数字悄悄漂走）。
KB_EXPECT_PASS=(10 9 28)
#: 环境层用例清单（唯一来源：本数组）。
ENV_LAYER_FILES=(tests/test_archive_e2.py tests/test_projection_and_frozen.py)
#: 两类检查共用的环境变量（真执行与 dry-run 打印同源）。
RUN_ENV=(LOOP_LLM_MODE="${LOOP_LLM_MODE:-standin}")
#: 数据根指向副本内 kb（env_layer 要求"数据根位于 ENV_ROOT 之内"的布局）；打印与执行同源。
KB_ENV=(LOOP_ENV_ROOT="$COPY" LOOP_WORKSPACE="$COPY/kb" PYTHONDONTWRITEBYTECODE=1)

usage() {
  # 只打印头部注释（不带 `#` 前缀）；遇到第一行非注释即停，改注释长度不会把实现代码带出来。
  awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"
}

for arg in "$@"; do
  case "$arg" in
    --cleanup) CLEANUP=1 ;;
    --reuse) REUSE=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --with-kb-selftests) WITH_KB=1 ;;
    -h|--help) usage; exit 0 ;;
    *) PASSTHRU+=("$arg") ;;
  esac
done

if [ "$CLEANUP" = "1" ]; then
  if [ "$DRY_RUN" = "1" ]; then
    # 零副作用优先：绝不因为 `--cleanup` 就真的删（2026-10-27 独立复核 A 项）。
    if [ -d "$COPY" ]; then
      echo "[dry-run] 将删除派生 ENV_ROOT：$COPY（未删除：--dry-run 零副作用）"
    else
      echo "[dry-run] 派生 ENV_ROOT 不存在，无需删除：$COPY"
    fi
    exit 0
  fi
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

if [ "$DRY_RUN" = "1" ]; then
  echo "[dry-run] 不复制派生 ENV_ROOT、不执行任何检查、不删除任何东西；只打印计划。"
  echo "[dry-run] ENV_ROOT = $ENV_ROOT（源，只读）"
  if [ -d "$COPY" ]; then
    echo "[dry-run] 派生副本 = $COPY（已存在：--reuse 时跳过 2.6 GB 复制，否则重建）"
  else
    echo "[dry-run] 派生副本 = $COPY（不存在：将复制约 2.6 GB 后使用）"
  fi
  if [ "$WITH_KB" = "1" ]; then
    echo "[dry-run] kb 自测 ${#KB_SELFTESTS[@]} 项（与 env_layer 共用同一个派生副本；验收数字 PASS=${KB_EXPECT_PASS[*]}）："
    for i in "${!KB_SELFTESTS[@]}"; do
      echo "[dry-run]   env LOOP_ENV_ROOT=$COPY LOOP_WORKSPACE=$COPY/kb PYTHONDONTWRITEBYTECODE=1 $PY -B kb/tools/${KB_SELFTESTS[$i]}（要求 PASS=${KB_EXPECT_PASS[$i]} FAIL=0）"
    done
  else
    echo "[dry-run] kb 自测：未启用（加 --with-kb-selftests 才跑 ${#KB_SELFTESTS[@]} 项）"
  fi
  echo "[dry-run] 环境层用例 3 条（2 个文件）：env ${RUN_ENV[*]} ${KB_ENV[*]} $PY -m pytest -q -m env_layer ${ENV_LAYER_FILES[*]}"
  echo "[dry-run] 零写入见证：跑前建 marker，跑后对原 ENV_ROOT 取 find -newer（命中即 exit 3）"
  exit 0
fi

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

# 零写入见证：marker 在**跑任何检查之前**创建，跑完检查原 ENV_ROOT 是否有比它新的文件。
MARKER="$(mktemp "${TMPDIR:-/tmp}/env-layer-marker-XXXXXX")"
trap 'rm -f "$MARKER"' EXIT

cd "$REPO"

KB_RC=0
KB_STATUS=()
if [ "$WITH_KB" = "1" ]; then
  echo "[info] kb 自测：${#KB_SELFTESTS[@]} 项（与 env_layer 共用派生副本，原环境零写入；验收数字 PASS=${KB_EXPECT_PASS[*]}）" >&2
  for i in "${!KB_SELFTESTS[@]}"; do
    name="${KB_SELFTESTS[$i]}"
    want="${KB_EXPECT_PASS[$i]}"
    OUT="$(env "${KB_ENV[@]}" "$PY" -B "kb/tools/$name" 2>&1)"
    RC=$?
    SUMMARY="$(printf '%s\n' "$OUT" | grep -o 'PASS=[0-9]* FAIL=[0-9]*' | tail -1)"
    GOT="$(printf '%s' "$SUMMARY" | sed -n 's/^PASS=\([0-9]\{1,\}\).*/\1/p')"
    FAILS="$(printf '%s' "$SUMMARY" | sed -n 's/.*FAIL=\([0-9]\{1,\}\)$/\1/p')"
    if [ "$RC" -eq 0 ] && [ -n "$SUMMARY" ] && [ "${FAILS:-1}" = "0" ] && [ "${GOT:-}" = "$want" ]; then
      echo "[kb] $name: $SUMMARY（验收数字 PASS=$want 相符）" >&2
      KB_STATUS+=("$name: $SUMMARY")
    else
      echo "[FAIL] $name: rc=$RC 汇总行=${SUMMARY:-<无>}；验收数字要求 PASS=$want FAIL=0" >&2
      printf '%s\n' "$OUT" | tail -25 >&2
      KB_STATUS+=("$name: FAIL(rc=$RC${SUMMARY:+; $SUMMARY})")
      KB_RC=1
    fi
  done
fi

echo "[info] 环境层用例：3 条（2 个文件：test_archive_e2 ×2、test_projection_and_frozen ×1）" >&2
echo "[info] 数据根 = 副本内的 kb（满足『数据根位于 ENV_ROOT 之内』的布局要求）" >&2
cd "$REPO/loop"
env "${RUN_ENV[@]}" "${KB_ENV[@]}" \
  "$PY" -m pytest -q -m env_layer "${ENV_LAYER_FILES[@]}" "${PASSTHRU[@]}"
RC=$?

# 红线 11 见证：原 ENV_ROOT 必须零写入。
TOUCHED="$(find "$ENV_ROOT" -newer "$MARKER" 2>/dev/null | head -20)"
if [ -n "$TOUCHED" ]; then
  echo "[FAIL] 原 ENV_ROOT 出现新写入（红线 11）：" >&2
  printf '%s\n' "$TOUCHED" >&2
  exit 3
fi
echo "[info] 原 ENV_ROOT 零写入（find -newer 命中 0）" >&2

if [ "$WITH_KB" = "1" ]; then
  echo "[summary] kb 自测 ${#KB_SELFTESTS[@]} 项：$(printf '%s ; ' "${KB_STATUS[@]:-<无>}")env_layer rc=$RC；原 ENV_ROOT 零写入" >&2
fi
[ "$KB_RC" -eq 0 ] || exit "$KB_RC"
exit "$RC"
