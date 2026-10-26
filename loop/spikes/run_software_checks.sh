#!/usr/bin/env bash
# F03-b 软件层检查入口：用**可写影子数据根**跑单测，不写共享 state、不写 ENV_ROOT。
#
# 为什么需要它：`WORKSPACE_ROOT` 默认 = `<ENV_ROOT>/kb`，内网/只读挂载下 `kb/runs` 不可写，
# 实测 46 项用例在 `mkdir` 处报 `OSError: [Errno 30] Read-only file system`
# （见 doc/STATUS.md §14–§16）。本脚本把数据根换成一次性影子目录。
# 影子目录怎么造**不在这里写第二遍**：统一委托 `spikes/provision_dev_workspace.sh
# --link-fixture`（夹具与 baselines 符号链接、index/conflicts/adjudication 浅拷贝），
# 持久副本与一次性影子共用同一份构造口径（2026-10-26 A2）。
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

SPIKES_DIR="$(dirname "${BASH_SOURCE[0]}")"
SHADOW="$(mktemp -d "${TMPDIR:-/tmp}/loop-software-XXXXXX")"
cleanup() {
  if [[ "${KEEP_SHADOW:-0}" == "1" ]]; then
    echo "[info] 影子数据根保留在：$SHADOW"
  else
    chmod -R u+w "$SHADOW" 2>/dev/null
    rm -rf "$SHADOW"
  fi
}
trap cleanup EXIT

# 数据根的构造**只有一份实现**：`spikes/provision_dev_workspace.sh`（2026-10-26 A2）。
# 这里只声明「一次性影子」这一形态：夹具与 baselines 用符号链接（不复制 733 MB），
# 缺夹具时降级为 warn（依赖它的用例会失败，但不是软件层缺陷）。
DEST="$SHADOW" bash "$SPIKES_DIR/provision_dev_workspace.sh" \
  --force --link-fixture --quiet --tolerate-missing-fixture \
  || { echo "[FAIL] 影子数据根构造失败" >&2; exit 2; }

echo "[info] 软件层数据根：$SHADOW（drill 夹具与 baselines → 真实只读源）" >&2
echo "[info] 共享 state 由 conftest 注入一次性目录（\$LOOP_STATE_ROOT）" >&2

# 测试分层（F03-b）：默认排除需要可写 ENV_ROOT / 冻结见证的 env_layer 用例。
# 它们不是 skip：默认根 pytest 仍如实执行并失败；这里只是把「软件层」与「环境层」分开。
MARK_ARGS=(-m "not env_layer")
if [[ "${INCLUDE_ENV_LAYER:-0}" == "1" ]]; then
  MARK_ARGS=()
  echo "[info] 包含环境层用例（需要可写 ENV_ROOT / 内网冻结见证）" >&2
else
  echo "[info] 默认排除环境层用例（-m \"not env_layer\"）；INCLUDE_ENV_LAYER=1 可包含" >&2
  # 打印被排除的用例清单（只收集不执行；规格 §4.1：排除项必须可见）。
  ENV_LAYER_LIST="$("$PY" -m pytest --collect-only -q -m env_layer 2>/dev/null | grep '::' || true)"
  if [[ -n "$ENV_LAYER_LIST" ]]; then
    echo "[info] 被排除的环境层用例（$(printf '%s\n' "$ENV_LAYER_LIST" | wc -l | tr -d ' ') 项）：" >&2
    printf '%s\n' "$ENV_LAYER_LIST" | sed 's/^/  - /' >&2
  fi
  if [[ " $* " == *" -m "* ]]; then
    echo "[warn] 检测到用户 -m 参数：它会覆盖默认的 env_layer 排除（后面的 -m 生效）" >&2
  fi
fi

# 安静模式：脚本自带 `-q` 只为输出紧凑；但调用方也传 `-q` 时会拼成 `-qq`，
# pytest 的 `-qq` 会**吞掉 "N passed" 汇总行**（实测见 STATUS §47.3 第 6 条）。
# 因此只有调用方没给 quiet 参数时才加 `-q`（R3-14）。
QUIET_ARGS=(-q)
for _arg in "$@"; do
  case "$_arg" in
    -q|--quiet|-qq|-qqq) QUIET_ARGS=(); break ;;
  esac
done

LOOP_WORKSPACE="$SHADOW" \
LOOP_LLM_MODE="${LOOP_LLM_MODE:-standin}" \
  "$PY" -m pytest "${QUIET_ARGS[@]}" "${MARK_ARGS[@]}" "$@"
