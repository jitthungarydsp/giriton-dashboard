const state = {
  user: null,
  data: null,
  selectedDate: null,
  workflow: null,
  billingProfile: null,
  checkedInvoiceFile: null,
  checkedInvoiceMonth: null,
  currentRoute: null,
  coordinatorSetup: null,
  deviceReports: [],
  salaryAdvanceRequests: [],
  statistics: null,
  serviceWorkerRegistration: null,
  workflowMonth: new Date().toISOString().slice(0, 7),
  workflowProcess: "",
  workflowProcesses: [{ id: "", label: "Havi folyamat" }],
  workflowPreviewCourierId: "",
  statisticsMonth: new Date().toISOString().slice(0, 7),
  statisticsHistoryDate: "",
  section: "home",
};
const APP_VERSION = "v57";
const $ = (selector) => document.querySelector(selector);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, { credentials: "same-origin", cache: "no-store", ...options, headers });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    throw new Error(typeof detail === "string" ? detail : detail?.message || "A kérés nem sikerült.");
  }
  return payload;
}

function localDate(offset = 0) {
  const value = new Date();
  value.setDate(value.getDate() + offset);
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function dateLabel(value, short = false) {
  const date = new Date(`${value}T12:00:00`);
  return new Intl.DateTimeFormat("hu-HU", short
    ? { weekday: "short" }
    : { month: "long", day: "numeric", weekday: "long" }
  ).format(date);
}

function shiftDateTime(item, field) {
  const dateValue = item?.date;
  const timeValue = item?.[field];
  if (!dateValue || !timeValue) return null;
  const value = new Date(`${dateValue}T${timeValue}:00`);
  return Number.isNaN(value.getTime()) ? null : value;
}

function activeOrNextShift(items = []) {
  const now = new Date();
  const sorted = [...items]
    .filter((item) => item.date && item.start)
    .sort((left, right) => {
      const leftStart = shiftDateTime(left, "start")?.getTime() || 0;
      const rightStart = shiftDateTime(right, "start")?.getTime() || 0;
      return leftStart - rightStart;
    });

  const active = sorted.find((item) => {
    const start = shiftDateTime(item, "start");
    const end = shiftDateTime(item, "end");
    if (!start) return false;
    const effectiveEnd = end || new Date(start.getTime() + 8 * 60 * 60 * 1000);
    return start <= now && now <= effectiveEnd;
  });

  return active || sorted.find((item) => {
    const start = shiftDateTime(item, "start");
    return start && start >= now;
  }) || null;
}

function showLogin() {
  $("#login-view").classList.remove("hidden");
  $("#app-view").classList.add("hidden");
}

function showApp() {
  $("#login-view").classList.add("hidden");
  $("#app-view").classList.remove("hidden");
  $("#welcome").textContent = `Szia, ${state.user.username.split(" ")[0]}!`;
  const role = String(state.user.role || "").toLowerCase();
  const canCoordinate = ["admin", "coordinator"].includes(role);
  $("#nav-coordinator").classList.toggle("hidden", !canCoordinate);
  const coordinatorOnly = role === "coordinator";
  ["#nav-home", "#nav-settlement", "#nav-statistics", "#nav-salary-advance", "#nav-documents", "#nav-profile", "#nav-device", "#nav-tours"]
    .forEach((selector) => $(selector).classList.toggle("hidden", coordinatorOnly));
  const previewWrapper = $("#workflow-preview-wrapper");
  if (previewWrapper) previewWrapper.classList.toggle("hidden", !state.user.canPreviewCouriers);
}

function showSection(section) {
  state.section = section;
  $("#home-content").classList.toggle("hidden", section !== "home");
  $("#settlement-content").classList.toggle("hidden", section !== "settlement");
  $("#statistics-content").classList.toggle("hidden", section !== "statistics");
  $("#salary-advance-content").classList.toggle("hidden", section !== "salary-advance");
  $("#documents-content").classList.toggle("hidden", section !== "documents");
  $("#profile-content").classList.toggle("hidden", section !== "profile");
  $("#device-content").classList.toggle("hidden", section !== "device");
  $("#tours-content").classList.toggle("hidden", section !== "tours");
  $("#coordinator-content").classList.toggle("hidden", section !== "coordinator");

  $("#nav-home").classList.toggle("active", section === "home");
  $("#nav-settlement").classList.toggle("active", section === "settlement");
  $("#nav-statistics").classList.toggle("active", section === "statistics");
  $("#nav-salary-advance").classList.toggle("active", section === "salary-advance");
  $("#nav-documents").classList.toggle("active", section === "documents");
  $("#nav-profile").classList.toggle("active", section === "profile");
  $("#nav-device").classList.toggle("active", section === "device");
  $("#nav-tours").classList.toggle("active", section === "tours");
  $("#nav-coordinator").classList.toggle("active", section === "coordinator");

  if (section === "settlement" && !state.workflow) loadWorkflow();
  if (section === "statistics" && !state.statistics) loadStatistics();
  if (section === "salary-advance") loadSalaryAdvanceRequests();
  if (section === "documents") loadDocuments();
  if (section === "profile") {
    loadBillingProfile();
    refreshNotificationToggle();
  }
  if (section === "device") loadDeviceReports();
  if (section === "tours") {
    loadCurrentRoute();
  }
  if (section === "coordinator") loadCoordinatorAdjustments();

  window.scrollTo({ top: 0, behavior: "smooth" });
}

function formatCount(value) {
  return new Intl.NumberFormat("hu-HU", { maximumFractionDigits: 0 }).format(Number(value || 0));
}

function formatAverage(value) {
  return new Intl.NumberFormat("hu-HU", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(Number(value || 0));
}

function formatHuf(value) {
  return `${formatCount(value)} Ft`;
}

function parseHufInput(value) {
  const digits = String(value || "").replace(/[^\d]/g, "");
  return Number(digits || 0);
}

function updateSalaryAdvancePreview() {
  const amount = parseHufInput($("#salary-advance-amount")?.value);
  const months = Math.max(1, Number($("#salary-advance-months")?.value || 1));
  const monthly = months ? Math.floor(amount / months) : 0;
  const lastMonthly = monthly + (amount - monthly * months);
  const target = $("#salary-advance-monthly");
  if (target) {
    target.value = lastMonthly !== monthly
      ? `${formatHuf(monthly)} (utolsó: ${formatHuf(lastMonthly)})`
      : formatHuf(monthly);
  }
}

function renderSalaryAdvanceRequests() {
  const target = $("#salary-advance-list");
  if (!target) return;
  const rows = state.salaryAdvanceRequests || [];
  if (!rows.length) {
    target.innerHTML = `
      <div class="process-title">
        <span class="step-code">Ft</span>
        <div><h3>Előleg kérelmek</h3><p>Még nincs rögzített előleg igényed.</p></div>
      </div>
    `;
    return;
  }
  target.innerHTML = `
    <div class="process-title">
      <span class="step-code">Ft</span>
      <div><h3>Előleg kérelmek</h3><p>A jóváhagyott igény külön elszámolási folyamatként választható ki.</p></div>
    </div>
    <div class="financial-card-grid salary-advance-grid">
      ${rows.map((item) => `
        <article class="financial-card">
          <summary>
            <span>${escapeHtml(item.statusLabel || item.status)}</span>
            <strong>${formatHuf(item.requestedAmountHuf)}</strong>
          </summary>
          <div class="stat-breakdown-list">
            <div class="stat-row"><span>Kezdés</span><strong>${escapeHtml(item.startDate || "-")}</strong></div>
            <div class="stat-row"><span>Havi bontás</span><strong>${formatCount(item.installmentMonths)} hó</strong></div>
            <div class="stat-row"><span>Havi levonás</span><strong>${formatHuf(item.monthlyAmountHuf)}</strong></div>
            ${item.processId ? `<div class="stat-row"><span>Folyamat</span><strong>${escapeHtml(item.processId)}</strong></div>` : ""}
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

async function loadSalaryAdvanceRequests() {
  const message = $("#salary-advance-message");
  if (message) message.textContent = "Előleg kérelmek betöltése...";
  try {
    const payload = await api("/api/salary-advance/requests");
    state.salaryAdvanceRequests = payload.requests || [];
    renderSalaryAdvanceRequests();
    if (message) message.textContent = "";
  } catch (error) {
    if (message) message.textContent = error.message;
  }
}

function statisticCard(label, value, note = "") {
  return `
    <article class="stat-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      ${note ? `<small>${escapeHtml(note)}</small>` : ""}
    </article>
  `;
}

function shortDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
  return new Intl.DateTimeFormat("hu-HU", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function renderDelayDetailRows(rows = []) {
  if (!rows.length) return `<div class="stat-row"><span>Nincs route szintű késés adat</span><strong>-</strong></div>`;
  return rows.map((row) => `
    <div class="stat-row">
      <span>${escapeHtml(row.date || "-")} · Route ${escapeHtml(row.routeId || "-")} · WH${escapeHtml(row.warehouseId || "-")}</span>
      <strong>${formatCount(row.delayMinutes)} perc · ${formatCount(row.delayedStops)} cím</strong>
    </div>
  `).join("");
}

function renderComplianceDetailRows(rows = []) {
  if (!rows.length) return `<div class="stat-row"><span>Nincs késő bejelentkezés / no-show részlet</span><strong>-</strong></div>`;
  return rows.map((row) => `
    <div class="stat-row">
      <span>${escapeHtml(row.date || "-")} · Route ${escapeHtml(row.routeId || "-")} · ${escapeHtml(row.vehiclePlate || "")}</span>
      <strong>${formatCount(row.plannedStartDelayMinutes)} perc · ${shortDateTime(row.actualStartAt || row.shiftAvailableAt)}</strong>
    </div>
  `).join("");
}

function dailyHistoryByDate(rows = []) {
  return rows.reduce((acc, row) => {
    const date = String(row.date || "").slice(0, 10);
    if (!date) return acc;
    if (!acc[date]) acc[date] = [];
    acc[date].push(row);
    return acc;
  }, {});
}

function uniqueText(values = []) {
  return [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))];
}

function routeStoryTime(label, value) {
  return `<div class="stat-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(shortDateTime(value))}</strong></div>`;
}

function routeStoryMetric(label, value, suffix = "") {
  const numeric = Number(value || 0);
  return `<div class="stat-row"><span>${escapeHtml(label)}</span><strong>${formatCount(numeric)}${suffix}</strong></div>`;
}

function routeStoryDistance(label, value) {
  const numeric = Number(value || 0);
  return `<div class="stat-row"><span>${escapeHtml(label)}</span><strong>${formatAverage(numeric)} km</strong></div>`;
}

function routeStoryDelayLabel(story = {}) {
  const lateStops = Number(story.timeWindowLateCount || 0);
  const nextShiftDelay = Number(story.nextShiftDelayMinutes || 0);
  const parts = [];
  if (lateStops > 0) parts.push(`${formatCount(lateStops)} késéses cím`);
  if (nextShiftDelay > 0) parts.push(`${formatCount(nextShiftDelay)} perc csúszás a következő műszakra`);
  return parts.length ? `Igen - ${parts.join(" - ")}` : "Nem látszik késés";
}

function routeStoryShiftLabel(story = {}) {
  const name = String(story.shiftName || "").trim();
  const start = shortDateTime(story.shiftStart);
  const end = shortDateTime(story.shiftEnd);
  const time = start !== "-" || end !== "-" ? `${start} - ${end}` : "";
  return [name, time].filter(Boolean).join(" - ") || "-";
}

function renderCurrentRouteStory(route) {
  const story = route.routeStory || {};
  if (!Object.keys(story).length) {
    return `
      <section class="route-timeline">
        <div class="route-timeline-head">
          <span>API számítás</span>
          <strong>Nincs részletes mart adat</strong>
        </div>
      </section>
    `;
  }
  return `
    <section class="route-timeline">
      <div class="route-timeline-head">
        <span>API számítás</span>
        <strong>${escapeHtml(routeStoryShiftLabel(story))}</strong>
      </div>
      <div class="route-timeline-grid">
        ${routeStoryTime("Elérhető volt", story.queueStartedAt || story.availableForShiftSince || story.availableAt || story.courierRegisteredAt)}
        ${routeStoryTime("Túrát kapott", story.assignedAt || route.routeAssignedAt)}
        ${routeStoryMetric("Várakozott", story.queueWaitMinutes, " perc")}
        ${routeStoryTime("Raktárat elhagyta", story.realDeparture || route.realDeparture)}
        ${routeStoryTime("Tényleges visszaérkezés", story.realReturn || route.realReturn)}
        <div class="stat-row"><span>Volt késése?</span><strong>${escapeHtml(routeStoryDelayLabel(story))}</strong></div>
      </div>
      ${story.storyText ? `<p class="route-story-text">${escapeHtml(story.storyText)}</p>` : ""}
    </section>
  `;
}

function renderRouteStoryDetails(row) {
  const story = row.routeStory || {};
  if (!Object.keys(story).length) {
    return `
      <div class="daily-route-story">
        <div class="stat-row"><span>Route story</span><strong>Nincs mart adat</strong></div>
      </div>
    `;
  }
  const distance = Number(story.gpsDistanceKm || row.mileageKm || 0);
  return `
    <div class="daily-route-story">
      ${story.shiftName ? `<p class="updated-at">${escapeHtml(story.shiftName)}</p>` : ""}
      ${routeStoryTime("Műszak kezdete", story.shiftStart)}
      ${routeStoryTime("Sorba állt / elérhető", story.queueStartedAt || story.availableForShiftSince || story.availableAt || story.courierRegisteredAt)}
      ${routeStoryTime("Túrát kapott", story.assignedAt || row.routeAssignedAt)}
      ${routeStoryTime("Indulás a raktárból", story.realDeparture || row.departedAt)}
      ${routeStoryTime("Visszaérkezés a raktárba", story.realReturn || row.warehouseArrivedAt)}
      ${routeStoryMetric("Várakozás túrára", story.queueWaitMinutes, " perc")}
      ${routeStoryMetric("Időkapun túli késés", story.timeWindowLateCount, " cím")}
      ${routeStoryMetric("Kiosztástól visszaérkezésig", story.assignedToReturnMinutes || story.totalRouteMinutes, " perc")}
      ${routeStoryDistance("Megtett táv", distance)}
      ${story.storyText ? `<p class="route-story-text">${escapeHtml(story.storyText)}</p>` : ""}
    </div>
  `;
}

function renderDailyHistory(payload) {
  const rows = payload.dailyHistory || [];
  const byDate = dailyHistoryByDate(rows);
  const dates = Object.keys(byDate).sort().reverse();
  if (!dates.length) {
    state.statisticsHistoryDate = "";
    return `
      <section class="daily-history-card" id="daily-history-card">
        <div class="daily-history-head">
          <div><h3>Elmúlt napok</h3><p>Nincs még DB-be mentett napi autó/túra történet.</p></div>
        </div>
      </section>
    `;
  }
  if (!dates.includes(state.statisticsHistoryDate)) {
    state.statisticsHistoryDate = dates[0];
  }
  const index = Math.max(0, dates.indexOf(state.statisticsHistoryDate));
  const selectedRows = byDate[state.statisticsHistoryDate] || [];
  const plates = uniqueText(selectedRows.map((row) => row.vehiclePlate));
  const models = uniqueText(selectedRows.map((row) => row.vehicleModel));
  const orders = selectedRows.reduce((sum, row) => sum + Number(row.orders || 0), 0);
  const stops = selectedRows.reduce((sum, row) => sum + Number(row.stops || 0), 0);
  const mileage = selectedRows.reduce((sum, row) => sum + Number(row.mileageKm || 0), 0);
  const routes = selectedRows.length;
  const routeRows = selectedRows.map((row) => `
    <details class="daily-route-details">
      <summary class="daily-route-row">
        <div>
          <strong>Route ${escapeHtml(row.routeId || "-")}</strong>
          <small>WH${escapeHtml(row.warehouseId || "-")} · ${formatCount(row.orders)} cím · ${formatCount(row.stops)} stop · ${formatAverage(row.mileageKm)} km</small>
        </div>
        <div>
          <span>${escapeHtml(row.vehiclePlate || "-")}</span>
          <small>${escapeHtml(row.vehicleModel || "")}</small>
        </div>
      </summary>
      ${renderRouteStoryDetails(row)}
    </details>
  `).join("");
  return `
    <section class="daily-history-card" id="daily-history-card">
      <div class="daily-history-head">
        <button class="icon-button" id="daily-history-next" type="button" ${index >= dates.length - 1 ? "disabled" : ""}>‹</button>
        <div>
          <h3>${escapeHtml(dateLabel(state.statisticsHistoryDate))}</h3>
          <p>${escapeHtml(state.statisticsHistoryDate)} · ${index + 1}/${dates.length}</p>
        </div>
        <button class="icon-button" id="daily-history-prev" type="button" ${index <= 0 ? "disabled" : ""}>›</button>
      </div>
      <div class="daily-history-summary">
        <div><span>Kör</span><strong>${formatCount(routes)}</strong></div>
        <div><span>Cím</span><strong>${formatCount(orders)}</strong></div>
        <div><span>Km</span><strong>${formatAverage(mileage)}</strong></div>
      </div>
      <div class="vehicle-chip-row">
        ${(plates.length ? plates : ["Nincs rendszám"]).map((plate) => `<span>${escapeHtml(plate)}</span>`).join("")}
      </div>
      ${models.length ? `<p class="updated-at">${escapeHtml(models.join(" · "))}</p>` : ""}
      <div class="daily-route-list">${routeRows}</div>
    </section>
  `;
}

function changeDailyHistoryDate(offset) {
  const rows = state.statistics?.dailyHistory || [];
  const dates = Object.keys(dailyHistoryByDate(rows)).sort().reverse();
  if (!dates.length) return;
  const currentIndex = Math.max(0, dates.indexOf(state.statisticsHistoryDate));
  const nextIndex = Math.min(dates.length - 1, Math.max(0, currentIndex + offset));
  if (nextIndex === currentIndex) return;
  state.statisticsHistoryDate = dates[nextIndex];
  renderStatistics();
}

function bindDailyHistoryControls() {
  $("#daily-history-prev")?.addEventListener("click", () => changeDailyHistoryDate(-1));
  $("#daily-history-next")?.addEventListener("click", () => changeDailyHistoryDate(1));
  const card = $("#daily-history-card");
  if (!card) return;
  let startX = 0;
  card.addEventListener("touchstart", (event) => {
    startX = event.touches?.[0]?.clientX || 0;
  }, { passive: true });
  card.addEventListener("touchend", (event) => {
    const endX = event.changedTouches?.[0]?.clientX || 0;
    const delta = endX - startX;
    if (Math.abs(delta) < 45) return;
    changeDailyHistoryDate(delta < 0 ? 1 : -1);
  }, { passive: true });
}

function renderStatistics() {
  const payload = state.statistics;
  const grid = $("#statistics-grid");
  const message = $("#statistics-message");
  const breakdown = $("#statistics-breakdown");
  if (!grid || !message || !breakdown) return;

  if (!payload) {
    grid.innerHTML = "";
    breakdown.innerHTML = "";
    message.innerHTML = `<div class="notice">Válassz hónapot, majd frissítsd a statisztikát.</div>`;
    return;
  }

  const summary = payload.summary || {};
  const routes = Number(summary.routes || 0);
  const orders = Number(summary.orders || 0);
  const average = Number(summary.averageOrdersPerRoute || 0);
  const amountsHidden = Boolean(payload.amountsHidden);
  const rating = payload.customerRating || {};
  const ratingValue = rating.available && rating.averageRating !== null
    ? formatAverage(rating.averageRating)
    : "Előkészítve";

  message.innerHTML = `
    <div class="notice">
      ${escapeHtml(payload.month || state.statisticsMonth)} havi adatok. ${escapeHtml(payload.amountsNote || "A teljes bevétel rejtve a mobil nézetben.")}
    </div>
  `;
  grid.innerHTML = [
    statisticCard("Kör", formatCount(routes), "kivitt túrák"),
    statisticCard("Cím", formatCount(orders), "rendelések"),
    statisticCard("Átlag", formatAverage(average), "cím / kör"),
    statisticCard("Műszak", formatCount(summary.shiftCount), "összes"),
    statisticCard("Borravaló", amountsHidden ? "Rejtve" : formatHuf(summary.tipsTotalHuf), amountsHidden ? "havi nyitás után" : "összesen"),
    statisticCard("Futár bevétele", "Rejtve", "mobil nézetben"),
    statisticCard("Ügyfélértékelés", ratingValue, rating.available ? `${formatCount(rating.ratingCount)} értékelés` : "későbbi kimutatáshoz"),
  ].join("");

  const routeBreakdown = payload.routeBreakdown || {};
  const details = payload.performanceDetails || {};
  const quality = payload.dataQuality || {};
  const ruleRows = (quality.dayRules || []).map((rule) => `
    <div class="stat-row">
      <span>${escapeHtml(rule.dayType === "highlighted" ? "Kiemelt" : "Normál")} · ${escapeHtml(rule.weekdays || "-")}</span>
      <strong>${escapeHtml(rule.validFrom || "-")} - ${escapeHtml(rule.validTo || "folyamatos")}</strong>
    </div>
  `).join("");
  const delayRows = details.delayRows || [];
  const complianceRows = details.complianceRows || [];
  breakdown.innerHTML = `
    ${renderDailyHistory(payload)}
    <div class="process-title">
      <span class="step-code">∑</span>
      <div>
        <h3>Túra bontás</h3>
        <p>A besorolás az érvényes szabályokat figyeli, ha vannak szabályok a DB-ben.</p>
      </div>
    </div>
    <div class="stat-breakdown-list">
      <div class="stat-row"><span>Kiemelt City</span><strong>${formatCount(routeBreakdown.highlightedCityRoutes)}</strong></div>
      <div class="stat-row"><span>Normál City</span><strong>${formatCount(routeBreakdown.normalCityRoutes)}</strong></div>
      <div class="stat-row"><span>Kiemelt Express</span><strong>${formatCount(routeBreakdown.highlightedExpressRoutes)}</strong></div>
      <div class="stat-row"><span>Normál Express</span><strong>${formatCount(routeBreakdown.normalExpressRoutes)}</strong></div>
      <div class="stat-row"><span>Express kör</span><strong>${formatCount(routeBreakdown.expressRoutes)}</strong></div>
      <div class="stat-row"><span>Express cím</span><strong>${formatCount(routeBreakdown.expressOrders)}</strong></div>
      <div class="stat-row"><span>Normál kör</span><strong>${formatCount(routeBreakdown.normalRoutes)}</strong></div>
      <div class="stat-row"><span>Regionális kör</span><strong>${formatCount(routeBreakdown.regionalRoutes)}</strong></div>
    </div>
    <div class="stat-breakdown-list">
      <details class="stat-row detail-toggle">
        <summary><span>Késedelmi díj</span><strong>${delayRows.length ? formatCount(delayRows.length) : "Nincs"}</strong></summary>
        ${renderDelayDetailRows(delayRows)}
      </details>
      <details class="stat-row detail-toggle">
        <summary><span>Túramegfelelés</span><strong>${complianceRows.length ? formatCount(complianceRows.length) : "Nincs"}</strong></summary>
        ${renderComplianceDetailRows(complianceRows)}
      </details>
    </div>
    <p class="updated-at">Forrás: ${escapeHtml(quality.routeSource || "nincs route raw adat")} · napi sor: ${formatCount(quality.dailyRows)} · mart story: ${formatCount(quality.routeStoryRows)} · szabály: ${escapeHtml(quality.dayRuleSource || "-")}</p>
    <div class="stat-rule-list">
      <h4>Alkalmazott napbesorolás</h4>
      ${ruleRows || `<div class="stat-row"><span>Nincs aktív szabály</span><strong>-</strong></div>`}
    </div>
  `;
  bindDailyHistoryControls();
}

async function loadStatistics() {
  const monthInput = $("#statistics-month");
  if (monthInput?.value) state.statisticsMonth = monthInput.value;
  state.statisticsHistoryDate = "";
  $("#statistics-message").innerHTML = `<div class="notice">Statisztika betöltése...</div>`;
  try {
    state.statistics = await api(`/api/statistics/monthly?month=${encodeURIComponent(state.statisticsMonth)}&_=${Date.now()}`);
    renderStatistics();
  } catch (error) {
    state.statistics = null;
    $("#statistics-grid").innerHTML = "";
    $("#statistics-breakdown").innerHTML = "";
    $("#statistics-message").innerHTML = `<div class="notice error">A statisztika nem tölthető be: ${escapeHtml(error.message)}</div>`;
  }
}


function ensureRouteCard() {
  let container = $("#current-route-container");
  if (container) return container;

  const tours = $("#tours-content");
  if (!tours) return null;

  container = document.createElement("section");
  container.id = "current-route-container";
  container.className = "route-panel";
  tours.appendChild(container);
  return container;
}

function routeTimeRange(start, end) {
  if (start && end) return `${escapeHtml(start)}-${escapeHtml(end)}`;
  return escapeHtml(start || end || "-");
}

function returnCountdownText(minutes) {
  if (minutes === null || minutes === undefined || Number.isNaN(Number(minutes))) {
    return "Nincs visszaérkezési adat";
  }
  const value = Math.max(0, Number(minutes));
  if (value === 0) return "Most / lejárt";
  return `${formatCount(value)} perc van még`;
}

function routeStopBlock(title, checkpoint, cssClass = "") {
  if (!checkpoint) return "";

  const windowText = checkpoint.windowFrom || checkpoint.windowTo
    ? `<small>${routeTimeRange(checkpoint.windowFrom, checkpoint.windowTo)}</small>`
    : "";
  const position = checkpoint.position ? `<span class="route-stop-index">${escapeHtml(checkpoint.position)}</span>` : `<span class="route-stop-index">-</span>`;

  return `
    <div class="route-stop ${cssClass}">
      ${position}
      <div>
        <span>${escapeHtml(title)}</span>
        <strong>${escapeHtml(checkpoint.address || "Cím nincs megadva")}</strong>
        ${windowText}
      </div>
    </div>
  `;
}

function renderCurrentRoute() {
  const container = ensureRouteCard();
  if (!container) return;

  const payload = state.currentRoute;
  const route = payload?.route;

  if (!payload?.found || !route) {
    container.innerHTML = `
      <div class="route-empty">
        <span class="route-empty-icon">+</span>
        <div>
          <h3>Nincs aktív túra</h3>
          <p>Amint túrát kapsz, itt látod a címszámot és az aktuális címet.</p>
        </div>
      </div>
    `;
    return;
  }

  const departure = route.realDeparture || route.plannedDeparture || "";
  const returnTime = route.realReturn || route.plannedReturn || "";
  const current = route.current;

  container.innerHTML = `
    <div class="route-hero">
      <div>
        <p class="eyebrow">AKTUÁLIS TÚRA</p>
        <h3>#${escapeHtml(route.routeId)}</h3>
        <p>${escapeHtml(route.warehouse || "Raktár nincs megadva")}</p>
      </div>
      <span>${escapeHtml(route.status || "Folyamatban")}</span>
    </div>

    <div class="route-summary">
      <div><span>Címek</span><strong>${Number(route.totalOrders || 0)}</strong></div>
      <div><span>Indulás</span><strong>${escapeHtml(departure || "-")}</strong></div>
      <div><span>Vissza</span><strong>${escapeHtml(returnTime || "-")}</strong></div>
    </div>

    <div class="route-current">
      <span>Visszaérkezésig</span>
      <strong>${escapeHtml(returnCountdownText(route.minutesUntilReturn))}</strong>
    </div>

    ${renderCurrentRouteStory(route)}

    <div class="route-current">
      <span>Mostani cím</span>
      <strong>${escapeHtml(current?.address || "Nincs aktuális cím")}</strong>
      <small>${current ? `#${escapeHtml(current.orderId || "-")} · ${routeTimeRange(current.windowFrom, current.windowTo)}` : "A túra még nem indult el."}</small>
    </div>

    <div class="route-stop-list">
      ${routeStopBlock("Előző", route.previous)}
      ${routeStopBlock("Következő", route.next)}
    </div>

    <button id="delay-alert-button" class="route-problem-button" type="button">
      Problémám van
    </button>
  `;

  $("#delay-alert-button")?.addEventListener(
    "click",
    openDelayAlertDialog
  );
}

async function loadCurrentRoute() {
  try {
    state.currentRoute = await api("/api/routes/current");
    renderCurrentRoute();
  } catch (error) {
    const container = ensureRouteCard();
    if (container) {
      container.innerHTML = `
        <div class="warning-card">
          A túraadatok nem tölthetők be: ${escapeHtml(error.message)}
        </div>
      `;
    }
  }
}

function ensureDelayAlertDialog() {
  let dialog = $("#delay-alert-dialog");
  if (dialog) return dialog;

  dialog = document.createElement("dialog");
  dialog.id = "delay-alert-dialog";
  dialog.innerHTML = `
    <form id="delay-alert-form" class="process-form">
      <h3>Problémám van</h3>

      <label>
        Jelzés típusa
        <select id="route-alert-type">
          <option value="delay">Kések</option>
          <option value="bag_missing">Táska hiány</option>
        </select>
      </label>

      <label>
        Megjegyzés
        <textarea
          id="delay-alert-message"
          rows="4"
          required
        ></textarea>
      </label>

      <label id="route-alert-photo-label" class="hidden">
        Táska fotója
        <input id="route-alert-photo" type="file" accept="image/png,image/jpeg,image/webp" />
      </label>

      <label class="checkbox-row">
        <input id="dispatcher-notified" type="checkbox" />
        Diszpécsernek jeleztem
      </label>

      <p id="delay-alert-status" class="updated-at"></p>

      <div class="dialog-actions">
        <button id="delay-alert-cancel" class="secondary" type="button">
          Mégse
        </button>
        <button class="primary" type="submit">
          Küldés
        </button>
      </div>
    </form>
  `;

  document.body.appendChild(dialog);

  $("#delay-alert-cancel").addEventListener(
    "click",
    () => dialog.close()
  );
  $("#route-alert-type").addEventListener("change", updateRouteAlertDialogMode);
  $("#delay-alert-form").addEventListener(
    "submit",
    submitDelayAlert
  );

  return dialog;
}

function updateRouteAlertDialogMode() {
  const type = $("#route-alert-type")?.value || "delay";
  const photoLabel = $("#route-alert-photo-label");
  const photoInput = $("#route-alert-photo");
  const messageInput = $("#delay-alert-message");
  const isBagMissing = type === "bag_missing";
  photoLabel?.classList.toggle("hidden", !isBagMissing);
  if (photoInput) photoInput.required = isBagMissing;
  if (messageInput) {
    messageInput.required = type !== "bag_missing";
    messageInput.placeholder = isBagMissing
      ? "Opcionális megjegyzés a táska hiányhoz"
      : "Írd le röviden, miért késel";
  }
}

function openDelayAlertDialog() {
  const dialog = ensureDelayAlertDialog();
  $("#route-alert-type").value = "delay";
  $("#delay-alert-message").value = "";
  $("#route-alert-photo").value = "";
  $("#dispatcher-notified").checked = false;
  $("#delay-alert-status").textContent = "";
  $("#delay-alert-status").classList.remove("error");
  updateRouteAlertDialogMode();
  dialog.showModal();
}

async function submitDelayAlert(event) {
  event.preventDefault();

  const route = state.currentRoute?.route;
  const current = route?.current;
  const status = $("#delay-alert-status");
  const submit = event.currentTarget.querySelector(
    'button[type="submit"]'
  );

  submit.disabled = true;
  status.textContent = "Küldés…";

  try {
    const alertType = $("#route-alert-type").value || "delay";
    const form = new FormData();
    form.append("route_id", route.routeId);
    form.append("order_id", current?.orderId || "");
    form.append("alert_type", alertType);
    form.append("message", $("#delay-alert-message").value.trim());
    form.append("dispatcher_notified", $("#dispatcher-notified").checked ? "true" : "false");
    form.append("current_address", current?.address || "");
    if (current?.position !== null && current?.position !== undefined) {
      form.append("current_checkpoint_position", current.position);
    }
    form.append("warehouse", route.warehouse || "");
    form.append("route_departure", route.realDeparture || route.plannedDeparture || "");
    form.append("route_return", route.realReturn || route.plannedReturn || "");
    const photo = $("#route-alert-photo")?.files?.[0];
    if (photo) form.append("photo", photo);

    await api("/api/routes/alert", {
      method: "POST",
      body: form,
    });

    status.textContent = "A jelzés rögzítve.";
    setTimeout(() => $("#delay-alert-dialog").close(), 700);
  } catch (error) {
    status.textContent = error.message;
    status.classList.add("error");
  } finally {
    submit.disabled = false;
  }
}


function renderTabs() {
  const tabs = $("#day-tabs");
  tabs.innerHTML = "";
  for (let offset = 0; offset < 5; offset += 1) {
    const value = localDate(offset);
    const date = new Date(`${value}T12:00:00`);
    const button = document.createElement("button");
    button.className = `day-tab${state.selectedDate === value ? " active" : ""}`;
    const label = offset === 0 ? "Ma" : dateLabel(value, true).replace(".", "");
    button.innerHTML = `<span>${label}</span><strong>${date.getDate()}</strong>`;
    button.addEventListener("click", () => {
      state.selectedDate = value;
      renderTabs();
      renderShifts();
    });
    tabs.appendChild(button);
  }
}

function shiftCard(item, index = 0) {
  const end = item.end ? `–${escapeHtml(item.end)}` : "";
  const delayButton = index === 0
    ? `<button class="shift-delay-button" type="button" data-shift-index="${index}">Kések a műszakból</button>`
    : "";
  return `<article class="shift-card">
    <div class="shift-top">
      <div><p class="shift-time">${escapeHtml(item.start || "Időpont nélkül")}${end}</p><p class="shift-warehouse">${escapeHtml(item.warehouse || "Raktár nincs megadva")}</p></div>
      <span class="shift-state ${escapeHtml(item.status)}">${escapeHtml(item.statusLabel)}</span>
    </div>
    <div class="source-row">
      <span class="source ${item.muszakpro ? "ok" : ""}">MűszakPro ${item.muszakpro ? "✓" : "–"}</span>
      <span class="source ${item.attendance || item.giriton ? "ok" : ""}">Attendance ${item.attendance || item.giriton ? "✓" : "–"}</span>
      ${item.bookingCode ? `<span class="source">${escapeHtml(item.bookingCode)}</span>` : ""}
    </div>
    ${delayButton}
  </article>`;
}

function renderShifts() {
  const items = (state.data?.items || []).filter((item) => item.date === state.selectedDate);
  $("#shift-list").innerHTML = items.length
    ? items.map((item, index) => shiftCard(item, index)).join("")
    : `<div class="empty-card">Erre a napra nincs megjeleníthető műszak.</div>`;
}

function renderHero() {
  const upcoming = activeOrNextShift(state.data?.items || []);
  if (!upcoming) {
    $("#next-shift").textContent = "Nincs aktuális műszak";
    $("#next-shift-detail").textContent = "A következő öt napban nincs foglalás.";
    $("#next-status").textContent = "Szabad";
    return;
  }
  $("#next-shift").textContent = `${dateLabel(upcoming.date)} · ${upcoming.start}`;
  $("#next-shift-detail").textContent = upcoming.warehouse || "Raktár nincs megadva";
  $("#next-status").textContent = upcoming.statusLabel;
}

function renderWarnings() {
  $("#warning-list").innerHTML = (state.data?.warnings || [])
    .map((warning) => `<div class="warning-card">${escapeHtml(warning)}</div>`).join("");
}

async function loadShifts() {
  $("#refresh").disabled = true;
  try {
    state.data = await api("/api/shifts?days=5");
    const focusShift = activeOrNextShift(state.data?.items || []);
    state.selectedDate = focusShift?.date || state.selectedDate || localDate();
    renderHero();
    renderTabs();
    renderWarnings();
    renderShifts();
    $("#updated-at").textContent = `Utolsó lekérés: ${new Date(state.data.updatedAt).toLocaleString("hu-HU")}`;
  } catch (error) {
    $("#warning-list").innerHTML = `<div class="warning-card">${escapeHtml(error.message)}</div>`;
  } finally {
    $("#refresh").disabled = false;
  }
}

async function sendShiftDelayAlert(item, button) {
  if (!item) return;
  const originalText = button.textContent;
  button.disabled = true;
  button.textContent = "Küldés...";
  try {
    await api("/api/shifts/delay-alert", {
      method: "POST",
      body: JSON.stringify({
        work_date: item.date || "",
        start: item.start || "",
        end: item.end || "",
        warehouse: item.warehouse || "",
        shift_name: item.attendanceShiftName || item.muszakproShiftText || "",
        booking_code: item.bookingCode || "",
        message: "",
      }),
    });
    button.textContent = "Jelezve";
    button.classList.add("sent");
  } catch (error) {
    button.textContent = originalText;
    button.disabled = false;
    $("#warning-list").innerHTML = `<div class="warning-card">${escapeHtml(error.message)}</div>`;
  }
}

$("#shift-list").addEventListener("click", async (event) => {
  const button = event.target.closest(".shift-delay-button");
  if (!button) return;
  const items = (state.data?.items || []).filter((item) => item.date === state.selectedDate);
  const index = Number(button.dataset.shiftIndex || 0);
  await sendShiftDelayAlert(items[index], button);
});

function applyInvoiceValidationOverride() {
  const workflow = state.workflow;

  if (!workflow?.invoiceValidationOverride) {
    return;
  }

  const steps = workflow.steps || [];
  const invoiceDocuments = workflow.documents?.invoice || [];

  const invoiceSubmitStep = steps.find(
    (step) => step.key === "invoice_submit"
  );

  const invoiceCheckStep = steps.find(
    (step) => step.key === "invoice_check"
  );

  const invoicePaymentStep = steps.find(
    (step) => step.key === "invoice_payment"
  );

  const invoiceSubmitted = Boolean(
    invoiceSubmitStep?.done || invoiceDocuments.length
  );

  // Az admin továbbengedés az ellenőrzést sikeresnek tekinti.
  if (invoiceCheckStep) {
    invoiceCheckStep.done = true;
    invoiceCheckStep.locked = false;
    invoiceCheckStep.title = "Számlaellenőrzés – admin által továbbengedve";
  }

  // A kifizetési lépés csak akkor oldható fel,
  // ha a számla ténylegesen beérkezett.
  if (invoicePaymentStep && invoiceSubmitted) {
    invoicePaymentStep.locked = false;
  }
}

function workflowStep(key) {
  return state.workflow?.steps?.find((step) => step.key === key) || {};
}

function workflowQuery() {
  const params = new URLSearchParams({ month: state.workflowMonth });
  if (state.workflowProcess) params.set("process", state.workflowProcess);
  if (state.user?.canPreviewCouriers && state.workflowPreviewCourierId) {
    params.set("courier", state.workflowPreviewCourierId);
  }
  return params.toString();
}

function workflowProcessQuery() {
  const params = new URLSearchParams({ month: state.workflowMonth });
  if (state.user?.canPreviewCouriers && state.workflowPreviewCourierId) {
    params.set("courier", state.workflowPreviewCourierId);
  }
  return params.toString();
}

function renderWorkflowProcessPicker() {
  const picker = $("#workflow-process");
  if (!picker) return;
  const processes = state.workflowProcesses.length
    ? state.workflowProcesses
    : [{ id: "", label: "Havi folyamat" }];
  picker.innerHTML = processes.map((process) => (
    `<option value="${escapeHtml(process.id || "")}" ${process.id === state.workflowProcess ? "selected" : ""}>${escapeHtml(process.label || "Havi folyamat")}</option>`
  )).join("");
}

function renderWorkflowSteps() {
  $("#workflow-steps").innerHTML = (state.workflow?.steps || []).map((step, index) => {
    const waiting = step.key.endsWith("_document") && !step.done && !step.locked;
    const status = step.done ? "Kész" : step.locked ? "Zárolva" : waiting ? "Várakozás" : "Aktív";
    return `<li class="workflow-step ${step.done ? "done" : ""} ${step.locked ? "locked" : ""}">
      <span class="workflow-step-index">${step.done ? "✓" : index + 1}</span>
      <div><strong>${escapeHtml(step.title)}</strong><small>${status}</small></div>
      <span class="workflow-step-state">${step.done ? "✓" : step.locked ? "🔒" : waiting ? "…" : "→"}</span>
    </li>`;
  }).join("");
}

function documentList(documents) {
  if (!documents.length) return `<div class="empty-card">Ehhez a hónaphoz még nincs feltöltött dokumentum.</div>`;
  return `<div class="document-list">${documents.map((document) => `
    <div class="document-row">
      <div><strong>${escapeHtml(document.title || document.file_name)}</strong><small>${escapeHtml(document.file_name)} · ${Number(document.file_size || 0).toLocaleString("hu-HU")} bájt</small></div>
      <a class="download-link" href="${escapeHtml(document.downloadUrl)}">Letöltés</a>
    </div>`).join("")}</div>`;
}

function allWorkflowDocuments() {
  const docs = state.workflow?.documents || {};
  const responses = state.workflow?.complaintResponses || {};
  return [
    ...(docs.settlement || []),
    ...(docs.tig || []),
    ...(docs.invoice || []),
    ...(responses.settlement || []),
    ...(responses.tig || []),
  ].sort((a, b) => String(b.uploaded_at || "").localeCompare(String(a.uploaded_at || "")));
}

function renderDocumentsSection() {
  const target = $("#documents-list");
  if (!target) return;
  const paymentDone = state.workflow?.states?.invoice_payment?.status === "done";
  target.innerHTML = `
    <div class="process-title">
      <span class="step-code">${paymentDone ? "✓" : "…"}</span>
      <div>
        <h3>${paymentDone ? "A hónap lezárva" : "A hónap még nincs lezárva"}</h3>
        <p>${paymentDone ? "A számlát admin oldalon elfogadták és a kifizetés megtörtént." : "A lezárás a számla admin elfogadása és kifizetése után történik meg."}</p>
      </div>
    </div>
    ${documentList(allWorkflowDocuments())}
  `;
}

async function loadDocuments() {
  if (!state.workflow) {
    state.workflow = waitingWorkflow();
    renderDocumentsSection();
    try {
      state.workflow = await api(`/api/workflow?${workflowQuery()}`);
    } catch (error) {
      $("#documents-list").innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
      return;
    }
  }
  renderDocumentsSection();
}

function complaintList(complaints) {
  if (!complaints.length) return "";
  return `<div class="complaint-list">${complaints.map((complaint) => `
    <div class="complaint-row"><div><strong>${escapeHtml(complaint.message)}</strong><small>${escapeHtml(complaint.status)} · ${new Date(complaint.created_at).toLocaleString("hu-HU")}</small>${complaint.admin_response ? `<div class="notice">Admin válasza: ${escapeHtml(complaint.admin_response)}${complaint.responded_by || complaint.responded_at ? `<small>${escapeHtml(complaint.responded_by || "admin")} · ${complaint.responded_at ? new Date(complaint.responded_at).toLocaleString("hu-HU") : ""}</small>` : ""}</div>` : ""}</div></div>
  `).join("")}</div>`;
}

function complaintResponseList(responses) {
  if (!responses.length) return "";
  return `<div class="complaint-list"><strong>Admin valaszai</strong>${responses.map((response) => `
    <div class="complaint-row"><div><strong>${escapeHtml(response.note || response.title || "Admin valasz")}</strong><small>${escapeHtml(response.uploaded_by || "admin")} · ${response.uploaded_at ? new Date(response.uploaded_at).toLocaleString("hu-HU") : ""}</small>${response.downloadUrl ? `<a class="download-link" href="${escapeHtml(response.downloadUrl)}">Valasz letoltese</a>` : ""}</div></div>
  `).join("")}</div>`;
}

function hasOpenComplaint(complaints) {
  return complaints.some((complaint) => {
    const status = String(complaint.status || "").trim().toLowerCase();
    const hasAdminAnswer = Boolean(
      String(complaint.admin_response || "").trim()
      || String(complaint.responded_at || "").trim()
    );
    return !["resolved", "closed"].includes(status) && !hasAdminAnswer;
  });
}

function formatSignedHuf(value) {
  const amount = Number(value || 0);
  if (amount < 0) return `-${formatHuf(Math.abs(amount))}`;
  if (amount > 0) return `+${formatHuf(amount)}`;
  return formatHuf(0);
}

function formatFinancialValue(item) {
  if (item?.amountKind === "count") return formatCount(item.amountHuf);
  return formatSignedHuf(item?.amountHuf);
}

function financialDetailRows(items = []) {
  if (!items.length) return `<div class="empty-card">Nincs bontott adat ehhez a kártyához.</div>`;
  return `<div class="financial-detail-list">${items.map((item) => `
    <div class="financial-detail-row">
      <div>
        <strong>${escapeHtml(item.label)}</strong>
        <small>${escapeHtml(item.note || "")}</small>
      </div>
      <span>${formatFinancialValue(item)}</span>
    </div>
  `).join("")}</div>`;
}

function financialComplaintOptions(options = []) {
  if (!options.length) return `<div class="empty-card">Nincs választható altétel.</div>`;
  return `<div class="financial-complaint-options">${options.map((item) => `
    <label class="checkbox-line">
      <input type="checkbox" name="item" value="${escapeHtml(item.key)}" data-label="${escapeHtml(item.label)}" data-amount="${Number(item.amountHuf || 0)}" data-kind="${escapeHtml(item.amountKind || "huf")}" />
      <span>${escapeHtml(item.label)} <strong>${formatFinancialValue(item)}</strong></span>
    </label>
  `).join("")}</div>`;
}

function financialHighlightPanel(card, emptyText) {
  const items = (card?.items || []).filter((item) => Number(item.amountHuf || 0));
  if (!items.length) return `<div class="notice">${escapeHtml(emptyText)}</div>`;
  return `<div class="financial-highlight-panel">
    <strong>${escapeHtml(card.label || "Tetelek")}</strong>
    ${financialDetailRows(items)}
  </div>`;
}

function renderFinancialBreakdown(locked, accepted, blocksAcceptance) {
  const breakdown = state.workflow?.financialBreakdown || {};
  const complaints = state.workflow?.complaints?.settlement || [];
  const hasOpenComplaintForAction = hasOpenComplaint(complaints);
  const readOnly = Boolean(state.workflow?.viewerReadOnly);
  if (!breakdown.available) {
    return `<div class="notice">${escapeHtml(breakdown.message || "A havi pénzügyi bontás még nincs kész.")}</div>`;
  }
  const cards = breakdown.cards || [];
  const deductionCard = cards.find((card) => card.key === "deductions");
  const bonusMalusCard = cards.find((card) => card.key === "bonus_malus");
  const viewedUser = state.workflow?.viewingAs || {};
  const previewNotice = readOnly
    ? `<div class="notice">Előnézet: ${escapeHtml(viewedUser.username || "futár")} (${escapeHtml(viewedUser.courierId || "")}). Ebben a módban csak nézni lehet az adatokat.</div>`
    : "";
  return `
    ${previewNotice}
    <section class="financial-total-card">
      <span>Teljes kifizetendő összeg</span>
      <strong>${formatHuf(breakdown.totalPayableHuf)}</strong>
      <small>${escapeHtml(breakdown.month || state.workflowMonth)}</small>
    </section>
    ${financialHighlightPanel(deductionCard, "Ebben a honapban nincs levonas vagy korrekcio.")}
    ${financialHighlightPanel(bonusMalusCard, "Ebben a honapban nincs bonusz vagy malusz tetel.")}
    <div class="financial-card-grid">
      ${cards.map((card) => `
        <details class="financial-card ${escapeHtml(card.tone || "")}" ${["payable", "deductions", "bonus_malus"].includes(card.key) ? "open" : ""}>
          <summary>
            <span>${escapeHtml(card.label)}</span>
            <strong>${formatFinancialValue(card)}</strong>
          </summary>
          ${financialDetailRows(card.items || [])}
        </details>
      `).join("")}
    </div>
    <div class="accept-row">
      ${accepted
        ? `<div class="accept-row done">✓ Az elszámolási összeget elfogadtad.</div>`
        : readOnly
          ? `<button class="primary" disabled>Előnézeti módban nem módosítható</button>`
        : !locked && !blocksAcceptance
          ? `<button class="primary" id="accept-settlement">✓ Elfogadom az összeget</button>`
          : !locked
            ? `<button class="primary" disabled>Reklamáció lezárásáig nem fogadható el</button>`
            : ""}
    </div>
    <div class="complaint-box">
      <strong>Reklamáció</strong>
      ${complaintList(complaints)}
      ${hasOpenComplaintForAction
        ? `<div class="notice">Már van nyitott reklamáció ehhez a hónaphoz. Új rekordot az előző lezárása után tudsz küldeni.</div>`
        : readOnly
          ? `<div class="notice">Előnézeti módban reklamáció nem küldhető.</div>`
        : `<form id="complaint-settlement">
            <label>Melyik értékkel van gond?
              ${financialComplaintOptions(breakdown.complaintOptions || [])}
            </label>
            <label>Rövid leírás<textarea name="message" placeholder="Írd le röviden, mit kell javítani vagy ellenőrizni." required></textarea></label>
            <button class="secondary" type="submit">Reklamáció küldése</button>
          </form>`}
    </div>
  `;
}

function renderLegacySettlementDocumentPanel(documents, complaints, accepted, locked, blocksAcceptance, readOnly) {
  return `
    <div class="notice">Régi elszámolási dokumentum alapján kezelhető folyamat. Nyisd meg a PDF-et, majd fogadd el vagy küldj reklamációt.</div>
    ${documentList(documents)}
    ${accepted
      ? `<div class="accept-row done">✓ Az elszámolást elfogadtad.</div>`
      : readOnly
        ? `<div class="accept-row"><button class="primary" disabled>Előnézeti módban nem módosítható</button></div>`
      : documents.length && !locked && !blocksAcceptance
        ? `<div class="accept-row"><button class="primary" id="accept-settlement">✓ Elfogadom az elszámolást</button></div>`
        : documents.length && !locked && blocksAcceptance
          ? `<div class="accept-row"><button class="primary" disabled>Reklamáció lezárásáig nem fogadható el</button></div>`
          : ""}
    <div class="complaint-box">
      <strong>Reklamáció</strong>
      ${complaintList(complaints)}
      ${hasOpenComplaint(complaints)
        ? `<div class="notice">Már van nyitott reklamáció ehhez a hónaphoz. Új rekordot az előző lezárása után tudsz küldeni.</div>`
        : readOnly
          ? `<div class="notice">Előnézeti módban reklamáció nem küldhető.</div>`
        : `<form id="complaint-settlement"><label>Mi a gond?<textarea name="message" placeholder="Írd le röviden, mit kell javítani vagy ellenőrizni." required></textarea></label><button class="secondary" type="submit">Reklamáció küldése</button></form>`}
    </div>
  `;
}

function tigValue(value) {
  return formatHuf(Number(value || 0));
}

function renderTigBreakdown() {
  const tig = state.workflow?.tigBreakdown || {};
  if (!tig.available) {
    return `<div class="notice">${escapeHtml(tig.message || "A TIG bontas meg nincs kesz.")}</div>`;
  }
  const rows = tig.rows || [];
  return `
    <section class="tig-total-card">
      <span>TIG vegosszeg</span>
      <strong>${tigValue(tig.finalTotalHuf)}</strong>
      <small>${escapeHtml(tig.month || state.workflowMonth)} · ${escapeHtml(tig.taxLabel || "")}</small>
    </section>
    <div class="tig-table">
      <div class="tig-row head"><span>Tetel</span><span>Netto</span><span>AFA</span><span>Brutto</span></div>
      ${rows.map((row) => `
        <div class="tig-row ${row.key === "cash_deduction" ? "deduction" : ""}">
          <span><strong>${escapeHtml(row.label || "")}</strong><small>${escapeHtml(row.note || "")}</small></span>
          <span>${tigValue(row.netHuf)}</span>
          <span>${row.vatLabel ? escapeHtml(row.vatLabel) : tigValue(row.vatHuf)}</span>
          <span>${tigValue(row.grossHuf)}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function isExtraWorkflow() {
  return Boolean(state.workflow?.process);
}

function renderDocumentPanel(action, title, stepNumber) {
  const panel = $(`#${action}-panel`);
  const documents = state.workflow?.documents?.[action] || [];
  const complaints = state.workflow?.complaints?.[action] || [];
  const complaintResponses = state.workflow?.complaintResponses?.[action] || [];
  const ignoreComplaints = Boolean(state.workflow?.ignoreComplaintsForBilling);
  const hasOpenComplaintForAction = hasOpenComplaint(complaints);
  const blocksAcceptance = !ignoreComplaints && hasOpenComplaintForAction;
  const readOnly = Boolean(state.workflow?.viewerReadOnly);
  const accepted = state.workflow?.states?.[action]?.status === "done";
  const documentStep = workflowStep(`${action}_document`);
  const locked = Boolean(documentStep.locked) && !(action === "tig" && readOnly && state.workflow?.tigBreakdown?.available);
  const breakdown = state.workflow?.financialBreakdown || {};
  const useLegacySettlementDocument = action === "settlement" && !breakdown.available && documents.length > 0;
  const waitingTitle = action === "settlement"
    ? "Várakozás az elszámolás elkészítésére"
    : "Várakozás a TIG elkészítésére";
  const visibleTitle = documents.length ? title : waitingTitle;
  const description = locked
    ? "Az előző lépés lezárása után válik aktívvá."
    : documents.length
      ? "Nézd meg a dokumentumot, majd fogadd el vagy küldj reklamációt."
      : "Amint az admin elkészíti és elküldi, itt automatikusan megjelenik.";
  panel.classList.toggle("locked", locked);
  if (action === "settlement") {
    panel.innerHTML = `
      <div class="process-title"><span class="step-code">${stepNumber}</span><div><h3>Elszámolásom</h3><p>A kártyákra nyitva látod, miből áll össze a havi összeg.</p></div></div>
      ${isExtraWorkflow()
        ? `<div class="notice">Ez egy egyéb folyamat. Itt nincs külön havi elszámolás vagy TIG; a következő teendő a számla feltöltése.</div>`
        : locked
          ? `<div class="empty-card">🔒 Az elszámolási adatok még nem aktívak.</div>`
          : useLegacySettlementDocument
            ? renderLegacySettlementDocumentPanel(documents, complaints, accepted, locked, blocksAcceptance, readOnly)
          : renderFinancialBreakdown(locked, accepted, blocksAcceptance)}
    `;
    const acceptButton = $(`#accept-${action}`);
    if (acceptButton) acceptButton.addEventListener("click", () => acceptDocument(action));
    const complaintForm = $(`#complaint-${action}`);
    if (complaintForm) complaintForm.addEventListener("submit", (event) => submitComplaint(event, action));
    return;
  }
  if (action === "tig" && !isExtraWorkflow()) {
    const tig = state.workflow?.tigBreakdown || {};
    const tigReady = Boolean(tig.available);
    panel.innerHTML = `
      <div class="process-title"><span class="step-code">${stepNumber}</span><div><h3>TIG és elfogadás</h3><p>A TIG tételes bontása itt jelenik meg, KP sorral és KP levonással.</p></div></div>
      ${locked ? `<div class="empty-card">Az előző lépés még nincs lezárva.</div>` : renderTigBreakdown()}
      ${!locked && documents.length ? documentList(documents) : ""}
      ${accepted
        ? `<div class="accept-row done">A TIG-et elfogadtad.</div>`
        : readOnly
          ? `<div class="accept-row"><button class="primary" disabled>Előnézeti módban nem módosítható</button></div>`
        : tigReady && !locked && !blocksAcceptance
          ? `<div class="accept-row"><button class="primary" id="accept-${action}">Elfogadom a TIG-et</button></div>`
        : tigReady && !locked && blocksAcceptance
          ? `<div class="accept-row"><button class="primary" disabled>Reklamáció lezárásáig nem fogadható el</button></div>`
          : ""}
      ${!locked && tigReady ? `<div class="complaint-box">
        <strong>Reklamáció</strong>
        ${complaintList(complaints)}
        ${complaintResponseList(complaintResponses)}
        ${hasOpenComplaintForAction
          ? `<div class="notice">Már van nyitott reklamáció ehhez a lépéshez. Új rekordot az előző lezárása után tudsz küldeni.</div>`
          : readOnly
            ? `<div class="notice">Előnézeti módban reklamáció nem küldhető.</div>`
          : `<form id="complaint-${action}"><label>Mi a gond?<textarea name="message" placeholder="Írd le röviden, mit kell javítani vagy ellenőrizni." required></textarea></label><button class="secondary" type="submit">Reklamáció küldése</button></form>`}
      </div>` : ""}`;
    const acceptButton = $(`#accept-${action}`);
    if (acceptButton) acceptButton.addEventListener("click", () => acceptDocument(action));
    const complaintForm = $(`#complaint-${action}`);
    if (complaintForm) complaintForm.addEventListener("submit", (event) => submitComplaint(event, action));
    return;
  }
  panel.innerHTML = `
    <div class="process-title"><span class="step-code">${stepNumber}</span><div><h3>${visibleTitle}</h3><p>${description}</p></div></div>
    ${locked ? `<div class="empty-card">🔒 Az előző lépés még nincs lezárva.</div>` : documentList(documents)}
    ${accepted
      ? `<div class="accept-row done">✓ A dokumentumot elfogadtad.</div>`
      : documents.length && readOnly
        ? `<div class="accept-row"><button class="primary" disabled>Előnézeti módban nem módosítható</button></div>`
      : documents.length && !locked && !blocksAcceptance
        ? `<div class="accept-row"><button class="primary" id="accept-${action}">✓ Elfogadom a dokumentumot</button></div>`
        : documents.length && !locked && blocksAcceptance
          ? `<div class="accept-row"><button class="primary" disabled>Reklamacio lezarasaig nem fogadhato el</button></div>`
          : ""}
    ${documents.length && !locked ? `<div class="complaint-box">
      <strong>Reklamáció</strong>
      ${complaintList(complaints)}
      ${complaintResponseList(complaintResponses)}
      ${hasOpenComplaintForAction
        ? `<div class="notice">Mar van nyitott reklamacio ehhez a lepeshez. Uj rekordot az elozo lezarasa utan tudsz kuldeni.</div>`
        : readOnly
          ? `<div class="notice">Előnézeti módban reklamáció nem küldhető.</div>`
        : `<form id="complaint-${action}"><label>Mi a gond?<textarea name="message" placeholder="Írd le röviden, mit kell javítani vagy ellenőrizni." required></textarea></label><button class="secondary" type="submit">Reklamáció küldése</button></form>`}
    </div>` : ""}`;

  const acceptButton = $(`#accept-${action}`);
  if (acceptButton) acceptButton.addEventListener("click", () => acceptDocument(action));
  const complaintForm = $(`#complaint-${action}`);
  if (complaintForm) complaintForm.addEventListener("submit", (event) => submitComplaint(event, action));
}

function setPanelLocked(id, locked) {
  const panel = $(id);
  panel.classList.toggle("locked", locked);
  panel.querySelectorAll("input, textarea, button").forEach((control) => { control.disabled = locked; });
}

function activeWorkflowPanel() {
  const steps = state.workflow?.steps || [];
  const firstActive = steps.find((step) => !step.done && !step.locked) || steps.find((step) => !step.done);
  if (!firstActive && state.workflow?.states?.invoice_payment?.status === "done") return "invoice-check-panel";
  if (isExtraWorkflow() && (firstActive?.key?.startsWith("settlement") || firstActive?.key?.startsWith("tig"))) {
    const invoiceStep = workflowStep("invoice_submit");
    if (!invoiceStep.locked && !invoiceStep.done) return "invoice-submit-panel";
  }
  const key = firstActive?.key || "";
  if (key.startsWith("settlement")) return "settlement-panel";
  if (key.startsWith("tig")) return "tig-panel";
  if (key === "invoice_submit") return "invoice-submit-panel";
  if (key === "invoice_check" || key === "invoice_payment") return "invoice-check-panel";
  return "settlement-panel";
}

function showOnlyWorkflowPanel(panelId) {
  ["settlement-panel", "tig-panel", "invoice-submit-panel", "invoice-check-panel"].forEach((id) => {
    const panel = $(`#${id}`);
    if (panel) panel.classList.toggle("hidden", id !== panelId);
  });
}

function renderWorkflow() {
  applyInvoiceValidationOverride();
  renderWorkflowSteps();
  renderDocumentPanel("settlement", "Elszámolás és elfogadás", 1);
  renderDocumentPanel("tig", "TIG és elfogadás", 3);
  const readOnly = Boolean(state.workflow?.viewerReadOnly);
  const invoiceAlreadySubmitted = Boolean(workflowStep("invoice_submit").done)
    || Boolean((state.workflow?.documents?.invoice || []).length);
  setPanelLocked("#invoice-submit-panel", readOnly || invoiceAlreadySubmitted || Boolean(workflowStep("invoice_submit").locked));
  setPanelLocked("#invoice-check-panel", readOnly || Boolean(workflowStep("invoice_check").locked));
  showOnlyWorkflowPanel(activeWorkflowPanel());
  const viewedUser = state.workflow?.viewingAs;
  const previewNotice = readOnly && viewedUser
    ? `<div class="notice">Előnézet: ${escapeHtml(viewedUser.username || "futár")} (${escapeHtml(viewedUser.courierId || "")}). Ebben a módban csak nézni lehet az adatokat.</div>`
    : "";
  let overrideNotice = state.workflow?.invoiceValidationOverride
    ? `<div class="notice">Admin továbbengedés aktív: a számlaellenőrzési hibák figyelmeztetésként kezelődnek.</div>`
    : "";
  if (state.workflow?.efoInvoiceSkip) {
    overrideNotice += `<div class="notice">EFO folyamat: számla nem szükséges, a folyamat admin kifizetésre vár.</div>`;
  } else if (state.workflow?.manualInvoiceSkip) {
    overrideNotice += `<div class="notice">SzĂˇmlafeltĂ¶ltĂ©s kĂ©zzel kihagyva, a folyamat admin kifizetĂ©sre vĂˇr.</div>`;
  }
  const checkInfo = $("#invoice-check-info");
  if (checkInfo) {
    const checkDone = !state.workflow?.manualInvoiceSkip && !state.workflow?.efoInvoiceSkip && state.workflow?.states?.invoice_check?.status === "done";
    const checkOpen = state.workflow?.states?.invoice_check?.status === "open";
    checkInfo.innerHTML = `${previewNotice}${overrideNotice}${checkDone ? `<div class="notice">A feltöltött számla ellenőrzése sikeres.</div>` : ""}${checkOpen ? `<div class="notice error">A számla manuális ellenőrzésre került, kérlek légy türelemmel.</div>` : ""}${complaintList(state.workflow?.complaints?.invoice_check || [])}`;
  }
  const submitInfo = $("#invoice-submit-info");
  if (submitInfo) {
    submitInfo.innerHTML = `${previewNotice}${overrideNotice}${
      invoiceAlreadySubmitted ? `<div class="notice">A számla már beérkezett ehhez a folyamathoz, új feltöltés nem indítható.</div>` : ""
    }${complaintList(state.workflow?.complaints?.invoice_submit || [])}`;
  }
  $("#invoice-document-list").innerHTML = (state.workflow?.documents?.invoice || []).length
    ? `<div class="complaint-box"><strong>Korábban feltöltött számlák</strong>${documentList(state.workflow.documents.invoice)}</div>`
    : "";
  renderDocumentsSection();
  $("#workflow-updated-at").textContent = `Frissítve: ${new Date(state.workflow.updatedAt).toLocaleString("hu-HU")} · ${APP_VERSION}`;
}

function showWorkflowMessage(message, isError = false) {
  $("#workflow-message").innerHTML = message ? `<div class="notice ${isError ? "error" : ""}">${escapeHtml(message)}</div>` : "";
}

function waitingWorkflow() {
  const titles = [
    ["settlement_document", "Várakozás az elszámolás elkészítésére", false],
    ["settlement", "Elszámolás elfogadása", true],
    ["tig_document", "Várakozás a TIG elkészítésére", true],
    ["tig", "TIG elfogadása", true],
    ["invoice_submit", "Számlafeltöltés", true],
    ["invoice_check", "Számlaellenőrzés", true],
    ["invoice_payment", "Admin számlaelfogadás és kifizetés", true],
  ];
  return {
    month: state.workflowMonth,
    steps: titles.map(([key, title, locked]) => ({ key, title, locked, done: false })),
    states: {},
    documents: { settlement: [], tig: [], invoice: [] },
    process: state.workflowProcess,
    processLabel: state.workflowProcess ? `Egyéb folyamat: ${state.workflowProcess}` : "Havi folyamat",
    complaints: { settlement: [], tig: [], invoice_submit: [], invoice_check: [] },
    complaintResponses: { settlement: [], tig: [], invoice_submit: [], invoice_check: [] },
    updatedAt: new Date().toISOString(),
  };
}

async function loadWorkflow() {
  const refreshButton = $("#workflow-refresh");
  if (refreshButton) {
    refreshButton.disabled = true;
    refreshButton.textContent = "Frissítés…";
  }
  state.workflow = waitingWorkflow();
  renderWorkflow();
  showWorkflowMessage("Folyamat betöltése…");
  try {
    const processPayload = await api(`/api/workflow/processes?${workflowProcessQuery()}`);
    state.workflowProcesses = processPayload.processes || [{ id: "", label: "Havi folyamat" }];
    if (!state.workflowProcesses.some((process) => process.id === state.workflowProcess)) {
      state.workflowProcess = "";
    }
    renderWorkflowProcessPicker();
    state.workflow = await api(`/api/workflow?${workflowQuery()}`);
    renderWorkflow();
    showWorkflowMessage("");
  } catch (error) {
    state.workflow = waitingWorkflow();
    renderWorkflow();
    showWorkflowMessage("Az elszámolás adatai jelenleg nem érhetők el. A folyamat várakozó állapotban marad; próbáld meg később frissíteni.", true);
  } finally {
    if (refreshButton) {
      refreshButton.disabled = false;
      refreshButton.textContent = "Frissítés";
    }
  }
}

async function acceptDocument(action) {
  showWorkflowMessage("Elfogadás mentése…");
  try {
    const payload = await api(`/api/workflow/${action}/accept`, {
      method: "POST",
      body: JSON.stringify({ month: state.workflowMonth, process: state.workflowProcess }),
    });
    state.workflow = payload.workflow;
    renderWorkflow();
    showWorkflowMessage("Az elfogadás rögzítve. A következő lépés aktívvá vált.");
  } catch (error) {
    showWorkflowMessage(error.message, true);
  }
}

async function submitComplaint(event, action) {
  event.preventDefault();
  const form = event.currentTarget;
  const selectedItems = [...form.querySelectorAll("input[name='item']:checked")]
    .map((input) => {
      const label = input.dataset.label || input.value;
      const amount = Number(input.dataset.amount || 0);
      const value = input.dataset.kind === "count" ? formatCount(amount) : formatSignedHuf(amount);
      return `${label}: ${value}`;
    });
  const rawMessage = String(new FormData(form).get("message") || "").trim();
  const message = selectedItems.length
    ? `Érintett tétel(ek): ${selectedItems.join("; ")}\n\n${rawMessage}`
    : rawMessage;
  showWorkflowMessage("Reklamáció küldése…");
  try {
    const payload = await api("/api/workflow/complaints", {
      method: "POST",
      body: JSON.stringify({ month: state.workflowMonth, process: state.workflowProcess, action, message }),
    });
    state.workflow = payload.workflow;
    renderWorkflow();
    showWorkflowMessage("A reklamáció megérkezett az admin elszámolási felületére.");
  } catch (error) {
    showWorkflowMessage(error.message, true);
  }
}

async function requestInvoiceHelp(action) {
  const labels = {
    invoice_check: "számlaellenőrzés",
    invoice_submit: "számlafeltöltés",
  };
  const message = `Elakadtam a(z) ${labels[action] || action} lépésnél, segítséget kérek.`;
  showWorkflowMessage("Segítségkérés küldése…");
  try {
    const payload = await api("/api/workflow/complaints", {
      method: "POST",
      body: JSON.stringify({ month: state.workflowMonth, process: state.workflowProcess, action, message }),
    });
    state.workflow = payload.workflow;
    renderWorkflow();
    showWorkflowMessage("A segítségkérés megérkezett az admin elszámolási felületére.");
  } catch (error) {
    showWorkflowMessage(error.message, true);
  }
}

const invoiceCheckHelpButton = $("#invoice-check-help");
if (invoiceCheckHelpButton) {
  invoiceCheckHelpButton.addEventListener("click", () => requestInvoiceHelp("invoice_check"));
}

const invoiceSubmitHelpButton = $("#invoice-submit-help");
if (invoiceSubmitHelpButton) {
  invoiceSubmitHelpButton.addEventListener("click", () => requestInvoiceHelp("invoice_submit"));
}



function urlBase64ToUint8Array(value) {
  const padding = "=".repeat((4 - (value.length % 4)) % 4);
  const base64 = (value + padding).replaceAll("-", "+").replaceAll("_", "/");
  const raw = atob(base64);
  return Uint8Array.from([...raw].map((character) => character.charCodeAt(0)));
}

function uint8ArrayToUrlBase64(value) {
  const bytes = value instanceof Uint8Array ? value : new Uint8Array(value || []);
  let raw = "";
  bytes.forEach((byte) => {
    raw += String.fromCharCode(byte);
  });
  return btoa(raw).replaceAll("+", "-").replaceAll("/", "_").replaceAll("=", "");
}

function isPushSecureContext() {
  return window.isSecureContext || ["localhost", "127.0.0.1"].includes(window.location.hostname);
}

async function ensureServiceWorkerRegistration() {
  if (!("serviceWorker" in navigator)) {
    throw new Error("A service worker nem támogatott ezen az eszközön.");
  }
  if (!state.serviceWorkerRegistration) {
    state.serviceWorkerRegistration = await navigator.serviceWorker.register("/sw.js?v=57");
  }
  return navigator.serviceWorker.ready;
}

function ensureNotificationToggle() {
  let card = $("#notification-settings-card");
  if (card) return card;

  const profile = $("#profile-content");
  if (!profile) return null;

  card = document.createElement("section");
  card.id = "notification-settings-card";
  card.className = "process-card";
  card.innerHTML = `
    <div class="process-title">
      <span class="step-code">🔔</span>
      <div>
        <h3>Értesítések</h3>
        <p id="notification-status">Kikapcsolva.</p>
      </div>
    </div>
    <label class="notification-toggle-row">
      <span>Push értesítések</span>
      <input id="notification-toggle" type="checkbox" role="switch" />
    </label>
  `;
  profile.appendChild(card);

  const toggle = card.querySelector("#notification-toggle");
  toggle.addEventListener("change", handleNotificationToggleChange);

  return card;
}

async function getPushSubscription() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return null;
  const registration = await ensureServiceWorkerRegistration();
  return registration.pushManager.getSubscription();
}

function subscriptionUsesPublicKey(subscription, publicKey) {
  const currentKey = subscription?.options?.applicationServerKey;
  if (!currentKey || !publicKey) return true;
  return uint8ArrayToUrlBase64(currentKey) === publicKey;
}

async function removeBrowserPushSubscription(subscription) {
  if (!subscription) return;
  const serialized = subscription.toJSON();
  if (serialized.endpoint) {
    await api("/api/push/unsubscribe", {
      method: "POST",
      body: JSON.stringify({
        endpoint: serialized.endpoint,
        keys: serialized.keys || {},
        user_agent: navigator.userAgent,
      }),
    }).catch(() => {});
  }
  await subscription.unsubscribe();
}

function setNotificationStatus(message, isError = false) {
  const target = $("#notification-status");
  if (!target) return;
  target.textContent = message;
  target.classList.toggle("error", Boolean(isError));
}

async function refreshNotificationToggle() {
  ensureNotificationToggle();
  const toggle = $("#notification-toggle");
  if (!toggle) return;

  if (!("Notification" in window) || !("PushManager" in window)) {
    toggle.checked = false;
    toggle.disabled = true;
    setNotificationStatus("A push értesítés nem támogatott.", true);
    return;
  }
  if (!isPushSecureContext()) {
    toggle.checked = false;
    toggle.disabled = true;
    setNotificationStatus("A push értesítéshez HTTPS vagy localhost szükséges.", true);
    return;
  }

  let subscription = null;
  try {
    const status = await api("/api/push/status");
    if (!status.configured) {
      toggle.checked = false;
      toggle.disabled = true;
      setNotificationStatus(status.error || "A push értesítések még nincsenek konfigurálva.", true);
      return;
    }
    const keyPayload = await api("/api/push/public-key");
    subscription = await getPushSubscription();
    if (
      Notification.permission === "granted" &&
      subscription &&
      !subscriptionUsesPublicKey(subscription, keyPayload.publicKey)
    ) {
      setNotificationStatus("Push kulcsváltás frissítése...");
      await removeBrowserPushSubscription(subscription);
      await subscribeToPush();
      subscription = await getPushSubscription();
    }
  } catch (error) {
    toggle.checked = false;
    setNotificationStatus(`Push állapot hiba: ${error.message}`, true);
    return;
  }
  toggle.checked = Notification.permission === "granted" && Boolean(subscription);
  toggle.disabled = Notification.permission === "denied";

  if (Notification.permission === "denied") {
    setNotificationStatus("Az értesítések le vannak tiltva.", true);
  } else if (toggle.checked) {
    setNotificationStatus("Bekapcsolva. Értesítést kapsz a holnapi műszakodról és az új dokumentumokról.");
  } else {
    setNotificationStatus("Kikapcsolva.");
  }
}

async function subscribeToPush() {
  if (!isPushSecureContext()) {
    throw new Error("A push értesítés csak HTTPS-en vagy localhoston kapcsolható be.");
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Az értesítési engedély nem lett megadva.");
  }

  const keyPayload = await api("/api/push/public-key");
  if (!keyPayload.publicKey) {
    throw new Error("A VAPID publikus kulcs nem érhető el.");
  }

  const registration = await ensureServiceWorkerRegistration();
  const existingSubscription =
    await registration.pushManager.getSubscription();

  // A korábbi VAPID kulccsal készült feliratkozást újra kell létrehozni.
  if (existingSubscription) {
    await removeBrowserPushSubscription(existingSubscription);
  }

  const applicationServerKey = urlBase64ToUint8Array(keyPayload.publicKey);
  if (applicationServerKey.byteLength !== 65) {
    throw new Error("A VAPID publikus kulcs formátuma hibás.");
  }

  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey,
  });

  const serialized = subscription.toJSON();

  if (
    !serialized.endpoint ||
    !serialized.keys?.p256dh ||
    !serialized.keys?.auth
  ) {
    throw new Error("A böngésző hiányos feliratkozási adatot adott vissza.");
  }

  await api("/api/push/subscribe", {
    method: "POST",
    body: JSON.stringify({
      endpoint: serialized.endpoint,
      keys: serialized.keys,
      user_agent: navigator.userAgent,
    }),
  });
}

async function unsubscribeFromPush() {
  const subscription = await getPushSubscription();
  if (!subscription) return;
  await removeBrowserPushSubscription(subscription);
}

async function handleNotificationToggleChange(event) {
  const toggle = event.currentTarget;
  toggle.disabled = true;
  let hasError = false;

  setNotificationStatus(
    toggle.checked ? "Bekapcsolás…" : "Kikapcsolás…"
  );

  try {
    if (toggle.checked) {
      await subscribeToPush();
    } else {
      await unsubscribeFromPush();
    }
  } catch (error) {
    hasError = true;
    toggle.checked = !toggle.checked;
    setNotificationStatus(
      `Hiba: ${error.message}`,
      true
    );
  } finally {
    toggle.disabled = false;
    if (!hasError) {
      await refreshNotificationToggle();
    }
  }
}


function setBillingMessage(message, isError = false) {
  const target = $("#billing-profile-message");
  if (!target) return;
  target.textContent = message || "";
  target.classList.toggle("error", Boolean(isError));
}

function updateBillingProfileEditState() {
  const form = $("#billing-profile-form");
  if (!form) return;

  const courierIdInput = $("#profile-courier-id");
  const courierId = String(courierIdInput?.value || "").trim();
  if (courierIdInput) {
    courierIdInput.readOnly = Boolean(courierId);
    courierIdInput.toggleAttribute("aria-readonly", Boolean(courierId));
    courierIdInput.classList.toggle("locked", Boolean(courierId));
    courierIdInput.title = courierId
      ? "A futár ID már rögzítve van, ezért nem módosítható."
      : "A futár ID csak addig írható, amíg üres.";
  }

  form.querySelectorAll("input").forEach((input) => {
    if (input.id === "profile-courier-id") return;
    input.readOnly = false;
    input.toggleAttribute("aria-readonly", false);
    input.classList.remove("locked");
  });

  const submitButton = form.querySelector('button[type="submit"]');
  if (submitButton) submitButton.hidden = false;
}

function fillBillingProfile(data = {}) {
  const values = {
    "#profile-courier-id": data.courier_id || state.user?.courier_id || state.user?.id || "",
    "#profile-courier-name": data.courier_name || state.user?.username || "",
    "#profile-phone-number": data.phone_number || state.user?.phone || "",
    "#billing-company-name": data.company_name || "",
    "#billing-company-address": data.company_address || "",
    "#billing-tax-number": data.tax_number || "",
    "#billing-bank-account": data.bank_account_number || "",
    "#billing-email": data.billing_email || "",
  };

  Object.entries(values).forEach(([selector, value]) => {
    const input = $(selector);
    if (input) input.value = value;
  });

  updateBillingProfileEditState();
}

async function loadBillingProfile() {
  updateBillingProfileEditState();
  setBillingMessage("Számlázási adatok betöltése…");

  try {
    const payload = await api("/api/profile/billing");
    // Kezeli mindkét válaszformát: { billing: {...} } vagy közvetlen {...}.
    const billing = payload.billing || payload || {};
    state.billingProfile = billing;
    fillBillingProfile(billing);

    const hasData = [
      billing.company_name,
      billing.company_address,
      billing.tax_number,
      billing.bank_account_number,
      billing.billing_email,
    ].some((value) => String(value || "").trim());

    if (!hasData) {
      setBillingMessage("Ehhez a profilhoz még nincsenek rögzített számlázási adatok.", true);
      return;
    }

    setBillingMessage(
      billing.updated_at
        ? `Utolsó frissítés: ${new Date(billing.updated_at).toLocaleString("hu-HU")}`
        : "A számlázási adatok központilag kezeltek, itt csak megtekinthetők."
    );
  } catch (error) {
    state.billingProfile = null;
    fillBillingProfile({});
    setBillingMessage(`A számlázási adatok nem tölthetők be: ${error.message}`, true);
  }
}

updateBillingProfileEditState();

const billingProfileForm = $("#billing-profile-form");
if (billingProfileForm) {
  billingProfileForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = billingProfileForm.querySelector('button[type="submit"]');
    const payload = {
      courier_id: $("#profile-courier-id")?.value || "",
      courier_name: $("#profile-courier-name")?.value || "",
      phone_number: $("#profile-phone-number")?.value || "",
      company_name: $("#billing-company-name")?.value || "",
      company_address: $("#billing-company-address")?.value || "",
      tax_number: $("#billing-tax-number")?.value || "",
      bank_account_number: $("#billing-bank-account")?.value || "",
      billing_email: $("#billing-email")?.value || "",
    };

    setBillingMessage("Profiladatok mentése folyamatban…");
    if (button) button.disabled = true;
    try {
      const response = await api("/api/profile/billing", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const billing = response.billing || response || {};
      state.billingProfile = billing;
      fillBillingProfile(billing);
      setBillingMessage(
        billing.updated_at
          ? `Profiladatok mentve. Utolsó frissítés: ${new Date(billing.updated_at).toLocaleString("hu-HU")}`
          : "Profiladatok mentve."
      );
    } catch (error) {
      setBillingMessage(`A profiladatok mentése sikertelen: ${error.message}`, true);
    } finally {
      if (button) button.disabled = false;
    }
  });
}


function setDeviceConditionMessage(message, isError = false) {
  const target = $("#device-condition-message");
  if (!target) return;
  target.textContent = message || "";
  target.classList.toggle("error", Boolean(isError));
}

function deviceReportPhotos(photos = []) {
  if (!photos.length) return "";
  return `<div class="device-photo-list">${photos.map((photo, index) => `
    <a href="${escapeHtml(photo.url || "#")}" target="_blank" rel="noopener">
      ${escapeHtml(photo.label || `Fotó ${index + 1}`)}
    </a>
  `).join("")}</div>`;
}

function renderDeviceReports() {
  const target = $("#device-condition-history");
  if (!target) return;
  const reports = state.deviceReports || [];
  if (!reports.length) {
    target.innerHTML = `<div class="empty-card">Még nincs rögzített telefon állapot.</div>`;
    return;
  }

  target.innerHTML = `
    <div class="device-history-head">
      <strong>Előzmények</strong>
      <span>${reports.length} bejegyzés</span>
    </div>
    ${reports.map((report) => `
      <article class="device-report">
        <div>
          <strong>${escapeHtml(report.serialNumber || "-")}</strong>
          <small>${escapeHtml(report.label || "Ellenőrzés")} · ${report.reportedAt ? new Date(report.reportedAt).toLocaleString("hu-HU") : ""}</small>
          ${report.imei ? `<small>IMEI: ${escapeHtml(report.imei)}</small>` : ""}
        </div>
        ${report.note ? `<p>${escapeHtml(report.note)}</p>` : ""}
        <div class="device-report-meta">
          <span>${Number(report.photoCount || 0)} fotó</span>
        </div>
        ${deviceReportPhotos(report.photos || [])}
      </article>
    `).join("")}
  `;
}

async function loadDeviceReports() {
  const target = $("#device-condition-history");
  if (!target) return;
  target.innerHTML = `<div class="empty-card">Telefon előzmények betöltése...</div>`;
  try {
    const payload = await api("/api/devices/reports");
    state.deviceReports = payload.reports || [];
    renderDeviceReports();
  } catch (error) {
    target.innerHTML = `<div class="notice error">A telefon előzmények nem tölthetők be: ${escapeHtml(error.message)}</div>`;
  }
}

const deviceConditionForm = $("#device-condition-form");
if (deviceConditionForm) {
  deviceConditionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = deviceConditionForm.querySelector('button[type="submit"]');
    const photos = $("#device-condition-photos")?.files || [];
    if (!photos.length) {
      setDeviceConditionMessage("Legalább egy fotót fel kell tölteni.", true);
      return;
    }

    const form = new FormData(deviceConditionForm);
    setDeviceConditionMessage("Telefon állapot mentése...");
    if (button) button.disabled = true;
    try {
      await api("/api/devices/reports", { method: "POST", body: form });
      deviceConditionForm.reset();
      setDeviceConditionMessage("Telefon állapot rögzítve.");
      await loadDeviceReports();
    } catch (error) {
      setDeviceConditionMessage(`A telefon állapot mentése sikertelen: ${error.message}`, true);
    } finally {
      if (button) button.disabled = false;
    }
  });
}

const passwordChangeForm = $("#password-change-form");
if (passwordChangeForm) {
  passwordChangeForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const message = $("#password-change-message");
    const currentPassword = $("#current-password").value;
    const newPassword = $("#new-password").value;
    const confirmPassword = $("#new-password-confirm").value;
    if (newPassword !== confirmPassword) {
      message.textContent = "Az új jelszavak nem egyeznek.";
      return;
    }
    message.textContent = "Jelszó módosítása...";
    try {
      await api("/api/profile/password", {
        method: "PUT",
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      passwordChangeForm.reset();
      message.textContent = "A jelszó módosítva.";
    } catch (error) {
      message.textContent = error.message;
    }
  });
}


function renderValidation(target, validation, stored = null) {
  if (!target) return;
  const summary = validation.ok
    ? stored === true ? "A számla feltöltve, ellenőrizve és eltárolva." : "Az ellenőrzés sikeres."
    : stored === true ? "A számla feltöltve, manuális ellenőrzésre került. Kérlek légy türelemmel." : `Manuális ellenőrzés szükséges (${validation.score}%).`;
  target.innerHTML = `<div class="result-box">
    <div class="result-summary ${validation.ok ? "ok" : "error"}">${escapeHtml(summary)}</div>
    ${(validation.checks || []).map((check) => `<div class="check-row ${escapeHtml(check.status)}"><strong>${escapeHtml(check.title)}</strong><br>${escapeHtml(check.detail)}</div>`).join("")}
  </div>`;
}

function fillInvoiceSubmitFromValidation(validation) {
  const parsed = validation?.parsed || {};
  const invoiceNumber = $("#invoice-number");
  const grossAmount = $("#gross-amount");
  const tigReference = $("#tig-reference");

  if (invoiceNumber && parsed.invoiceNumber) {
    invoiceNumber.value = parsed.invoiceNumber;
  }
  if (grossAmount && Number(parsed.grossTotal || 0) > 0) {
    grossAmount.value = String(parsed.grossTotal);
  }
  if (tigReference && !tigReference.value.trim()) {
    const courierId = state.user?.courier_id || state.user?.id || "";
    tigReference.value = courierId
      ? `${courierId} - ${state.workflowMonth}`
      : state.workflowMonth;
  }
}

const invoiceCheckForm = $("#invoice-check-form");
if (invoiceCheckForm) invoiceCheckForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const checkedFile = form.get("invoice_file");
  form.append("month", state.workflowMonth);
  form.append("process", state.workflowProcess);
  showWorkflowMessage("A számla ellenőrzése folyamatban…");
  try {
    const payload = await api("/api/invoices/check", { method: "POST", body: form });
    state.workflow = payload.workflow;
    renderWorkflow();
    renderValidation($("#invoice-check-result"), payload.validation);
    if (payload.validation?.ok) {
      state.checkedInvoiceFile = checkedFile instanceof File && checkedFile.name ? checkedFile : null;
      state.checkedInvoiceMonth = state.workflowMonth;
      fillInvoiceSubmitFromValidation(payload.validation);
    }
    showWorkflowMessage(payload.validation.ok ? "Sikeres ellenőrzés. A 6. lépés számlaadatait automatikusan kitöltöttem." : "A hibákat javítani kell a feltöltés előtt.", !payload.validation.ok);
  } catch (error) {
    showWorkflowMessage(error.message, true);
  }
});

$("#invoice-submit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (workflowStep("invoice_submit").done || (state.workflow?.documents?.invoice || []).length) {
    showWorkflowMessage("Ehhez a folyamathoz már érkezett számla, új feltöltés nem indítható.", true);
    return;
  }
  const submitButton = event.currentTarget.querySelector('button[type="submit"]');
  if (submitButton) submitButton.disabled = true;
  const form = new FormData(event.currentTarget);
  const selectedInvoiceFile = form.get("invoice_file");
  const hasSelectedInvoiceFile =
    selectedInvoiceFile instanceof File && Boolean(selectedInvoiceFile.name);
  if (!hasSelectedInvoiceFile && state.checkedInvoiceFile && state.checkedInvoiceMonth === state.workflowMonth) {
    form.set("invoice_file", state.checkedInvoiceFile);
  } else if (!hasSelectedInvoiceFile) {
    showWorkflowMessage("Válaszd ki a feltöltendő számla PDF-et.", true);
    return;
  }
  form.append("month", state.workflowMonth);
  form.append("process", state.workflowProcess);
  const selectedCashInvoiceFile = form.get("cash_invoice_file");
  const hasCashInvoiceFile =
    selectedCashInvoiceFile instanceof File && Boolean(selectedCashInvoiceFile.name);
  showWorkflowMessage(
    hasCashInvoiceFile
      ? "A normál és a KP számla ellenőrzése és tárolása folyamatban…"
      : "A számla végső ellenőrzése és tárolása folyamatban…"
  );
  try {
    const payload = await api("/api/invoices/submit", { method: "POST", body: form });
    state.workflow = payload.workflow;
    renderWorkflow();
    renderValidation($("#invoice-submit-result"), payload.validation, payload.stored);
    showWorkflowMessage(
      payload.manualReview
        ? `${payload.storedCount || 1} számla bekerült hozzánk, manuális ellenőrzésre ment. Kérlek légy türelemmel.`
        : payload.stored
          ? `${payload.storedCount || 1} számla bekerült a dokumentumtárba és az ellenőrzés sikeres.`
        : "A számla nem került eltárolásra, mert hibát találtunk.",
      !payload.stored
    );
    if (payload.stored) {
      event.currentTarget.reset();
      state.checkedInvoiceFile = null;
      state.checkedInvoiceMonth = null;
    }
  } catch (error) {
    showWorkflowMessage(error.message, true);
  } finally {
    if (submitButton && !workflowStep("invoice_submit").done && !(state.workflow?.documents?.invoice || []).length) {
      submitButton.disabled = false;
    }
  }
});

function coordinatorItems(kind) {
  return state.coordinatorSetup?.items?.[kind] || [];
}

function renderCoordinatorItems() {
  const kind = $("#coordinator-kind").value || "bonus";
  const items = coordinatorItems(kind);
  $("#coordinator-item").innerHTML = items.length
    ? items.map((item) => `<option value="${escapeHtml(item.id)}" data-amount="${Number(item.default_amount_huf || 0)}">${escapeHtml(item.item_name)}</option>`).join("")
    : `<option value="">Nincs aktív tétel</option>`;
  const firstAmount = Number(items[0]?.default_amount_huf || 0);
  if (firstAmount > 0) $("#coordinator-amount").value = String(firstAmount);
}

function renderCoordinatorAdjustments() {
  const setup = state.coordinatorSetup || { couriers: [], items: {}, entries: {} };
  $("#coordinator-courier").innerHTML = (setup.couriers || [])
    .map((courier) => `<option value="${escapeHtml(courier.courier_id)}">${escapeHtml(courier.courier_name)} · #${escapeHtml(courier.courier_id)}</option>`)
    .join("");
  renderCoordinatorItems();

  const entries = [
    ...(setup.entries?.bonus || []).map((entry) => ({ ...entry, kind: "bonus" })),
    ...(setup.entries?.malus || []).map((entry) => ({ ...entry, kind: "malus" })),
  ].sort((a, b) => String(b.recorded_at || "").localeCompare(String(a.recorded_at || "")));
  const container = $("#coordinator-entry-list");
  if (!entries.length) {
    container.innerHTML = `<h3>Legutóbbi rögzítések</h3><p class="muted">Még nincs aktív bónusz vagy málusz.</p>`;
    return;
  }
  container.innerHTML = `<h3>Legutóbbi rögzítések</h3>${entries.map((entry) => {
    const sign = entry.kind === "bonus" ? "+" : "-";
    const amount = new Intl.NumberFormat("hu-HU").format(Number(entry.amount_huf || 0));
    const recordedAt = entry.recorded_at ? new Date(entry.recorded_at).toLocaleString("hu-HU") : "";
    return `<article class="adjustment-entry">
      <div class="adjustment-entry-head">
        <div><strong>${escapeHtml(entry.courier_name)}</strong><small>${escapeHtml(entry.item_name)} · ${escapeHtml(entry.effective_date || "")}</small></div>
        <span class="adjustment-amount ${entry.kind}">${sign}${amount} Ft</span>
      </div>
      ${entry.note ? `<p>${escapeHtml(entry.note)}</p>` : ""}
      <small>Rögzítette: ${escapeHtml(entry.recorded_by || "-")} · ${escapeHtml(recordedAt)}</small>
      <button class="secondary coordinator-delete" type="button" data-kind="${entry.kind}" data-id="${escapeHtml(entry.id)}">Visszavonás</button>
    </article>`;
  }).join("")}`;
}

async function loadCoordinatorAdjustments() {
  const message = $("#coordinator-message");
  message.textContent = "Adatok frissítése…";
  try {
    state.coordinatorSetup = await api("/api/coordinator-adjustments");
    renderCoordinatorAdjustments();
    message.textContent = "Frissítve.";
  } catch (error) {
    message.textContent = error.message;
  }
}

$("#coordinator-kind").addEventListener("change", renderCoordinatorItems);
$("#coordinator-item").addEventListener("change", (event) => {
  const option = event.currentTarget.selectedOptions[0];
  const amount = Number(option?.dataset?.amount || 0);
  if (amount > 0) $("#coordinator-amount").value = String(amount);
});
$("#coordinator-refresh").addEventListener("click", loadCoordinatorAdjustments);
$("#coordinator-adjustment-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = $("#coordinator-message");
  message.textContent = "Rögzítés…";
  try {
    const payload = await api("/api/coordinator-adjustments", {
      method: "POST",
      body: JSON.stringify({
        kind: $("#coordinator-kind").value,
        courier_id: $("#coordinator-courier").value,
        item_id: $("#coordinator-item").value,
        amount_huf: Number($("#coordinator-amount").value || 0),
        note: $("#coordinator-note").value,
        effective_date: $("#coordinator-date").value,
      }),
    });
    state.coordinatorSetup = payload.setup;
    renderCoordinatorAdjustments();
    $("#coordinator-note").value = "";
    message.textContent = "A tétel naplózva és rögzítve.";
  } catch (error) {
    message.textContent = error.message;
  }
});
$("#coordinator-entry-list").addEventListener("click", async (event) => {
  const button = event.target.closest(".coordinator-delete");
  if (!button) return;
  const reason = window.prompt("Miért vonod vissza ezt a tételt?");
  if (!reason?.trim()) return;
  button.disabled = true;
  try {
    const payload = await api(`/api/coordinator-adjustments/${encodeURIComponent(button.dataset.kind)}/${encodeURIComponent(button.dataset.id)}/delete`, {
      method: "POST",
      body: JSON.stringify({ reason: reason.trim() }),
    });
    state.coordinatorSetup = payload.setup;
    renderCoordinatorAdjustments();
    $("#coordinator-message").textContent = "A tétel visszavonva; az auditnaplóban megmaradt.";
  } catch (error) {
    button.disabled = false;
    $("#coordinator-message").textContent = error.message;
  }
});

$("#workflow-month").value = state.workflowMonth;
const workflowPreviewCourierInput = $("#workflow-preview-courier");
if (workflowPreviewCourierInput) workflowPreviewCourierInput.value = state.workflowPreviewCourierId;
renderWorkflowProcessPicker();
$("#statistics-month").value = state.statisticsMonth;
$("#coordinator-date").value = localDate();
$("#workflow-month").addEventListener("change", (event) => {
  state.workflowMonth = event.target.value || new Date().toISOString().slice(0, 7);
  state.workflow = null;
  state.checkedInvoiceFile = null;
  state.checkedInvoiceMonth = null;
  loadWorkflow();
});

$("#workflow-process").addEventListener("change", (event) => {
  state.workflowProcess = event.target.value || "";
  state.workflow = null;
  state.checkedInvoiceFile = null;
  state.checkedInvoiceMonth = null;
  loadWorkflow();
});

workflowPreviewCourierInput?.addEventListener("change", (event) => {
  state.workflowPreviewCourierId = String(event.target.value || "").trim();
  state.workflowProcess = "";
  state.workflow = null;
  state.checkedInvoiceFile = null;
  state.checkedInvoiceMonth = null;
  loadWorkflow();
});

$("#workflow-refresh").addEventListener("click", () => {
  loadWorkflow();
});

$("#statistics-month").addEventListener("change", (event) => {
  state.statisticsMonth = event.target.value || new Date().toISOString().slice(0, 7);
  state.statistics = null;
  loadStatistics();
});

$("#statistics-refresh").addEventListener("click", () => {
  state.statistics = null;
  loadStatistics();
});

$("#salary-advance-start-date").value = state.workflowMonth;
updateSalaryAdvancePreview();
["#salary-advance-amount", "#salary-advance-months"].forEach((selector) => {
  $(selector)?.addEventListener("input", updateSalaryAdvancePreview);
});
$("#salary-advance-refresh")?.addEventListener("click", loadSalaryAdvanceRequests);
$("#salary-advance-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const message = $("#salary-advance-message");
  if (button) button.disabled = true;
  if (message) message.textContent = "Igény mentése...";
  try {
    const month = $("#salary-advance-start-date").value || state.workflowMonth;
    const payload = await api("/api/salary-advance/requests", {
      method: "POST",
      body: JSON.stringify({
        start_date: `${month}-01`,
        requested_amount_huf: parseHufInput($("#salary-advance-amount").value),
        installment_months: Number($("#salary-advance-months").value || 1),
        note: $("#salary-advance-note").value || "",
      }),
    });
    state.salaryAdvanceRequests = payload.requests || [];
    renderSalaryAdvanceRequests();
    form.reset();
    $("#salary-advance-start-date").value = state.workflowMonth;
    $("#salary-advance-months").value = "1";
    updateSalaryAdvancePreview();
    if (message) message.textContent = "Az előleg igény rögzítve, jóváhagyásra vár.";
  } catch (error) {
    if (message) message.textContent = error.message;
  } finally {
    if (button) button.disabled = false;
  }
});

function showAuthPanel(panel) {
  const loginForm = $("#login-form");
  const registerForm = $("#register-form");
  const resetForm = $("#password-reset-form");
  const links = document.querySelector(".auth-links");
  if (loginForm) loginForm.classList.toggle("hidden", panel !== "login");
  if (registerForm) registerForm.classList.toggle("hidden", panel !== "register");
  if (resetForm) resetForm.classList.toggle("hidden", panel !== "reset");
  if (links) links.classList.toggle("hidden", panel !== "login");
  $("#login-error").textContent = "";
  const registerMessage = $("#register-message");
  const resetMessage = $("#password-reset-message");
  if (registerMessage) registerMessage.textContent = "";
  if (resetMessage) resetMessage.textContent = "";
}

function setAuthMessage(selector, message, isError = false) {
  const target = $(selector);
  if (!target) return;
  target.textContent = message || "";
  target.classList.toggle("success", !isError && Boolean(message));
  target.classList.toggle("error", Boolean(isError));
}

$("#show-register")?.addEventListener("click", () => showAuthPanel("register"));
$("#show-password-reset")?.addEventListener("click", () => showAuthPanel("reset"));
document.querySelectorAll("[data-auth-back]").forEach((button) => {
  button.addEventListener("click", () => showAuthPanel("login"));
});

$("#login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("#login-error").textContent = "";
  try {
    const payload = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ username: $("#username").value, password: $("#password").value }),
    });
    state.user = payload.user;
    showApp();
    showSection("home");
    await loadShifts();
  } catch (error) {
    $("#login-error").textContent = error.message;
  }
});

$("#register-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  setAuthMessage("#register-message", "Regisztracio ellenorzese...");
  if (button) button.disabled = true;
  const payload = {
    courier_id: $("#register-courier-id").value,
    courier_name: $("#register-name").value,
    phone_number: $("#register-phone").value,
    email: $("#register-email").value,
  };
  try {
    const response = await api("/api/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (response.redirect === "password_reset") {
      $("#reset-courier-id").value = payload.courier_id;
      $("#reset-email").value = payload.email;
      showAuthPanel("reset");
      setAuthMessage(
        "#password-reset-message",
        response.emailUpdated
          ? "A futar ID mar szerepel a torzsben. Az e-mail cimet frissitettuk, innen tudsz jelszot kerni."
          : "A futar ID mar szerepel a torzsben. Innen tudsz jelszot kerni."
      );
      return;
    }
    form.reset();
    setAuthMessage("#register-message", response.message || "Regisztracio rogzitve.");
  } catch (error) {
    setAuthMessage("#register-message", error.message, true);
  } finally {
    if (button) button.disabled = false;
  }
});

$("#password-reset-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  setAuthMessage("#password-reset-message", "Belepesi adatok kuldese...");
  if (button) button.disabled = true;
  try {
    const response = await api("/api/password-reset", {
      method: "POST",
      body: JSON.stringify({
        courier_id: $("#reset-courier-id").value,
        email: $("#reset-email").value,
      }),
    });
    form.reset();
    setAuthMessage(
      "#password-reset-message",
      response.emailUpdated
        ? "E-mail cim frissitve, a belepesi adatokat elkuldtuk."
        : response.message || "A belepesi adatokat elkuldtuk."
    );
  } catch (error) {
    setAuthMessage("#password-reset-message", error.message, true);
  } finally {
    if (button) button.disabled = false;
  }
});

$("#logout").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  state.user = null;
  state.workflow = null;
  state.billingProfile = null;
  state.checkedInvoiceFile = null;
  state.checkedInvoiceMonth = null;
  state.coordinatorSetup = null;
  state.deviceReports = [];
  state.salaryAdvanceRequests = [];
  state.statistics = null;
  showLogin();
});
$("#refresh").addEventListener("click", loadShifts);
$("#nav-home").addEventListener("click", () => showSection("home"));
$("#nav-settlement").addEventListener("click", () => showSection("settlement"));
$("#nav-statistics").addEventListener("click", () => showSection("statistics"));
$("#nav-salary-advance").addEventListener("click", () => showSection("salary-advance"));
$("#nav-documents").addEventListener("click", () => showSection("documents"));
$("#nav-profile").addEventListener("click", () => showSection("profile"));
$("#nav-device").addEventListener("click", () => showSection("device"));
$("#nav-tours").addEventListener("click", () => showSection("tours"));
$("#nav-coordinator").addEventListener("click", () => showSection("coordinator"));

async function start() {
  try {
    const payload = await api("/api/me");
    state.user = payload.user;
    showApp();
    if (String(state.user.role || "").toLowerCase() === "coordinator") {
      showSection("coordinator");
    } else {
      showSection("home");
      await loadShifts();
    }
  } catch (_) {
    showLogin();
  }
  if ("serviceWorker" in navigator) {
    ensureServiceWorkerRegistration().catch((error) => {
      console.warn("Service worker registration failed", error);
    });
  }
}

start();
