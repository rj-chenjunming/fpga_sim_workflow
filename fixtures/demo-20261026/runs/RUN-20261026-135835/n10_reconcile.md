# N10 结果对账

- run_id：`RUN-20261026-135835`
- 目标用例：`tc_pcie_rw_02`
- 口径一（`*E` 文本行数）：**29**
- 口径二（UVM Report Summary）：**{'UVM_INFO': 29, 'UVM_WARNING': 0, 'UVM_ERROR': 0, 'UVM_FATAL': 0}**
- 判据：`PASS ⟺ 两套口径皆 0 ∧ UVM Report Summary 出现 ∧ 期望观测点印记三向一致` ⇒ **passed=False**
- 身份四方同值：`None`

## 逐用例

- `tc_pcie_rw_02`：口径一=29 / 口径二={'UVM_INFO': 29, 'UVM_WARNING': 0, 'UVM_ERROR': 0, 'UVM_FATAL': 0} ⇒ passed=False （口径一 = 29 ≠ 0; 无预期观测点印记（I3：预期观测点必须留下通过印记））

## FAIL 三分类

(无分类输出)

## 待裁决（分类 2/3）

(无)
