#!/usr/bin/env bash
# v1 验收驱动器：在**一次 bash 调用内**跑完 phase 1 → 重启 → 2/3 → 重启 → 4 → 重启 → 4b/5。
#
# 为什么必须在一个调用里（实测踩过）：
#   本工程的 bash 调用各自跑在 bwrap 沙箱里（--unshare-pid --die-with-parent）——
#   换一个调用既看不见也杀不掉上一个调用留下的 uvicorn（曾因此把 phase 1 打到旧代码的服务上，
#   端口被占还静默继续）；而用 DSH 的 job_kill 会连沙箱把长任务的子进程一起收掉，
#   于是"运行中的长任务跨重启仍然活着"这条根本测不出来。
#   所以这里自己起停服务，并且只 kill uvicorn 那一个 PID：长任务子进程是
#   start_new_session=true 起的独立会话，必须活下来。
#
# 重启必须等端口真的不再响应再起下一代：只等 pid 消失不够（实测：上一代没退，
# 下一代的就绪探测打到了它，phase 4b 对着旧进程跑，结论全错）。
#
# 用法：bash spikes/accept_v1_run.sh
set -uo pipefail
cd "$(dirname "$0")/.."

LOG=.logs/accept
PORT="${LOOP_PORT:-8099}"
BASE="http://127.0.0.1:${PORT}"
export LOOP_LLM_MODE=standin
export LOOP_PORT="$PORT"

RC=()
SRV=""
mkdir -p "$LOG"
: > "$LOG/server.out"
: > "$LOG/driver.log"

clean_state () {
  rm -rf state spikes/.accept_v1_state.json
  for d in ../kb/runs/RUN-*; do
    [ -f "$d/.loop_drill" ] && rm -rf "$d"
  done
  return 0
}

alive () { curl -s --max-time 1 "$BASE/api/health" >/dev/null 2>&1; }

start_server () {
  if alive; then
    echo "[driver] [FAIL] 起第 $1 代之前 $BASE 已有服务在响应（重启不成立）" | tee -a "$LOG/driver.log"
    return 1
  fi
  ./run.sh >>"$LOG/server.out" 2>&1 &
  SRV=$!
  for _ in $(seq 1 80); do
    if alive; then
      echo "[driver] 服务已起 pid=$SRV（第 $1 代）" | tee -a "$LOG/driver.log"
      return 0
    fi
    sleep 0.5
  done
  echo "[driver] [FAIL] 服务未能在 40s 内起来（第 $1 代）" | tee -a "$LOG/driver.log"
  return 1
}

stop_server_keep_jobs () {
  [ -n "$SRV" ] && kill -TERM "$SRV" 2>/dev/null
  for _ in $(seq 1 40); do
    kill -0 "$SRV" 2>/dev/null || break
    sleep 0.25
  done
  kill -0 "$SRV" 2>/dev/null && kill -KILL "$SRV" 2>/dev/null
  for _ in $(seq 1 80); do
    alive || break
    sleep 0.25
  done
  if alive; then
    echo "[driver] [FAIL] $BASE 仍有服务在响应，重启不成立" | tee -a "$LOG/driver.log"
  fi
  echo "[driver] 已停 uvicorn pid=$SRV（未触碰长任务）" | tee -a "$LOG/driver.log"
}

phase () {
  echo "" | tee -a "$LOG/driver.log"
  echo "########## phase $1 ##########" | tee -a "$LOG/driver.log"
  .venv/bin/python spikes/accept_v1.py --base "$BASE" --phase "$1" 2>&1 | tee "$LOG/phase$1.txt"
  RC+=("$1=${PIPESTATUS[0]}")
  return 0
}

echo "== 清理运行时状态 ==" | tee -a "$LOG/driver.log"
clean_state

echo "== 第 1 代：phase 1 ==" | tee -a "$LOG/driver.log"
start_server 1 || exit 2
phase 1
stop_server_keep_jobs

echo "== 第 2 代：phase 2 / 3（真重启后重附着 + 收敛） ==" | tee -a "$LOG/driver.log"
start_server 2 || exit 2
phase 2
phase 3
stop_server_keep_jobs

echo "== 第 3 代：phase 4（起长任务并停放；不取消） ==" | tee -a "$LOG/driver.log"
start_server 3 || exit 2
phase 4
stop_server_keep_jobs

echo "== 第 4 代：phase 4b（重附着到仍在跑的长任务 + 取消）/ 5（死任务） ==" | tee -a "$LOG/driver.log"
start_server 4 || exit 2
phase 4b
phase 5
stop_server_keep_jobs

echo "" | tee -a "$LOG/driver.log"
echo "================= 驱动汇总 =================" | tee -a "$LOG/driver.log"
FAILED=0
for kv in "${RC[@]}"; do
  name="${kv%%=*}"; rc="${kv##*=}"
  [ "$rc" != "0" ] && FAILED=1
  printf '  phase %-4s rc=%s\n' "$name" "$rc" | tee -a "$LOG/driver.log"
done
echo "  => $([ $FAILED = 0 ] && echo 'ALL PASS' || echo 'HAS FAILURE')" | tee -a "$LOG/driver.log"
exit $FAILED
