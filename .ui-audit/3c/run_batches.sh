#!/usr/bin/env bash
# 3C 分批合并（staging 隔离）：每批 ≤15 个选择器 → 指纹（主视口 8 状态）→ diff=0 才继续。
# 所有改动只落在 `.ui-audit/3c/web-stage/app.css`（= pristine web 副本 + 合并后的 app.css），
# 因此与批次 4 正在改的 index.html/app.js 互不干扰；收口后由 Lead 把 app.css 拷回 loop/web。
# 任何一批指纹非空/报错立刻停止（该批已落盘，可用 snap-batchNN 覆盖回滚），不自动掩盖。
set -u
R=/home/work/chenjunming/change-impact-loop
STAGE=$R/.ui-audit/3c/web-stage
export MERGE_CSS=$STAGE/app.css
cd "$R" || exit 9
PY=loop/.venv/bin/python
EVID=$R/.ui-audit/3c/cooccur-full.json
LOG=$R/.ui-audit/3c/batches.log
: > "$LOG"

fingerprint() {
  (cd "$R/loop" && PLAYWRIGHT_BROWSERS_PATH=$R/.pw-browsers HOME=$R/.chrome-home \
     TMPDIR=$R/.chrome-tmp .venv/bin/python "$R/.ui-audit/verify_style_equivalence.py" \
     --before-web "$R/.ui-audit/3c/snap-before" --after-web "$STAGE" --no-sweep 2>&1 | tail -2)
}

for i in $(seq 1 24); do
  n=$(printf "%02d" "$i")
  snap="$R/.ui-audit/3c/snap-batch$n"
  mkdir -p "$snap"
  cp "$STAGE/app.css" "$snap/app.css"
  echo "===== batch $i  start $(date +%H:%M:%S) =====" | tee -a "$LOG"
  out=$($PY .ui-audit/3c/merge_plan.py merge --max 15 --batch "$i" --evidence "$EVID" 2>&1)
  merged=$(echo "$out" | grep -o "本批合并 [0-9]* 个选择器" | grep -o "[0-9]*")
  echo "$out" | tail -2 | tee -a "$LOG"
  if [ "${merged:-0}" = "0" ]; then
    echo "batch $i: 没有可合并组，收工" | tee -a "$LOG"
    break
  fi
  fp=$(fingerprint) || fp="FINGERPRINT-ERROR"
  # 指纹报错（浏览器抖动/超时）重试一次，仍失败则停止并保留现场
  if ! echo "$fp" | grep -qE "^(PASS|DIFF)"; then
    echo "--- 指纹首次未返回判定，重试一次 ---" | tee -a "$LOG"
    sleep 5
    fp=$(fingerprint) || fp="FINGERPRINT-ERROR"
  fi
  echo "$fp" | tee -a "$LOG"
  if echo "$fp" | grep -q "^PASS"; then
    continue
  fi
  echo "!!! batch $i 指纹非空或报错：停止，保留现场（回滚用 cp $snap/app.css $STAGE/app.css）" | tee -a "$LOG"
  exit 1
done
echo "ALL BATCHES DONE $(date +%H:%M:%S)" | tee -a "$LOG"
