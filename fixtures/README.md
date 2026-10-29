# `fixtures/` —— 冻结夹具的版本库副本（2026-10-29 由人工决定入库）

> **本目录是什么**：从本机数据根 `workspaces/s0-ws-20261023/fixtures/` **原样复制**过来的两份冻结夹具。
> 入库理由是**人工决定**（2026-10-29）：让 fresh clone / 另一台机器不必依赖本机大目录就能演示与回放。
> 所有数字与 md5 均由命令输出复制（`AGENTS.md` 红线 2），禁手算。

## 1 这与既有「夹具不入 git」约定的关系

`workspaces/README.md` 与 [演示夹具身份档案](../doc/evidence/DEMO_FIXTURE_20261026.md) 说夹具「**不入 git**，身份另记在
`doc/evidence/`」——那条约定针对的是 **`workspaces/` 下的活数据根**（整个 `workspaces/` 实测 134 GB，`/home/...` 绝对路径、
每轮运行都会增长）。本次**没有推翻它**：

| | `workspaces/<env>/fixtures/**`（活数据根，回放/演示时实际读取） | `fixtures/**`（本目录，版本库副本） |
|---|---|---|
| 入库 | **不入**，仍由 `.gitignore:19` 的 `workspaces/*/` 排除 | 入（`fixtures/` 不在忽略范围内） |
| 作用 | 工作副本，供本机演示与 drill 回放 | 分发副本，供他机/他人复现 |
| 变更 | 可随时新增夹具 | **只增不改**：已提交目录不再就地修改 |

两份内容**字节一致**（§2 的 md5 逐值校验）。若将来活数据根里的同名夹具被更新，本目录**不回填**，
而是新增一份（`AGENTS.md` 红线 3「归档只增不改」）。

## 2 内容与身份

| 夹具 | 文件数 | 体量 | `md5.txt` 行数 | `md5.txt` 自身 md5 |
|---|---|---|---|---|
| `demo-20261026/` | 105 | 14 MB | 103 | `db298e33dc29e95884982d91a5a092d5` |
| `drill-real-20261024/` | 36 | 14 MB | 35 | `bfdac9aa8938bf2b6b9832df34a0b0f9` |
| **合计** | **141** | **28 MB** | — | — |

- `demo-20261026/` = `RUN-20261026-135835`：可完整演示四屏与三道闸门，G1 逐条处置真的落账。详见
  [演示夹具身份档案](../doc/evidence/DEMO_FIXTURE_20261026.md)。
- `drill-real-20261024/` = `RUN-20261024-002609` 的真实轮回放片段，供 `LOOP_DRILL_FIXTURE` 使用。详见
  [SPEC-REV-12 验证](../doc/evidence/SPEC_REV05_VERIFY_20261026.md)。

`demo-20261026/` 关键件 md5（其余见各目录 `md5.txt`）：

```
2e0ed2c98aa19f0cfe4ea6c109a280c5  decisions/G1_diff_confirm.json
752105e273481a49dc4285d5af119ed9  decisions/G2_report_accept.json
9c7c9a09fef7afe613ced8a4535be2e9  decisions/G3_regression_decision.json
e295baebf57fa9ca171521493f3783f6  gates.json
661eb086df03a49296130385972e6ed5  view.json
```

## 3 校验（clone 后必须全 OK）

`.gitattributes` 对 `fixtures/**` 设 `-text -diff`，禁止行尾转换——夹具内有 **10 个文件含 CRLF**，
一旦被规范化，`md5sum -c` 就会失败。校验：

```bash
cd fixtures/demo-20261026        && md5sum -c md5.txt | grep -c ': OK$'   # 期望 103
cd fixtures/drill-real-20261024  && md5sum -c md5.txt | grep -c ': OK$'   # 期望 35
```

## 4 怎么用

```bash
# 演示：把 run 放进一个可写数据根，不要就地改夹具
mkdir -p /tmp/demo-ws/runs
cp -a fixtures/demo-20261026/runs/RUN-20261026-135835 /tmp/demo-ws/runs/
cd loop && LOOP_WORKSPACE=/tmp/demo-ws bash run.sh

# drill 回放：指向夹具目录（相对 WORKSPACE_ROOT）
LOOP_DRILL_FIXTURE=fixtures/drill-real-20261024
```

> 注意：`LOOP_DRILL_FIXTURE` 的含 `/` 相对值按 `WORKSPACE_ROOT` 解析（`loop/workflows/context.py`），
> 因此用 drill 夹具时须把本目录的数据摆到数据根下，或改用不含 `/` 的 run_id 形式。
