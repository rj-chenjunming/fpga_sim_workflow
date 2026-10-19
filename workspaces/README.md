# `workspaces/<env-id>/` —— 软件管理的「每环境数据」（**目标位置**）

环境是插件；**数据归软件管**。本目录是**约定的目标位置**：一个环境在软件侧的全部状态都落在这里，
按 `environments.json` 里的 `workspace:` 归类，环境仓本身只保留它自带的冻结资产与文档。

> **当前实际（2026-10-19）**：default 环境 `simenv-tcs9620-64ch` 的 `workspace` 仍指向
> `<ENV_ROOT>/kb`（`ENV_ROOT=/home/work/chenjunming/FPGA_SIM/SimEnv_TCS9620_64CH_F_RJ_PANGO_DCN_WHITEBOXES`），
> 即数据仍在环境仓的 `kb/` 下。**数据不搬**的决定与理由见 `doc/spec/ENV_PLUGIN_SPEC.md` §7；
> 因此本目录目前只有本说明与 `.gitkeep`。

```
<WORKSPACE_ROOT>/                 # 解析：$LOOP_WORKSPACE → environments.json → 旧布局回落
├── index/        # 该环境的段/寄存器/用例访问/段↔RTL 索引（N1 生成物）
├── conflicts/    # 该环境的一等公民清单：C1—C72 / 访问限制 / D1—D20（I4 的输入）
├── baselines/    # 该环境的基线归档（七件套 + manifest(parent 链) + evidence）
├── adjudication/ # 该环境待人拍板的裁决材料（只写请求，不写结论）
└── runs/         # 该环境的每轮运行目录（含冻结见证）
                  # 例：<WORKSPACE_ROOT>/runs/<run_id>/**（N16 与闸门状态也在此）
```

**为什么按环境分而不是按软件分**：`index`/`conflicts`/`baselines`/`runs` 都是**关于某个环境
某一修订**的事实。换一个环境（甚至同一个环境的另一个基线），这些内容必须另起一份，
绝不能互相覆盖 —— 所以第一键是环境，第二键才是修订。

**归档只增不改**：`baselines/<v>/**` 与任何已冻结的 `runs/<run_id>/**` 一旦写入即只读
（`chmod 444`），md5 记到目录之外；迁移/复制时必须记录「路径映射表 + 前后内容 md5」，
不得就地回填历史轮。

> 本目录的数据**默认不入 git**（体积大、且属运行产物）；只保留本说明与 `.gitkeep`。
