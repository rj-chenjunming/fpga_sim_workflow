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

**演示/回放夹具**：`<环境>/fixtures/<夹具名>/` 存放**冻结的运行片段**（自带 `md5.txt` 与 `README.md`），
用于演示或 drill 回放；它们与 `runs/` 同样**不入 git**，身份另记在 `doc/evidence/`。
当前有：`s0-ws-20261023/fixtures/drill-real-20261024/`（真实轮回放，见
[SPEC-REV-12 验证](../doc/evidence/SPEC_REV05_VERIFY_20261026.md)）与
`s0-ws-20261023/fixtures/demo-20261026/`（可完整演示三道闸门 + G1 逐条处置，见
[演示夹具身份档案](../doc/evidence/DEMO_FIXTURE_20261026.md)）。

**为什么按环境分而不是按软件分**：`index`/`conflicts`/`baselines`/`runs` 都是**关于某个环境
某一修订**的事实。换一个环境（甚至同一个环境的另一个基线），这些内容必须另起一份，
绝不能互相覆盖 —— 所以第一键是环境，第二键才是修订。

**归档只增不改**：`baselines/<v>/**` 与任何已冻结的 `runs/<run_id>/**` 一旦写入即只读
（`chmod 444`），md5 记到目录之外；迁移/复制时必须记录「路径映射表 + 前后内容 md5」，
不得就地回填历史轮。

> 本目录的数据**默认不入 git**（体积大、且属运行产物）；只保留本说明与 `.gitkeep`。
>
> **例外（2026-10-29 人工决定）**：上述两份夹具已**原样复制**到仓库根的
> [`fixtures/`](../fixtures/README.md) 并入库（141 文件 / 28 MB），目的是让 fresh clone 与他机
> 也能演示/回放。**本目录仍是回放时实际读取的活数据根，其内容依旧不入库**；两处内容字节一致，
> 校验方法与边界见 [`fixtures/README.md`](../fixtures/README.md) §1。
