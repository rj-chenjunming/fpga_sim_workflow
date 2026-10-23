#!/usr/bin/env bash
# drill 全流程演示的人工闸门签名助手（仅本地演练；可从中断处恢复）。
#
# 用法：
#   bash loop/spikes/demo_drill_sign.sh <RUN_ID> <human:你的名字>
#
# 行为：
#   · 只处理三道具名闸门的**待签**状态；已签的门自动跳过（所以服务重启后可直接重跑续上）；
#   · 每道门先打印材料摘要（差异条数/阻断/可选决策），**等你按 Enter 才**以你给的 actor 签名；
#   · 签名后同步等待执行推进到下一道门（drill 几秒；期间无输出是正常的）；
#   · 不内置任何人的名字，不替你做判断（I6：人工闸门必须由人签）。
set -u
RUN="${1:-}"
ACTOR="${2:-}"
BASE="${LOOP_DEMO_BASE:-http://127.0.0.1:8099}"
export LOOP_DEMO_BASE="$BASE"
PY=loop/.venv/bin/python
if [ -z "$RUN" ] || [ -z "$ACTOR" ]; then
  echo "用法：bash loop/spikes/demo_drill_sign.sh <RUN_ID> <human:你的名字>" >&2
  exit 2
fi
case "$ACTOR" in
  human:?*) ;;
  *) echo "actor 必须以 'human:' 开头（I6）" >&2; exit 2 ;;
esac

declare -A DECISION=(
  [G1_diff_confirm]=confirmed
  [G2_report_accept]=accept
  [G3_regression_decision]=milestone_only
)
declare -A REASON=(
  [G1_diff_confirm]="演练：已逐条核对 N2 差异与 Host 留痕，同意进入修订"
  [G2_report_accept]="演练：已读报告，接受报告本身（不表示判绿）"
  [G3_regression_decision]="演练：冲突未清零，选仅里程碑回归"
)

post() { # gate
  "$PY" - "$RUN" "$ACTOR" "$1" "${DECISION[$1]}" "${REASON[$1]}" <<'PY'
import json, os, sys, urllib.request, urllib.error
run, actor, gate, decision, reason = sys.argv[1:6]
base = os.environ.get("LOOP_DEMO_BASE", "http://127.0.0.1:8099")
body = {"decision": decision, "actor": actor, "reason": reason}
req = urllib.request.Request(f"{base}/api/runs/{run}/gates/{gate}/decision",
    data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST")
try:
    r = json.load(urllib.request.urlopen(req))
    gs = (r.get("gate_state") or {})
    print("  -> OK", gate, gs.get("decision"), "human_signed=", gs.get("human_signed"), "actor=", gs.get("actor"))
except urllib.error.HTTPError as e:
    print("  -> HTTP", e.code, e.read().decode()[:400])
PY
}

query() { # -> "status gate"
  curl -s --max-time 8 "$BASE/api/runs/$RUN" | "$PY" -c "
import json,sys
v=json.load(sys.stdin)
p=(v.get('pending_interrupt') or {}).get('payload') or {}
print(v['status'], p.get('gate') or '-')" 2>/dev/null
}

material() {
  curl -s --max-time 8 "$BASE/api/runs/$RUN" | "$PY" -c "
import json,sys
v=json.load(sys.stdin); p=v['pending_interrupt']['payload']
d=p.get('difference_items') or {}
print('   材料：差异', d.get('count'), '条 / 未决', d.get('unresolved_count'))
print('   阻断：', [b.get('code') for b in (p.get('blockers') or [])][:6])
print('   选项：', [o.get('value') for o in (p.get('decision_options') or [])])"
}

echo "== run $RUN @ $BASE"
for _ in $(seq 1 600); do
  line=$(query); st=${line%% *}; gate=${line##* }
  case "$st" in
    failed) echo "!! run failed"; break ;;
    finished) echo "== run finished"; break ;;
  esac
  if [ "$st" = "waiting_gate" ] && [ -n "${DECISION[$gate]:-}" ]; then
    echo
    echo "== $gate 待签：${DECISION[$gate]}"
    material
    read -r -p "   按 Enter 以 $ACTOR 签名（Ctrl+C 放弃）…" _
    post "$gate"
    continue
  fi
  sleep 2
done

echo
echo "== 账本：<WORKSPACE>/runs/$RUN/gates.json"
