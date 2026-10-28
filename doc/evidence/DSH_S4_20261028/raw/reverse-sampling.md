# S4 反向抽检汇总（改坏实现 → 对应用例必须变红 → 复原）

> 口径：每条"变异"都只在**私有副本或改动前留底**的前提下进行，复原后逐字节 md5 校验一致。数字从命令输出复制。
> 参与方：三个实现 owner 各自抽检 + **独立验证者**（未参与实现，只报告不改）另做 28 条。

## 独立验证者（s4-reviewer）26+2 条

| 组 | 变异 | 结果 |
|---|---|---|
| 反代拒绝/改写 | R1 去字面 `..`、R2 改 rule 归属、R3 拆两层防御、R4 去 `%2f`、R6 去控制字符/反斜杠、R7 去 Host loopback 校验、R9 去 target loopback、R13 去 401/403 处理、R14 不丢客户端 `?token=`、R15 Location 原样、R16 不丢 `X-Forwarded-*`、R17 不删 Cookie Domain、R18 不收窄 `frame-ancestors`、R19 5xx 不标 unavailable、R20 不删 XFO | **全部 RED** |
| 凭据/SSRF | token 写进日志；客户端 `?url=` 改写目标；session-copy facts 置空 | **全部 RED** |
| 投影/未知 | 无进展 `>=`→`>`；`unknown`→`ok`；`standin`→`real`；compaction unknown→0；`accepted` 当 `applied`；`scope_expiry` 说成"已判定生效" | **全部 RED** |
| P1-1 缺口 | availability 的 attempt 钉成 1 | **首轮未变红 ⇒ 判为 P1（无覆盖）**；补 `test_p1_availability_scoped_to_node_and_attempt` 后，该变异与 `load_target` 的 `effective_attempt→1` 变异**均被抓**（终态复核） |
| P2-3 | 删 import 期压级调用 / 压级函数空操作 | **RED**（初版用例是空断言，已替换为 import-time spy 用例） |

## 各 owner 自检（非独立复核，仅作为"断言可证伪"的补充）

- S4-A：5 类变异全红（阈值/unknown→0/不传 now/accepted 当 applied/越界·链接校验失效），复原后 86→111 passed。
- S4-B：30 变异 / 28 抓；2 条如实登记为**等价或无效**（见 `red-green.md`）。
- S4-C：6 条界面变异 + P1-1/P2-5 各 1 条，除"锚点无效"两次（已改锚点）外全部 RED。

## 口径说明（不粉饰）

1. **"改坏后仍绿"不等于用例无效**：可能是两次防御重叠（R3 需同时拆两层）或断言分散在另一用例（`accepted≠applied` 在 revoked 用例里）。已逐条记录。
2. **"改坏后变红"也不等于断言强**：S4-C 有两次"改动被后续收尾行抵消"⇒ 等价于没改坏（无效锚点），已改成真正改坏再验。
3. 独立验证者的抽检在 `loop/.logs/s4-verify/`（gitignored 私有副本）内进行，**没有**修改被测文件；留底 `s4-before.patch`。
