# 演练证据迁移记录：`doc/agents/_demo/` → `doc/evidence/demo/`

> **迁移日期**：2026-10-19
> **迁移方式**：`git mv`（目录整体迁移；未对证据正文做任何改写）
> **迁移范围**：32 个文件（`accept/`、`evidence/`、`review/`、`guard/`、`TESTLIB_sandbox/`、`README.md`）
> **内容完整性声明**：32/32 文件与**迁移前 HEAD `dc7c69e`** 中的旧路径 blob **逐字节相同**
> （逐文件 md5 比对，0 不一致；迁移当时 `git diff --cached -M --summary` 全部显示
> `rename ... (100%)`）。
> **本文件是新增的迁移说明**，不属于原 32 件证据，也不改变任何证据内容。

---

## 1 目录级映射（old → new）

| 旧路径（迁移前） | 新路径（本仓当前） | 迁移方式 |
|---|---|---|
| `doc/agents/_demo/` | `doc/evidence/demo/` | `git mv`（整目录） |
| `doc/agents/_demo/README.md` | `doc/evidence/demo/README.md` | 同上 |
| `doc/agents/_demo/accept/` | `doc/evidence/demo/accept/` | 同上（含 `accept/evidence/`、`accept/review/`、`accept/guard/`、`accept/TESTLIB_sandbox/`） |
| `doc/agents/_demo/evidence/` | `doc/evidence/demo/evidence/` | 同上 |
| `doc/agents/_demo/review/` | `doc/evidence/demo/review/` | 同上 |
| `doc/agents/_demo/guard/` | `doc/evidence/demo/guard/` | 同上 |
| `doc/agents/_demo/TESTLIB_sandbox/` | `doc/evidence/demo/TESTLIB_sandbox/` | 同上 |

## 2 关键件级映射 + 内容 md5（新旧一致）

| 旧路径 | 新路径 | md5（迁移前后相同） |
|---|---|---|
| `doc/agents/_demo/README.md` | `doc/evidence/demo/README.md` | `af220937b6c035ee323c6e29c8374d69` |
| `doc/agents/_demo/TESTLIB_sandbox/tc_rtc_blk_reset_chk_01.sv` | `doc/evidence/demo/TESTLIB_sandbox/tc_rtc_blk_reset_chk_01.sv` | `21fd7e49a4c9916d76dada84fc276ca7` |
| `doc/agents/_demo/accept/ACCEPTANCE_PLAN.md` | `doc/evidence/demo/accept/ACCEPTANCE_PLAN.md` | `198b8cf343dc5d45e8188add03a1547c` |
| `doc/agents/_demo/accept/TESTLIB_baseline_md5.txt` | `doc/evidence/demo/accept/TESTLIB_baseline_md5.txt` | `4e5ac033f8c7ac671f1be82bd37ca702` |
| `doc/agents/_demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv` | `doc/evidence/demo/accept/TESTLIB_sandbox/tc_dom_polling_trig_chk_01.sv` | `8ad474be7928496487517a8666691d78` |
| `doc/agents/_demo/accept/evidence/A2_compile_evidence.md` | `doc/evidence/demo/accept/evidence/A2_compile_evidence.md` | `a09a9a8c7f02d1241d231172f756a12c` |
| `doc/agents/_demo/accept/evidence/A2f_compile_evidence_v6.md` | `doc/evidence/demo/accept/evidence/A2f_compile_evidence_v6.md` | `8ea66f2d2e53d40aa1bef16af693d09b` |
| `doc/agents/_demo/accept/evidence/A4_run_evidence.md` | `doc/evidence/demo/accept/evidence/A4_run_evidence.md` | `25786600959bdf46b3e8b0a10ed73d09` |
| `doc/agents/_demo/accept/guard/A6_guard.md` | `doc/evidence/demo/accept/guard/A6_guard.md` | `c20fe4628a451f808e4c8ad0a51f8b1d` |
| `doc/agents/_demo/accept/review/A3_review.md` | `doc/evidence/demo/accept/review/A3_review.md` | `999445d1a6fe7cbbd19ff5c1a4388707` |
| `doc/agents/_demo/accept/review/A3f_review_v6.md` | `doc/evidence/demo/accept/review/A3f_review_v6.md` | `2a5343fbb6ab9324a9ccad19700b4bea` |
| `doc/agents/_demo/accept/review/A5_reconcile.md` | `doc/evidence/demo/accept/review/A5_reconcile.md` | `f06e58ac82679cf86788725d8172d378` |
| `doc/agents/_demo/evidence/T2_compile_evidence.md` | `doc/evidence/demo/evidence/T2_compile_evidence.md` | `b276686a2c97f00ee76138329d47f31f` |
| `doc/agents/_demo/evidence/T2_prerun_snapshot.md` | `doc/evidence/demo/evidence/T2_prerun_snapshot.md` | `adf30d0ab0ad1d6c1ec1ed5c741e1cfe` |
| `doc/agents/_demo/evidence/T2b_compile_evidence_v2.md` | `doc/evidence/demo/evidence/T2b_compile_evidence_v2.md` | `0f5bc23740b071ec771e399bb49b0740` |
| `doc/agents/_demo/guard/T4_guard.md` | `doc/evidence/demo/guard/T4_guard.md` | `b758fcce8f4d0cbe7d66aecbd916a0ec` |
| `doc/agents/_demo/guard/T4_baseline.md` | `doc/evidence/demo/guard/T4_baseline.md` | `84ebb05dd9776e5243579d7a77489d8b` |
| `doc/agents/_demo/guard/T4_artifacts_md5.txt` | `doc/evidence/demo/guard/T4_artifacts_md5.txt` | `f1fffa53383a9bb22e214164dfcd2fe9` |
| `doc/agents/_demo/guard/T4_baseline_LOG_md5.txt` | `doc/evidence/demo/guard/T4_baseline_LOG_md5.txt` | `0af5b50cd9325ae7f9ab9c3c30e1cab2` |
| `doc/agents/_demo/guard/T4_blueprint_uvs_setup.txt` | `doc/evidence/demo/guard/T4_blueprint_uvs_setup.txt` | `e229293e1e08ef25f8b6347f269cac3f` |
| `doc/agents/_demo/review/T3_review.md` | `doc/evidence/demo/review/T3_review.md` | `1f937873bc5c0b0c3dd8428c569762ff` |
| `doc/agents/_demo/review/T3_baseline_prep.md` | `doc/evidence/demo/review/T3_baseline_prep.md` | `88c79a07fce1539bb964c2072bf89244` |
| `doc/agents/_demo/review/T3b_review_v2.md` | `doc/evidence/demo/review/T3b_review_v2.md` | `5232decefda897e5691e4a4a5ceeaa06` |

> 其余 9 件（`accept/evidence/A2b–A2e`、`accept/review/A3b–A3e`、`accept/guard/A6_audit_window_md5.txt`）
> 同样逐字节未变；**全量 32/32 已逐文件核过**（见 §3），本表只列关键件。

## 3 完整性校验（可复跑）

```bash
# ① 重命名检测（迁移当时、提交前）：应全部显示 rename ... (100%)
git diff --cached -M --summary | grep 'doc/agents/_demo'
# 提交后改用：
# git log --diff-filter=R --summary -- doc/evidence/demo

# ② 逐文件内容比对（旧 blob vs 新文件）：0 不一致
#    迁移前 HEAD = dc7c69e（本仓当时 HEAD；迁移后的提交是它的后代）
python3 - <<'PY'
import hashlib, os, subprocess
OLD_REF = 'dc7c69e'
new_root = 'doc/evidence/demo'
bad = []
for dp, _, fns in os.walk(new_root):
    for fn in fns:
        if fn == 'MIGRATION.md':      # 本迁移说明是新增件，不参与「未变」比对
            continue
        new = os.path.join(dp, fn)
        old = 'doc/agents/_demo/' + os.path.relpath(new, new_root)
        blob = subprocess.run(['git', 'show', OLD_REF + ':' + old], capture_output=True, check=True).stdout
        if hashlib.md5(blob).hexdigest() != hashlib.md5(open(new, 'rb').read()).hexdigest():
            bad.append(old)
print(f'checked=32 mismatched={len(bad)}'); print(*bad, sep='\n')
PY
```

**结论**：32/32 内容未变；本次迁移是**路径迁移**，不是内容修改。

## 4 内部历史路径字符串（**不要批量重写**）

- 迁移后的 32 件证据中，有 **28 个文件正文仍含 `doc/agents/_demo/...` 字符串**
  （不含本迁移说明；如 `README.md`、`guard/T4_guard.md`、`guard/T4_baseline.md`、
  `guard/T4_artifacts_md5.txt`、`review/T3b_review_v2.md` 等）。复核命令：
  ```bash
  grep -rl 'doc/agents/_demo' doc/evidence/demo --exclude=MIGRATION.md | wc -l   # → 28
  ```
- 这些字符串是**历史路径**，记录了当时实际发生的工作目录与文件位置；证据文件本身**冻结**，
  重写会把「路径迁移」变成「内容修改」，并使 `guard/T4_artifacts_md5.txt` 等按路径+md5 记账的记录失效。
  因此**一律保留原样**，由本文件统一说明：
  - 读到 `doc/agents/_demo/...` ⇒ 当前实际位置 = `doc/evidence/demo/...`（去掉 `agents/_demo` 前缀）；
  - 这些历史字符串**不代表**该路径现在存在。
- 例外：`doc/evidence/demo/README.md` 的标题与「代码落点」两处也写的是旧路径，同样**保持原样**；
  阅读时按上述映射换算即可。

## 5 引用入口

- 目录索引：[`doc/evidence/README.md`](../README.md)
- 演练说明（内容冻结，路径未改写）：[`doc/evidence/demo/README.md`](README.md)
- 上层文档：`doc/README.md`、`doc/agents/README.md`（演练产物已迁出角色目录）
