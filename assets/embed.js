// Grow the embedded demo to the height of its content, so the page scrolls once, not twice.
(function () {
  var frame = document.querySelector(".embed iframe");
  if (!frame) return;
  function fit() {
    try {
      var doc = frame.contentDocument;
      if (!doc || !doc.documentElement) return;
      frame.style.height = doc.documentElement.scrollHeight + "px";
    } catch (err) { /* keep the fixed fallback height */ }
  }
  frame.addEventListener("load", function () {
    fit();
    try {
      if (window.ResizeObserver) new ResizeObserver(fit).observe(frame.contentDocument.body);
    } catch (err) { /* fallback height stays */ }
  });
})();
