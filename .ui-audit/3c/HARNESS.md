# 3C 证据工具 HARNESS（只读）

两个工具都在 `<repo>/.ui-audit/3c/`：只读 `loop/web/**`，只写 `.ui-audit/3c/`；数据一律来自
`collect_f14a.MockApi` 受控替身（**不是真实 run**）。环境：`PLAYWRIGHT_BROWSERS_PATH=$R/.pw-browsers`、
`HOME=$R/.chrome-home`、`TMPDIR=$R/.chrome-tmp`、`loop/.venv/bin/python`（`$R`=仓库根）。

## 1 `verify_style_equivalence.py`（交付 1）
判据（任一不过即 `DIFF`，exit 1）：①逐元素计算样式双哈希（全部 longhand + `::before`/`::after`，无限动画停 0 时刻）；
②样式表规则序列对账（逐条 `selectorText`+声明数，含 `@media`/`@supports`/`@keyframes`——浏览器静默丢弃非法选择器时靠它抓）；
③交互态可达性（一侧能落到焦点/悬停目标、另一侧不能 ⇒ DIFF）。
覆盖：主视口 1280×720/1440×900/1920×1080（真实高度）× 9 状态
`s0/setup/run/gate/dirpicker/agent/node-detail/empty/legacy`；交互态 10 焦点（`s0`/`gate` ×
`button/a/summary/input/.rail-entry`，键盘 Tab）+ 5 悬停（`.btn/.rail-entry/.run-item/.agent-open/.crumb-seg`）；
断点扫描 50 宽度 ×(`s0`,`run`)(h=1000) + 窄断点 `agent` + 3 主视口 `legacy`。共 196 组合（`--no-sweep` 时 72）。
未覆盖：`focus:gate:summary`（gate 视图没有 `<summary>`，两侧都不可达，JSON 里登记）；`:active`/拖拽/触摸/reduced-motion；
像素级截图目检；真实服务端数据。规则序列只在有差异时序列化（before/after 总条数 + 首个差异项 + 该条两版原文）。
复跑：`cd $R/loop && PLAYWRIGHT_BROWSERS_PATH=$R/.pw-browsers HOME=$R/.chrome-home TMPDIR=$R/.chrome-tmp
.venv/bin/python $R/.ui-audit/3c/verify_style_equivalence.py --before-web <A> --after-web <B> [--no-sweep]`
耗时（本机实测）：72 组合 232 s；196 组合 634 s。

## 2 `cooccur.py`（交付 2）
读 `--selectors`（`{"selectors":[...], "blocked_pairs":[[a,b],...]}`），对每个选择器先 sanitize
（剥 `:hover/:focus/:focus-visible/:focus-within/:active` 与伪元素 `::before/::after/:after/…`；
保留 `:disabled/:checked/:first-child/:empty/:not()/:nth-*` 等静态伪类），再 `querySelectorAll`，
用 `WeakMap` 自增 id + 结构路径给稳定 key，输出 `cooccur.json`：`states`、`selector_counts`、
`co_match`（只输出 count>0；count=同一状态里命中同一元素的次数）、`blocked_pairs` 逐对回填、
`empty_scan_selfcheck`、`zero_hit_selectors`、`selector_sanitized`。附加探针 `button`/`#btnS0`（`probe_selectors`）。
覆盖 36 个状态（9 基础 ×3 视口 + `toast`/`alert`（`#s0Error[role=alert]` 真实错误态）/`gate-empty` ×3）；
`<dialog>` 打开态由 `agent`(`#agentWindow`) 与 `node-detail`(`#nodeDetail`) 覆盖。
未覆盖：29 个 0 命中选择器（JSON 逐条列出）、伪元素之间、非受控的动态列表/超长错误文案。
复跑：`... cooccur.py --web <dir> --selectors ... --out ... [--selfcheck]`；稳定性：`--out A.json --check-stable B.json`。
耗时：38 s / 次。

## 3 为什么这些证据不等于全态证明
- 指纹只证明「**这些受控状态 × 这些视口**下计算样式与规则集合一致」；hover/focus 只测列出的目标，断点只测 50 个邻域。
- `co_match` 是「可能互相影响」的**下界**证据：不共命中≠全态独立（未测状态/断点/态可能命中）；伪元素互斥只能靠静态判据。
- 元素按 DOM 序号比对：DOM 结构变化会表现为大面积差异（噪声），不会静默漏报；但元素改名而样式同值不会被发现。
