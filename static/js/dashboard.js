// Dashboard charts. Data comes from the server (json_script), colours from CSS tokens,
// so both charts follow light/dark mode. Re-rendered on the "themechange" event.
(function () {
  "use strict";
  if (typeof Chart === "undefined") return;

  var statusData = JSON.parse(document.getElementById("status-data").textContent);
  var progressData = JSON.parse(document.getElementById("progress-data").textContent);
  var charts = [];

  function token(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function render() {
    charts.forEach(function (c) { c.destroy(); });
    charts = [];

    var text = token("--text-muted");
    var surface = token("--surface");
    Chart.defaults.font.family = token("--font");
    Chart.defaults.color = text;

    var tooltip = {
      backgroundColor: token("--text"),
      titleColor: surface,
      bodyColor: surface,
      padding: 10,
      cornerRadius: 6,
      displayColors: false,
    };

    var statusCanvas = document.getElementById("statusChart");
    if (statusCanvas) {
      charts.push(new Chart(statusCanvas, {
        type: "doughnut",
        data: {
          labels: statusData.map(function (s) { return s.label; }),
          datasets: [{
            data: statusData.map(function (s) { return s.count; }),
            backgroundColor: statusData.map(function (s) { return token("--chart-" + s.slot); }),
            borderColor: surface,
            borderWidth: 2,
            hoverOffset: 4,
          }],
        },
        options: {
          cutout: "64%",
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },  // the HTML legend beside the chart carries labels and counts
            tooltip: Object.assign({}, tooltip, {
              callbacks: {
                label: function (ctx) {
                  var s = statusData[ctx.dataIndex];
                  return s.count + " task" + (s.count === 1 ? "" : "s") + " (" + s.pct + "%)";
                },
              },
            }),
          },
        },
      }));
    }

    var progressCanvas = document.getElementById("progressChart");
    if (progressCanvas) {
      charts.push(new Chart(progressCanvas, {
        type: "bar",
        data: {
          labels: progressData.map(function (p) { return p.name; }),
          datasets: [{
            data: progressData.map(function (p) { return p.pct; }),
            backgroundColor: token("--chart-bar"),
            borderRadius: 4,
            borderSkipped: "start",
            maxBarThickness: 18,
          }],
        },
        options: {
          indexAxis: "y",
          maintainAspectRatio: false,
          scales: {
            x: {
              min: 0,
              max: 100,
              grid: { color: token("--chart-grid") },
              border: { display: false },
              ticks: { callback: function (v) { return v + "%"; } },
            },
            y: { grid: { display: false }, border: { display: false } },
          },
          plugins: {
            legend: { display: false },
            tooltip: Object.assign({}, tooltip, {
              callbacks: {
                label: function (ctx) {
                  var p = progressData[ctx.dataIndex];
                  return p.pct + "% complete (" + p.done + " of " + p.total + " tasks)";
                },
              },
            }),
          },
        },
      }));
    }
  }

  // Wait for the web font so axis labels are measured with the font they are drawn in.
  (document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve()).then(render);
  document.addEventListener("themechange", render);
})();
