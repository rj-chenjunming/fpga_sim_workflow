#!/usr/bin/env bash
# 3C+4+3B 收口门（顺序执行；浏览器单租户）
set -u
R=/home/work/chenjunming/change-impact-loop
cd "$R" || exit 9
OUT=$R/doc/evidence/UI_CSS_MERGE_20261030/raw
E3B=$R/doc/evidence/UI_COLOR_TOKENS_20261030/raw
mkdir -p "$OUT" "$E3B"
export PLAYWRIGHT_BROWSERS_PATH=$R/.pw-browsers HOME=$R/.chrome-home TMPDIR=$R/.chrome-tmp

echo "===== [1/4] measure.py 运行时读数 $(date +%H:%M:%S) ====="
loop/.venv/bin/python .ui-audit/measure.py > "$E3B/measure-final.stdout.txt" 2>&1
echo "exit=$? -> $E3B/measure-final.stdout.txt"
cp .ui-audit/measure.json "$E3B/measure-final.json"

echo "===== [2/4] 浏览器全量 $(date +%H:%M:%S) ====="
( cd loop && .venv/bin/python -m pytest -q tests/browser > "$OUT/browser-gate.txt" 2>&1; echo "exit=$?" >> "$OUT/browser-gate.txt" )
tail -3 "$OUT/browser-gate.txt"

echo "===== [3/4] 软件层门 $(date +%H:%M:%S) ====="
( cd loop && bash spikes/run_software_checks.sh --ignore=tests/browser -q > "$OUT/software-gate.txt" 2>&1; echo "exit=$?" >> "$OUT/software-gate.txt" )
tail -3 "$OUT/software-gate.txt"

echo "===== [4/4] 文档门 $(date +%H:%M:%S) ====="
python3 doc/audit/check_doc_links.py > "$OUT/doc-gate.txt" 2>&1
echo "exit=$?" >> "$OUT/doc-gate.txt"
tail -2 "$OUT/doc-gate.txt"
echo "ALL GATES DONE $(date +%H:%M:%S)"
