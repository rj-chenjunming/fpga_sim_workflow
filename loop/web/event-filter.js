/* U5（SPEC-REV-07）：事件流客户端过滤的纯判定。
 *
 * 定位：只做筛选——kind 集合推导（首现顺序）、勾选切换、过滤应用。
 * 纯客户端过滤，清除过滤即还原全量；不改写事件对象（只筛引用），
 * 服务端投影与 F11 的分页结论不变。口径与 tests/test_event_filter.py 同源。
 */
"use strict";

(function (root) {
  function kindsOf(events) {
    var seen = Object.create(null);
    var out = [];
    var list = Array.isArray(events) ? events : [];
    for (var i = 0; i < list.length; i++) {
      var e = list[i];
      if (!e || !e.kind || seen[e.kind]) continue;
      seen[e.kind] = true;
      out.push(String(e.kind));
    }
    return out;
  }

  /* active: null = 不过滤（全部）；数组 = 仅勾选 kind。
     切换语义：null → 单选；已含 → 移除（移除到空 ⇒ 回到 null=全部）；未含 → 加入。 */
  function toggleKind(active, kind) {
    var k = String(kind);
    if (active === null || active === undefined) return [k];
    var has = active.indexOf(k) >= 0;
    var next = has ? active.filter(function (x) { return x !== k; }) : active.concat([k]);
    return next.length ? next : null;
  }

  function applyFilter(events, active) {
    var list = Array.isArray(events) ? events : [];
    if (active === null || active === undefined || !active.length) return list;
    var allow = Object.create(null);
    active.forEach(function (k) { allow[k] = true; });
    return list.filter(function (e) { return e && allow[e.kind]; });
  }

  var EventFilter = { kindsOf: kindsOf, toggleKind: toggleKind, applyFilter: applyFilter };

  root.EventFilter = EventFilter;
  if (typeof module !== "undefined" && module.exports) module.exports = EventFilter;
})(typeof window !== "undefined" ? window : globalThis);
