# 附录 B · 反向抽检（变异）13 条 — 命令与原始输出

> 对象：`7b38c0e` 的 S7 最终树（复核起点工作树干净）。数据根 = `<repo>/.dev-ws-s8a`。
> 纪律：每条变异在**同一条 bash 调用内**完成「改 → 跑定向用例 → `git checkout -- <file>` → 核对」，
> 事后 `git diff --name-only <file>` 必须为空。**未留任何变异残留**（§B-14 汇总核对）。
> 报告正文：[AUDIT-20261029-s7.md](../AUDIT-20261029-s7.md) §5。

## B-1 复原方法（每条统一）

```bash
# 1) 精确替换（锚点必须命中，否则断言失败、不跑测试）
python3 - <<'PY'
p = "<file>"; s = open(p).read(); old = "<原实现>"
assert old in s, "anchor missing"
open(p, "w").write(s.replace(old, "<变异实现>"))
print("mutated")
PY
# 2) 只跑定向用例（不跑全量）
cd loop && LOOP_WORKSPACE=<repo>/.dev-ws-s8a LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q <target>
# 3) 立即复原并核对
cd <repo> && git checkout -- <file> && git diff --name-only <file>    # 空 = 已复原
```

---

## B-2 M1 · `materials_for` 恒返回 `INPUT_MATERIALS`（材料面白名单失效）

```python
# loop/host/agent_backends/dsh_assets.py
-    return NODE_MATERIALS.get(key, INPUT_MATERIALS)
+    return INPUT_MATERIALS  # MUTATION M1
```

```text
pytest -q tests/test_n6_material_face.py
...
FAILED tests/test_n6_material_face.py::test_n6_summary_records_derivation_source_and_md5
FAILED tests/test_n6_material_face.py::test_n6_summary_projects_only_target_fields_not_a_second_judgement
FAILED tests/test_n6_material_face.py::test_non_n6_nodes_keep_the_full_material_face
FAILED tests/test_n6_material_face.py::test_n6_missing_derivation_source_is_absent_not_faked
FAILED tests/test_n6_material_face.py::test_n6_derivation_from_malformed_source_is_explicit_failure
6 failed, 6 passed in 0.75s
restored; git status: (目标文件无 diff)
```

**判定：RED —— 判据有判别性。**

## B-3 M2 · `derive_material` 把源件整块投影进摘要（原文回流）

```python
# loop/host/agent_backends/dsh_assets.py（projected 字典里追加整条源 item）
                                         "rtl_files": [str(x) for x in (item.get("rtl_files") or [])],
+                                        "raw": item}  # MUTATION M2
```

```text
pytest -q tests/test_n6_material_face.py
...
tests/test_n6_material_face.py:98: AssertionError
FAILED tests/test_n6_material_face.py::test_n6_input_excludes_full_impact_documents
FAILED tests/test_n6_material_face.py::test_n6_summary_projects_only_target_fields_not_a_second_judgement
2 failed, 10 passed in 0.72s
M2 restored above (empty diff = ok)
```

**判定：RED。**

> 备注（`dsh_assets.py` 的模拟与真实差异）：本条与 M1 都在复核早期执行（当时 `git status` 干净、
> `dsh_assets.py` 未被并行 writer 改动）。复核后期 S8b 在该文件追加了未提交内容，故本报告引用的
> `dsh_assets.py` 行号/片段一律以 `git show 7b38c0e:loop/host/agent_backends/dsh_assets.py` 为准。

## B-4 M3 · `prepare_attempt` 绕过 `materials_for`

```python
# loop/host/agent_backends/dsh.py
-        chosen = A.materials_for(node) if materials is None else tuple(materials)
+        chosen = A.INPUT_MATERIALS if materials is None else tuple(materials)  # MUTATION M3
```

```text
pytest -q tests/test_n6_material_face.py
FAILED … test_n6_summary_projects_only_target_fields_not_a_second_judgement
FAILED … test_n6_missing_derivation_source_is_absent_not_faked
FAILED … test_n6_derivation_from_malformed_source_is_explicit_failure
5 failed, 7 passed in 0.79s
M3 restored (empty diff=ok)
```

**判定：RED。**

## B-5 M4 · `runtime_fingerprint` 恒加 `tool_allowlist` 键（回退档不再等于 S6）

```python
# loop/host/agent_backends/dsh.py
-    if config.tool_allowlist.enabled:
-        payload["tool_allowlist"] = AL.policy_fingerprint(config.tool_allowlist)
+    payload["tool_allowlist"] = AL.policy_fingerprint(config.tool_allowlist)  # MUTATION M4
```

```text
pytest -q tests/test_dsh_tool_allowlist.py tests/test_dsh_admission.py tests/test_dsh_backend.py
........................................................................ [ 49%]
........................................................................ [ 99%]
.                                                                        [100%]
145 passed in 9.06s
M4 restored
```

**判定：GREEN ⇒ 覆盖缺口 G1**（没有任何用例钉「关闭时指纹必须与 S6 逐字相同」）。

## B-6 M5 · `_plugins()` 恒挂白名单插件（关闭也挂）

```python
# loop/host/agent_backends/dsh.py
-        if self._config.tool_allowlist.enabled:
-            return (SUBMIT_PLUGIN, ALLOWLIST_PLUGIN, SELFCHECK_PLUGIN)
-        return (SUBMIT_PLUGIN, SELFCHECK_PLUGIN)
+        return (SUBMIT_PLUGIN, ALLOWLIST_PLUGIN, SELFCHECK_PLUGIN)  # MUTATION M5
```

```text
pytest -q tests/test_dsh_tool_allowlist.py tests/test_dsh_admission.py tests/test_dsh_backend.py
145 passed in 8.56s
M5 restored
```

**判定：GREEN ⇒ 覆盖缺口 G1**（现有 `test_real_dsh_allowlist_disabled_echoes_absence` 自己传插件元组，
不经 `_plugins()`，所以抓不到）。

## B-7 M6 · `session_copy` 的 missing 映射漂移

```python
# loop/services/instance_proxy.py
-        reason = {OWNERSHIP_MISSING: "session_metadata_missing",
+        reason = {OWNERSHIP_MISSING: "session_log_missing",  # MUTATION M6
```

```text
pytest -q tests/test_instance_proxy.py
FAILED tests/test_instance_proxy.py::test_session_copy_unavailable_reason
FAILED tests/test_instance_proxy.py::test_s7d_ownership_kind_maps_to_each_reason_vocabulary
2 failed, 58 passed, 1 warning in 18.66s
M6 restored
```

**判定：RED（S7d「reason 逐条不变」有钉子）。**

## B-8 M7 · `load_target` 的 invalid 映射漂移

```python
# loop/services/instance_proxy.py
-        raise TargetUnavailable(
-            "target_invalid" if exc.kind == OWNERSHIP_INVALID else "target_missing") from None
+        raise TargetUnavailable("target_missing") from None  # MUTATION M7
```

```text
pytest -q tests/test_instance_proxy.py
FAILED tests/test_instance_proxy.py::test_r10_missing_or_mismatched_metadata_unavailable
FAILED tests/test_instance_proxy.py::test_s7d_ownership_kind_maps_to_each_reason_vocabulary
2 failed, 58 passed, 1 warning in 18.62s
M7 restored
```

**判定：RED。**

## B-9 M8 · `agent_instance.json` 权限 0600 → 0644

```python
# loop/host/agent_backends/dsh_web_instance.py
-METADATA_MODE = 0o600
+METADATA_MODE = 0o644  # MUTATION M8
```

```text
pytest -q tests/test_dsh_web_instance.py
FAILED tests/test_dsh_web_instance.py::test_write_metadata_is_atomic_0600_and_replaces
1 failed, 29 passed in 2.50s
M8 restored
```

**判定：RED。**

## B-10 M9 · `TokenRedactFilter` 变成 no-op

```python
# loop/services/instance_proxy.py
     def filter(self, record: logging.LogRecord) -> bool:
+        return True  # MUTATION M9: no redaction
         record.msg = _redact_token_text(record.msg)
```

```text
pytest -q tests/test_instance_proxy.py
FAILED tests/test_instance_proxy.py::test_s7c_token_in_uvicorn_access_line_is_redacted
1 failed, 59 passed, 1 warning in 18.63s
M9 restored
```

**判定：RED —— 但只覆盖 uvicorn access-log 一种形态（见覆盖缺口 G2 与 P1-2）。**

## B-11 M10 · 前端把未知 session reason 折成「原因未知」

```js
// loop/web/s4-view.js
     if (has(SESSION_REASON, key)) return SESSION_REASON[key] + "（" + key + "）";
-    return key;
+    return "原因未知";  // MUTATION M10: fold unknown values
```

```text
PLAYWRIGHT_BROWSERS_PATH=<repo>/.pw-browsers HOME=<repo>/.chrome-home TMPDIR=<repo>/.chrome-tmp \
  pytest -q tests/browser/test_s4_projection_ui.py -k "session_copy or session_reason"
tests/browser/test_s4_projection_ui.py:476: AssertionError
FAILED tests/browser/test_s4_projection_ui.py::test_unknown_session_reason_is_shown_verbatim_not_folded
1 failed, 4 passed, 23 deselected in 11.09s
M10 restored
```

**判定：RED。**

## B-12 M11 · `WebInstance.describe()` 回吐 token

```python
# loop/host/agent_backends/dsh_web_instance.py
-        return {"host": None if target is None else target.host,
+        return {"token": None if target is None else target.token,  # MUTATION M11
+                "host": None if target is None else target.host,
```

```text
pytest -q tests/test_dsh_web_instance.py -k "token"
FAILED tests/test_dsh_web_instance.py::test_token_never_reaches_logs_repr_or_describe
1 failed, 4 passed, 25 deselected in 0.86s
M11 restored
```

**判定：RED。**

## B-13 M12 · S7d 中文 reason 文案漂移

```js
// loop/web/s4-view.js
-    session_log_missing: "元数据未声明会话日志（Host 未落账 session_log）",
+    session_log_missing: "会话日志缺失",  // MUTATION M12
```

```text
pytest -q tests/browser/test_s4_projection_ui.py -k "session_copy or session_reason"
tests/browser/test_s4_projection_ui.py:464: AssertionError
FAILED tests/browser/test_s4_projection_ui.py::test_unavailable_session_copy_explains_reason
1 failed, 4 passed, 23 deselected in 11.26s
M12 restored
```

**判定：RED。**

## B-14 M13 · R20 不再删除上游 `X-Frame-Options`

```python
# loop/services/instance_proxy.py
         if low == "x-frame-options":  # R20
-            continue
+            pass                      # MUTATION M13: stop dropping XFO
```

```text
pytest -q tests/test_instance_proxy.py -k "r20 or r18 or r17 or r15"
FAILED tests/test_instance_proxy.py::test_r20_x_frame_options_always_dropped
1 failed, 4 passed, 55 deselected, 1 warning in 3.36s
M13 restored
```

**判定：RED（拒绝矩阵 R20 有判别性）。**

## B-15 汇总与残留核对

| 变异 | 目标文件 | 结果 | 抓它的用例数 |
|---|---|---|---|
| M1 | `dsh_assets.py` | RED 6 failed | 6 |
| M2 | `dsh_assets.py` | RED 2 failed | 2 |
| M3 | `dsh.py` | RED 5 failed | 5 |
| M4 | `dsh.py` | **GREEN** 145 passed | **0（G1）** |
| M5 | `dsh.py` | **GREEN** 145 passed | **0（G1）** |
| M6 | `instance_proxy.py` | RED 2 failed | 2 |
| M7 | `instance_proxy.py` | RED 2 failed | 2 |
| M8 | `dsh_web_instance.py` | RED 1 failed | 1 |
| M9 | `instance_proxy.py` | RED 1 failed | 1 |
| M10 | `s4-view.js` | RED 1 failed | 1 |
| M11 | `dsh_web_instance.py` | RED 1 failed | 1 |
| M12 | `s4-view.js` | RED 1 failed | 1 |
| M13 | `instance_proxy.py` | RED 1 failed | 1 |
| **合计** | | **11 RED / 2 GREEN** | 23 |

**残留核对**（复核结束时，只针对我改过的 5 个文件）：

```text
$ git diff --name-only loop/host/agent_backends/dsh_assets.py loop/host/agent_backends/dsh.py \
    loop/services/instance_proxy.py loop/host/agent_backends/dsh_web_instance.py loop/web/s4-view.js
（空）

$ git status --short          # 复核后期快照（含并行 writer 的在制品，**不是我的写入**）
 M loop/host/agent_backends/dsh_assets.py     ← 并行 S8b 的未提交改动（复核对象之外）
 M loop/services/agent_view.py                ← 并行 S8c 的未提交改动（复核对象之外）
?? loop/tests/test_agent_view_identity_cold_read.py
?? loop/tests/test_ds09_home_provenance.py
```

我本轮唯一写入 = `doc/audit/AUDIT-20261029-s7.md` + `doc/audit/parts/s7-*.md`（三份）。
