// TaskFlow: small progressive enhancements. Every feature also works without JS.
(function () {
  "use strict";

  // Auto-submit forms whose <select data-autosubmit> changes (quick status update).
  document.addEventListener("change", function (event) {
    var el = event.target;
    if (el.matches && el.matches("select[data-autosubmit]")) {
      el.form.submit();
    }
  });
})();

(function () {
  "use strict";
  var root = document.documentElement;

  // Dark mode toggle: persists the choice and tells charts to redraw.
  document.addEventListener("click", function (event) {
    var toggle = event.target.closest("[data-theme-toggle]");
    if (!toggle) return;
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("taskflow-theme", next); } catch (e) {}
    document.dispatchEvent(new CustomEvent("themechange", { detail: next }));
  });

  // Mobile navigation drawer.
  var sidebar = document.getElementById("sidebar");
  var backdrop = document.querySelector(".sidebar-backdrop");
  var navToggle = document.querySelector("[data-nav-toggle]");
  function setNav(open) {
    if (!sidebar) return;
    sidebar.classList.toggle("open", open);
    if (backdrop) backdrop.hidden = !open;
    if (navToggle) navToggle.setAttribute("aria-expanded", String(open));
  }
  document.addEventListener("click", function (event) {
    if (event.target.closest("[data-nav-toggle]")) setNav(!sidebar.classList.contains("open"));
    else if (event.target.closest("[data-nav-close]")) setNav(false);
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") setNav(false);
  });

  // Flash messages: dismiss on click, success/info fade out on their own.
  document.addEventListener("click", function (event) {
    var close = event.target.closest("[data-dismiss]");
    if (close) close.parentElement.remove();
  });
  document.querySelectorAll(".message-success, .message-info").forEach(function (el) {
    setTimeout(function () { el.classList.add("fade"); }, 5000);
    setTimeout(function () { el.remove(); }, 5600);
  });

  // Confirm before destructive inline actions (e.g. removing a prerequisite).
  document.addEventListener("submit", function (event) {
    var message = event.target.getAttribute("data-confirm");
    if (message && !window.confirm(message)) event.preventDefault();
  });
})();
