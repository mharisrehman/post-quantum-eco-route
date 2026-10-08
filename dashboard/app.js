const REFRESH_INTERVAL_MS = 5000;
const MAX_RECENT_ROWS = 8;

const elements = {
  alertCount: document.querySelector("#alert-count"),
  alertList: document.querySelector("#alert-list"),
  averageFill: document.querySelector("#average-fill"),
  binCount: document.querySelector("#bin-count"),
  binSelect: document.querySelector("#bin-select"),
  errorBanner: document.querySelector("#error-banner"),
  fillDisplay: document.querySelector("#fill-display"),
  fillLevel: document.querySelector("#fill-level"),
  fillStatus: document.querySelector("#fill-status"),
  levelFill: document.querySelector("#level-fill"),
  readingCount: document.querySelector("#reading-count"),
  readingEmpty: document.querySelector("#reading-empty"),
  readingMeta: document.querySelector("#reading-meta"),
  readingRows: document.querySelector("#reading-rows"),
  readingTime: document.querySelector("#reading-time"),
  refreshButton: document.querySelector("#refresh-button"),
  systemState: document.querySelector("#system-state"),
  systemStateLabel: document.querySelector("#system-state-label"),
  trendChart: document.querySelector("#trend-chart"),
  updatedAt: document.querySelector("#updated-at"),
  visibleAlertCount: document.querySelector("#visible-alert-count"),
};

const state = {
  alerts: [],
  bins: [],
  readings: [],
  selectedBinId: "",
};

function newestFirst(items, dateKey) {
  return [...items].sort(
    (left, right) => Date.parse(right[dateKey]) - Date.parse(left[dateKey]),
  );
}

function formatTime(value) {
  if (!value) return "Time unavailable";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Time unavailable";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  }).format(date);
}

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

async function fetchJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${path} returned HTTP ${response.status}`);
  }
  return response.json();
}

function setSystemState(online, message = "") {
  elements.systemState.dataset.state = online ? "online" : "offline";
  elements.systemStateLabel.textContent = online ? "Cloud API online" : "API unavailable";
  elements.errorBanner.hidden = online;
  elements.errorBanner.textContent = message;
}

function updateBinOptions() {
  const currentSelection = state.selectedBinId || elements.binSelect.value;
  elements.binSelect.replaceChildren();

  if (state.bins.length === 0) {
    const option = makeElement("option", "", "No bins registered");
    option.value = "";
    elements.binSelect.append(option);
    state.selectedBinId = "";
    return;
  }

  for (const bin of state.bins) {
    const option = makeElement("option", "", bin.bin_id);
    option.value = bin.bin_id;
    elements.binSelect.append(option);
  }

  const hasCurrent = state.bins.some((bin) => bin.bin_id === currentSelection);
  const latestReading = newestFirst(state.readings, "recorded_at")[0];
  state.selectedBinId = hasCurrent
    ? currentSelection
    : latestReading?.bin_id || state.bins[0].bin_id;
  elements.binSelect.value = state.selectedBinId;
}

function latestReadingFor(binId) {
  return newestFirst(
    state.readings.filter((reading) => reading.bin_id === binId),
    "recorded_at",
  )[0];
}

function renderMetrics() {
  elements.binCount.textContent = String(state.bins.length);
  elements.readingCount.textContent = String(state.readings.length);
  elements.alertCount.textContent = String(state.alerts.length);

  const latestByBin = new Map();
  for (const reading of state.readings) {
    const previous = latestByBin.get(reading.bin_id);
    if (
      !previous ||
      Date.parse(reading.recorded_at) > Date.parse(previous.recorded_at)
    ) {
      latestByBin.set(reading.bin_id, reading);
    }
  }

  const latestLevels = [...latestByBin.values()].map((reading) => reading.fill_level);
  const average = latestLevels.length
    ? Math.round(
        latestLevels.reduce((total, level) => total + level, 0) /
          latestLevels.length,
      )
    : null;
  elements.averageFill.textContent = average === null ? "--" : `${average}%`;
}

function renderCurrentReading() {
  const reading = latestReadingFor(state.selectedBinId);
  elements.readingEmpty.hidden = Boolean(reading);

  if (!reading) {
    elements.fillLevel.textContent = "--";
    elements.fillDisplay.dataset.level = "normal";
    elements.fillStatus.dataset.level = "normal";
    elements.fillStatus.textContent = "No reading yet";
    elements.readingTime.textContent = "No reading received for this bin";
    elements.readingMeta.textContent = state.selectedBinId || "Select a registered bin";
    elements.levelFill.style.width = "0%";
    drawTrend([]);
    return;
  }

  const isHigh = reading.fill_level > 80;
  const level = isHigh ? "high" : "normal";
  elements.fillLevel.textContent = String(reading.fill_level);
  elements.fillDisplay.dataset.level = level;
  elements.fillStatus.dataset.level = level;
  elements.fillStatus.textContent = isHigh ? "Attention needed" : "Within range";
  elements.readingTime.textContent = `Recorded ${formatTime(reading.recorded_at)}`;
  elements.readingMeta.textContent = `Bin ${reading.bin_id} · reading #${reading.id ?? "-"}`;
  elements.levelFill.dataset.level = level;
  elements.levelFill.style.width = `${reading.fill_level}%`;

  const trend = newestFirst(
    state.readings.filter((item) => item.bin_id === state.selectedBinId),
    "recorded_at",
  )
    .slice(0, 12)
    .reverse();
  drawTrend(trend.map((item) => item.fill_level));
}

function drawTrend(levels) {
  const canvas = elements.trendChart;
  const bounds = canvas.getBoundingClientRect();
  const width = Math.max(1, bounds.width);
  const height = Math.max(1, bounds.height);
  const pixelRatio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * pixelRatio);
  canvas.height = Math.round(height * pixelRatio);

  const context = canvas.getContext("2d");
  context.scale(pixelRatio, pixelRatio);
  context.clearRect(0, 0, width, height);
  context.strokeStyle = "#e4ece8";
  context.lineWidth = 1;
  context.beginPath();
  context.moveTo(0, height - 1);
  context.lineTo(width, height - 1);
  context.stroke();

  if (levels.length === 0) return;

  const inset = 7;
  const chartHeight = height - inset * 2;
  const points = levels.map((level, index) => ({
    x: levels.length === 1 ? width / 2 : (index / (levels.length - 1)) * width,
    y: height - inset - (Math.max(0, Math.min(100, level)) / 100) * chartHeight,
  }));

  context.beginPath();
  context.moveTo(points[0].x, points[0].y);
  for (const point of points.slice(1)) context.lineTo(point.x, point.y);
  context.strokeStyle = levels.at(-1) > 80 ? "#c48a3a" : "#18846b";
  context.lineWidth = 2.5;
  context.lineJoin = "round";
  context.lineCap = "round";
  context.stroke();

  const lastPoint = points.at(-1);
  context.beginPath();
  context.arc(lastPoint.x, lastPoint.y, 4, 0, Math.PI * 2);
  context.fillStyle = context.strokeStyle;
  context.fill();
}

function renderReadings() {
  const readings = newestFirst(state.readings, "recorded_at").slice(
    0,
    MAX_RECENT_ROWS,
  );
  elements.readingRows.replaceChildren();

  if (readings.length === 0) {
    const row = makeElement("tr");
    const cell = makeElement("td", "table-empty", "No readings received yet.");
    cell.colSpan = 4;
    row.append(cell);
    elements.readingRows.append(row);
    return;
  }

  for (const reading of readings) {
    const row = makeElement("tr");
    const status = reading.fill_level > 80 ? "Alert" : "Stored";
    const level = reading.fill_level > 80 ? "high" : "normal";
    row.append(
      makeElement("td", "", reading.bin_id),
      makeElement("td", "", `${reading.fill_level}%`),
      makeElement("td", "", formatTime(reading.recorded_at)),
    );
    const statusCell = makeElement("td");
    const statusLabel = makeElement("span", "reading-status", status);
    statusLabel.dataset.level = level;
    statusCell.append(statusLabel);
    row.append(statusCell);
    elements.readingRows.append(row);
  }
}

function renderAlerts() {
  const alerts = newestFirst(state.alerts, "raised_at").slice(0, 6);
  elements.alertList.replaceChildren();
  elements.visibleAlertCount.textContent = String(alerts.length);

  if (alerts.length === 0) {
    elements.alertList.append(
      makeElement("li", "empty-message", "No alerts recorded."),
    );
    return;
  }

  for (const alert of alerts) {
    const item = makeElement("li", "alert-item");
    item.append(makeElement("span", "alert-marker"));
    const copy = makeElement("span", "alert-copy");
    copy.append(
      makeElement("strong", "", `${alert.bin_id} needs collection`),
      makeElement("span", "", `Fill level reached ${alert.fill_level}%`),
    );
    item.append(copy, makeElement("time", "alert-time", formatTime(alert.raised_at)));
    elements.alertList.append(item);
  }
}

async function refreshDashboard() {
  elements.refreshButton.disabled = true;
  try {
    const [health, bins, readings, alerts] = await Promise.all([
      fetchJson("/healthz"),
      fetchJson("/bins"),
      fetchJson("/readings"),
      fetchJson("/alerts"),
    ]);
    if (health.status !== "ok") throw new Error("Cloud API health check failed");

    state.bins = bins;
    state.readings = readings;
    state.alerts = alerts;
    updateBinOptions();
    renderMetrics();
    renderCurrentReading();
    renderReadings();
    renderAlerts();
    setSystemState(true);
    elements.updatedAt.textContent = `Updated ${new Intl.DateTimeFormat(
      undefined,
      { timeStyle: "medium" },
    ).format(new Date())}`;
  } catch (error) {
    setSystemState(false, `Could not refresh dashboard data: ${error.message}`);
  } finally {
    elements.refreshButton.disabled = false;
  }
}

elements.binSelect.addEventListener("change", () => {
  state.selectedBinId = elements.binSelect.value;
  renderCurrentReading();
});
elements.refreshButton.addEventListener("click", refreshDashboard);
window.addEventListener("resize", () => {
  if (state.selectedBinId) renderCurrentReading();
});

refreshDashboard();
window.setInterval(refreshDashboard, REFRESH_INTERVAL_MS);