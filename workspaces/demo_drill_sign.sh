#!/usr/bin/env bash
# S0/drill 演示：按阶段等你按 Enter，再由你（human:chenjunming）签名。
# 每个 Enter 都对应一次人工闸门决策；脚本不替代你的判断，只替你发 POST。
set -u
RUN="${1:-RUN-20261022-195952}"
ACTOR="${2:-human:chenjunming}"
BASE=http://127.0.0.1:8099
PY=loop/.venv/bin/python

post() { # gate decision reason
  "$PY" - "$RUN" "$ACTOR" "$1" "$2" "$3" <<'PY'
import json, sys, urllib.request, urllib.error
run, actor, gate, decision, reason = sys.argv[1:6]
body = {"decision": decision, "actor": actor, "reason": reason}
req = urllib.request.Request(
    f"http://127.0.0.1:8099/api/runs/{run}/gates/{gate}/decision",
    data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
try:
    r = json.load(urllib.request.urlopen(req))
    gs = (r.get("gate_state") or {})
    print("  -> OK", gate, gs.get("decision"), "human_signed=", gs.get("human_signed"), "actor=", gs.get("actor"))
except urllib.error.HTTPError as e:
    print("  -> HTTP", e.code, e.read().decode()[:400])
PY
}

wait_gate() {
  for _ in $(seq 1 120); do
    line=$(curl -s --max-time 5 "$BASE/api/runs/$RUN" | "$PY" -c "
import json,sys
v=json.load(sys.stdin); p=(v.get('pending_interrupt') or {}).get('payload') or {}
print(v['status'], p.get('gate') or '-', v.get('error') or '')" 2>/dev/null)
    set -- $line
    st=$1; gate=$2
    if [ "$st" = "failed" ]; then echo "!! run failed: $3"; exit 1; fi
    if [ "$st" = "finished" ]; then echo "== run finished"; return 2; fi
    if [ "$st" = "waiting_gate" ] && [ "$gate" = "$1" ]; then return 0; fi
    sleep 1
  done
  echo "!! 等闸门超时"; exit 1
}

step() { # gate decision reason
  local gate=$1 decision=$2 reason=$3
  for _ in $(seq 1 120); do
    cur=$(curl -s --max-time 5 "$BASE/api/runs/$RUN" | "$PY" -c "
import json,sys
v=json.load(sys.stdin); p=(v.get('pending_interrupt') or {}).get('payload') or {}
print(v['status'], p.get('gate') or '-')" 2>/dev/null)
    st=${cur%% *}; g=${cur##* }
    if [ "$st" = "failed" ]; then echo "!! run failed"; exit 1; fi
    if [ "$st" = "finished" ]; then echo "== run finished"; exit 0; fi
    if [ "$st" = "waiting_gate" ] && [ "$g" = "$gate" ]; then break; fi
    sleep 1
  done
  echo
  echo "== $gate 待签：$decision"
  curl -s --max-time 5 "$BASE/api/runs/$RUN" | "$PY" -c "
import json,sys
v=json.load(sys.stdin); p=v['pending_interrupt']['payload']
print('   材料：差异', (p.get('difference_items') or {}).get('count'),'条 / 未决',(p.get('difference_items') or {}).get('unresolved_count'))
print('   阻断：', [b.get('code') for b in (p.get('blockers') or [])][:6])
print('   选项：', [o.get('value') for o in (p.get('decision_options') or [])])"
  read -r -p "   按 Enter 以 $ACTOR 签名（Ctrl+C 放弃）…" _
  post "$gate" "$decision" "$reason"
}

step G1_diff_confirm confirmed "演练：已逐条核对 N2 差异与 Host 留痕，同意进入修订"
step G2_report_accept accept "演练：已读报告，接受报告本身（不表示判绿）"
step G3_regression_decision milestone_only "演练：冲突未清零，选仅里程碑回归"

for _ in $(seq 1 120); do
  line=$(curl -s --max-time 5 "$BASE/api/runs/$RUN" | "$PY" -c "
import json,sys;v=json.load(sys.stdin);print(v['status'], v.get('error') or '')" 2>/dev/null)
  st=${line%% *}
  if [ "$st" = "finished" ]; then echo "== 结束：$line"; break; fi
  if [ "$st" = "failed" ]; then echo "!! 失败：$line"; break; fi
  sleep 1
done
echo "== 账本：workspaces/simenv-tcs9620-64ch-sandbox/runs/$RUN/gates.json"
