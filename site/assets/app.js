/* PMHostX 文献周报 · 交互
   由 scripts/build_page.py 原样拷进 site/assets/。

   页面内容全部由 Python 生成在 HTML 里，这里只做三件事：
   1. 过期提示：数据截至哪天由构建时写进页面，「今天」只有浏览器知道——
      所以漏跑能不能被看出来，取决于这段在访问时现算，而不是构建时算。
   2. 周次下拉跳转。
   3. 筛选（主题 × 标本 × 只看必读 × 搜索），计数随其他条件联动。 */
(function () {
  "use strict";
  var STALE_DAYS = 8;

  // ---------- 1. 过期提示
  var stale = document.getElementById("stale");
  if (stale) {
    var last = stale.getAttribute("data-last");
    var days = Math.floor((Date.now() - new Date(last + "T00:00:00+08:00").getTime()) / 864e5);
    if (days > STALE_DAYS) {
      stale.firstElementChild.innerHTML =
        "<b>数据截至 " + last + "，已 " + days + " 天没有新批次。</b>" +
        "自动任务每周一 00:00 运行；超过 " + STALE_DAYS + " 天没有新批次，说明至少漏跑了一次，" +
        "不代表这段时间没有新文献。";
      stale.hidden = false;
    }
  }

  // ---------- 2. 周次下拉
  var pick = document.getElementById("pick");
  if (pick) {
    pick.addEventListener("change", function () {
      if (pick.value) location.href = pick.value;
    });
  }

  // ---------- 3. 筛选
  var tools = document.getElementById("tools");
  if (!tools) return;
  var cards = [].slice.call(document.querySelectorAll(".cb"));
  var sections = [].slice.call(document.querySelectorAll(".sec"));
  var gOpts = [].slice.call(tools.querySelectorAll("[data-g]"));
  var spOpts = [].slice.call(tools.querySelectorAll("[data-sp]"));
  var must = document.getElementById("must");
  var q = document.getElementById("q");
  var clear = document.getElementById("clear");
  var nomatch = document.getElementById("nomatch");
  var mapq = document.getElementById("mapq");
  var S = { g: "0", sp: "", must: false, q: "", raw: "" };  // q 用于匹配（小写），raw 保留原样用于显示

  var items = cards.map(function (el) {
    var sp = (el.getAttribute("data-sp") || "").split(" ").filter(Boolean);
    return {
      el: el,
      g: el.getAttribute("data-g"),
      sp: sp.length ? sp : ["none"],
      must: el.getAttribute("data-must") === "1",
      text: el.textContent.toLowerCase()
    };
  });

  function passes(it, skip) {
    if (S.must && !it.must) return false;
    if (S.q && it.text.indexOf(S.q) < 0) return false;
    if (skip !== "g" && S.g !== "0" && it.g !== S.g) return false;
    if (skip !== "sp" && S.sp && it.sp.indexOf(S.sp) < 0) return false;
    return true;
  }

  function setCount(btn, n) {
    btn.querySelector("small").textContent = n;
    var on = btn.getAttribute("aria-pressed") === "true";
    btn.disabled = !on && n === 0;
  }

  function apply() {
    var shown = 0;
    items.forEach(function (it) {
      var ok = passes(it);
      it.el.hidden = !ok;
      if (ok) shown++;
    });
    sections.forEach(function (s) {
      s.hidden = !s.querySelector(".cb:not([hidden])");
    });
    var forG = items.filter(function (it) { return passes(it, "g"); });
    var forSp = items.filter(function (it) { return passes(it, "sp"); });
    gOpts.forEach(function (b) {
      var v = b.getAttribute("data-g");
      b.setAttribute("aria-pressed", String(v === S.g));
      setCount(b, v === "0" ? forG.length : forG.filter(function (it) { return it.g === v; }).length);
    });
    spOpts.forEach(function (b) {
      var v = b.getAttribute("data-sp");
      b.setAttribute("aria-pressed", String(v === S.sp));
      setCount(b, v === "" ? forSp.length : forSp.filter(function (it) { return it.sp.indexOf(v) >= 0; }).length);
    });
    if (must) must.setAttribute("aria-pressed", String(S.must));
    if (clear) clear.hidden = !(S.g !== "0" || S.sp || S.must || S.q);
    if (nomatch) nomatch.hidden = shown > 0 || !items.length;
    if (mapq) {
      mapq.hidden = !S.q;
      mapq.href = mapq.getAttribute("data-base") + "?q=" + encodeURIComponent(S.raw);
      mapq.textContent = "在累积地图里搜「" + S.raw + "」";
    }
  }

  gOpts.forEach(function (b) {
    b.addEventListener("click", function () { S.g = b.getAttribute("data-g"); apply(); });
  });
  spOpts.forEach(function (b) {
    b.addEventListener("click", function () { S.sp = b.getAttribute("data-sp"); apply(); });
  });
  if (must) must.addEventListener("click", function () { S.must = !S.must; apply(); });
  var timer;
  if (q) q.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () { S.raw = q.value.trim(); S.q = S.raw.toLowerCase(); apply(); }, 120);
  });
  [].slice.call(document.querySelectorAll("[data-clear]")).forEach(function (b) {
    b.addEventListener("click", function () {
      S = { g: "0", sp: "", must: false, q: "", raw: "" };
      if (q) q.value = "";
      apply();
    });
  });

  // 从周页「在累积地图里搜」跳过来时带着 ?q=
  var m = /[?&]q=([^&]*)/.exec(location.search);
  if (m && q) {
    q.value = decodeURIComponent(m[1].replace(/\+/g, " "));
    S.raw = q.value.trim();
    S.q = S.raw.toLowerCase();
  }
  apply();
})();
