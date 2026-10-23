# AI 工作面板首批实现证据

日期：2026-10-24；同一执行者编制规格、实现与验证，没有独立终验。
规格先于实现：[SPEC-09 §11](../../spec/AI_WORK_PANEL_SPEC.md#11-本批实现契约2026-10-24先于代码)，
切片见 [计划](../../plans/2026-10-24-ai-work-panel-implementation.md)，全部结果与缺口归 [STATUS §55](../../STATUS.md)。

基线为远端 d58e936；未改业务后端、环境冻结资产与原 REV04。
执行连接中断后重新连通，核对保留的工作树再继续；首次产品补丁因连接断开未落盘，恢复后重新应用。
基线文件标明仅保留工具摘要；其余测试日志来自实际命令输出，没有将中间失败删除或标绿。
中间浏览器失败包括新导航缺少 agents API 夹具与焦点回退缺陷；原故事/报告断言完整保留。
另一次 G2 自动选页断言未满足，原用例未放宽，后续定向与最终完整运行均通过；未据此声称查明根因。
截图使用受控 API；画面中的模型方式/校验状态是测试记录，不是真实模型、真机仿真或生产运行证据。

## 复现命令

在 loop 目录使用现有虚拟环境，不安装依赖、不调用 live 模型：

```bash
LOOP_BROWSER_EXECUTABLE=/usr/bin/chromium .venv/bin/python -m pytest -q tests/browser
LOOP_LLM_MODE=standin .venv/bin/python -m pytest -q tests/test_web_smoke.py tests/test_agent_view.py tests/test_agent_control.py tests/test_agent_context_memory.py tests/test_node_story.py tests/test_node_registry.py tests/test_node_detail_refs.py tests/test_context_explain.py tests/test_capability_format.py tests/test_capability_facts.py
```

红灯组为新文件首次执行；边界组首次使用关键词 unknown_payload / changed_revision / reading_position / returns_to_single。
最终完整浏览器包含新增面板与保留的节点详情、报告、闸门、草稿、布局场景。
kb 自测使用临时可写根，归档资产缺失按失败保留；端到端只做前置检查，未执行清理状态的驱动。
全套软件入口和整库文档门的未通过结果不由局部回归替代。DSH 接入、用户效率测量与内网验收未执行。

## 归档文件与 MD5

目录内容只新增，归档后只读；完整校验清单在目录外的同名 .md5 文件。

| 文件 | MD5 |
|---|---|
| [01-baseline-summary.txt](01-baseline-summary.txt) | `8294e46660b56fac9ebc3eb7506df765` |
| [02-new-tests-red.txt](02-new-tests-red.txt) | `db2b76d2c73a4c002b90dff845c1a38f` |
| [03-first-green.txt](03-first-green.txt) | `621905335c4376c93e4f6f1f492a5833` |
| [04-edge-red.txt](04-edge-red.txt) | `ad724f73986bbe4ad742900050a98d68` |
| [05-edge-green.txt](05-edge-green.txt) | `31091c88c460b0826b028ea66cf52de7` |
| [06-browser-integration.txt](06-browser-integration.txt) | `626eeed1eb76fbe5b03bc01385006c67` |
| [07-focus-red.txt](07-focus-red.txt) | `d5da958d2f4466dde3bff20994985bc0` |
| [08-focus-green.txt](08-focus-green.txt) | `6bbcc908fbc491bb8cb25ccb22fe799b` |
| [09-browser-final.txt](09-browser-final.txt) | `c44c0f371d8dcc022de777e1cd7036de` |
| [10-software.txt](10-software.txt) | `93a160346c077bf71179b315f095020d` |
| [11-kb-schema.txt](11-kb-schema.txt) | `53e4752a3aa20f8407e34ee6f9d01a68` |
| [12-kb-n5.txt](12-kb-n5.txt) | `dbd16ac7ca3aae24da08f784cfd498b6` |
| [13-e2e-preflight.txt](13-e2e-preflight.txt) | `452b3505b1c2575008d8fdee3175207d` |
| [14-doc-delta.txt](14-doc-delta.txt) | `d77dab61ea44f19058d51e5f33a6b7a0` |
| [1440-n6.png](1440-n6.png) | `3b27258d346664f1e6bac257e913bf13` |
| [15-official-software-entry.txt](15-official-software-entry.txt) | `1e8041aece3be1658ce3b838c5e1c692` |
| [320-n6.png](320-n6.png) | `fd5ea56ee08e40eb1d4734574c38ddd6` |
| [768-n6.png](768-n6.png) | `71370d090ad0f8a4d59951c4e1a329d1` |
