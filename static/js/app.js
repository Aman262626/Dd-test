/* WiFi Scanner Pro - Frontend Application */

(function () {
  "use strict";

  // State
  let networks = [];
  let scanHistory = [];
  let autoRefreshTimer = null;
  let charts = {};

  // DOM refs
  const scanBtn = document.getElementById("scanBtn");
  const searchInput = document.getElementById("searchInput");
  const bandFilter = document.getElementById("bandFilter");
  const encFilter = document.getElementById("encFilter");
  const sortBy = document.getElementById("sortBy");
  const autoRefreshCheckbox = document.getElementById("autoRefresh");
  const refreshIntervalSelect = document.getElementById("refreshInterval");
  const networkGrid = document.getElementById("networkGrid");
  const modal = document.getElementById("networkModal");
  const modalClose = document.getElementById("modalClose");
  const themeToggle = document.getElementById("themeToggle");
  const exportCsv = document.getElementById("exportCsv");
  const exportJson = document.getElementById("exportJson");
  const signalTrackSelect = document.getElementById("signalTrackSelect");

  // Initialize
  function init() {
    scanBtn.addEventListener("click", performScan);
    searchInput.addEventListener("input", renderNetworks);
    bandFilter.addEventListener("change", renderNetworks);
    encFilter.addEventListener("change", renderNetworks);
    sortBy.addEventListener("change", renderNetworks);
    autoRefreshCheckbox.addEventListener("change", toggleAutoRefresh);
    refreshIntervalSelect.addEventListener("change", toggleAutoRefresh);
    modalClose.addEventListener("click", closeModal);
    modal.addEventListener("click", function (e) {
      if (e.target === modal) closeModal();
    });
    themeToggle.addEventListener("click", toggleTheme);
    exportCsv.addEventListener("click", () => exportData("csv"));
    exportJson.addEventListener("click", () => exportData("json"));
    signalTrackSelect.addEventListener("change", loadSignalTrack);

    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });

    // Load saved theme
    const saved = localStorage.getItem("wifiScannerTheme");
    if (saved) document.documentElement.setAttribute("data-theme", saved);

    initCharts();
  }

  // Theme
  function toggleTheme() {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("wifiScannerTheme", next);
    updateChartsTheme();
  }

  // Tabs
  function switchTab(tabId) {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));
    document.querySelector(`[data-tab="${tabId}"]`).classList.add("active");
    document.getElementById(`tab-${tabId}`).classList.add("active");
  }

  // Scan
  async function performScan() {
    scanBtn.classList.add("scanning");
    scanBtn.querySelector("span").textContent = "Scanning...";
    showToast("Scanning for networks...", "info");

    try {
      const res = await fetch("/api/scan");
      const data = await res.json();

      if (data.status === "success") {
        networks = data.networks;
        updateStats(data.summary);
        renderNetworks();
        updateCharts(data);
        updateSignalTrackOptions();
        loadHistory();
        loadChannelAnalysis();
        showToast(`Found ${networks.length} networks`, "success");
      } else {
        showToast("Scan failed", "error");
      }
    } catch (err) {
      showToast("Error: " + err.message, "error");
    } finally {
      scanBtn.classList.remove("scanning");
      scanBtn.querySelector("span").textContent = "Scan Networks";
    }
  }

  // Stats
  function updateStats(summary) {
    document.getElementById("totalNetworks").textContent = summary.total;
    document.getElementById("securedNetworks").textContent = summary.secured;
    document.getElementById("openNetworks").textContent = summary.open;
    document.getElementById("avgSignal").textContent = summary.avg_signal;
    document.getElementById("band24Count").textContent = summary.band_2ghz;
    document.getElementById("band5Count").textContent = summary.band_5ghz;
  }

  // Signal helpers
  function getSignalClass(dbm) {
    if (dbm >= -40) return "excellent";
    if (dbm >= -55) return "good";
    if (dbm >= -70) return "fair";
    if (dbm >= -80) return "weak";
    return "poor";
  }

  function getSignalLabel(dbm) {
    if (dbm >= -40) return "Excellent";
    if (dbm >= -55) return "Good";
    if (dbm >= -70) return "Fair";
    if (dbm >= -80) return "Weak";
    return "Poor";
  }

  function getSignalColor(dbm) {
    const cls = getSignalClass(dbm);
    const map = {
      excellent: "#22c55e",
      good: "#84cc16",
      fair: "#f59e0b",
      weak: "#f97316",
      poor: "#ef4444",
    };
    return map[cls];
  }

  function getSignalBars(dbm) {
    if (dbm >= -40) return 4;
    if (dbm >= -55) return 3;
    if (dbm >= -70) return 2;
    if (dbm >= -80) return 1;
    return 0;
  }

  function getEncClass(enc) {
    const lower = enc.toLowerCase();
    if (lower === "open") return "enc-open";
    if (lower.includes("wpa3")) return "enc-wpa3";
    if (lower.includes("wpa2")) return "enc-wpa2";
    return "enc-wpa";
  }

  // Render
  function renderNetworks() {
    let filtered = [...networks];

    // Search
    const query = searchInput.value.toLowerCase();
    if (query) {
      filtered = filtered.filter(
        (n) =>
          n.ssid.toLowerCase().includes(query) ||
          n.bssid.toLowerCase().includes(query) ||
          n.vendor.toLowerCase().includes(query)
      );
    }

    // Band filter
    const band = bandFilter.value;
    if (band !== "all") {
      filtered = filtered.filter((n) => n.band === band);
    }

    // Encryption filter
    const enc = encFilter.value;
    if (enc !== "all") {
      filtered = filtered.filter((n) => n.encryption === enc);
    }

    // Sort
    const sort = sortBy.value;
    filtered.sort((a, b) => {
      switch (sort) {
        case "signal":
          return b.signal_strength - a.signal_strength;
        case "ssid":
          return a.ssid.localeCompare(b.ssid);
        case "channel":
          return a.channel - b.channel;
        case "encryption":
          return a.encryption.localeCompare(b.encryption);
        default:
          return 0;
      }
    });

    if (filtered.length === 0) {
      networkGrid.innerHTML = `
        <div class="empty-state">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="64" height="64">
            <path d="M5 12.55a11 11 0 0 1 14.08 0"/>
            <path d="M1.42 9a16 16 0 0 1 21.16 0"/>
            <path d="M8.53 16.11a6 6 0 0 1 6.95 0"/>
            <circle cx="12" cy="20" r="1"/>
          </svg>
          <h3>${networks.length === 0 ? "No Networks Scanned" : "No Matching Networks"}</h3>
          <p>${networks.length === 0 ? 'Click "Scan Networks" to discover nearby WiFi networks' : "Try adjusting your filters"}</p>
        </div>`;
      return;
    }

    networkGrid.innerHTML = filtered.map((n) => createNetworkCard(n)).join("");

    // Click handlers
    networkGrid.querySelectorAll(".network-card").forEach((card) => {
      card.addEventListener("click", () => {
        const bssid = card.dataset.bssid;
        const net = networks.find((n) => n.bssid === bssid);
        if (net) showNetworkDetail(net);
      });
    });
  }

  function createNetworkCard(n) {
    const sigClass = getSignalClass(n.signal_strength);
    const bars = getSignalBars(n.signal_strength);
    const sigColor = getSignalColor(n.signal_strength);
    const encClass = getEncClass(n.encryption);

    let barsHtml = "";
    for (let i = 1; i <= 4; i++) {
      barsHtml += `<div class="signal-bar bar-${i} ${i <= bars ? "active" : ""}"></div>`;
    }

    return `
      <div class="network-card signal-${sigClass}" data-bssid="${n.bssid}">
        <div class="net-header">
          <span class="net-ssid" title="${n.ssid}">${escapeHtml(n.ssid)}</span>
          <span class="net-signal-badge ${sigClass}">
            <span class="signal-bars">${barsHtml}</span>
            ${n.signal_strength} dBm
          </span>
        </div>
        <div class="net-details">
          <div class="net-detail">
            <span class="net-detail-label">BSSID</span>
            <span class="net-detail-value">${n.bssid}</span>
          </div>
          <div class="net-detail">
            <span class="net-detail-label">Channel</span>
            <span class="net-detail-value">Ch ${n.channel}</span>
          </div>
          <div class="net-detail">
            <span class="net-detail-label">Frequency</span>
            <span class="net-detail-value">${n.frequency}</span>
          </div>
          <div class="net-detail">
            <span class="net-detail-label">Speed</span>
            <span class="net-detail-value">${n.speed}</span>
          </div>
        </div>
        <div class="net-signal-bar">
          <div class="net-signal-fill" style="width: ${n.signal_quality}%; background: ${sigColor};"></div>
        </div>
        <div class="net-tags">
          <span class="net-tag ${encClass}">${n.encryption}</span>
          <span class="net-tag band">${n.band}</span>
          ${n.ssid === "<Hidden>" ? '<span class="net-tag hidden">Hidden</span>' : ""}
        </div>
      </div>`;
  }

  // Modal
  function showNetworkDetail(n) {
    const sigClass = getSignalClass(n.signal_strength);
    const sigColor = getSignalColor(n.signal_strength);

    document.getElementById("modalTitle").textContent = n.ssid;
    document.getElementById("modalBody").innerHTML = `
      <div class="modal-detail-grid">
        <div class="modal-detail">
          <span class="modal-detail-label">SSID</span>
          <span class="modal-detail-value">${escapeHtml(n.ssid)}</span>
        </div>
        <div class="modal-detail">
          <span class="modal-detail-label">BSSID</span>
          <span class="modal-detail-value">${n.bssid}</span>
        </div>
        <div class="modal-detail">
          <span class="modal-detail-label">Signal Strength</span>
          <span class="modal-detail-value">${n.signal_strength} dBm (${getSignalLabel(n.signal_strength)})</span>
        </div>
        <div class="modal-detail">
          <span class="modal-detail-label">Signal Quality</span>
          <span class="modal-detail-value">${n.signal_quality}%</span>
        </div>
        <div class="modal-detail">
          <span class="modal-detail-label">Channel</span>
          <span class="modal-detail-value">${n.channel}</span>
        </div>
        <div class="modal-detail">
          <span class="modal-detail-label">Frequency</span>
          <span class="modal-detail-value">${n.frequency}</span>
        </div>
        <div class="modal-detail">
          <span class="modal-detail-label">Band</span>
          <span class="modal-detail-value">${n.band}</span>
        </div>
        <div class="modal-detail">
          <span class="modal-detail-label">Encryption</span>
          <span class="modal-detail-value">${n.encryption}</span>
        </div>
        <div class="modal-detail">
          <span class="modal-detail-label">Mode</span>
          <span class="modal-detail-value">${n.mode}</span>
        </div>
        <div class="modal-detail">
          <span class="modal-detail-label">Speed</span>
          <span class="modal-detail-value">${n.speed}</span>
        </div>
        <div class="modal-detail">
          <span class="modal-detail-label">Vendor</span>
          <span class="modal-detail-value">${n.vendor}</span>
        </div>
        <div class="modal-detail">
          <span class="modal-detail-label">Last Seen</span>
          <span class="modal-detail-value">${new Date(n.last_seen).toLocaleString()}</span>
        </div>
      </div>
      <div class="modal-signal-section">
        <h4>Signal Strength</h4>
        <div class="modal-signal-bar">
          <div class="modal-signal-fill" style="width: ${n.signal_quality}%; background: ${sigColor};"></div>
        </div>
        <div class="modal-signal-labels">
          <span>-90 dBm (Poor)</span>
          <span>${n.signal_strength} dBm</span>
          <span>-30 dBm (Excellent)</span>
        </div>
      </div>`;

    modal.classList.add("active");
  }

  function closeModal() {
    modal.classList.remove("active");
  }

  // Auto-refresh
  function toggleAutoRefresh() {
    if (autoRefreshTimer) {
      clearInterval(autoRefreshTimer);
      autoRefreshTimer = null;
    }

    if (autoRefreshCheckbox.checked) {
      const interval = parseInt(refreshIntervalSelect.value) * 1000;
      performScan();
      autoRefreshTimer = setInterval(performScan, interval);
      showToast(`Auto-refresh: every ${refreshIntervalSelect.value}s`, "info");
    }
  }

  // Export
  function exportData(format) {
    if (networks.length === 0) {
      showToast("No data to export. Run a scan first.", "error");
      return;
    }
    window.open(`/api/export/${format}`, "_blank");
    showToast(`Downloading ${format.toUpperCase()} file...`, "success");
  }

  // History
  async function loadHistory() {
    try {
      const res = await fetch("/api/history?limit=50");
      const data = await res.json();
      scanHistory = data.history || [];
      renderHistoryTable();
      updateHistoryChart();
    } catch (err) {
      console.error("Failed to load history:", err);
    }
  }

  function renderHistoryTable() {
    const tbody = document.querySelector("#historyTable tbody");
    tbody.innerHTML = scanHistory
      .map(
        (entry, i) => `
      <tr>
        <td>${i + 1}</td>
        <td>${new Date(entry.timestamp).toLocaleString()}</td>
        <td>${entry.network_count}</td>
      </tr>`
      )
      .join("");
  }

  // Signal tracking
  function updateSignalTrackOptions() {
    signalTrackSelect.innerHTML = '<option value="">-- Select Network --</option>';
    const unique = {};
    networks.forEach((n) => {
      if (!unique[n.bssid]) {
        unique[n.bssid] = n.ssid;
      }
    });

    Object.entries(unique).forEach(([bssid, ssid]) => {
      const opt = document.createElement("option");
      opt.value = bssid;
      opt.textContent = `${ssid} (${bssid})`;
      signalTrackSelect.appendChild(opt);
    });
  }

  async function loadSignalTrack() {
    const bssid = signalTrackSelect.value;
    if (!bssid) return;

    try {
      const res = await fetch(`/api/network/${encodeURIComponent(bssid)}/history`);
      const data = await res.json();
      updateSignalTrackChart(data.history, bssid);
    } catch (err) {
      console.error("Failed to load signal track:", err);
    }
  }

  // Channel analysis
  async function loadChannelAnalysis() {
    try {
      const res = await fetch("/api/channel-analysis");
      const data = await res.json();

      if (data.status === "success") {
        updateChannelCharts(data);
        updateChannelRecommendation(data);
      }
    } catch (err) {
      console.error("Failed to load channel analysis:", err);
    }
  }

  function updateChannelRecommendation(data) {
    const container = document.querySelector("#channelRecommendation .recommendation-content");
    container.innerHTML = `
      <div class="rec-item">
        <span class="rec-badge">2.4 GHz</span>
        <span>Recommended Channel: <strong>${data.recommended_2ghz || "N/A"}</strong> (least congested)</span>
      </div>
      <div class="rec-item">
        <span class="rec-badge">5 GHz</span>
        <span>Recommended Channel: <strong>${data.recommended_5ghz || "N/A"}</strong> (least congested)</span>
      </div>`;
  }

  // Charts
  function getChartDefaults() {
    const style = getComputedStyle(document.documentElement);
    return {
      textColor: style.getPropertyValue("--text-secondary").trim(),
      gridColor: style.getPropertyValue("--chart-grid").trim(),
      bgCard: style.getPropertyValue("--bg-card").trim(),
    };
  }

  function initCharts() {
    const defaults = getChartDefaults();
    Chart.defaults.color = defaults.textColor;
    Chart.defaults.borderColor = defaults.gridColor;
    Chart.defaults.font.family = "'Inter', sans-serif";
    Chart.defaults.font.size = 12;

    // Signal distribution
    charts.signal = new Chart(document.getElementById("signalChart"), {
      type: "bar",
      data: { labels: [], datasets: [{ label: "Signal (dBm)", data: [], backgroundColor: [] }] },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          y: { beginAtZero: false, title: { display: true, text: "Signal (dBm)" } },
          x: { ticks: { maxRotation: 45 } },
        },
      },
    });

    // Encryption pie
    charts.encryption = new Chart(document.getElementById("encryptionChart"), {
      type: "doughnut",
      data: {
        labels: [],
        datasets: [{ data: [], backgroundColor: ["#22c55e", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6"] }],
      },
      options: { responsive: true, plugins: { legend: { position: "bottom" } } },
    });

    // Band pie
    charts.band = new Chart(document.getElementById("bandChart"), {
      type: "doughnut",
      data: {
        labels: [],
        datasets: [{ data: [], backgroundColor: ["#06b6d4", "#8b5cf6", "#22c55e"] }],
      },
      options: { responsive: true, plugins: { legend: { position: "bottom" } } },
    });

    // Vendor bar
    charts.vendor = new Chart(document.getElementById("vendorChart"), {
      type: "bar",
      data: {
        labels: [],
        datasets: [{ label: "Count", data: [], backgroundColor: "#3b82f6" }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        plugins: { legend: { display: false } },
      },
    });

    // Channel 2.4
    charts.channel24 = new Chart(document.getElementById("channel24Chart"), {
      type: "bar",
      data: {
        labels: Array.from({ length: 13 }, (_, i) => `Ch ${i + 1}`),
        datasets: [{ label: "Networks", data: new Array(13).fill(0), backgroundColor: "#06b6d4" }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
      },
    });

    // Channel 5
    charts.channel5 = new Chart(document.getElementById("channel5Chart"), {
      type: "bar",
      data: {
        labels: [],
        datasets: [{ label: "Networks", data: [], backgroundColor: "#8b5cf6" }],
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
      },
    });

    // History
    charts.history = new Chart(document.getElementById("historyChart"), {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Networks Found",
            data: [],
            borderColor: "#3b82f6",
            backgroundColor: "rgba(59,130,246,0.1)",
            fill: true,
            tension: 0.3,
          },
        ],
      },
      options: {
        responsive: true,
        scales: { y: { beginAtZero: true, ticks: { stepSize: 1 } } },
      },
    });

    // Signal track
    charts.signalTrack = new Chart(document.getElementById("signalTrackChart"), {
      type: "line",
      data: {
        labels: [],
        datasets: [
          {
            label: "Signal (dBm)",
            data: [],
            borderColor: "#22c55e",
            backgroundColor: "rgba(34,197,94,0.1)",
            fill: true,
            tension: 0.3,
          },
        ],
      },
      options: {
        responsive: true,
        scales: {
          y: { title: { display: true, text: "dBm" } },
        },
      },
    });
  }

  function updateCharts(data) {
    const nets = data.networks;
    const summary = data.summary;

    // Signal chart
    const sorted = [...nets].sort((a, b) => b.signal_strength - a.signal_strength);
    charts.signal.data.labels = sorted.map((n) => n.ssid.substring(0, 15));
    charts.signal.data.datasets[0].data = sorted.map((n) => n.signal_strength);
    charts.signal.data.datasets[0].backgroundColor = sorted.map((n) => getSignalColor(n.signal_strength));
    charts.signal.update();

    // Encryption chart
    const encTypes = summary.encryption_types;
    charts.encryption.data.labels = Object.keys(encTypes);
    charts.encryption.data.datasets[0].data = Object.values(encTypes);
    charts.encryption.update();

    // Band chart
    const bandData = {};
    if (summary.band_2ghz > 0) bandData["2.4 GHz"] = summary.band_2ghz;
    if (summary.band_5ghz > 0) bandData["5 GHz"] = summary.band_5ghz;
    if (summary.band_6ghz > 0) bandData["6 GHz"] = summary.band_6ghz;
    charts.band.data.labels = Object.keys(bandData);
    charts.band.data.datasets[0].data = Object.values(bandData);
    charts.band.update();

    // Vendor chart
    const vendors = Object.entries(summary.vendors)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);
    charts.vendor.data.labels = vendors.map((v) => v[0]);
    charts.vendor.data.datasets[0].data = vendors.map((v) => v[1]);
    charts.vendor.update();
  }

  function updateChannelCharts(data) {
    // 2.4 GHz
    const ch24Data = new Array(13).fill(0);
    Object.entries(data.channels_2ghz || {}).forEach(([ch, nets]) => {
      const idx = parseInt(ch) - 1;
      if (idx >= 0 && idx < 13) ch24Data[idx] = nets.length;
    });
    charts.channel24.data.datasets[0].data = ch24Data;
    charts.channel24.update();

    // 5 GHz
    const ch5 = data.channels_5ghz || {};
    const channels5 = Object.keys(ch5).sort((a, b) => parseInt(a) - parseInt(b));
    charts.channel5.data.labels = channels5.map((c) => `Ch ${c}`);
    charts.channel5.data.datasets[0].data = channels5.map((c) => ch5[c].length);
    charts.channel5.update();
  }

  function updateHistoryChart() {
    const labels = scanHistory.map((e) => {
      const d = new Date(e.timestamp);
      return d.toLocaleTimeString();
    });
    charts.history.data.labels = labels;
    charts.history.data.datasets[0].data = scanHistory.map((e) => e.network_count);
    charts.history.update();
  }

  function updateSignalTrackChart(history, bssid) {
    const labels = history.map((e) => {
      const d = new Date(e.timestamp);
      return d.toLocaleTimeString();
    });
    charts.signalTrack.data.labels = labels;
    charts.signalTrack.data.datasets[0].data = history.map((e) => e.signal_strength);
    charts.signalTrack.update();
  }

  function updateChartsTheme() {
    const defaults = getChartDefaults();
    Chart.defaults.color = defaults.textColor;
    Chart.defaults.borderColor = defaults.gridColor;

    Object.values(charts).forEach((chart) => {
      chart.options.scales &&
        Object.values(chart.options.scales).forEach((scale) => {
          if (scale.ticks) scale.ticks.color = defaults.textColor;
          if (scale.title) scale.title.color = defaults.textColor;
          scale.grid = scale.grid || {};
          scale.grid.color = defaults.gridColor;
        });
      chart.update();
    });
  }

  // Toast
  function showToast(message, type) {
    const container = document.getElementById("toastContainer");
    const toast = document.createElement("div");
    toast.className = `toast ${type || "info"}`;
    toast.textContent = message;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.animation = "slideOut 0.3s ease forwards";
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  // Utility
  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  // === Stress Test ===
  function initStressTest() {
    const runFullBtn = document.getElementById("runFullStress");
    const detectBtn = document.getElementById("detectGateway");

    if (runFullBtn) runFullBtn.addEventListener("click", runFullStressTest);
    if (detectBtn) detectBtn.addEventListener("click", detectGateway);

    document.querySelectorAll(".run-test-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        runIndividualTest(btn.dataset.test);
      });
    });
  }

  async function detectGateway() {
    try {
      const res = await fetch("/api/stress/gateway");
      const data = await res.json();
      if (data.status === "success") {
        document.getElementById("stressHost").value = data.gateway;
        showToast("Gateway detected: " + data.gateway, "success");
      }
    } catch (err) {
      showToast("Failed to detect gateway", "error");
    }
  }

  function getStressHost() {
    return document.getElementById("stressHost").value.trim() || null;
  }

  async function runIndividualTest(testType) {
    const host = getStressHost();
    const param = host ? `?host=${encodeURIComponent(host)}` : "";
    const cardMap = {
      ping: "pingCard",
      "rapid-ping": "rapidPingCard",
      connections: "connCard",
      "latency-load": "latencyCard",
      bandwidth: "bandwidthCard",
    };

    const cardId = cardMap[testType];
    const card = document.getElementById(cardId);
    if (card) card.classList.add("running");

    showToast(`Running ${testType} test...`, "info");

    try {
      const res = await fetch(`/api/stress/${testType}${param}`);
      const data = await res.json();

      if (data.status === "success") {
        renderTestResult(testType, data.result, cardId);
        showToast(`${testType} test complete`, "success");
      } else {
        showToast(`${testType} test failed`, "error");
      }
    } catch (err) {
      showToast("Error: " + err.message, "error");
    } finally {
      if (card) {
        card.classList.remove("running");
        card.classList.add("complete");
      }
    }
  }

  async function runFullStressTest() {
    const btn = document.getElementById("runFullStress");
    const progress = document.getElementById("stressProgress");
    const progressBar = document.getElementById("stressProgressBar");
    const progressText = document.getElementById("stressProgressText");
    const scoreCard = document.getElementById("stressScoreCard");
    const host = getStressHost();
    const param = host ? `?host=${encodeURIComponent(host)}` : "";

    btn.classList.add("scanning");
    btn.querySelector("span").textContent = "Running...";
    progress.style.display = "block";
    progressBar.style.width = "10%";
    progressText.textContent = "Starting full stress test suite...";

    // Animate progress
    let pct = 10;
    const progressInterval = setInterval(() => {
      if (pct < 90) {
        pct += 5;
        progressBar.style.width = pct + "%";
      }
    }, 3000);

    try {
      const res = await fetch(`/api/stress/full${param}`);
      const data = await res.json();

      clearInterval(progressInterval);
      progressBar.style.width = "100%";
      progressText.textContent = "Tests complete!";

      if (data.status === "success") {
        const result = data.result;

        // Render individual test results
        if (result.tests.ping) renderTestResult("ping", result.tests.ping, "pingCard");
        if (result.tests.rapid_ping) renderTestResult("rapid-ping", result.tests.rapid_ping, "rapidPingCard");
        if (result.tests.concurrent_connections) renderTestResult("connections", result.tests.concurrent_connections, "connCard");
        if (result.tests.latency_under_load) renderTestResult("latency-load", result.tests.latency_under_load, "latencyCard");
        if (result.tests.bandwidth) renderTestResult("bandwidth", result.tests.bandwidth, "bandwidthCard");

        // Render score
        if (result.score) {
          renderScoreCard(result.score);
        }

        showToast(
          `Stress test complete! Score: ${result.score.score}/100 (${result.score.grade})`,
          result.score.score >= 60 ? "success" : "error"
        );
      }
    } catch (err) {
      clearInterval(progressInterval);
      showToast("Stress test failed: " + err.message, "error");
    } finally {
      btn.classList.remove("scanning");
      btn.querySelector("span").textContent = "Run Full Stress Test";
      setTimeout(() => {
        progress.style.display = "none";
      }, 3000);
    }
  }

  function renderTestResult(testType, result, cardId) {
    const card = document.getElementById(cardId);
    if (!card) return;
    const body = card.querySelector(".stress-card-body");

    card.classList.remove("running");
    card.classList.add("complete");

    switch (testType) {
      case "ping":
        body.innerHTML = `
          <div class="stress-result-grid">
            <div class="stress-result-item">
              <span class="stress-result-label">Avg Latency</span>
              <span class="stress-result-value ${result.avg_ms <= 10 ? "good" : result.avg_ms <= 50 ? "warn" : "bad"}">${result.avg_ms} ms</span>
            </div>
            <div class="stress-result-item">
              <span class="stress-result-label">Packet Loss</span>
              <span class="stress-result-value ${result.loss_percent === 0 ? "good" : result.loss_percent <= 5 ? "warn" : "bad"}">${result.loss_percent}%</span>
            </div>
            <div class="stress-result-item">
              <span class="stress-result-label">Min / Max</span>
              <span class="stress-result-value">${result.min_ms} / ${result.max_ms} ms</span>
            </div>
            <div class="stress-result-item">
              <span class="stress-result-label">Jitter</span>
              <span class="stress-result-value ${result.jitter_ms <= 5 ? "good" : result.jitter_ms <= 20 ? "warn" : "bad"}">${result.jitter_ms} ms</span>
            </div>
          </div>`;
        break;

      case "rapid-ping":
        body.innerHTML = `
          <div class="stress-result-grid">
            <div class="stress-result-item">
              <span class="stress-result-label">Avg Latency</span>
              <span class="stress-result-value ${result.avg_ms <= 15 ? "good" : result.avg_ms <= 50 ? "warn" : "bad"}">${result.avg_ms} ms</span>
            </div>
            <div class="stress-result-item">
              <span class="stress-result-label">Packet Loss</span>
              <span class="stress-result-value ${result.loss_percent <= 2 ? "good" : result.loss_percent <= 10 ? "warn" : "bad"}">${result.loss_percent}%</span>
            </div>
            <div class="stress-result-item">
              <span class="stress-result-label">Sent / Received</span>
              <span class="stress-result-value">${result.sent} / ${result.received}</span>
            </div>
            <div class="stress-result-item">
              <span class="stress-result-label">Jitter</span>
              <span class="stress-result-value ${result.jitter_ms <= 10 ? "good" : result.jitter_ms <= 30 ? "warn" : "bad"}">${result.jitter_ms} ms</span>
            </div>
          </div>`;
        break;

      case "connections":
        body.innerHTML = `
          <div class="stress-result-grid">
            <div class="stress-result-item">
              <span class="stress-result-label">Successful</span>
              <span class="stress-result-value good">${result.successful_connections}</span>
            </div>
            <div class="stress-result-item">
              <span class="stress-result-label">Failed</span>
              <span class="stress-result-value ${result.failed_connections === 0 ? "good" : "warn"}">${result.failed_connections}</span>
            </div>
            <div class="stress-result-item">
              <span class="stress-result-label">Avg Connect Time</span>
              <span class="stress-result-value">${result.avg_connect_time_ms} ms</span>
            </div>
            <div class="stress-result-item">
              <span class="stress-result-label">Max Attempted</span>
              <span class="stress-result-value">${result.max_attempted}</span>
            </div>
          </div>`;
        break;

      case "latency-load":
        body.innerHTML = `
          <div class="stress-result-grid">
            <div class="stress-result-item">
              <span class="stress-result-label">Baseline Latency</span>
              <span class="stress-result-value">${result.baseline_latency_ms} ms</span>
            </div>
            <div class="stress-result-item">
              <span class="stress-result-label">Under Load</span>
              <span class="stress-result-value ${result.loaded_latency_avg_ms <= result.baseline_latency_ms * 1.5 ? "good" : "warn"}">${result.loaded_latency_avg_ms} ms</span>
            </div>
            <div class="stress-result-item">
              <span class="stress-result-label">Degradation</span>
              <span class="stress-result-value ${Math.abs(result.latency_degradation_percent) <= 25 ? "good" : Math.abs(result.latency_degradation_percent) <= 50 ? "warn" : "bad"}">${result.latency_degradation_percent}%</span>
            </div>
            <div class="stress-result-item">
              <span class="stress-result-label">Jitter Under Load</span>
              <span class="stress-result-value">${result.loaded_jitter_ms} ms</span>
            </div>
          </div>`;
        break;

      case "bandwidth":
        body.innerHTML = `
          <div class="stress-result-grid">
            <div class="stress-result-item">
              <span class="stress-result-label">Est. Throughput</span>
              <span class="stress-result-value good">${result.estimated_max_throughput_mbps} Mbps</span>
            </div>
            <div class="stress-result-item">
              <span class="stress-result-label">Packet Tests</span>
              <span class="stress-result-value">${result.packet_tests ? result.packet_tests.length : 0}</span>
            </div>
            ${
              result.packet_tests && result.packet_tests.length > 0
                ? `<div class="stress-result-item" style="grid-column: 1 / -1;">
                <span class="stress-result-label">Breakdown</span>
                <span class="stress-result-value" style="font-size:0.75rem">${result.packet_tests.map((t) => `${t.packet_size}B: ${t.avg_latency_ms}ms`).join(" | ")}</span>
              </div>`
                : ""
            }
          </div>`;
        break;
    }
  }

  function renderScoreCard(score) {
    const scoreCard = document.getElementById("stressScoreCard");
    const scoreCircle = document.getElementById("scoreCircle");
    const scoreValue = document.getElementById("scoreValue");
    const scoreGrade = document.getElementById("scoreGrade");
    const scoreBreakdown = document.getElementById("scoreBreakdown");

    scoreCard.style.display = "flex";
    scoreValue.textContent = score.score;

    // Grade styling
    const gradeClass = score.grade.startsWith("A")
      ? "grade-a"
      : score.grade.startsWith("B")
        ? "grade-b"
        : score.grade.startsWith("C")
          ? "grade-c"
          : score.grade.startsWith("D")
            ? "grade-d"
            : "grade-f";

    scoreCircle.className = "score-circle " + gradeClass;
    scoreGrade.textContent = `Grade: ${score.grade}`;
    scoreGrade.style.color =
      gradeClass === "grade-a"
        ? "var(--success)"
        : gradeClass === "grade-b"
          ? "var(--info)"
          : gradeClass === "grade-c"
            ? "var(--warning)"
            : "var(--danger)";

    const details = score.details || {};
    scoreBreakdown.innerHTML = `
      <div class="score-breakdown-item">
        <span class="score-breakdown-label">Ping Quality</span>
        <span class="score-breakdown-value">${details.ping_quality_score || 0}/25</span>
      </div>
      <div class="score-breakdown-item">
        <span class="score-breakdown-label">Packet Loss</span>
        <span class="score-breakdown-value">${details.packet_loss_score || 0}/25</span>
      </div>
      <div class="score-breakdown-item">
        <span class="score-breakdown-label">Rapid Ping</span>
        <span class="score-breakdown-value">${details.rapid_ping_score || 0}/25</span>
      </div>
      <div class="score-breakdown-item">
        <span class="score-breakdown-label">Load Resilience</span>
        <span class="score-breakdown-value">${details.load_resilience_score || 0}/25</span>
      </div>`;
  }

  // Boot
  document.addEventListener("DOMContentLoaded", function () {
    init();
    initStressTest();
  });
})();
