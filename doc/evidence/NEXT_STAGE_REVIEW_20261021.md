# 下一阶段优化与重构成册 · 复核证据

日期：2026-10-21（Asia/Shanghai）。基线提交：`d7cf7c6084e884b0f554893c11f812b04c64f6bc`。本轮仅复核、文档与受控只读探针，没有修复业务实现或执行整套业务验收；同一执行者复核，不是独立终验。

成果：[执行手册](../plans/OPTIMIZATION_PLAYBOOK.md)、[本次复核](../audit/AUDIT-20261021-post-ui-roadmap.md)。汇总在 [STATUS §13](../STATUS.md#13-下一阶段优化与重构成册2026-10-21)。旧 F01–F12 编号延续，F13–F15 为本次补充；文档中的步骤是后续目标，不是已交付能力。

## 可复现探针

源码：[post-ui-roadmap-probe.py](../audit/parts/post-ui-roadmap-probe.py)。运行位置为仓库根：

```bash
PYTHONDONTWRITEBYTECODE=1 LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium loop/.venv/bin/python doc/audit/parts/post-ui-roadmap-probe.py --browser
```

基线输入只在自动清理的临时目录中构造；N2 的实际工具调用被截获并立即终止；文档解析器只读；浏览器通过现有测试装置加载真实静态页，所有业务 API 均由受控 route 提供，没有连接真实 provider、kb 写工具或仿真器。脚本退出成功仅表示观察完成。

原始 stdout，退出码 0：

```jsonl
{"probe": "manifest_only", "valid": true}
{"probe": "manifest_array", "exception": "AttributeError"}
{"probe": "guardian_idle", "summary": "未实现（审计 A10）"}
{"probe": "n2_baseline", "requested": "v-next", "actual": "v0"}
{"probe": "tool_reference", "local_exists": true, "resolved": "None", "root": "env?"}
{"probe": "first_load_error", "head": "A\n加载中…\n读取失败", "claims_previous_success": true, "write_requests": 0, "page_errors": []}
```

解读：基线有效性/参数传递、guardian 提示和仓库路径解析的局部问题仍在；新增观察到非对象 manifest 抛 AttributeError、首次读取失败却声称有成功历史。局部观察不能证明历史真实运行已经受影响。

## 源码复核边界

已读并定位：创建准入与 N0/N1/N2、N11 实现与投影、网页请求/异常提示、样式重复声明和断点、测试根与清理驱动、Agent 全量历史查询、数据/校验发布顺序及进程内注册表。来源符号及基线行号在本次复核中列出。

样式层叠是结构性维护问题，没有据此宣称页面已出渲染事故。Agent I/O 性能、进程杀断恢复和真实 provider 取消语义没有在本轮测量；它们在手册中列为先测量/先注入故障或新增能力。S0-b 明确缺失，当前 ready=false 符合既有阻断契约。

## 文档检查方法

检查本轮新增/修改 Markdown 的相对链接、锚点和源代码行号；将新增 inline 路径与 HEAD 比较；核对总表与任务卡的 F-ID 覆盖、优先项及依赖；对照 HEAD 核验旧冻结证据内容 MD5；确认 loop/kb 实现无差异；探针源码作 Python 语法检查，补丁执行 git diff --check。

检查脚本以 git diff 与未跟踪清单确定范围，逐项解析链接及目标标题，调用现有解析器比较 inline 路径增量，并以 git show HEAD 内容核验旧件 MD5。实际 stdout，退出码 0：

```text
PASS: changed Markdown links, anchors and source line references resolve.
PASS: no additional unresolved inline paths versus HEAD.
PASS: F01-F15 task cards, priority table and dependency references agree.
PASS: prior evidence, history and audit content MD5 values are unchanged.
PASS: loop/kb implementation has no diff against HEAD.
PASS: read-only probe Python syntax is valid.
PASS: git diff --check.
```

汇总见 STATUS §13。本轮不运行会清理共享 state 的端到端脚本，不把既有全库文档扫描的外部缺件归零，也不把历史浏览器通过数复用成本轮结果。后续修改必须按执行手册逐片验证，完整内网验收条件保持可见。

报告冻结后仅新增后续证据，不回填；自身 MD5 记录于 STATUS。
