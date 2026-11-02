# 节点整合本地补测证据（2026-11-02）

执行者为本次实现者，不构成独立复核。

对照源码：远端主线 f710079 与整合提交 3f0f18f，分别从完整 Git 提交导出到独立 Linux 目录，以相同合成 ENV_ROOT、各自空数据根和同一已核验 drill 夹具执行软件测试，不含浏览器、不设置失败上限。副本在本轮完整比较时尚未建立 loop/.venv 入口，相关脚本测试存在前置失败/跳过；完整统计与限制见 STATUS §160。

- failure-comparison.json：从两份 pytest 日志的最终汇总和 FAILED/ERROR 测试 ID 行机械提取，比较失败项差集；不是完整日志，不保存测试私有材料。
- supplement.log：补齐整合副本的 loop/.venv 入口后执行快照校验与新增合成流程测试的原始输出。
- 新增测试：loop/tests/test_modular_zero_flow.py；数据由测试即时生成，不冒充历史夹具，覆盖 G1_no_impact 等待恢复和决策后结束/进入 N9 停放取消。未替代历史默认夹具、真实 FPGA 或 DSH 验收。

完整比较日志保留在本机 WSL /home/fpga/work/validation-20261102-cont/ 下，未作为冻结原始日志归档。本文与附件新增后只读，校验清单位于目录之外；Windows 只读属性不等同 Linux chmod 444。
