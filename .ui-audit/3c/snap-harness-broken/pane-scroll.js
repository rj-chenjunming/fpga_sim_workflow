/* 闸门视图双栏独立滚动的判定（WEB_UI_SPEC §5「材料/操作双栏独立滚动」/ §10 A11，2026-10-29）。
 *
 * 纯函数：不读 DOM、不写全局、不发请求。重绘 owner 仍是 app.js
 * （持有 DOM、包两个渲染入口、回填 scrollTop）；本文件只回答三个可判定问题：
 *   ① 这一屏的身份是什么（run_id + 闸门 + 轮次）；
 *   ② 重绘后该恢复到哪里（同身份 ⇒ 上次位置；否则回顶）；
 *   ③ 是否真的溢出（决定要不要给 Tab 停靠点）。
 * 理由是「每 1.5 s 一次全量重绘」（§9）：只加 CSS 而不保持滚动位置，人每 1.5 s 被滚回顶部，
 * 功能不成立；而判据若散在渲染分支里，会出现第二套口径（红线 8）。
 */
(function (root) {
  "use strict";

  /* 身份三元组：三者任一变化都是新屏幕（切运行 / 切闸门 / 切轮次）。
     `null` 与 `0` 必须区分：未开始（无轮次）不得套用上一轮的位置。 */
  function identity(runId, gate, cycle) {
    var norm = function (value) {
      return value === null || value === undefined ? null : String(value);
    };
    return JSON.stringify([norm(runId), norm(gate), norm(cycle)]);
  }

  function normalizeTop(top) {
    var value = Number(top);
    if (!isFinite(value) || value <= 0) return 0;
    return Math.floor(value);
  }

  /* 重绘后应回填的 scrollTop：身份相同才保持，否则回顶（0）。
     入参 `saved` 形如 {identity, top}；缺失/脏值一律 0，不回落到「上次的另一个身份」。 */
  function restore(saved, nextIdentity) {
    if (!saved || typeof saved !== "object") return 0;
    if (saved.identity === null || saved.identity === undefined) return 0;
    if (nextIdentity === null || nextIdentity === undefined) return 0;
    if (String(saved.identity) !== String(nextIdentity)) return 0;
    return normalizeTop(saved.top);
  }

  /* 实际溢出（含 1px 容差：亚像素/边框取整会让 scrollHeight 比 clientHeight 大 1）。
     不溢出就不该产生 Tab 停靠点（§5 第 4 条）。 */
  function isScrollable(scrollHeight, clientHeight) {
    /* null/undefined 不是数字：面板隐藏时 clientHeight 为 0、度量缺失时是 null，
       都不能据此断言「可滚动」而给 Tab 停靠点（`Number(null)` 会变成 0，必须显式挡掉）。 */
    if (scrollHeight === null || scrollHeight === undefined ||
        clientHeight === null || clientHeight === undefined) return false;
    var outer = Number(scrollHeight);
    var inner = Number(clientHeight);
    if (!isFinite(outer) || !isFinite(inner)) return false;
    return outer > inner + 1;
  }

  var api = {identity: identity, restore: restore, isScrollable: isScrollable};
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (root) root.PaneScroll = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
