#!/usr/bin/env bash
# 3B 重跑入口：把当前 loop/web/{app,legacy,tokens}.css 与 legacy.html 钉成快照，
# 再重算清单/映射/自检。3C 合并改动 app.css 后必须重跑（行号会变，字面量→令牌不变）。
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p .ui-audit/3b/snap
cp loop/web/app.css loop/web/legacy.css loop/web/tokens.css loop/web/legacy.html .ui-audit/3b/snap/
md5sum .ui-audit/3b/snap/app.css .ui-audit/3b/snap/legacy.css .ui-audit/3b/snap/tokens.css \
  > .ui-audit/3b/snap/MD5SUMS.txt
export UI3B_SNAP=1
python3 .ui-audit/3b/scan_colors.py
python3 .ui-audit/3b/build_mapping.py
python3 .ui-audit/3b/emit.py
python3 .ui-audit/3b/selfcheck.py | tee .ui-audit/3b/selfcheck.out
