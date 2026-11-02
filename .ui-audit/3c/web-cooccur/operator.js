/* U1-c 操作者身份会话记忆（SPEC-REV-07，2026-10-24）：纯判定 + 可注入存储。
 *
 * 定位：单机单用户工具里 `human:<name>` 在闸门表单 / Agent 控制窗口重复手填，
 * 本模块把「上一次使用的合规操作者」存入 localStorage 并在**空/默认值**时预填。
 *
 * 边界（与 tests/test_operator_prefill.py 同源）：
 *   · 只记 `human:<非空白>`；model:*、空值一律不记；
 *   · 预填只填「空串或默认前缀 human:」，绝不覆盖任何已填值（含输入到一半的值）；
 *   · 存储不可用（localStorage 抛错/被禁/存值被手改成不合规）⇒ 静默降级为无记忆；
 *   · 本模块不参与任何提交校验——权威仍以 gates.json 的 human_signed 为准。
 */
"use strict";

(function (root) {
  var KEY = "loop.operator.name";

  function norm(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function isValid(value) {
    return /^human:\S+$/.test(value);
  }

  function defaultStorage() {
    try {
      return root.localStorage || null;
    } catch (e) {
      return null;
    }
  }

  function remember(value, storage) {
    var s = storage || defaultStorage();
    var v = norm(value);
    if (!s || !isValid(v)) return false;
    try {
      s.setItem(KEY, v);
      return true;
    } catch (e) {
      return false;
    }
  }

  function recall(storage) {
    var s = storage || defaultStorage();
    if (!s) return "";
    try {
      var v = norm(s.getItem(KEY));
      return isValid(v) ? v : "";
    } catch (e) {
      return "";
    }
  }

  function apply(current, remembered) {
    var c = typeof current === "string" ? current : "";
    var r = norm(remembered);
    if ((c === "" || c === "human:") && isValid(r)) return r;
    return c;
  }

  var Operator = {
    remember: remember,
    recall: recall,
    apply: apply
  };

  root.Operator = Operator;
  if (typeof module !== "undefined" && module.exports) module.exports = Operator;
})(typeof window !== "undefined" ? window : globalThis);
