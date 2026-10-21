#!/usr/bin/env bash
# F03-b 软件层检查入口：用**可写影子数据根**跑单测，不写共享 state、不写 ENV_ROOT。
#
# 为什么需要它：`WORKSPACE_ROOT` 默认 = `<ENV_ROOT>/kb`，内网/只读挂载下 `kb/runs` 不可写，
# 实测 46 项用例在 `mkdir` 处报 `OSError: [Errno 30] Read-only file system`
# （见 doc/STATUS.md §14–§16）。本脚本把数据根换成一次性影子目录：
#   - `runs/`        ：本脚本自己建（可写）
#   - `baselines/`   ：符号链接到真实基线（只读复制意义不大，用例只读）
#   - `index/`、`conflicts/`：从真实数据根浅拷贝（小，且部分用例会写）
# 软件 state（jobs/recovery/events/槽锁）由 conftest 注入一次性目录（$LOOP_STATE_ROOT）。
#
# 用法：
#   bash spikes/run_software_checks.sh                 # 全套
#   bash spikes/run_software_checks.sh tests/test_flow.py -q
#   KEEP_SHADOW=1 bash spikes/run_software_checks.sh   # 保留影子目录便于排查
#
# **它证明什么**：软件层用例在可写数据根 + 隔离 state 下可执行。
# **它不证明什么**：需要可写 ENV_ROOT 的环境侧用例（归档/守卫脚本）仍属环境层，
# 失败必须在输出与 STATUS 中单独登记，不能当作通过。
set -euo pipefail

LOOP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$LOOP_DIR"

PY=".venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "[FAIL] 找不到 $LOOP_DIR/.venv/bin/python（先按 README 建 venv）" >&2
  exit 2
fi

REAL_ROOT="$("$PY" - <<'PY'
from host import paths as P
print(P.WORKSPACE_ROOT)
PY
)"
if [[ ! -d "$REAL_ROOT" ]]; then
  echo "[FAIL] 数据根不存在：$REAL_ROOT" >&2
  exit 2
fi

SHADOW="$(mktemp -d "${TMPDIR:-/tmp}/loop-software-XXXXXX")"
cleanup() {
  if [[ "${KEEP_SHADOW:-0}" == "1" ]]; then
    echo "[info] 影子数据根保留在：$SHADOW"
  else
    rm -rf "$SHADOW"
  fi
}
trap cleanup EXIT

mkdir -p "$SHADOW/runs"
for part in index conflicts adjudication; do
  if [[ -d "$REAL_ROOT/$part" ]]; then
    cp -a "$REAL_ROOT/$part" "$SHADOW/$part"
  fi
done
if [[ -d "$REAL_ROOT/baselines" ]]; then
  ln -s "$REAL_ROOT/baselines" "$SHADOW/baselines"
fi
# drill 夹具轮（733 MB，只读）：符号链接，不复制。N0/N1/N2 与若干冻结见证用例都读它。
FIXTURE_RUN="RUN-20261015-120626"
if [[ -d "$REAL_ROOT/runs/$FIXTURE_RUN" ]]; then
  ln -s "$REAL_ROOT/runs/$FIXTURE_RUN" "$SHADOW/runs/$FIXTURE_RUN"
else
  echo "[warn] 缺 drill 夹具轮 $FIXTURE_RUN；依赖它的用例会失败（不是软件层缺陷）" >&2
fi

echo "[info] 软件层数据根：$SHADOW（baselines → 真实只读基线）" >&2
echo "[info] 共享 state 由 conftest 注入一次性目录（\$LOOP_STATE_ROOT）" >&2

# 测试分层（F03-b）：默认排除需要可写 ENV_ROOT / 冻结见证的 env_layer 用例。
# 它们不是 skip：默认根 pytest 仍如实执行并失败；这里只是把「软件层」与「环境层」分开。
MARK_ARGS=(-m "not env_layer")
if [[ "${INCLUDE_ENV_LAYER:-0}" == "1" ]]; then
  MARK_ARGS=()
  echo "[info] 包含环境层用例（需要可写 ENV_ROOT / 内网冻结见证）" >&2
else
  echo "[info] 默认排除环境层用例（-m \"not env_layer\"）；INCLUDE_ENV_LAYER=1 可包含" >&2
fi

LOOP_WORKSPACE="$SHADOW" \
LOOP_LLM_MODE="${LOOP_LLM_MODE:-standin}" \
  "$PY" -m pytest -q "${MARK_ARGS[@]}" "$@"
