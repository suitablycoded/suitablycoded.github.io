// Small motion touches for every page. All of them are skipped when the visitor has asked for
// reduced motion, and the page reads the same without this script.
(function () {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  var hover = window.matchMedia("(hover: hover)").matches;

  // 1. Screenshots tilt in 3D under the pointer.
  if (hover) {
    document.querySelectorAll(".shot img").forEach(function (img) {
      img.addEventListener("pointermove", function (ev) {
        var r = img.getBoundingClientRect();
        var x = (ev.clientX - r.left) / r.width - 0.5, y = (ev.clientY - r.top) / r.height - 0.5;
        img.style.transform = "perspective(1000px) rotateY(" + x * 6 + "deg) rotateX(" + -y * 6 + "deg) scale(1.01)";
      });
      img.addEventListener("pointerleave", function () { img.style.transform = ""; });
    });
  }

  if (!("IntersectionObserver" in window)) return;

  // 2. Figures count up when they scroll into view ("600", "364.9 min", "100%").
  var counted = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      counted.unobserve(e.target);
      var el = e.target, text = el.textContent;
      var m = text.match(/-?[\d,]*\.?\d+/);
      if (!m) return;
      var target = parseFloat(m[0].replace(/,/g, ""));
      var decimals = (m[0].split(".")[1] || "").length;
      var commas = m[0].indexOf(",") >= 0;
      var t0 = null;
      function step(ts) {
        if (t0 === null) t0 = ts;
        var p = Math.min(1, (ts - t0) / 1100), eased = 1 - Math.pow(1 - p, 3);
        var v = (target * eased).toFixed(decimals);
        if (commas) v = Number(v).toLocaleString("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
        el.textContent = text.replace(m[0], v);
        if (p < 1) requestAnimationFrame(step); else el.textContent = text;
      }
      requestAnimationFrame(step);
    });
  }, { threshold: 0.6 });
  document.querySelectorAll(".figures dd").forEach(function (dd) { counted.observe(dd); });

  // 3. Steps and sections slide in one after another as they scroll into view.
  var items = document.querySelectorAll(".steps li");
  if (items.length) {
    document.documentElement.classList.add("reveal-on");
    var shown = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        shown.unobserve(e.target);
        e.target.classList.add("in");
      });
    }, { threshold: 0.3 });
    items.forEach(function (li, i) { li.style.transitionDelay = (i % 4) * 0.12 + "s"; shown.observe(li); });
  }
})();
