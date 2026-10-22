# N10 结果对账

- run_id：`RUN-20261022-181700`
- 目标用例：`tc_pcie_rw_02, tc_pcie_rw_smoke, tc_rtc_05`
- 口径一（`*E` 文本行数）：**1687**
- 口径二（UVM Report Summary）：**{'UVM_INFO': 35066, 'UVM_WARNING': 0, 'UVM_ERROR': 0, 'UVM_FATAL': 0}**
- 判据：`聚合判据 = 各用例 I3 判据的合取（含印记三向一致）` ⇒ **passed=False**
- 身份四方同值：`True`

## 逐用例

- `tc_pcie_rw_02`：口径一=1687 / 口径二={'UVM_INFO': 34930, 'UVM_WARNING': 0, 'UVM_ERROR': 0, 'UVM_FATAL': 0} ⇒ passed=False （口径一 = 1687 ≠ 0; 无预期观测点印记（I3：预期观测点必须留下通过印记））
- `tc_pcie_rw_smoke`：口径一=0 / 口径二={'UVM_INFO': 57, 'UVM_WARNING': 0, 'UVM_ERROR': 0, 'UVM_FATAL': 0} ⇒ passed=False （无预期观测点印记（I3：预期观测点必须留下通过印记））
- `tc_rtc_05`：口径一=0 / 口径二={'UVM_INFO': 79, 'UVM_WARNING': 0, 'UVM_ERROR': 0, 'UVM_FATAL': 0} ⇒ passed=False （无预期观测点印记（I3：预期观测点必须留下通过印记））

## FAIL 三分类

- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x41xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x4100-0x41ff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x42xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x4200-0x42ff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x43xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x4300-0x43ff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x45xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x4500-0x45ff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x47xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x4700-0x47ff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x49xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x4900-0x49ff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x4bxx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x4b00-0x4bff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x4dxx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x4d00-0x4dff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x4fxx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x4f00-0x4fff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x51xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x5100-0x51ff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x52xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x5200-0x52ff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x53xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x5300-0x53ff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x55xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x5500-0x55ff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x57xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x5700-0x57ff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x59xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x5900-0x59ff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x5axx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x5a00-0x5aff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x5bxx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x5b00-0x5bff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x5dxx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x5d00-0x5dff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x5exx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x5e00-0x5eff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x5fxx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x5f00-0x5fff；entry_count=64，address_count=64；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x40xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x4000-0x40ff；entry_count=47，address_count=46；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x50xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x5000-0x50ff；entry_count=47，address_count=46；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:PCIE_REG_RD@3DW|0x58xx` ⇒ 既有缺陷：通道 PCIE_REG_RD@3DW；地址范围 0x5800-0x58ff；entry_count=47，address_count=46；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。
- `tc_pcie_rw_02:(merged)` ⇒ 既有缺陷：通道 (mixed)；地址范围为其余 22 个桶的归并桶；entry_count=266，address_count=204；Host 标记 overlaps_revision_point=false，且 revision_points 为空，未落在本轮修订点上，故归为既有缺陷。

## 待裁决（分类 2/3）

(无)
