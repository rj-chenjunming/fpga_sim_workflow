| 材料 | S6 前（`INPUT_MATERIALS` 全量） | S7a 后（N6 派生面） |
|---|---|---|
| `n1_manifest_new.json` | 2879 B  md5=c5e4b45b9615932e2cb02cebef6b2e28 | —（不再进 N6 input） |
| `n2_diff.json` | 5520 B  md5=a24c84986b0b06f7853cb5ca1cb5e089 | —（不再进 N6 input） |
| `n2_diff.md` | 3009 B  md5=e45946068349e4d8183626d65787c3fd | —（不再进 N6 input） |
| `n3_digest.md` | 26706 B  md5=ad58e9c6b8042a519b2ccf280dd00f02 | —（不再进 N6 input） |
| `n5_impact.json` | 345638 B  md5=dd1306a4e8584e7a7f0f43cb1a83e87e | —（不再进 N6 input） |
| `n5_impact.md` | 141098 B  md5=2b81ad54c2fa91db76ddbdd372601ae1 | —（不再进 N6 input） |
| `doc_entries.jsonl` | 323 B  md5=3466067f771931a5add7cfda31cecdf4 | —（不再进 N6 input） |
| `case_states.json` | 2949 B  md5=5bdbdad250d3f58b618f3c25da281410 | —（不再进 N6 input） |
| `TESTLIB/tc_bmc_i2c_03.sv`（目标用例源件，`stage_sources`） | 已在（S5 加） | 15470 B |
| `n6_impact_summary.json`（Host 派生） | — | 1287 B（派生自 `n5_impact.json` 345638 B / md5 `dd1306a4…`） |

**总量：S6 全量面 = 528122 B → S7a 的 N6 材料面 = 16757 B（15470 + 1287），缩小 96.8%。**
