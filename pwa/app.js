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
  vehicleReports: [],
  vehicleAssignments: [],
  vehicleSearchResults: [],
  queueStatus: null,
  queueTimer: null,
  salaryAdvanceRequests: [],
  expenseRequests: [],
  atmPayments: [],
  game: null,
  gameStartedAt: null,
  statistics: null,
  openMuszakproShifts: null,
  serviceWorkerRegistration: null,
  workflowMonth: new Date().toISOString().slice(0, 7),
  workflowProcess: "",
  workflowProcesses: [{ id: "", label: "Havi folyamat" }],
  workflowPreviewCourierId: "",
  statisticsMonth: new Date().toISOString().slice(0, 7),
  statisticsDay: "",
  statisticsHistoryDate: "",
  statisticsQualityTopic: "",
  statisticsRequestSeq: 0,
  section: "home",
  routeAutoDelayKeys: new Set(),
};
const APP_VERSION = "v90";
const $ = (selector) => document.querySelector(selector);
const QUEUE_STORAGE_KEY = "giriton-active-queue";
const PHONEBOOK_CONTACTS = [
  { label: "Diszpécser", phone: "+3612000391", note: "Kifli támogatás" },
  { label: "FC2 Diszpécser", phone: "+3612002763", note: "FC2 támogatás" },
  { label: "FC2 Logisztikai műszakvezető", phone: "+3612069507", note: "Logisztikai vezető" },
  { label: "FC1 Logisztikai műszakvezető", phone: "+3612001147", note: "Logisztikai vezető" },
  { label: "Ügyfélszolgálat", phone: "0612000881", note: "Központi ügyfélszolgálat" },
];

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

function previewCourierValue() {
  if (!state.user?.canPreviewCouriers) return "";
  return String(state.workflowPreviewCourierId || "").trim();
}

function isAdminPreviewMode() {
  return Boolean(previewCourierValue());
}

function withPreviewCourier(path) {
  const courier = previewCourierValue();
  if (!courier) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}courier=${encodeURIComponent(courier)}`;
}

function currentSectionRefresh() {
  if (!state.user) return Promise.resolve();
  if (state.section === "home") return loadShifts();
  if (state.section === "tours") return loadCurrentRoute();
  if (state.section === "statistics") return loadStatistics();
  if (state.section === "workflow") return loadWorkflow();
  if (state.section === "atm") return loadAtmPayments();
  if (state.section === "expense") return loadExpenseRequests();
  if (state.section === "vehicle") return loadVehicleSection();
  if (state.section === "game") return loadGame();
  return Promise.resolve();
}

function setAdminPreviewStatus(message = "") {
  const target = $("#admin-preview-status");
  if (target) target.textContent = message;
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

function activeShift(items = []) {
  const now = new Date();
  return [...items]
    .filter((item) => item.date && item.start)
    .find((item) => {
      const start = shiftDateTime(item, "start");
      const end = shiftDateTime(item, "end");
      if (!start) return false;
      const effectiveEnd = end || new Date(start.getTime() + 8 * 60 * 60 * 1000);
      return start <= now && now <= effectiveEnd;
    }) || null;
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

  return activeShift(sorted) || sorted.find((item) => {
    const start = shiftDateTime(item, "start");
    return start && start >= now;
  }) || null;
}

function queueStorageRead() {
  try {
    return JSON.parse(localStorage.getItem(QUEUE_STORAGE_KEY) || "null") || null;
  } catch (_error) {
    return null;
  }
}

function queueStorageWrite(queue) {
  if (queue?.active && queue.queuedAt) {
    localStorage.setItem(QUEUE_STORAGE_KEY, JSON.stringify(queue));
  } else {
    localStorage.removeItem(QUEUE_STORAGE_KEY);
  }
}

function queueElapsedText(queuedAt) {
  const start = new Date(queuedAt);
  if (Number.isNaN(start.getTime())) return "00:00";
  const totalSeconds = Math.max(0, Math.floor((Date.now() - start.getTime()) / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return hours > 0
    ? `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
    : `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function activeQueue() {
  return state.queueStatus?.active ? state.queueStatus : queueStorageRead();
}

function clearActiveQueue() {
  state.queueStatus = null;
  queueStorageWrite(null);
  renderQueueStatus();
}

function renderQueueStatus() {
  const target = $("#queue-status-panel");
  if (!target) return;
  const queue = activeQueue();
  if (!queue?.active || !queue.queuedAt) {
    target.innerHTML = "";
    target.classList.add("hidden");
    return;
  }
  target.classList.remove("hidden");
  target.innerHTML = `
    <section class="queue-status-card">
      <div>
        <span>Sorban várakozás</span>
        <strong>${escapeHtml(queueElapsedText(queue.queuedAt))}</strong>
        <small>${escapeHtml(queue.warehouse || queue.shiftName || "Aktív sorba állás")}</small>
      </div>
      <div>
        <span>Előtted vár</span>
        <strong>${formatCount(queue.aheadCount || 0)}</strong>
        <small>kolléga</small>
      </div>
    </section>
  `;
}

function startQueueTimer() {
  if (state.queueTimer) return;
  state.queueTimer = window.setInterval(renderQueueStatus, 1000);
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
  const hrOnly = role === "hr";
  ["#nav-home", "#nav-settlement", "#nav-statistics", "#nav-phonebook", "#nav-atm", "#nav-salary-advance", "#nav-documents", "#nav-profile", "#nav-device", "#nav-vehicle", "#nav-tours", "#nav-game"]
    .forEach((selector) => $(selector).classList.toggle("hidden", coordinatorOnly));
  if (hrOnly) {
    ["#nav-home", "#nav-settlement", "#nav-statistics", "#nav-phonebook", "#nav-atm", "#nav-salary-advance", "#nav-documents", "#nav-device", "#nav-tours", "#nav-game"]
      .forEach((selector) => $(selector)?.classList.add("hidden"));
    ["#nav-profile", "#nav-vehicle"].forEach((selector) => $(selector)?.classList.remove("hidden"));
  }
  $("#nav-expense")?.classList.add("hidden");
  ["#workflow-preview-wrapper", "#statistics-preview-wrapper"].forEach((selector) => {
    const previewWrapper = $(selector);
    if (previewWrapper) previewWrapper.classList.toggle("hidden", !state.user.canPreviewCouriers);
  });
  const adminPreviewBar = $("#admin-preview-bar");
  if (adminPreviewBar) adminPreviewBar.classList.toggle("hidden", !state.user.canPreviewCouriers);
  const adminPreviewInput = $("#admin-preview-courier");
  if (adminPreviewInput) adminPreviewInput.value = state.workflowPreviewCourierId;
}

function showSection(section) {
  state.section = section;
  $("#home-content").classList.toggle("hidden", section !== "home");
  $("#settlement-content").classList.toggle("hidden", section !== "settlement");
  $("#statistics-content").classList.toggle("hidden", section !== "statistics");
  $("#phonebook-content").classList.toggle("hidden", section !== "phonebook");
  $("#atm-content").classList.toggle("hidden", section !== "atm");
  $("#salary-advance-content").classList.toggle("hidden", section !== "salary-advance");
  $("#expense-content").classList.toggle("hidden", section !== "expense");
  $("#documents-content").classList.toggle("hidden", section !== "documents");
  $("#profile-content").classList.toggle("hidden", section !== "profile");
  $("#device-content").classList.toggle("hidden", section !== "device");
  $("#vehicle-content").classList.toggle("hidden", section !== "vehicle");
  $("#tours-content").classList.toggle("hidden", section !== "tours");
  $("#game-content").classList.toggle("hidden", section !== "game");
  $("#coordinator-content").classList.toggle("hidden", section !== "coordinator");

  $("#nav-home").classList.toggle("active", section === "home");
  $("#nav-settlement").classList.toggle("active", section === "settlement");
  $("#nav-statistics").classList.toggle("active", section === "statistics");
  $("#nav-phonebook").classList.toggle("active", section === "phonebook");
  $("#nav-atm").classList.toggle("active", section === "atm");
  $("#nav-salary-advance").classList.toggle("active", section === "salary-advance");
  $("#nav-expense").classList.toggle("active", section === "expense");
  $("#nav-documents").classList.toggle("active", section === "documents");
  $("#nav-profile").classList.toggle("active", section === "profile");
  $("#nav-device").classList.toggle("active", section === "device");
  $("#nav-vehicle").classList.toggle("active", section === "vehicle");
  $("#nav-tours").classList.toggle("active", section === "tours");
  $("#nav-game").classList.toggle("active", section === "game");
  $("#nav-coordinator").classList.toggle("active", section === "coordinator");

  if (section === "settlement" && !state.workflow) loadWorkflow();
  if (section === "statistics" && !state.statistics) loadStatistics();
  if (section === "phonebook") renderPhonebook();
  if (section === "atm") loadAtmPayments();
  if (section === "salary-advance") loadSalaryAdvanceRequests();
  if (section === "expense") loadExpenseRequests();
  if (section === "documents") loadDocuments();
  if (section === "profile") {
    loadBillingProfile();
    refreshNotificationToggle();
  }
  if (section === "device") loadDeviceReports();
  if (section === "vehicle") loadVehicleSection();
  if (section === "tours") {
    loadCurrentRoute();
  }
  if (section === "game") loadGame();
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

function telHref(phone) {
  return `tel:${String(phone || "").replace(/[^\d+]/g, "")}`;
}

function renderPhonebook() {
  const target = $("#phonebook-list");
  if (!target) return;
  target.innerHTML = PHONEBOOK_CONTACTS.map((contact) => `
    <article class="phonebook-card">
      <div>
        <strong>${escapeHtml(contact.label)}</strong>
        <span>${escapeHtml(contact.note || "")}</span>
        <a href="${escapeHtml(telHref(contact.phone))}">${escapeHtml(contact.phone)}</a>
      </div>
      <a class="phonebook-call" href="${escapeHtml(telHref(contact.phone))}" aria-label="${escapeHtml(contact.label)} hívása">Hívás</a>
    </article>
  `).join("");
}

function gameElapsedSeconds() {
  return state.gameStartedAt ? Math.max(0, Math.round((Date.now() - state.gameStartedAt) / 1000)) : 0;
}

function safeDomName(value) {
  return String(value || "").replace(/[^a-z0-9_-]/gi, "");
}

function renderGame() {
  const target = $("#game-panel");
  if (!target) return;
  const game = state.game;
  if (!game?.puzzle) {
    target.innerHTML = `<div class="empty-card">Játék betöltése...</div>`;
    return;
  }
  const puzzle = game.puzzle;
  const leaders = game.leaderboard || [];
  const myBest = game.myBest;
  const myRank = leaders.find((item) => item.courierId === state.user?.courierId)?.rank || "-";
  target.innerHTML = `
    <div class="game-summary">
      <div><span>Mai maximum</span><strong>${formatCount(puzzle.maxScore || 0)}</strong></div>
      <div><span>Saját mai pont</span><strong>${myBest ? formatCount(myBest.score) : "-"}</strong></div>
      <div><span>Havi helyezés</span><strong>${escapeHtml(myRank)}</strong></div>
    </div>
    <form id="daily-game-form" class="game-form">
      <section class="game-block">
        <h3>Szókereső</h3>
        <div class="word-search-grid">
          ${(puzzle.wordSearch?.grid || []).flatMap((row) => row.map((letter) => `<span>${escapeHtml(letter)}</span>`)).join("")}
        </div>
        <div class="word-list">
          ${(puzzle.wordSearch?.words || []).map((item) => `
            <label><input type="checkbox" name="game-word" value="${escapeHtml(item.word)}" /> <strong>${escapeHtml(item.word)}</strong><small>${escapeHtml(item.hint || "")}</small></label>
          `).join("")}
        </div>
      </section>
      <section class="game-block">
        <h3>Kérdések</h3>
        <div class="quiz-list">
          ${(puzzle.quiz || []).map((question) => `
            <fieldset class="quiz-card">
              <legend>${escapeHtml(question.category || "Kérdés")}</legend>
              <p>${escapeHtml(question.question || "")}</p>
              <div class="choice-grid">
                ${(question.options || []).map((option, index) => `
                  <label><input type="radio" name="game-quiz-${escapeHtml(safeDomName(question.id))}" value="${escapeHtml(option)}" ${index === 0 ? "required" : ""} />${escapeHtml(option)}</label>
                `).join("")}
              </div>
            </fieldset>
          `).join("")}
        </div>
      </section>
      <button class="primary" type="submit">Pont beküldése</button>
      <p id="game-message" class="updated-at"></p>
    </form>
    <section class="leaderboard">
      <h3>Havi ranglista</h3>
      ${leaders.length ? leaders.map((item) => `
        <div class="leader-row ${item.courierId === state.user?.courierId ? "me" : ""}">
          <span>${formatCount(item.rank)}.</span>
          <strong>${escapeHtml(item.courierName || "Futár")}</strong>
          <small>${formatCount(item.score)} pont · ${formatCount(item.daysPlayed)} nap</small>
        </div>
      `).join("") : `<div class="empty-card">Még nincs havi pontszám.</div>`}
    </section>
  `;
  $("#daily-game-form")?.addEventListener("submit", submitGame);
}

async function loadGame() {
  const target = $("#game-panel");
  if (target && !state.game) target.innerHTML = `<div class="empty-card">Játék betöltése...</div>`;
  try {
    state.game = await api("/api/games/daily-challenge");
    state.gameStartedAt = Date.now();
    renderGame();
  } catch (error) {
    if (target) target.innerHTML = `<div class="warning-card">${escapeHtml(error.message)}</div>`;
  }
}

async function submitGame(event) {
  event.preventDefault();
  const button = event.currentTarget.querySelector('button[type="submit"]');
  const message = $("#game-message");
  if (button) button.disabled = true;
  if (message) message.textContent = "Pontszám mentése...";
  try {
    const foundWords = [...document.querySelectorAll('input[name="game-word"]:checked')].map((item) => item.value);
    const quizAnswers = {};
    for (const question of state.game?.puzzle?.quiz || []) {
      quizAnswers[question.id] = document.querySelector(`input[name="game-quiz-${safeDomName(question.id)}"]:checked`)?.value || "";
    }
    state.game = await api("/api/games/daily-challenge", {
      method: "POST",
      body: JSON.stringify({
        found_words: foundWords,
        quiz_answers: quizAnswers,
        elapsed_seconds: gameElapsedSeconds(),
      }),
    });
    renderGame();
    const saved = state.game?.submitted?.score;
    const savedMessage = $("#game-message");
    if (savedMessage) savedMessage.textContent = `Mentve: ${formatCount(saved)} pont.`;
  } catch (error) {
    if (message) message.textContent = error.message;
  } finally {
    if (button) button.disabled = false;
  }
}

function atmPaymentStatusLabel(value) {
  const status = String(value || "submitted").trim().toLowerCase();
  return {
    submitted: "Beküldve",
    reviewed: "Ellenőrizve",
    rejected: "Elutasítva",
  }[status] || status || "-";
}

function renderAtmPayments(balance = null) {
  const total = Number(balance?.paidTotalHuf ?? state.atmPayments.reduce((sum, item) => sum + Number(item.amountHuf || 0), 0));
  const count = Number(balance?.count ?? state.atmPayments.length);
  const totalTarget = $("#atm-balance-paid");
  const countTarget = $("#atm-balance-count");
  if (totalTarget) totalTarget.textContent = formatHuf(total);
  if (countTarget) countTarget.textContent = `${formatCount(count)} befizetés`;

  const target = $("#atm-list");
  if (!target) return;
  const rows = state.atmPayments || [];
  if (!rows.length) {
    target.innerHTML = `
      <div class="process-title">
        <span class="step-code">ATM</span>
        <div><h3>Beküldött ATM befizetések</h3><p>Még nincs rögzített ATM befizetés.</p></div>
      </div>
    `;
    return;
  }
  target.innerHTML = `
    <div class="process-title">
      <span class="step-code">ATM</span>
      <div><h3>Beküldött ATM befizetések</h3><p>A bizonylatok külön ATM naplóban maradnak, nem módosítják a havi elszámolást.</p></div>
    </div>
    <div class="financial-card-grid salary-advance-grid">
      ${rows.map((item) => `
        <article class="financial-card">
          <summary>
            <span>${escapeHtml(atmPaymentStatusLabel(item.status))}</span>
            <strong>${formatHuf(item.amountHuf)}</strong>
          </summary>
          <div class="stat-breakdown-list">
            <div class="stat-row"><span>Dátum</span><strong>${escapeHtml(shortDateTime(item.paidAt || item.createdAt))}</strong></div>
            <div class="stat-row"><span>Bizonylat</span><strong>${escapeHtml(item.invoiceNumber || "-")}</strong></div>
            <div class="stat-row"><span>Fájl</span><strong>${escapeHtml(item.fileName || "-")}</strong></div>
            ${item.note ? `<div class="stat-row"><span>Megjegyzés</span><strong>${escapeHtml(item.note)}</strong></div>` : ""}
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

async function loadAtmPayments() {
  const message = $("#atm-message");
  if (message) message.textContent = "ATM befizetések betöltése...";
  try {
    const payload = await api(withPreviewCourier("/api/atm-payments"));
    state.atmPayments = payload.payments || [];
    renderAtmPayments(payload.balance || null);
    if (message) message.textContent = "";
  } catch (error) {
    renderAtmPayments();
    if (message) message.textContent = error.message;
  }
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
    const payload = await api(withPreviewCourier("/api/salary-advance/requests"));
    state.salaryAdvanceRequests = payload.requests || [];
    renderSalaryAdvanceRequests();
    if (message) message.textContent = "";
  } catch (error) {
    if (message) message.textContent = error.message;
  }
}

function renderExpenseRequests() {
  const target = $("#expense-list");
  if (!target) return;
  const rows = state.expenseRequests || [];
  if (!rows.length) {
    target.innerHTML = `
      <div class="process-title">
        <span class="step-code">T</span>
        <div><h3>Beküldött költségszámlák</h3><p>Még nincs rögzített tankolás vagy egyéb számla.</p></div>
      </div>
    `;
    return;
  }
  target.innerHTML = `
    <div class="process-title">
      <span class="step-code">T</span>
      <div><h3>Beküldött költségszámlák</h3><p>Ezek külön kifizetési folyamatként mennek tovább.</p></div>
    </div>
    <div class="financial-card-grid salary-advance-grid">
      ${rows.map((item) => `
        <article class="financial-card">
          <summary>
            <span>${escapeHtml(item.typeLabel || "Költségszámla")}</span>
            <strong>${formatHuf(item.amountHuf)}</strong>
          </summary>
          <div class="stat-breakdown-list">
            <div class="stat-row"><span>Státusz</span><strong>${escapeHtml(item.statusLabel || item.status || "-")}</strong></div>
            <div class="stat-row"><span>Rendszám</span><strong>${escapeHtml(item.licensePlate || "-")}</strong></div>
            <div class="stat-row"><span>Km óra</span><strong>${formatCount(item.odometerKm || 0)}</strong></div>
            <div class="stat-row"><span>Számlaszám</span><strong>${escapeHtml(item.invoiceNumber || "-")}</strong></div>
            ${item.processId ? `<div class="stat-row"><span>Folyamat</span><strong>${escapeHtml(item.processId)}</strong></div>` : ""}
          </div>
        </article>
      `).join("")}
    </div>
  `;
}

async function loadExpenseRequests() {
  const message = $("#expense-message");
  if (message) message.textContent = "Költségszámlák betöltése...";
  try {
    const payload = await api(withPreviewCourier("/api/expense-requests"));
    state.expenseRequests = payload.requests || [];
    renderExpenseRequests();
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

function fullDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
  return new Intl.DateTimeFormat("hu-HU", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function timeOnly(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(11, 16) || String(value);
  return new Intl.DateTimeFormat("hu-HU", { hour: "2-digit", minute: "2-digit" }).format(date);
}

function durationText(minutes) {
  if (minutes === null || minutes === undefined || minutes === "") return "Nincs adat";
  const numeric = Number(minutes);
  if (!Number.isFinite(numeric)) return "Nincs adat";
  const value = Math.max(0, numeric);
  const hours = Math.floor(value / 60);
  const mins = value % 60;
  if (hours && mins) return `${formatCount(hours)} óra ${formatCount(mins)} perc`;
  if (hours) return `${formatCount(hours)} óra`;
  return `${formatCount(mins)} perc`;
}

function nullableNumber(...values) {
  for (const value of values) {
    if (value === null || value === undefined || value === "") continue;
    const numeric = Number(value);
    if (Number.isFinite(numeric)) return numeric;
  }
  return null;
}

function routeStoryTextMatch(text, pattern) {
  const match = String(text || "").match(pattern);
  return match ? match[1].trim() : "";
}

function renderDelayDetailRows(rows = []) {
  if (!rows.length) return `<div class="stat-row"><span>Nincs route szintű késés adat</span><strong>-</strong></div>`;
  return rows.map((row) => `
    <div class="stat-row">
      <span>${escapeHtml(row.date || "-")} · Route ${escapeHtml(row.routeId || "-")} · WH${escapeHtml(row.warehouseId || "-")}</span>
      <strong>${formatCount(row.delayMinutes)} perc · ${formatCount(row.delayedStops)} cím · mentesítés: ${row.hasDelayCleaning ? "Igen" : "Nem"}</strong>
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

function updateStatisticsDayPicker(dates = []) {
  const picker = $("#statistics-day");
  if (!picker) return;
  const previous = state.statisticsDay;
  const options = [`<option value="">Legutóbbi nap</option>`].concat(
    dates.map((date) => `<option value="${escapeHtml(date)}">${escapeHtml(dateLabel(date))}</option>`)
  );
  picker.innerHTML = options.join("");
  picker.disabled = dates.length === 0;
  if (previous && dates.includes(previous)) {
    picker.value = previous;
  } else {
    state.statisticsDay = "";
    picker.value = "";
  }
}

function uniqueText(values = []) {
  return [...new Set(values.map((value) => String(value || "").trim()).filter(Boolean))];
}

function routeStoryTime(label, value) {
  const missing = !value;
  return `<div class="stat-row ${missing ? "missing" : ""}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(missing ? "Hiányzik" : shortDateTime(value))}</strong></div>`;
}

function routeStoryMetric(label, value, suffix = "") {
  const missing = value === null || value === undefined || value === "";
  const numeric = Number(value || 0);
  return `<div class="stat-row ${missing ? "missing" : ""}"><span>${escapeHtml(label)}</span><strong>${escapeHtml(missing ? "Hiányzik" : `${formatCount(numeric)}${suffix}`)}</strong></div>`;
}

function routeTypeLabel(value) {
  const key = String(value || "").toLowerCase();
  if (key === "express") return "Express";
  if (key === "regional") return "Regionális";
  return "Normál";
}

function minutesBetween(start, end) {
  const startTime = start ? new Date(start).getTime() : NaN;
  const endTime = end ? new Date(end).getTime() : NaN;
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime) || endTime < startTime) return 0;
  return Math.round((endTime - startTime) / 60000);
}

function nullableMinutesBetween(start, end) {
  const startTime = start ? new Date(start).getTime() : NaN;
  const endTime = end ? new Date(end).getTime() : NaN;
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime) || endTime < startTime) return null;
  return Math.round((endTime - startTime) / 60000);
}

function signedMinutesBetween(start, end) {
  const startTime = start ? new Date(start).getTime() : NaN;
  const endTime = end ? new Date(end).getTime() : NaN;
  if (!Number.isFinite(startTime) || !Number.isFinite(endTime)) return null;
  return Math.round((endTime - startTime) / 60000);
}

function shiftKeyForRoute(row = {}) {
  return String(
    row.routeStory?.shiftStart
    || row.plannedStartAt
    || row.shiftAvailableAt
    || row.actualStartAt
    || `${row.date || ""}_${row.routeId || ""}`
  ).trim();
}

function buildDailyShiftReport(rows = []) {
  const grouped = rows.reduce((acc, row) => {
    const key = shiftKeyForRoute(row);
    if (!acc[key]) acc[key] = [];
    acc[key].push(row);
    return acc;
  }, {});
  return Object.entries(grouped).map(([key, items], index) => {
    const lateStartRows = items.filter((row) => Number(row.plannedStartDelayMinutes || 0) > 0);
    const lateStopRows = items.filter((row) => {
      const cleanedCount = Number(row.cleanedDelayCount || 0);
      const uncleanedCount = Number(row.uncleanedDelayCount || 0);
      const hasCleaningData = Boolean(row.hasDelayCleaning || cleanedCount > 0 || uncleanedCount > 0);
      if (hasCleaningData) return uncleanedCount > 0;
      return Number(row.timeWindowLateCount || row.apiDelayedOrderCount || 0) > 0;
    });
    const sameCheckin = uniqueText(items.map((row) => row.actualStartAt || row.shiftAvailableAt)).length === 1 && items.length > 1;
    return {
      key,
      label: shortDateTime(key) !== "-" ? shortDateTime(key) : `Műszak ${index + 1}`,
      routes: items.length,
      lateStartRows,
      lateStopRows,
      sameCheckin,
      ok: lateStartRows.length === 0 && lateStopRows.length === 0,
    };
  });
}

function renderStatusBadge(ok) {
  return `<span class="route-status-badge ${ok ? "ok" : "bad"}">${ok ? ":)" : ":("}</span>`;
}

function renderDailyShiftReport(rows = []) {
  const report = buildDailyShiftReport(rows);
  if (!report.length) return "";
  return `
    <div class="shift-quality-list">
      ${report.map((shift) => `
        <div class="shift-quality-row">
          ${renderStatusBadge(shift.ok)}
          <div>
            <strong>${escapeHtml(shift.label)}</strong>
            <small>${formatCount(shift.routes)} túra${shift.sameCheckin ? " · azonos bejelentkezés több túránál" : ""}</small>
          </div>
          <span>${shift.ok ? "Rendben" : "Eltérés"}</span>
        </div>
      `).join("")}
    </div>
  `;
}

function uncleanedLateStopCount(row = {}) {
  const cleanedCount = Number(row.cleanedDelayCount || 0);
  const uncleanedCount = Number(row.uncleanedDelayCount || 0);
  const hasCleaningData = Boolean(row.hasDelayCleaning || cleanedCount > 0 || uncleanedCount > 0);
  if (hasCleaningData) return Math.max(0, uncleanedCount);
  return Math.max(0, Number(row.timeWindowLateCount || row.apiDelayedOrderCount || 0));
}

function qualitySummaryFromDailyHistory(rows = []) {
  const noShowByDate = {};
  const lateShiftKeys = new Set();
  let uncleanedLateCount = 0;
  let uncleanedLateMinutes = 0;

  rows.forEach((row) => {
    const workDate = String(row.date || "").slice(0, 10);
    const noShow = Number(row.apiDidNotComeCount || 0);
    if (workDate) noShowByDate[workDate] = Math.max(noShowByDate[workDate] || 0, noShow);

    const shiftLateMinutes = routeShiftLateMinutes(row, row.routeStory || {});
    if (shiftLateMinutes > 0) lateShiftKeys.add(shiftKeyForRoute(row));

    const lateCount = uncleanedLateStopCount(row);
    uncleanedLateCount += lateCount;
    if (lateCount > 0) uncleanedLateMinutes += Number(row.uncleanedDelayMinutes || row.timeWindowLateMinutes || 0);
  });

  const noShowCount = Object.values(noShowByDate).reduce((sum, value) => sum + Number(value || 0), 0);
  const totalProblems = noShowCount + lateShiftKeys.size + uncleanedLateCount;
  return {
    noShowCount,
    lateShiftCount: lateShiftKeys.size,
    uncleanedTimeWindowLateCount: uncleanedLateCount,
    uncleanedTimeWindowLateMinutes: uncleanedLateMinutes,
    totalProblems,
    ok: totalProblems <= 0,
  };
}

function renderQualitySummaryChart(payload = {}) {
  const summary = payload.qualitySummary || qualitySummaryFromDailyHistory(payload.dailyHistory || []);
  const activeTopic = state.statisticsQualityTopic || "";
  const details = summary.details || {};
  const items = [
    {
      key: "lateShift",
      label: "Műszak késés",
      value: Number(summary.lateShiftCount || 0),
      note: "Késő sorba állás / műszakkezdéshez képest",
    },
    {
      key: "uncleanedTimeWindowLate",
      label: "Nem mentesített címkésés",
      value: Number(summary.uncleanedTimeWindowLateCount || 0),
      note: `${formatCount(summary.uncleanedTimeWindowLateMinutes || 0)} perc összesen`,
    },
    {
      key: "noShow",
      label: "No-show",
      value: Number(summary.noShowCount || 0),
      note: "Nem jelent meg műszakban",
    },
  ];
  const maxValue = Math.max(1, ...items.map((item) => item.value));
  const statusOk = Boolean(summary.ok || Number(summary.totalProblems || 0) <= 0);
  return `
    <section class="quality-summary-card ${statusOk ? "ok" : "warn"}">
      <div class="quality-summary-head">
        ${renderStatusBadge(statusOk)}
        <div>
          <h3>${statusOk ? "Szép munka, tiszta hónap" : "Erre érdemes ránézni"}</h3>
          <p>${statusOk ? "Nincs no-show, műszak késés vagy nem mentesített időablak-késés." : "A három fő minőségi jelzés havi összesítése."}</p>
        </div>
      </div>
      <div class="quality-bars">
        ${items.map((item) => {
          const width = Math.max(4, Math.round((item.value / maxValue) * 100));
          return `
            <button class="quality-bar-row ${activeTopic === item.key ? "active" : ""}" type="button" data-quality-topic="${escapeHtml(item.key)}">
              <div>
                <strong>${escapeHtml(item.label)}</strong>
                <small>${escapeHtml(item.note)}</small>
              </div>
              <div class="quality-bar-track"><span style="width: ${width}%"></span></div>
              <b>${formatCount(item.value)}</b>
            </button>
          `;
        }).join("")}
      </div>
      ${renderQualitySummaryDetails(activeTopic, details)}
    </section>
  `;
}

function renderQualitySummaryDetails(topic, details = {}) {
  if (!topic) return "";
  const labels = {
    lateShift: "Vizsgálandó műszak késések",
    uncleanedTimeWindowLate: "Vizsgálandó időkapun túli késések",
    noShow: "Vizsgálandó no-show műszakok",
  };
  const rows = Array.isArray(details[topic]) ? details[topic] : [];
  return `
    <div class="quality-detail-list">
      <h4>${escapeHtml(labels[topic] || "Vizsgálandó tételek")}</h4>
      ${rows.length ? rows.map((row) => `
        <div class="quality-detail-row">
          <strong>${escapeHtml(row.date || "-")}</strong>
          <span>${escapeHtml(row.label || "-")}</span>
          <small>${escapeHtml(row.note || "")}${row.routeId ? ` · Route ${escapeHtml(row.routeId)}` : ""}</small>
        </div>
      `).join("") : `<p>Nincs külön vizsgálandó sor ehhez a jelzéshez.</p>`}
    </div>
  `;
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

function routeShiftLateMinutes(row = {}, story = {}) {
  const explicitDelay = Number(row.plannedStartDelayMinutes || 0);
  if (explicitDelay > 0) return explicitDelay;
  const shiftStart = story.shiftStart || row.plannedStartAt;
  const queuedAt = story.queueStartedAt || row.actualStartAt || story.availableForShiftSince || story.availableAt || row.shiftAvailableAt;
  const computedDelay = minutesBetween(shiftStart, queuedAt);
  return computedDelay > 0 ? computedDelay : 0;
}

function routeDelayCleaningLabel(row = {}) {
  const cleanedCount = Number(row.cleanedDelayCount || 0);
  const uncleanedCount = Number(row.uncleanedDelayCount || 0);
  const cleanedMinutes = Number(row.cleanedDelayMinutes || 0);
  const uncleanedMinutes = Number(row.uncleanedDelayMinutes || 0);
  const reasons = Array.isArray(row.cleanedReasons) ? row.cleanedReasons.filter(Boolean) : [];
  if (cleanedCount <= 0 && uncleanedCount <= 0) {
    return row.hasDelayCleaning ? "Igen" : "Nem";
  }
  const parts = [];
  if (cleanedCount > 0) {
    parts.push(`Igen: ${formatCount(cleanedCount)} cím / ${formatCount(cleanedMinutes)} perc${reasons.length ? ` (${reasons.join(", ")})` : ""}`);
  }
  if (uncleanedCount > 0) {
    parts.push(`Nem: ${formatCount(uncleanedCount)} cím / ${formatCount(uncleanedMinutes)} perc`);
  }
  return parts.join(" · ") || "Nem";
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
    return "";
  }
  return `
    <section class="route-timeline">
      <div class="route-timeline-head">
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

function renderNarrativeRouteStory(row) {
  const story = row.routeStory || {};
  if (!Object.keys(story).length && !story.storyText) return "";

  const storyText = String(story.storyText || "");
  const shiftStart = story.shiftStart || row.plannedStartAt;
  const shiftEnd = story.shiftEnd || "";
  const shiftCheckinAt = story.queueStartedAt || row.actualStartAt || story.availableForShiftSince || story.availableAt || row.shiftAvailableAt;
  const availableAt = story.availableForShiftSince || story.availableAt || shiftCheckinAt || story.courierRegisteredAt || row.shiftAvailableAt;
  const registeredAt = story.courierRegisteredAt || shiftCheckinAt;
  const assignedAt = story.assignedAt || row.routeAssignedAt;
  const computedQueueDelta = shiftStart && shiftCheckinAt ? signedMinutesBetween(shiftStart, shiftCheckinAt) : null;
  const queueDelta = nullableNumber(story.queueEntryDeltaMinutes, computedQueueDelta);
  const queueWait = nullableNumber(story.queueWaitMinutes, nullableMinutesBetween(shiftCheckinAt, assignedAt));
  const plannedDeparture = story.plannedDeparture || row.plannedDepartureAt;
  const realDeparture = story.realDeparture || row.departedAt;
  const plannedReturn = story.plannedReturn || row.plannedReturnAt;
  const realReturn = story.realReturn || row.warehouseArrivedAt || row.lastOrderFinishedAt;
  const plannedLoading = nullableNumber(story.plannedLoadingMinutes, nullableMinutesBetween(assignedAt, plannedDeparture));
  const realLoading = nullableNumber(story.realLoadingMinutes, nullableMinutesBetween(assignedAt, realDeparture));
  const plannedRoute = nullableNumber(story.plannedRouteMinutes, nullableMinutesBetween(plannedDeparture, plannedReturn));
  const realRoute = nullableNumber(story.realRouteMinutes, row.routeDurationMinutes, nullableMinutesBetween(realDeparture, realReturn));
  const totalRoute = nullableNumber(story.totalRouteMinutes, story.assignedToReturnMinutes, nullableMinutesBetween(assignedAt, realReturn));
  const gpsDistance = nullableNumber(story.gpsDistanceKm, Number(row.mileageKm || 0) > 0 ? row.mileageKm : null);
  const straightDistance = nullableNumber(story.checkpointStraightKm);
  const addressCount = nullableNumber(story.addressCount, row.orders, row.stops);
  const timeWindowLate = nullableNumber(story.timeWindowLateCount, row.timeWindowLateCount);
  const nextShiftDelay = nullableNumber(story.nextShiftDelayMinutes);
  const nextShiftText = routeStoryTextMatch(storyText, /A kovetkezo foglalt muszak:\s*([^.]+)/i);
  const bookedShiftCount = routeStoryTextMatch(storyText, /napi foglalt muszakok szama:\s*(\d+)/i);
  const plannedEarly = routeStoryTextMatch(storyText, /tervezetthez kepest korai:\s*(\d+)/i);
  const plannedLate = routeStoryTextMatch(storyText, /tervezetthez kepest keso:\s*(\d+)/i);
  const windowEarly = routeStoryTextMatch(storyText, /idokapuhoz kepest korai:\s*(\d+)/i);
  const windowLate = routeStoryTextMatch(storyText, /idokapuhoz kepest keso:\s*(\d+)/i) || String(timeWindowLate ?? 0);
  const earlyText = queueDelta === null
    ? "a műszakkezdéshez képest nincs pontos adat"
    : queueDelta < 0
    ? `${formatCount(Math.abs(queueDelta))} perccel a műszakkezdés előtt`
    : queueDelta > 0
      ? `${formatCount(queueDelta)} perccel a műszakkezdés után`
      : "pontosan a műszakkezdéskor";

  return `
    <article class="route-story-card">
      <div class="route-story-card-head">
        <span>Route történet</span>
        <strong>Route ${escapeHtml(row.routeId || "-")}</strong>
      </div>

      <section>
        <h4>Műszak és sorban állás</h4>
        <p>A futár műszakja <strong>${escapeHtml(fullDateTime(shiftStart))}</strong> és <strong>${escapeHtml(timeOnly(shiftEnd))}</strong> között volt.</p>
        <p><strong>${escapeHtml(timeOnly(shiftCheckinAt || availableAt))}</strong>-kor állt be a műszak sorába, vagyis ${escapeHtml(earlyText)}. A route regisztráció <strong>${escapeHtml(timeOnly(registeredAt))}</strong>-kor történt.</p>
        <p>A túrát <strong>${escapeHtml(timeOnly(assignedAt))}</strong>-kor kapta meg, így összesen <strong>${escapeHtml(durationText(queueWait))}</strong> állt sorban.</p>
      </section>

      <section>
        <h4>Idők</h4>
        <p>A bepakolás tervezett ideje <strong>${escapeHtml(durationText(plannedLoading))}</strong> volt, a valós bepakolási idő <strong>${escapeHtml(durationText(realLoading))}</strong> lett.</p>
        <p>A túra tervezett hossza <strong>${escapeHtml(durationText(plannedRoute))}</strong> volt, a tényleges túraidő <strong>${escapeHtml(durationText(realRoute))}</strong> lett. A teljes időtartam összesen <strong>${escapeHtml(durationText(totalRoute))}</strong> volt.</p>
      </section>

      <section>
        <h4>Távolság</h4>
        <p>A GPS alapján mért távolság <strong>${gpsDistance === null ? "Nincs adat" : `${escapeHtml(formatAverage(gpsDistance))} km`}</strong> volt.${straightDistance ? ` A címek közötti egyenes távolság <strong>${escapeHtml(formatAverage(straightDistance))} km</strong>.` : ""}</p>
      </section>

      <section>
        <h4>Foglalás és következő műszak</h4>
        <p>Az adott napon a futárnak <strong>${escapeHtml(bookedShiftCount || "-")}</strong> foglalt műszakja volt.</p>
        ${nextShiftText ? `<p>A következő foglalt műszak <strong>${escapeHtml(nextShiftText)}</strong> volt.${nextShiftDelay ? ` A route visszaérkezési ideje alapján ebből <strong>${escapeHtml(durationText(nextShiftDelay))}</strong> késés keletkezett.` : ""}</p>` : ""}
      </section>

      <section>
        <h4>Címek</h4>
        <p>Összesen <strong>${addressCount === null ? "Nincs adat" : `${formatCount(addressCount)} cím`}</strong> volt a túrán. A tervezett időponthoz képest <strong>${escapeHtml(plannedEarly || "0")}</strong> cím korábban, <strong>${escapeHtml(plannedLate || "0")}</strong> cím később teljesült.</p>
        <p>Az időkapuhoz képest <strong>${escapeHtml(windowEarly || "0")}</strong> cím korábban teljesült, késéses cím pedig <strong>${escapeHtml(windowLate || "0")}</strong> volt.</p>
      </section>
    </article>
  `;
}

function renderRouteStoryDetails(row) {
  const story = row.routeStory || {};
  const distance = Number(story.gpsDistanceKm || row.mileageKm || 0);
  const routeMinutes = Number(
    story.realRouteMinutes
    || story.assignedToReturnMinutes
    || story.totalRouteMinutes
    || row.routeDurationMinutes
    || minutesBetween(row.departedAt || row.routeAssignedAt, row.warehouseArrivedAt)
    || 0
  );
  const lateCount = Number(story.timeWindowLateCount || row.timeWindowLateCount || 0);
  const apiDelayedOrders = Number(row.apiDelayedOrderCount || 0);
  const apiLateCount = Number(row.apiLateCount || 0);
  const hasApiQuality = Number(row.apiShiftCount || 0) > 0 || apiDelayedOrders > 0 || apiLateCount > 0 || Number(row.apiDidNotComeCount || 0) > 0;
  const lateMinutes = Number(row.timeWindowLateMinutes || 0);
  const maxDelay = Number(row.maxDelayMinutes || 0);
  const cleanedCount = Number(row.cleanedDelayCount || 0);
  const uncleanedCount = Number(row.uncleanedDelayCount || 0);
  const hasCleaningData = Boolean(row.hasDelayCleaning || cleanedCount > 0 || uncleanedCount > 0);
  const visibleLateCount = hasApiQuality ? apiDelayedOrders : lateCount;
  const qualityLateCount = hasCleaningData ? uncleanedCount : visibleLateCount;
  const lateText = visibleLateCount || lateMinutes || maxDelay
    ? `${formatCount(visibleLateCount)} cím · ${formatCount(lateMinutes)} perc${maxDelay ? ` · max ${formatCount(maxDelay)} perc` : ""}`
    : "Nincs";
  const routeOk = qualityLateCount <= 0;
  const shiftLateMinutes = routeShiftLateMinutes(row, story);
  const shiftOk = shiftLateMinutes <= 0;
  return `
    <div class="daily-route-story">
      <div class="route-quality-head">
        ${renderStatusBadge(routeOk)}
        <div><strong>${routeOk ? "Időkapun belül" : "Időkapun kívül"}</strong><small>Időablak szerinti ellenőrzés</small></div>
      </div>
      <div class="route-quality-head">
        ${renderStatusBadge(shiftOk)}
        <div><strong>${shiftOk ? "Műszak időben" : "Késett a műszakból"}</strong><small>${shiftOk ? "Sorba állás rendben" : `${formatCount(shiftLateMinutes)} perc késés a műszakhoz képest`}</small></div>
      </div>
      ${story.shiftName ? `<p class="updated-at">${escapeHtml(story.shiftName)}</p>` : ""}
      ${routeStoryTime("Műszak kezdete", story.shiftStart || row.plannedStartAt)}
      <div class="stat-row"><span>Túratípus</span><strong>${escapeHtml(routeTypeLabel(row.routeType))}</strong></div>
      ${routeStoryTime("Elérhető volt", story.availableForShiftSince || story.availableAt || story.courierRegisteredAt || row.shiftAvailableAt)}
      ${routeStoryTime("Sorba állt", story.queueStartedAt || row.actualStartAt)}
      ${routeStoryTime("Túrát kapott", story.assignedAt || row.routeAssignedAt)}
      ${routeStoryTime("Indulás a raktárból", story.realDeparture || row.departedAt)}
      ${routeStoryTime("Tervezett visszaérkezés", story.plannedReturn || row.plannedReturnAt)}
      ${routeStoryTime("Valós visszaérkezés", story.realReturn || row.warehouseArrivedAt)}
      ${routeStoryMetric("Várakozás túrára", story.queueWaitMinutes, " perc")}
      ${routeStoryMetric("Túra hossza", routeMinutes, " perc")}
      <div class="stat-row"><span>Időkapun túli késés</span><strong>${escapeHtml(lateText)}</strong></div>
      <div class="stat-row"><span>Késés mentesítés</span><strong>${escapeHtml(routeDelayCleaningLabel(row))}</strong></div>
      ${routeStoryDistance("Megtett táv", distance)}
      ${renderNarrativeRouteStory(row)}
      ${Object.keys(story).length ? "" : `<p class="updated-at">Forrás: napi route history + compliance/delay táblák</p>`}
      ${renderRouteNoteForm(row)}
    </div>
  `;
}

function renderRouteNoteForm(row) {
  const routeId = String(row.routeId || "").trim();
  const workDate = String(row.date || "").trim();
  if (!routeId || !workDate) return "";
  const previewReadOnly = Boolean(state.user?.canPreviewCouriers && state.workflowPreviewCourierId);
  if (previewReadOnly) {
    return `
      <div class="route-note-form">
        <label>Megjegyzés<textarea readonly>${escapeHtml(row.routeNote || "")}</textarea></label>
        <p class="updated-at">${row.routeNoteUpdatedAt ? `Mentve: ${escapeHtml(shortDateTime(row.routeNoteUpdatedAt))}` : "Előnézetben a megjegyzés nem szerkeszthető."}</p>
      </div>
    `;
  }
  return `
    <form class="route-note-form" data-route-id="${escapeHtml(routeId)}" data-work-date="${escapeHtml(workDate)}">
      <label>Megjegyzés<textarea name="note" maxlength="1200" placeholder="Ide írhatod a route-tal kapcsolatos megjegyzést.">${escapeHtml(row.routeNote || "")}</textarea></label>
      <button class="secondary" type="submit">Megjegyzés mentése</button>
      <p class="updated-at route-note-status">${row.routeNoteUpdatedAt ? `Mentve: ${escapeHtml(shortDateTime(row.routeNoteUpdatedAt))}` : ""}</p>
    </form>
  `;
}

function renderDailyHistory(payload) {
  const rows = payload.dailyHistory || [];
  const byDate = dailyHistoryByDate(rows);
  const dates = Object.keys(byDate).sort().reverse();
  updateStatisticsDayPicker(dates);
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
  if (state.statisticsDay && dates.includes(state.statisticsDay)) {
    state.statisticsHistoryDate = state.statisticsDay;
  } else if (!dates.includes(state.statisticsHistoryDate)) {
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
  const apiShifts = selectedRows.reduce((max, row) => Math.max(max, Number(row.apiShiftCount || 0)), 0);
  const shifts = apiShifts || buildDailyShiftReport(selectedRows).length;
  const routeRows = selectedRows.map((row) => `
    <details class="daily-route-details">
      <summary class="daily-route-row">
        <div>
          <strong>Route ${escapeHtml(row.routeId || "-")}</strong>
          <small>WH${escapeHtml(row.warehouseId || "-")} · ${escapeHtml(routeTypeLabel(row.routeType))} · ${formatCount(row.orders)} cím · ${formatCount(row.stops)} stop · ${formatAverage(row.mileageKm)} km</small>
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
        <div><span>Műszakok</span><strong>${formatCount(shifts)}</strong></div>
        <div><span>Cím</span><strong>${formatCount(orders)}</strong></div>
        <div><span>Km</span><strong>${formatAverage(mileage)}</strong></div>
      </div>
      ${renderDailyShiftReport(selectedRows)}
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
  const currentIndex = dates.includes(state.statisticsHistoryDate)
    ? dates.indexOf(state.statisticsHistoryDate)
    : 0;
  const nextIndex = Math.min(dates.length - 1, Math.max(0, currentIndex + offset));
  if (nextIndex === currentIndex) return;
  state.statisticsHistoryDate = dates[nextIndex];
  state.statisticsDay = dates[nextIndex];
  renderStatistics();
}

async function saveRouteNote(form) {
  const routeId = String(form.dataset.routeId || "").trim();
  const workDate = String(form.dataset.workDate || "").trim();
  const noteInput = form.querySelector("textarea[name='note']");
  const status = form.querySelector(".route-note-status");
  const button = form.querySelector("button[type='submit']");
  const note = String(noteInput?.value || "").trim();
  if (!routeId || !workDate) return;
  if (button) button.disabled = true;
  if (status) status.textContent = "Mentés...";
  try {
    const response = await api("/api/statistics/route-note", {
      method: "PUT",
      body: JSON.stringify({ route_id: routeId, work_date: workDate, note }),
    });
    const row = (state.statistics?.dailyHistory || []).find((item) => String(item.routeId || "") === routeId && String(item.date || "") === workDate);
    if (row) {
      row.routeNote = response.note || note;
      row.routeNoteUpdatedAt = response.updatedAt || new Date().toISOString();
    }
    if (status) status.textContent = `Mentve: ${shortDateTime(response.updatedAt || new Date().toISOString())}`;
  } catch (error) {
    if (status) status.textContent = error.message || "Nem sikerült menteni.";
  } finally {
    if (button) button.disabled = false;
  }
}

function bindDailyHistoryControls() {
  $("#daily-history-prev")?.addEventListener("click", () => changeDailyHistoryDate(-1));
  $("#daily-history-next")?.addEventListener("click", () => changeDailyHistoryDate(1));
  const card = $("#daily-history-card");
  if (!card) return;
  let startX = 0;
  let startY = 0;
  card.addEventListener("touchstart", (event) => {
    if (event.target?.closest?.("button, input, textarea, select, summary, details")) return;
    startX = event.touches?.[0]?.clientX || 0;
    startY = event.touches?.[0]?.clientY || 0;
  }, { passive: true });
  card.addEventListener("touchend", (event) => {
    if (event.target?.closest?.("button, input, textarea, select, summary, details")) return;
    const endX = event.changedTouches?.[0]?.clientX || 0;
    const endY = event.changedTouches?.[0]?.clientY || 0;
    const delta = endX - startX;
    const verticalDelta = endY - startY;
    if (Math.abs(delta) < 65 || Math.abs(delta) < Math.abs(verticalDelta) * 1.4) return;
    changeDailyHistoryDate(delta < 0 ? 1 : -1);
  }, { passive: true });
}

function renderStatistics() {
  const payload = state.statistics;
  const grid = $("#statistics-grid");
  const message = $("#statistics-message");
  const qualityPanel = $("#statistics-quality");
  const breakdown = $("#statistics-breakdown");
  if (!grid || !message || !qualityPanel || !breakdown) return;

  if (!payload) {
    grid.innerHTML = "";
    qualityPanel.innerHTML = "";
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

  const viewedUser = payload.viewingAs || payload.courier || state.workflow?.viewingAs || {};
  const previewNotice = state.user?.canPreviewCouriers && state.workflowPreviewCourierId
    ? `<div class="notice">Előnézet: ${escapeHtml(viewedUser.username || state.workflowPreviewCourierId)} (${escapeHtml(viewedUser.courierId || state.workflowPreviewCourierId)}). Ebben a módban más futár statisztikáját látod.</div>`
    : "";

  message.innerHTML = `
    ${previewNotice}
    <div class="notice">
      ${escapeHtml(payload.month || state.statisticsMonth)} havi adatok. ${escapeHtml(payload.amountsNote || "A teljes bevétel rejtve a mobil nézetben.")}
    </div>
  `;
  grid.innerHTML = [
    statisticCard("Kör", formatCount(routes), "kivitt túrák"),
    statisticCard("Műszakok", formatCount(summary.shiftCount), "foglalt / teljesített"),
    statisticCard("Cím", formatCount(orders), "rendelések"),
    statisticCard("Átlag", formatAverage(average), "cím / kör"),
    statisticCard("Borravaló", formatHuf(summary.tipsTotalHuf), "összesen"),
    statisticCard("Futár bevétele", "Rejtve", "mobil nézetben"),
    statisticCard("Ügyfélértékelés", ratingValue, rating.available ? `${formatCount(rating.ratingCount)} értékelés` : "későbbi kimutatáshoz"),
  ].join("");
  qualityPanel.innerHTML = renderQualitySummaryChart(payload);

  const routeBreakdown = payload.routeBreakdown || {};
  const quality = payload.dataQuality || {};
  const ruleRows = (quality.dayRules || []).map((rule) => `
    <div class="stat-row">
      <span>${escapeHtml(rule.dayType === "highlighted" ? "Kiemelt" : "Normál")} · ${escapeHtml(rule.weekdays || "-")}</span>
      <strong>${escapeHtml(rule.validFrom || "-")} - ${escapeHtml(rule.validTo || "folyamatos")}</strong>
    </div>
  `).join("");
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
    <p class="updated-at">Forrás: ${escapeHtml(quality.routeSource || "nincs route raw adat")} · napi sor: ${formatCount(quality.dailyRows)} · mart story: ${formatCount(quality.routeStoryRows)} · szabály: ${escapeHtml(quality.dayRuleSource || "-")}</p>
    <div class="stat-rule-list">
      <h4>Alkalmazott napbesorolás</h4>
      ${ruleRows || `<div class="stat-row"><span>Nincs aktív szabály</span><strong>-</strong></div>`}
    </div>
  `;
  bindDailyHistoryControls();
}

async function loadStatistics(options = {}) {
  const monthInput = $("#statistics-month");
  if (monthInput?.value) state.statisticsMonth = monthInput.value;
  if (options.resetHistory) state.statisticsHistoryDate = "";
  state.statisticsQualityTopic = "";
  const requestSeq = ++state.statisticsRequestSeq;
  const requestedHistoryDate = state.statisticsHistoryDate;
  $("#statistics-message").innerHTML = `<div class="notice">Statisztika betöltése...</div>`;
  try {
    const params = new URLSearchParams({ month: state.statisticsMonth, _: String(Date.now()) });
    if (state.user?.canPreviewCouriers && state.workflowPreviewCourierId) {
      params.set("courier", state.workflowPreviewCourierId);
    }
    const payload = await api(`/api/statistics/monthly?${params.toString()}`);
    if (requestSeq !== state.statisticsRequestSeq) return;
    state.statistics = payload;
    const dates = Object.keys(dailyHistoryByDate(payload.dailyHistory || [])).sort().reverse();
    if (!options.resetHistory && requestedHistoryDate && dates.includes(requestedHistoryDate)) {
      state.statisticsHistoryDate = requestedHistoryDate;
    }
    renderStatistics();
  } catch (error) {
    if (requestSeq !== state.statisticsRequestSeq) return;
    state.statistics = null;
    $("#statistics-grid").innerHTML = "";
    $("#statistics-quality").innerHTML = "";
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
    ? `<small>Időkapu: ${routeTimeRange(checkpoint.windowFrom, checkpoint.windowTo)}</small>`
    : "";
  const arrivalText = checkpoint.estimatedArrival || checkpoint.plannedArrival
    ? `<small>${checkpoint.estimatedArrival ? "Várható érkezés" : "Tervezett érkezés"}: ${escapeHtml(checkpoint.estimatedArrival || checkpoint.plannedArrival)}</small>`
    : "";
  const position = checkpoint.position ? `<span class="route-stop-index">${escapeHtml(checkpoint.position)}</span>` : `<span class="route-stop-index">-</span>`;
  const delayClass = checkpoint.isLate ? " delayed" : "";
  const delayText = checkpoint.isLate
    ? `<small class="route-delay-note">Időablakhoz képest késés: ${formatCount(checkpoint.delayMinutes || 0)} perc</small>`
    : "";

  return `
    <div class="route-stop ${cssClass}${delayClass}">
      ${position}
      <div>
        <span>${escapeHtml(title)}</span>
        <strong>${escapeHtml(checkpoint.address || "Cím nincs megadva")}</strong>
        ${windowText}
        ${arrivalText}
        ${delayText}
      </div>
    </div>
  `;
}

function wazeUrl(address) {
  const value = String(address || "").trim();
  if (!value) return "";
  return `https://waze.com/ul?q=${encodeURIComponent(value)}&navigate=yes`;
}

function vehicleLabel(vehicle) {
  if (!vehicle) return "";
  const plate = vehicle.licensePlate || "";
  const car = vehicle.car || "";
  return [plate, car].filter(Boolean).join(" · ");
}

function routeVehicleBlock(vehicle) {
  const label = vehicleLabel(vehicle);
  if (!label) return "";
  const shift = [vehicle.shiftStart, vehicle.shiftEnd].filter(Boolean).join("–");
  const detail = [vehicle.source, vehicle.shiftType, shift].filter(Boolean).join(" · ") || "Aktuális hozzárendelés";
  return `
    <div class="route-current">
      <span>Autó</span>
      <strong>${escapeHtml(label)}</strong>
      <small>${escapeHtml(detail)}</small>
    </div>
  `;
}

async function logRouteAutoDelay(route) {
  const checkpoint = route?.current;
  if (!route?.routeId || !checkpoint?.isLate || isAdminPreviewMode()) return;
  const key = `${route.routeId}:${checkpoint.orderId || checkpoint.position || ""}`;
  if (state.routeAutoDelayKeys.has(key) || localStorage.getItem(`route-auto-delay:${key}`)) return;
  state.routeAutoDelayKeys.add(key);
  try {
    await api("/api/routes/auto-delay", {
      method: "POST",
      body: JSON.stringify({
        route_id: String(route.routeId),
        order_id: checkpoint.orderId || "",
        message: `Időablakhoz képest késés: ${formatCount(checkpoint.delayMinutes || 0)} perc`,
        current_address: checkpoint.address || "",
        current_checkpoint_position: checkpoint.position || null,
      }),
    });
    localStorage.setItem(`route-auto-delay:${key}`, new Date().toISOString());
  } catch (error) {
    state.routeAutoDelayKeys.delete(key);
  }
}

function renderCurrentRoute() {
  const container = ensureRouteCard();
  if (!container) return;

  const payload = state.currentRoute;
  const route = payload?.route;

  if (!payload?.found || !route) {
    container.innerHTML = `
      <div class="route-empty error-state">
        <span class="route-empty-icon">!</span>
        <div>
          <h3>Nincs aktív túra</h3>
          <p>Nem érkezett Kiflis túraadat ehhez a futárhoz. Ha most túrán kellene lenned, kérj ellenőrzést.</p>
        </div>
      </div>
    `;
    return;
  }

  const departure = route.realDeparture || route.plannedDeparture || "";
  const returnTime = route.realReturn || route.plannedReturn || "";
  const current = route.current;
  const nextWaze = wazeUrl(current?.address);
  const currentWindow = current ? routeTimeRange(current.windowFrom, current.windowTo) : "";
  const currentArrival = current?.estimatedArrival || current?.plannedArrival || "";

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

    ${routeVehicleBlock(route.vehicle)}

    ${renderCurrentRouteStory(route)}

    <div class="route-current">
      <span>Következő cím</span>
      <strong>${escapeHtml(current?.address || "Nincs aktuális cím")}</strong>
      <small>${current ? `#${escapeHtml(current.orderId || "-")} · Időkapu: ${escapeHtml(currentWindow || "-")}` : "A túra még nem indult el."}</small>
      ${currentArrival ? `<small>${current?.estimatedArrival ? "Várható érkezés" : "Tervezett érkezés"}: ${escapeHtml(currentArrival)}</small>` : ""}
    </div>

    <div class="route-stop-list">
      ${routeStopBlock("Előző", route.previous)}
      ${routeStopBlock("Utána következő", route.next)}
    </div>

    ${nextWaze ? `<a class="waze-button" href="${nextWaze}" target="_blank" rel="noopener">Irány a cím felé</a>` : ""}

    <button id="delay-alert-button" class="route-problem-button" type="button">
      Problémám van
    </button>
  `;

  $("#delay-alert-button")?.addEventListener(
    "click",
    openDelayAlertDialog
  );
  logRouteAutoDelay(route);
}

async function loadCurrentRoute() {
  try {
    state.currentRoute = await api(withPreviewCourier("/api/routes/current"));
    if (state.currentRoute?.found) {
      const wasQueueActive = Boolean(activeQueue()?.active);
      clearActiveQueue();
      if (wasQueueActive && state.section === "tours" && !isAdminPreviewMode()) {
        showSection("home");
        await loadShifts();
        return;
      }
    }
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
      state.openMuszakproShifts = null;
      renderTabs();
      renderShifts();
      renderOpenMuszakproShifts();
    });
    tabs.appendChild(button);
  }
}

function shiftCard(item, index = 0) {
  const end = item.end ? `–${escapeHtml(item.end)}` : "";
  const actionDisabled = isAdminPreviewMode() ? " disabled" : "";
  const delayButton = `<button class="shift-delay-button" type="button" data-shift-index="${index}"${actionDisabled}>Kések a műszakból</button>`;
  const queueButton = `<button class="shift-queue-button" type="button" data-shift-index="${index}" data-shift-event="queued"${actionDisabled}>Sorba álltam</button>`;
  const returnButton = `<button class="shift-return-button" type="button" data-shift-index="${index}" data-shift-event="returned"${actionDisabled}>Visszaérkeztem</button>`;
  const vehicleText = vehicleLabel(item.vehicle);
  const hasMuszakpro = Boolean(item.muszakpro);
  const hasKiflis = Boolean(item.attendance || item.giriton);
  const sourceChip = (label, ok) => `<span class="source ${ok ? "ok" : "missing"}">${escapeHtml(label)} ${ok ? "✓" : "!"}</span>`;
  return `<article class="shift-card ${!hasMuszakpro || !hasKiflis ? "has-missing-source" : ""}">
    <div class="shift-top">
      <div><p class="shift-time">${escapeHtml(item.start || "Időpont nélkül")}${end}</p><p class="shift-warehouse">${escapeHtml(item.warehouse || "Raktár nincs megadva")}</p></div>
      <span class="shift-state ${escapeHtml(item.status)}">${escapeHtml(item.statusLabel)}</span>
    </div>
    <div class="source-row">
      ${sourceChip("MűszakPro", hasMuszakpro)}
      ${sourceChip("Kiflis", hasKiflis)}
      ${item.bookingCode ? `<span class="source">${escapeHtml(item.bookingCode)}</span>` : ""}
      ${vehicleText ? `<span class="source ok">Autó ${escapeHtml(vehicleText)}</span>` : ""}
    </div>
    <div class="shift-action-grid">
      ${delayButton}
      ${queueButton}
      ${returnButton}
    </div>
  </article>`;
}

function renderShifts() {
  const items = (state.data?.items || []).filter((item) => item.date === state.selectedDate);
  $("#shift-list").innerHTML = items.length
    ? items.map((item, index) => shiftCard(item, index)).join("")
    : `<div class="empty-card">Erre a napra nincs megjeleníthető műszak.</div>`;
  renderQueueStatus();
}

function renderOpenMuszakproShifts() {
  const card = $("#work-offer-card");
  const target = $("#open-muszakpro-list");
  const hasActiveShift = Boolean(activeShift(state.data?.items || []));
  if (card) card.classList.toggle("hidden", hasActiveShift);
  if (hasActiveShift) {
    state.openMuszakproShifts = null;
    if (target) {
      target.classList.add("hidden");
      target.innerHTML = "";
    }
    return;
  }
  if (!target) return;
  const payload = state.openMuszakproShifts;
  if (!payload || payload.date !== state.selectedDate) {
    target.classList.add("hidden");
    target.innerHTML = "";
    return;
  }

  target.classList.remove("hidden");
  const items = payload.items || [];
  if (!items.length) {
    const message = payload.message || "A kiválasztott napra nincs szabad MűszakPro műszak a raktáradhoz.";
    target.innerHTML = `<div class="empty-card">${escapeHtml(message)}</div>`;
    return;
  }

  target.innerHTML = items.map((item) => {
    const end = item.end ? `–${escapeHtml(item.end)}` : "";
    const freeText = Number(item.freeCount || 0) > 1 ? `${formatCount(item.freeCount)} hely` : "1 hely";
    const capacityText = item.capacity ? `Kapacitás: ${formatCount(item.bookedCount || 0)}/${formatCount(item.capacity)}` : "";
    return `<article class="open-shift-card">
      <div>
        <strong>${escapeHtml(item.start || "Időpont nélkül")}${end}</strong>
        <small>${escapeHtml(item.warehouse || "Raktár nincs megadva")} · ${escapeHtml(item.shiftCode || "MűszakPro műszak")}</small>
        <small>Ezt a műszakot a MűszakPro felületén tudod lefoglalni.</small>
        ${capacityText ? `<small>${escapeHtml(capacityText)}</small>` : ""}
      </div>
      <span class="open-shift-count">${escapeHtml(freeText)}</span>
    </article>`;
  }).join("");
}

async function loadOpenMuszakproShifts() {
  const button = $("#open-muszakpro-refresh");
  const selectedDate = state.selectedDate || localDate();
  if (button) {
    button.disabled = true;
    button.textContent = "Nézem...";
  }
  try {
    state.openMuszakproShifts = await api(withPreviewCourier(`/api/muszakpro/open-shifts?day=${encodeURIComponent(selectedDate)}`));
    renderOpenMuszakproShifts();
  } catch (error) {
    state.openMuszakproShifts = {
      date: selectedDate,
      items: [],
      message: error.message || "A szabad MűszakPro műszakok most nem tölthetők be.",
    };
    renderOpenMuszakproShifts();
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Mutasd";
    }
  }
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
    state.data = await api(withPreviewCourier("/api/shifts?days=5"));
    const focusShift = activeOrNextShift(state.data?.items || []);
    state.selectedDate = focusShift?.date || state.selectedDate || localDate();
    renderHero();
    renderTabs();
    renderWarnings();
    renderShifts();
    renderOpenMuszakproShifts();
    loadQueueStatus().catch(() => {});
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

async function sendShiftQueueCheckin(item, button) {
  if (!item || isAdminPreviewMode()) return;
  const originalText = button.textContent;
  const eventType = button.dataset.shiftEvent || "queued";
  button.disabled = true;
  button.textContent = "Mentés...";
  try {
    const payload = await api("/api/shifts/queue-checkin", {
      method: "POST",
      body: JSON.stringify({
        work_date: item.date || "",
        start: item.start || "",
        end: item.end || "",
        warehouse: item.warehouse || "",
        shift_name: item.attendanceShiftName || item.muszakproShiftText || "",
        booking_code: item.bookingCode || "",
        event_type: eventType,
      }),
    });
    if (eventType === "queued") {
      state.queueStatus = payload.queue || {
        active: true,
        queuedAt: new Date().toISOString(),
        aheadCount: 0,
        warehouse: item.warehouse || "",
        shiftName: item.attendanceShiftName || item.muszakproShiftText || "",
      };
      queueStorageWrite(state.queueStatus);
      renderQueueStatus();
    }
    button.textContent = "Rögzítve";
    button.classList.add("sent");
  } catch (error) {
    button.textContent = originalText;
    button.disabled = false;
    $("#warning-list").innerHTML = `<div class="warning-card">${escapeHtml(error.message)}</div>`;
  }
}

$("#shift-list").addEventListener("click", async (event) => {
  const button = event.target.closest(".shift-delay-button, .shift-queue-button, .shift-return-button");
  if (!button) return;
  const items = (state.data?.items || []).filter((item) => item.date === state.selectedDate);
  const index = Number(button.dataset.shiftIndex || 0);
  if (button.classList.contains("shift-queue-button") || button.classList.contains("shift-return-button")) {
    await sendShiftQueueCheckin(items[index], button);
    return;
  }
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

  const invoiceSubmitted = !invoiceUploadReopened() && Boolean(
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

async function loadQueueStatus() {
  if (isAdminPreviewMode()) return;
  const payload = await api("/api/shifts/queue-status");
  state.queueStatus = payload.queue || null;
  queueStorageWrite(state.queueStatus);
  renderQueueStatus();
}

function workflowStatus(key) {
  return String(state.workflow?.states?.[key]?.status || "").toLowerCase();
}

function invoiceUploadReopened() {
  return workflowStatus("invoice_submit") === "open";
}

function invoiceUploadBlockedByExistingDocument() {
  return !invoiceUploadReopened()
    && (Boolean(workflowStep("invoice_submit").done) || Boolean((state.workflow?.documents?.invoice || []).length));
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
      <a class="download-link" href="${escapeHtml(withPreviewCourier(document.downloadUrl || "#"))}">Letöltés</a>
    </div>`).join("")}</div>`;
}

function latestDocumentList(documents) {
  const latestDocuments = [...documents].sort((a, b) => {
    const left = String(a.uploaded_at || a.uploadedAt || a.created_at || "");
    const right = String(b.uploaded_at || b.uploadedAt || b.created_at || "");
    return right.localeCompare(left);
  });
  return documentList(latestDocuments.slice(0, 1));
}

function finalDocumentList(documents) {
  const rankedDocuments = [...documents].sort((a, b) => {
    const finalScore = (document) => {
      const text = [
        document.title,
        document.file_name,
        document.note,
      ].map((value) => String(value || "").toLowerCase()).join(" ");
      return text.includes("végleges") || text.includes("vegleges") ? 1 : 0;
    };
    const scoreDiff = finalScore(b) - finalScore(a);
    if (scoreDiff) return scoreDiff;
    const left = String(a.uploaded_at || a.uploadedAt || a.created_at || "");
    const right = String(b.uploaded_at || b.uploadedAt || b.created_at || "");
    return right.localeCompare(left);
  });
  return documentList(rankedDocuments.slice(0, 1));
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
    <div class="complaint-row"><div><strong>${escapeHtml(response.note || response.title || "Admin valasz")}</strong><small>${escapeHtml(response.uploaded_by || "admin")} · ${response.uploaded_at ? new Date(response.uploaded_at).toLocaleString("hu-HU") : ""}</small>${response.downloadUrl ? `<a class="download-link" href="${escapeHtml(withPreviewCourier(response.downloadUrl))}">Valasz letoltese</a>` : ""}</div></div>
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
  let items = (card?.items || []).filter((item) => Number(item.amountHuf || 0));
  if (!items.length && Number(card?.amountHuf || 0)) {
    items = [{
      key: `${card.key || "card"}_total`,
      label: card.label || "Osszesen",
      amountHuf: Number(card.amountHuf || 0),
      note: "Osszesitett havi adat.",
    }];
  }
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
  const displayCards = cards.filter((card) => card.key !== "deductions");
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
    <div class="financial-card-grid">
      ${displayCards.map((card) => `
        <details class="financial-card ${escapeHtml(card.tone || "")}" ${["payable", "bonus_malus"].includes(card.key) ? "open" : ""}>
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

function renderLegacyTigDocumentPanel(documents) {
  return `
    <div class="notice">Régi TIG dokumentum alapján kezelhető folyamat. Nyisd meg a végleges TIG PDF-et, majd fogadd el vagy küldj reklamációt.</div>
    ${finalDocumentList(documents)}
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
  const rows = (tig.rows || []).filter((row) => row.key !== "cash_deduction" && row.key !== "tig_cash_deduction");
  const transferRows = rows.filter((row) => row.key !== "cash_service");
  const cashRows = rows.filter((row) => row.key === "cash_service");
  const renderTigRows = (items) => `
    <div class="tig-table">
      <div class="tig-row head"><span>Tétel</span><span>Netto</span><span>ÁFA</span><span>Brutto</span></div>
      ${items.map((row) => `
        <div class="tig-row ${Number(row.grossHuf || 0) < 0 ? "deduction" : ""}">
          <span><strong>${escapeHtml(row.label || "")}</strong><small>${escapeHtml(row.note || "")}</small></span>
          <span>${tigValue(row.netHuf)}</span>
          <span>${row.vatLabel ? escapeHtml(row.vatLabel) : tigValue(row.vatHuf)}</span>
          <span>${tigValue(row.grossHuf)}</span>
        </div>
      `).join("")}
    </div>
  `;
  const buyer = tig.buyer || {};
  const buyerBlock = buyer.name ? `
    <section class="tig-buyer-card">
      <span>${escapeHtml(buyer.label || "Vevő")}</span>
      <strong>${escapeHtml(buyer.name || "")}</strong>
      <small>${escapeHtml(buyer.postalCity || "")}</small>
      <small>${escapeHtml(buyer.address || "")}</small>
      <small>Adószám: ${escapeHtml(buyer.taxNumber || "")}</small>
      ${buyer.periodLabel ? `<small>Teljesítési időszak: ${escapeHtml(buyer.periodLabel)}</small>` : ""}
      ${buyer.performanceDate ? `<small>Teljesítés: ${escapeHtml(buyer.performanceDate)}</small>` : ""}
      ${buyer.paymentDueDate ? `<small>Fizetési határidő: ${escapeHtml(buyer.paymentDueDate)}</small>` : ""}
      ${buyer.note ? `<small>Megjegyzés: ${escapeHtml(buyer.note)}</small>` : ""}
    </section>
  ` : "";
  return `
    <section class="tig-total-card">
      <span>TIG végösszeg</span>
      <strong>${tigValue(tig.finalTotalHuf)}</strong>
      <small>${escapeHtml(tig.month || state.workflowMonth)}</small>
    </section>
    ${buyerBlock}
    ${renderTigRows(transferRows)}
    ${cashRows.length ? `<section class="tig-buyer-card"><span>KP külön számla</span><strong>Készpénzes teljesítés</strong><small>A KP nem levonásként jelenik meg, külön számlás tétel.</small></section>${renderTigRows(cashRows)}` : ""}
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
  const breakdown = state.workflow?.financialBreakdown || {};
  const tig = state.workflow?.tigBreakdown || {};
  const settlementVisibleData = action === "settlement" && !isExtraWorkflow() && (Boolean(breakdown.available) || documents.length > 0);
  const tigVisibleData = action === "tig" && !isExtraWorkflow() && (Boolean(tig.available) || documents.length > 0);
  const locked = Boolean(documentStep.locked) && !settlementVisibleData && !tigVisibleData;
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
  panel.classList.toggle("accepted", accepted);
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
    const tigReady = Boolean(tig.available) || documents.length > 0;
    const tigContent = tig.available
      ? renderTigBreakdown()
      : documents.length
        ? renderLegacyTigDocumentPanel(documents)
        : renderTigBreakdown();
    panel.innerHTML = `
      <div class="process-title"><span class="step-code">${stepNumber}</span><div><h3>TIG és elfogadás</h3><p>A TIG tételes bontása itt jelenik meg, külön KP sorral.</p></div></div>
      ${locked ? `<div class="empty-card">Az előző lépés még nincs lezárva.</div>` : tigContent}
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
  const docs = state.workflow?.documents || {};
  const showSettlement = !isExtraWorkflow() && (
    Boolean(state.workflow?.financialBreakdown?.available)
    || Boolean((docs.settlement || []).length)
  );
  const showTig = !isExtraWorkflow() && (
    Boolean(state.workflow?.tigBreakdown?.available)
    || Boolean((docs.tig || []).length)
  );
  ["settlement-panel", "tig-panel", "invoice-submit-panel", "invoice-check-panel"].forEach((id) => {
    const panel = $(`#${id}`);
    const visible = id === panelId
      || (showSettlement && id === "settlement-panel")
      || (showTig && id === "tig-panel");
    if (panel) panel.classList.toggle("hidden", !visible);
  });
}

function renderWorkflow() {
  applyInvoiceValidationOverride();
  renderWorkflowSteps();
  renderDocumentPanel("settlement", "Elszámolás és elfogadás", 1);
  renderDocumentPanel("tig", "TIG és elfogadás", 3);
  const readOnly = Boolean(state.workflow?.viewerReadOnly);
  const invoiceAlreadySubmitted = invoiceUploadBlockedByExistingDocument();
  const invoiceLocked = readOnly || (!invoiceUploadReopened() && Boolean(workflowStep("invoice_submit").locked)) || invoiceAlreadySubmitted;
  setPanelLocked("#invoice-submit-panel", invoiceLocked);
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
    state.serviceWorkerRegistration = await navigator.serviceWorker.register("/sw.js?v=90");
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
  const previewReadOnly = isAdminPreviewMode();

  const courierIdInput = $("#profile-courier-id");
  const courierId = String(courierIdInput?.value || "").trim();
  if (courierIdInput) {
    courierIdInput.readOnly = previewReadOnly || Boolean(courierId);
    courierIdInput.toggleAttribute("aria-readonly", previewReadOnly || Boolean(courierId));
    courierIdInput.classList.toggle("locked", previewReadOnly || Boolean(courierId));
    courierIdInput.title = courierId
      ? "A futár ID már rögzítve van, ezért nem módosítható."
      : "A futár ID csak addig írható, amíg üres.";
  }

  form.querySelectorAll("input, select").forEach((input) => {
    if (input.id === "profile-courier-id") return;
    if (input.tagName === "SELECT") {
      input.disabled = previewReadOnly;
    } else {
      input.readOnly = previewReadOnly;
      input.toggleAttribute("aria-readonly", previewReadOnly);
    }
    input.classList.toggle("locked", previewReadOnly);
  });

  const submitButton = form.querySelector('button[type="submit"]');
  if (submitButton) submitButton.hidden = previewReadOnly;
}

function fillBillingProfile(data = {}) {
  const values = {
    "#profile-courier-id": data.courier_id || state.user?.courier_id || state.user?.id || "",
    "#profile-courier-name": data.courier_name || state.user?.username || "",
    "#profile-phone-number": data.phone_number || state.user?.phone || "",
    "#profile-warehouse": data.warehouse_name || "",
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
    const payload = await api(withPreviewCourier("/api/profile/billing"));
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

    if (isAdminPreviewMode()) {
      setBillingMessage("Admin előnézet: a kiválasztott futár profiladatai csak olvashatók.");
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
      warehouse_name: $("#profile-warehouse")?.value || "",
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
    <a href="${escapeHtml(withPreviewCourier(photo.url || "#"))}" target="_blank" rel="noopener">
      <img src="${escapeHtml(withPreviewCourier(photo.url || "#"))}" alt="${escapeHtml(photo.label || `Fotó ${index + 1}`)}" loading="lazy" />
      <span>${escapeHtml(photo.label || `Fotó ${index + 1}`)}</span>
    </a>
  `).join("")}</div>`;
}

function comparisonBlock(report) {
  if (!report.comparisonStatus || report.comparisonStatus === "not_run") return "";
  const labels = {
    no_previous: "AI: nincs korábbi fotó",
    not_configured: "AI nincs konfigurálva",
    missing_photos: "AI: hiányzó fotó",
    failed: "AI hiba",
    checked: "AI ellenőrizve",
    possible_new_damage: "AI: gyanús új sérülés",
  };
  return `
    <div class="ai-comparison ${escapeHtml(report.comparisonStatus)}">
      <strong>${escapeHtml(labels[report.comparisonStatus] || "AI összehasonlítás")}</strong>
      ${report.comparisonNote ? `<p>${escapeHtml(report.comparisonNote)}</p>` : ""}
    </div>
  `;
}

function renderConditionReports({ targetSelector, reports, emptyText, title }) {
  const target = $(targetSelector);
  if (!target) return;
  if (!reports.length) {
    target.innerHTML = `<div class="empty-card">${escapeHtml(emptyText)}</div>`;
    return;
  }

  target.innerHTML = `
    <div class="device-history-head">
      <strong>${escapeHtml(title)}</strong>
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
        ${comparisonBlock(report)}
        <div class="device-report-meta">
          <span>${Number(report.photoCount || 0)} fotó</span>
        </div>
        ${deviceReportPhotos(report.photos || [])}
      </article>
    `).join("")}
  `;
}

function renderDeviceReports() {
  renderConditionReports({
    targetSelector: "#device-condition-history",
    reports: state.deviceReports || [],
    emptyText: "Még nincs rögzített telefon állapot.",
    title: "Előzmények",
  });
}

async function loadDeviceReports() {
  const target = $("#device-condition-history");
  if (!target) return;
  target.innerHTML = `<div class="empty-card">Telefon előzmények betöltése...</div>`;
  try {
    const payload = await api(withPreviewCourier("/api/devices/reports"));
    state.deviceReports = payload.reports || [];
    renderDeviceReports();
  } catch (error) {
    target.innerHTML = `<div class="notice error">A telefon előzmények nem tölthetők be: ${escapeHtml(error.message)}</div>`;
  }
}

function renderVehicleReports() {
  const plate = String($("#vehicle-license-plate")?.value || "").trim();
  renderConditionReports({
    targetSelector: "#vehicle-condition-history",
    reports: state.vehicleReports || [],
    emptyText: plate
      ? "Ehhez a rendszámhoz még nincs korábbi autó állapot."
      : "Írd be a rendszámot, és megjelennek az autó korábbi fotós ellenőrzései.",
    title: plate ? `Előzmények: ${plate.toUpperCase()}` : "Autó előzmények",
  });
}

function vehicleAssignmentRows(items = []) {
  if (!items.length) return `<div class="empty-card">Nincs autó-hozzárendelés az adott időszakban.</div>`;
  return items.map((item) => `
    <article class="vehicle-assignment-row">
      <div>
        <strong>${escapeHtml(item.licensePlate || "-")}</strong>
        <small>${escapeHtml(item.car || "Autó típus nélkül")}</small>
      </div>
      <div>
        <strong>${escapeHtml(item.driverName || "-")}</strong>
        <small>${escapeHtml(item.date || "-")} · ${escapeHtml([item.shiftStart, item.shiftEnd].filter(Boolean).join("–") || "-")}</small>
      </div>
      ${item.shiftType ? `<span>${escapeHtml(item.shiftType)}</span>` : `<span>-</span>`}
    </article>
  `).join("");
}

function renderVehicleAssignments() {
  const target = $("#vehicle-assignment-history");
  if (!target) return;
  target.innerHTML = `
    <div class="device-history-head">
      <strong>Saját autóhasználat</strong>
      <span>${(state.vehicleAssignments || []).length} bejegyzés</span>
    </div>
    ${vehicleAssignmentRows(state.vehicleAssignments || [])}
  `;
}

async function loadVehicleAssignments() {
  const target = $("#vehicle-assignment-history");
  if (!target) return;
  target.innerHTML = `<div class="empty-card">Autó-hozzárendelések betöltése...</div>`;
  try {
    const payload = await api(withPreviewCourier("/api/vehicles/assignments?days=10"));
    state.vehicleAssignments = payload.items || [];
    renderVehicleAssignments();
  } catch (error) {
    target.innerHTML = `<div class="notice error">Az autó-hozzárendelések nem tölthetők be: ${escapeHtml(error.message)}</div>`;
  }
}

function renderVehicleHrPanel() {
  const panel = $("#vehicle-hr-panel");
  if (!panel) return;
  panel.classList.toggle("hidden", !state.user?.canManageVehicles);
}

function renderVehicleSearchResults(lastUsage, items = []) {
  const target = $("#vehicle-hr-search-results");
  if (!target) return;
  if (!items.length) {
    target.innerHTML = `<div class="empty-card">Nincs találat erre a keresésre.</div>`;
    return;
  }
  target.innerHTML = `
    ${lastUsage ? `<div class="vehicle-last-usage">
      <span>Utolsó használat</span>
      <strong>${escapeHtml(lastUsage.licensePlate || "-")} · ${escapeHtml(lastUsage.driverName || "-")}</strong>
      <small>${escapeHtml(lastUsage.date || "-")} · ${escapeHtml([lastUsage.shiftStart, lastUsage.shiftEnd].filter(Boolean).join("–") || "-")} · ${escapeHtml(lastUsage.car || "")}</small>
    </div>` : ""}
    <div class="device-history-head">
      <strong>Keresési találatok</strong>
      <span>${items.length} bejegyzés</span>
    </div>
    ${vehicleAssignmentRows(items)}
  `;
}

async function searchVehicleAssignments() {
  const target = $("#vehicle-hr-search-results");
  const input = $("#vehicle-hr-search");
  if (!target || !input) return;
  const query = String(input.value || "").trim();
  if (!query) {
    target.innerHTML = `<div class="empty-card">Adj meg rendszámot vagy nevet.</div>`;
    return;
  }
  target.innerHTML = `<div class="empty-card">Keresés folyamatban...</div>`;
  try {
    const payload = await api(`/api/vehicles/assignments/search?query=${encodeURIComponent(query)}`);
    state.vehicleSearchResults = payload.items || [];
    renderVehicleSearchResults(payload.lastUsage, state.vehicleSearchResults);
  } catch (error) {
    target.innerHTML = `<div class="notice error">A keresés nem sikerült: ${escapeHtml(error.message)}</div>`;
  }
}

async function loadVehicleReports() {
  const target = $("#vehicle-condition-history");
  if (!target) return;
  if (!state.user?.courierId && state.user?.canManageVehicles) {
    target.innerHTML = `<div class="empty-card">HR nézetben a fotós előzményhez keress rendszámra vagy válassz futár előnézetet admin jogosultsággal.</div>`;
    return;
  }
  const plate = String($("#vehicle-license-plate")?.value || "").trim();
  target.innerHTML = `<div class="empty-card">Autó előzmények betöltése...</div>`;
  try {
    const query = new URLSearchParams();
    if (plate) query.set("serial_number", plate);
    const payload = await api(withPreviewCourier(`/api/vehicles/reports?${query.toString()}`));
    state.vehicleReports = payload.reports || [];
    renderVehicleReports();
  } catch (error) {
    target.innerHTML = `<div class="notice error">Az autó előzmények nem tölthetők be: ${escapeHtml(error.message)}</div>`;
  }
}

async function loadVehicleSection() {
  renderVehicleHrPanel();
  await Promise.all([loadVehicleAssignments(), loadVehicleReports()]);
}

const deviceConditionForm = $("#device-condition-form");
if (deviceConditionForm) {
  deviceConditionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (isAdminPreviewMode()) {
      setDeviceConditionMessage("Admin előnézetben nem rögzíthető telefonállapot.", true);
      return;
    }
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

function setVehicleConditionMessage(message, isError = false) {
  const target = $("#vehicle-condition-message");
  if (!target) return;
  target.textContent = message || "";
  target.classList.toggle("error", Boolean(isError));
}

const vehiclePlateInput = $("#vehicle-license-plate");
vehiclePlateInput?.addEventListener("change", () => {
  state.vehicleReports = [];
  loadVehicleReports();
});
vehiclePlateInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    state.vehicleReports = [];
    loadVehicleReports();
  }
});

$("#vehicle-hr-search-form")?.addEventListener("submit", (event) => {
  event.preventDefault();
  searchVehicleAssignments();
});

const vehicleConditionForm = $("#vehicle-condition-form");
if (vehicleConditionForm) {
  vehicleConditionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (isAdminPreviewMode()) {
      setVehicleConditionMessage("Admin előnézetben nem rögzíthető autóállapot.", true);
      return;
    }
    const button = vehicleConditionForm.querySelector('button[type="submit"]');
    const photos = $("#vehicle-condition-photos")?.files || [];
    if (!photos.length) {
      setVehicleConditionMessage("Legalább egy fotót fel kell tölteni.", true);
      return;
    }
    const form = new FormData(vehicleConditionForm);
    const plate = String($("#vehicle-license-plate")?.value || "").trim();
    setVehicleConditionMessage("Autó állapot mentése és AI összehasonlítás indítása...");
    if (button) button.disabled = true;
    try {
      const payload = await api("/api/vehicles/reports", { method: "POST", body: form });
      vehicleConditionForm.reset();
      $("#vehicle-license-plate").value = plate;
      const comparisonStatus = payload.report?.comparisonStatus || "";
      setVehicleConditionMessage(
        comparisonStatus === "no_previous"
          ? "Autó állapot rögzítve. Még nincs korábbi fotó az AI összehasonlításhoz."
          : "Autó állapot rögzítve, az AI összehasonlítás eredménye mentve."
      );
      await loadVehicleReports();
    } catch (error) {
      setVehicleConditionMessage(`Az autó állapot mentése sikertelen: ${error.message}`, true);
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
  if (invoiceUploadBlockedByExistingDocument()) {
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
    if (submitButton && !invoiceUploadBlockedByExistingDocument()) {
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
const statisticsPreviewCourierInput = $("#statistics-preview-courier");
if (statisticsPreviewCourierInput) statisticsPreviewCourierInput.value = state.workflowPreviewCourierId;
const adminPreviewCourierInput = $("#admin-preview-courier");
if (adminPreviewCourierInput) adminPreviewCourierInput.value = state.workflowPreviewCourierId;
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

function updatePreviewCourier(value) {
  state.workflowPreviewCourierId = String(value || "").trim();
  if (workflowPreviewCourierInput) workflowPreviewCourierInput.value = state.workflowPreviewCourierId;
  if (statisticsPreviewCourierInput) statisticsPreviewCourierInput.value = state.workflowPreviewCourierId;
  if (adminPreviewCourierInput) adminPreviewCourierInput.value = state.workflowPreviewCourierId;
  state.workflowProcess = "";
  state.workflow = null;
  state.statistics = null;
  state.data = null;
  state.currentRoute = null;
  state.billingProfile = null;
  state.deviceReports = [];
  state.vehicleReports = [];
  state.salaryAdvanceRequests = [];
  state.expenseRequests = [];
  state.atmPayments = [];
  state.checkedInvoiceFile = null;
  state.checkedInvoiceMonth = null;
  setAdminPreviewStatus(state.workflowPreviewCourierId ? `Előnézet aktív: ${state.workflowPreviewCourierId}` : "Saját profil aktív.");
  if (state.section === "home") loadShifts();
  if (state.section === "settlement" || state.section === "documents") loadWorkflow().then(() => {
    if (state.section === "documents") renderDocumentsSection();
  });
  if (state.section === "statistics") loadStatistics({ resetHistory: true });
  if (state.section === "salary-advance") loadSalaryAdvanceRequests();
  if (state.section === "expense") loadExpenseRequests();
  if (state.section === "profile") loadBillingProfile();
  if (state.section === "device") loadDeviceReports();
  if (state.section === "vehicle") loadVehicleReports();
  if (state.section === "tours") loadCurrentRoute();
}

workflowPreviewCourierInput?.addEventListener("change", (event) => {
  updatePreviewCourier(event.target.value);
});

statisticsPreviewCourierInput?.addEventListener("change", (event) => {
  updatePreviewCourier(event.target.value);
});

adminPreviewCourierInput?.addEventListener("change", (event) => {
  updatePreviewCourier(event.target.value);
});

adminPreviewCourierInput?.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    event.preventDefault();
    updatePreviewCourier(event.currentTarget.value);
  }
});

$("#admin-preview-open")?.addEventListener("click", () => {
  updatePreviewCourier(adminPreviewCourierInput?.value || "");
});

$("#admin-preview-clear")?.addEventListener("click", () => {
  updatePreviewCourier("");
});

$("#workflow-refresh").addEventListener("click", () => {
  loadWorkflow();
});

$("#statistics-month").addEventListener("change", (event) => {
  state.statisticsMonth = event.target.value || new Date().toISOString().slice(0, 7);
  state.statisticsDay = "";
  state.statisticsQualityTopic = "";
  state.statistics = null;
  loadStatistics({ resetHistory: true });
});

$("#statistics-day").addEventListener("change", (event) => {
  state.statisticsDay = event.target.value || "";
  if (state.statisticsDay) {
    state.statisticsHistoryDate = state.statisticsDay;
  }
  renderStatistics();
});

$("#statistics-refresh").addEventListener("click", () => {
  state.statistics = null;
  state.statisticsQualityTopic = "";
  loadStatistics();
});

$("#statistics-quality")?.addEventListener("click", (event) => {
  const button = event.target.closest("[data-quality-topic]");
  if (!button) return;
  const topic = button.getAttribute("data-quality-topic") || "";
  state.statisticsQualityTopic = state.statisticsQualityTopic === topic ? "" : topic;
  renderStatistics();
});

$("#statistics-breakdown").addEventListener("submit", (event) => {
  const form = event.target.closest(".route-note-form");
  if (!form) return;
  event.preventDefault();
  saveRouteNote(form);
});

$("#salary-advance-start-date").value = state.workflowMonth;
updateSalaryAdvancePreview();
["#salary-advance-amount", "#salary-advance-months"].forEach((selector) => {
  $(selector)?.addEventListener("input", updateSalaryAdvancePreview);
});
$("#salary-advance-refresh")?.addEventListener("click", loadSalaryAdvanceRequests);
$("#salary-advance-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (isAdminPreviewMode()) {
    const message = $("#salary-advance-message");
    if (message) message.textContent = "Admin előnézetben nem indítható előlegigény.";
    return;
  }
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

$("#expense-refresh")?.addEventListener("click", loadExpenseRequests);
$("#expense-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (isAdminPreviewMode()) {
    const message = $("#expense-message");
    if (message) message.textContent = "Admin előnézetben nem küldhető be költségszámla.";
    return;
  }
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const message = $("#expense-message");
  if (button) button.disabled = true;
  if (message) message.textContent = "Költségszámla beküldése...";
  try {
    const formData = new FormData();
    formData.append("request_type", $("#expense-type").value || "fuel");
    formData.append("license_plate", $("#expense-license-plate").value || "");
    formData.append("odometer_km", $("#expense-odometer").value || "0");
    formData.append("amount_huf", String(parseHufInput($("#expense-amount").value)));
    formData.append("invoice_number", $("#expense-invoice-number").value || "");
    formData.append("note", $("#expense-note").value || "");
    const file = $("#expense-file").files?.[0];
    if (file) formData.append("invoice_file", file);
    const payload = await api("/api/expense-requests", {
      method: "POST",
      body: formData,
    });
    state.expenseRequests = payload.requests || [];
    renderExpenseRequests();
    form.reset();
    if (message) message.textContent = "A költségszámla beküldve, külön kifizetési folyamatként jelenik meg.";
  } catch (error) {
    if (message) message.textContent = error.message;
  } finally {
    if (button) button.disabled = false;
  }
});

$("#atm-refresh")?.addEventListener("click", loadAtmPayments);
$("#atm-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (isAdminPreviewMode()) {
    const message = $("#atm-message");
    if (message) message.textContent = "Admin előnézetben nem küldhető be ATM befizetés.";
    return;
  }
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const message = $("#atm-message");
  if (button) button.disabled = true;
  if (message) message.textContent = "ATM befizetés mentése...";
  try {
    const formData = new FormData();
    formData.append("amount_huf", String(parseHufInput($("#atm-amount").value)));
    formData.append("invoice_number", $("#atm-invoice-number").value || "");
    formData.append("note", $("#atm-note").value || "");
    const file = $("#atm-file").files?.[0];
    if (file) formData.append("receipt_file", file);
    const payload = await api("/api/atm-payments", {
      method: "POST",
      body: formData,
    });
    state.atmPayments = payload.payments || [];
    renderAtmPayments(payload.balance || null);
    form.reset();
    if (message) message.textContent = "Az ATM befizetés rögzítve.";
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
    state.queueStatus = queueStorageRead();
    renderQueueStatus();
    showApp();
    if (String(state.user.role || "").toLowerCase() === "hr") {
      showSection("vehicle");
    } else {
      showSection("home");
      await loadShifts();
    }
  } catch (error) {
    $("#login-error").textContent = error.message;
  }
});

$("#register-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  setAuthMessage("#register-message", "Regisztráció ellenőrzése...");
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
          ? "A futár ID már szerepel a törzsben. Az e-mail címet frissítettük, innen tudsz új jelszót kérni."
          : "A futár ID már szerepel a törzsben. Innen tudsz új jelszót kérni."
      );
      return;
    }
    form.reset();
    setAuthMessage("#register-message", response.message || "Regisztráció rögzítve.");
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
  setAuthMessage("#password-reset-message", "Új jelszó küldése...");
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
        ? "E-mail cím frissítve, az új jelszót elküldtük."
        : response.message || "Az új jelszót elküldtük."
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
  state.vehicleReports = [];
  state.salaryAdvanceRequests = [];
  state.expenseRequests = [];
  state.queueStatus = null;
  state.statistics = null;
  state.game = null;
  state.gameStartedAt = null;
  state.openMuszakproShifts = null;
  renderQueueStatus();
  showLogin();
});
$("#refresh").addEventListener("click", loadShifts);
$("#open-muszakpro-refresh").addEventListener("click", loadOpenMuszakproShifts);
$("#nav-home").addEventListener("click", () => showSection("home"));
$("#nav-settlement").addEventListener("click", () => showSection("settlement"));
$("#nav-statistics").addEventListener("click", () => showSection("statistics"));
$("#nav-phonebook").addEventListener("click", () => showSection("phonebook"));
$("#nav-atm").addEventListener("click", () => showSection("atm"));
$("#nav-salary-advance").addEventListener("click", () => showSection("salary-advance"));
$("#nav-expense").addEventListener("click", () => showSection("expense"));
$("#nav-documents").addEventListener("click", () => showSection("documents"));
$("#nav-profile").addEventListener("click", () => showSection("profile"));
$("#nav-device").addEventListener("click", () => showSection("device"));
$("#nav-vehicle").addEventListener("click", () => showSection("vehicle"));
$("#nav-tours").addEventListener("click", () => showSection("tours"));
$("#nav-game").addEventListener("click", () => showSection("game"));
$("#game-refresh")?.addEventListener("click", loadGame);
$("#nav-coordinator").addEventListener("click", () => showSection("coordinator"));

setInterval(() => {
  currentSectionRefresh().catch(() => {});
}, 5 * 60 * 1000);
startQueueTimer();

let pullStartY = null;
let pullTriggered = false;
window.addEventListener("touchstart", (event) => {
  if (window.scrollY > 0 || $("#app-view")?.classList.contains("hidden")) return;
  pullStartY = event.touches?.[0]?.clientY ?? null;
  pullTriggered = false;
}, { passive: true });

window.addEventListener("touchmove", (event) => {
  if (pullStartY === null || pullTriggered || window.scrollY > 0) return;
  const currentY = event.touches?.[0]?.clientY ?? pullStartY;
  if (currentY - pullStartY > 85) {
    pullTriggered = true;
    currentSectionRefresh().catch(() => {});
  }
}, { passive: true });

window.addEventListener("touchend", () => {
  pullStartY = null;
  pullTriggered = false;
}, { passive: true });

async function start() {
  try {
    const payload = await api("/api/me");
    state.user = payload.user;
    showApp();
    if (String(state.user.role || "").toLowerCase() === "coordinator") {
      showSection("coordinator");
    } else if (String(state.user.role || "").toLowerCase() === "hr") {
      showSection("vehicle");
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
