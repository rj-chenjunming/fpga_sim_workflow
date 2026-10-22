# N2 差异对比（Host 确定性，spec §2 N2 / schema `n2_diff`）

- run_id：`RUN-20261022-181700`｜generated_at：`2026-10-22T18:17:02+0800`
- from：`v0`（`baselines/v0/manifest.json`）
- to  ：`v1`（`runs/RUN-20261022-181700/n1_manifest_new.json`）
- 结论：**有变化**

## 三路统计

| 路 | entries_from | entries_to | modified | added | removed |
|---|---|---|---|---|---|
| ① rtl_file | 162 | 162 | 1 | 0 | 0 |
| ② allfile | 4491 | 4491 | 1 | 0 | 0 |
| ③ doc_entry | 126 | 126 | 0 | 0 | 0 |

② 路 scope：`['PKG', 'RTL', 'TB', 'TESTLIB']`｜交集 `['PKG', 'RTL', 'TB', 'TESTLIB']`｜只在旧版 `[]`｜只在新版 `[]`

## 差异条目（每条带 evidence，下游 N3 的行号唯一来源）

| kind | id | change | before | after | evidence | lines | offsets |
|---|---|---|---|---|---|---|---|
| allfile | `RTL/SRC/imports/SRC/pcie_controller/pcie_register.v` | modified | d560f2ff15388aad16dc64431d67a617 | 50e4ca25f384d0ee384252b34f30e760 | baselines/v0/allfiles.md5:L2896 -> runs/RUN-20261022-181700/bundle/allfiles.md5:L2896（逐文件 md5 变化） | - | - |
| rtl_file | `RTL/SRC/imports/SRC/pcie_controller/pcie_register.v` | modified | d560f2ff15388aad16dc64431d67a617 | 50e4ca25f384d0ee384252b34f30e760 | baselines/v0/rtl_files.md5:L119 -> runs/RUN-20261022-181700/bundle/rtl_files.md5:L119（逐文件 md5 变化） | [171, 172] | ['0xd04'] |

## 无法定位的条目（不丢条目，给 unresolved 说明）

- `RTL/SRC/imports/SRC/pcie_controller/pcie_register.v`（allfile）：② 路只比逐文件 md5 清单，无文本 hunk（旧版正文不在 KB）⇒ offset 由 ①/③ 路提供；本条已按『modified』计入差异

## 抽出的 offset（供 N5 段粗筛后与用例访问求交）

| offset | kind | 来源 | entry_id |
|---|---|---|---|
| `0xd04` | rtl_file | `RTL/SRC/imports/SRC/pcie_controller/pcie_register.v` | - |

## 口径说明

- offset 两条来源：①路 hunk 新增/删除行里的地址字面量（`32'hXXXX_XXXX`、`0xXXXX`，按**块内偏移**理解，N5 用 `segment_rtl.json` 映射到段后换算 `<段基址>+<块内偏移>`）；③路 `entry_id` 的 `offset_global`**直接**作为 offset（无需从文本抽）。
- 归一化指纹复算口径（task-18 / F-DET-01）：`checks.normalized_sha256 = sha256(canon_json(本对象 **剔除 `checks`** 后，把 `generated_at` 替换为 `"<TIMESTAMP>"`))` —— 按 README §3.1.1 的字面公式**必须先剔除自指簿记键**才能复算。被剔除键清单：`["checks"]`（其中含本字段自身）；被归一化的时间字段：`["generated_at"]`。本件自报值见 `checks.normalized_sha256`。
- `generated_at` 是**唯一**被允许的非确定性字段（README §3.1.1，本脚本声明时间字段 `("generated_at",)`）；一律经 `kb_lib.now_iso()`，`--now`/`KB_NOW` 注入。强判据：同一输入 + 同一 `--now` 两次逐字节相同；弱判据：不同 `--now` 两次，`K.sha256_obj_normalized(obj, ("generated_at",))` 相同。
- ②路只比两版 `allfiles_manifest.scope` 交集；scope 只在单侧有的范围内文件**不可比**，记入 `scope_notes`，不静默当无差异。

③ 路条目集解析：旧版 = `baselines/v0/doc_entries.jsonl`（manifest.doc_fingerprint.path 同目录（主口径））；新版 = `runs/RUN-20261022-181700/bundle/doc_entries.jsonl`（manifest.doc_fingerprint.path 同目录（主口径））；用了回退=False
① 路 hunk 解码编码：utf-8（非 UTF-8 走 utf-8→gb18030→gbk→latin-1 回退；task-9 N2-3 / SPEC-REV-01 R3）

