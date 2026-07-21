const monthFormatter = new Intl.DateTimeFormat("hu-HU", {
  year: "numeric",
  month: "long",
});

const state = {
  view: "home",
  selectedMonth: "",
  couriers: [],
  courierSearch: "",
  financial: {
    loading: false,
    rows: [],
    payload: null,
    summary: null,
    requestUrl: "",
    saved: false,
    saveWarning: "",
    error: "",
  },
  alertCounts: {
    home: 0,
    settlement: 0,
    tig: 0,
    billing: 0,
    complaints: 0,
  },
};

function $(selector) {
  return document.querySelector(selector);
}

function formatMaybe(value, fallback = "-") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function escapeHtml(value) {
  return formatMaybe(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function parseSelectedMonth() {
  const value = state.selectedMonth || $("#month-select")?.value || "";
  const [year, month] = value.split("-").map((part) => Number(part));
  return {
    year: Number.isFinite(year) ? year : new Date().getFullYear(),
    month: Number.isFinite(month) ? month : new Date().getMonth() + 1,
  };
}

function getFinancialRows(payload) {
  if (Array.isArray(payload)) return payload;
  if (!payload || typeof payload !== "object") return [];

  const keys = ["courierRows", "couriers", "items", "data", "rows", "eligibilities", "content", "results"];
  for (const key of keys) {
    if (Array.isArray(payload[key])) return payload[key];
  }

  return [];
}

function flattenPreviewRow(row) {
  if (!row || typeof row !== "object" || Array.isArray(row)) {
    return { value: row };
  }

  const flat = {};
  Object.entries(row).forEach(([key, value]) => {
    if (value && typeof value === "object") {
      if ("amount" in value) {
        flat[key] = value.amount;
      } else if ("value" in value) {
        flat[key] = value.value;
      } else {
        flat[key] = JSON.stringify(value);
      }
    } else {
      flat[key] = value;
    }
  });
  return flat;
}

function pickPreviewColumns(rows) {
  const preferred = [
    "courierId",
    "courier_id",
    "userId",
    "user_id",
    "id",
    "name",
    "courierName",
    "routes",
    "routeCount",
    "shifts",
    "orders",
    "orderCount",
    "totalCost",
    "costPerRoute",
    "baseFee",
    "bonuses",
    "surcharges",
    "courierDetailUrl",
  ];
  const found = new Set();
  rows.slice(0, 20).forEach((row) => {
    Object.keys(flattenPreviewRow(row)).forEach((key) => found.add(key));
  });
  const ordered = preferred.filter((key) => found.has(key));
  const extra = [...found].filter((key) => !ordered.includes(key)).slice(0, 8);
  return [...ordered, ...extra].slice(0, 14);
}

function showView(view) {
  state.view = view;
  document.querySelectorAll(".view").forEach((section) => {
    section.classList.toggle("hidden", section.id !== view);
  });
  document.querySelectorAll(".top-nav button").forEach((button) => {
    button.classList.toggle("active", button.dataset.view === view);
  });
}

function courierMatchesSearch(row, query) {
  if (!query) return true;
  const haystack = [
    row.courier_id,
    row.courier_name,
    row.email,
    row.phone_number,
    row.warehouse_name,
    row.license_plate,
    row.current_state,
  ]
    .map((value) => String(value || "").toLocaleLowerCase("hu-HU"))
    .join(" ");
  return haystack.includes(query.toLocaleLowerCase("hu-HU"));
}

function renderCouriers() {
  const list = $("#courier-list");
  if (!list) return;

  const rows = state.couriers.filter((row) =>
    courierMatchesSearch(row, state.courierSearch),
  );
  const activeCount = state.couriers.filter((row) => row.active === true).length;

  $("#courier-count").textContent = String(state.couriers.length);
  $("#active-courier-count").textContent = String(activeCount);
  $("#home-warning-count").textContent = String(
    Object.values(state.alertCounts).reduce((sum, value) => sum + Number(value || 0), 0),
  );

  if (!rows.length) {
    list.innerHTML = '<div class="empty-state">Nincs találat erre a szűrésre.</div>';
    return;
  }

  list.innerHTML = rows
    .map((row) => {
      const activeClass = row.active === true ? "active" : "";
      const activeText = row.active === true ? "Aktív" : "Nem aktív";
      return `
        <div class="courier-row">
          <strong>#${escapeHtml(row.courier_id)}</strong>
          <div>
            <strong>${escapeHtml(row.courier_name)}</strong>
            <small>${escapeHtml(row.email)}</small>
          </div>
          <div>
            <strong>${escapeHtml(row.warehouse_name)}</strong>
            <small>${escapeHtml(row.phone_number)}</small>
          </div>
          <div>
            <strong>${escapeHtml(row.license_plate)}</strong>
            <small>${escapeHtml(row.current_state)}</small>
          </div>
          <span class="status-pill ${activeClass}">${activeText}</span>
        </div>
      `;
    })
    .join("");
}

function renderFinancialOverview() {
  const rowCount = $("#financial-row-count");
  const payloadType = $("#financial-payload-type");
  const warehouseLabel = $("#financial-warehouse-label");
  const saveStatus = $("#financial-save-status");
  const status = $("#financial-status");
  const head = $("#financial-preview-head");
  const body = $("#financial-preview-body");
  const warehouseSelect = $("#financial-warehouse");

  if (!rowCount || !payloadType || !warehouseLabel || !saveStatus || !status || !head || !body) {
    return;
  }

  const warehouseId = warehouseSelect?.value || "1";
  warehouseLabel.textContent = warehouseId === "2" ? "BUD2" : "BUD1";

  const summary = state.financial.summary || {};
  rowCount.textContent = String(summary.rowCount || state.financial.rows.length || 0);
  payloadType.textContent = summary.payloadType
    ? `Payload: ${summary.payloadType}`
    : "Még nincs lekérés";

  if (state.financial.loading) {
    saveStatus.textContent = "...";
    status.className = "notice muted";
    status.textContent = "Courier Hub adatok lekérése folyamatban...";
    body.innerHTML = "<tr><td>Betöltés...</td></tr>";
    head.innerHTML = "";
    return;
  }

  if (state.financial.error) {
    saveStatus.textContent = "Hiba";
    status.className = "notice danger";
    status.textContent = state.financial.error;
    head.innerHTML = "";
    body.innerHTML = "<tr><td>A lekeres hibara futott.</td></tr>";
    return;
  }

  if (!state.financial.payload) {
    saveStatus.textContent = "-";
    status.className = "notice muted";
    status.textContent = "Válassz hónapot és raktárt, majd indítsd a lekérést.";
    head.innerHTML = "";
    body.innerHTML = "<tr><td>Még nincs betöltött Courier Hub adat.</td></tr>";
    return;
  }

  saveStatus.textContent = state.financial.saved ? "OK" : "Nincs mentve";
  status.className = state.financial.saveWarning ? "notice danger" : "notice success";
  status.innerHTML = `
    Lekérés kész és raw mentés lefutott.
    <span class="soft-link">${escapeHtml(state.financial.requestUrl)}</span>
  `;

  const rows = state.financial.rows;
  if (!rows.length) {
    head.innerHTML = "";
    body.innerHTML = "<tr><td>A válaszban nem találtam listás futár sort, a raw ettől még mentésre került.</td></tr>";
    return;
  }

  const columns = pickPreviewColumns(rows);
  head.innerHTML = `<tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>`;
  body.innerHTML = rows
    .slice(0, 50)
    .map((row) => {
      const flat = flattenPreviewRow(row);
      return `<tr>${columns.map((column) => `<td>${escapeHtml(flat[column])}</td>`).join("")}</tr>`;
    })
    .join("");
}

function renderFinancialOverviewClean() {
  const rowCount = $("#financial-row-count");
  const payloadType = $("#financial-payload-type");
  const warehouseLabel = $("#financial-warehouse-label");
  const saveStatus = $("#financial-save-status");
  const status = $("#financial-status");
  const head = $("#financial-preview-head");
  const body = $("#financial-preview-body");
  const warehouseSelect = $("#financial-warehouse");

  if (!rowCount || !payloadType || !warehouseLabel || !saveStatus || !status || !head || !body) {
    return;
  }

  const warehouseId = warehouseSelect?.value || "1";
  warehouseLabel.textContent = warehouseId === "2" ? "BUD2" : "BUD1";

  const summary = state.financial.summary || {};
  rowCount.textContent = String(summary.rowCount || state.financial.rows.length || 0);
  payloadType.textContent = summary.payloadType
    ? `Payload: ${summary.payloadType}`
    : "Meg nincs lekeres";

  if (state.financial.loading) {
    saveStatus.textContent = "...";
    status.className = "notice muted";
    status.textContent = "Courier Hub adatok lekerese folyamatban...";
    head.innerHTML = "";
    body.innerHTML = "<tr><td>Betoltes...</td></tr>";
    return;
  }

  if (state.financial.error) {
    saveStatus.textContent = "Hiba";
    status.className = "notice danger";
    status.textContent = state.financial.error;
    head.innerHTML = "";
    body.innerHTML = "<tr><td>A lekeres hibara futott.</td></tr>";
    return;
  }

  if (!state.financial.payload) {
    saveStatus.textContent = "-";
    status.className = "notice muted";
    status.textContent = "Valassz honapot es raktart, majd inditsd a lekerest.";
    head.innerHTML = "";
    body.innerHTML = "<tr><td>Meg nincs betoltott Courier Hub adat.</td></tr>";
    return;
  }

  saveStatus.textContent = state.financial.saved ? "OK" : "Nincs mentve";
  status.className = state.financial.saveWarning ? "notice danger" : "notice success";
  status.innerHTML = `
    ${state.financial.saveWarning
      ? escapeHtml(state.financial.saveWarning)
      : "Lekeres kesz es raw mentes lefutott."}
    <span class="soft-link">${escapeHtml(state.financial.requestUrl)}</span>
  `;

  const rows = state.financial.rows;
  if (!rows.length) {
    head.innerHTML = "";
    body.innerHTML = "<tr><td>A valaszban nem talaltam listas futar sort, a raw ettol meg mentheto.</td></tr>";
    return;
  }

  const columns = pickPreviewColumns(rows);
  head.innerHTML = `<tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr>`;
  body.innerHTML = rows
    .slice(0, 50)
    .map((row) => {
      const flat = flattenPreviewRow(row);
      return `<tr>${columns.map((column) => `<td>${escapeHtml(flat[column])}</td>`).join("")}</tr>`;
    })
    .join("");
}

renderFinancialOverview = renderFinancialOverviewClean;

async function loadFinancialOverview() {
  const button = $("#load-financial-overview");
  const warehouseSelect = $("#financial-warehouse");
  const { year, month } = parseSelectedMonth();
  const warehouseId = Number(warehouseSelect?.value || 1);

  state.financial.loading = true;
  renderFinancialOverview();
  if (button) button.disabled = true;

  try {
    const params = new URLSearchParams({
      year: String(year),
      month: String(month),
      warehouse_id: String(warehouseId),
      dsp_id: "8",
      save_raw: "true",
    });
    const response = await fetch(`/api/settlement/financial-overview?${params.toString()}`, {
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      let detail = `HTTP ${response.status}`;
      try {
        const errorPayload = await response.json();
        detail = errorPayload.detail || detail;
      } catch (_) {}
      throw new Error(detail);
    }

    const payload = await response.json();
    const rows = Array.isArray(payload.rows) ? payload.rows : getFinancialRows(payload.payload);
    state.financial = {
      loading: false,
      rows,
      payload: payload.payload,
      summary: payload.summary || { rowCount: rows.length },
      requestUrl: payload.requestUrl || "",
      saved: payload.saved === true,
      saveWarning: payload.saveWarning || "",
      error: "",
    };
  } catch (error) {
    state.financial.loading = false;
    state.financial.payload = null;
    state.financial.rows = [];
    state.financial.summary = null;
    state.financial.requestUrl = "";
    state.financial.saved = false;
    state.financial.saveWarning = "";
    state.financial.error = `Courier Hub lekeres sikertelen: ${error.message}`;
    const status = $("#financial-status");
    if (status) {
      status.className = "notice danger";
      status.textContent = `Courier Hub lekérés sikertelen: ${error.message}`;
    }
  } finally {
    if (button) button.disabled = false;
    renderFinancialOverview();
  }
}

async function loadCouriers() {
  const list = $("#courier-list");
  if (list) {
    list.innerHTML = '<div class="empty-state">Futár törzs betöltése...</div>';
  }

  try {
    const response = await fetch("/api/settlement/couriers", {
      headers: { Accept: "application/json" },
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const payload = await response.json();
    state.couriers = Array.isArray(payload.couriers) ? payload.couriers : [];
    setAlertCounts(payload.alertCounts || {});
    renderCouriers();
  } catch (error) {
    state.couriers = [];
    if (list) {
      list.innerHTML = `
        <div class="empty-state">
          A DB kapcsolat még nincs bekötve ehhez a nézethez, vagy az API nem fut.
          Indítás: python elszamolas_api.py
        </div>
      `;
    }
  }
}

function buildMonthOptions(monthCount = 12) {
  const select = $("#month-select");
  if (!select) return;

  const today = new Date();
  select.innerHTML = "";

  for (let index = 0; index < monthCount; index += 1) {
    const date = new Date(today.getFullYear(), today.getMonth() - index, 1);
    const value = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}`;
    const option = document.createElement("option");
    option.value = value;
    option.textContent = monthFormatter.format(date);
    select.append(option);
  }

  state.selectedMonth = select.value;
  select.addEventListener("change", () => {
    state.selectedMonth = select.value;
    document.dispatchEvent(
      new CustomEvent("settlement-month-change", {
        detail: { month: state.selectedMonth },
      }),
    );
  });
}

function setAlertCounts(counts = {}) {
  state.alertCounts = { ...state.alertCounts, ...counts };

  document.querySelectorAll("[data-badge]").forEach((badge) => {
    const key = badge.dataset.badge;
    const count = Number(state.alertCounts[key] || 0);
    badge.textContent = String(count);
    badge.classList.toggle("hidden", count <= 0);
    badge.setAttribute("aria-label", `${count} nyitott figyelmeztetés`);
  });

  const homeWarningCount = $("#home-warning-count");
  if (homeWarningCount) {
    homeWarningCount.textContent = String(
      Object.values(state.alertCounts).reduce((sum, value) => sum + Number(value || 0), 0),
    );
  }
}

function initNavigation() {
  document.querySelectorAll(".top-nav button").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view));
  });
}

function initHome() {
  const refreshButton = $("#refresh-couriers");
  const searchInput = $("#courier-search");

  if (refreshButton) {
    refreshButton.addEventListener("click", loadCouriers);
  }

  if (searchInput) {
    searchInput.addEventListener("input", () => {
      state.courierSearch = searchInput.value.trim();
      renderCouriers();
    });
  }
}

function initSettlement() {
  const loadButton = $("#load-financial-overview");
  const warehouseSelect = $("#financial-warehouse");

  if (loadButton) {
    loadButton.addEventListener("click", loadFinancialOverview);
  }

  if (warehouseSelect) {
    warehouseSelect.addEventListener("change", renderFinancialOverview);
  }

  document.addEventListener("settlement-month-change", () => {
    state.financial = {
      loading: false,
      rows: [],
      payload: null,
      summary: null,
      requestUrl: "",
      saved: false,
      saveWarning: "",
      error: "",
    };
    renderFinancialOverview();
  });

  renderFinancialOverview();
}

function initMonth() {
  buildMonthOptions();
  setAlertCounts();
}

function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.register("./sw.js?v=5").catch(() => {});
}

initMonth();
initNavigation();
initHome();
initSettlement();
showView(state.view);
loadCouriers();
registerServiceWorker();

window.elszamolasApp = {
  setAlertCounts,
  getSelectedMonth: () => state.selectedMonth,
};
