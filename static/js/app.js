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
