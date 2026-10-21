# F05 前端按功能拆分（第一步：闸门会话判定） · 切片计划

> 承接 [OPTIMIZATION_PLAYBOOK](OPTIMIZATION_PLAYBOOK.md) F05（P1 保持行为重构）、
> [WEB_UI_SPEC §7.1](../spec/WEB_UI_SPEC.md)（运行切换与闸门会话）。
> 本切片是 F05 的**第一步**：先提取“闸门会话判定”这一唯一协调关注点，不引入框架；
> 运行/Agent/计数、配置/目录浏览的渲染提取留待后续（见 §4 未完成项）。

| 项 | 内容 |
|---|---|
| 类型 | 保持行为重构（前端结构；不改协议/载荷/DOM id/事件绑定数量） |
| 基线提交 | `50383dc` |
| 唯一 owner | UI owner |
| 独立复核者 | 只读子代理（只在 `doc/audit/` 写一份验证报告） |
| 规格位置 | [WEB_UI_SPEC §7.1](../spec/WEB_UI_SPEC.md)、§7.2 |
| 允许修改 | `loop/web/`（新增 gate-session.js；改 app.js/index.html）、`loop/tests/`（新增 node 判据用例）、`doc/spec/WEB_UI_SPEC.md`（仅结构说明）、本计划、`doc/STATUS.md`、`doc/audit/` |
| 不修改 | 服务端协议、API 载荷、DOM id、闸门枚举来源、`kb/**`、冻结证据 |

## 1 问题

`app.js` 同时承担装配、渲染与会话判定；闸门草稿身份、提交互斥、选择代次等**判定**散落在渲染函数里
（`gateSessionKey/ensureDraft/submitGate/updateGateForm`），无法在无浏览器环境用受控断言固定，
也无法被第二个视图复用而不复制。

## 2 目标可观察行为（重构后不变）

1. 草稿身份仍为 `run_id + interrupt.id + gate + cycle`；身份不变时保留选项/actor/理由/焦点；
   身份改变或运行切换时清空，不继承旧选择。
2. 同一身份提交期间不再发第二次 POST；切走再返回仍保持提交中；拒绝后解除并保留输入。
3. 服务端撤回的选项不得继续提交；决策为空时提交被拒（前端提示，授权仍由服务端判定）。
4. DOM id、事件绑定、API 载荷、错误路径与重构前一致；不重建带输入的 DOM 子树。

## 3 不变量

1. **一个会话协调 owner**：`app.js` 仍持有 `state.gateDraft/gateSubmissions/selectionEpoch`；
   新模块只提供**纯函数**（输入→输出），不读全局、不写 DOM、不发起请求。
2. 判定唯一实现：`web/gate-session.js`；app.js 不得再写第二套 key/草稿/互斥判定。
3. 不引入框架、不引入构建步骤；`index.html` 按依赖顺序加载。
4. 浏览器交互验收仍是最终判据；本机无 playwright ⇒ 只能做 node 纯函数断言 + 静态审查，**不声称浏览器已验证**。

## 4 切片与验证

| 切片 | 内容 | 验证门 |
|---|---|---|
| F05-1 | 规格结构说明 + 本计划 | 文档门 |
| F05-2 | 红灯：`tests/test_gate_session.py`（node 驱动纯函数） | 先红（模块不存在） |
| F05-3 | 实现：`web/gate-session.js` + app.js 消费 + index.html | node 断言 + `node --check` + web smoke |
| F05-4 | 独立复核报告（`doc/audit/`，只读子代理） | 静态审查 + 纯函数实测；md5 记入 STATUS |
| F05-5 | STATUS §28 | 命令/输出逐字复制；浏览器未运行单列 |

**本切片未完成（明确登记）**：运行/Agent/计数渲染提取、配置/目录浏览提取（F05 后续步骤）；
它们需要浏览器特征集做等价性验收，本机不可运行，留待具备 UI 依赖的执行端。

## 5 回退

删除 `gate-session.js` 与用例，把纯函数判定内联回 app.js；不改协议。
