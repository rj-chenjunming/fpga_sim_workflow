#!/usr/bin/env bash
# 把 ENV_ROOT/kb 的数据**复制**（不是移动）到 workspaces/<env>-sandbox/，供受限环境/演示使用。
#
# 背景：本会话的 DSH 文件沙箱把 ENV_ROOT 挂为只读；而闭环的闸门/运行记录要写 WORKSPACE_ROOT。
# 为了让「Windows → 隧道 → 界面」这条链路可以真交互，这里复制一份可写数据；权威原件不动。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
cd "$REPO_ROOT"

ENV_ROOT="$("$REPO_ROOT/loop/.venv/bin/python" - <<'PY'
import json, pathlib
reg = json.loads(pathlib.Path("environments.json").read_text(encoding="utf-8"))
print(reg["environments"][reg["default"]]["path"])
PY
)"

SRC="$ENV_ROOT/kb"
DEST="$REPO_ROOT/workspaces/simenv-tcs9620-64ch-sandbox"

if [ ! -d "$SRC" ]; then
  echo "源数据根不存在：$SRC" >&2
  exit 2
fi

mkdir -p "$DEST"
echo "复制（不是移动）：$SRC/ → $DEST/"
rsync -a "$SRC/" "$DEST/"
echo "完成。权威数据仍在：$SRC（未改动）"
echo "启动：bash loop/remote/serve.sh --sandbox"
