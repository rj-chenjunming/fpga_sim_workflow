# 附录 C · 只读临时探针（token 脱敏 / 回退档 / 白名单 / reason 词表 / 转义）

> 本附录的探针都是**只读**的：不写被测文件、不改数据根、不启真机进程。脚本用 heredoc 直接喂给
> venv python，不落仓（`.dev-ws-s8a/` 下临时产物已随数据根留在 gitignored 目录）。
> 报告正文：[AUDIT-20261029-s7.md](../AUDIT-20261029-s7.md)（P1-2 / P2-1 / P2-3 / P2-5 / P2-12）。

## C-1 `TokenRedactFilter` 覆盖面对照（P1-2 的证据）

前提：`from services import instance_proxy` 即安装过滤器（import 副作用）。用**同一个已安装实现**，
把日志流捕获到内存（formatter 额外打印 `extra.url`），逐组检查 secret 是否出现。

```python
import io, logging, sys
sys.path.insert(0, ".")
from services import instance_proxy as IP          # import 即 install_token_redaction()
SECRET = "SECRETTOKEN123"
buf = io.StringIO()
class F(logging.Formatter):
    def format(self, r):
        base = super().format(r); extra = getattr(r, "url", "")
        return base + ("|EXTRA=" + extra if extra else "")
h = logging.StreamHandler(buf); h.setFormatter(F("%(name)s|%(levelname)s|%(message)s"))
root = logging.getLogger(); root.setLevel(logging.DEBUG); root.addHandler(h)
for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
    logging.getLogger(name).setLevel(logging.DEBUG)

def run(label, fn):
    buf.truncate(0); buf.seek(0); fn(); out = buf.getvalue()
    print(f"[{label}] leaked={SECRET in out} out={out.strip()[:300]!r}")
```

```text
installed filters: {'uvicorn.access': ['TokenRedactFilter'], 'uvicorn.error': ['TokenRedactFilter'],
                    'uvicorn': ['TokenRedactFilter'], '': ['TokenRedactFilter']}

[child logger services.instance_proxy]    leaked=True  out='services.instance_proxy|WARNING|proxy url ?token=SECRETTOKEN123'
[child logger services.api]               leaked=True  out='services.api|WARNING|api url ?token=SECRETTOKEN123'
[uvicorn.access parameterized full_path]  leaked=False out='uvicorn.access|INFO|127.0.0.1:5 - "GET /instance/R/N/1/?token=<redacted> HTTP/1.1" 303'
[uvicorn.error exc_info traceback]        leaked=True  out='uvicorn.error|ERROR|Exception in ASGI application\nTraceback (most recent call last):\n  File "<stdin>", line 17, in _exc\nRuntimeError: upstream GET http://127.0.0.1:9/?token=SECRETTOKEN123 failed'
[uvicorn.access extra=]                   leaked=True  out='uvicorn.access|INFO|no token in msg|EXTRA=http://x/?token=SECRETTOKEN123'
[root direct parameterized token=%s]      leaked=False out=''
```

**结论**

| 面 | 是否脱敏 | 说明 |
|---|---|---|
| `uvicorn.access` 的 request line（真机修复的那一面） | ✅ 是 | msg 无 token、token 在 args 里，args 被逐项脱敏 |
| 子 logger（`services.instance_proxy` / `services.api` / 任意非上表 logger） | ❌ 否 | **logger 级 filter 不作用于冒泡记录**；root 的 filter 只对"直接打在 root 上"的记录生效 |
| `extra=` 自定义字段 | ❌ 否 | filter 只改 `record.msg` / `record.args` |
| `exc_info` traceback | ❌ 否 | filter 不碰 `record.exc_info` / `record.exc_text` |

**附带发现（同一探针的第一版原始 stderr）**：当调用形态是 `logger.warning("…?token=%s", secret)` 时，
过滤器把 **格式串**里的 `token=%s` 改成 `token=<redacted>`，却保留了 arg ⇒ `record.getMessage()` 抛
`TypeError: not all arguments converted during string formatting`，logging 内部的错误处理把**原始 arg
打到 stderr**：

```text
--- Logging error ---
TypeError: not all arguments converted during string formatting
Message: 'root direct ?token=<redacted>'
Arguments: ('SECRETTOKEN123',)
```

⇒ 即使不认为「子 logger/extra/traceback」必须覆盖，**「先脱敏格式串、再交给 % 格式化」这个实现顺序本身**
在参数化日志下会把 secret 泄到 stderr、并丢掉该条日志。建议修复时一并处理（例如先 `record.getMessage()`
再脱敏并置 `record.args = ()`）。

## C-2 allowlist 回退档直跑（工单 b 的核心验收）

不跑门、不起进程，直接在自造配置上调用实现：

```python
cfg_disp = D.DshConfig(enabled=True, version="0.2.1-rc.2", node=binp, bin=binp,
                       bin_sha256=..., timeout_s=30.0)                      # tool_allowlist=DISABLED_POLICY
cfg_on   = replace(cfg_disp, tool_allowlist=AL.policy_from_settings({"enabled": True}))
```

```text
1) plugins(disabled) = ['s2-submit-result', 's2-selfcheck']
1) plugins(enabled)  = ['s2-submit-result', 's7b-tool-allowlist', 's2-selfcheck']
2) render_env(disabled) = {}
2) render_env(enabled)  = {'DSH_TOOL_ALLOWLIST': '{"allowed":["read","write","edit","glob","grep","bash","submit_result"],"enabled":true,"enforce_visibility":true}'}
3) fp(disabled)==S6_formula: True
3) fp(disabled): sha256:caab7e4ad0aaac0aacf
3) fp(enabled) != fp(disabled): True
4) env_extra keys (disabled): ['DSH_ATTEMPT_KEY', 'DSH_SELFCHECK_DIR', 'DSH_SELFCHECK_NONCE']
4) DSH_TOOL_ALLOWLIST present: False
4) env_extra keys (enabled): ['DSH_ATTEMPT_KEY', 'DSH_SELFCHECK_DIR', 'DSH_SELFCHECK_NONCE', 'DSH_TOOL_ALLOWLIST']
4) patch count disabled/enabled: 4 5
```

其中 `fp(disabled)==S6_formula` 是拿 `runtime_fingerprint()` 与**手写的 S6 旧公式**（payload 只含
`schema/version/bin_sha256/profile/pins`，无 `tool_allowlist` 键）逐字比对 —— 相等 ⇒ 回退档指纹确实回到 S6。
⇒ **三处（插件/env/指纹）真的可回退**（代码正确）；缺口在「没有用例钉住」（变异 M4/M5 全绿，附录 B）。

## C-3 回退档的残留字段（P2-1）

`allowlist_record()` 关闭时返回 `None`，但调用点（`dsh.py:857-865`）**无条件**写这个键：

```python
selfcheck = {..., "toolAllowlist": allowlist_record(facts, self._config.tool_allowlist)}
```

```text
allowlist_record(disabled) = None
sealed selfcheck (disabled) = {'phase': 'deferred', 'toolCount': 26, 'toolAllowlist': None}
residual empty field present: True
```

```text
$ grep -rn "toolAllowlist" --include=*.py --include=*.js . | grep -v .logs
./host/agent_backends/dsh.py:864:                             "toolAllowlist": allowlist_record(
```

⇒ 全仓**没有任何消费者/用例**引用该键；关闭档的 sealed result 比 S6 多一个 `toolAllowlist: null`。
与 `allowlist_record` docstring「开关关 ⇒ None，不留空字段」（`dsh.py:227`）矛盾。

## C-4 `stage_inputs` 的白名单成员校验（P2-3）

```python
run/ 里放：n5_impact.json（真材料）+ secrets.json（非白名单）
D.stage_inputs(layout, run, materials=("secrets.json",))     # 显式传非白名单名
D.stage_inputs(layout2, run)                                  # 走默认参数
```

```text
explicit non-whitelist name staged: ['secrets.json'] -> file exists: True
default materials staged: ['n1_manifest_new.json', 'n2_diff.json', 'n2_diff.md', 'n3_digest.md',
                           'n5_impact.json', 'n5_impact.md', 'doc_entries.jsonl', 'case_states.json']
```

⇒ `stage_inputs` 只做「裸文件名 / 非符号链接 / run 目录内」检查（`dsh.py:448-465`），**不检查名字是否属于
`materials` 白名单**；默认参数仍是 S7a 前的 8 件全量面。生产侧因只经 `prepare_attempt→materials_for` 而安全，
但这意味着「白名单」是**调用方约定**而不是函数内判据 —— 未来任何一处直接调用都会静默绕过 S7a 的瘦身。

## C-5 `session_copy` 的 reason 词表外取值（P2-5）

造一个 `agent_instance.json` 指向**非 zstd 内容**的 `bad.zstd`：

```python
out = IP.session_copy(RUN_DIR, node="N3", attempt=1)
```

```text
available: False
reason: 'zstd -dc 失败 rc=1：zstd: /…/.dev-ws-s8a/tmp_probe/run/bad.zstd: unsupported format（/…/.dev-ws-s8a/tmp_probe/run/bad.zstd）'
in 6-item vocab: False
facts.reason: None
```

⇒ REV-16 §6.2 的六项 `session_*` 词表（`session_metadata_missing / session_metadata_invalid /
session_owner_mismatch / session_log_missing / session_log_invalid / session_log_unavailable`）
**只覆盖归属与路径判据**；`read_session_log` 的 `facts.reason` 是自由文本（含宿主绝对路径），
被 `instance_proxy.py:484-486` 原样透传成 HTTP `reason`。前端「未知值原样显示」（S7d 的有意行为）
会把这串长文本直出到界面。

## C-6 错误页 `prefix_root` 转义（P2-12）

```python
IP.unavailable_response("target_missing", accept="text/html",
                        prefix_root="/instance/x/<img src=x onerror=alert(1)>/N6/1/")
```

```text
status: 503
body: …<p><a href="/instance/x/<img src=x onerror=alert(1)>/N6/1/" target="_blank" rel="noopener">在新标签页打开</a></p>…
UNESCAPED_INJECTION: True
```

**可达性核查（关键，故不升级为安全缺陷）**：该 `prefix_root` 由路由段 `run_id`/`node` 拼成，
而 `services/api.py:580-585` 的 `_agent_root()` 在进 `forward()` **之前**要求
`run_id in manager.docs` 且 `node in control.NODES`，否则 404 ⇒ 两个段都落在固定集合内，
攻击者无法让 `<img …>` 进入 `prefix_root`。登记为**加固建议**（既有 S4 代码，非 S7 改动）：
`_error_page` 对 `link` 做 `html.escape` 即可一次性消除该面。

## C-7 真机 session log 里的模型读取面（支持 P1-1 的机制结论）

一次性的真机工作区（gitignored，可重建）里解压该 attempt 的 session log：

```text
$ zstd -dc …/session-3f1df466-….v4.jsonl.zstd | grep -o '"tool/call".\{0,220\}' | head -3
"tool/call","seq":14,…,"name":"bash","arguments":"{\"command\":\"ls -la; echo ---; ls -la ../input; echo ---; ls -la ../input/TESTLIB\"…"
"tool/call","seq":18,…,"name":"grep","arguments":"{\"pattern\":\"REG_FPGA_DATE|REG_FPGA_VERSION\",\"path\":\"../input\"…"
"tool/call","seq":23,…,"name":"bash","arguments":"{\"command\":\"cat ../input/n6_impact_summary.json\"…"

$ zstd -dc … | grep -c "n5_impact"
1     # 唯一出现处 = summary 的 "source": "n5_impact.json" 字段
```

⇒ 模型**读了派生摘要、没有读 345 KB 的 `n5_impact.json`**（`n2_diff`/`n3_digest` 也未读）。
这支持「材料面瘦身确实改变了模型的解析面」这一机制结论；但请注意该 session log **不在冻结证据内**
（覆盖缺口 P2-10：冻结证据只留了工具调用次数，没留参数）。
