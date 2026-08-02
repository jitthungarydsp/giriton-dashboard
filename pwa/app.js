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
  statistics: null,
  serviceWorkerRegistration: null,
  workflowMonth: new Date().toISOString().slice(0, 7),
  statisticsMonth: new Date().toISOString().slice(0, 7),
  section: "home",
};
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
  const response = await fetch(path, { credentials: "same-origin", ...options, headers });
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
  ["#nav-home", "#nav-settlement", "#nav-statistics", "#nav-documents", "#nav-profile", "#nav-tours"]
    .forEach((selector) => $(selector).classList.toggle("hidden", coordinatorOnly));
}

function showSection(section) {
  state.section = section;
  $("#home-content").classList.toggle("hidden", section !== "home");
  $("#settlement-content").classList.toggle("hidden", section !== "settlement");
  $("#statistics-content").classList.toggle("hidden", section !== "statistics");
  $("#documents-content").classList.toggle("hidden", section !== "documents");
  $("#profile-content").classList.toggle("hidden", section !== "profile");
  $("#tours-content").classList.toggle("hidden", section !== "tours");
  $("#coordinator-content").classList.toggle("hidden", section !== "coordinator");

  $("#nav-home").classList.toggle("active", section === "home");
  $("#nav-settlement").classList.toggle("active", section === "settlement");
  $("#nav-statistics").classList.toggle("active", section === "statistics");
  $("#nav-documents").classList.toggle("active", section === "documents");
  $("#nav-profile").classList.toggle("active", section === "profile");
  $("#nav-tours").classList.toggle("active", section === "tours");
  $("#nav-coordinator").classList.toggle("active", section === "coordinator");

  if (section === "settlement" && !state.workflow) loadWorkflow();
  if (section === "statistics" && !state.statistics) loadStatistics();
  if (section === "documents") loadDocuments();
  if (section === "profile") {
    loadBillingProfile();
    loadDeviceReports();
    refreshNotificationToggle();
  }
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

function statisticCard(label, value, note = "") {
  return `
    <article class="stat-card">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      ${note ? `<small>${escapeHtml(note)}</small>` : ""}
    </article>
  `;
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
    statisticCard("Késéses cím", formatCount(summary.delayedOrders), "Dataport"),
    statisticCard("Késés", formatCount(summary.lateCount), "műszak"),
    statisticCard("No-show", formatCount(summary.noShowCount), "műszak"),
    statisticCard("Műszak", formatCount(summary.shiftCount), "összes"),
    statisticCard("Borravaló", formatHuf(summary.tipsTotalHuf), "összesen"),
    statisticCard("Futár bevétele", "Rejtve", "mobil nézetben"),
    statisticCard("Ügyfélértékelés", ratingValue, rating.available ? `${formatCount(rating.ratingCount)} értékelés` : "későbbi kimutatáshoz"),
  ].join("");

  const routeBreakdown = payload.routeBreakdown || {};
  const quality = payload.dataQuality || {};
  breakdown.innerHTML = `
    <div class="process-title">
      <span class="step-code">∑</span>
      <div>
        <h3>Túra bontás</h3>
        <p>A besorolás az érvényes szabályokat figyeli, ha vannak szabályok a DB-ben.</p>
      </div>
    </div>
    <div class="stat-breakdown-list">
      <div class="stat-row"><span>Kiemelt napi kör</span><strong>${formatCount(routeBreakdown.highlightedRoutes)}</strong></div>
      <div class="stat-row"><span>Nem kiemelt napi kör</span><strong>${formatCount(routeBreakdown.normalDayRoutes)}</strong></div>
      <div class="stat-row"><span>Express kör</span><strong>${formatCount(routeBreakdown.expressRoutes)}</strong></div>
      <div class="stat-row"><span>Express cím</span><strong>${formatCount(routeBreakdown.expressOrders)}</strong></div>
      <div class="stat-row"><span>Normál kör</span><strong>${formatCount(routeBreakdown.normalRoutes)}</strong></div>
      <div class="stat-row"><span>Regionális kör</span><strong>${formatCount(routeBreakdown.regionalRoutes)}</strong></div>
    </div>
    <p class="updated-at">Forrás: ${escapeHtml(quality.routeSource || "nincs route raw adat")} · napi sor: ${formatCount(quality.dailyRows)} · szabály: ${escapeHtml(quality.dayRuleSource || "-")}</p>
  `;
}

async function loadStatistics() {
  const monthInput = $("#statistics-month");
  if (monthInput?.value) state.statisticsMonth = monthInput.value;
  $("#statistics-message").innerHTML = `<div class="notice">Statisztika betöltése...</div>`;
  try {
    state.statistics = await api(`/api/statistics/monthly?month=${encodeURIComponent(state.statisticsMonth)}`);
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
    <form id="delay-alert-form" method="dialog" class="process-form">
      <h3>Problémám van</h3>

      <label>
        Mi a probléma?
        <textarea
          id="delay-alert-message"
          rows="4"
          required
        ></textarea>
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
  $("#delay-alert-form").addEventListener(
    "submit",
    submitDelayAlert
  );

  return dialog;
}

function openDelayAlertDialog() {
  const dialog = ensureDelayAlertDialog();
  $("#delay-alert-message").value = "";
  $("#dispatcher-notified").checked = false;
  $("#delay-alert-status").textContent = "";
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
    await api("/api/routes/delay-alert", {
      method: "POST",
      body: JSON.stringify({
        route_id: route.routeId,
        order_id: current?.orderId || "",
        message: $("#delay-alert-message").value.trim(),
        dispatcher_notified: $("#dispatcher-notified").checked,
        current_address: current?.address || "",
        current_checkpoint_position: current?.position ?? null,
      }),
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

function workflowStep(key) {
  return state.workflow?.steps?.find((step) => step.key === key) || {};
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
      state.workflow = await api(`/api/workflow?month=${encodeURIComponent(state.workflowMonth)}`);
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

function renderDocumentPanel(action, title, stepNumber) {
  const panel = $(`#${action}-panel`);
  const documents = state.workflow?.documents?.[action] || [];
  const complaints = state.workflow?.complaints?.[action] || [];
  const complaintResponses = state.workflow?.complaintResponses?.[action] || [];
  const ignoreComplaints = Boolean(state.workflow?.ignoreComplaintsForBilling);
  const hasOpenComplaint = !ignoreComplaints && complaints.some((complaint) => {
    const status = String(complaint.status || "").trim().toLowerCase();
    const hasAdminAnswer = Boolean(
      String(complaint.admin_response || "").trim()
      || String(complaint.responded_at || "").trim()
    );
    return status !== "resolved" && !hasAdminAnswer;
  });
  const accepted = state.workflow?.states?.[action]?.status === "done";
  const documentStep = workflowStep(`${action}_document`);
  const locked = Boolean(documentStep.locked);
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
  panel.innerHTML = `
    <div class="process-title"><span class="step-code">${stepNumber}</span><div><h3>${visibleTitle}</h3><p>${description}</p></div></div>
    ${locked ? `<div class="empty-card">🔒 Az előző lépés még nincs lezárva.</div>` : documentList(documents)}
    ${accepted
      ? `<div class="accept-row done">✓ A dokumentumot elfogadtad.</div>`
      : documents.length && !locked && !hasOpenComplaint
        ? `<div class="accept-row"><button class="primary" id="accept-${action}">✓ Elfogadom a dokumentumot</button></div>`
        : documents.length && !locked && hasOpenComplaint
          ? `<div class="accept-row"><button class="primary" disabled>Reklamacio lezarasaig nem fogadhato el</button></div>`
          : ""}
    ${documents.length && !locked ? `<div class="complaint-box">
      <strong>Reklamáció</strong>
      ${complaintList(complaints)}
      ${complaintResponseList(complaintResponses)}
      <form id="complaint-${action}"><label>Mi a gond?<textarea name="message" placeholder="Írd le röviden, mit kell javítani vagy ellenőrizni." required></textarea></label><button class="secondary" type="submit">Reklamáció küldése</button></form>
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

function renderWorkflow() {
  renderWorkflowSteps();
  renderDocumentPanel("settlement", "Elszámolás és elfogadás", 1);
  renderDocumentPanel("tig", "TIG és elfogadás", 3);
  setPanelLocked("#invoice-check-panel", Boolean(workflowStep("invoice_check").locked));
  setPanelLocked("#invoice-submit-panel", Boolean(workflowStep("invoice_submit").locked));
  const overrideNotice = state.workflow?.invoiceValidationOverride
    ? `<div class="notice">Admin továbbengedés aktív: a számlaellenőrzési hibák figyelmeztetésként kezelődnek.</div>`
    : "";
  const checkInfo = $("#invoice-check-info");
  if (checkInfo) checkInfo.innerHTML = `${overrideNotice}${complaintList(state.workflow?.complaints?.invoice_check || [])}`;
  const submitInfo = $("#invoice-submit-info");
  if (submitInfo) submitInfo.innerHTML = `${overrideNotice}${complaintList(state.workflow?.complaints?.invoice_submit || [])}`;
  $("#invoice-document-list").innerHTML = (state.workflow?.documents?.invoice || []).length
    ? `<div class="complaint-box"><strong>Korábban feltöltött számlák</strong>${documentList(state.workflow.documents.invoice)}</div>`
    : "";
  renderDocumentsSection();
  $("#workflow-updated-at").textContent = `Frissítve: ${new Date(state.workflow.updatedAt).toLocaleString("hu-HU")}`;
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
    ["invoice_check", "Számlaellenőrzés", true],
    ["invoice_submit", "Számlafeltöltés", true],
    ["invoice_payment", "Admin számlaelfogadás és kifizetés", true],
  ];
  return {
    month: state.workflowMonth,
    steps: titles.map(([key, title, locked]) => ({ key, title, locked, done: false })),
    states: {},
    documents: { settlement: [], tig: [], invoice: [] },
    complaints: { settlement: [], tig: [], invoice_check: [], invoice_submit: [] },
    complaintResponses: { settlement: [], tig: [], invoice_check: [], invoice_submit: [] },
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
    state.workflow = await api(`/api/workflow?month=${encodeURIComponent(state.workflowMonth)}`);
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
      body: JSON.stringify({ month: state.workflowMonth }),
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
  const message = new FormData(event.currentTarget).get("message");
  showWorkflowMessage("Reklamáció küldése…");
  try {
    const payload = await api("/api/workflow/complaints", {
      method: "POST",
      body: JSON.stringify({ month: state.workflowMonth, action, message }),
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
      body: JSON.stringify({ month: state.workflowMonth, action, message }),
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
    state.serviceWorkerRegistration = await navigator.serviceWorker.register("/sw.js?v=29");
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


function renderValidation(target, validation, stored = null) {
  const summary = validation.ok
    ? stored === true ? "A számla ellenőrizve és eltárolva." : "Az ellenőrzés sikeres. A számlafeltöltés aktív."
    : `Javítandó számla (${validation.score}%).`;
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

$("#invoice-check-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  const checkedFile = form.get("invoice_file");
  form.append("month", state.workflowMonth);
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
  const form = new FormData(event.currentTarget);
  const selectedInvoiceFile = form.get("invoice_file");
  const hasSelectedInvoiceFile =
    selectedInvoiceFile instanceof File && Boolean(selectedInvoiceFile.name);
  if (!hasSelectedInvoiceFile && state.checkedInvoiceFile && state.checkedInvoiceMonth === state.workflowMonth) {
    form.set("invoice_file", state.checkedInvoiceFile);
  } else if (!hasSelectedInvoiceFile) {
    showWorkflowMessage("Előbb ellenőrizd a számlát az 5. lépésben, vagy válassz PDF-et a 6. lépésnél.", true);
    return;
  }
  form.append("month", state.workflowMonth);
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
      payload.stored
        ? `${payload.storedCount || 1} számla bekerült a dokumentumtárba.`
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
$("#statistics-month").value = state.statisticsMonth;
$("#coordinator-date").value = localDate();
$("#workflow-month").addEventListener("change", (event) => {
  state.workflowMonth = event.target.value || new Date().toISOString().slice(0, 7);
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
  state.statistics = null;
  showLogin();
});
$("#refresh").addEventListener("click", loadShifts);
$("#nav-home").addEventListener("click", () => showSection("home"));
$("#nav-settlement").addEventListener("click", () => showSection("settlement"));
$("#nav-statistics").addEventListener("click", () => showSection("statistics"));
$("#nav-documents").addEventListener("click", () => showSection("documents"));
$("#nav-profile").addEventListener("click", () => showSection("profile"));
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
