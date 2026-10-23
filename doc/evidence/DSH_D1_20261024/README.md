# DSH D1 后端边界首片证据

日期：2026-10-24；基线 `dacdf54`。同一执行者实施与验证，无独立终验。
契约：[SPEC-REV-06](../../spec/SPEC-REV-06-20261024.md)；
计划：[D1 首片](../../plans/2026-10-24-dsh-backend-boundary.md)。
结果数字与缺口唯一汇总在 [STATUS §56](../../STATUS.md#56-dsh-d1-首片后端边界与-agently-适配2026-10-24)。

原始输出收在 [logs.tar.gz](logs.tar.gz)，保留失败、尾随空格及原始字节；未清洗日志来制造格式通过。
本目录冻结为只读，目录外 [MD5 清单](../DSH_D1_20261024.md5) 用于校验。

## 命令与顺序

命令在软件仓执行；pytest 在 loop 目录，以 LOOP_LLM_MODE=standin 运行。
受控 SDK 替身不会访问真实模型。

| 包内文件 | 执行内容 |
|---|---|
| 01-baseline.txt | `.venv/bin/python -m pytest -q tests/test_agent_backend_characterization.py tests/test_agent_context_memory.py tests/test_agent_control.py`；修改生产实现前 |
| 02-red.txt | `.venv/bin/python -m pytest -q tests/test_agent_backends.py`；新能力实现前，保留缺模块及参数错误 |
| 03-extraction.txt | 同基线命令；仅提取实际 SDK 调用后，尚未接入选择/元数据/固定配置 |
| 04-integration.txt | backend 新测试加上述特征、memory/control；新增行为接线后 |
| 05-regression.txt | 上述测试及 agent_view、context_explain、n8_context_budget、n6_imprint、f06_structure、f08_sealed、web_smoke、node_registry、node_detail_refs、capability_facts、capability_format |
| 06-software-gate.txt | `bash loop/spikes/run_software_checks.sh --ignore=tests/browser`；保留实际 exit |
| 07-kb-schema.txt / 08-kb-n5.txt | `loop/.venv/bin/python kb/tools/_selftest_gate_schema.py` / `_selftest_n5_reachability.py`；LOOP_WORKSPACE 指向各自临时目录；不造历史资产 |
| 09-runtime-preflight.txt | 读取权威 paths 解析结果、存在性及 PATH；git cat-file 检查旧对象，检查旧 bundle；不运行端到端清理 |
| 10-docs.txt / check-docs.py | 同一环境对比基线/当前文档门集合；新增链接和围栏检查；脚本保留供复核 |
| 11-runtime-status.json | 云运行时安全字段摘要，不含凭据或环境原文 |

D0 未发现可验证的原生 DSH 接口，因此没有猜测 CLI、会话/工具活动或 DSH 可用性。
后端边界通过测试不代表真 DSH、内网模型或仿真通过；完整门禁和旧提交恢复缺口继续保留。
