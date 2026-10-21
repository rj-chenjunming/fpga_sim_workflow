# SpecDD 后续优化整理证据

本轮为文档整理与只读复核，不是实施/独立终验。范围为 HEAD `5f6cdb2` 加工作区既有修改；没有修改运行代码、kb 工具或历史证据。汇总及质量门状态以 [STATUS §11](../STATUS.md#11-后续优化与特征重构整理2026-10-21) 为准；结论见 [审计](../audit/AUDIT-20261021-specdd-followups.md)，行动见 [路线](../plans/2026-10-21-specdd-followups.md)。

## 受控探针

下列脚本运行于项目根，使用本仓 venv；临时目录仅写受控空 manifest，N2 工具执行被截获并终止。没有调用真实 kb 写工具、provider 或仿真器；观察的是现有行为，没有修复缺陷。脚本完成成功不等于业务验收通过。

将以下代码保存到临时脚本后，以项目根为工作目录执行。复现到其他位置时仅调整 repo 路径。原命令：

```bash
LOOP_LLM_MODE=standin loop/.venv/bin/python /workspace/scratch/specdd-followup-probes.py
```

```python
import asyncio
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

repo = Path('/workspace/fpga_sim_workflow')
sys.path.insert(0, str(repo / 'loop'))
from services.config_api import list_baselines
from services.agent_view import build_agents
from workflows.chunks import host_steps

class Captured(Exception):
    pass

async def main():
    with tempfile.TemporaryDirectory(prefix='specdd-audit-') as folder:
        root = Path(folder)
        baseline = root / 'baselines' / 'v-next'
        baseline.mkdir(parents=True)
        (baseline / 'manifest.json').write_text('{}')
        item = list_baselines(root)['baselines'][0]
        print(json.dumps({'probe': 'manifest_only_baseline', 'valid': item['valid'],
                          'files': [p.name for p in baseline.iterdir()]}, ensure_ascii=False))
        guardian = next(a for a in build_agents([], run_dir=root) if a['role'] == 'guardian')
        print(json.dumps({'probe': 'guardian_idle', 'summary': guardian['summary'],
                          'note': guardian['note']}, ensure_ascii=False))
        ctx = SimpleNamespace(mode='real', run_dir=root / 'run', run_id='AUDIT',
                              node_started=lambda *args: None)
        def capture(tool, args):
            print(json.dumps({'probe': 'n2_selected_baseline', 'requested_baseline': 'v-next',
                              'tool': tool, 'args': args}, ensure_ascii=False))
            raise Captured
        data = SimpleNamespace(input={'baseline': 'v-next'},
                               get_state=lambda key: {'baseline': 'v-next'})
        with patch.object(host_steps, 'ctx_of', return_value=ctx), patch.object(host_steps, 'run_kb_tool', capture):
            try:
                await host_steps.n2_diff(data)
            except Captured:
                pass
    spec = importlib.util.spec_from_file_location('doc_links', repo / 'doc/audit/check_doc_links.py')
    scanner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scanner)
    for ref in ['kb/tools/kb_lib.py', 'kb/schema/gates.schema.json']:
        if (repo / ref).exists():
            resolved, label = scanner._resolve(ref, None, None)
            print(json.dumps({'probe': 'tool_root_reference', 'ref': ref,
                              'local_exists': True, 'resolved': str(resolved), 'label': label}))

asyncio.run(main())

```

原始 stdout（退出码 0）：

```text
{"probe": "manifest_only_baseline", "valid": true, "files": ["manifest.json"]}
{"probe": "guardian_idle", "summary": "未实现（审计 A10）", "note": "N11 证据守护在业务契约中存在、当前实现为评估节点（该能力未实现，审计 A10）；本卡可能长期 idle。"}
{"probe": "n2_selected_baseline", "requested_baseline": "v-next", "tool": "n2_diff.py", "args": ["--from-baseline", "v0", "--to-manifest", "/tmp/specdd-audit-idoaoq9s/run/n1_manifest_new.json", "--run", "AUDIT", "--out-dir", "/tmp/specdd-audit-idoaoq9s/run"]}
{"probe": "tool_root_reference", "ref": "kb/tools/kb_lib.py", "local_exists": true, "resolved": "None", "label": "env?"}
```

## 全库文档扫描

命令：`python3 doc/audit/check_doc_links.py`，退出码 1。原始摘要：

```text
TOOL_ROOT = /workspace/fpga_sim_workflow
ENV_ROOT  = /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES
WORKSPACE = /home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES/kb
checked=820 skipped=10209 historical=834 missing=353
```

采样在评估/路线及导航写入后、STATUS 新节和本证据入档前；原始完整日志保存在工作区 scratch。缺失项仍包括内网资产与工具根解析误判，未据此宣布全库断链已解决。

## 验证边界

本轮不改实现，因此未新写业务测试或执行单测/浏览器/kb/端到端；后续改动仍需先绿特征、先红新行为以及逐门记录。内网资产不可访问，不要求用户外传。源码确认的读取方式和进程注册表限制不冒充生产性能/崩溃实验结论。

新增文档链接、源文件行号与索引入口通过专门检查；git diff 空白检查通过。输出在 STATUS §11。归档后 chmod 444，MD5 记录于本证据目录之外；既有冻结件不回填。

本轮增量检查 stdout：

```text
PASS: new document links, source line references and navigation anchors resolve.
PASS: audit finding IDs map to implementation slices.
```

git diff --check：退出码 0，无输出。
