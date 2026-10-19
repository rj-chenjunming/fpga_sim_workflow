#!/usr/bin/env bash
# 服务器侧启动器：起「变更影响闭环」Web 界面（只绑 127.0.0.1），并打印 Windows 侧隧道命令。
#
# 为什么只绑 127.0.0.1：本界面**没有鉴权**（单机单用户），绝不能直接暴露到网络上；
# 远程访问一律走 SSH 本地端口转发（与 DeepSeekHarnessLauncher 对 DSH Web 的做法一致）。
#
# 用法：
#   bash loop/remote/serve.sh                # 用 environments.json 的默认数据根
#   bash loop/remote/serve.sh --sandbox      # 用 workspaces/<env>-sandbox 的可写副本（演示/受限环境）
#   LOOP_PORT=9000 bash loop/remote/serve.sh # 换端口
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
LOOP_DIR="$(cd "$HERE/.." && pwd)"
REPO_ROOT="$(cd "$LOOP_DIR/.." && pwd)"
cd "$LOOP_DIR"

PORT="${LOOP_PORT:-8099}"
MODE="${1:-}"

if [ "$MODE" = "--sandbox" ]; then
  WS="$REPO_ROOT/workspaces/simenv-tcs9620-64ch-sandbox"
  if [ ! -d "$WS/index" ]; then
    echo "缺少沙箱工作区：$WS" >&2
    echo "先运行：bash loop/remote/seed-sandbox-workspace.sh" >&2
    exit 2
  fi
  export LOOP_WORKSPACE="$WS"
  echo "[mode] sandbox（可写副本，权威数据仍在 ENV_ROOT/kb）"
else
  echo "[mode] default（按 environments.json）"
fi

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
USER_NAME="$(id -un)"

cat <<EOF

────────────────────────────────────────────────────────────
 服务端已准备启动
   监听      : http://127.0.0.1:${PORT}/
   工作区    : ${LOOP_WORKSPACE:-<由 environments.json 解析>}
   环境根    : ${LOOP_ENV_ROOT:-<由 environments.json 解析>}

 Windows 侧（任选其一）：
   1) cmd / PowerShell 直接开隧道：
        ssh -N -L ${PORT}:127.0.0.1:${PORT} ${USER_NAME}@${LAN_IP}
      然后浏览器打开 http://127.0.0.1:${PORT}/

   2) 用仓库内脚本（自动开隧道 + 打开浏览器）：
        loop\\remote\\connect-loop.bat
        powershell -ExecutionPolicy Bypass -File loop\\remote\\connect-loop.ps1

   3) PuTTY：Connection > SSH > Tunnels
        Source port = ${PORT}
        Destination   = 127.0.0.1:${PORT}
        (选 Local，再 Open 到 ${LAN_IP})

 安全：本服务无鉴权，**不要**把它绑到 0.0.0.0，也不要把 ${PORT} 暴露到网络。
 停止：Ctrl+C；后台运行时 `pkill -f "uvicorn services.api:app"`。
────────────────────────────────────────────────────────────

EOF

# 前台运行（关闭即停）。后台常驻可自行加 nohup/setsid。
exec env LOOP_PORT="$PORT" ./run.sh
