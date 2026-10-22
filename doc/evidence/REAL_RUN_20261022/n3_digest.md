# N3 差异语义摘要

- 模型模式：`live`；provider：`origin-deepseek-v4-1-flash`
- 校验：`True`

## 摘要

本轮两条差异均指向 pcie_register.v，逐文件 md5 与 RTL 文本均标记为 modified；文本 hunk 将 s_reg_test 写入值改为仅保留 [15:0] 并新增 0x0d04 pcie_test 的保留位注释。另一条为逐文件 md5 变化，无文本 hunk，需人工确认其与 RTL hunk 的对应关系。

## 分组

(无分组输出)

## 需人工重点确认

- offered_segments 为空，两条 diff 的 segment 均为 null；无法按“段 + 变更种类”落组，需 Host/人工提供段信息后再确认分组与影响面。
- 同一 entry_id 出现两条 diff（allfile 与 rtl_file），且前后 md5 值一致、change 均为 modified；需人工确认二者是同一物理改动的双路证据还是应分别计入，避免影响面重复或遗漏。
- allfile 条目无 diff_hunk、lines 为空，unresolved 标注仅逐文件 md5；需人工确认文本层是否还有未展示改动，并核对该条与 rtl_file hunk 的对应关系。
- rtl_file hunk 仅展示 s_reg_test 写入路径将 dcb_wdata 高 16 位清零（{16'h0, dcb_wdata[15:0]}）并新增 0x0d04 pcie_test 注释；需人工确认读路径“reserved read as 0”及该寄存器地址/字段语义是否在别处覆盖，不能仅凭此 hunk 判断完整行为。
- hunk 头为 @@ -168,7 +168,8 @@，但 lines 为 171、172，offset 为 0xd04；需人工确认行号/偏移映射与实际修改位置一致，并检查邻近未展示行是否受影响。

## 元数据

- input_digest：`{"run_id": "RUN-20261022-181700", "diffs": 2, "offered_segments": 0, "coverage": 5}`
