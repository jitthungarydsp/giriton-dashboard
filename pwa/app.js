const state = {
  user: null,
  data: null,
  selectedDate: null,
  workflow: null,
  workflowMonth: new Date().toISOString().slice(0, 7),
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

function showLogin() {
  $("#login-view").classList.remove("hidden");
  $("#app-view").classList.add("hidden");
}

function showApp() {
  $("#login-view").classList.add("hidden");
  $("#app-view").classList.remove("hidden");
  $("#welcome").textContent = `Szia, ${state.user.username.split(" ")[0]}!`;
}

function showSection(section) {
  state.section = section;
  $("#home-content").classList.toggle("hidden", section !== "home");
  $("#settlement-content").classList.toggle("hidden", section !== "settlement");
  $("#nav-home").classList.toggle("active", section === "home");
  $("#nav-settlement").classList.toggle("active", section === "settlement");
  if (section === "settlement" && !state.workflow) loadWorkflow();
  window.scrollTo({ top: 0, behavior: "smooth" });
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

function shiftCard(item) {
  const end = item.end ? `–${escapeHtml(item.end)}` : "";
  return `<article class="shift-card">
    <div class="shift-top">
      <div><p class="shift-time">${escapeHtml(item.start || "Időpont nélkül")}${end}</p><p class="shift-warehouse">${escapeHtml(item.warehouse || "Raktár nincs megadva")}</p></div>
      <span class="shift-state ${escapeHtml(item.status)}">${escapeHtml(item.statusLabel)}</span>
    </div>
    <div class="source-row">
      <span class="source ${item.muszakpro ? "ok" : ""}">MűszakPro ${item.muszakpro ? "✓" : "–"}</span>
      <span class="source ${item.giriton ? "ok" : ""}">Giriton ${item.giriton ? "✓" : "–"}</span>
      ${item.bookingCode ? `<span class="source">${escapeHtml(item.bookingCode)}</span>` : ""}
    </div>
  </article>`;
}

function renderShifts() {
  const items = (state.data?.items || []).filter((item) => item.date === state.selectedDate);
  $("#shift-list").innerHTML = items.length
    ? items.map(shiftCard).join("")
    : `<div class="empty-card">Erre a napra nincs megjeleníthető műszak.</div>`;
}

function renderHero() {
  const upcoming = (state.data?.items || []).find((item) => item.date >= localDate());
  if (!upcoming) {
    $("#next-shift").textContent = "Nincs közelgő műszak";
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
    state.selectedDate ||= localDate();
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

function complaintList(complaints) {
  if (!complaints.length) return "";
  return `<div class="complaint-list">${complaints.map((complaint) => `
    <div class="complaint-row"><div><strong>${escapeHtml(complaint.message)}</strong><small>${escapeHtml(complaint.status)} · ${new Date(complaint.created_at).toLocaleString("hu-HU")}</small>${complaint.admin_response ? `<div class="notice">Admin válasza: ${escapeHtml(complaint.admin_response)}</div>` : ""}</div></div>
  `).join("")}</div>`;
}

function renderDocumentPanel(action, title, stepNumber) {
  const panel = $(`#${action}-panel`);
  const documents = state.workflow?.documents?.[action] || [];
  const complaints = state.workflow?.complaints?.[action] || [];
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
      : documents.length && !locked
        ? `<div class="accept-row"><button class="primary" id="accept-${action}">✓ Elfogadom a dokumentumot</button></div>`
        : ""}
    ${documents.length && !locked ? `<div class="complaint-box">
      <strong>Reklamáció</strong>
      ${complaintList(complaints)}
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
  $("#invoice-document-list").innerHTML = (state.workflow?.documents?.invoice || []).length
    ? `<div class="complaint-box"><strong>Korábban feltöltött számlák</strong>${documentList(state.workflow.documents.invoice)}</div>`
    : "";
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
  ];
  return {
    month: state.workflowMonth,
    steps: titles.map(([key, title, locked]) => ({ key, title, locked, done: false })),
    states: {},
    documents: { settlement: [], tig: [], invoice: [] },
    complaints: { settlement: [], tig: [] },
    updatedAt: new Date().toISOString(),
  };
}

async function loadWorkflow() {
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

function renderValidation(target, validation, stored = null) {
  const summary = validation.ok
    ? stored === true ? "A számla ellenőrizve és eltárolva." : "Az ellenőrzés sikeres. A számlafeltöltés aktív."
    : `Javítandó számla (${validation.score}%).`;
  target.innerHTML = `<div class="result-box">
    <div class="result-summary ${validation.ok ? "ok" : "error"}">${escapeHtml(summary)}</div>
    ${(validation.checks || []).map((check) => `<div class="check-row ${escapeHtml(check.status)}"><strong>${escapeHtml(check.title)}</strong><br>${escapeHtml(check.detail)}</div>`).join("")}
  </div>`;
}

$("#invoice-check-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  form.append("month", state.workflowMonth);
  showWorkflowMessage("A számla ellenőrzése folyamatban…");
  try {
    const payload = await api("/api/invoices/check", { method: "POST", body: form });
    state.workflow = payload.workflow;
    renderWorkflow();
    renderValidation($("#invoice-check-result"), payload.validation);
    showWorkflowMessage(payload.validation.ok ? "Sikeres ellenőrzés." : "A hibákat javítani kell a feltöltés előtt.", !payload.validation.ok);
  } catch (error) {
    showWorkflowMessage(error.message, true);
  }
});

$("#invoice-submit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  form.append("month", state.workflowMonth);
  showWorkflowMessage("A számla végső ellenőrzése és tárolása folyamatban…");
  try {
    const payload = await api("/api/invoices/submit", { method: "POST", body: form });
    state.workflow = payload.workflow;
    renderWorkflow();
    renderValidation($("#invoice-submit-result"), payload.validation, payload.stored);
    showWorkflowMessage(payload.stored ? "A számla bekerült a dokumentumtárba." : "A számla nem került eltárolásra, mert hibát találtunk.", !payload.stored);
    if (payload.stored) event.currentTarget.reset();
  } catch (error) {
    showWorkflowMessage(error.message, true);
  }
});

$("#workflow-month").value = state.workflowMonth;
$("#workflow-month").addEventListener("change", (event) => {
  state.workflowMonth = event.target.value || new Date().toISOString().slice(0, 7);
  state.workflow = null;
  loadWorkflow();
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

$("#logout").addEventListener("click", async () => {
  await api("/api/logout", { method: "POST" });
  state.user = null;
  state.workflow = null;
  showLogin();
});
$("#refresh").addEventListener("click", loadShifts);
$("#nav-home").addEventListener("click", () => showSection("home"));
$("#nav-settlement").addEventListener("click", () => showSection("settlement"));

async function start() {
  try {
    const payload = await api("/api/me");
    state.user = payload.user;
    showApp();
    showSection("home");
    await loadShifts();
  } catch (_) {
    showLogin();
  }
  if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
}

start();
