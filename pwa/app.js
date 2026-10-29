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
  coordinatorLiveMap: null,
  departureHelper: null,
  coordinatorLeafletMap: null,
  coordinatorSchedule: null,
  coordinatorScheduleDay: localDate(),
  coordinatorScheduleView: "calendar",
  coordinatorScheduleWarehouse: "",
  coordinatorScheduleRequestSeq: 0,
  coordinatorScheduleActionActive: false,
  todayWorkers: null,
  todayWorkersQuery: "",
  couriers: [],
  deviceReports: [],
  vehicleReports: [],
  vehicleAssignments: [],
  vehicleAssignmentQuery: "",
  vehicleActiveTab: "today",
  vehicleWarehouseFilter: "",
  vehicleDateFilter: localDate(),
  vehicleVisibleAssignments: [],
  vehicleSearchResults: [],
  vehicleConfigurations: [],
  vehicleConfigurationSetup: null,
  scheduleVehicleConfigurations: [],
  scheduleOpenVehiclePanels: new Set(),
  scheduleVehicleSort: "time",
  queueStatus: null,
  queueTimer: null,
  salaryAdvanceRequests: [],
  expenseRequests: [],
  atmPayments: [],
  registrationRequests: [],
  passwordResetRequests: [],
  documentArchive: [],
  atmSubmitting: false,
  currentRouteLoading: false,
  game: null,
  gameStartedAt: null,
  statistics: null,
  statisticsPrevious: null,
  openMuszakproShifts: null,
  serviceWorkerRegistration: null,
  workflowMonth: new Date().toISOString().slice(0, 7),
  workflowMonths: [],
  workflowMonthsLoadedFor: "",
  workflowMonthLocked: false,
  workflowProcess: "",
  workflowProcesses: [{ id: "", label: "Havi folyamat" }],
  workflowPreviewCourierId: "",
  workflowLoading: false,
  statisticsMonth: new Date().toISOString().slice(0, 7),
  statisticsDay: "",
  statisticsHistoryDate: "",
  statisticsQualityTopic: "",
  statisticsRequestSeq: 0,
  adminStatistics: null,
  adminStatisticsMonth: new Date().toISOString().slice(0, 7),
  adminStatisticsWarehouse: "all",
  adminStatisticsRequestSeq: 0,
  financialStatistics: null,
  financialStatisticsMonth: new Date().toISOString().slice(0, 7),
  financialStatisticsWarehouse: "all",
  financialStatisticsRequestSeq: 0,
  loadingCount: 0,
  loadingTimer: null,
  loadingVisible: false,
  silentLoading: false,
  routeDetails: null,
  routeStatistics: null,
  routeShiftReport: null,
  routeDetailsSelectedIndex: 0,
  routeDetailsQuery: "",
  routeDetailsRouteId: "",
  routeDetailsType: "all",
  routeDetailsReportFields: ["courierId", "courierName", "warehouse", "routeType", "orders", "loading", "routeTime", "fullTime", "over5h", "tip"],
  routeDetailsIncludeSummary: true,
  routeDetailsAutoExcel: false,
  routeDetailsDialogShownOnce: false,
  section: "home",
  routeAutoDelayKeys: new Set(),
  routePlannerSelectedStopIndex: null,
  routePlannerRouteKey: "",
  settlementDashboard: null,
  settlementDashboardMonth: previousLocalMonth(),
  settlementDashboardQuery: "",
  settlementDashboardStatusFilter: "",
  settlementDashboardExpandedCourierId: "",
  settlementDashboardExpandedTab: "settlement",
  settlementDashboardEditCourierId: "",
  settlementDashboardDetail: null,
  settlementDashboardDetailCache: {},
  settlementDashboardPayment: null,
  settlementDashboardPaymentDrafts: {},
  settlementQualityDetailsCache: {},
  settlementDashboardSearchTimer: null,
  financialEditCardKey: "",
  financialSnapshots: [],
  financialSnapshotsLoadedFor: "",
  settlementImportStep: 1,
  settlementImportMonth: previousLocalMonth(),
  settlementImportResult: null,
  settlementImportUploading: false,
  settlementImportColumnConfig: {},
  settlementImportColumnConfigSignature: "",
  settlementImportColumnConfigTouched: false,
  settlementImportSheetConfig: {},
  settlementImportSheetConfigSignature: "",
  settlementImportSheetConfigTouched: false,
  settlementImportDraggedColumnId: "",
  settlementImportDraggedSheetId: "",
};
const APP_VERSION = "v255";
const $ = (selector) => document.querySelector(selector);

const ROUTE_REPORT_FIELDS = [
  { key: "date", label: "Munkanap", column: "Munkanap", get: (row) => routeDetailValue(row.date) },
  { key: "courierId", label: "Futár ID", column: "Futár ID", get: (row) => routeDetailValue(row.courierId) },
  { key: "courierName", label: "Futár neve", column: "Futár neve", get: (row) => routeDetailValue(row.courierName) },
  { key: "warehouse", label: "Raktár", column: "Raktár", get: (row) => routeDetailValue(row.warehouse) },
  { key: "warehouseAddress", label: "Raktár cím", column: "Raktár cím", get: (row) => routeDetailValue(row.warehouseAddress) },
  { key: "shiftName", label: "Műszak neve", column: "Műszak", get: (row) => routeDetailValue(row.shiftName) },
  { key: "shiftStart", label: "Műszak kezdés", column: "Műszak kezdés", get: (row) => shortDateTime(row.shiftStartAt) },
  { key: "shiftEnd", label: "Műszak vége", column: "Műszak vége", get: (row) => shortDateTime(row.shiftEndAt) },
  { key: "shiftAvailable", label: "Elérhető műszakra", column: "Elérhető", get: (row) => shortDateTime(row.shiftAvailableAt) },
  { key: "queueStarted", label: "Sorbaállt", column: "Sorbaállt", get: (row) => shortDateTime(row.queueStartedAt) },
  { key: "actualShiftStart", label: "Tényleges műszak kezdés", column: "Tényleges kezdés", get: (row) => shortDateTime(row.actualShiftStartAt) },
  { key: "routeAssigned", label: "Túrát kapott", column: "Túrát kapott", get: (row) => shortDateTime(row.routeAssignedAt) },
  { key: "plannedDeparture", label: "Tervezett indulás", column: "Tervezett indulás", get: (row) => shortDateTime(row.plannedDepartureAt) },
  { key: "departed", label: "Indulás a raktárból", column: "Indulás", get: (row) => shortDateTime(row.departedAt) },
  { key: "plannedReturn", label: "Tervezett visszaérkezés", column: "Tervezett vissza", get: (row) => shortDateTime(row.plannedReturnAt) },
  { key: "returned", label: "Tényleges visszaérkezés", column: "Visszaérkezés", get: (row) => shortDateTime(row.returnedAt) },
  { key: "routeType", label: "Túratípus", column: "Túratípus", get: (row) => routeDetailValue(row.routeTypeLabel) },
  { key: "orders", label: "Rendelés / cím", column: "Címek", summary: "orders", get: (row) => formatCount(row.orders || 0) },
  { key: "stops", label: "Stopok", column: "Stopok", summary: "stops", get: (row) => formatCount(row.stops || 0) },
  { key: "waiting", label: "Várakozás", column: "Várakozás", summary: "waitingAvg", get: (row) => routeDetailMinutes(row.waitingMinutes) },
  { key: "plannedLoading", label: "Tervezett bepakolás", column: "Terv bepakolás", get: (row) => routeDetailMinutes(row.plannedLoadingMinutes) },
  { key: "loading", label: "Bepakolás", column: "Bepakolás", summary: "loadingAvg", get: (row) => routeDetailMinutes(row.loadingMinutes) },
  { key: "plannedRouteTime", label: "Tervezett túraidő", column: "Terv túraidő", get: (row) => routeDetailClock(row.plannedRouteMinutes) },
  { key: "routeTime", label: "Túraidő", column: "Túra bepakolás nélkül", summary: "routeAvg", get: (row) => routeDetailClock(row.routeMinutes) },
  { key: "fullTime", label: "Teljes idő", column: "Túra bepakolással", summary: "fullAvg", get: (row) => routeDetailClock(row.totalMinutes) },
  { key: "over5h", label: "5 óra felett", column: "5h+", summary: "over5h", get: (row) => Number(row.totalMinutes || row.routeMinutes || 0) > 300 ? "Igen" : "Nem" },
  { key: "delay", label: "Késés a túrán", column: "Késés", get: (row) => `${formatCount(row.routeDelayCount || 0)} db` },
  { key: "delayMinutes", label: "Késés percek", column: "Késés perc", get: (row) => routeDetailMinutes(row.routeDelayMinutes) },
  { key: "plannedKm", label: "Tervezett km", column: "Tervezett km", get: (row) => routeDetailDistance(row.hubPlannedKm) },
  { key: "hubMileageKm", label: "Hub mileage km", column: "Hub km", get: (row) => routeDetailDistance(row.hubMileageKm) },
  { key: "actualKm", label: "Hub tényleges km", column: "Tényleges km", get: (row) => routeDetailDistance(row.actualKm) },
  { key: "googleRouteKm", label: "Google útvonal km", column: "Google km", get: (row) => routeDetailDistance(row.googleRouteKm) },
  { key: "distance", label: "Címekből számolt km", column: "Számolt km", get: (row) => routeDetailDistance(routeDetailCalculatedKm(row)) },
  { key: "distanceDelta", label: "Km eltérés", column: "Km eltérés", get: (row) => routeDetailDistance(row.distanceDeltaKm) },
  { key: "distanceSource", label: "Km forrás", column: "Km forrás", get: (row) => routeDetailValue(row.distanceSource || row.distanceStatus) },
  { key: "nextShift", label: "Következő műszak aznap", column: "Következő műszak", get: (row) => routeDetailValue(row.nextShiftSameDay) },
  { key: "vehiclePlate", label: "Rendszám", column: "Rendszám", get: (row) => routeDetailValue(row.vehiclePlate) },
  { key: "vehicleModel", label: "Autó", column: "Autó", get: (row) => routeDetailValue(row.vehicleModel || row.vehicleLabel) },
  { key: "kifliVehicle", label: "Kiflis autó", column: "Kiflis autó", get: (row) => routeDetailValue(row.kifliVehicle) },
  { key: "tip", label: "Borravaló", column: "Borravaló", summary: "tipSum", get: (row) => formatHuf(row.tipHuf || 0) },
  { key: "tipSource", label: "Borravaló forrás", column: "Tip forrás", get: (row) => routeDetailValue(row.tipSource) },
  { key: "dataSource", label: "Adatforrás", column: "Forrás", get: (row) => routeDetailValue(row.dataSource) },
  { key: "narrative", label: "Szöveges összefoglaló", column: "Összefoglaló", get: (row) => routeDetailValue(row.narrative) },
];

const DEFAULT_ROUTE_REPORT_FIELDS = ["courierId", "courierName", "warehouse", "routeType", "orders", "loading", "routeTime", "fullTime", "over5h", "tip"];
const QUEUE_STORAGE_KEY = "giriton-active-queue";
const ROUTE_LIVE_REFRESH_MS = 2 * 60 * 1000;
const COORDINATOR_LIVE_REFRESH_MS = 60 * 1000;
const VEHICLE_LIVE_REFRESH_MS = 60 * 1000;
const SCHEDULE_BOOKING_JOB_POLL_MS = 10000;
const SCHEDULE_BOOKING_JOB_MAX_POLLS = 72;
const LEAFLET_CSS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const LEAFLET_JS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
const PHONEBOOK_CONTACTS = [
  { label: "Diszpécser", phone: "+3612000391", note: "Kifli támogatás" },
  { label: "FC2 Diszpécser", phone: "+3612002763", note: "FC2 támogatás" },
  { label: "FC2 Logisztikai műszakvezető", phone: "+3612069507", note: "Logisztikai vezető" },
  { label: "FC1 Logisztikai műszakvezető", phone: "+3612001147", note: "Logisztikai vezető" },
  { label: "Ügyfélszolgálat", phone: "0612000882", note: "Központi ügyfélszolgálat" },
];
const HUNGARIAN_COUNTIES = [
  "Bács-Kiskun",
  "Baranya",
  "Békés",
  "Borsod-Abaúj-Zemplén",
  "Csongrád-Csanád",
  "Fejér",
  "Győr-Moson-Sopron",
  "Hajdú-Bihar",
  "Heves",
  "Jász-Nagykun-Szolnok",
  "Komárom-Esztergom",
  "Nógrád",
  "Pest",
  "Somogy",
  "Szabolcs-Szatmár-Bereg",
  "Tolna",
  "Vas",
  "Veszprém",
  "Zala",
];

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setLoadingPanel(visible, message = "Adatok betöltése...") {
  const panel = $("#global-loading-panel");
  if (!panel) return;
  panel.classList.toggle("hidden", !visible);
  panel.setAttribute("aria-hidden", visible ? "false" : "true");
  const text = $("#global-loading-text");
  if (text) text.textContent = message || "Adatok betöltése...";
}

function beginLoading(message = "") {
  state.loadingCount += 1;
  if (state.loadingTimer) return;
  state.loadingTimer = window.setTimeout(() => {
    state.loadingTimer = null;
    if (state.loadingCount > 0) {
      state.loadingVisible = true;
      setLoadingPanel(true, message);
    }
  }, 450);
}

function endLoading() {
  state.loadingCount = Math.max(0, state.loadingCount - 1);
  if (state.loadingCount <= 0) {
    if (state.loadingTimer) {
      window.clearTimeout(state.loadingTimer);
      state.loadingTimer = null;
    }
    state.loadingVisible = false;
    setLoadingPanel(false);
  }
}

async function withSilentLoading(callback) {
  const previous = state.silentLoading;
  state.silentLoading = true;
  try {
    return await callback();
  } finally {
    state.silentLoading = previous;
  }
}

async function api(path, options = {}) {
  const { silentLoading = false, loadingMessage = "", ...fetchOptions } = options;
  const method = String(fetchOptions.method || "GET").toUpperCase();
  const shouldShowLoading = method !== "GET" && !silentLoading && !state.silentLoading;
  if (shouldShowLoading) beginLoading(loadingMessage);
  const headers = { ...(fetchOptions.headers || {}) };
  if (fetchOptions.body && !(fetchOptions.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  try {
    const response = await fetch(path, { credentials: "same-origin", cache: "no-store", ...fetchOptions, headers });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = payload.detail;
      throw new Error(typeof detail === "string" ? detail : detail?.message || `A kérés nem sikerült. (${response.status})`);
    }
    return payload;
  } finally {
    if (shouldShowLoading) endLoading();
  }
}

function previewCourierValue() {
  if (!state.user?.canPreviewCouriers || String(state.user.role || "").toLowerCase() === "coordinator") return "";
  return String(state.workflowPreviewCourierId || "").trim();
}

function isAdminPreviewMode() {
  return Boolean(previewCourierValue());
}

function withPreviewCourier(path) {
  const courier = previewCourierValue();
  if (!courier) return path;
  // Server-generated preview links already carry their document owner.
  // Do not add a second courier parameter from possibly changed UI state.
  const url = new URL(path, window.location.origin);
  if (url.searchParams.has("courier")) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}courier=${encodeURIComponent(courier)}`;
}

function currentSectionRefresh() {
  if (!state.user) return Promise.resolve();
  if (state.section === "home") return loadShifts();
  if (state.section === "tours") return loadCurrentRoute();
  if (state.section === "statistics") return loadStatistics();
  if (state.section === "route-details") {
    if (state.routeDetails) return loadRouteDetails();
    if (state.routeShiftReport) return loadRouteShiftReport();
    if (state.routeStatistics) return loadRouteStatistics();
    return Promise.resolve();
  }
  if (state.section === "workflow") return loadWorkflow();
  if (state.section === "atm") return loadAtmPayments();
  if (state.section === "expense") return loadExpenseRequests();
  if (state.section === "registration-admin") return loadRegistrationRequests();
  if (state.section === "coordinator-live") return loadCoordinatorLiveMap();
  if (state.section === "departure-helper") return loadDepartureHelper();
  if (state.section === "webshop") return loadWebshop();
  if (state.section === "quality-complaints") return loadQualityComplaints();
  if (state.section === "today-workers") return loadTodayWorkers();
  if (state.section === "settlement-dashboard") return loadSettlementDashboard();
  if (state.section === "settlement-import-config") {
    renderSettlementImportConfig();
    return Promise.resolve();
  }
  if (state.section === "coordinator-schedule") {
    if (state.coordinatorScheduleActionActive) return Promise.resolve();
    return state.coordinatorScheduleView === "day"
      ? loadCoordinatorScheduleDay(state.coordinatorScheduleDay, { keepRendered: true })
      : loadCoordinatorSchedule();
  }
  if (state.section === "vehicle") return loadVehicleAssignments({ background: true });
  if (state.section === "vehicle-config") return loadVehicleConfigurations();
  if (state.section === "game") return loadGame();
  return Promise.resolve();
}

function setAdminPreviewStatus(message = "") {
  const target = $("#admin-preview-status");
  if (target) target.textContent = message;
}

function courierOptionLabel(courier) {
  const name = courier?.courierName || "Futár";
  const id = courier?.courierId || "";
  const warehouse = courier?.warehouse || "";
  return `${name}${id ? ` · #${id}` : ""}${warehouse ? ` · ${warehouse}` : ""}`;
}

function renderCourierMasterOptions() {
  const datalist = $("#courier-master-list");
  if (datalist) {
    datalist.innerHTML = (state.couriers || [])
      .map((courier) => `<option value="${escapeHtml(courier.courierId)}" label="${escapeHtml(courierOptionLabel(courier))}"></option>`)
      .join("");
  }
  const vehicleCourier = $("#vehicle-hr-courier");
  if (vehicleCourier) {
    const currentValue = vehicleCourier.value;
    vehicleCourier.innerHTML = `<option value="">Válassz futárt</option>${(state.couriers || [])
      .map((courier) => `<option value="${escapeHtml(courier.courierId)}">${escapeHtml(courierOptionLabel(courier))}</option>`)
      .join("")}`;
    if (currentValue) vehicleCourier.value = currentValue;
  }
  const vehicleConfigCourier = $("#vehicle-config-dedicated-courier");
  if (vehicleConfigCourier) {
    const currentValue = vehicleConfigCourier.value;
    vehicleConfigCourier.innerHTML = `<option value="">Nincs dedikált futár</option>${(state.couriers || [])
      .map((courier) => `<option value="${escapeHtml(courier.courierId)}" data-name="${escapeHtml(courier.courierName || "")}">${escapeHtml(courierOptionLabel(courier))}</option>`)
      .join("")}`;
    if (currentValue) vehicleConfigCourier.value = currentValue;
  }
  const routeDetailsCourier = $("#route-details-courier");
  if (routeDetailsCourier) {
    const currentValue = routeDetailsCourier.value || state.workflowPreviewCourierId;
    routeDetailsCourier.innerHTML = `<option value="">Összes futár (Excel export)</option>${(state.couriers || [])
      .map((courier) => `<option value="${escapeHtml(courier.courierId)}">${escapeHtml(courierOptionLabel(courier))}</option>`)
      .join("")}`;
    if (currentValue) routeDetailsCourier.value = currentValue;
  }
}

async function loadCourierMasterOptions() {
  if (!state.user || (!state.user.canPreviewCouriers && !state.user.canManageVehicles)) return;
  if (state.couriers.length) {
    renderCourierMasterOptions();
    return;
  }
  if (state.couriersLoadingPromise) return state.couriersLoadingPromise;
  state.couriersLoadingPromise = (async () => {
  try {
    const payload = await api("/api/couriers");
    state.couriers = payload.couriers || [];
    renderCourierMasterOptions();
  } catch (error) {
    console.warn("Courier master list failed", error);
  }
  })().finally(() => {
    state.couriersLoadingPromise = null;
  });
  return state.couriersLoadingPromise;
}

function localDate(offset = 0) {
  const value = new Date();
  value.setDate(value.getDate() + offset);
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function localMonth() {
  return localDate().slice(0, 7);
}

function previousLocalMonth() {
  const value = new Date();
  value.setMonth(value.getMonth() - 1, 1);
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  return `${year}-${month}`;
}

function monthStartDate(month) {
  const value = String(month || new Date().toISOString().slice(0, 7)).slice(0, 7);
  return `${value}-01`;
}

function monthEndDate(month) {
  const [year, monthNumber] = String(month || new Date().toISOString().slice(0, 7)).split("-").map((part) => Number(part));
  if (!year || !monthNumber) return localDate();
  const value = new Date(year, monthNumber, 0);
  const yyyy = value.getFullYear();
  const mm = String(value.getMonth() + 1).padStart(2, "0");
  const dd = String(value.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
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
  if (role === "coordinator") {
    // A koordinátor a koordinátori menüket használja, admin előnézetet nem.
    state.user.canPreviewCouriers = false;
    state.workflowPreviewCourierId = "";
  }
  const canCoordinate = ["admin", "coordinator"].includes(role);
  const canViewAdminSettlement = Boolean(state.user.canViewSettlementDashboard)
    || ["admin", "superadmin"].includes(role);
  $("#nav-coordinator").classList.toggle("hidden", !canCoordinate);
  $("#nav-coordinator-live").classList.toggle("hidden", !canCoordinate);
  $("#nav-departure-helper").classList.toggle("hidden", !canCoordinate);
  $("#nav-quality-complaints").classList.toggle("hidden", !["admin", "superadmin"].includes(role));
  $("#nav-today-workers").classList.toggle("hidden", !canCoordinate);
  $("#nav-coordinator-schedule").classList.toggle("hidden", !canCoordinate);
  ["#nav-home", "#nav-settlement", "#nav-statistics", "#nav-phonebook", "#nav-atm", "#nav-salary-advance", "#nav-documents", "#nav-profile", "#nav-device", "#nav-vehicle", "#nav-tours", "#nav-game"]
    .forEach((selector) => $(selector)?.classList.remove("hidden"));
  $("#nav-registration-admin").classList.toggle("hidden", !state.user.canApproveRegistrations);
  $("#nav-route-details").classList.toggle("hidden", !state.user.canPreviewCouriers);
  $("#nav-settlement-dashboard").classList.toggle("hidden", !canViewAdminSettlement);
  $("#nav-settlement-import-config").classList.toggle("hidden", !canViewAdminSettlement);
  $("#nav-financial-statistics")?.classList.toggle("hidden", !canViewAdminSettlement);
  $("#nav-vehicle-config").classList.toggle("hidden", !state.user.canManageVehicles);
  const coordinatorOnly = role === "coordinator";
  const hrOnly = role === "hr";
  if (coordinatorOnly) {
    // A koordinátori jogosultság hozzáadódik a futár saját menüihez.
    $("#nav-vehicle-config")?.classList.toggle("hidden", !state.user.canManageVehicles);
  }
  if (hrOnly) {
    ["#nav-home", "#nav-settlement", "#nav-statistics", "#nav-phonebook", "#nav-atm", "#nav-salary-advance", "#nav-documents", "#nav-device", "#nav-tours", "#nav-route-details", "#nav-game", "#nav-registration-admin", "#nav-settlement-dashboard", "#nav-settlement-import-config"]
      .forEach((selector) => $(selector)?.classList.add("hidden"));
    ["#nav-profile", "#nav-vehicle"].forEach((selector) => $(selector)?.classList.remove("hidden"));
    $("#nav-vehicle-config")?.classList.toggle("hidden", !state.user.canManageVehicles);
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
  const scheduleWarehouseWrap = $("#coordinator-schedule-warehouse-wrap");
  if (scheduleWarehouseWrap) scheduleWarehouseWrap.classList.toggle("hidden", role !== "admin");
  loadCourierMasterOptions();
}

function showSection(section) {
  if (section === "quality-complaints" && !["admin", "superadmin"].includes(String(state.user?.role || "").toLowerCase())) return;
  state.section = section;
  $("#webshop-content").classList.toggle("hidden", section !== "webshop");
  $("#nav-webshop").classList.toggle("active", section === "webshop");
  $("#quality-complaints-content").classList.toggle("hidden", section !== "quality-complaints");
  $("#nav-quality-complaints").classList.toggle("active", section === "quality-complaints");
  $("#home-content").classList.toggle("hidden", section !== "home");
  $("#settlement-content").classList.toggle("hidden", section !== "settlement");
  $("#statistics-content").classList.toggle("hidden", section !== "statistics");
  $("#admin-statistics-content")?.classList.toggle("hidden", section !== "admin-statistics");
  $("#financial-statistics-content")?.classList.toggle("hidden", section !== "financial-statistics");
  $("#route-details-content").classList.toggle("hidden", section !== "route-details");
  $("#phonebook-content").classList.toggle("hidden", section !== "phonebook");
  $("#atm-content").classList.toggle("hidden", section !== "atm");
  $("#salary-advance-content").classList.toggle("hidden", section !== "salary-advance");
  $("#expense-content").classList.toggle("hidden", section !== "expense");
  $("#documents-content").classList.toggle("hidden", section !== "documents");
  $("#profile-content").classList.toggle("hidden", section !== "profile");
  $("#device-content").classList.toggle("hidden", section !== "device");
  $("#vehicle-content").classList.toggle("hidden", section !== "vehicle");
  $("#vehicle-config-content").classList.toggle("hidden", section !== "vehicle-config");
  $("#tours-content").classList.toggle("hidden", section !== "tours");
  $("#game-content").classList.toggle("hidden", section !== "game");
  $("#coordinator-content").classList.toggle("hidden", section !== "coordinator");
  $("#coordinator-live-content").classList.toggle("hidden", section !== "coordinator-live");
  $("#departure-helper-content").classList.toggle("hidden", section !== "departure-helper");
  $("#today-workers-content").classList.toggle("hidden", section !== "today-workers");
  $("#coordinator-schedule-content").classList.toggle("hidden", section !== "coordinator-schedule");
  $("#registration-admin-content").classList.toggle("hidden", section !== "registration-admin");
  $("#settlement-dashboard-content").classList.toggle("hidden", section !== "settlement-dashboard");
  $("#settlement-import-config-content").classList.toggle("hidden", section !== "settlement-import-config");

  $("#nav-home").classList.toggle("active", section === "home");
  $("#nav-settlement").classList.toggle("active", section === "settlement");
  $("#nav-statistics").classList.toggle("active", section === "statistics");
  $("#nav-statistics").classList.toggle("active", section === "admin-statistics");
  $("#nav-financial-statistics")?.classList.toggle("active", section === "financial-statistics");
  $("#nav-route-details").classList.toggle("active", section === "route-details");
  $("#nav-phonebook").classList.toggle("active", section === "phonebook");
  $("#nav-atm").classList.toggle("active", section === "atm");
  $("#nav-salary-advance").classList.toggle("active", section === "salary-advance");
  $("#nav-expense").classList.toggle("active", section === "expense");
  $("#nav-documents").classList.toggle("active", section === "documents");
  $("#nav-profile").classList.toggle("active", section === "profile");
  $("#nav-device").classList.toggle("active", section === "device");
  $("#nav-vehicle").classList.toggle("active", section === "vehicle");
  $("#nav-vehicle-config").classList.toggle("active", section === "vehicle-config");
  $("#nav-tours").classList.toggle("active", section === "tours");
  $("#nav-game").classList.toggle("active", section === "game");
  $("#nav-coordinator").classList.toggle("active", section === "coordinator");
  $("#nav-coordinator-live").classList.toggle("active", section === "coordinator-live");
  $("#nav-departure-helper").classList.toggle("active", section === "departure-helper");
  $("#nav-today-workers").classList.toggle("active", section === "today-workers");
  $("#nav-coordinator-schedule").classList.toggle("active", section === "coordinator-schedule");
  $("#nav-registration-admin").classList.toggle("active", section === "registration-admin");
  $("#nav-settlement-dashboard").classList.toggle("active", section === "settlement-dashboard");
  $("#nav-settlement-import-config").classList.toggle("active", section === "settlement-import-config");

  if (section === "settlement" && !state.workflow) loadWorkflow();
  if (section === "settlement-dashboard") loadSettlementDashboard();
  if (section === "settlement-import-config") renderSettlementImportConfig();
  if (section === "statistics" && !state.statistics) loadStatistics();
  if (section === "admin-statistics" && !state.adminStatistics) loadAdminStatistics();
  if (section === "financial-statistics" && !state.financialStatistics) loadFinancialStatistics();
  if (section === "route-details") {
    loadCourierMasterOptions().then(() => {
      if (!$("#route-details-month")?.value) $("#route-details-month").value = state.statisticsMonth;
      if (!$("#route-stats-start")?.value) $("#route-stats-start").value = monthStartDate($("#route-details-month")?.value || state.statisticsMonth);
      if (!$("#route-stats-end")?.value) $("#route-stats-end").value = monthEndDate($("#route-details-month")?.value || state.statisticsMonth);
      if (state.workflowPreviewCourierId && $("#route-details-courier")) $("#route-details-courier").value = state.workflowPreviewCourierId;
      renderRouteReportBuilder();
      if (!state.routeDetails && !state.routeDetailsDialogShownOnce) {
        state.routeDetailsDialogShownOnce = true;
        openRouteReportDialog();
      }
    });
    renderRouteShiftReport();
    renderRouteStatistics();
    renderRouteDetails();
  }
  if (section === "phonebook") renderPhonebook();
  if (section === "atm") loadAtmPayments();
  if (section === "salary-advance") {
    const startInput = $("#salary-advance-start-date");
    if (startInput && !startInput.value) startInput.value = localMonth();
    loadSalaryAdvanceRequests();
  }
  if (section === "expense") loadExpenseRequests();
  if (section === "documents") loadDocuments();
  if (section === "profile") {
    loadBillingProfile();
    refreshNotificationToggle();
  }
  if (section === "device") loadDeviceReports();
  if (section === "vehicle") loadVehicleSection();
  if (section === "vehicle-config") loadVehicleConfigurations();
  if (section === "tours") {
    loadCurrentRoute();
  }
  if (section === "game") loadGame();
  if (section === "coordinator") loadCoordinatorAdjustments();
  if (section === "coordinator-live") loadCoordinatorLiveMap();
  if (section === "departure-helper") loadDepartureHelper();
  if (section === "webshop") loadWebshop();
  if (section === "quality-complaints") loadQualityComplaints();
  if (section === "today-workers") loadTodayWorkers();
  if (section === "coordinator-schedule") {
    if (state.coordinatorScheduleView === "day") {
      loadCoordinatorScheduleDay(state.coordinatorScheduleDay, { keepRendered: true });
    } else {
      loadCoordinatorSchedule();
    }
  }
  if (section === "registration-admin") loadRegistrationRequests();

  if (section !== "coordinator-schedule") {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
}

function formatCount(value) {
  return new Intl.NumberFormat("hu-HU", { maximumFractionDigits: 0 }).format(Number(value || 0));
}

function formatAverage(value) {
  return new Intl.NumberFormat("hu-HU", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(Number(value || 0));
}

function formatPercent(value) {
  return `${new Intl.NumberFormat("hu-HU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value || 0))}%`;
}

function formatHuf(value) {
  return `${formatCount(value)} Ft`;
}

function formatMonthLabel(month) {
  const [year, monthNumber] = String(month || "").split("-").map((part) => Number(part));
  if (!year || !monthNumber) return String(month || "");
  return new Date(year, monthNumber - 1, 1).toLocaleDateString("hu-HU", {
    year: "numeric",
    month: "long",
  });
}

function formatDateTime(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString("hu-HU");
}

function adminInvoiceUploadMonths() {
  const current = new Date();
  current.setDate(1);
  const previous = new Date(current);
  previous.setMonth(previous.getMonth() - 1);
  const monthKey = (value) => `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}`;
  return [monthKey(current), monthKey(previous)];
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
          ${item.receiptUrl ? `
            <a class="atm-receipt-preview" href="${escapeHtml(withPreviewCourier(item.receiptUrl))}" target="_blank" rel="noopener">
              <span>Bizonylat megnyitása</span>
            </a>
          ` : ""}
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
  const isAdminList = Boolean(state.user?.canPreviewCouriers);
  if (!rows.length) {
    target.innerHTML = `
      <div class="process-title">
        <span class="step-code">Ft</span>
        <div><h3>Előleg kérelmek</h3><p>${isAdminList ? "Nincs rögzített előleg kérelem." : "Még nincs rögzített előleg igényed."}</p></div>
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
            ${isAdminList ? `<div class="stat-row"><span>Futár</span><strong>${escapeHtml(item.courierName || "-")} #${escapeHtml(item.courierId || "-")}</strong></div>` : ""}
            <div class="stat-row"><span>Kezdés</span><strong>${escapeHtml(item.startDate || "-")}</strong></div>
            <div class="stat-row"><span>Havi bontás</span><strong>${formatCount(item.installmentMonths)} hó</strong></div>
            <div class="stat-row"><span>Havi levonás</span><strong>${formatHuf(item.monthlyAmountHuf)}</strong></div>
            ${item.processId ? `<div class="stat-row"><span>Folyamat</span><strong>${escapeHtml(item.processId)}</strong></div>` : ""}
          </div>
          ${state.user?.canPreviewCouriers && item.status === "requested"
            ? `<button class="primary full-width salary-advance-approve" type="button" data-id="${escapeHtml(item.id)}">Előleg jóváhagyása admin módban</button>`
            : ""}
        </article>
      `).join("")}
    </div>
  `;
}

async function loadSalaryAdvanceRequests() {
  const message = $("#salary-advance-message");
  if (message) message.textContent = "Előleg kérelmek betöltése...";
  try {
    const url = state.user?.canPreviewCouriers ? "/api/salary-advance/requests?scope=all" : withPreviewCourier("/api/salary-advance/requests");
    const payload = await api(url);
    state.salaryAdvanceRequests = payload.requests || [];
    renderSalaryAdvanceRequests();
    if (message) message.textContent = "";
  } catch (error) {
    if (message) message.textContent = error.message;
  }
}

async function approveSalaryAdvanceRequest(requestId) {
  if (!requestId || !state.user?.canPreviewCouriers) return;
  const message = $("#salary-advance-message");
  if (message) message.textContent = "Előleg jóváhagyása...";
  try {
    const payload = await api(`/api/admin/salary-advance/requests/${encodeURIComponent(requestId)}/approve`, {
      method: "POST",
      body: JSON.stringify({ month: state.workflowMonth }),
    });
    state.salaryAdvanceRequests = payload.requests || [];
    state.workflowMonthsLoadedFor = "";
    state.workflowMonths = [];
    renderSalaryAdvanceRequests();
    if (message) message.textContent = "Előleg jóváhagyva, a kifizetési folyamat létrejött.";
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

function dateTimeMs(value) {
  if (!value) return NaN;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : NaN;
}

function routeQueueStartedAt(row = {}, story = row.routeStory || {}) {
  const assignedAt = story.assignedAt || row.routeAssignedAt;
  const assignedMs = dateTimeMs(assignedAt);
  const candidates = [story.queueStartedAt, row.queueStartedAt, row.actualStartAt];
  for (const candidate of candidates) {
    const candidateMs = dateTimeMs(candidate);
    if (!Number.isFinite(candidateMs)) continue;
    if (Number.isFinite(assignedMs) && candidateMs > assignedMs) continue;
    return candidate;
  }
  const shiftStart = story.shiftStart || row.plannedStartAt || row.shiftStartAt;
  const shiftStartMs = dateTimeMs(shiftStart);
  if (Number.isFinite(shiftStartMs) && Number.isFinite(assignedMs) && shiftStartMs <= assignedMs) {
    return shiftStart;
  }
  return "";
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

function dailyRouteStatusOk(row = {}) {
  const story = row.routeStory || {};
  return uncleanedLateStopCount(row) <= 0 && routeShiftLateMinutes(row, story) <= 0;
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

function localTodayIsoDate() {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function pastQualityDetails(rows = []) {
  const today = localTodayIsoDate();
  return rows.filter((row) => {
    const date = String(row?.date || "").slice(0, 10);
    return date && date < today;
  });
}

function qualityDetailCount(row = {}) {
  const match = String(row.note || "").match(/^(\d+)\s/);
  return match ? Number(match[1]) : 1;
}

function visibleQualityCount(summary = {}, key) {
  const details = summary.details || {};
  const rows = Array.isArray(details[key]) ? details[key] : [];
  if (!rows.length) return Number(summary[`${key}Count`] || 0);
  const visibleRows = key === "noShow" ? pastQualityDetails(rows) : rows;
  return visibleRows.reduce((sum, row) => sum + qualityDetailCount(row), 0);
}

function qualityProblemDates(payload = {}) {
  const details = payload.qualitySummary?.details || {};
  const rows = [
    ...(details.lateShift || []),
    ...(details.uncleanedTimeWindowLate || []),
    ...pastQualityDetails(details.noShow || []),
  ];
  return new Set(rows.map((row) => String(row?.date || "").slice(0, 10)).filter(Boolean));
}

function renderQualitySummaryChart(payload = {}) {
  const sourceSummary = payload.qualitySummary || qualitySummaryFromDailyHistory(payload.dailyHistory || []);
  const activeTopic = state.statisticsQualityTopic || "";
  const sourceDetails = sourceSummary.details || {};
  const visibleNoShowDetails = pastQualityDetails(sourceDetails.noShow || []);
  const sourceNoShowDetails = sourceDetails.noShow || [];
  const visibleNoShowCount = sourceNoShowDetails.length
    ? visibleNoShowDetails.reduce((sum, row) => sum + qualityDetailCount(row), 0)
    : Number(sourceSummary.noShowCount || 0);
  const hiddenFutureNoShows = Math.max(0, Number(sourceSummary.noShowCount || 0) - visibleNoShowCount);
  const summary = {
    ...sourceSummary,
    noShowCount: visibleNoShowCount,
    totalProblems: Math.max(0, Number(sourceSummary.totalProblems || 0) - hiddenFutureNoShows),
  };
  summary.ok = summary.totalProblems <= 0;
  const details = { ...sourceDetails, noShow: visibleNoShowDetails };
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
      key: "cleanedTimeWindowLate",
      label: "Mentesített címkésés",
      value: Number(summary.cleanedTimeWindowLateCount || 0),
      note: `${formatCount(summary.cleanedTimeWindowLateMinutes || 0)} perc összesen`,
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
          <p>${statusOk ? "Nincs no-show, műszak késés vagy nem mentesített időablak-késés." : "A fő minőségi jelzések havi összesítése."}</p>
        </div>
      </div>
      <div class="quality-bars">
        ${items.map((item) => {
          const width = Math.max(4, Math.round((item.value / maxValue) * 100));
          return `
            <div class="quality-item">
              <button class="quality-bar-row ${activeTopic === item.key ? "active" : ""}" type="button" data-quality-topic="${escapeHtml(item.key)}">
                <div>
                  <strong>${escapeHtml(item.label)}</strong>
                  <small>${escapeHtml(item.note)}</small>
                </div>
                <div class="quality-bar-track"><span style="width: ${width}%"></span></div>
                <b>${formatCount(item.value)}</b>
              </button>
              ${activeTopic === item.key ? renderQualitySummaryDetails(item.key, details) : ""}
            </div>
          `;
        }).join("")}
      </div>
      <div id="courier-quality-complaints" aria-live="polite">${renderCourierQualityComplaints(payload)}</div>
    </section>
  `;
}

function renderCourierQualityComplaints(payload = {}) {
  const header = '<div class="courier-complaint-heading"><div><h4>Reklamációim</h4><p>A kiválasztott hónapban érintett ügyek állapota</p></div><button class="text-button" type="button" data-courier-complaints-refresh>Állapot frissítése</button></div>';
  if (payload.qualityComplaintsError) return `<section class="courier-complaints">${header}<p class="notice error">A reklamációk állapotát most nem sikerült lekérni. Próbáld újra az állapotfrissítést.</p></section>`;
  if (!payload.qualityComplaints) return `<section class="courier-complaints">${header}<p class="muted">Reklamációk állapotának betöltése…</p></section>`;
  if (!payload.qualityComplaints.length) return `<section class="courier-complaints">${header}<p class="muted">Erre a hónapra még nincs beküldött reklamációd.</p></section>`;
  const labels = { lateShift: "Műszakkésés", noShow: "No-show", uncleanedTimeWindowLate: "Nem mentesített címkésés", cleanedTimeWindowLate: "Mentesített címkésés" };
  const explanations = { open: "Megkaptuk a reklamációdat, feldolgozásra vár.", forwarded: "A reklamációdat továbbítottuk a Kifli felé. Válaszra várunk.", closed: "Az ügyet lezártuk. Az alábbi válaszban találod az eredményt." };
  return `<section class="courier-complaints">${header}<div class="courier-complaint-list">${payload.qualityComplaints.map(item => {
    const status = ["open", "forwarded", "closed"].includes(item.status) ? item.status : "unknown";
    return `<article class="courier-complaint-card">
      <div class="courier-complaint-top"><h4>${escapeHtml(labels[item.topic] || "Reklamáció")}</h4><span class="courier-complaint-badge ${status}">${escapeHtml(qualityComplaintStatus(item.status))}</span></div>
      <p class="courier-complaint-description">${escapeHtml(explanations[status] || "Az ügy állapota frissítésre vár.")}</p>
      <div class="courier-complaint-dates"><span>Beküldve <strong>${escapeHtml(shortDateTime(item.created_at))}</strong></span>${item.forwarded_at ? `<span>Továbbítva <strong>${escapeHtml(shortDateTime(item.forwarded_at))}</strong></span>` : ""}${item.closed_at ? `<span>Lezárva <strong>${escapeHtml(shortDateTime(item.closed_at))}</strong></span>` : ""}</div>
      ${item.admin_response ? `<div class="courier-complaint-response"><strong>Válasz a reklamációdra</strong>${item.responded_at ? `<small>${escapeHtml(shortDateTime(item.responded_at))}</small>` : ""}<p class="complaint-text">${escapeHtml(item.admin_response)}</p></div>` : ""}
      <details><summary>Beküldött reklamáció és érintett műszakok</summary><p class="complaint-text">${escapeHtml(item.message)}</p>
      ${(item.affected_items || []).map(row => `<p class="courier-complaint-item">${escapeHtml(row.date)} · ${escapeHtml(row.label)}</p>`).join("")}
      ${(item.attachments || []).map((photo, index) => `<a class="courier-complaint-photo" href="/api/quality/complaints/${encodeURIComponent(item.id)}/photos/${encodeURIComponent(photo.sha256)}" target="_blank" rel="noopener">Csatolt kép ${index + 1}</a>`).join("")}
      ${(item.history || []).filter(event => event.message).map(event => `<p class="complaint-text">${escapeHtml(shortDateTime(event.at))} · ${escapeHtml(event.message)}</p>`).join("")}</details>
    </article>`;
  }).join("")}</div>${payload.qualityComplaintsHasMore ? '<p class="muted">A legutóbbi 200 reklamációt mutatjuk.</p>' : ""}</section>`;
}

async function refreshCourierQualityComplaints() {
  const payload = state.statistics;
  if (!payload) return;
  const sequence = (state.courierComplaintRequest || 0) + 1;
  state.courierComplaintRequest = sequence;
  const params = new URLSearchParams({ month: payload.month || state.statisticsMonth });
  if (state.user?.canPreviewCouriers && state.workflowPreviewCourierId) params.set("courier", state.workflowPreviewCourierId);
  try {
    const result = await api(`/api/quality/complaints/mine?${params}`, { silentLoading: true });
    if (state.statistics !== payload || state.courierComplaintRequest !== sequence) return;
    payload.qualityComplaints = result.items || [];
    payload.qualityComplaintsHasMore = result.hasMore;
    payload.qualityComplaintsError = false;
  } catch (_) {
    if (state.statistics !== payload || state.courierComplaintRequest !== sequence) return;
    payload.qualityComplaintsError = true;
  }
  const target = $("#courier-quality-complaints");
  if (target) target.innerHTML = renderCourierQualityComplaints(payload);
}

function qualityShiftTimes(row, topic) {
  if (topic !== "lateShift") return "";
  const clock = (value) => {
    if (!value) return "Nincs adat";
    if (/^\d{2}:\d{2}(?::\d{2})?$/.test(value)) return value.slice(0, 5);
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "Nincs adat" : new Intl.DateTimeFormat("hu-HU", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Budapest" }).format(date);
  };
  return `<small>Giriton-bejelentkezés: ${escapeHtml(clock(row.giritonLoginAt))}</small><small>Sorba állás: ${escapeHtml(clock(row.queueStartedAt))}</small>`;
}

function renderQualitySummaryDetails(topic, details = {}) {
  if (!topic) return "";
  const labels = {
    lateShift: "Vizsgálandó műszak késések",
    uncleanedTimeWindowLate: "Vizsgálandó időkapun túli késések",
    cleanedTimeWindowLate: "Mentesített időkapun túli késések",
    noShow: "Vizsgálandó no-show műszakok",
  };
  const rows = Array.isArray(details[topic]) ? details[topic] : [];
  return `
    <div class="quality-detail-list">
      <h4>${escapeHtml(labels[topic] || "Vizsgálandó tételek")}</h4>
      ${rows.length ? rows.map((row) => `
        <div class="quality-detail-row" role="button" tabindex="0" data-quality-date="${escapeHtml(row.date || "")}" data-quality-topic-row="${escapeHtml(topic)}">
          <strong>${escapeHtml(row.date || "-")}</strong>
          <span>${escapeHtml(row.label || "-")}</span>
          <small>${escapeHtml(row.note || "")}${row.routeId ? ` · Route ${escapeHtml(row.routeId)}` : ""}</small>
          ${qualityShiftTimes(row, topic)}
          <button class="secondary quality-reclamation-trigger" type="button" data-quality-reclamation-topic="${escapeHtml(topic)}">Reklamáció</button>
        </div>
      `).join("") : `<p>Nincs külön vizsgálandó sor ehhez a jelzéshez.</p>`}
    </div>
  `;
}

function qualityComplaintStatus(value) {
  return ({ open: "Nyitott", forwarded: "Továbbított", closed: "Lezárt" })[value] || value;
}

async function loadQualityComplaints() {
  if (!["admin", "superadmin"].includes(String(state.user?.role || "").toLowerCase())) return;
  const target = $("#quality-complaints-list");
  const status = $("#quality-complaints-status");
  const request = (state.qualityComplaintRequest || 0) + 1;
  state.qualityComplaintRequest = request;
  status.textContent = "Betöltés…";
  try {
    const payload = await api(`/api/quality/complaints?status=${encodeURIComponent($("#quality-complaints-filter").value)}&offset=${state.qualityComplaintOffset || 0}`);
    if (state.qualityComplaintRequest !== request) return;
    target.innerHTML = payload.items.length ? payload.items.map((item) => {
      const topics = { lateShift: "Műszakkésés", noShow: "No-show", uncleanedTimeWindowLate: "Nem mentesített címkésés", cleanedTimeWindowLate: "Mentesített címkésés" };
      return `<article class="shift-card" data-complaint-id="${escapeHtml(item.id)}">
        <div class="shift-top"><div><h3>${escapeHtml(item.courier_name)} · #${escapeHtml(item.courier_id)}</h3><p>${escapeHtml(topics[item.topic] || item.topic)} · ${escapeHtml(shortDateTime(item.created_at))}</p></div><span class="source">${escapeHtml(qualityComplaintStatus(item.status))}</span></div>
        <p class="complaint-text">${escapeHtml(item.message)}</p>
        ${(item.attachments || []).length ? `<div class="source-row">${item.attachments.map((photo, index) => `<a class="secondary" href="/api/quality/complaints/${encodeURIComponent(item.id)}/photos/${encodeURIComponent(photo.sha256)}" target="_blank" rel="noopener">Kép ${index + 1}: ${escapeHtml(photo.file_name)}</a>`).join("")}</div>` : ""}
        <details><summary>Érintett tételek és előzmények</summary>
          ${(item.affected_items || []).map(row => `<div class="stat-row"><span>${escapeHtml(row.date)} · ${escapeHtml(row.label)}</span><strong>${escapeHtml(row.note)}</strong></div>`).join("")}
          ${(item.history || []).map(event => `<p class="complaint-text">${escapeHtml(shortDateTime(event.at))} · ${escapeHtml(event.actor)} · ${escapeHtml(qualityComplaintStatus(event.status))}<br>${escapeHtml(event.message || event.reference)}</p>`).join("")}
        </details>
        ${item.admin_response ? `<div class="notice complaint-text"><strong>Válasz:</strong> ${escapeHtml(item.admin_response)}</div>` : ""}
        ${payload.canManage && item.status !== "closed" ? `<label>Szöveges válasz<textarea data-complaint-response maxlength="5000" placeholder="Válasz a futárnak…"></textarea></label>
          <div class="dialog-actions"><button type="button" class="secondary" data-complaint-action="reply">Válasz mentése</button><button type="button" data-complaint-action="close">Lezárás válasszal</button></div>
          ${item.status === "open" ? `<details><summary>Kifli-továbbítás rögzítése</summary><p class="muted">Csak a tényleges továbbítás után. Ez a gomb nem küldi el a reklamációt.</p><label>Kifli ügyazonosító / feltöltési hivatkozás<input data-complaint-reference maxlength="500" /></label><button type="button" class="secondary" data-complaint-action="forward">Továbbítottként rögzítés</button></details>` : ""}` : ""}
        <p data-complaint-result role="status" aria-live="polite"></p>
      </article>`;
    }).join("") : '<div class="empty-card">Nincs ilyen státuszú reklamáció.</div>';
    $("#quality-complaints-prev").disabled = !(state.qualityComplaintOffset > 0);
    $("#quality-complaints-next").disabled = !payload.hasMore;
    status.textContent = `${payload.items.length} reklamáció ezen az oldalon`;
    target.querySelectorAll("[data-complaint-action]").forEach(button => button.addEventListener("click", async () => {
      const card = button.closest("[data-complaint-id]");
      const result = card.querySelector("[data-complaint-result]");
      const action = button.dataset.complaintAction;
      const message = card.querySelector("[data-complaint-response]")?.value.trim() || "";
      const reference = card.querySelector("[data-complaint-reference]")?.value.trim() || "";
      if (action !== "forward" && message.length < 5) { result.textContent = "Legalább 5 karakteres válasz szükséges."; return; }
      if (action === "forward" && reference.length < 3) { result.textContent = "Add meg a továbbítás hivatkozását."; return; }
      const buttons = card.querySelectorAll("button");
      buttons.forEach(b => b.disabled = true);
      result.textContent = "Mentés…";
      try {
        const response = await api(`/api/quality/complaints/${encodeURIComponent(card.dataset.complaintId)}/actions`, { method: "POST", body: JSON.stringify({ action, message, reference }) });
        if (!response.ok) throw new Error("Nem igazolható a mentés.");
        await loadQualityComplaints();
      } catch (error) {
        result.textContent = error.message;
        buttons.forEach(b => b.disabled = false);
      }
    }));
  } catch (error) {
    if (state.qualityComplaintRequest === request) status.textContent = error.message;
  }
}

function ensureQualityReclamationDialog() {
  let dialog = $("#quality-reclamation-dialog");
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.id = "quality-reclamation-dialog";
  dialog.className = "worker-shift-dialog quality-reclamation-dialog";
  dialog.innerHTML = `
    <form method="dialog" class="worker-shift-dialog-card">
      <div class="worker-shift-dialog-head">
        <div><span>MINŐSÉGI ELLENŐRZÉS</span><strong data-quality-reclamation-title>Reklamáció</strong><small data-quality-reclamation-subtitle></small></div>
        <button type="button" class="icon-button" data-quality-reclamation-close aria-label="Bezárás">×</button>
      </div>
      <div data-quality-reclamation-body></div>
      <label>Reklamáció indoka<textarea data-quality-reclamation-note placeholder="Ide írható a reklamáció rövid indoklása..."></textarea></label>
      <label>Képek csatolása (nem kötelező)<input data-quality-reclamation-photos type="file" accept="image/jpeg,image/png,image/webp" multiple /></label>
      <small>Legfeljebb 5 kép, képenként maximum 8 MB. JPG, PNG vagy WebP.</small>
      <p data-quality-reclamation-status role="status" aria-live="polite"></p>
      <div class="dialog-actions"><button type="button" class="secondary" data-quality-reclamation-close>Bezárás</button><button type="button" data-quality-reclamation-submit>Reklamáció beküldése</button></div>
    </form>
  `;
  document.body.appendChild(dialog);
  dialog.querySelector("[data-quality-reclamation-submit]").addEventListener("click", async () => {
    const button = dialog.querySelector("[data-quality-reclamation-submit]");
    const status = dialog.querySelector("[data-quality-reclamation-status]");
    const note = dialog.querySelector("[data-quality-reclamation-note]");
    const photoInput = dialog.querySelector("[data-quality-reclamation-photos]");
    const context = dialog.complaintContext;
    if (!context || context.saved || button.disabled) return;
    const message = note.value.trim();
    if (message.length < 5) { status.textContent = "Legalább 5 karakteres indoklást adj meg."; return; }
    const photos = context.photos || Array.from(photoInput.files || []);
    if (photos.length > 5 || photos.some(file => file.size > 8 * 1024 * 1024)) {
      status.textContent = "Legfeljebb 5 képet válassz, egyenként maximum 8 MB méretben."; return;
    }
    button.disabled = true;
    note.disabled = true;
    photoInput.disabled = true;
    status.textContent = "Mentés folyamatban…";
    try {
      if (!context.complaintId) {
        const result = await api("/api/quality/complaints", { method: "POST", body: JSON.stringify({
          request_id: context.requestId, topic: context.topic, month: context.month, items: context.rows, message,
        }) });
        if (!result.ok || !result.id) throw new Error("A mentés nem igazolható.");
        context.complaintId = result.id;
        context.photos = photos;
        context.uploaded = 0;
      }
      for (let index = context.uploaded; index < context.photos.length; index++) {
        status.textContent = `Reklamáció elmentve. Képfeltöltés: ${index + 1}/${context.photos.length}…`;
        const form = new FormData();
        form.append("photo", context.photos[index]);
        const uploaded = await api(`/api/quality/complaints/${encodeURIComponent(context.complaintId)}/photos`, { method: "POST", body: form });
        if (!uploaded.ok) throw new Error("A kép feltöltése nem igazolható.");
        context.uploaded = index + 1;
      }
      context.saved = true;
      status.textContent = `A reklamációt és ${context.uploaded} képet elmentettük. Azonosító: ${context.complaintId}`;
      refreshCourierQualityComplaints();
    } catch (error) {
      status.textContent = context.complaintId
        ? `A reklamáció elmentve, de a képfeltöltés nem fejeződött be: ${error.message} A beküldés gombbal folytathatod.`
        : `Nem sikerült menteni: ${error.message} Az indoklás és a képek megmaradtak, újrapróbálhatod.`;
      if (context.complaintId) refreshCourierQualityComplaints();
      if (dialog.complaintContext === context) {
        button.disabled = false;
        note.disabled = Boolean(context.complaintId);
        photoInput.disabled = Boolean(context.complaintId);
      }
    }
  });
  dialog.querySelectorAll("[data-quality-reclamation-close]").forEach((button) => button.addEventListener("click", () => dialog.close()));
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  return dialog;
}

function openQualityReclamation(topic) {
  const dialog = ensureQualityReclamationDialog();
  if (dialog.querySelector("[data-quality-reclamation-note]").disabled && !dialog.complaintContext?.saved) {
    dialog.showModal();
    return;
  }
  const summary = state.statistics?.qualitySummary || {};
  const details = summary.details || {};
  const rows = topic === "noShow" ? pastQualityDetails(details.noShow || []) : (details[topic] || []);
  const labels = {
    lateShift: "Műszakkésés reklamáció",
    uncleanedTimeWindowLate: "Nem mentesített címkésés reklamáció",
    cleanedTimeWindowLate: "Mentesített címkésés reklamáció",
    noShow: "No-show reklamáció",
  };
  dialog.querySelector("[data-quality-reclamation-title]").textContent = labels[topic] || "Reklamáció";
  dialog.querySelector("[data-quality-reclamation-subtitle]").textContent = `${rows.length} érintett tétel`;
  dialog.querySelector("[data-quality-reclamation-body]").innerHTML = rows.length
    ? `<div class="quality-reclamation-list">${rows.map((row) => `<div class="stat-row"><span>${escapeHtml(row.date || "-")} · ${escapeHtml(row.label || "Műszak")}${qualityShiftTimes(row, topic)}</span><strong>${escapeHtml(row.note || "")}</strong></div>`).join("")}</div>`
    : `<p class="updated-at">Ehhez a jelzéshez nincs részletes adat.</p>`;
  dialog.querySelector("[data-quality-reclamation-note]").value = "";
  dialog.querySelector("[data-quality-reclamation-note]").disabled = false;
  dialog.querySelector("[data-quality-reclamation-photos]").value = "";
  dialog.querySelector("[data-quality-reclamation-photos]").disabled = false;
  const preview = Boolean(previewCourierValue() || state.workflowPreviewCourierId);
  dialog.complaintContext = { topic, month: state.statistics?.month || state.statisticsMonth,
    rows, requestId: crypto.randomUUID(), saved: false };
  dialog.querySelector("[data-quality-reclamation-submit]").disabled = preview || !rows.length;
  dialog.querySelector("[data-quality-reclamation-status]").textContent = preview
    ? "Admin előnézetből nem küldhető be reklamáció a futár nevében." : "";
  dialog.showModal();
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
  const shiftStart = story.shiftStart || row.plannedStartAt;
  const queuedAt = routeQueueStartedAt(row, story);
  const computedDelay = minutesBetween(shiftStart, queuedAt);
  if (queuedAt) return computedDelay > 0 ? computedDelay : 0;
  const explicitDelay = Number(row.plannedStartDelayMinutes || 0);
  return explicitDelay > 0 ? explicitDelay : 0;
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
  const queueStartedAt = routeQueueStartedAt(route, story);
  return `
    <section class="route-timeline">
      <div class="route-timeline-head">
        <strong>${escapeHtml(routeStoryShiftLabel(story))}</strong>
      </div>
      <div class="route-timeline-grid">
        ${routeStoryTime("Elérhető volt", story.availableForShiftSince || story.availableAt || story.courierRegisteredAt)}
        ${routeStoryTime("Sorba állt", queueStartedAt)}
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
  const shiftCheckinAt = routeQueueStartedAt(row, story);
  const availableAt = story.availableForShiftSince || story.availableAt || story.courierRegisteredAt || row.shiftAvailableAt;
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
  const queueStartedAt = routeQueueStartedAt(row, story);
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
        <div><strong>${routeOk ? "Időkapun belül" : "Időkapun kívül"}</strong><small>Időablak szerinti ellenőrzés</small></div>
      </div>
      <div class="route-quality-head">
        <div><strong>${shiftOk ? "Műszak időben" : "Késett a műszakból"}</strong><small>${shiftOk ? "Sorba állás rendben" : `${formatCount(shiftLateMinutes)} perc késés a műszakhoz képest`}</small></div>
      </div>
      ${story.shiftName ? `<p class="updated-at">${escapeHtml(story.shiftName)}</p>` : ""}
      ${routeStoryTime("Műszak kezdete", story.shiftStart || row.plannedStartAt)}
      ${routeStoryTime("Giriton-bejelentkezés", story.giritonLoginAt || row.giritonLoginAt)}
      <div class="stat-row"><span>Túratípus</span><strong>${escapeHtml(routeTypeLabel(row.routeType))}</strong></div>
      ${routeStoryTime("Elérhető volt", story.availableForShiftSince || story.availableAt || story.courierRegisteredAt || row.shiftAvailableAt)}
      ${routeStoryTime("Sorba állt", queueStartedAt)}
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
  const problemDates = qualityProblemDates(payload);
  const selectedDateHasIssue = problemDates.has(state.statisticsHistoryDate);
  const plates = uniqueText(selectedRows.map((row) => row.vehiclePlate));
  const models = uniqueText(selectedRows.map((row) => row.vehicleModel));
  const orders = selectedRows.reduce((sum, row) => sum + Number(row.orders || 0), 0);
  const stops = selectedRows.reduce((sum, row) => sum + Number(row.stops || 0), 0);
  const mileage = selectedRows.reduce((sum, row) => sum + Number(row.mileageKm || 0), 0);
  const routeRowsOnly = selectedRows.filter((row) => !row.qualityStatus);
  const routes = routeRowsOnly.length;
  const apiShifts = selectedRows.reduce((max, row) => Math.max(max, Number(row.apiShiftCount || 0)), 0);
  const shifts = apiShifts || buildDailyShiftReport(selectedRows).length;
  const muszakproBookings = selectedRows.reduce((max, row) => Math.max(max, Number(row.muszakproBookingCount || 0)), 0);
  const hubShifts = selectedRows.reduce((max, row) => Math.max(max, Number(row.hubShiftCount || 0)), 0);
  const routeRows = selectedRows.map((row) => row.qualityStatus === "NO_SHOW"
    ? `<div class="daily-route-row daily-quality-exception"><div><strong>No-show műszak</strong><small>Műszak: ${escapeHtml(row.qualityLabel || (row.routeStory || {}).shiftName || "-")}</small></div><div class="daily-route-status">${renderStatusBadge(false)}</div><div><span>${escapeHtml(row.qualityNote || "Nem jelent meg a műszakban")}</span></div></div>`
    : `
    <details class="daily-route-details">
      <summary class="daily-route-row">
        <div>
          <strong>Route ${escapeHtml(row.routeId || "-")}</strong>
          <small>WH${escapeHtml(row.warehouseId || "-")} · Műszak: ${escapeHtml((row.routeStory || {}).shiftName || shortDateTime(row.plannedStartAt) || "-")} · ${escapeHtml(routeTypeLabel(row.routeType))} · ${formatCount(row.orders)} cím · ${formatCount(row.stops)} stop · ${formatAverage(row.mileageKm)} km</small>
        </div>
        <div class="daily-route-status">${renderStatusBadge(dailyRouteStatusOk(row))}</div>
        <div>
          <span>${escapeHtml(row.vehiclePlate || "-")}</span>
          <small>${escapeHtml(row.vehicleModel || "")}</small>
        </div>
      </summary>
      ${renderRouteStoryDetails(row)}
    </details>
  `).join("");
  return `
    <section class="daily-history-card ${selectedDateHasIssue ? "quality-problem-day" : ""}" id="daily-history-card">
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
        <div><span>MűszakPRO foglalás</span><strong>${formatCount(muszakproBookings)}</strong></div>
        <div><span>Hub műszak</span><strong>${formatCount(hubShifts)}</strong></div>
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
  const comparison = $("#statistics-comparison");
  const message = $("#statistics-message");
  const qualityPanel = $("#statistics-quality");
  const breakdown = $("#statistics-breakdown");
  if (!grid || !message || !qualityPanel || !breakdown) return;

  if (!payload) {
    grid.innerHTML = "";
    if (comparison) comparison.innerHTML = "";
    qualityPanel.innerHTML = "";
    breakdown.innerHTML = "";
    message.innerHTML = `<div class="notice">Válassz hónapot, majd frissítsd a statisztikát.</div>`;
    return;
  }

  const summary = payload.summary || {};
  const previousPayload = state.statisticsPrevious || {};
  const previousSummary = previousPayload.summary || {};
  const currentQuality = payload.qualitySummary || {};
  const previousQuality = previousPayload.qualitySummary || {};
  const routes = Number(summary.routes || 0);
  const orders = Number(summary.orders || 0);

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
  const personalComparison = `
    <section class="courier-statistics-compare">
      <div class="process-title"><span class="step-code">↗</span><div><h3>Havi összehasonlítás</h3><p>Az aktuális hónap eredménye az előző hónaphoz képest.</p></div></div>
      <div class="admin-stat-donut-grid courier-stat-donut-grid">
        ${adminDonutCard("Összes kör", "Kivitt túrák", routes, previousSummary.routes)}
        ${adminDonutCard("Összes cím", "Teljesített rendelések", orders, previousSummary.orders)}
        ${adminDonutCard("No-show", "Nem jelent meg műszakban", visibleQualityCount(currentQuality, "noShow"), visibleQualityCount(previousQuality, "noShow"))}
        ${adminDonutCard("Műszakkésés", "Késő sorba állás / műszakkezdés", visibleQualityCount(currentQuality, "lateShift"), visibleQualityCount(previousQuality, "lateShift"))}
        ${adminMoneyDonutCard("Borravaló", "Összes borravaló", summary.tipsTotalHuf, previousSummary.tipsTotalHuf)}
        ${adminPlaceholderDonutCard("Várható bevétel", "Havi várható kifizetés")}
      </div>
    </section>
  `;
  if (comparison) comparison.innerHTML = personalComparison;
  grid.innerHTML = "";
  grid.classList.add("hidden");
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
    const previousParams = new URLSearchParams({ month: previousMonthValue(state.statisticsMonth), _: String(Date.now()) });
    if (state.user?.canPreviewCouriers && state.workflowPreviewCourierId) {
      previousParams.set("courier", state.workflowPreviewCourierId);
    }
    const [payload, previousPayload] = await Promise.all([
      api(`/api/statistics/monthly?${params.toString()}`),
      api(`/api/statistics/monthly?${previousParams.toString()}`),
    ]);
    if (requestSeq !== state.statisticsRequestSeq) return;
    state.statistics = payload;
    state.statisticsPrevious = previousPayload;
    const dates = Object.keys(dailyHistoryByDate(payload.dailyHistory || [])).sort().reverse();
    if (!options.resetHistory && requestedHistoryDate && dates.includes(requestedHistoryDate)) {
      state.statisticsHistoryDate = requestedHistoryDate;
    }
    renderStatistics();
    refreshCourierQualityComplaints();
  } catch (error) {
    if (requestSeq !== state.statisticsRequestSeq) return;
    state.statistics = null;
    state.statisticsPrevious = null;
    if ($("#statistics-comparison")) $("#statistics-comparison").innerHTML = "";
    $("#statistics-grid").innerHTML = "";
    $("#statistics-quality").innerHTML = "";
    $("#statistics-breakdown").innerHTML = "";
    $("#statistics-message").innerHTML = `<div class="notice error">A statisztika nem tölthető be: ${escapeHtml(error.message)}</div>`;
  }
}

function previousMonthValue(month) {
  const [year, monthNumber] = String(month || localMonth()).split("-").map(Number);
  const value = new Date(year || new Date().getFullYear(), (monthNumber || 1) - 2, 1);
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}`;
}

function adminWarehouseFilters(active, target) {
  return `<div class="admin-stat-filter-row" role="group" aria-label="Raktár szűrő">
    ${[["all", "Összes raktár"], ["BUD1", "BUD1"], ["BUD2", "BUD2"]].map(([value, label]) => `<button type="button" class="admin-stat-filter ${active === value ? "active" : ""}" data-admin-warehouse="${value}" data-admin-target="${target}" aria-pressed="${active === value ? "true" : "false"}">${label}</button>`).join("")}
  </div>`;
}

function adminDelta(current, previous) {
  const now = Number(current || 0);
  const before = Number(previous || 0);
  if (!before && !now) return { text: "Nincs változás", className: "neutral" };
  if (!before) return { text: "▲ új érték", className: "up" };
  const percent = ((now - before) / before) * 100;
  return { text: `${percent >= 0 ? "▲" : "▼"} ${Math.abs(percent).toFixed(1).replace(".", ",")}%`, className: percent >= 0 ? "up" : "down" };
}

function adminDonutCard(label, note, current, previous) {
  const now = Number(current || 0);
  const before = Number(previous || 0);
  const ratio = Math.max(8, Math.min(92, before || now ? Math.round((now / Math.max(now, before, 1)) * 100) : 8));
  const delta = previous == null ? { text: "Összehasonlítás nem érhető el", className: "neutral" } : adminDelta(now, before);
  return `<article class="admin-stat-donut-card">
    <h3>${escapeHtml(label)}</h3><p>${escapeHtml(note)}</p>
    <div class="admin-stat-donut-wrap"><div class="admin-stat-donut ${delta.className}" style="--admin-donut-fill:${ratio}%"><div><strong>${formatCount(now)}</strong><span>${escapeHtml(label === "Összes cím" || label === "Címről késés" ? "cím" : label === "Összes kör" ? "kör" : "eset")}</span></div></div></div>
    <span class="admin-stat-delta ${delta.className}">${delta.text}</span>
    <div class="admin-stat-compare"><span>Előző hónap</span><b>${previous == null ? "—" : formatCount(before)}</b></div>
  </article>`;
}

function adminMoneyDonutCard(label, note, current, previous) {
  const now = Number(current || 0);
  const before = Number(previous || 0);
  const ratio = Math.max(8, Math.min(92, before || now ? Math.round((now / Math.max(now, before, 1)) * 100) : 8));
  const delta = adminDelta(now, before);
  return `<article class="admin-stat-donut-card">
    <h3>${escapeHtml(label)}</h3><p>${escapeHtml(note)}</p>
    <div class="admin-stat-donut-wrap"><div class="admin-stat-donut ${delta.className}" style="--admin-donut-fill:${ratio}%"><div><strong>${formatHuf(now)}</strong><span>összesen</span></div></div></div>
    <span class="admin-stat-delta ${delta.className}">${delta.text}</span>
    <div class="admin-stat-compare"><span>Előző hónap</span><b>${formatHuf(before)}</b></div>
  </article>`;
}

function adminPlaceholderDonutCard(label, note) {
  return `<article class="admin-stat-donut-card admin-stat-donut-placeholder">
    <h3>${escapeHtml(label)}</h3><p>${escapeHtml(note)}</p>
    <div class="admin-stat-donut-wrap"><div class="admin-stat-donut neutral" style="--admin-donut-fill:8%"><div><strong>—</strong><span>Később</span></div></div></div>
    <span class="admin-stat-delta neutral">Hamarosan</span>
    <div class="admin-stat-compare"><span>Adatfeltöltés után</span><b>—</b></div>
  </article>`;
}

function renderAdminShiftBookingComparison(report = {}) {
  const summary = report?.summary || [];
  const groups = new Map();
  const add = (label, muszakpro, hub) => {
    const current = groups.get(label) || { label, muszakpro: 0, hub: 0 };
    current.muszakpro += Number(muszakpro || 0);
    current.hub += Number(hub || 0);
    groups.set(label, current);
  };
  summary.forEach((row) => add(row.warehouse || "Ismeretlen raktár", row.muszakpro_booked, row.hub_uploaded));
  const rows = [
    { label: "Összesen", muszakpro: Number(report?.totals?.muszakproBooked || 0), hub: Number(report?.totals?.hubUploaded || 0) },
    ...["BUD1", "BUD2"].map((label) => groups.get(label) || { label, muszakpro: 0, hub: 0 }),
  ];
  return `
    <section class="admin-stat-section admin-shift-compare-section">
      <h3>Műszakfoglalás összevetése</h3>
      <p class="admin-stat-note">A MűszakProban foglalt műszakok és a Courier Hub / Kifli felvezetett műszakok összehasonlítása.</p>
      <div class="admin-shift-compare-table-wrap">
        <table class="admin-shift-compare-table">
          <thead><tr><th>Raktár</th><th>MűszakPro foglalt</th><th>Courier Hub / Kifli foglalt</th><th>Különbség</th><th>Hub / MűszakPro</th></tr></thead>
          <tbody>${rows.map((row) => {
            const difference = row.hub - row.muszakpro;
            const ratio = row.muszakpro ? Math.round((row.hub / row.muszakpro) * 100) : 0;
            const tone = difference === 0 ? "neutral" : difference > 0 ? "positive" : "negative";
            return `<tr><td><strong>${escapeHtml(row.label)}</strong></td><td>${formatCount(row.muszakpro)}</td><td>${formatCount(row.hub)}</td><td class="${tone}">${difference > 0 ? "+" : ""}${formatCount(difference)}</td><td>${row.muszakpro ? `${formatCount(ratio)}%` : "-"}</td></tr>`;
          }).join("")}</tbody>
        </table>
      </div>
    </section>
  `;
}

function renderAdminStatisticsPanel(current, previous, shiftReport = null) {
  const currentSummary = current?.summary || {};
  const previousSummary = previous?.summary || {};
  const currentTypes = current?.routeTypes || [];
  const maxType = Math.max(1, ...currentTypes.map((item) => Number(item.routes || 0)));
  const typeRows = currentTypes.map((item) => `<div class="admin-stat-type-row"><span>${escapeHtml(item.label || item.key || "-")}</span><div class="admin-stat-track"><i class="${escapeHtml(item.key || "city")}" style="width:${Math.max(3, Math.round((Number(item.routes || 0) / maxType) * 100))}%"></i></div><b>${formatCount(item.routes)}</b></div>`).join("");
  return `${adminWarehouseFilters(current?.warehouse || state.adminStatisticsWarehouse, "admin")}
    <div class="admin-stat-subtitle">${escapeHtml(current?.month || state.adminStatisticsMonth)} · Összes raktárra vagy kiválasztott raktárra szűrve</div>
    <div class="admin-stat-donut-grid">
      ${adminDonutCard("Összes kör", "Kivitt túrák", currentSummary.routes, previousSummary.routes)}
      ${adminDonutCard("Összes cím", "Teljesített rendelések", currentSummary.orders, previousSummary.orders)}
      ${adminDonutCard("No-show", "Nem jelent meg műszakban", currentSummary.noShow, previousSummary.noShow)}
      ${adminDonutCard("Címről késés", "Késő címek összesen", currentSummary.lateAddresses, previousSummary.lateAddresses)}
    </div>
    <section class="admin-stat-section"><h3>Túratípus szerinti bontás</h3><div class="admin-stat-type-list">${typeRows || `<div class="notice">Nincs túratípus adat.</div>`}</div><p class="updated-at">Műszakkésés: ${formatCount(currentSummary.lateShift)} · Műszakok: ${formatCount(currentSummary.shifts)}</p></section>
    ${shiftReport ? renderAdminShiftBookingComparison(shiftReport) : ""}`;
}

function renderFinancialStatisticsPanel(payload) {
  const summary = payload?.summary || {};
  const weekly = payload?.weekly || [];
  const breakdown = payload?.breakdown || [];
  const maxWeekly = Math.max(1, ...weekly.map((item) => Number(item.costHuf || 0)));
  const weeklyRows = weekly.map((item) => `<div class="financial-stat-week"><span>${escapeHtml(item.week || "-")}</span><div class="financial-stat-track"><i style="width:${Math.max(3, Math.round((Number(item.costHuf || 0) / maxWeekly) * 100))}%"></i></div><b>${formatHuf(item.costHuf || 0)}</b></div>`).join("");
  const breakdownRows = breakdown.map((item) => `<div class="financial-stat-breakdown-row"><span>${escapeHtml(item.label || item.key || "Egyéb")}</span><b>${formatHuf(item.amountHuf || 0)}</b></div>`).join("");
  return `${adminWarehouseFilters(payload?.warehouse || state.financialStatisticsWarehouse, "financial")}
    <div class="admin-stat-subtitle">${escapeHtml(payload?.month || state.financialStatisticsMonth)} · Pénzügyi snapshot és Courier Hub route adatok</div>
    <div class="financial-stat-kpi-grid"><div><span>Teljes költség</span><strong>${formatHuf(summary.totalCostHuf || 0)}</strong></div><div><span>Útvonalak</span><strong>${formatCount(summary.routes)}</strong></div><div><span>Rendelések</span><strong>${formatCount(summary.orders)}</strong></div><div><span>Költség / útvonal</span><strong>${formatHuf(summary.costPerRouteHuf || 0)}</strong></div></div>
    <div class="financial-stat-grid"><section class="admin-stat-section"><h3>Heti költségtrend</h3><div class="financial-stat-weeks">${weeklyRows || `<div class="notice">Nincs heti adat.</div>`}</div></section><section class="admin-stat-section"><h3>Díjbontás</h3><div class="financial-stat-breakdown">${breakdownRows || `<div class="notice">Nincs pénzügyi tétel.</div>`}</div></section></div>`;
}

function bindAdminStatisticsFilters(panel) {
  panel?.querySelectorAll("[data-admin-warehouse]").forEach((button) => button.addEventListener("click", () => {
    const target = button.getAttribute("data-admin-target");
    const warehouse = button.getAttribute("data-admin-warehouse") || "all";
    if (target === "financial") {
      state.financialStatisticsWarehouse = warehouse;
      loadFinancialStatistics();
    } else {
      state.adminStatisticsWarehouse = warehouse;
      loadAdminStatistics();
    }
  }));
}

async function statisticsApi(path) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    return await api(path, { signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted) throw new Error("A lekérdezés túllépte a 30 másodperces időkorlátot. Próbáld újra a Frissítés gombbal.");
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function loadAdminStatistics() {
  const monthInput = $("#admin-statistics-month");
  if (monthInput?.value) state.adminStatisticsMonth = monthInput.value;
  const panel = $("#admin-statistics-panel");
  if (!panel) return;
  const requestSeq = ++state.adminStatisticsRequestSeq;
  panel.innerHTML = `<div class="notice">Admin statisztika betöltése...</div>`;
  state.adminStatistics = null;
  const month = state.adminStatisticsMonth;
  const warehouse = state.adminStatisticsWarehouse;
  const loaded = { current: null, previous: null, shiftReport: null };
  const errors = {};
  const pending = new Set(["current", "previous", "shiftReport"]);
  const render = () => {
    if (requestSeq !== state.adminStatisticsRequestSeq) return;
    const notices = [];
    if (loaded.current) {
      state.adminStatistics = { ...loaded };
      notices.push(renderAdminStatisticsPanel(loaded.current, loaded.previous, loaded.shiftReport));
    } else {
      notices.push(`<div class="notice ${errors.current ? "error" : ""}">${errors.current ? `Az admin statisztika nem tölthető be: ${escapeHtml(errors.current)}` : "Admin statisztika betöltése..."}</div>`);
    }
    for (const [key, label] of [["previous", "Előző havi összehasonlítás"], ["shiftReport", "Műszakfoglalás összevetése"]]) {
      if (errors[key]) notices.push(`<div class="notice error">${label}: ${escapeHtml(errors[key])}</div>`);
      else if (pending.has(key)) notices.push(`<div class="notice">${label} betöltése...</div>`);
    }
    panel.innerHTML = notices.join("");
    bindAdminStatisticsFilters(panel);
  };
  const load = async (key, path) => {
    try {
      loaded[key] = await statisticsApi(path);
    } catch (error) {
      errors[key] = error.message;
    } finally {
      pending.delete(key);
      render();
    }
  };
  const params = (value) => new URLSearchParams({ month: value, warehouse, _: String(Date.now()) });
  await Promise.all([
    load("current", `/api/admin/statistics/monthly?${params(month)}`),
    load("previous", `/api/admin/statistics/monthly?${params(previousMonthValue(month))}`),
    load("shiftReport", `/api/routes/monthly-shift-report?${params(month)}`),
  ]);
}

async function loadFinancialStatistics() {
  const monthInput = $("#financial-statistics-month");
  if (monthInput?.value) state.financialStatisticsMonth = monthInput.value;
  const panel = $("#financial-statistics-panel");
  if (!panel) return;
  const requestSeq = ++state.financialStatisticsRequestSeq;
  panel.innerHTML = `<div class="notice">Pénzügyi statisztika betöltése...</div>`;
  try {
    const params = new URLSearchParams({ month: state.financialStatisticsMonth, warehouse: state.financialStatisticsWarehouse, _: String(Date.now()) });
    const payload = await statisticsApi(`/api/admin/statistics/monthly?${params}`);
    if (requestSeq !== state.financialStatisticsRequestSeq) return;
    state.financialStatistics = payload;
    panel.innerHTML = renderFinancialStatisticsPanel(payload);
    bindAdminStatisticsFilters(panel);
  } catch (error) {
    if (requestSeq !== state.financialStatisticsRequestSeq) return;
    panel.innerHTML = `<div class="notice error">A pénzügyi statisztika nem tölthető be: ${escapeHtml(error.message)}</div>`;
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

function googleMapsUrl(address) {
  const value = String(address || "").trim();
  if (!value) return "";
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(value)}&travelmode=driving`;
}

function googleMapsRouteUrl(stops) {
  const addresses = (stops || []).map((stop) => String(stop.address || "").trim()).filter(Boolean);
  if (!addresses.length) return "";
  const origin = addresses[0];
  const destination = addresses[addresses.length - 1] || origin;
  const waypoints = addresses.slice(1, -1).slice(0, 23);
  const params = new URLSearchParams({
    api: "1",
    origin,
    destination,
    travelmode: "driving",
  });
  if (waypoints.length) params.set("waypoints", waypoints.join("|"));
  return `https://www.google.com/maps/dir/?${params.toString()}`;
}

function googleMapsEmbedRouteUrl(stops, apiKey) {
  const addresses = (stops || []).map((stop) => String(stop.address || "").trim()).filter(Boolean);
  const key = String(apiKey || "").trim();
  if (!key || addresses.length < 2) return "";
  const origin = addresses[0];
  const destination = addresses[addresses.length - 1];
  const waypoints = addresses.slice(1, -1).slice(0, 20);
  const params = new URLSearchParams({
    key,
    origin,
    destination,
    mode: "driving",
    language: "hu",
    region: "hu",
  });
  if (waypoints.length) params.set("waypoints", waypoints.join("|"));
  return `https://www.google.com/maps/embed/v1/directions?${params.toString()}`;
}

function googleMapsPublicEmbedUrl(address) {
  const value = String(address || "").trim();
  if (!value) return "";
  return `https://maps.google.com/maps?q=${encodeURIComponent(value)}&output=embed`;
}

function googleMapsPublicRouteEmbed(stops) {
  const addresses = (stops || []).map((stop) => String(stop.address || "").trim()).filter(Boolean);
  if (addresses.length < 2) return null;
  const visibleAddresses = addresses.slice(0, 25);
  const params = new URLSearchParams({
    output: "embed",
    saddr: visibleAddresses[0],
    daddr: visibleAddresses.slice(1).join(" to:"),
  });
  return {
    url: `https://maps.google.com/maps?${params.toString()}`,
    visibleCount: visibleAddresses.length,
    totalCount: addresses.length,
  };
}

function stopStateClass(stop) {
  const stateValue = String(stop?.state || "").toLowerCase();
  if (stateValue === "completed") return "done";
  if (stateValue === "current") return "active";
  if (stop?.isLate || stop?.slotMissProjected) return "risk";
  return "pending";
}

function stopTimingLabel(stop) {
  if (!stop) return "";
  const arrival = stop.realArrival || stop.estimatedArrival || stop.plannedArrival || "";
  const arrivalLabel = stop.realArrival ? "Érkezett" : stop.estimatedArrival ? "Várható" : "Tervezett";
  const windowText = routeTimeRange(stop.windowFrom, stop.windowTo);
  return `${arrival ? `${arrivalLabel}: ${arrival}` : "Érkezés: -"} · Ügyfélablak: ${windowText}`;
}

function stopDeltaText(stop) {
  if (!stop) return "";
  if (stop.slotMissProjected) return "kockázat";
  const delta = Number(stop.deltaMinutes);
  if (!Number.isFinite(delta) || delta === 0) return "időben";
  if (delta < 0) return `${formatCount(Math.abs(delta))} p előny`;
  return `${formatCount(delta)} p késés`;
}

function stopWindowStatusText(stop) {
  if (!stop || (!stop.address && !stop.position && !stop.windowFrom && !stop.windowTo)) return "Nincs címadat";
  const delta = Number(stop.deltaMinutes || 0);
  if (stop.slotMissProjected) return "Időkapu kockázat";
  if (!Number.isFinite(delta) || delta === 0) return "Időben";
  if (delta < 0) return `${formatCount(Math.abs(delta))} perc előny`;
  return `${formatCount(delta)} perc késés`;
}

function nextBreakText(current, next) {
  if (!current || !next) return "Nincs számolható pihenő";
  const currentDate = new Date(`2000-01-01T${current.realArrival || current.estimatedArrival || current.plannedArrival || "00:00"}:00`);
  const nextWindow = new Date(`2000-01-01T${next.windowFrom || "00:00"}:00`);
  if (Number.isNaN(currentDate.getTime()) || Number.isNaN(nextWindow.getTime())) return "Nincs számolható pihenő";
  const minutes = Math.round((nextWindow.getTime() - currentDate.getTime()) / 60000);
  if (minutes <= 5) return "Nincs érdemi várakozás";
  return `${formatCount(minutes)} perc pihenhető`;
}

function trafficSummaryText(traffic) {
  if (!traffic?.available) return "Nincs élő adat";
  const duration = Number(traffic.durationMinutes);
  if (!Number.isFinite(duration)) return "Nincs élő adat";
  const delta = Number(traffic.trafficDeltaMinutes);
  if (!Number.isFinite(delta) || delta === 0) return `${formatCount(duration)} perc`;
  const sign = delta > 0 ? "+" : "-";
  return `${formatCount(duration)} perc (${sign}${formatCount(Math.abs(delta))} p)`;
}

function trafficDetailText(traffic) {
  if (!traffic?.available) return traffic?.message || "Google/Waze API bekötés után számolható";
  const parts = [];
  if (traffic.staticDurationMinutes !== null && traffic.staticDurationMinutes !== undefined) {
    parts.push(`alap ${formatCount(traffic.staticDurationMinutes)} p`);
  }
  if (traffic.distanceKm !== null && traffic.distanceKm !== undefined) {
    parts.push(`${formatAverage(traffic.distanceKm)} km`);
  }
  return parts.join(" · ") || "Google Routes élő adat";
}

function routePlannerDefaultStopIndex(stops) {
  const index = (stops || []).findIndex((stop) => String(stop.state || "").toUpperCase() === "CURRENT");
  if (index >= 0) return index;
  const pendingIndex = (stops || []).findIndex((stop) => String(stop.state || "").toUpperCase() !== "COMPLETED");
  return pendingIndex >= 0 ? pendingIndex : 0;
}

function selectedRoutePlannerStop(stops) {
  if (!Array.isArray(stops) || !stops.length) return null;
  const selected = Number(state.routePlannerSelectedStopIndex);
  if (Number.isInteger(selected) && selected >= 0 && selected < stops.length) return stops[selected];
  return stops[routePlannerDefaultStopIndex(stops)];
}

function renderRoutePlannerMap(stops, selectedStop) {
  const mapConfig = state.currentRoute?.map || {};
  const liveMapUrl = googleMapsEmbedRouteUrl(stops, mapConfig.apiKey);
  const publicRouteMap = liveMapUrl ? null : googleMapsPublicRouteEmbed(stops);
  const selectedUrl = selectedStop?.address ? googleMapsUrl(selectedStop.address) : "";
  const selectedMapUrl = selectedStop?.address ? googleMapsPublicEmbedUrl(selectedStop.address) : "";
  const mapUrl = liveMapUrl || publicRouteMap?.url || selectedMapUrl;
  if (!mapUrl) {
    return `
      <div class="route-planner-map route-planner-map-missing" aria-label="Túra térkép nézet">
        <strong>Élő térkép nem elérhető</strong>
        <small>Nincs megjeleníthető cím ehhez a túrához.</small>
      </div>
    `;
  }
  return `
    <div class="route-planner-map route-planner-live-map" aria-label="Élő Google térkép">
      <iframe
        title="Élő túratérkép"
        src="${escapeHtml(mapUrl)}"
        loading="lazy"
        referrerpolicy="no-referrer-when-downgrade"
        allowfullscreen>
      </iframe>
      <div class="route-planner-map-toolbar">
        <span>${
          liveMapUrl
            ? `${escapeHtml(formatCount(stops.length))} megálló`
            : publicRouteMap
              ? `${escapeHtml(formatCount(publicRouteMap.visibleCount))}/${escapeHtml(formatCount(publicRouteMap.totalCount))} megálló térképen`
              : "Kiválasztott megálló térképen"
        }</span>
        ${selectedUrl ? `<a href="${selectedUrl}" target="_blank" rel="noopener">Kiválasztott cím</a>` : ""}
      </div>
    </div>
  `;
}

function renderRoutePlanner(route) {
  const stops = Array.isArray(route?.stops) ? route.stops : [];
  if (!stops.length) return "";
  const routeKey = [route?.routeId, route?.courierId, route?.warehouse].filter(Boolean).join(":");
  if (routeKey && state.routePlannerRouteKey !== routeKey) {
    state.routePlannerRouteKey = routeKey;
    state.routePlannerSelectedStopIndex = null;
  }
  const status = route.plannerStatus || {};
  const current = route.current || stops.find((stop) => String(stop.state || "").toUpperCase() === "CURRENT") || stops.find((stop) => String(stop.state || "").toUpperCase() !== "COMPLETED") || stops[0];
  const next = route.next || stops.find((stop) => Number(stop.position) > Number(current?.position || 0) && String(stop.state || "").toUpperCase() !== "COMPLETED");
  const selectedStop = selectedRoutePlannerStop(stops) || current;
  const nextAddress = selectedStop?.address || next?.address || current?.address || "";
  const fullRouteUrl = googleMapsRouteUrl(stops);
  return `
    <section class="route-planner">
      <div class="route-planner-head">
        <div>
          <span>Túra állapota</span>
          <strong>${escapeHtml(status.label || `${current?.position || "-"} / ${stops.length}`)}</strong>
          <small>${escapeHtml(formatCount(status.remainingStops ?? 0))} megálló van hátra</small>
        </div>
        <div>
          <span>Aktuális cím</span>
          <strong>${escapeHtml(current?.address || "Nincs aktuális cím")}</strong>
          <small>${escapeHtml(stopTimingLabel(current))}</small>
        </div>
      </div>
      ${renderRoutePlannerMap(stops, selectedStop)}
      <div class="route-planner-selected">
        <span>Kiválasztott megálló</span>
        <strong>#${escapeHtml(selectedStop?.position || "-")} · ${escapeHtml(selectedStop?.address || "Cím nincs megadva")}</strong>
        <small>${escapeHtml(stopTimingLabel(selectedStop))}</small>
        <small>Állapot: ${escapeHtml(selectedStop?.stateLabel || "-")} · ${escapeHtml(stopDeltaText(selectedStop))}</small>
      </div>
      <div class="route-planner-insights">
        <div><span>Forgalmi eltérés</span><strong>${escapeHtml(trafficSummaryText(route.traffic))}</strong><small>${escapeHtml(trafficDetailText(route.traffic))}</small></div>
        <div><span>Pihenő / várakozás</span><strong>${escapeHtml(nextBreakText(current, next))}</strong><small>Következő ügyfélablak alapján</small></div>
        <div><span>Időablak állapot</span><strong>${status.lateOrRiskyStops ? `${formatCount(status.lateOrRiskyStops)} figyelendő` : "Rendben"}</strong><small>Hub stop adatok alapján</small></div>
      </div>
      <div class="route-planner-actions">
        ${nextAddress ? `<a class="waze-button" href="${wazeUrl(nextAddress)}" target="_blank" rel="noopener">Waze</a>` : ""}
        ${nextAddress ? `<a class="route-map-button" href="${googleMapsUrl(nextAddress)}" target="_blank" rel="noopener">Google térkép</a>` : ""}
        ${fullRouteUrl ? `<a class="route-map-button route-map-button-wide" href="${fullRouteUrl}" target="_blank" rel="noopener">Teljes túra térképen</a>` : ""}
      </div>
      <div class="route-planner-stop-list">
        ${stops.map((stop, index) => `
          <button class="route-planner-stop ${stopStateClass(stop)} ${String(stop.position || "") === String(selectedStop?.position || "") ? "selected" : ""}" type="button" data-route-stop-index="${index}">
            <span class="route-planner-stop-number">${escapeHtml(stop.position || "-")}</span>
            <div>
              <strong>${escapeHtml(stop.address || "Cím nincs megadva")}</strong>
              <small>${escapeHtml(stopTimingLabel(stop))}</small>
            </div>
            <em>${escapeHtml(stopDeltaText(stop))}</em>
          </button>
        `).join("")}
      </div>
    </section>
  `;
}

function bindRoutePlannerInteractions() {
  document.querySelectorAll("[data-route-stop-index]").forEach((element) => {
    element.addEventListener("click", () => {
      state.routePlannerSelectedStopIndex = Number(element.dataset.routeStopIndex);
      renderCurrentRoute();
    });
  });
}

function vehicleLabel(vehicle) {
  if (!vehicle) return "";
  if (typeof vehicle === "string") return vehicle;
  const plate = vehicle.licensePlate || vehicle.vehiclePlate || "";
  const car = vehicle.car || vehicle.fridgeConfig || "";
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

function routeProgressCounts(route) {
  const total = Number(route?.totalOrders || route?.stops?.length || 0);
  const explicitDelivered = Number(route?.deliveredOrders || 0);
  const completedStops = Array.isArray(route?.stops)
    ? route.stops.filter((stop) => String(stop?.state || "").toUpperCase() === "COMPLETED").length
    : 0;
  const currentPosition = Number(route?.current?.position || 0);
  let delivered = Math.max(explicitDelivered, completedStops);
  if (!delivered && Number.isFinite(currentPosition) && currentPosition > 1) {
    delivered = currentPosition - 1;
  }
  if (String(route?.current?.state || "").toUpperCase() === "COMPLETED" && currentPosition > delivered) {
    delivered = currentPosition;
  }
  delivered = Math.max(0, Math.min(delivered, total || delivered));
  const remaining = Math.max(0, total - delivered);
  return { total, delivered, remaining };
}

function routeProgressPercent(route) {
  const { total, delivered } = routeProgressCounts(route);
  if (!Number.isFinite(total) || total <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round((delivered / total) * 100)));
}

function routeLivePositionBlock(route) {
  const position = route?.livePosition || {};
  const latitude = Number(position.latitude);
  const longitude = Number(position.longitude);
  if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return "";
  const mapUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(`${latitude},${longitude}`)}`;
  return `
    <section class="route-live-card">
      <div>
        <span>Élő pozíció</span>
        <strong>${escapeHtml(latitude.toFixed(5))}, ${escapeHtml(longitude.toFixed(5))}</strong>
        <small>Utolsó jel: ${escapeHtml(shortDateTime(position.lastSeenAt || route.updatedAt || ""))}</small>
      </div>
      <a class="route-map-button" href="${mapUrl}" target="_blank" rel="noopener">Térkép</a>
    </section>
  `;
}

function routeProgressBlock(route) {
  const { total, delivered, remaining } = routeProgressCounts(route);
  const percent = routeProgressPercent(route);
  const late = Number(route?.plannerStatus?.lateOrRiskyStops || 0);
  return `
    <section class="route-progress-card">
      <div class="route-progress-head">
        <div>
          <span>Haladás</span>
          <strong>${formatCount(delivered)} / ${formatCount(total)} cím</strong>
        </div>
        <em>${formatCount(remaining)} hátra</em>
      </div>
      <div class="route-progress-bar"><i style="width:${percent}%"></i></div>
      <div class="route-progress-meta">
        <span>Aktuális: #${escapeHtml(route?.current?.position || "-")}</span>
        <span>Késéses: ${formatCount(late)}</span>
      </div>
    </section>
  `;
}

function routeTimeDetailsBlock(route, departure, returnTime) {
  const story = route?.routeStory || {};
  const queueStartedAt = routeQueueStartedAt(route || {}, story);
  return `
    <section class="route-detail-card">
      <h4>Idő részletek</h4>
      <div class="stat-breakdown-list">
        <div class="stat-row"><span>Sorba állt</span><strong>${escapeHtml(timeOnly(queueStartedAt))}</strong></div>
        <div class="stat-row"><span>Túrát kapott</span><strong>${escapeHtml(timeOnly(story.assignedAt || route.routeAssignedAt || ""))}</strong></div>
        <div class="stat-row"><span>Indulás</span><strong>${escapeHtml(departure || "-")}</strong></div>
        <div class="stat-row"><span>Várható vissza</span><strong>${escapeHtml(returnTime || "-")}</strong></div>
        <div class="stat-row"><span>Visszaérkezésig</span><strong>${escapeHtml(returnCountdownText(route.minutesUntilReturn))}</strong></div>
      </div>
    </section>
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
  const nextGoogle = googleMapsUrl(current?.address);
  const currentWindow = current ? routeTimeRange(current.windowFrom, current.windowTo) : "";
  const currentArrival = current?.estimatedArrival || current?.plannedArrival || "";
  const missingCheckpointText = route.source && route.source !== "live"
    ? "Ehhez a mentett túraadathoz nincs cím-szintű lista."
    : "A túra még nem indult el.";
  const progressCounts = routeProgressCounts(route);

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
      <div><span>Teljesítve</span><strong>${formatCount(progressCounts.delivered)}</strong></div>
      <div><span>Vissza</span><strong>${escapeHtml(returnTime || "-")}</strong></div>
    </div>

    <section class="route-next-card">
      <span>Következő cím</span>
      <div class="route-next-number">#${escapeHtml(current?.position || "-")}</div>
      <strong>${escapeHtml(current?.address || "Nincs aktuális cím")}</strong>
      <small>${current ? `Order: ${escapeHtml(current.orderId || "-")} · Időkapu: ${escapeHtml(currentWindow || "-")}` : escapeHtml(missingCheckpointText)}</small>
      ${currentArrival ? `<small>${current?.estimatedArrival ? "Várható érkezés" : "Tervezett érkezés"}: ${escapeHtml(currentArrival)}</small>` : ""}
      <div class="route-action-row">
        ${nextWaze ? `<a class="waze-button" href="${nextWaze}" target="_blank" rel="noopener">Waze</a>` : ""}
        ${nextGoogle ? `<a class="route-map-button" href="${nextGoogle}" target="_blank" rel="noopener">Google</a>` : ""}
        ${current?.address ? `<button class="route-copy-button" id="route-copy-address" type="button">Cím másolása</button>` : ""}
      </div>
    </section>

    ${routeLivePositionBlock(route)}

    ${routeProgressBlock(route)}

    ${renderRoutePlanner(route)}

    ${routeTimeDetailsBlock(route, departure, returnTime)}

    ${routeVehicleBlock(route.vehicle)}

    ${renderCurrentRouteStory(route)}

    <button id="delay-alert-button" class="route-problem-button" type="button">
      Problémám van
    </button>
  `;

  $("#delay-alert-button")?.addEventListener(
    "click",
    openDelayAlertDialog
  );
  $("#route-copy-address")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(current?.address || "");
      $("#route-copy-address").textContent = "Másolva";
    } catch (_error) {
      $("#route-copy-address").textContent = "Nem sikerült";
    }
  });
  bindRoutePlannerInteractions();
  logRouteAutoDelay(route);
}

async function loadCurrentRoute() {
  if (state.currentRouteLoading) return;
  state.currentRouteLoading = true;
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
  } finally {
    state.currentRouteLoading = false;
  }
}

function routeDetailValue(value, fallback = "-") {
  const text = String(value ?? "").trim();
  return text || fallback;
}

function routeDetailMinutes(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${formatCount(numeric)} perc` : "-";
}

function routeDetailClock(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return "-";
  const minutes = Math.max(0, Math.round(numeric));
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return `${formatCount(hours)}:${String(rest).padStart(2, "0")}`;
}

function routeDetailDistance(value) {
  if (value === null || value === undefined || value === "") return "-";
  const numeric = Number(value);
  return Number.isFinite(numeric) ? `${formatAverage(numeric)} km` : "-";
}

function routeDetailCalculatedKm(row = {}) {
  return row.calculatedRouteKm ?? row.routeDistance?.distanceKm ?? "";
}

function routeDetailsSearchText(value = "") {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function routeDetailsTypeKey(row = {}) {
  const text = routeDetailsSearchText(`${row.routeType || ""} ${row.routeTypeLabel || ""}`);
  if (text.includes("express")) return "express";
  if (text.includes("region") || text.includes("regio")) return "regional";
  return "city";
}

function routeDetailsFilteredRows(rows = []) {
  const query = routeDetailsSearchText(state.routeDetailsQuery || $("#route-details-query")?.value || "");
  const routeId = routeDetailsSearchText(state.routeDetailsRouteId || $("#route-details-route-id")?.value || "");
  const routeType = state.routeDetailsType || $("#route-details-type")?.value || "all";
  const warehouse = $("#route-stats-warehouse")?.value || "all";
  return rows.filter((row) => {
    if (warehouse !== "all" && String(row.warehouse || "").toUpperCase() !== warehouse) return false;
    if (routeType !== "all" && routeDetailsTypeKey(row) !== routeType) return false;
    if (routeId && !routeDetailsSearchText(row.routeId).includes(routeId)) return false;
    if (query) {
      const haystack = routeDetailsSearchText(`${row.courierName || ""} ${row.courierId || ""}`);
      if (!haystack.includes(query)) return false;
    }
    return true;
  });
}

function routeDetailsSummary(rows = []) {
  const totalWaiting = rows.reduce((sum, row) => sum + Number(row.waitingMinutes || 0), 0);
  const totalLoading = rows.reduce((sum, row) => sum + Number(row.loadingMinutes || 0), 0);
  const totalRoute = rows.reduce((sum, row) => sum + Number(row.routeMinutes || 0), 0);
  const totalFull = rows.reduce((sum, row) => sum + Number(row.totalMinutes || 0), 0);
  const tipSum = rows.reduce((sum, row) => sum + Number(row.tipHuf || 0), 0);
  const over5h = rows.filter((row) => Number(row.totalMinutes || row.routeMinutes || 0) > 300).length;
  return {
    routes: rows.length,
    orders: rows.reduce((sum, row) => sum + Number(row.orders || 0), 0),
    stops: rows.reduce((sum, row) => sum + Number(row.stops || 0), 0),
    waitingAvg: rows.length ? Math.round(totalWaiting / rows.length) : 0,
    loadingAvg: rows.length ? Math.round(totalLoading / rows.length) : 0,
    routeAvg: rows.length ? Math.round(totalRoute / rows.length) : 0,
    fullAvg: rows.length ? Math.round(totalFull / rows.length) : 0,
    tipSum,
    over5h,
  };
}

function routeReportFieldsByKey() {
  return Object.fromEntries(ROUTE_REPORT_FIELDS.map((field) => [field.key, field]));
}

function routeReportSelectedFields() {
  const fieldsByKey = routeReportFieldsByKey();
  const keys = (state.routeDetailsReportFields || []).filter((key) => fieldsByKey[key]);
  if (!keys.length) return DEFAULT_ROUTE_REPORT_FIELDS.map((key) => fieldsByKey[key]).filter(Boolean);
  return keys.map((key) => fieldsByKey[key]).filter(Boolean);
}

function routeReportMoveField(key, target) {
  const fieldsByKey = routeReportFieldsByKey();
  if (!fieldsByKey[key]) return;
  const current = state.routeDetailsReportFields || [];
  if (target === "selected") {
    if (!current.includes(key)) state.routeDetailsReportFields = [...current, key];
  } else {
    state.routeDetailsReportFields = current.filter((item) => item !== key);
  }
  renderRouteReportBuilder();
  renderRouteDetails();
}

function renderRouteReportBuilder() {
  const availableTarget = $("#route-report-available-fields");
  const selectedTarget = $("#route-report-selected-fields");
  if (!availableTarget || !selectedTarget) return;
  const selectedKeys = new Set(state.routeDetailsReportFields || []);
  const renderChip = (field, zone) => `
    <button class="route-report-field-chip" type="button" draggable="true" data-route-report-field="${escapeHtml(field.key)}" data-route-report-zone-source="${zone}">
      <strong>${escapeHtml(field.label)}</strong>
      <small>${zone === "selected" ? "látható" : "hozzáadás"}</small>
    </button>
  `;
  availableTarget.innerHTML = ROUTE_REPORT_FIELDS
    .filter((field) => !selectedKeys.has(field.key))
    .map((field) => renderChip(field, "available"))
    .join("") || `<p class="muted">Minden mező a riportban van.</p>`;
  selectedTarget.innerHTML = routeReportSelectedFields()
    .map((field) => renderChip(field, "selected"))
    .join("") || `<p class="muted">Kattints vagy húzz ide mezőket.</p>`;
}

function openRouteReportDialog() {
  const dialog = $("#route-report-dialog");
  if (!dialog) return;
  if ($("#route-report-auto-excel")) $("#route-report-auto-excel").checked = Boolean(state.routeDetailsAutoExcel);
  if ($("#route-report-include-summary")) $("#route-report-include-summary").checked = state.routeDetailsIncludeSummary !== false;
  renderRouteReportBuilder();
  if (typeof dialog.showModal === "function") dialog.showModal();
}

function closeRouteReportDialog() {
  const dialog = $("#route-report-dialog");
  if (dialog?.open) dialog.close();
}

function routeReportSummaryCards(summary = {}) {
  const selectedSummaries = new Set(routeReportSelectedFields().map((field) => field.summary).filter(Boolean));
  const cards = [
    { key: "routes", label: "Túra összesen", value: formatCount(summary.routes), note: "szűrés után", always: true },
    { key: "orders", label: "Rendelés / cím", value: formatCount(summary.orders), note: "route sorokból" },
    { key: "stops", label: "Stopok", value: formatCount(summary.stops), note: "route sorokból" },
    { key: "waitingAvg", label: "Átlag várakozás", value: routeDetailMinutes(summary.waitingAvg), note: "sorbaállástól kiosztásig" },
    { key: "loadingAvg", label: "Átlag bepakolás", value: routeDetailMinutes(summary.loadingAvg), note: "kiosztástól indulásig" },
    { key: "routeAvg", label: "Átlag túraidő", value: routeDetailClock(summary.routeAvg), note: "bepakolás nélkül" },
    { key: "fullAvg", label: "Átlag teljes idő", value: routeDetailClock(summary.fullAvg), note: "bepakolással" },
    { key: "over5h", label: "5 óra felett", value: formatCount(summary.over5h), note: "teljes idő alapján" },
    { key: "tipSum", label: "Borravaló", value: formatHuf(summary.tipSum || 0), note: "összesen" },
  ];
  return cards
    .filter((card) => card.always || selectedSummaries.has(card.key))
    .map((card) => `<div class="stat-card"><span>${escapeHtml(card.label)}</span><strong>${escapeHtml(card.value)}</strong><small>${escapeHtml(card.note)}</small></div>`)
    .join("");
}

function renderRouteLegs(row = {}) {
  const legs = Array.isArray(row.routeLegs)
    ? row.routeLegs
    : Array.isArray(row.routeDistance?.legs)
      ? row.routeDistance.legs
      : [];
  if (!legs.length) {
    return `
      <section class="route-leg-list">
        <h4>Km bontás</h4>
        <p>Nincs címek közötti km bontás ehhez a route-hoz.</p>
      </section>
    `;
  }
  return `
    <section class="route-leg-list">
      <h4>Km bontás</h4>
      ${legs.map((leg) => `
        <div class="route-leg-row">
          <span>${escapeHtml(leg.from || "-")} → ${escapeHtml(leg.to || "-")}</span>
          <strong>${escapeHtml(routeDetailDistance(leg.distanceKm))}</strong>
          <small>${escapeHtml(leg.toAddress || "")}</small>
        </div>
      `).join("")}
    </section>
  `;
}

function routeDetailsExcelUrl() {
  const month = $("#route-details-month")?.value || state.statisticsMonth;
  const courier = $("#route-details-courier")?.value || "";
  const query = state.routeDetailsQuery || $("#route-details-query")?.value || "";
  const routeId = state.routeDetailsRouteId || $("#route-details-route-id")?.value || "";
  const routeType = state.routeDetailsType || $("#route-details-type")?.value || "all";
  const warehouse = $("#route-stats-warehouse")?.value || "all";
  if (!month) return "";
  const params = new URLSearchParams({ month });
  if (courier) params.set("courier", courier);
  if (query) params.set("q", query);
  if (routeId) params.set("route_id", routeId);
  if (routeType && routeType !== "all") params.set("route_type", routeType);
  if (warehouse && warehouse !== "all") params.set("warehouse", warehouse);
  return `/api/routes/details.xlsx?${params.toString()}`;
}

function monthlyShiftRouteReportExcelUrl() {
  const month = $("#route-details-month")?.value || state.statisticsMonth;
  const courier = $("#route-details-courier")?.value || state.workflowPreviewCourierId || "";
  const warehouse = $("#route-stats-warehouse")?.value || "all";
  if (!month) return "";
  const params = new URLSearchParams({ month });
  if (courier) params.set("courier", courier);
  if (warehouse && warehouse !== "all") params.set("warehouse", warehouse);
  return `/api/routes/monthly-shift-report.xlsx?${params.toString()}`;
}

function routeShiftReportRange() {
  const month = $("#route-details-month")?.value || state.statisticsMonth;
  const courier = $("#route-details-courier")?.value || state.workflowPreviewCourierId || "";
  const warehouse = $("#route-stats-warehouse")?.value || "all";
  return { month, courier, warehouse };
}

function routeStatisticsRange() {
  const month = $("#route-details-month")?.value || state.statisticsMonth;
  const start = $("#route-stats-start")?.value || monthStartDate(month);
  const end = $("#route-stats-end")?.value || monthEndDate(month);
  const warehouse = $("#route-stats-warehouse")?.value || "all";
  return { start, end, warehouse };
}

function routeStatisticsExcelUrl() {
  const { start, end, warehouse } = routeStatisticsRange();
  if (!start || !end) return "";
  const params = new URLSearchParams({ start, end, warehouse });
  return `/api/routes/statistics.xlsx?${params.toString()}`;
}

function routeStatsBarRows(rows = [], labelKey = "label") {
  const maxRoutes = Math.max(1, ...rows.map((row) => Number(row.routes || 0)));
  return rows.map((row) => {
    const routes = Number(row.routes || 0);
    const width = Math.max(2, Math.round(routes / maxRoutes * 100));
    return `
      <div class="route-stat-bar-row">
        <div>
          <strong>${escapeHtml(row[labelKey] || row.date || "-")}</strong>
          <small>${formatCount(row.orders || 0)} cím</small>
        </div>
        <div class="route-stat-bar-track"><span style="width:${width}%"></span></div>
        <b>${formatCount(routes)}</b>
      </div>
    `;
  }).join("");
}

function renderRouteStatistics() {
  const panel = $("#route-statistics-panel");
  if (!panel) return;
  if (!state.user?.canPreviewCouriers) {
    panel.innerHTML = "";
    return;
  }
  const payload = state.routeStatistics;
  if (!payload) {
    panel.innerHTML = "";
    return;
  }
  const excelUrl = routeStatisticsExcelUrl();
  const summary = payload.summary || {};
  const daily = payload.daily || [];
  const topDaily = [...daily].sort((a, b) => Number(b.routes || 0) - Number(a.routes || 0)).slice(0, 14);
  const routeTypes = payload.routeTypes || [];
  const warehouses = payload.warehouses || [];
  panel.innerHTML = `
    <div class="route-details-head">
      <div>
        <span>${escapeHtml(payload.start || "-")} - ${escapeHtml(payload.end || "-")}</span>
        <strong>Túra statisztika</strong>
        <small>${escapeHtml(payload.warehouse === "all" ? "Összes raktár" : payload.warehouse || "Összes raktár")} · ${escapeHtml(payload.source || "-")}</small>
      </div>
      <div class="route-details-actions">
        ${excelUrl ? `<a class="download-link" href="${excelUrl}">Statisztika Excel</a>` : ""}
      </div>
    </div>
    <div class="statistics-grid route-stat-kpis">
      <div class="stat-card"><span>Összes kivitt kör</span><strong>${formatCount(summary.routes || 0)}</strong><small>${formatCount(summary.orders || 0)} cím / rendelés</small></div>
      <div class="stat-card"><span>City</span><strong>${formatCount(summary.cityRoutes || 0)}</strong><small>Normál / city körök</small></div>
      <div class="stat-card"><span>Express</span><strong>${formatCount(summary.expressRoutes || 0)}</strong><small>Express körök</small></div>
      <div class="stat-card"><span>Regionális</span><strong>${formatCount(summary.regionalRoutes || 0)}</strong><small>Regionális körök</small></div>
      <div class="stat-card"><span>BUD1</span><strong>${formatCount(summary.bud1Routes || 0)}</strong><small>Raktári bontás</small></div>
      <div class="stat-card"><span>BUD2</span><strong>${formatCount(summary.bud2Routes || 0)}</strong><small>Raktári bontás</small></div>
    </div>
    <div class="route-stat-chart-grid">
      <section class="route-stat-chart">
        <h4>Napi körszám</h4>
        ${routeStatsBarRows(daily, "date") || `<p>Nincs adat a kiválasztott időszakra.</p>`}
      </section>
      <section class="route-stat-chart">
        <h4>Túratípus bontás</h4>
        ${routeStatsBarRows(routeTypes)}
      </section>
      <section class="route-stat-chart">
        <h4>Raktár bontás</h4>
        ${routeStatsBarRows(warehouses) || `<p>Nincs adat a kiválasztott időszakra.</p>`}
      </section>
      <section class="route-stat-chart">
        <h4>Legforgalmasabb napok</h4>
        ${routeStatsBarRows(topDaily, "date") || `<p>Nincs adat a kiválasztott időszakra.</p>`}
      </section>
    </div>
    <div class="route-details-table-wrap route-stat-table-wrap">
      <table class="route-details-table route-stat-table">
        <thead>
          <tr>
            <th>Dátum</th>
            <th>Összes kör</th>
            <th>City</th>
            <th>Express</th>
            <th>Regionális</th>
            <th>BUD1</th>
            <th>BUD2</th>
            <th>Cím / rendelés</th>
          </tr>
        </thead>
        <tbody>
          ${daily.map((row) => `
            <tr>
              <td><strong>${escapeHtml(row.date || "-")}</strong></td>
              <td>${formatCount(row.routes || 0)}</td>
              <td>${formatCount(row.cityRoutes || 0)}</td>
              <td>${formatCount(row.expressRoutes || 0)}</td>
              <td>${formatCount(row.regionalRoutes || 0)}</td>
              <td>${formatCount(row.bud1Routes || 0)}</td>
              <td>${formatCount(row.bud2Routes || 0)}</td>
              <td>${formatCount(row.orders || 0)}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

function routeShiftPercent(value) {
  return formatPercent(Number(value || 0) * 100);
}

function routeShiftRatio(numerator, denominator) {
  const bottom = Number(denominator || 0);
  return bottom ? Number(numerator || 0) / bottom : 0;
}

function routeShiftReportSummaryRows(rows = []) {
  return rows.map((row) => `
    <tr>
      <td><strong>${escapeHtml(row.courier_name || "-")}</strong><small>#${escapeHtml(row.courier_id || "-")} · ${escapeHtml(row.warehouse || "-")}</small></td>
      <td>${formatCount(row.muszakpro_booked || 0)}</td>
      <td>${formatCount(row.hub_uploaded || 0)}</td>
      <td>${formatCount(row.routes_delivered || 0)}</td>
      <td>${formatCount(row.muszakpro_days || 0)}</td>
      <td>${formatCount(row.hub_days || 0)}</td>
      <td>${formatCount(row.route_days || 0)}</td>
      <td>${routeShiftPercent(routeShiftRatio(row.hub_uploaded, row.muszakpro_booked))}</td>
      <td>${routeShiftPercent(routeShiftRatio(row.routes_delivered, row.hub_uploaded))}</td>
      <td>${formatCount(row.city_over_5h || 0)}</td>
    </tr>
  `).join("");
}

function routeShiftReportDailyRows(rows = []) {
  return rows.slice(0, 120).map((row) => `
    <tr>
      <td><strong>${escapeHtml(row.work_date || "-")}</strong></td>
      <td>${escapeHtml(row.courier_name || "-")} <small>#${escapeHtml(row.courier_id || "-")}</small></td>
      <td>${escapeHtml(row.warehouse || "-")}</td>
      <td>${formatCount(row.muszakpro_booked || 0)}</td>
      <td>${formatCount(row.hub_uploaded || 0)}</td>
      <td>${formatCount(row.routes_delivered || 0)}</td>
      <td>${formatCount(row.city_over_5h || 0)}</td>
    </tr>
  `).join("");
}

function routeShiftReportWorkTimeRows(rows = []) {
  return rows.slice(0, 300).map((row) => `
    <tr>
      <td><strong>${escapeHtml(row.work_date || "-")}</strong></td>
      <td>${escapeHtml(row.courier_name || "-")}</td>
      <td>${escapeHtml(row.work_start ? shortDateTime(row.work_start) : "-")}</td>
      <td>${escapeHtml(row.work_end ? shortDateTime(row.work_end) : "-")}</td>
      <td>${escapeHtml(durationText(row.work_minutes))}</td>
      <td>${escapeHtml(row.work_end_source || "-")}</td>
    </tr>
  `).join("");
}

function routeShiftReportCityRows(rows = []) {
  return rows.slice(0, 120).map((row) => `
    <tr>
      <td><strong>${escapeHtml(row.date || "-")}</strong></td>
      <td>${escapeHtml(row.courierName || "-")} <small>#${escapeHtml(row.courierId || "-")}</small></td>
      <td>${escapeHtml(row.warehouse || "-")}</td>
      <td>${escapeHtml(row.routeId || "-")}</td>
      <td>${escapeHtml(row.shiftName || "-")}</td>
      <td>${escapeHtml(row.routeTypeLabel || row.routeType || "-")}</td>
      <td>${escapeHtml(shortDateTime(row.plannedDepartureAt || ""))}</td>
      <td>${escapeHtml(shortDateTime(row.plannedReturnAt || ""))}</td>
      <td>${escapeHtml(routeDetailClock(row.plannedDepotToDepotMinutes))}</td>
      <td>${escapeHtml(shortDateTime(row.returnedAt || ""))}</td>
    </tr>
  `).join("");
}

function routeShiftReportSourceRows(payload = {}) {
  const rows = [];
  (payload.muszakpro_rows || []).forEach((row) => rows.push({
    source: row.source || "MűszakPro",
    date: row.work_date,
    courierId: row.courier_id,
    courierName: row.courier_name,
    warehouse: row.warehouse,
    identifier: row.booking_code || row.serial,
    name: row.shift_text,
    start: row.shift_start,
    end: "",
    status: "Aktív",
  }));
  (payload.hub_rows || []).forEach((row) => rows.push({
    source: row.source || "HUB/Giriton műszak",
    date: row.work_date,
    courierId: row.courier_id,
    courierName: row.courier_name,
    warehouse: row.warehouse,
    identifier: row.shift_id,
    name: row.shift_name,
    start: row.shift_start,
    end: row.shift_end,
    status: row.status,
  }));
  (payload.route_rows || []).forEach((row) => rows.push({
    source: "Kivitt kör",
    date: row.date,
    courierId: row.courierId,
    courierName: row.courierName,
    warehouse: row.warehouse,
    identifier: row.routeId,
    name: row.shiftName,
    start: row.plannedDepartureAt || row.routeAssignedAt,
    end: row.plannedReturnAt || row.returnedAt,
    status: row.routeTypeLabel || row.routeType,
  }));
  return rows.sort((left, right) => (
    String(left.date || "").localeCompare(String(right.date || ""))
    || String(left.courierName || "").localeCompare(String(right.courierName || ""), "hu")
    || String(left.source || "").localeCompare(String(right.source || ""), "hu")
  ));
}

function routeShiftReportSourceTableRows(rows = []) {
  return rows.slice(0, 300).map((row) => `
    <tr>
      <td>${escapeHtml(row.source || "-")}</td>
      <td><strong>${escapeHtml(row.date || "-")}</strong></td>
      <td>${escapeHtml(row.courierName || "-")} <small>#${escapeHtml(row.courierId || "-")}</small></td>
      <td>${escapeHtml(row.warehouse || "-")}</td>
      <td>${escapeHtml(row.identifier || "-")}</td>
      <td>${escapeHtml(row.name || "-")}</td>
      <td>${escapeHtml(row.start ? shortDateTime(row.start) : "-")}</td>
      <td>${escapeHtml(row.end ? shortDateTime(row.end) : "-")}</td>
      <td>${escapeHtml(row.status || "-")}</td>
    </tr>
  `).join("");
}

function renderRouteShiftReport() {
  const panel = $("#route-shift-report-panel");
  if (!panel) return;
  if (!state.user?.canPreviewCouriers) {
    panel.innerHTML = "";
    return;
  }
  const payload = state.routeShiftReport;
  if (!payload) {
    panel.innerHTML = "";
    return;
  }
  const excelUrl = monthlyShiftRouteReportExcelUrl();
  const rows = payload.summary || [];
  const daily = payload.daily || [];
  const cityRows = payload.cityOver5hRows || payload.city_over_5h_rows || [];
  const sourceRows = routeShiftReportSourceRows(payload);
  const workTimeRows = payload.work_time_rows || [];
  const sourceCounts = payload.sourceCounts || {};
  const totals = payload.totals || {};
  panel.innerHTML = `
    <div class="route-details-head">
      <div>
        <span>${escapeHtml(payload.month || "-")}</span>
        <strong>Futár műszak/kör statisztika</strong>
        <small>${escapeHtml(payload.filters?.warehouse === "all" ? "Összes raktár" : payload.filters?.warehouse || "Összes raktár")} · ${formatCount(rows.length)} futár · MűszakPro sor: ${formatCount(sourceCounts.muszakpro || 0)} · HUB sor: ${formatCount(sourceCounts.hub || 0)} · kör sor: ${formatCount(sourceCounts.routes || 0)}</small>
      </div>
      <div class="route-details-actions">
        ${excelUrl ? `<a class="download-link" href="${excelUrl}">Riport Excel</a>` : ""}
      </div>
    </div>
    <div class="statistics-grid route-stat-kpis">
      <div class="stat-card"><span>MűszakPro foglalás</span><strong>${formatCount(totals.muszakproBooked || 0)}</strong><small>foglalt műszak</small></div>
      <div class="stat-card"><span>HUB-on kapott</span><strong>${formatCount(totals.hubUploaded || 0)}</strong><small>felvezetett műszak</small></div>
      <div class="stat-card"><span>Kivitt kör</span><strong>${formatCount(totals.routesDelivered || 0)}</strong><small>route stat alapján</small></div>
      <div class="stat-card"><span>HUB / MűszakPro</span><strong>${routeShiftPercent(totals.hubToMuszakproRatio || 0)}</strong><small>arány</small></div>
      <div class="stat-card"><span>Kivitt / HUB</span><strong>${routeShiftPercent(totals.routeToHubRatio || 0)}</strong><small>arány</small></div>
      <div class="stat-card"><span>City 5 óra felett</span><strong>${formatCount(totals.cityOver5h || 0)}</strong><small>ellenőrzéshez</small></div>
    </div>
    <details class="daily-route-details route-shift-daily" open>
      <summary class="route-details-head">
        <div>
          <span>Giriton jelenléti tábla</span>
          <strong>Ledolgozott idő naponta</strong>
          <small>${formatCount(workTimeRows.length)} Giriton sor${workTimeRows.length > 300 ? " · első 300 megjelenítve" : ""}</small>
        </div>
      </summary>
      <div class="route-details-table-wrap route-stat-table-wrap">
        <table class="route-details-table route-shift-report-table">
          <thead><tr><th>Dátum</th><th>Futár</th><th>Giriton kezdés</th><th>Giriton vége / raktári vissza</th><th>Ledolgozott idő</th><th>Végidő forrása</th></tr></thead>
          <tbody>${workTimeRows.length ? routeShiftReportWorkTimeRows(workTimeRows) : `<tr><td colspan="6">Nincs Giriton jelenléti adat.</td></tr>`}</tbody>
        </table>
      </div>
    </details>
    <div class="route-details-table-wrap route-stat-table-wrap">
      <table class="route-details-table route-shift-report-table">
        <thead>
          <tr>
            <th>Futár</th>
            <th>MűszakPro foglalt</th>
            <th>HUB-on kapott</th>
            <th>Kivitt kör</th>
            <th>MűszakPro nap</th>
            <th>HUB nap</th>
            <th>Körös nap</th>
            <th>HUB / MűszakPro</th>
            <th>Kivitt / HUB</th>
            <th>City 5h+</th>
          </tr>
        </thead>
        <tbody>
          ${rows.length ? routeShiftReportSummaryRows(rows) : `<tr><td colspan="10">Nincs adat a kiválasztott szűrésre.</td></tr>`}
        </tbody>
      </table>
    </div>
    <details class="daily-route-details route-shift-daily">
      <summary class="route-details-head">
        <div>
          <span>Napi bontás</span>
          <strong>Futár napi adatok</strong>
          <small>${formatCount(daily.length)} sor${daily.length > 120 ? " · első 120 megjelenítve" : ""}</small>
        </div>
      </summary>
      <div class="route-details-table-wrap route-stat-table-wrap">
        <table class="route-details-table route-stat-table">
          <thead>
            <tr>
              <th>Dátum</th>
              <th>Futár</th>
              <th>Raktár</th>
              <th>MűszakPro</th>
              <th>HUB</th>
              <th>Kivitt kör</th>
              <th>City 5h+</th>
            </tr>
          </thead>
          <tbody>
            ${daily.length ? routeShiftReportDailyRows(daily) : `<tr><td colspan="7">Nincs napi bontás.</td></tr>`}
          </tbody>
        </table>
      </div>
    </details>
    <details class="daily-route-details route-shift-daily">
      <summary class="route-details-head">
        <div>
          <span>City 5 óra felett</span>
          <strong>Excel ellenőrző lista</strong>
          <small>${formatCount(cityRows.length)} sor${cityRows.length > 120 ? " · első 120 megjelenítve" : ""}</small>
        </div>
      </summary>
      <div class="route-details-table-wrap route-stat-table-wrap">
        <table class="route-details-table route-shift-report-table">
          <thead>
            <tr>
              <th>Dátum</th>
              <th>Futár</th>
              <th>Raktár</th>
              <th>Route ID</th>
              <th>Műszak</th>
              <th>Típus</th>
              <th>Tervezett indulás</th>
              <th>Tervezett vissza</th>
              <th>Tervezett idő</th>
              <th>Tényleges vissza</th>
            </tr>
          </thead>
          <tbody>
            ${cityRows.length ? routeShiftReportCityRows(cityRows) : `<tr><td colspan="10">Nincs City 5 óra feletti sor.</td></tr>`}
          </tbody>
        </table>
      </div>
    </details>
    <details class="daily-route-details route-shift-daily">
      <summary class="route-details-head">
        <div>
          <span>Forrás sorok</span>
          <strong>Excel forrás nézet</strong>
          <small>${formatCount(sourceRows.length)} sor${sourceRows.length > 300 ? " · első 300 megjelenítve" : ""}</small>
        </div>
      </summary>
      <div class="route-details-table-wrap route-stat-table-wrap">
        <table class="route-details-table route-shift-source-table">
          <thead>
            <tr>
              <th>Forrás</th>
              <th>Dátum</th>
              <th>Futár</th>
              <th>Raktár</th>
              <th>Azonosító</th>
              <th>Műszak / Route</th>
              <th>Kezdés</th>
              <th>Vége / vissza</th>
              <th>Státusz</th>
            </tr>
          </thead>
          <tbody>
            ${sourceRows.length ? routeShiftReportSourceTableRows(sourceRows) : `<tr><td colspan="9">Nincs forrás sor a kiválasztott szűrésre.</td></tr>`}
          </tbody>
        </table>
      </div>
    </details>
  `;
}

function renderRouteDetails() {
  const panel = $("#route-details-panel");
  if (!panel) return;
  if (!state.user?.canPreviewCouriers) {
    panel.innerHTML = `<div class="route-empty error-state"><span class="route-empty-icon">!</span><div><h3>Nincs jogosultság</h3><p>Ezt a nézetet admin jogosultsággal lehet használni.</p></div></div>`;
    return;
  }
  const payload = state.routeDetails;
  const allRows = payload?.rows || [];
  const rows = routeDetailsFilteredRows(allRows);
  if (!payload) {
    panel.innerHTML = `
      <div class="process-title">
        <span class="step-code">⇲</span>
        <div><h3>Nincs aktív riport</h3><p>Nyisd meg az új riport ablakot, válassz időszakot, raktárt, futárt és megjelenítendő statisztikákat.</p></div>
      </div>
      <button class="secondary route-details-export-all" type="button" data-route-report-open>Új riport kérése</button>
    `;
    panel.querySelector("[data-route-report-open]")?.addEventListener("click", openRouteReportDialog);
    return;
  }
  if (!rows.length) {
    panel.innerHTML = `
      <div class="route-empty">
        <span class="route-empty-icon">0</span>
        <div><h3>Nincs túra adat</h3><p>A kiválasztott szűrőkkel nem találtam route sort. Próbáld törölni a név/ID vagy Route ID szűrőt.</p></div>
      </div>
    `;
    return;
  }
  const selectedIndex = Math.min(Math.max(0, state.routeDetailsSelectedIndex || 0), rows.length - 1);
  const selected = rows[selectedIndex];
  const excelUrl = routeDetailsExcelUrl();
  const monthlyReportUrl = monthlyShiftRouteReportExcelUrl();
  const summary = routeDetailsSummary(rows);
  const selectedFields = routeReportSelectedFields();
  const summaryCards = state.routeDetailsIncludeSummary === false ? "" : routeReportSummaryCards(summary);
  panel.innerHTML = `
    <div class="route-details-head">
      <div>
        <span>${escapeHtml(payload.month || "-")}</span>
        <strong>${escapeHtml(payload.courier?.name || "Összes futár")}</strong>
        <small>${formatCount(rows.length)} route sor szűrve · ${formatCount(allRows.length)} összes sor</small>
      </div>
      <div class="route-details-actions">
        <button class="secondary" type="button" data-route-report-open>Új riport</button>
        ${excelUrl ? `<a class="download-link" href="${excelUrl}">Excel letöltés</a>` : ""}
        ${monthlyReportUrl ? `<a class="download-link" href="${monthlyReportUrl}">Havi műszak/kör riport</a>` : ""}
      </div>
    </div>
    ${summaryCards ? `<div class="statistics-grid route-details-kpis">${summaryCards}</div>` : ""}
    <div class="route-report-workspace">
      <div class="route-report-list">
        <div class="route-report-list-head">
          <div>
            <span>Túra lista</span>
            <strong>Szűrt route sorok</strong>
          </div>
          <small>Kattints egy sorra a jobb oldali bontáshoz</small>
        </div>
        <div class="route-details-table-wrap">
          <table class="route-details-table">
        <thead>
          <tr>
            <th>Route ID</th>
            ${selectedFields.map((field) => `<th>${escapeHtml(field.column)}</th>`).join("")}
          </tr>
        </thead>
        <tbody>
          ${rows.map((row, index) => `
            <tr class="${index === selectedIndex ? "active" : ""}" data-route-detail-index="${index}">
              <td><strong>${escapeHtml(routeDetailValue(row.routeId))}</strong></td>
              ${selectedFields.map((field) => `<td>${escapeHtml(field.get(row))}</td>`).join("")}
            </tr>
          `).join("")}
        </tbody>
          </table>
        </div>
      </div>
      <article class="route-story-card route-report-side">
      <div class="route-story-card-head">
        <span>Szöveges túra részletező</span>
        <strong>Route ${escapeHtml(selected.routeId || "-")}</strong>
      </div>
      <p>${escapeHtml(selected.narrative || "Ehhez a route-hoz nincs szöveges részletező.")}</p>
      <div class="route-timeline-grid">
        <div class="stat-row"><span>Futár</span><strong>${escapeHtml(selected.courierName || "-")} (#${escapeHtml(selected.courierId || "-")})</strong></div>
        <div class="stat-row"><span>Raktár</span><strong>${escapeHtml(selected.warehouse || "-")}</strong></div>
        <div class="stat-row"><span>Raktár cím</span><strong>${escapeHtml(selected.warehouseAddress || "-")}</strong></div>
        <div class="stat-row"><span>Műszak neve</span><strong>${escapeHtml(selected.shiftName || "-")}</strong></div>
        <div class="stat-row"><span>Sorbaállt</span><strong>${escapeHtml(shortDateTime(selected.queueStartedAt))}</strong></div>
        <div class="stat-row"><span>Tényleges műszak kezdés</span><strong>${escapeHtml(shortDateTime(selected.actualShiftStartAt))}</strong></div>
        <div class="stat-row"><span>Túrát kapott</span><strong>${escapeHtml(shortDateTime(selected.routeAssignedAt))}</strong></div>
        <div class="stat-row"><span>Címek / stopok</span><strong>${formatCount(selected.orders || 0)} / ${formatCount(selected.stops || 0)}</strong></div>
        <div class="stat-row"><span>Késés a túrán</span><strong>${formatCount(selected.routeDelayCount || 0)} db</strong></div>
        <div class="stat-row"><span>Indulás a raktárból</span><strong>${escapeHtml(shortDateTime(selected.departedAt))}</strong></div>
        <div class="stat-row"><span>Visszaérkezés</span><strong>${escapeHtml(shortDateTime(selected.returnedAt))}</strong></div>
        <div class="stat-row"><span>Tervezett bepakolás</span><strong>${escapeHtml(routeDetailMinutes(selected.plannedLoadingMinutes))}</strong></div>
        <div class="stat-row"><span>Bepakolás</span><strong>${escapeHtml(routeDetailMinutes(selected.loadingMinutes))}</strong></div>
        <div class="stat-row"><span>Tervezett hossz/idő</span><strong>${escapeHtml(routeDetailClock(selected.plannedRouteMinutes))}</strong></div>
        <div class="stat-row"><span>Tervezett visszaérkezés</span><strong>${escapeHtml(shortDateTime(selected.plannedReturnAt))}</strong></div>
        <div class="stat-row"><span>Tényleges túraidő</span><strong>${escapeHtml(routeDetailClock(selected.routeMinutes))}</strong></div>
        <div class="stat-row"><span>Túra bepakolással</span><strong>${escapeHtml(routeDetailMinutes(selected.totalMinutes))}</strong></div>
        <div class="stat-row"><span>Tervezett km</span><strong>${escapeHtml(routeDetailDistance(selected.hubPlannedKm))}</strong></div>
        <div class="stat-row"><span>Hub tényleges km</span><strong>${escapeHtml(routeDetailDistance(selected.actualKm))}</strong></div>
        <div class="stat-row"><span>Címekből számolt km</span><strong>${escapeHtml(routeDetailDistance(routeDetailCalculatedKm(selected)))}</strong></div>
        <div class="stat-row"><span>Hub mileage km</span><strong>${escapeHtml(routeDetailDistance(selected.hubMileageKm))}</strong></div>
        <div class="stat-row"><span>Km eltérés</span><strong>${escapeHtml(routeDetailDistance(selected.distanceDeltaKm))}</strong></div>
        <div class="stat-row"><span>Km forrás</span><strong>${escapeHtml(selected.distanceSource || selected.distanceStatus || "Nincs adat")}</strong></div>
        <div class="stat-row"><span>Következő műszak aznap</span><strong>${escapeHtml(selected.nextShiftSameDay || "-")}</strong></div>
        <div class="stat-row"><span>Túra típusa</span><strong>${escapeHtml(selected.routeTypeLabel || "-")}</strong></div>
        <div class="stat-row"><span>Borravaló</span><strong>${escapeHtml(formatHuf(selected.tipHuf || 0))}</strong></div>
        <div class="stat-row"><span>Kiflis autó</span><strong>${escapeHtml(selected.kifliVehicle || "Nincs adat")}</strong></div>
        <div class="stat-row"><span>Forrás</span><strong>${escapeHtml(selected.dataSource || "-")}</strong></div>
      </div>
      ${renderRouteLegs(selected)}
      </article>
    </div>
  `;
  panel.querySelector("[data-route-report-open]")?.addEventListener("click", openRouteReportDialog);
  panel.querySelectorAll("[data-route-detail-index]").forEach((row) => {
    row.addEventListener("click", () => {
      state.routeDetailsSelectedIndex = Number(row.dataset.routeDetailIndex || 0);
      renderRouteDetails();
    });
  });
}

async function loadRouteDetails() {
  const message = $("#route-details-message");
  const monthInput = $("#route-details-month");
  const courierSelect = $("#route-details-courier");
  const month = monthInput?.value || state.statisticsMonth;
  const courier = courierSelect?.value || "";
  try {
    state.routeDetailsAutoExcel = Boolean($("#route-report-auto-excel")?.checked);
    state.routeDetailsIncludeSummary = $("#route-report-include-summary")?.checked !== false;
    state.routeDetailsQuery = $("#route-details-query")?.value || "";
    state.routeDetailsRouteId = $("#route-details-route-id")?.value || "";
    state.routeDetailsType = $("#route-details-type")?.value || "all";
    if (message) message.innerHTML = `<div class="notice">Túra részletek betöltése...</div>`;
    state.routeDetailsSelectedIndex = 0;
    const params = new URLSearchParams({ month });
    if (courier) params.set("courier", courier);
    if (state.routeDetailsQuery) params.set("q", state.routeDetailsQuery);
    if (state.routeDetailsRouteId) params.set("route_id", state.routeDetailsRouteId);
    if (state.routeDetailsType && state.routeDetailsType !== "all") params.set("route_type", state.routeDetailsType);
    const warehouse = $("#route-stats-warehouse")?.value || "all";
    if (warehouse && warehouse !== "all") params.set("warehouse", warehouse);
    state.routeDetails = await api(`/api/routes/details?${params.toString()}`);
    if (message) message.innerHTML = "";
    closeRouteReportDialog();
    renderRouteDetails();
    if (state.routeDetailsAutoExcel) window.open(routeDetailsExcelUrl(), "_blank", "noopener");
  } catch (error) {
    if (message) message.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
  }
}

async function loadRouteStatistics() {
  const message = $("#route-details-message");
  const { start, end, warehouse } = routeStatisticsRange();
  if (!start || !end) {
    if (message) message.innerHTML = `<div class="notice error">Válassz kezdő és záró dátumot.</div>`;
    return;
  }
  try {
    if (message) message.innerHTML = `<div class="notice">Túra statisztika betöltése...</div>`;
    const params = new URLSearchParams({ start, end, warehouse });
    state.routeStatistics = await api(`/api/routes/statistics?${params.toString()}`);
    if (message) message.innerHTML = "";
    renderRouteStatistics();
  } catch (error) {
    if (message) message.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
  }
}

async function loadRouteShiftReport() {
  const message = $("#route-details-message");
  const { month, courier, warehouse } = routeShiftReportRange();
  if (!month) {
    if (message) message.innerHTML = `<div class="notice error">Válassz hónapot.</div>`;
    return;
  }
  try {
    if (message) message.innerHTML = `<div class="notice">Futár műszak/kör statisztika betöltése...</div>`;
    const params = new URLSearchParams({ month, warehouse });
    if (courier) params.set("courier", courier);
    state.routeShiftReport = await api(`/api/routes/monthly-shift-report?${params.toString()}`);
    if (message) message.innerHTML = "";
    renderRouteShiftReport();
  } catch (error) {
    if (message) message.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
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
  const actionDisabled = "";
  const delayButton = `<button class="shift-delay-button" type="button" data-shift-index="${index}"${actionDisabled}>Kések a műszakból</button>`;
  const queueButton = `<button class="shift-queue-button" type="button" data-shift-index="${index}" data-shift-event="queued"${actionDisabled}>Sorba álltam</button>`;
  const returnButton = `<button class="shift-return-button" type="button" data-shift-index="${index}" data-shift-event="returned"${actionDisabled}>Visszaérkeztem</button>`;
  const vehicleText = vehicleLabel(item.vehicle);
  const isCourierHubSource = item.source === "courier_shift_overview";
  const hasMuszakpro = Boolean(item.muszakpro);
  const hasKiflis = Boolean(item.attendance || item.giriton);
  const sourceChip = (label, ok) => `<span class="source ${ok ? "ok" : "missing"}">${escapeHtml(label)} ${ok ? "✓" : "!"}</span>`;
  const actualStart = item.actualStartAt ? timeOnly(item.actualStartAt) : "";
  const hubMeta = isCourierHubSource && (actualStart || item.evaluation)
    ? `<div class="shift-meta">
        ${actualStart ? `<span>Tényleges kezdés: <strong>${escapeHtml(actualStart)}</strong></span>` : ""}
        ${item.evaluation ? `<span>Értékelés: <strong>${escapeHtml(item.evaluation)}</strong></span>` : ""}
      </div>`
    : "";
  return `<article class="shift-card ${!isCourierHubSource && (!hasMuszakpro || !hasKiflis) ? "has-missing-source" : ""}">
    <div class="shift-top">
      <div><p class="shift-time">${escapeHtml(item.start || "Időpont nélkül")}${end}</p><p class="shift-warehouse">${escapeHtml(item.warehouse || "Raktár nincs megadva")}</p></div>
      <span class="shift-state ${escapeHtml(item.status)}">${escapeHtml(item.statusLabel)}</span>
    </div>
    ${hubMeta}
    <div class="source-row">
      ${isCourierHubSource ? sourceChip("Courier Hub", true) : sourceChip("MűszakPro", hasMuszakpro)}
      ${isCourierHubSource ? "" : sourceChip("Kiflis", hasKiflis)}
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
  const button = $("#open-muszakpro-refresh");
  const hasActiveShift = Boolean(activeShift(state.data?.items || []));
  if (card) card.classList.toggle("hidden", hasActiveShift);
  if (hasActiveShift) {
    state.openMuszakproShifts = null;
    if (button) button.textContent = "Mutasd";
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
    if (button) button.textContent = "Mutasd";
    return;
  }

  target.classList.remove("hidden");
  if (button) button.textContent = "Elrejtés";
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
    await api(withPreviewCourier("/api/shifts/delay-alert"), {
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
    $("#warning-list").scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

async function sendShiftQueueCheckin(item, button) {
  if (!item) return;
  const originalText = button.textContent;
  const eventType = button.dataset.shiftEvent || "queued";
  button.disabled = true;
  button.textContent = "Mentés...";
  try {
    const payload = await api(withPreviewCourier("/api/shifts/queue-checkin"), {
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
  const payload = await api("/api/shifts/queue-status", { silentLoading: true });
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

function renderInvoiceRequirements(invoiceLocked = false) {
  const requirements = state.workflow?.invoiceRequirements || {};
  const cashOnlyInvoice = Boolean(requirements.cashOnlyInvoice);
  const cashAmount = Number(requirements.cashGrossHuf || 0);
  const requiresCashInvoice = Boolean(requirements.requiresCashInvoice) && cashAmount > 1000;
  const transferAmount = Number(requirements.transferGrossHuf || 0);
  const totalAmount = Number(requirements.totalGrossHuf || 0);
  const cashWrapper = $("#cash-invoice-submit-wrapper");
  const cashInput = $("#cash-invoice-submit-file");
  const cashLabel = $("#cash-invoice-submit-label");
  if (cashWrapper) cashWrapper.classList.toggle("hidden", !requiresCashInvoice);
  if (cashInput) {
    cashInput.required = requiresCashInvoice && !invoiceLocked;
    if (!requiresCashInvoice) cashInput.value = "";
  }
  if (cashLabel) {
    cashLabel.textContent = requiresCashInvoice
      ? `KP számla feltöltése (kötelező, ${formatHuf(cashAmount)})`
      : "KP számla feltöltése";
  }
  const mainInvoiceLabel = $("#invoice-submit-file-label");
  if (mainInvoiceLabel && cashOnlyInvoice) {
    mainInvoiceLabel.textContent = `KP számla feltöltése (${formatHuf(totalAmount || cashAmount)})`;
  } else if (mainInvoiceLabel) {
    mainInvoiceLabel.textContent = "Számla feltöltése (üresen az 5. lépésben ellenőrzött fájlt küldi be)";
  }
  const grossInput = $("#gross-amount");
  const grossLabel = $("#gross-amount-label");
  if (grossLabel) grossLabel.textContent = cashOnlyInvoice ? "KP-számla bruttó összege (Ft)" : "Átutalásos számla bruttó összege (Ft)";
  const expectedMainAmount = cashOnlyInvoice ? totalAmount || cashAmount : transferAmount;
  if (grossInput && expectedMainAmount) {
    grossInput.placeholder = formatHuf(expectedMainAmount);
  }
  return { requiresCashInvoice, cashAmount, transferAmount, totalAmount };
}

function workflowQuery() {
  const params = new URLSearchParams({ month: state.workflowMonth });
  if (state.workflowProcess) params.set("process", state.workflowProcess);
  if (state.user?.canPreviewCouriers && state.workflowPreviewCourierId) {
    params.set("courier", state.workflowPreviewCourierId);
  }
  params.set("_", String(Date.now()));
  return params.toString();
}

function workflowProcessQuery() {
  const params = new URLSearchParams({ month: state.workflowMonth });
  if (state.user?.canPreviewCouriers && state.workflowPreviewCourierId) {
    params.set("courier", state.workflowPreviewCourierId);
  }
  params.set("_", String(Date.now()));
  return params.toString();
}

function workflowMonthsQuery() {
  const params = new URLSearchParams();
  if (state.user?.canPreviewCouriers && state.workflowPreviewCourierId) {
    params.set("courier", state.workflowPreviewCourierId);
  }
  params.set("_", String(Date.now()));
  return params.toString();
}

function updateWorkflowMonthControl() {
  const input = $("#workflow-month");
  if (!input) return;
  const months = [...new Set(state.workflowMonths.map((item) => item.month).filter(Boolean))];
  const optionMonths = months.length ? [...months] : [state.workflowMonth].filter(Boolean);
  if (isAdminPreviewMode() && state.workflowMonth && !optionMonths.includes(state.workflowMonth)) {
    optionMonths.unshift(state.workflowMonth);
  }
  if (input.tagName === "SELECT") {
    const currentValue = state.workflowMonth || optionMonths[0] || "";
    input.innerHTML = optionMonths.map((month) => (
      `<option value="${escapeHtml(month)}" ${month === currentValue ? "selected" : ""}>${escapeHtml(formatMonthLabel(month))}</option>`
    )).join("");
  } else {
    input.value = state.workflowMonth;
    if (months.length) {
      input.min = months[months.length - 1];
      input.max = months[0];
    } else {
      input.removeAttribute("min");
      input.removeAttribute("max");
    }
  }
  input.value = state.workflowMonth;
  input.disabled = Boolean(state.workflowMonthLocked && months.length <= 1 && !isAdminPreviewMode());
  input.title = input.disabled
    ? "A hónapot az admin által publikált elszámolás rögzíti."
    : "";
}

async function ensureWorkflowMonths(options = {}) {
  const previewKey = previewCourierValue();
  if (!options.force && state.workflowMonthsLoadedFor === previewKey && state.workflowMonths.length) {
    updateWorkflowMonthControl();
    return;
  }
  const payload = await api(`/api/workflow/months?${workflowMonthsQuery()}`, { silentLoading: true });
  state.workflowMonths = payload.months || [];
  state.workflowMonthLocked = Boolean(payload.locked);
  state.workflowMonthsLoadedFor = previewKey;
  const visibleMonths = state.workflowMonths.map((item) => item.month).filter(Boolean);
  if (visibleMonths.length) {
    if (!visibleMonths.includes(state.workflowMonth)) {
      state.workflowMonth = payload.defaultMonth || visibleMonths[0];
      state.workflowProcess = "";
      state.workflow = null;
      state.checkedInvoiceFile = null;
      state.checkedInvoiceMonth = null;
    }
  } else if (payload.defaultMonth) {
    state.workflowMonth = payload.defaultMonth;
  }
  updateWorkflowMonthControl();
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

function canUseAdminWorkflowActions() {
  return Boolean(state.user?.canPreviewCouriers && state.workflowPreviewCourierId);
}

function renderAdminWorkflowActions() {
  const panel = $("#workflow-admin-actions");
  if (!panel) return;
  if (!canUseAdminWorkflowActions()) {
    panel.classList.add("hidden");
    panel.innerHTML = "";
    return;
  }
  const viewedUser = state.workflow?.viewingAs || {};
  const uploadMonths = adminInvoiceUploadMonths();
  const selectedUploadMonth = uploadMonths.includes(state.workflowMonth) ? state.workflowMonth : uploadMonths[0];
  panel.classList.remove("hidden");
  panel.innerHTML = `
    <div class="process-title">
      <span class="step-code">ADM</span>
      <div>
        <h3>Admin műveletek</h3>
        <p>${escapeHtml(viewedUser.username || state.workflowPreviewCourierId)} folyamatát a futár nevében lehet lezárni.</p>
      </div>
    </div>
    <div class="bulk-action-grid">
      <button class="secondary admin-workflow-action" type="button" data-action="settlement">Elszámolás elfogadása</button>
      <button class="secondary admin-workflow-action" type="button" data-action="tig">TIG elfogadása</button>
      <button class="secondary admin-workflow-action" type="button" data-action="invoice_submit">Számlafeltöltés jóváhagyása</button>
      <button class="secondary admin-workflow-action" type="button" data-action="invoice_check">Számlaellenőrzés jóváhagyása</button>
      <button class="secondary admin-workflow-action" type="button" data-action="invoice_payment">Kifizetés lezárása</button>
      <button class="primary admin-workflow-action" type="button" data-action="all">Minden lezárása</button>
    </div>
    <form id="admin-invoice-upload-form" class="process-form two-column admin-inline-form">
      <label>Számla hónap
        <select name="month">
          ${uploadMonths.map((month) => `<option value="${escapeHtml(month)}" ${month === selectedUploadMonth ? "selected" : ""}>${escapeHtml(formatMonthLabel(month))}</option>`).join("")}
        </select>
      </label>
      <label>Számlaszám<input name="invoice_number" autocomplete="off" /></label>
      <label>Bruttó összeg (Ft)<input name="gross_amount" type="number" min="0" step="1" /></label>
      <label>Megjegyzés<input name="note" autocomplete="off" placeholder="Admin feltöltés oka" /></label>
      <label class="full-width">Számla feltöltése<input name="invoice_file" type="file" accept="application/pdf,image/png,image/jpeg" required /></label>
      <button class="primary full-width" type="submit">Számla feltöltése a futár nevében</button>
    </form>
    <div id="admin-invoice-upload-result"></div>
  `;
}

function documentList(documents) {
  if (!documents.length) return `<div class="empty-card">Ehhez a hónaphoz még nincs feltöltött dokumentum.</div>`;
  return `<div class="document-list">${documents.map((document) => `
    <div class="document-row">
      <div><strong>${escapeHtml(document.title || document.file_name)}</strong><small>${escapeHtml(document.file_name)} · ${Number(document.file_size || 0).toLocaleString("hu-HU")} bájt</small></div>
      <a class="download-link" href="${escapeHtml(withPreviewCourier(document.downloadUrl || "#"))}">Letöltés</a>
    </div>`).join("")}</div>`;
}

function documentPreviewList(documents, courierId = "") {
  if (!documents.length) return documentList(documents);
  return `<div class="document-preview-list">
    ${documents.map((document) => {
      const baseUrl = document.downloadUrl || "#";
      const resourceUrl = new URL(baseUrl, window.location.origin);
      if (courierId) resourceUrl.searchParams.set("courier", courierId);
      else {
        const previewCourier = previewCourierValue();
        if (previewCourier && !resourceUrl.searchParams.has("courier")) resourceUrl.searchParams.set("courier", previewCourier);
      }
      const url = `${resourceUrl.pathname}${resourceUrl.search}`;
      resourceUrl.searchParams.set("inline", "true");
      const previewUrl = `${resourceUrl.pathname}${resourceUrl.search}`;
      const mime = String(document.mime_type || document.mimeType || "").toLowerCase();
      const fileName = String(document.file_name || document.fileName || "");
      const canPreview = mime.includes("pdf") || /\.(pdf)$/i.test(fileName) || mime.startsWith("image/") || /\.(png|jpe?g|webp|gif)$/i.test(fileName);
      return `<article class="document-preview-card">
        <div class="document-row">
          <div><strong>${escapeHtml(document.title || fileName)}</strong><small>${escapeHtml(fileName)} · ${Number(document.file_size || 0).toLocaleString("hu-HU")} bájt</small></div>
          <a class="download-link" href="${escapeHtml(url)}">Letöltés</a>
        </div>
        ${canPreview ? `<button class="secondary" type="button" aria-expanded="false" data-document-preview-url="${escapeHtml(previewUrl)}" data-document-preview-title="${escapeHtml(document.title || fileName)}" data-document-preview-type="${mime.startsWith("image/") || /\.(png|jpe?g|webp|gif)$/i.test(fileName) ? "image" : "pdf"}">Megtekintés</button>
          <div data-document-preview-panel></div>` : `<div class="empty-card">Ehhez a fájltípushoz nincs beágyazott előnézet.</div>`}
      </article>`;
    }).join("")}
  </div>`;
}

function closeDocumentPreview(panel) {
  panel.previewController?.abort();
  if (panel.previewObjectUrl) URL.revokeObjectURL(panel.previewObjectUrl);
  panel.previewObjectUrl = null;
  panel.replaceChildren();
}

async function loadDocumentPdfPage(panel, url, pageNumber = 1) {
  panel.previewController?.abort();
  const controller = new AbortController();
  panel.previewController = controller;
  if (panel.previewObjectUrl) URL.revokeObjectURL(panel.previewObjectUrl);
  panel.previewObjectUrl = null;
  panel.innerHTML = '<div class="empty-card">PDF-oldal betöltése…</div>';
  try {
    const resource = new URL(url, window.location.origin);
    resource.searchParams.set("preview_page", String(pageNumber));
    const response = await fetch(`${resource.pathname}${resource.search}`, {credentials: "same-origin", signal: controller.signal});
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(typeof error.detail === "string" ? error.detail : `Az előnézet nem tölthető be (${response.status}).`);
    }
    if (!response.headers.get("content-type")?.startsWith("image/")) throw new Error("Az előnézethez a szerver frissítése szükséges.");
    const blob = await response.blob();
    if (controller.signal.aborted) return;
    const pages = Math.max(1, Number(response.headers.get("X-PDF-Pages")) || 1);
    panel.previewObjectUrl = URL.createObjectURL(blob);
    panel.innerHTML = `<div class="pdf-preview-toolbar">
      <button type="button" class="secondary" data-pdf-page="${pageNumber - 1}" ${pageNumber <= 1 ? "disabled" : ""}>Előző oldal</button>
      <span>${pageNumber} / ${pages}. oldal</span>
      <button type="button" class="secondary" data-pdf-page="${pageNumber + 1}" ${pageNumber >= pages ? "disabled" : ""}>Következő oldal</button>
    </div><img class="pdf-preview-page" alt="PDF ${pageNumber}. oldal" />`;
    panel.querySelector("img").src = panel.previewObjectUrl;
    panel.querySelectorAll("[data-pdf-page]").forEach(button => button.addEventListener("click", () => {
      loadDocumentPdfPage(panel, url, Number(button.dataset.pdfPage));
    }));
  } catch (error) {
    if (controller.signal.aborted) return;
    panel.innerHTML = `<div class="notice error">${escapeHtml(error.message || "A PDF-előnézet nem tölthető be.")}</div>`;
  }
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-document-preview-url]");
  if (!button) return;
  const list = button.closest(".document-preview-list");
  const panel = button.closest(".document-preview-card").querySelector("[data-document-preview-panel]");
  const wasOpen = Boolean(panel.firstElementChild);
  list.querySelectorAll("[data-document-preview-panel]").forEach(closeDocumentPreview);
  list.querySelectorAll("[data-document-preview-url]").forEach(item => { item.textContent = "Megtekintés"; item.setAttribute("aria-expanded", "false"); });
  if (wasOpen) return;
  const url = button.dataset.documentPreviewUrl;
  const title = button.dataset.documentPreviewTitle || "Dokumentum";
  const link = document.createElement("a");
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener";
  link.className = "download-link";
  link.textContent = "Megnyitás külön lapon";
  panel.append(link);
  const content = document.createElement("div");
  panel.append(content);
  // Keep the render state on the panel so closing it cancels the active request.
  if (button.dataset.documentPreviewType === "image") {
    const media = document.createElement("img");
    media.alt = title;
    media.style.maxWidth = "100%";
    media.src = url;
    content.append(media);
  } else {
    panel.previewController = {abort: () => closeDocumentPreview(content)};
    loadDocumentPdfPage(content, url);
  }
  button.textContent = "Előnézet bezárása";
  button.setAttribute("aria-expanded", "true");
});

function documentArchiveQuery() {
  const params = new URLSearchParams();
  if (state.user?.canPreviewCouriers && state.workflowPreviewCourierId) {
    params.set("courier", state.workflowPreviewCourierId);
  }
  params.set("_", String(Date.now()));
  return params.toString();
}

function documentMonthKey(document) {
  const month = String(document.document_month || document.documentMonth || "").slice(0, 7);
  if (month) return month;
  return String(document.uploaded_at || document.uploadedAt || document.created_at || "").slice(0, 7) || "ismeretlen";
}

function documentMonthLabel(monthKey) {
  if (!/^\d{4}-\d{2}$/.test(monthKey)) return "Dátum nélküli dokumentumok";
  const date = new Date(`${monthKey}-01T00:00:00`);
  const label = new Intl.DateTimeFormat("hu-HU", { year: "numeric", month: "long" }).format(date);
  return label.charAt(0).toUpperCase() + label.slice(1);
}

function documentTypeLabel(documentType) {
  const cleanType = String(documentType || "").toLowerCase();
  const baseType = cleanType.split("__")[0];
  const labels = {
    settlement: "Elszámolás",
    tig: "TIG",
    invoice: "Számla",
    invoice_submit: "Számla",
    invoice_check: "Számla ellenőrzés",
    invoice_payment: "Kifizetés",
    complaint_response: "Admin válasz",
  };
  return labels[baseType] || "Egyéb dokumentum";
}

function groupedDocumentArchive(documents = []) {
  const groups = new Map();
  documents.forEach((document) => {
    const key = documentMonthKey(document);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(document);
  });
  return [...groups.entries()]
    .sort(([left], [right]) => right.localeCompare(left))
    .map(([month, rows]) => ({
      month,
      label: documentMonthLabel(month),
      rows: rows.sort((a, b) => {
        const left = String(a.uploaded_at || a.uploadedAt || a.created_at || "");
        const right = String(b.uploaded_at || b.uploadedAt || b.created_at || "");
        return right.localeCompare(left);
      }),
    }));
}

function renderDocumentArchive(documents = []) {
  const groups = groupedDocumentArchive(documents);
  if (!groups.length) return `<div class="empty-card">Még nincs feltöltött dokumentum.</div>`;
  return `<div class="document-month-list">${groups.map((group) => `
    <section class="document-month-group">
      <h3>${escapeHtml(group.label)}</h3>
      <div class="document-list">${group.rows.map((document) => `
        <div class="document-row archive">
          <div>
            <span class="document-badge">${escapeHtml(documentTypeLabel(document.document_type))}</span>
            <strong>${escapeHtml(document.title || document.file_name || "Dokumentum")}</strong>
            <small>${escapeHtml(document.file_name || "")}${Number(document.file_size || 0) > 0 ? ` · ${Number(document.file_size || 0).toLocaleString("hu-HU")} bájt` : ""}${document.uploaded_at ? ` · ${new Date(document.uploaded_at).toLocaleDateString("hu-HU")}` : ""}</small>
          </div>
          ${document.downloadUrl ? `<a class="download-link" href="${escapeHtml(withPreviewCourier(document.downloadUrl))}">Letöltés</a>` : ""}
        </div>
      `).join("")}</div>
    </section>
  `).join("")}</div>`;
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
  target.innerHTML = renderDocumentArchive(state.documentArchive || []);
}

async function loadDocuments() {
  const target = $("#documents-list");
  if (target) target.innerHTML = `<div class="empty-card">Dokumentumok betöltése...</div>`;
  try {
    const payload = await api(`/api/documents?${documentArchiveQuery()}`);
    state.documentArchive = payload.documents || [];
    renderDocumentsSection();
  } catch (error) {
    if (target) target.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
  }
}

function complaintCanWithdraw(complaint) {
  const status = String(complaint?.status || "").trim().toLowerCase();
  const hasAdminAnswer = Boolean(
    String(complaint?.admin_response || "").trim()
    || String(complaint?.responded_at || "").trim()
  );
  return !state.workflow?.viewerReadOnly
    && Boolean(complaint?.id)
    && !["resolved", "closed", "deleted"].includes(status)
    && !hasAdminAnswer;
}

function complaintMessageHtml(message) {
  let text = String(message || "");
  const heading = "Automatikus számlaellenőrzési hiba:";
  if (text.includes(heading)) {
    // Previously saved errors used pipes instead of line breaks.
    const index = text.indexOf(heading);
    const introduction = text.slice(0, index).trim();
    const errors = text.slice(index + heading.length).trim().replace(/\s*\|\s*/g, "\n\n");
    text = [introduction, heading, errors].filter(Boolean).join("\n\n");
  }
  return escapeHtml(text);
}

function complaintList(complaints) {
  if (!complaints.length) return "";
  return `<div class="complaint-list">${complaints.map((complaint) => `
    <div class="complaint-row"><div><strong class="complaint-message">${complaintMessageHtml(complaint.message)}</strong><small>${escapeHtml(complaint.status)} · ${new Date(complaint.created_at).toLocaleString("hu-HU")}</small>${complaint.admin_response ? `<div class="notice">Admin válasza: ${escapeHtml(complaint.admin_response)}${complaint.responded_by || complaint.responded_at ? `<small>${escapeHtml(complaint.responded_by || "admin")} · ${complaint.responded_at ? new Date(complaint.responded_at).toLocaleString("hu-HU") : ""}</small>` : ""}</div>` : ""}</div>${complaintCanWithdraw(complaint) ? `<button class="secondary complaint-withdraw" type="button" data-complaint-id="${escapeHtml(complaint.id)}">Visszavonás</button>` : ""}</div>
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
  const visibleItems = (items || []).filter((item) => !item.hidden);
  if (!visibleItems.length) return `<div class="empty-card">Nincs bontott adat ehhez a kártyához.</div>`;
  return `<div class="financial-detail-list">${visibleItems.map((item) => `
    <div class="financial-detail-row">
      <div class="financial-detail-text">
        <strong>${escapeHtml(item.label)}</strong>
        <small>${escapeHtml(item.note || "")}</small>
      </div>
      <span>${formatFinancialValue(item)}</span>
    </div>
  `).join("")}</div>`;
}

function canEditFinancialCards() {
  return Boolean(state.user?.canViewSettlementDashboard && state.workflowPreviewCourierId && state.workflow?.financialBreakdown?.available);
}

function financialCardItemsForEdit(card = {}) {
  const items = (card.items || []).filter((item) => !item.hidden);
  if (items.length) return items;
  return [{
    key: `${card.key || "card"}_total`,
    label: card.label || "Összesen",
    amountHuf: Number(card.amountHuf || 0),
    amountKind: card.amountKind || "huf",
    note: card.note || "",
  }];
}

function renderFinancialCardActions(card, editing) {
  if (!canEditFinancialCards()) return "";
  if (card?.amountKind === "count") return "";
  return `<div class="financial-card-actions">
    ${editing
      ? `<button class="icon-button financial-save" type="button" title="Mentés" data-financial-save-card="${escapeHtml(card.key || "")}">✓</button>`
      : `<button class="icon-button financial-edit" type="button" title="Kártya szerkesztése" data-financial-edit-card="${escapeHtml(card.key || "")}">✎</button>`}
  </div>`;
}

function financialEditableRows(card = {}) {
  const items = financialCardItemsForEdit(card);
  return `<div class="financial-editor" data-financial-card-editor="${escapeHtml(card.key || "")}">
    <div class="financial-editor-head">
      <strong>Szerkeszthető tételek</strong>
      <button class="secondary" type="button" data-financial-add-item="${escapeHtml(card.key || "")}">+ Tétel</button>
    </div>
    <div class="financial-editor-rows">
      ${items.map((item, index) => `
        <div class="financial-editor-row" data-financial-edit-row>
          <input data-field="key" type="hidden" value="${escapeHtml(item.key || "")}" />
          <label>Tétel
            <input data-field="label" value="${escapeHtml(item.label || "")}" />
          </label>
          <label>Összeg
            <input data-field="amountHuf" type="number" step="1" value="${Number(item.amountHuf || 0)}" />
          </label>
          <label>Megjegyzés
            <input data-field="note" value="${escapeHtml(item.note || "")}" />
          </label>
          <input data-field="amountKind" type="hidden" value="${escapeHtml(item.amountKind || "huf")}" />
          <input data-field="deleted" type="hidden" value="false" />
          <button class="icon-button danger" type="button" title="Tétel törlése" data-financial-delete-row="${index}">×</button>
        </div>
      `).join("")}
    </div>
    <div class="financial-editor-note">A mentés a PWA és a devtest.py által is használt havi override táblába kerül.</div>
  </div>`;
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

function renderFinancialSnapshotRestore() {
  if (!canEditFinancialCards()) return "";
  const breakdown = state.workflow?.financialBreakdown || {};
  const month = breakdown.month || state.workflowMonth || "";
  const courierId = state.workflowPreviewCourierId || "";
  const key = `${month}|${courierId}`;
  const snapshots = state.financialSnapshotsLoadedFor === key ? state.financialSnapshots : [];
  return `<section class="financial-restore-panel">
    <div>
      <strong>Visszaállítás pénzügyi snapshotból</strong>
      <small>Ha rossz admin érték került be, itt egy korábbi mentett verzió tölthető vissza.</small>
    </div>
    <div class="financial-restore-actions">
      <button class="secondary" type="button" data-financial-load-snapshots="true">Snapshotok betöltése</button>
      <select id="financial-snapshot-select" ${snapshots.length ? "" : "disabled"}>
        ${snapshots.length
          ? snapshots.map((item) => `<option value="${escapeHtml(item.id)}">v${Number(item.version || 0)} · ${formatHuf(item.payableHuf || 0)} · ${escapeHtml(formatDateTime(item.createdAt || ""))}</option>`).join("")
          : `<option value="">Nincs betöltött snapshot</option>`}
      </select>
      <button class="danger secondary" type="button" data-financial-restore-snapshot="true" ${snapshots.length ? "" : "disabled"}>Visszaállítás</button>
    </div>
  </section>`;
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
  const displayCards = cards.filter((card) => {
    const key = String(card.key || "");
    const tone = String(card.tone || "");
    const label = String(card.label || "").trim().toLowerCase();
    return !["payable", "deductions"].includes(key)
      && tone !== "total"
      && label !== "teljes összeg";
  });
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
    ${renderFinancialSnapshotRestore()}
    <div class="financial-card-grid">
      ${displayCards.map((card) => {
        const editing = state.financialEditCardKey === String(card.key || "");
        return `
        <details class="financial-card ${editing ? "editing" : ""} ${escapeHtml(card.tone || "")} financial-card-${escapeHtml(card.key || "item")}" ${qualityDetailAttributes(card.key, state.workflow?.viewingAs?.courierId || previewCourierValue() || state.user?.courierId || "", state.workflowMonth)} ${editing || ["base", "tip", "compliance_bonus", "bonus_malus", "atm_effect", "loyalty_bonus", "corrections"].includes(card.key) ? "open" : ""}>
          <summary>
            <div class="financial-card-title">
              <span>${escapeHtml(card.label)}</span>
              ${card.note ? `<small>${escapeHtml(card.note)}</small>` : ""}
              ${card.overrideNote ? `<small>${escapeHtml(card.overrideNote)}</small>` : ""}
            </div>
            <div class="financial-card-summary-side">
              <strong>${formatFinancialValue(card)}</strong>
              ${renderFinancialCardActions(card, editing)}
            </div>
          </summary>
          ${editing ? financialEditableRows(card) : financialDetailRows(card.items || [])}
          ${qualityDetailsPlaceholder(card.key)}
        </details>
      `;
      }).join("")}
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

function financialEditorPayload(cardKey) {
  const editor = document.querySelector(`[data-financial-card-editor="${CSS.escape(cardKey)}"]`);
  if (!editor) return [];
  return [...editor.querySelectorAll("[data-financial-edit-row]")].map((row) => ({
    key: row.querySelector('[data-field="key"]')?.value || "",
    label: row.querySelector('[data-field="label"]')?.value || "",
    amountHuf: Number(row.querySelector('[data-field="amountHuf"]')?.value || 0),
    amountKind: row.querySelector('[data-field="amountKind"]')?.value || "huf",
    note: row.querySelector('[data-field="note"]')?.value || "",
    deleted: row.querySelector('[data-field="deleted"]')?.value === "true",
  })).filter((item) => item.label.trim());
}

async function saveFinancialCardOverride(cardKey) {
  const breakdown = state.workflow?.financialBreakdown || {};
  const card = (breakdown.cards || []).find((item) => String(item.key || "") === String(cardKey || ""));
  if (!card || !canEditFinancialCards()) return;
  try {
    const payload = await api("/api/admin/settlement-card-overrides", {
      method: "POST",
      body: JSON.stringify({
        month: breakdown.month || state.workflowMonth,
        courierId: state.workflowPreviewCourierId,
        cardKey: card.key || cardKey,
        cardLabel: card.label || "",
        items: financialEditorPayload(String(card.key || cardKey)),
      }),
      loadingMessage: "Kártya mentése...",
    });
    state.financialEditCardKey = "";
    if (payload.workflow) {
      state.workflow = payload.workflow;
      state.workflowProcesses = state.workflow.processes || state.workflowProcesses;
      renderWorkflowProcessPicker();
      renderWorkflow();
    } else {
      await loadWorkflow({ background: true });
    }
    showWorkflowMessage(`Kártya mentve: ${escapeHtml(formatHuf(payload.totalHuf || 0))}.`);
  } catch (error) {
    showWorkflowMessage(error.message, true);
  }
}

async function loadFinancialSnapshotsForRestore() {
  const breakdown = state.workflow?.financialBreakdown || {};
  const month = breakdown.month || state.workflowMonth;
  const courierId = state.workflowPreviewCourierId || "";
  if (!month || !courierId) return;
  try {
    const query = new URLSearchParams({ month, courierId });
    const payload = await api(`/api/admin/settlement-finance-snapshots?${query.toString()}`, {
      loadingMessage: "Snapshotok betöltése...",
    });
    state.financialSnapshots = payload.snapshots || [];
    state.financialSnapshotsLoadedFor = `${month}|${courierId}`;
    renderWorkflow();
    showWorkflowMessage(state.financialSnapshots.length ? "Snapshot lista betöltve." : "Nincs elérhető pénzügyi snapshot ehhez a futárhoz.");
  } catch (error) {
    showWorkflowMessage(error.message, true);
  }
}

async function restoreFinancialSnapshot() {
  const breakdown = state.workflow?.financialBreakdown || {};
  const month = breakdown.month || state.workflowMonth;
  const courierId = state.workflowPreviewCourierId || "";
  const select = $("#financial-snapshot-select");
  const snapshotId = select?.value || "";
  if (!month || !courierId || !snapshotId) return;
  try {
    const payload = await api("/api/admin/settlement-finance-snapshots/restore", {
      method: "POST",
      body: JSON.stringify({ month, courierId, snapshotId }),
      loadingMessage: "Snapshot visszaállítása...",
    });
    state.financialEditCardKey = "";
    if (payload.workflow) {
      state.workflow = payload.workflow;
      state.workflowProcesses = state.workflow.processes || state.workflowProcesses;
      renderWorkflowProcessPicker();
      renderWorkflow();
    } else {
      await loadWorkflow({ background: true });
    }
    showWorkflowMessage(`Pénzügyi snapshot visszaállítva: v${Number(payload.snapshotVersion || 0)} (${Number(payload.restoredRows || 0)} sor).`);
  } catch (error) {
    showWorkflowMessage(error.message, true);
  }
}

function addFinancialEditorRow(cardKey) {
  const editor = document.querySelector(`[data-financial-card-editor="${CSS.escape(cardKey)}"] .financial-editor-rows`);
  if (!editor) return;
  const key = `draft_${Date.now()}`;
  const row = document.createElement("div");
  row.className = "financial-editor-row";
  row.dataset.financialEditRow = "";
  row.innerHTML = `
    <input data-field="key" type="hidden" value="${escapeHtml(key)}" />
    <label>Tétel
      <input data-field="label" value="" placeholder="Új tétel neve" />
    </label>
    <label>Összeg
      <input data-field="amountHuf" type="number" step="1" value="0" />
    </label>
    <label>Megjegyzés
      <input data-field="note" value="Admin által hozzáadva" />
    </label>
    <input data-field="amountKind" type="hidden" value="huf" />
    <input data-field="deleted" type="hidden" value="false" />
    <button class="icon-button danger" type="button" title="Tétel törlése" data-financial-delete-row>×</button>
  `;
  editor.appendChild(row);
  row.querySelector('[data-field="label"]')?.focus();
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

function workflowTigDownloadUrl() {
  const params = new URLSearchParams(workflowQuery());
  if (state.user?.canPreviewCouriers) {
    const viewedCourier = String(state.workflow?.viewingAs?.courierId || "").trim();
    if (viewedCourier) params.set("courier", viewedCourier);
  }
  return `/api/workflow/tig.pdf?${params}`;
}

function renderTigBreakdown(tig = state.workflow?.tigBreakdown || {}, options = {}) {
  if (!tig.available) {
    return `<div class="notice">${escapeHtml(tig.message || "A TIG bontas meg nincs kesz.")}</div>`;
  }
  const tigDownloadUrl = options.downloadUrl || workflowTigDownloadUrl();
  const tigMonth = tig.month || options.month || state.workflowMonth;
  const tigIdentifier = tig.documentReference ? `${tigMonth} · ${tig.documentReference}` : tigMonth;
  const rows = (tig.rows || []).filter((row) => row.key !== "cash_deduction" && row.key !== "tig_cash_deduction");
  const transferRows = rows.filter((row) => row.key !== "cash_service");
  const cashRows = rows.filter((row) => row.key === "cash_service");
  const cashTotalHuf = cashRows.reduce((sum, row) => sum + Number(row.grossHuf || 0), 0);
  const tigRowNote = (row) => [
    row.note || "",
    row.performanceDate ? `Teljesítés: ${row.performanceDate}` : "",
    row.paymentDueDate ? `Kifizetés: ${row.paymentDueDate}` : "",
  ].filter(Boolean).join(" · ");
  const renderTigRows = (items) => `
    <div class="tig-table">
      <div class="tig-row head"><span>Tétel</span><span>Netto</span><span>ÁFA</span><span>Brutto</span></div>
      ${items.map((row) => `
        <div class="tig-row ${Number(row.grossHuf || 0) < 0 ? "deduction" : ""}">
          <span><strong>${escapeHtml(row.label || "")}</strong><small>${escapeHtml(tigRowNote(row))}</small></span>
          <span>${tigValue(row.netHuf)}</span>
          <span>${row.vatLabel ? escapeHtml(row.vatLabel) : tigValue(row.vatHuf)}</span>
          <span>${tigValue(row.grossHuf)}</span>
        </div>
      `).join("")}
    </div>
  `;
  const buyer = tig.buyer || {};
  const seller = tig.seller || {};
  const renderPartyBlock = (party, fallbackLabel) => party.name ? `
    <section class="tig-buyer-card">
      <span>${escapeHtml(party.label || fallbackLabel)}</span>
      <strong>${escapeHtml(party.name || "")}</strong>
      ${party.postalCity ? `<small>${escapeHtml(party.postalCity || "")}</small>` : ""}
      ${party.address ? `<small>${escapeHtml(party.address || "")}</small>` : ""}
      ${party.taxNumber ? `<small>Adószám: ${escapeHtml(party.taxNumber || "")}</small>` : ""}
      ${party.periodLabel ? `<small>Teljesítési időszak: ${escapeHtml(party.periodLabel)}</small>` : ""}
      ${party.performanceDate ? `<small>Teljesítés: ${escapeHtml(party.performanceDate)}</small>` : ""}
      ${party.paymentDueDate ? `<small>Fizetési határidő: ${escapeHtml(party.paymentDueDate)}</small>` : ""}
      ${party.note ? `<small>Megjegyzés: ${escapeHtml(party.note)}</small>` : ""}
    </section>
  ` : "";
  const buyerBlock = renderPartyBlock(buyer, "Vevő");
  const sellerBlock = renderPartyBlock(seller, "Eladó");
  const cashBuyerBlock = renderPartyBlock({ ...buyer, label: "Vevő - KP számla" }, "Vevő - KP számla");
  const cashSellerBlock = renderPartyBlock({ ...seller, label: "Eladó - KP számla" }, "Eladó - KP számla");
  return `
    <div class="tig-toolbar">
      <a class="download-link tig-download-link" href="${escapeHtml(tigDownloadUrl)}">TIG letöltése PDF-ben</a>
    </div>
    <section class="tig-total-card">
      <span>TIG végösszeg</span>
      <strong>${tigValue(tig.finalTotalHuf)}</strong>
      <small>${escapeHtml(tigIdentifier)}</small>
    </section>
    <div class="tig-party-grid">${buyerBlock}${sellerBlock}</div>
    ${transferRows.length ? renderTigRows(transferRows) : ""}
    ${cashRows.length && cashTotalHuf > 1000 ? `
      <section class="tig-cash-invoice">
        <div class="tig-cash-heading">
          <span>Külön KP számla szükséges</span>
          <strong>${tigValue(cashTotalHuf)}</strong>
          <em>Készpénzes teljesítés</em>
          <small>A KP tételt külön számlán kell kiállítani. Aznapi teljesítés, aznapi kifizetés, TAM.</small>
        </div>
        <div class="tig-party-grid">${cashBuyerBlock}${cashSellerBlock}</div>
        ${renderTigRows(cashRows)}
      </section>
    ` : ""}
  `;
}

function isExtraWorkflow() {
  return Boolean(state.workflow?.process);
}

function isKpInvoiceWorkflow() {
  return state.workflow?.processType === "kp_invoice";
}

function workflowCanShowTig() {
  return !isExtraWorkflow() || isKpInvoiceWorkflow();
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
  const tigVisibleData = action === "tig" && workflowCanShowTig() && (Boolean(tig.available) || documents.length > 0);
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
        ? `<div class="notice">${isKpInvoiceWorkflow() ? "Ez KP számla pótlási folyamat. A havi elszámolás helyett csak a KP TIG és a hozzá tartozó számlafeltöltés aktív." : "Ez egy egyéb folyamat. Itt nincs külön havi elszámolás vagy TIG; a következő teendő a számla feltöltése."}</div>`
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
  if (action === "tig" && workflowCanShowTig()) {
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
  if (isExtraWorkflow() && !workflowCanShowTig() && (firstActive?.key?.startsWith("settlement") || firstActive?.key?.startsWith("tig"))) {
    const invoiceStep = workflowStep("invoice_submit");
    if (!invoiceStep.locked && !invoiceStep.done) return "invoice-submit-panel";
  }
  const key = firstActive?.key || "";
  if (key.startsWith("settlement")) return "settlement-panel";
  if (key.startsWith("tig")) return "tig-panel";
  if (key === "invoice_submit") return "invoice-submit-panel";
  if (key === "invoice_check") return "invoice-check-panel";
  if (key === "invoice_payment") return "invoice-payment-panel";
  return "settlement-panel";
}

function showOnlyWorkflowPanel(panelId) {
  const docs = state.workflow?.documents || {};
  const settlementStep = workflowStep("settlement");
  const tigStep = workflowStep("tig");
  const showSettlement = !isExtraWorkflow() && (
    Boolean(state.workflow?.financialBreakdown?.available)
    || Boolean((docs.settlement || []).length)
    || Boolean(settlementStep && !settlementStep.locked)
  );
  const showTig = workflowCanShowTig() && (
    Boolean(state.workflow?.tigBreakdown?.available)
    || Boolean((docs.tig || []).length)
    || Boolean(tigStep && !tigStep.locked)
  );
  ["settlement-panel", "tig-panel", "invoice-submit-panel", "invoice-check-panel", "invoice-payment-panel"].forEach((id) => {
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
  renderAdminWorkflowActions();
  renderDocumentPanel("settlement", "Elszámolás és elfogadás", 1);
  renderDocumentPanel("tig", "TIG és elfogadás", 3);
  const readOnly = Boolean(state.workflow?.viewerReadOnly);
  const invoiceAlreadySubmitted = invoiceUploadBlockedByExistingDocument();
  const invoiceLocked = readOnly || (!invoiceUploadReopened() && Boolean(workflowStep("invoice_submit").locked)) || invoiceAlreadySubmitted;
  const invoiceRequirements = renderInvoiceRequirements(invoiceLocked);
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
  const paymentInfo = $("#invoice-payment-info");
  if (paymentInfo) {
    const paymentStep = workflowStep("invoice_payment");
    const paymentDone = Boolean(paymentStep.done) || workflowStatus("invoice_payment") === "done";
    const paymentOpen = workflowStatus("invoice_payment") === "open";
    paymentInfo.innerHTML = paymentDone
      ? `<div class="notice">A kifizetés lezárult.</div>`
      : paymentOpen && !paymentStep.locked
        ? `<div class="notice">Az elszámolás és a számla rendben van. A kifizetés adminisztráció alatt van.</div>`
        : `<div class="notice">A kifizetés a korábbi számla-lépések lezárása után válik aktívvá.</div>`;
  }
  const submitInfo = $("#invoice-submit-info");
  if (submitInfo) {
    submitInfo.innerHTML = `${previewNotice}${overrideNotice}${
      invoiceRequirements.requiresCashInvoice && !invoiceAlreadySubmitted
        ? `<div class="notice">Ennél a TIG-nél külön KP számla is szükséges (${escapeHtml(formatHuf(invoiceRequirements.cashAmount))}). A véglegesítés csak az átutalásos és a KP számla feltöltése után indul.</div>`
        : ""
    }${
      invoiceAlreadySubmitted ? `<div class="notice">A számla már beérkezett ehhez a folyamathoz, új feltöltés nem indítható.</div>` : ""
    }${complaintList(state.workflow?.complaints?.invoice_submit || [])}`;
  }
  $("#invoice-document-list").innerHTML = (state.workflow?.documents?.invoice || []).length
    ? `<div class="complaint-box"><strong>Korábban feltöltött számlák</strong>${documentList(state.workflow.documents.invoice)}</div>`
    : "";
  renderDocumentsSection();
  attachComplaintWithdrawHandlers();
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

async function loadWorkflow(options = {}) {
  const background = Boolean(options.background);
  if (state.workflowLoading) return;
  state.workflowLoading = true;
  const refreshButton = $("#workflow-refresh");
  if (refreshButton && !background) {
    refreshButton.disabled = true;
    refreshButton.textContent = "Frissítés…";
  }
  if (!background || !state.workflow) {
    state.workflow = waitingWorkflow();
    renderWorkflow();
    showWorkflowMessage("Folyamat betöltése…");
  }
  let loadingStage = "Elérhető hónapok lekérése";
  try {
    await ensureWorkflowMonths();
    loadingStage = "Futár havi folyamatának lekérése";
    state.workflow = await api(`/api/workflow?${workflowQuery()}`);
    state.workflowProcesses = state.workflow.processes || [{ id: "", label: "Havi folyamat" }];
    if (!state.workflowProcesses.some((process) => process.id === state.workflowProcess)) {
      state.workflowProcess = "";
      state.workflow = await api(`/api/workflow?${workflowQuery()}`);
      state.workflowProcesses = state.workflow.processes || [{ id: "", label: "Havi folyamat" }];
    }
    renderWorkflowProcessPicker();
    renderWorkflow();
    showWorkflowMessage("");
  } catch (error) {
    if (!background || !state.workflow) {
      state.workflow = waitingWorkflow();
      renderWorkflow();
      const errorMessage = isAdminPreviewMode()
        ? `Az admin előnézet betöltése sikertelen. Lépés: ${loadingStage}. Hiba: ${error?.message || "Ismeretlen betöltési hiba."} A megjelenített zárolások ideiglenesek, a mentett folyamat státuszai nem változtak.`
        : "Az elszámolás adatai jelenleg nem érhetők el. A folyamat várakozó állapotban marad; próbáld meg később frissíteni.";
      showWorkflowMessage(errorMessage, true);
    }
  } finally {
    state.workflowLoading = false;
    if (refreshButton && !background) {
      refreshButton.disabled = false;
      refreshButton.textContent = "Frissítés";
    }
  }
}

function toggleOpenMuszakproShifts() {
  const target = $("#open-muszakpro-list");
  const selectedDate = state.selectedDate || localDate();
  const isOpen = Boolean(
    target
      && !target.classList.contains("hidden")
      && state.openMuszakproShifts
      && state.openMuszakproShifts.date === selectedDate
  );
  if (isOpen) {
    state.openMuszakproShifts = null;
    renderOpenMuszakproShifts();
    return Promise.resolve();
  }
  return loadOpenMuszakproShifts();
}

function renderSettlementDashboardStatus(status = {}, courierId = "") {
  const text = escapeHtml(status.label || "Ismeretlen");
  const classes = `settlement-dashboard-status ${escapeHtml(status.tone || "muted")}`;
  if (!courierId) return `<span class="${classes}">${text}</span>`;
  return `<button type="button" class="${classes} settlement-dashboard-status-button" data-dashboard-change-status="${escapeHtml(courierId)}" aria-label="${escapeHtml(`Státusz módosítása: ${status.label || 'Ismeretlen'}`)}">${text}</button>`;
}

function openSettlementDashboardStatusEditor(courierId) {
  const row = (state.settlementDashboard?.rows || []).find(item => String(item.courierId) === String(courierId));
  if (!row) return;
  const month = state.settlementDashboardMonth || previousLocalMonth();
  const options = [
    ["settlement_wait", "Elszámolás elfogadásra vár"], ["tig_wait", "TIG-re vár"],
    ["tig_accept", "TIG elfogadásra vár"], ["invoice_upload", "Számlafeltöltésre vár"],
    ["invoice_check", "Számla ellenőrzésre vár"], ["payment_wait", "Kifizetésre vár"],
  ];
  document.querySelector("#monthly-status-editor")?.remove();
  const dialog = document.createElement("dialog");
  dialog.id = "monthly-status-editor";
  dialog.className = "monthly-status-editor";
  dialog.innerHTML = `<form><h3>Státusz módosítása</h3>
    <p>${escapeHtml(row.courierName)} · ${escapeHtml(formatMonthLabel(month))}</p>
    <p>Jelenlegi státusz: <strong>${escapeHtml(row.status?.label || "Ismeretlen")}</strong></p>
    <label>Új státusz<select name="target">${options.map(([key, label]) => `<option value="${key}" ${row.status?.label === label ? "selected" : ""}>${escapeHtml(label)}</option>`).join("")}</select></label>
    <label>Módosítás megjegyzése<textarea name="note" required placeholder="Miért kerül ebbe a státuszba?"></textarea></label>
    <div class="notice">Mentéskor a futár ehhez a havi folyamathoz tartozó nyitott reklamációi automatikusan lezárulnak. A módosítás megjegyzése kerül a lezárás indokába.</div>
    <div class="notice">Ez a futár havi folyamatát módosítja. A cél előtti lépéseket admin által teljesítettnek jelöli, a későbbieket visszalépteti. Az összeg nem változik. A kifizetést a Kifizetés fülön lehet lezárni vagy visszanyitni.</div>
    <div data-status-error role="alert"></div>
    <button type="button" class="secondary" data-recheck-latest-invoice>Ellenőrzés újrafuttatása</button>
    <div data-invoice-recheck-result aria-live="polite"></div>
    <button type="submit" class="primary">Státusz mentése</button>
    <button type="button" class="secondary" data-status-cancel>Mégse</button>
  </form>`;
  document.body.appendChild(dialog);
  dialog.querySelector("[data-status-cancel]").onclick = () => dialog.close();
  dialog.addEventListener("close", () => dialog.remove());
  dialog.querySelector("[data-recheck-latest-invoice]").addEventListener("click", async () => {
    const resultBox = dialog.querySelector("[data-invoice-recheck-result]");
    const buttons = [...dialog.querySelectorAll("button")];
    buttons.forEach(button => { button.disabled = true; });
    resultBox.className = "notice";
    resultBox.textContent = "A legújabb elszámolási számla ellenőrzése folyamatban...";
    try {
      const result = await api("/api/admin/settlement-dashboard/recheck-invoice", {
        method: "POST", body: JSON.stringify({month, courierId: String(courierId)}),
        loadingMessage: "A legújabb számla újraellenőrzése...",
      });
      const validation = result.validation || {};
      resultBox.className = validation.ok ? "notice" : "notice error";
      resultBox.innerHTML = `<strong>${validation.ok ? "Sikeres ellenőrzés." : "Az ellenőrzés hibát talált."}</strong>
        ${(result.documents || []).map(item => `<div>Ellenőrzött számla: ${escapeHtml(item.fileName || item.id)}</div>`).join("")}
        ${(validation.checks || []).filter(check => check.status === "error").map(check => `<div>${escapeHtml(check.title)}: ${escapeHtml(check.detail || "")}</div>`).join("")}
        ${result.paymentClosed ? `<div>A lezárt kifizetés állapota változatlan.</div>` : ""}
        ${validation.ok ? `<small>A havi folyamathoz tartozó nyitott reklamációk a státusz mentésekor automatikusan lezárulnak.</small>` : ""}`;
      delete state.settlementDashboardDetailCache[`${month}:${courierId}`];
      if (state.settlementDashboardPayment?.courierId === String(courierId)) state.settlementDashboardPayment = null;
      await loadSettlementDashboard();
      if (state.settlementDashboardExpandedCourierId === String(courierId)) await loadSettlementDashboardCourierDetail(courierId);
    } catch (exc) {
      resultBox.className = "notice error";
      resultBox.textContent = exc.message;
    } finally {
      buttons.forEach(button => { button.disabled = false; });
    }
  });
  dialog.querySelector("form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('[type="submit"]');
    const error = form.querySelector("[data-status-error]");
    const note = form.elements.note.value.trim();
    if (!note) return;
    button.disabled = true;
    error.textContent = "";
    try {
      await api("/api/admin/settlement-dashboard/status", {method:"POST",
        body:JSON.stringify({month, courierId:String(courierId), target:form.elements.target.value, note}),
        loadingMessage:"Státusz mentése..."});
      delete state.settlementDashboardDetailCache[`${month}:${courierId}`];
      if (state.settlementDashboardPayment?.courierId === String(courierId)) state.settlementDashboardPayment = null;
      dialog.close();
      await loadSettlementDashboard();
      if (state.settlementDashboardExpandedCourierId === String(courierId)) await loadSettlementDashboardCourierDetail(courierId);
    } catch (exc) {
      error.className = "notice error";
      error.textContent = exc.message;
      button.disabled = false;
    }
  });
  dialog.showModal();
}

function settlementDashboardStatusOptions(statusCounts = {}) {
  const preferred = [
    "Elszámolás készül",
    "Elszámolás",
    "Elszámolás elfogadásra vár",
    "TIG-re vár",
    "TIG elfogadásra vár",
    "Számlafeltöltésre vár",
    "Számla ellenőrzésre vár",
    "Kifizetésre vár",
    "Reklamáció",
    "Kifizetve",
  ];
  const extras = Object.keys(statusCounts || {}).filter((label) => !preferred.includes(label)).sort();
  return [...preferred, ...extras];
}

function renderSettlementStatusFilters(statusCounts = {}) {
  const active = String(state.settlementDashboardStatusFilter || "");
  const searching = Boolean(String(state.settlementDashboardQuery || "").trim());
  const options = settlementDashboardStatusOptions(statusCounts);
  return `<div class="settlement-dashboard-filter-panel">
    <div class="settlement-dashboard-filter-title">
      <strong>Áttekintés</strong>
      <small>${searching ? "Gyorskeresés aktív: a státuszszűrő most nem korlátozza a találatokat." : active ? `Aktív szűrés: ${escapeHtml(active)}` : "Nincs státuszszűrés: minden futár megjelenik."}</small>
    </div>
    <div class="settlement-dashboard-filter-grid">
      ${options.map((label) => {
        const count = Number(statusCounts?.[label] || 0);
        const isActive = active === label;
        return `<button class="settlement-dashboard-filter ${isActive ? "active" : ""}" type="button" data-settlement-status-filter="${escapeHtml(label)}">
          <span class="filter-dot"></span>
          <strong>${escapeHtml(label)}</strong>
          <small>${escapeHtml(formatCount(count))} db</small>
        </button>`;
      }).join("")}
    </div>
  </div>`;
}

function renderSettlementDashboardFlags(flags = []) {
  if (!flags.length) return "";
  return `<div class="settlement-dashboard-flags">
    ${flags.map((flag) => `
      <span class="settlement-dashboard-flag ${escapeHtml(flag.tone || "")}">${escapeHtml(flag.label || "")}</span>
    `).join("")}
  </div>`;
}

function settlementDashboardDetailTabs() {
  const tabs = [
    ["settlement", "Elszámolás"],
    ["tig", "TIG"],
    ["complaints", "Reklamáció"],
    ["payment", "Kifizetés"],
    ["documents", "Dokumentumok"],
  ];
  return `<div class="settlement-dashboard-tabs">
    ${tabs.map(([key, label]) => `<button class="${state.settlementDashboardExpandedTab === key ? "active" : ""}" type="button" data-settlement-dashboard-tab="${key}">${label}</button>`).join("")}
  </div>`;
}

function qualityDetailAttributes(card, courier, month) {
  if (!["delay_bonus", "compliance_bonus"].includes(card)) return "";
  return `data-quality-card="${escapeHtml(card)}" data-quality-courier="${escapeHtml(courier)}" data-quality-month="${escapeHtml(month)}"`;
}

function qualityDetailsPlaceholder(card) {
  if (!["delay_bonus", "compliance_bonus"].includes(card)) return "";
  return `<div data-quality-details><button class="secondary" type="button" data-quality-retry>${card === "compliance_bonus" ? "Műszakkésések és no-show napok" : "Címkésések napjai"}</button></div>`;
}

function renderSettlementQualityDetails(payload) {
  return `<div class="quality-detail-list">
    ${(payload.groups || []).map((group) => `<section><h4>${escapeHtml(group.label)} · ${Number(group.count || 0)} db</h4>
      ${(group.rows || []).length ? group.rows.map((row) => `<div class="quality-detail-row">
        <strong>${escapeHtml(row.date || "-")}</strong><span>${escapeHtml(row.label || "")}</span>
        <small>${escapeHtml(row.note || "")}</small></div>`).join("") : `<p>${Number(group.count || 0) > 0 ? "A havi összesítésben szerepel, de ehhez nincs mentett napi részlet." : "Nincs ilyen esemény a mentett adatokban."}</p>`}
    </section>`).join("")}
    ${payload.truncated ? `<div class="notice">Az első 200 érintett túra látható.</div>` : ""}
    <button class="secondary" type="button" data-quality-retry>Naplista frissítése</button>
  </div>`;
}

async function loadSettlementQualityDetails(details, force = false) {
  const card = details.dataset.qualityCard;
  const courier = details.dataset.qualityCourier;
  const month = details.dataset.qualityMonth;
  const target = details.querySelector("[data-quality-details]");
  if (!target || !courier || !month) return;
  const key = `${state.user?.username || ""}:${month}:${courier}:${card}`;
  const cache = state.settlementQualityDetailsCache;
  const cached = cache[key];
  if (!force && cached?.data && Date.now() - cached.loadedAt < 30000) {
    target.innerHTML = renderSettlementQualityDetails(cached.data);
    return;
  }
  if (cached?.loading) return;
  cache[key] = {loading:true};
  target.innerHTML = `<div class="empty-card">Napok betöltése...</div>`;
  try {
    const params = new URLSearchParams({month, courier, card});
    const data = await api(`/api/workflow/quality-details?${params}`, {silentLoading:true});
    cache[key] = {data, loadedAt:Date.now(), loading:false};
    if (target.isConnected) target.innerHTML = renderSettlementQualityDetails(data);
  } catch (error) {
    delete cache[key];
    if (target.isConnected) target.innerHTML = `<div class="notice error">${escapeHtml(error.message)}
      <button class="secondary" type="button" data-quality-retry>Újrapróbálás</button></div>`;
  }
}

document.addEventListener("click", (event) => {
  const retry = event.target.closest("[data-quality-retry]");
  const details = event.target.closest("details[data-quality-card]");
  if (!details) return;
  if (retry) {
    loadSettlementQualityDetails(details, true);
    return;
  }
  const summary = event.target.closest("summary");
  if (summary && summary.parentElement === details && !details.open) {
    setTimeout(() => { if (details.open) loadSettlementQualityDetails(details); }, 0);
  }
});

function settlementDashboardBreakdownPreview(workflow = {}) {
  const breakdown = workflow.financialBreakdown || {};
  if (!breakdown.available) return `<div class="empty-card">${escapeHtml(breakdown.message || "Nincs elszámolási bontás.")}</div>`;
  const cardOrder = [
    "base",
    "tip",
    "delay_bonus",
    "compliance_bonus",
    "address_bonus_kifli",
    "loyalty_bonus",
    "customer_rating",
    "kiflis_bonus_malus",
    "bonus_malus",
    "corrections",
    "atm_effect",
    "salary_advance",
    "insurance",
    "performance",
  ];
  const cards = (breakdown.cards || []).filter((card) => {
    const key = String(card.key || "");
    const label = String(card.label || "").trim().toLowerCase();
    return !["payable", "deductions"].includes(key) && label !== "teljes összeg";
  }).sort((left, right) => {
    const leftIndex = cardOrder.indexOf(String(left.key || ""));
    const rightIndex = cardOrder.indexOf(String(right.key || ""));
    return (leftIndex === -1 ? 999 : leftIndex) - (rightIndex === -1 ? 999 : rightIndex);
  });
  return `<div class="settlement-dashboard-mini-breakdown">
    <div class="settlement-dashboard-mini-total">
      <span>Kifizetendő</span>
      <strong>${escapeHtml(formatHuf(breakdown.totalPayableHuf || 0))}</strong>
    </div>
    ${cards.map((card) => `
      <details class="settlement-dashboard-mini-card" ${qualityDetailAttributes(card.key, state.settlementDashboardExpandedCourierId, state.settlementDashboardMonth || previousLocalMonth())}>
        <summary><span>${escapeHtml(card.label || "")}</span><strong>${formatFinancialValue(card)}</strong></summary>
        ${financialDetailRows(card.items || [])}
        ${qualityDetailsPlaceholder(card.key)}
      </details>
    `).join("")}
    <button class="secondary" type="button" data-settlement-dashboard-open-preview>Teljes admin előnézet megnyitása</button>
  </div>`;
}

function settlementDashboardEditorRows(workflow = {}) {
  return Array.isArray(workflow.editableFinanceRows) ? workflow.editableFinanceRows : [];
}

function settlementDashboardManualPreviewRow() {
  const month = state.settlementDashboardMonth || previousLocalMonth();
  const [year, monthNumber] = month.split("-").map(Number);
  const lastDay = new Date(year, monthNumber, 0).getDate();
  return `<div class="settlement-worksheet-manual-row" data-dashboard-editor-row>
    <label>Típus<select aria-label="Kézi tétel típusa">${["Bónusz", "Malus", "Korrekció +", "Korrekció −", "Ügyfélértékelés", "ATM levonás", "Egyéb kiadás"].map(label => `<option>${label}</option>`).join("")}</select></label>
    <label>Összeg (Ft)<input type="number" value="0" step="1" aria-label="Kézi tétel összege"></label>
    <label class="settlement-worksheet-note">Megjegyzés<input type="text" placeholder="A módosítás indoka" aria-label="Kézi tétel megjegyzése"></label>
    <label>Érvényes ettől<input type="date" value="${escapeHtml(month)}-01" aria-label="Érvényesség kezdete"></label>
    <label>Érvényes eddig<input type="date" value="${escapeHtml(month)}-${lastDay}" aria-label="Érvényesség vége"></label>
    <button class="secondary settlement-dashboard-editor-delete" type="button" data-dashboard-editor-delete aria-label="Kézi tétel eltávolítása">×</button>
  </div>`;
}

function settlementDashboardFinanceEditor(workflow = {}) {
  if (workflow.worksheetPilot
      && workflow.worksheetPilot.courierId === state.settlementDashboardExpandedCourierId
      && workflow.worksheetPilot.month === state.settlementDashboardMonth) {
    return settlementDashboardPilotFinanceEditor(workflow.worksheetPilot);
  }
  const rows = settlementDashboardEditorRows(workflow);
  const totals = new Set(["payable", "income", "deductions"]);
  if (rows.some(row => ["correction_income", "correction_deduction"].includes(row.key))) totals.add("correction");
  const values = rows.filter(row => !totals.has(row.key));
  const savedTotal = workflow.financialBreakdown?.totalPayableHuf ?? rows.find(row => row.key === "payable")?.amountHuf ?? 0;
  const tigTotal = workflow.tigBreakdown?.finalTotalHuf;
  return `<div class="settlement-dashboard-editor settlement-worksheet" data-visual-only-editor>
    <div class="settlement-dashboard-editor-head">
      <div><strong>Pénzügyi munkalap</strong><small>A mezők kipróbálhatók. A módosítások csak ezen a képernyőn látszanak, bezáráskor elvesznek.</small></div>
      <span class="settlement-dashboard-editor-badge">Vizuális előnézet</span>
    </div>
    <section class="settlement-worksheet-section">
      <h4>Pénzügyi értékek</h4>
      <table class="settlement-worksheet-table"><thead><tr><th>Tétel</th><th>Mentett érték</th><th>Új érték</th></tr></thead><tbody>
        ${values.map(row => `<tr><td><strong>${escapeHtml(row.label || row.key)}</strong><small>${escapeHtml(row.note || "")}</small></td>
          <td>${escapeHtml(row.amountKind === "count" ? `${formatCount(row.amountHuf || 0)} db` : formatHuf(row.amountHuf || 0))}</td>
          <td><label class="settlement-worksheet-value"><input type="number" value="${escapeHtml(String(row.amountHuf ?? 0))}" step="1" aria-label="${escapeHtml(row.label || row.key)} új értéke"><span>${row.amountKind === "count" ? "db" : "Ft"}</span></label></td></tr>`).join("") || `<tr><td colspan="3">Nincs szerkeszthető pénzügyi tétel.</td></tr>`}
      </tbody></table>
      <small class="settlement-dashboard-editor-help">Az összesített végösszegek külön, az előnézetben jelennek meg.</small>
    </section>
    <section class="settlement-worksheet-section">
      <div class="settlement-dashboard-editor-head"><div><h4>Kézi tételek</h4><small>Új módosítások tervezete. A meglévő összegek a fenti táblázatban láthatók.</small></div><button class="secondary" type="button" data-dashboard-editor-add>+ Új tétel</button></div>
      <div data-worksheet-manual-rows>${settlementDashboardManualPreviewRow()}</div>
    </section>
    <section class="settlement-worksheet-section"><label>Módosítás indoka<textarea placeholder="Mi változott és miért?" rows="2" aria-label="Módosítás indoka"></textarea></label></section>
    <section class="settlement-worksheet-section">
      <div class="settlement-worksheet-totals"><div><small>Mentett kifizetendő</small><strong>${escapeHtml(formatHuf(savedTotal))}</strong></div><div><small>Tervezett kifizetendő</small><strong>—</strong></div><div><small>Eltérés</small><strong>—</strong></div></div>
      <div class="settlement-worksheet-tig"><strong>TIG</strong><span>${tigTotal == null ? "A TIG összege ezen a nézeten még nincs betöltve." : `Mentett összeg: ${escapeHtml(formatHuf(tigTotal))}`}</span></div>
      <div class="settlement-dashboard-editor-actions"><button class="secondary" type="button" disabled>Előnézet számítása</button><button class="primary" type="button" disabled>Változások mentése</button></div>
      <small class="settlement-dashboard-editor-help">Az újraszámítás, mentés és TIG-módosítás ebben a vizuális változatban nem működik.</small>
    </section>
  </div>`;
}

function settlementDashboardPilotManualRow(row = {}) {
  const month = state.settlementDashboardMonth || previousLocalMonth();
  const firstDate = `${month}-01`;
  const lastDate = `${month}-${String(new Date(Number(month.slice(0, 4)), Number(month.slice(5, 7)), 0).getDate()).padStart(2, "0")}`;
  const id = row.id || `manual-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  const types = [["bonus", "Bónusz"], ["malus", "Malus"], ["correction_income", "Korrekció +"], ["correction_deduction", "Korrekció −"], ["customer_rating", "Ügyfélértékelés"], ["atm_deduction", "ATM levonás"], ["other_expense", "Egyéb kiadás"]];
  return `<div class="settlement-worksheet-manual-row" data-dashboard-editor-row data-manual-id="${escapeHtml(id)}">
    <label>Típus<select data-manual-field="type">${types.map(([key, label]) => `<option value="${key}" ${row.type === key ? "selected" : ""}>${label}</option>`).join("")}</select></label>
    <label>Összeg (Ft)<input type="number" min="0" step="1" data-manual-field="amountHuf" value="${escapeHtml(String(row.amountHuf ?? 0))}"></label>
    <label class="settlement-worksheet-note">Megjegyzés<input data-manual-field="note" value="${escapeHtml(row.note || "")}" placeholder="Miért jár ez a tétel?"></label>
    <label>Érvényes ettől<input type="date" data-manual-field="validFrom" value="${escapeHtml(row.validFrom || firstDate)}" min="${firstDate}" max="${lastDate}"></label>
    <label>Érvényes eddig<input type="date" data-manual-field="validTo" value="${escapeHtml(row.validTo || lastDate)}" min="${firstDate}" max="${lastDate}"></label>
    <button type="button" class="secondary settlement-dashboard-editor-delete" data-dashboard-editor-delete aria-label="Kézi tétel eltávolítása">×</button>
  </div>`;
}

function settlementDashboardPilotFinanceEditor(pilot) {
  return `<div class="settlement-dashboard-editor settlement-worksheet" data-pilot-worksheet data-snapshot-id="${escapeHtml(pilot.snapshotId)}" data-courier-id="${escapeHtml(pilot.courierId)}" data-month="${escapeHtml(pilot.month)}">
    <div class="settlement-dashboard-editor-head"><div><strong>Pénzügyi munkalap</strong><small>${escapeHtml(pilot.courierName || pilot.courierId)} · #${escapeHtml(pilot.courierId)} · ${escapeHtml(pilot.month)} · mentett verzió: v${escapeHtml(String(pilot.version))}</small></div><span class="settlement-dashboard-editor-badge">Szerkeszthető</span></div>
    <div class="notice">Csak ennek a futárnak a mentett tételeit módosítja. A mentés után ugyanaz az új verzió látszik a PWA-ban és a devtest.py-ban. A meglévő TIG PDF változatlan marad.</div>
    <section class="settlement-worksheet-section"><h4>Pénzügyi értékek</h4><small>A levonások negatív előjellel szerepelnek. A darabszám módosítása önmagában nem számolja újra a díjakat.</small>
      <table class="settlement-worksheet-table"><thead><tr><th>Tétel</th><th>Mentett alapérték</th><th>Új alapérték</th></tr></thead><tbody>${pilot.rows.map(row => `<tr><td><strong>${escapeHtml(row.label)}</strong><small>${escapeHtml(row.note || "")}</small></td><td>${escapeHtml(row.amountKind === "count" ? `${formatCount(row.amountHuf)} db` : formatHuf(row.amountHuf))}</td><td><label class="settlement-worksheet-value"><input type="number" step="1" data-worksheet-key="${escapeHtml(row.key)}" value="${escapeHtml(String(row.amountHuf))}" aria-label="${escapeHtml(row.label)} új értéke"><span>${row.amountKind === "count" ? "db" : "Ft"}</span></label></td></tr>`).join("")}</tbody></table>
    </section>
    <section class="settlement-worksheet-section"><div class="settlement-dashboard-editor-head"><div><h4>PWA kézi tételek</h4><small>Ezek az alapértékeken felüli módosítások. Egy sor eltávolítása csak ezt a sort veszi ki a tervezetből.</small></div><button type="button" class="secondary" data-dashboard-editor-add>+ Új tétel</button></div><div data-worksheet-manual-rows>${(pilot.manualRows || []).map(settlementDashboardPilotManualRow).join("")}</div>
    ${(pilot.existingManualRows || []).length ? `<details><summary>Korábbi kézi forrástételek (${pilot.existingManualRows.length})</summary><small>A mentett alapértékek már tartalmazhatják ezeket; nem adjuk hozzá újra.</small>${pilot.existingManualRows.map(row => `<p>${escapeHtml(row.note || row.adjustment_type)} · ${escapeHtml(formatHuf(row.amount_huf))}</p>`).join("")}</details>` : ""}</section>
    <section class="settlement-worksheet-section"><label>Módosítás indoka<textarea data-worksheet-note placeholder="Mi változott és miért?" rows="2"></textarea></label></section>
    <section class="settlement-worksheet-section"><div class="settlement-worksheet-totals"><div><small>Mentett kifizetendő</small><strong>${escapeHtml(formatHuf(pilot.savedTotal))}</strong></div><div><small>Tervezett kifizetendő</small><strong data-worksheet-total>—</strong></div><div><small>Eltérés</small><strong data-worksheet-delta>—</strong></div></div>
    <div class="settlement-worksheet-tig"><strong>TIG-bontás előnézete</strong><span data-worksheet-tig>—</span></div><div data-worksheet-changes></div>
    <div class="settlement-dashboard-editor-actions"><button type="button" class="secondary" data-worksheet-preview>Előnézet számítása</button><button type="button" class="primary" data-worksheet-commit disabled>Változások mentése</button></div><div data-worksheet-message role="status" aria-live="polite"></div></section>
  </div>`;
}

function readPilotWorksheet(editor) {
  return { month: editor.dataset.month, courierId: editor.dataset.courierId, snapshotId: editor.dataset.snapshotId,
    note: editor.querySelector("[data-worksheet-note]").value.trim(),
    rows: [...editor.querySelectorAll("[data-worksheet-key]")].map(input => ({key: input.dataset.worksheetKey, amountHuf: Number(input.value)})),
    manualRows: [...editor.querySelectorAll("[data-manual-id]")].map(row => {
      const value = key => row.querySelector(`[data-manual-field="${key}"]`).value;
      return {id: row.dataset.manualId, type: value("type"), amountHuf: Number(value("amountHuf")), note: value("note").trim(), validFrom: value("validFrom"), validTo: value("validTo")};
    }) };
}

function invalidatePilotWorksheet(editor) {
  if (!editor) return;
  editor.worksheetPreview = null;
  editor.querySelector("[data-worksheet-commit]").disabled = true;
  editor.querySelector("[data-worksheet-total]").textContent = "—";
  editor.querySelector("[data-worksheet-delta]").textContent = "—";
  editor.querySelector("[data-worksheet-tig]").textContent = "—";
  editor.querySelector("[data-worksheet-changes]").textContent = "";
  editor.querySelector("[data-worksheet-message]").textContent = "A módosításokhoz friss előnézet szükséges.";
}

async function submitPilotWorksheet(editor, commit) {
  if (state.settlementDashboardExpandedCourierId !== editor.dataset.courierId || state.settlementDashboardMonth !== editor.dataset.month) return;
  const payload = readPilotWorksheet(editor);
  const message = editor.querySelector("[data-worksheet-message]");
  if (!payload.note) { message.textContent = "A módosítás indoka kötelező."; return; }
  if (commit && (!editor.worksheetPreview || editor.worksheetPreview.payload !== JSON.stringify(payload))) {
    invalidatePilotWorksheet(editor); return;
  }
  const inputs = [...editor.querySelectorAll("input,select,textarea,button")];
  inputs.forEach(input => { input.disabled = true; });
  message.textContent = commit ? "Mentés folyamatban..." : "Előnézet számítása...";
  try {
    const result = await api(`/api/admin/settlement-worksheet/${commit ? "commit" : "preview"}`, {
      method: "POST", body: JSON.stringify({...payload, previewHash: commit ? editor.worksheetPreview.hash : ""}),
      loadingMessage: commit ? "Futár módosításainak mentése..." : "Futár előnézetének számítása...",
    });
    if (commit) {
      delete state.settlementDashboardDetailCache[`${payload.month}:${payload.courierId}`];
      state.settlementDashboardPayment = null;
      await loadSettlementDashboard();
      if (state.settlementDashboardExpandedCourierId === payload.courierId && state.settlementDashboardMonth === payload.month) {
        await loadSettlementDashboardCourierDetail(payload.courierId);
        const savedMessage = document.querySelector("[data-pilot-worksheet] [data-worksheet-message]");
        if (savedMessage) savedMessage.textContent = `Mentve: v${result.version}. A devtest.py nézetet frissítve ugyanez a mentés jelenik meg. A korábbi TIG PDF nem frissült.`;
      }
    } else {
      editor.worksheetPreview = {hash: result.previewHash, payload: JSON.stringify(payload)};
      editor.querySelector("[data-worksheet-total]").textContent = formatHuf(result.totals.payable_total);
      editor.querySelector("[data-worksheet-delta]").textContent = formatHuf(result.delta);
      editor.querySelector("[data-worksheet-tig]").textContent = `${formatHuf(result.tig.finalTotalHuf)} átutalás${result.tig.cashGrossHuf ? ` + ${formatHuf(result.tig.cashGrossHuf)} külön KP` : ""}`;
      editor.querySelector("[data-worksheet-changes]").innerHTML = result.changes.map(row => `<p>${escapeHtml(row.label)}: ${escapeHtml(formatHuf(row.before))} → ${escapeHtml(formatHuf(row.after))}</p>`).join("");
      message.textContent = "Előnézet kész. Még nem történt mentés.";
    }
  } catch (error) {
    message.textContent = error.message;
    if (!commit) editor.worksheetPreview = null;
  } finally {
    inputs.forEach(input => { input.disabled = false; });
    editor.querySelector("[data-worksheet-commit]").disabled = !editor.worksheetPreview;
  }
}

function settlementDashboardComplaintManager(complaints = []) {
  if (!complaints.length) return `<div class="empty-card">Nincs reklamáció ehhez a futárhoz.</div>`;
  return `<div class="settlement-dashboard-complaints">
    ${complaints.map((complaint) => `
      <article class="settlement-dashboard-complaint" data-dashboard-complaint-id="${escapeHtml(complaint.id || "")}">
        <div>
          <strong class="complaint-message">${complaintMessageHtml(complaint.message || "Reklamáció")}</strong>
          <small>${escapeHtml(complaint.document_type || complaint.documentType || "")} · ${escapeHtml(complaint.status || "new")} · ${complaint.created_at ? escapeHtml(new Date(complaint.created_at).toLocaleString("hu-HU")) : ""}</small>
        </div>
        <label>Státusz
          <select data-complaint-field="status">
            ${["new", "open", "in_progress", "resolved", "closed"].map((status) => `<option value="${status}" ${String(complaint.status || "") === status ? "selected" : ""}>${status}</option>`).join("")}
          </select>
        </label>
        <label>Admin válasz
          <textarea data-complaint-field="response" placeholder="Mit válaszolunk a futárnak?">${escapeHtml(complaint.admin_response || "")}</textarea>
        </label>
        <button class="primary" type="button" data-save-dashboard-complaint="${escapeHtml(complaint.id || "")}">Válasz mentése</button>
      </article>
    `).join("")}
  </div>`;
}

function settlementDashboardPaymentPanel(row) {
  const month = state.settlementDashboardMonth || previousLocalMonth();
  const loaded = state.settlementDashboardPayment;
  if (!loaded || loaded.courierId !== String(row.courierId) || loaded.month !== month) {
    return `<div class="empty-card">A havi kifizetési adatok még nincsenek betöltve.
      <button class="secondary" type="button" data-load-monthly-payment>Adatok betöltése</button></div>`;
  }
  if (loaded.loading) return `<div class="empty-card">Számlák és kifizetési adatok betöltése...</div>`;
  if (loaded.error) return `<div class="notice error">${escapeHtml(loaded.error)}
    <button class="secondary" type="button" data-load-monthly-payment>Újrapróbálás</button></div>`;
  const payment = loaded.data;
  const draft = state.settlementDashboardPaymentDrafts?.[`${month}:${row.courierId}`] || {};
  const table = (items) => `<div style="overflow-x:auto"><table><thead><tr><th>Tétel</th><th>Összeg</th></tr></thead><tbody>
    ${items.map((item) => `<tr><td>${escapeHtml(item.label || item.key || "")}</td><td>${escapeHtml(formatHuf(item.amountHuf))}</td></tr>`).join("")}
    </tbody></table></div>`;
  const check = payment.invoiceCheck || {};
  return `<div class="settlement-dashboard-tab-panel" data-monthly-payment-form>
    <strong>Havi kifizetés</strong>
    <small>Mentett elszámolás: v${escapeHtml(payment.snapshotVersion)} · ${escapeHtml(formatMonthLabel(month))}</small>
    ${payment.closed ? `<div class="notice">A havi kifizetés már lezárva.${payment.closedBy ? ` ${escapeHtml(payment.closedBy)}` : ""}</div>` : ""}
    ${payment.blockingReason ? `<div class="notice error">${escapeHtml(payment.blockingReason)}</div>` : ""}
    <label>Kedvezményezett<input readonly value="${escapeHtml(payment.recipientName || "")}"></label>
    <label>Bankszámlaszám<input readonly value="${escapeHtml(payment.bankAccount || "")}"></label>
    <label>Kifizetendő összeg<input readonly value="${escapeHtml(formatHuf(payment.amountHuf))}"></label>
    <label>Számlaszám<input data-monthly-payment-invoice value="${escapeHtml(draft.invoiceNumber ?? payment.invoiceNumber ?? "")}" ${payment.closed ? "disabled" : ""}></label>
    <label>Közlemény<input readonly data-monthly-payment-reference value="${escapeHtml(payment.paymentNote || "")}"></label>
    <strong>Feltöltött számlák</strong>
    ${documentPreviewList(payment.invoices || [], row.courierId)}
    <div class="notice">Számlaellenőrzés: ${escapeHtml(check.status === "done" ? "Jóváhagyva" : check.status === "open" ? "Ellenőrzésre vár" : "Nincs rögzítve")}
      ${check.status_note ? `<div style="white-space:pre-wrap">${escapeHtml(check.status_note)}</div>` : ""}</div>
    <details><summary>Összeg részletei</summary>${table(payment.breakdown || [])}</details>
    <details><summary>TIG részletei</summary>${table((payment.tigBreakdown?.rows || []).map((item) => ({label:item.label || item.key, amountHuf:item.grossHuf})))}
      <a class="download-link" href="/api/workflow/tig.pdf?month=${encodeURIComponent(month)}&courier=${encodeURIComponent(row.courierId)}">TIG PDF megnyitása</a></details>
    <label>Kifizetési megjegyzés<textarea data-monthly-payment-admin-note ${payment.closed ? "disabled" : ""}>${escapeHtml(draft.adminNote ?? payment.adminNote ?? "")}</textarea></label>
    <label>Kifizetés lezárási megjegyzés<textarea data-monthly-payment-note ${payment.closed ? "disabled" : ""}>${escapeHtml(payment.closed ? payment.closeNote : (draft.note ?? (payment.closeNote || `Kifizetve: ${formatHuf(payment.amountHuf)}`)))}</textarea></label>
    <small>A lezárás a már elvégzett kifizetést rögzíti, banki utalást nem indít.</small>
    <button class="primary" type="button" data-close-monthly-payment ${!payment.canClose ? "disabled" : ""}>Havi kifizetés lezárása</button>
    <label>Elutasítás / visszanyitás indoka<textarea data-monthly-payment-reject-note>${escapeHtml(draft.rejectNote || "")}</textarea></label>
    <label><input type="checkbox" data-monthly-payment-notify> E-mail értesítés a futárnak elutasításkor</label>
    <button class="secondary" type="button" data-reopen-monthly-payment>Havi kifizetés elutasítása / visszanyitás</button>
    <button class="secondary" type="button" data-load-monthly-payment>Kifizetési adatok frissítése</button>
  </div>`;
}

async function loadSettlementDashboardMonthlyPayment(courierId) {
  const month = state.settlementDashboardMonth || previousLocalMonth();
  const id = String(courierId || "");
  state.settlementDashboardPayment = {courierId:id, month, loading:true, data:null, error:""};
  renderSettlementDashboard();
  try {
    const params = new URLSearchParams({month, courier:id});
    const data = await api(`/api/admin/settlement-payment?${params}`, {silentLoading:true});
    if (state.settlementDashboardPayment?.courierId === id && state.settlementDashboardPayment?.month === month) {
      state.settlementDashboardPayment = {courierId:id, month, loading:false, data, error:""};
    }
  } catch (error) {
    if (state.settlementDashboardPayment?.courierId === id && state.settlementDashboardPayment?.month === month) {
      state.settlementDashboardPayment = {courierId:id, month, loading:false, data:null, error:error.message};
    }
  }
  renderSettlementDashboard();
}

function renderDashboardInvoiceIssue(row) {
  if (row.status?.label !== "Számla ellenőrzésre vár") return "";
  const check = row.invoiceCheck || {};
  const messages = [...new Set([check.note, ...(check.messages || [])].map(value => String(value || "").trim()).filter(Boolean))];
  const formatNote = value => escapeHtml(String(value).replace(/\s+\|\s+/g, "\n\n")).replace(/\r?\n/g, "<br>");
  return `<div class="notice error dashboard-invoice-issue" role="note">
    <strong>Számlaellenőrzés – mentett indok</strong>
    ${messages.length ? messages.map(message => `<p>${formatNote(message)}</p>`).join("")
      : `<p>Még nincs rögzített hibaindok. Ez a státusz önmagában nem jelenti, hogy a számla hibás; az adminellenőrzés még folyamatban lehet.</p>`}
  </div>`;
}

function settlementDashboardTigPanel(workflow, row) {
  const month = state.settlementDashboardMonth || previousLocalMonth();
  const accepted = workflow.states?.tig?.status === "done";
  const params = new URLSearchParams({month, courier: String(row.courierId)});
  const documents = workflow.documents?.tig || [];
  const content = workflow.tigBreakdown?.available
    ? renderTigBreakdown(workflow.tigBreakdown, {month, downloadUrl: `/api/workflow/tig.pdf?${params}`})
    : documents.length
      ? documentPreviewList(documents, row.courierId)
      : `<div class="notice">${escapeHtml(workflow.tigBreakdown?.message || "Ehhez a hónaphoz még nincs elkészített TIG.")}</div>`;
  return `<section class="process-card settlement-dashboard-tab-panel ${accepted ? "accepted" : ""}">
    <div class="process-title"><span class="step-code">3</span><div><h3>TIG és elfogadás</h3><p>A TIG tételes bontása, külön KP sorral.</p></div></div>
    ${content}
    ${accepted ? `<div class="accept-row done">A TIG-et elfogadtad.</div>` : `<div class="notice">A TIG még nincs elfogadva.</div>`}
  </section>`;
}

function renderSettlementDashboardExpanded(row) {
  const detail = state.settlementDashboardDetail || {};
  const workflow = detail.workflow || {};
  const currentTab = state.settlementDashboardExpandedTab || "settlement";
  const documents = [
    ...(workflow.documents?.settlement || []),
    ...(workflow.documents?.tig || []),
    ...(workflow.documents?.invoice || []),
  ];
  const complaints = [
    ...(workflow.complaints?.settlement || []),
    ...(workflow.complaints?.tig || []),
    ...(workflow.complaints?.invoice_submit || []),
    ...(workflow.complaints?.invoice_check || []),
  ];
  return `<article class="settlement-dashboard-expanded" data-expanded-courier-id="${escapeHtml(row.courierId || "")}">
    <div class="settlement-dashboard-expanded-head">
      <div>
        <strong>${escapeHtml(row.courierName || "Futár")}</strong>
        <small>#${escapeHtml(row.courierId || "-")} · ${escapeHtml(formatMonthLabel(state.settlementDashboardMonth))}</small>
      </div>
      <div class="settlement-dashboard-expanded-actions">
        ${renderSettlementDashboardStatus(row.status || {}, row.courierId)}
        <button class="icon-button settlement-dashboard-edit" type="button" data-settlement-dashboard-edit="${escapeHtml(row.courierId || "")}" aria-pressed="${state.settlementDashboardEditCourierId === String(row.courierId || "")}" title="Futár értékeinek szerkesztése" aria-label="Futár értékeinek szerkesztése"><span aria-hidden="true">✎</span><span>Szerkesztés</span></button>
      </div>
    </div>
    ${settlementDashboardDetailTabs()}
    ${renderDashboardInvoiceIssue(row)}
    ${detail.loading ? `<div class="empty-card">Futár részletek betöltése...</div>` : ""}
    ${detail.error ? `<div class="notice error">${escapeHtml(detail.error)}</div>` : ""}
    ${!detail.loading && !detail.error && currentTab === "settlement" ? (state.settlementDashboardEditCourierId === String(row.courierId || "") ? settlementDashboardFinanceEditor(workflow) : settlementDashboardBreakdownPreview(workflow)) : ""}
    ${!detail.loading && !detail.error && currentTab === "tig" ? settlementDashboardTigPanel(workflow, row) : ""}
    ${!detail.loading && !detail.error && currentTab === "complaints" ? `
      <div class="settlement-dashboard-tab-panel">
        <strong>Reklamációk</strong>
        ${settlementDashboardComplaintManager(complaints)}
      </div>
    ` : ""}
    ${currentTab === "payment" ? settlementDashboardPaymentPanel(row) : ""}
    ${!detail.loading && !detail.error && currentTab === "documents" ? `
      <div class="settlement-dashboard-tab-panel">
        <strong>Dokumentumok</strong>
        ${documentPreviewList(documents, row.courierId || "")}
      </div>
    ` : ""}
  </article>`;
}

function settlementDashboardVisibleRows(rows, query, statusFilter) {
  const normalize = value => String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase("hu-HU").replace(/#/g, "").trim();
  const words = normalize(query).split(/\s+/).filter(Boolean);
  if (words.length) {
    return rows.filter(row => {
      const text = normalize(`${row.courierName || ""} ${row.courierId || ""}`);
      return words.every(word => text.includes(word));
    });
  }
  return statusFilter ? rows.filter(row => String(row.status?.label || "") === statusFilter) : rows;
}

function renderSettlementDashboard() {
  const target = $("#settlement-dashboard-panel");
  if (!target) return;
  const payload = state.settlementDashboard;
  if (!payload) {
    target.innerHTML = `<div class="empty-card">Elszámolási dashboard betöltése...</div>`;
    return;
  }
  const rows = payload.rows || [];
  const summary = payload.summary || {};
  const statusCounts = {};
  rows.forEach((row) => {
    const label = String(row.status?.label || "Elszámolás készül");
    statusCounts[label] = (statusCounts[label] || 0) + 1;
  });
  const activeStatusFilter = String(state.settlementDashboardStatusFilter || "");
  const displayRows = settlementDashboardVisibleRows(rows, state.settlementDashboardQuery, activeStatusFilter);
  const hasSearch = Boolean(String(state.settlementDashboardQuery || "").trim());
  target.innerHTML = `
    <section class="settlement-dashboard-hero">
      <div>
        <span>Aktív elszámolási hónap</span>
        <strong>${escapeHtml(formatMonthLabel(payload.month || state.settlementDashboardMonth))}</strong>
        <small>${escapeHtml(shortDateTime(payload.updatedAt || "")) ? `Frissítve: ${escapeHtml(shortDateTime(payload.updatedAt || ""))}` : "DB-ből betöltött elszámolási állapot"}</small>
      </div>
      <div class="settlement-dashboard-hero-total">
        <span>Kifizetendő összesen</span>
        <strong>${escapeHtml(formatHuf(summary.totalPayableHuf || 0))}</strong>
        <small>${escapeHtml(formatCount(summary.couriers || rows.length || 0))} futár</small>
      </div>
    </section>
    <div class="settlement-quick-search">
      <label for="settlement-dashboard-search">Gyorskeresés az összes futár között</label>
      <div><input id="settlement-dashboard-search" type="search" value="${escapeHtml(state.settlementDashboardQuery || "")}" placeholder="Név vagy futár ID részlete…" autocomplete="off" aria-describedby="settlement-quick-search-hint" /><button type="button" class="secondary" data-settlement-clear-search ${!hasSearch ? 'disabled' : ''}>Törlés</button></div>
      <p id="settlement-quick-search-hint">${hasSearch ? 'A keresés a kiválasztott hónap összes futárában keres, a státuszszűrőtől függetlenül.' : 'Azonnali, részleges név- és ID-keresés. Ékezet nélkül is működik.'}</p>
    </div>
    ${renderSettlementStatusFilters(statusCounts)}
    <div class="settlement-dashboard-toolbar">
      <strong>${hasSearch ? "Keresési találatok" : "Futár elszámolások"}</strong>
      <span>${escapeHtml(formatCount(displayRows.length))} sor</span>
    </div>
    <div class="settlement-dashboard-list">
      ${displayRows.length ? displayRows.map((row) => `
        <div class="settlement-dashboard-row ${state.settlementDashboardExpandedCourierId === String(row.courierId || "") ? "active" : ""} ${(row.flags || []).some((flag) => settlementImportRuleText(flag.label || "") === "kiemelt figyeles") ? "highlighted" : ""}">
          <button class="settlement-dashboard-row-main" type="button" data-courier-id="${escapeHtml(row.courierId || "")}">
          <div>
            <strong>${escapeHtml(row.courierName || "Futár")}</strong>
            <small>#${escapeHtml(row.courierId || "-")}${row.warehouse ? ` · ${escapeHtml(row.warehouse)}` : ""}</small>
            ${renderSettlementDashboardFlags(row.flags || [])}
          </div>
          <div>
            ${renderSettlementDashboardStatus(row.status || {}, row.courierId)}
            <small>${escapeHtml(row.status?.detail || "")}</small>
          </div>
          <strong>${escapeHtml(formatHuf(row.totalPayableHuf || 0))}</strong>
          </button>
          <button class="icon-button settlement-dashboard-edit" type="button" data-settlement-dashboard-edit="${escapeHtml(row.courierId || "")}" aria-pressed="${state.settlementDashboardEditCourierId === String(row.courierId || "")}" title="Futár értékeinek szerkesztése" aria-label="Futár értékeinek szerkesztése"><span aria-hidden="true">✎</span><span>Szerkesztés</span></button>
        </div>
        ${state.settlementDashboardExpandedCourierId === String(row.courierId || "") ? renderSettlementDashboardExpanded(row) : renderDashboardInvoiceIssue(row)}
      `).join("") : `<div class="empty-card">${hasSearch ? "Nincs a keresésnek megfelelő futár ebben a hónapban." : activeStatusFilter ? "Nincs futár ebben a státuszban." : "Nincs futár a kiválasztott hónapban."}</div>`}
    </div>
  `;
}

const settlementDashboardDetailRequests = new Map();

async function loadSettlementDashboardCourierDetail(courierId, {includeTig = state.settlementDashboardExpandedTab === "tig"} = {}) {
  const cleanId = String(courierId || "").trim();
  if (!cleanId) return;
  const month = state.settlementDashboardMonth || previousLocalMonth();
  const cacheKey = `${month}:${cleanId}`;
  state.settlementDashboardExpandedCourierId = cleanId;
  const cached = state.settlementDashboardDetailCache?.[cacheKey];
  if (cached && (!includeTig || cached.tigLoaded)) {
    state.settlementDashboardDetail = { courierId: cleanId, loading: false, workflow: cached, error: "" };
    renderSettlementDashboard();
    return;
  }
  state.settlementDashboardDetail = { courierId: cleanId, loading: true, workflow: null, error: "" };
  renderSettlementDashboard();
  const requestKey = `${cacheKey}:${includeTig}`;
  let request = settlementDashboardDetailRequests.get(requestKey);
  const stillSelected = () => state.settlementDashboardExpandedCourierId === cleanId
    && (state.settlementDashboardMonth || previousLocalMonth()) === month;
  try {
    const params = new URLSearchParams({
      month,
      courier: cleanId,
      _: String(Date.now()),
    });
    if (includeTig) params.set("include_tig", "true");
    if (!request) {
      request = api(`/api/admin/settlement-dashboard/detail?${params}`, { silentLoading: true });
      settlementDashboardDetailRequests.set(requestKey, request);
    }
    const response = await request;
    const existing = state.settlementDashboardDetailCache[cacheKey];
    const workflow = existing?.tigLoaded && !response.tigLoaded ? existing : response;
    state.settlementDashboardDetailCache[cacheKey] = workflow;
    if (!stillSelected()) return;
    state.settlementDashboardDetail = { courierId: cleanId, loading: false, workflow, error: "" };
  } catch (error) {
    if (!stillSelected()) return;
    state.settlementDashboardDetail = { courierId: cleanId, loading: false, workflow: null, error: error.message };
  } finally {
    if (settlementDashboardDetailRequests.get(requestKey) === request) settlementDashboardDetailRequests.delete(requestKey);
  }
  renderSettlementDashboard();
}

async function loadSettlementDashboard() {
  const requestSeq = (state.settlementDashboardRequestSeq || 0) + 1;
  state.settlementDashboardRequestSeq = requestSeq;
  const target = $("#settlement-dashboard-panel");
  if (target && !state.settlementDashboard) target.innerHTML = `<div class="empty-card">Elszámolási dashboard betöltése...</div>`;
  const month = $("#settlement-dashboard-month")?.value || state.settlementDashboardMonth || previousLocalMonth();
  const query = $("#settlement-dashboard-search")?.value || state.settlementDashboardQuery || "";
  state.settlementDashboardMonth = month;
  state.settlementDashboardQuery = query;
  try {
    const params = new URLSearchParams({ month, _: String(Date.now()) });
    const payload = await api(`/api/admin/settlement-dashboard?${params}`);
    if (requestSeq !== state.settlementDashboardRequestSeq) return;
    state.settlementDashboard = payload;
    renderSettlementDashboard();
  } catch (error) {
    if (requestSeq !== state.settlementDashboardRequestSeq) return;
    if (target) target.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
  }
}

function renderSettlementImportSteps() {
  const steps = [
    [1, "Hónap", "Elszámolási hónap kiválasztása"],
    [2, "Excel", "Fájl feltöltése"],
    [3, "Konfigurátor", "Oszlopok kártyákhoz"],
    [4, "Validálás", "Ellenőrzés és betöltés"],
  ];
  return `<div class="settlement-import-stepper">
    ${steps.map(([index, title, detail]) => {
      const tone = state.settlementImportStep === index ? "active" : state.settlementImportStep > index ? "done" : "";
      return `<div class="settlement-import-step ${tone}">
        <span>${index}</span>
        <strong>${escapeHtml(title)}</strong>
        <small>${escapeHtml(detail)}</small>
      </div>`;
    }).join("")}
  </div>`;
}

const SETTLEMENT_IMPORT_CARD_TARGETS = [
  { key: "base", label: "Alapdíj", rule: "Túratípus + futár díj szabály" },
  { key: "tip", label: "Borravaló", rule: "Borravaló összegzés" },
  { key: "delay", label: "Késedelmi díj", rule: "Delay bonus szabály" },
  { key: "compliance", label: "Túramegfelelés", rule: "Compliance / hibamutató szabály" },
  { key: "stop_count", label: "Cím bónusz (Kifli)", rule: "Stop-count Bonus" },
  { key: "loyalty", label: "Lojalitás", rule: "Aktuális kör alapján" },
  { key: "customer_rating", label: "Ügyfélértékelési bónusz", rule: "Értékelés szabály" },
  { key: "kifli_adjustments", label: "Kiflis levonások / bónuszok", rule: "Kifli tétel besorolás" },
  { key: "jitt_adjustments", label: "JITT bónusz / malus", rule: "JITT tétel besorolás" },
  { key: "atm", label: "ATM hatás", rule: "ATM import / kézi KP" },
  { key: "correction", label: "Korrekció", rule: "Kézi / Excel korrekció" },
  { key: "payable", label: "Fizetendő", rule: "Összesítő kontroll" },
];

const SETTLEMENT_IMPORT_SHEET_GROUPS = [
  { key: "main_jit", label: "JIT túra alapadatok", rule: "Túrák, route type, rendelés, borravaló" },
  { key: "atm", label: "Wallet / ATM levonás", rule: "Wallet deducation / ATM hatás" },
  { key: "bonus_routes", label: "Bonus Routes", rule: "Külön bónusz útvonal lap" },
  { key: "penalties", label: "Penalties", rule: "Büntetés / levonás / malus sorok" },
  { key: "claims", label: "Claims of last month", rule: "Előző havi reklamáció / korrekció" },
  { key: "customer_rating", label: "Ügyfélértékelés", rule: "JITT courier ratings" },
  { key: "performance", label: "Teljesítmény mutatók", rule: "Delay / compliance indikátorok" },
  { key: "reference", label: "Referencia / nem elszámolás", rule: "Segédlap vagy kézi ellenőrzés" },
];

function settlementImportColumnId(sheetName, header) {
  return `${String(sheetName || "Munkalap")}::${String(header || "")}`;
}

function settlementImportSheetId(sheetName) {
  return String(sheetName || "Munkalap");
}

function settlementImportColumnsFromHeaders(headers = []) {
  return (headers || []).flatMap((sheet) => (sheet.headers || []).map((header) => ({
    id: settlementImportColumnId(sheet.sheetName, header),
    sheetName: sheet.sheetName || "Munkalap",
    header: String(header || ""),
  }))).filter((column) => column.header);
}

function settlementImportColumnSignature(columns = []) {
  return columns.map((column) => column.id).sort().join("|");
}

function settlementImportSheetsFromResult(result = {}) {
  const byName = new Map();
  (result.sheetNames || []).forEach((sheetName) => {
    const cleanName = settlementImportSheetId(sheetName);
    if (!byName.has(cleanName)) byName.set(cleanName, { id: cleanName, sheetName: cleanName });
  });
  (result.headers || []).forEach((sheet) => {
    const cleanName = settlementImportSheetId(sheet.sheetName);
    const current = byName.get(cleanName) || { id: cleanName, sheetName: cleanName };
    byName.set(cleanName, {
      ...current,
      columnCount: Number(sheet.columnCount || current.columnCount || 0),
      previewRows: Number(sheet.previewRows || current.previewRows || 0),
    });
  });
  (result.processing?.sheets || []).forEach((sheet) => {
    const cleanName = settlementImportSheetId(sheet.sheetName);
    const current = byName.get(cleanName) || { id: cleanName, sheetName: cleanName };
    byName.set(cleanName, {
      ...current,
      detectedType: sheet.targetTable || sheet.detectedType || "",
      status: sheet.status || "",
      acceptedRows: Number(sheet.acceptedRows || 0),
      rejectedRows: Number(sheet.rejectedRows || 0),
    });
  });
  return Array.from(byName.values()).sort((a, b) => a.sheetName.localeCompare(b.sheetName, "hu"));
}

function settlementImportSheetSignature(sheets = []) {
  return sheets.map((sheet) => sheet.id).sort().join("|");
}

function settlementImportRuleText(value = "") {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

function settlementImportAutoTargetForColumn(column) {
  const text = settlementImportRuleText(`${column.sheetName} ${column.header}`);
  const header = settlementImportRuleText(column.header);
  if (!header) return "";
  if (/\btip\b|\btips\b|borravalo|gratuity/.test(header)) return "tip";
  if (/\bdelay bonus\b|kesedel|\blate\b/.test(header)) return "delay";
  if (/compliance bonus|compliance|hibamutato|hibam/.test(header)) return "compliance";
  if (/stop count|stopcount|stop bonus|cim bonus|address bonus/.test(header)) return "stop_count";
  if (/rating|ertekeles|customer/.test(header)) return "customer_rating";
  if (/loyal/.test(header)) return "loyalty";
  if (/atm|wallet deduction|wallet deductions|cash|kp|keszpenz/.test(header)) return "atm";
  if (/jitt|jit bonus|malus/.test(text)) return "jitt_adjustments";
  if (/kifli|levonas|deduction|bonus routes/.test(text)) return "kifli_adjustments";
  if (/correction|korrekcio|manual/.test(header)) return "correction";
  if (/payable|fizetendo|total payable|osszesen|vegosszeg/.test(header)) return "payable";
  if (/route type|fixed rate|base rate|alapdij|turatipus|normal|express|region/.test(header)) return "base";
  if (/orders|routen|route count|stops|stop/.test(header)) return "stop_count";
  return "";
}

function settlementImportAutoGroupForSheet(sheet = {}) {
  const text = settlementImportRuleText(`${sheet.sheetName} ${sheet.detectedType}`);
  if (/jit_row|\bjit\b|all jit/.test(text)) return "main_jit";
  if (/atm_balance|wallet|atm|deducation|deduction/.test(text)) return "atm";
  if (/bonus_route|bonus routes/.test(text)) return "bonus_routes";
  if (/penalty|penalties|buntetes|levonas|malus/.test(text)) return "penalties";
  if (/claims|claim|last month|reklamacio|korrekcio/.test(text)) return "claims";
  if (/rating|ratings|courier ratings|ertekeles|customer/.test(text)) return "customer_rating";
  if (/performance|indicator|kesedelmi mutato|turamegfeleles/.test(text)) return "performance";
  return "";
}

function ensureSettlementImportAutoColumnConfig(columns = []) {
  const signature = settlementImportColumnSignature(columns);
  if (!signature || state.settlementImportColumnConfigTouched) return;
  const nextConfig = {};
  columns.forEach((column) => {
    const targetKey = settlementImportAutoTargetForColumn(column);
    if (!targetKey) return;
    nextConfig[targetKey] = [...(nextConfig[targetKey] || []), column.id];
  });
  if (state.settlementImportColumnConfigSignature === signature && JSON.stringify(state.settlementImportColumnConfig || {}) === JSON.stringify(nextConfig)) return;
  state.settlementImportColumnConfig = nextConfig;
  state.settlementImportColumnConfigSignature = signature;
}

function ensureSettlementImportAutoSheetConfig(sheets = []) {
  const signature = settlementImportSheetSignature(sheets);
  if (!signature || state.settlementImportSheetConfigTouched) return;
  const nextConfig = {};
  sheets.forEach((sheet) => {
    const groupKey = settlementImportAutoGroupForSheet(sheet);
    if (!groupKey) return;
    nextConfig[groupKey] = [...(nextConfig[groupKey] || []), sheet.id];
  });
  if (state.settlementImportSheetConfigSignature === signature && JSON.stringify(state.settlementImportSheetConfig || {}) === JSON.stringify(nextConfig)) return;
  state.settlementImportSheetConfig = nextConfig;
  state.settlementImportSheetConfigSignature = signature;
}

function settlementImportAssignedColumnIds() {
  return new Set(Object.values(state.settlementImportColumnConfig || {}).flat());
}

function settlementImportAssignedSheetIds() {
  return new Set(Object.values(state.settlementImportSheetConfig || {}).flat());
}

function settlementImportColumnById(columns, columnId) {
  return columns.find((column) => column.id === columnId) || null;
}

function settlementImportSheetById(sheets, sheetId) {
  return sheets.find((sheet) => sheet.id === sheetId) || null;
}

function renderSettlementImportColumnChip(column, extra = "") {
  return `<span class="settlement-import-column-chip ${extra}" draggable="true" data-settlement-column-id="${escapeHtml(column.id)}">
    <b>${escapeHtml(column.header)}</b>
    <small>${escapeHtml(column.sheetName)}</small>
  </span>`;
}

function renderSettlementImportSheetChip(sheet, extra = "") {
  const meta = [
    sheet.detectedType || "nincs cél tábla",
    `${formatCount(sheet.acceptedRows || 0)} sor`,
  ].filter(Boolean).join(" · ");
  return `<span class="settlement-import-column-chip settlement-import-sheet-chip ${extra}" draggable="true" data-settlement-sheet-id="${escapeHtml(sheet.id)}">
    <b>${escapeHtml(sheet.sheetName || "Munkalap")}</b>
    <small>${escapeHtml(meta)}</small>
  </span>`;
}

function renderSettlementImportSheetGrouping(result = {}) {
  const sheets = settlementImportSheetsFromResult(result);
  ensureSettlementImportAutoSheetConfig(sheets);
  const assignedIds = settlementImportAssignedSheetIds();
  const unassignedSheets = sheets.filter((sheet) => !assignedIds.has(sheet.id));
  if (!sheets.length) return "";
  return `<section class="settlement-import-sheet-grouper">
    <div class="settlement-import-header-title">
      <div>
        <span>Munkalap csoportosítás</span>
        <strong>${escapeHtml(formatCount(unassignedSheets.length))} szabad munkalap</strong>
      </div>
      <small>A teljes sheeteket tedd importcsoportba</small>
    </div>
    <div class="settlement-import-column-chip-list settlement-import-sheet-bank" data-settlement-sheet-group-key="">
      ${unassignedSheets.length
        ? unassignedSheets.map((sheet) => renderSettlementImportSheetChip(sheet)).join("")
        : `<em>Minden munkalap csoportba került.</em>`}
    </div>
    <div class="settlement-import-sheet-group-grid">
      ${SETTLEMENT_IMPORT_SHEET_GROUPS.map((group) => {
        const ids = state.settlementImportSheetConfig?.[group.key] || [];
        const assignedSheets = ids.map((id) => settlementImportSheetById(sheets, id)).filter(Boolean);
        return `<article class="settlement-import-config-card settlement-import-sheet-group" data-settlement-sheet-group-key="${escapeHtml(group.key)}">
          <div>
            <span>${escapeHtml(group.label)}</span>
            <strong>${escapeHtml(formatCount(assignedSheets.length))} munkalap</strong>
            <small>${escapeHtml(group.rule)}</small>
          </div>
          <div class="settlement-import-card-dropzone ${assignedSheets.length ? "has-items" : ""}" data-settlement-sheet-group-key="${escapeHtml(group.key)}">
            ${assignedSheets.length
              ? assignedSheets.map((sheet) => `
                <span class="settlement-import-column-chip settlement-import-sheet-chip assigned" draggable="true" data-settlement-sheet-id="${escapeHtml(sheet.id)}">
                  <b>${escapeHtml(sheet.sheetName)}</b>
                  <small>${escapeHtml(sheet.detectedType || "kézi csoport")}</small>
                  <button type="button" data-settlement-remove-sheet="${escapeHtml(sheet.id)}" aria-label="Munkalap eltávolítása">×</button>
                </span>
              `).join("")
              : `<em>Dobd ide a munkalapot</em>`}
          </div>
        </article>`;
      }).join("")}
    </div>
  </section>`;
}

function renderSettlementImportConfigurator(result = {}) {
  const columns = settlementImportColumnsFromHeaders(result.headers || []);
  ensureSettlementImportAutoColumnConfig(columns);
  const assignedIds = settlementImportAssignedColumnIds();
  const unassignedColumns = columns.filter((column) => !assignedIds.has(column.id));
  if (!columns.length) {
    return `<div class="empty-card">Nincs felismerhető oszlop a konfigurátorhoz.</div>`;
  }
  return `<div class="settlement-import-configurator">
    <section class="settlement-import-column-bank">
      <div class="settlement-import-header-title">
        <div>
          <span>Felismert Excel oszlopok</span>
          <strong>${escapeHtml(formatCount(unassignedColumns.length))} szabad oszlop</strong>
        </div>
        <small>Húzd át őket a megfelelő fő kártyára</small>
      </div>
      <div class="settlement-import-column-chip-list" data-settlement-card-key="">
        ${unassignedColumns.length
          ? unassignedColumns.map((column) => renderSettlementImportColumnChip(column)).join("")
          : `<em>Minden kiválasztott oszlop kártyára került.</em>`}
      </div>
    </section>
    <section class="settlement-import-card-config-grid">
      ${SETTLEMENT_IMPORT_CARD_TARGETS.map((card) => {
        const ids = state.settlementImportColumnConfig?.[card.key] || [];
        const assignedColumns = ids.map((id) => settlementImportColumnById(columns, id)).filter(Boolean);
        return `<article class="settlement-import-config-card" data-settlement-card-key="${escapeHtml(card.key)}">
          <div>
            <span>${escapeHtml(card.label)}</span>
            <strong>${escapeHtml(formatCount(assignedColumns.length))} oszlop</strong>
            <small>${escapeHtml(card.rule)}</small>
          </div>
          <div class="settlement-import-card-dropzone ${assignedColumns.length ? "has-items" : ""}" data-settlement-card-key="${escapeHtml(card.key)}">
            ${assignedColumns.length
              ? assignedColumns.map((column) => `
                <span class="settlement-import-column-chip assigned" draggable="true" data-settlement-column-id="${escapeHtml(column.id)}">
                  <b>${escapeHtml(column.header)}</b>
                  <small>${escapeHtml(column.sheetName)}</small>
                  <button type="button" data-settlement-remove-column="${escapeHtml(column.id)}" aria-label="Oszlop eltávolítása">×</button>
                </span>
              `).join("")
              : `<em>Dobd ide az oszlopot</em>`}
          </div>
        </article>`;
      }).join("")}
    </section>
  </div>`;
}

function renderSettlementImportHeaders(headers = []) {
  if (!headers.length) {
    return `<div class="empty-card">A preview nem talált megjeleníthető fejléceket.</div>`;
  }
  return `<div class="settlement-import-header-list">
    ${headers.map((sheet) => `
      <article class="settlement-import-header-card">
        <div class="settlement-import-header-title">
          <div>
            <span>Munkalap</span>
            <strong>${escapeHtml(sheet.sheetName || "Munkalap")}</strong>
          </div>
          <small>${escapeHtml(formatCount(sheet.columnCount || 0))} fejléc · ${escapeHtml(formatCount(sheet.previewRows || 0))} preview sor</small>
        </div>
        <div class="settlement-import-header-tags">
          ${(sheet.headers || []).length
            ? sheet.headers.map((header) => `<span>${escapeHtml(header)}</span>`).join("")
            : `<em>Nincs felismerhető fejléc</em>`}
        </div>
      </article>
    `).join("")}
  </div>`;
}

function renderSettlementImportProcessing(processing = {}) {
  if (!processing.status) return "";
  const ok = ["completed", "completed_with_warnings"].includes(String(processing.status || ""));
  return `<div class="settlement-import-processing ${ok ? "ok" : "warn"}">
    <div class="settlement-import-header-title">
      <div>
        <span>Feldolgozás</span>
        <strong>${escapeHtml(processing.status || "-")}</strong>
      </div>
      <small>${escapeHtml(formatCount(processing.acceptedRows || 0))} elfogadott · ${escapeHtml(formatCount(processing.rejectedRows || 0))} elutasított</small>
    </div>
    ${(processing.sheets || []).length ? `
      <div class="settlement-import-processing-list">
        ${(processing.sheets || []).map((sheet) => `
          <span>${escapeHtml(sheet.sheetName || "Munkalap")} → ${escapeHtml(sheet.targetTable || "-")} · ${escapeHtml(formatCount(sheet.acceptedRows || 0))} sor</span>
        `).join("")}
      </div>
    ` : ""}
    ${(processing.errors || []).length ? `
      <div class="settlement-import-processing-errors">
        ${(processing.errors || []).map((error) => `<small>${escapeHtml(error.code || "HIBA")}: ${escapeHtml(error.message || "")}</small>`).join("")}
      </div>
    ` : ""}
  </div>`;
}

function renderSettlementImportPublishedConfig(config = {}) {
  if (!config.sessionId) return "";
  return `<div class="settlement-import-published">
    <span>PWA forrás beállítva</span>
    <strong>${escapeHtml(formatMonthLabel(String(config.periodStart || "").slice(0, 7)))} · ${escapeHtml(config.calculationMode || "Excel")}</strong>
    <small>Session: ${escapeHtml(config.sessionId)} · Raktár: ${escapeHtml(config.warehouseLabel || "Összes")}</small>
  </div>`;
}

function renderSettlementImportValidation(validation = {}) {
  if (!validation || !Object.keys(validation).length) return "";
  const routeCounts = validation.routeCounts || {};
  const routeTypeSamples = validation.routeTypeSamples || {};
  const routeLabels = [
    ["normal", "Normál"],
    ["express", "Express"],
    ["regional", "Régiós"],
  ];
  const warehouses = ["BUD1", "BUD2"];
  const sample = validation.sampleCourier || {};
  const tig = validation.tigPreview || {};
  const baseRateBreakdown = sample.baseRateBreakdown || [];
  const bonusBreakdown = sample.bonusBreakdown || [];
  const reconciliation = validation.courierReconciliation || {};
  const reconciliationItems = reconciliation.items || [];
  const reconciliationPreviewItems = reconciliation.previewItems || [];
  return `<div class="settlement-import-validation">
    <div class="settlement-import-result-grid">
      <div><span>Futár összesen</span><strong>${escapeHtml(formatCount(validation.couriersTotal || 0))}</strong></div>
      <div><span>Összesítő sor</span><strong>${escapeHtml(formatCount(validation.summaryRows || 0))}</strong></div>
      <div><span>Kifizetendő összesen</span><strong>${escapeHtml(formatHuf(validation.payableTotalHuf || 0))}</strong></div>
    </div>
    <article class="settlement-import-reconciliation ${reconciliation.mismatchCount ? "warn" : "ok"}">
      <div class="settlement-import-header-title">
        <div>
          <span>Futár validáció</span>
          <strong>${reconciliation.mismatchCount ? "Eltérés van az Excel és Hub DB között" : "Excel és Hub DB egyezik"}</strong>
        </div>
        <small>${escapeHtml(formatCount(reconciliation.ok || 0))} / ${escapeHtml(formatCount(reconciliation.total || 0))} futár rendben</small>
      </div>
      <div class="settlement-import-reconciliation-stats">
        <small>Túraszám eltérés: <b>${escapeHtml(formatCount(reconciliation.routeMismatchCount || 0))}</b></small>
        <small>Túratípus eltérés: <b>${escapeHtml(formatCount(reconciliation.routeTypeMismatchCount || 0))}</b></small>
        <small>Borravaló eltérés: <b>${escapeHtml(formatCount(reconciliation.tipMismatchCount || 0))}</b></small>
        <small>Hiányzó Hub adat: <b>${escapeHtml(formatCount(reconciliation.missingSummaryCount || 0))}</b></small>
      </div>
      ${reconciliationPreviewItems.length ? `
        <div class="settlement-import-reconciliation-list">
          ${reconciliationPreviewItems.slice(0, 18).map((item) => {
            const excel = item.excel || {};
            const calculated = item.calculated || {};
            const ok = item.status === "ok";
            return `<div class="${ok ? "ok" : "warn"}">
              <strong>${escapeHtml(item.courierName || "Ismeretlen futár")} ${item.courierId ? `#${escapeHtml(item.courierId)}` : ""}</strong>
              <small>${escapeHtml((item.issues || []).join(", ") || "Rendben")}</small>
              <small>Excel: ${escapeHtml(formatCount(excel.total || 0))} túra (${escapeHtml(formatCount(excel.normal || 0))} normal, ${escapeHtml(formatCount(excel.express || 0))} express, ${escapeHtml(formatCount(excel.regional || 0))} régiós), ${escapeHtml(formatHuf(excel.tipHuf || 0))} borravaló</small>
              <small>Hub DB: ${escapeHtml(formatCount(calculated.routeCount || 0))} túra (${escapeHtml(formatCount(calculated.normal || 0))} normal, ${escapeHtml(formatCount(calculated.express || 0))} express, ${escapeHtml(formatCount(calculated.regional || 0))} régiós), ${escapeHtml(formatHuf(calculated.tipHuf || 0))} borravaló</small>
            </div>`;
          }).join("")}
        </div>
      ` : ""}
      ${reconciliationItems.length > reconciliationPreviewItems.length ? `<small class="settlement-import-reconciliation-note">További eltérések: ${escapeHtml(formatCount(reconciliationItems.length - reconciliationPreviewItems.length))}</small>` : ""}
    </article>
    <div class="settlement-import-route-checks">
      ${warehouses.map((warehouse) => {
        const counts = routeCounts[warehouse] || {};
        const samples = routeTypeSamples[warehouse] || {};
        return `<article>
          <span>${escapeHtml(warehouse)}</span>
          <strong>${escapeHtml(formatCount(counts.total || 0))} túra</strong>
          <div>
            ${routeLabels.map(([key, label]) => `<small>${escapeHtml(label)}: <b>${escapeHtml(formatCount(counts[key] || 0))}</b></small>`).join("")}
            ${Object.keys(samples).length ? `
              <em class="settlement-import-route-samples">
                ${Object.entries(samples).slice(0, 6).map(([label, count]) => `${escapeHtml(label)}: ${escapeHtml(formatCount(count || 0))}`).join(" · ")}
              </em>
            ` : ""}
          </div>
        </article>`;
      }).join("")}
    </div>
    ${sample.courierName ? `
      <div class="settlement-import-sample-grid">
        <article class="settlement-import-sample-card">
          <span>Első futár elszámolás minta</span>
          <strong>${escapeHtml(sample.courierName)} · #${escapeHtml(sample.courierId || "-")}</strong>
          <div class="settlement-import-sample-lines">
            <small>Túra: <b>${escapeHtml(formatCount(sample.routeCount || 0))}</b></small>
            <small>Rendelés: <b>${escapeHtml(formatCount(sample.orderCount || 0))}</b></small>
            <small>Alapdíj: <b>${escapeHtml(formatHuf(sample.baseHuf || 0))}</b></small>
            ${baseRateBreakdown.length ? `
              <div class="settlement-import-detail-list">
                ${baseRateBreakdown.map((item) => `
                  <small>
                    ${escapeHtml(item.label || "Túra")}:
                    <b>${escapeHtml(formatCount(item.count || 0))} db · ${escapeHtml(formatHuf(item.totalHuf || 0))}</b>
                  </small>
                  ${(item.rates || []).map((rate) => `
                    <small class="muted">Futár díj ${escapeHtml(formatHuf(rate.unitAmountHuf ?? rate.amountHuf ?? 0))} × ${escapeHtml(formatCount(rate.routeCount ?? rate.count ?? 0))} túra = ${escapeHtml(formatHuf(rate.totalHuf || 0))}</small>
                  `).join("")}
                `).join("")}
              </div>
            ` : ""}
            <small>Borravaló: <b>${escapeHtml(formatHuf(sample.tipHuf || 0))}</b></small>
            <small>Bónusz: <b>${escapeHtml(formatHuf(sample.bonusHuf || 0))}</b></small>
            ${bonusBreakdown.length ? `
              <div class="settlement-import-detail-list">
                ${bonusBreakdown.map((item) => `
                  <small>${escapeHtml(item.label || "Bónusz")}: <b>${escapeHtml(formatHuf(item.amountHuf || 0))}</b></small>
                `).join("")}
              </div>
            ` : ""}
            <small>Fizetendő: <b>${escapeHtml(formatHuf(sample.payableHuf || 0))}</b></small>
          </div>
        </article>
        <article class="settlement-import-tig-card">
          <span>TIG előnézet</span>
          <strong>${escapeHtml(formatHuf(tig.finalTotalHuf || 0))}</strong>
          <small>${escapeHtml(tig.taxLabel || "TIG bontás")}</small>
          <div class="settlement-import-tig-lines">
            ${(tig.rows || []).length ? (tig.rows || []).map((row) => `
              <small>${escapeHtml(row.label || "Tétel")} <b>${escapeHtml(formatHuf(row.grossHuf || 0))}</b></small>
            `).join("") : `<small>Nincs TIG sor az előnézethez.</small>`}
          </div>
        </article>
      </div>
    ` : ""}
  </div>`;
}

function renderSettlementImportConfig() {
  const target = $("#settlement-import-config-panel");
  if (!target) return;
  const step = state.settlementImportStep || 1;
  const result = state.settlementImportResult;
  const canFinish = Boolean(result?.ok);
  const importMismatchCount = Number(result?.validation?.courierReconciliation?.mismatchCount || 0);
  const canPublish = canFinish && importMismatchCount === 0;
  target.innerHTML = `
    ${renderSettlementImportSteps()}
    <div class="settlement-import-panel">
      ${step === 1 ? `
        <div class="settlement-import-copy">
          <p class="eyebrow">1. lépés</p>
          <h3>Válaszd ki az elszámolási hónapot</h3>
          <p class="muted">Ez a hónap lesz a feltöltés címkéje. A fájl tartalmát még csak nyersen töltjük be, nem számolunk belőle.</p>
        </div>
        <label>Elszámolási hónap
          <input id="settlement-import-month" type="month" value="${escapeHtml(state.settlementImportMonth || previousLocalMonth())}" />
        </label>
        <div class="settlement-import-actions">
          <button class="primary" type="button" data-settlement-import-action="next">Tovább</button>
        </div>
      ` : ""}
      ${step === 2 ? `
        <div class="settlement-import-copy">
          <p class="eyebrow">2. lépés</p>
          <h3>Excel fájl feltöltése</h3>
          <p class="muted">Ugyanaz a nyers betöltés indul el, mint a devtest importnál: munkalapok, sorok és oszlopok bekerülnek a raw import táblába.</p>
        </div>
        <label>Excel fájl
          <input id="settlement-import-file" type="file" accept=".xlsx,.xls,.xlsm" />
        </label>
        <div class="settlement-import-actions">
          <button class="secondary" type="button" data-settlement-import-action="back">Vissza</button>
          <button class="primary" type="button" data-settlement-import-action="upload" ${state.settlementImportUploading ? "disabled" : ""}>
            ${state.settlementImportUploading ? "Feltöltés..." : "Excel feltöltése"}
          </button>
        </div>
      ` : ""}
      ${step === 3 ? `
        <div class="settlement-import-copy">
          <p class="eyebrow">3. lépés</p>
          <h3>Oszlopok és fő kártyák összerendelése</h3>
          <p class="muted">A felismert Excel oszlopokat húzd át arra a fő kártyára, ahol később meg kell jelenniük vagy szabályt kell kapniuk.</p>
        </div>
        ${result?.ok ? `
          <div class="settlement-import-result-grid">
            <div><span>Hónap</span><strong>${escapeHtml(formatMonthLabel(result.month))}</strong></div>
            <div><span>Fájl</span><strong>${escapeHtml(result.sourceFileName || "-")}</strong></div>
            <div><span>Munkalap</span><strong>${escapeHtml(formatCount(result.sheetCount || 0))}</strong></div>
            <div><span>Betöltött sor</span><strong>${escapeHtml(formatCount(result.insertedRows || 0))}</strong></div>
          </div>
          ${renderSettlementImportHeaders(result.headers || [])}
          ${renderSettlementImportSheetGrouping(result)}
          ${renderSettlementImportConfigurator(result)}
        ` : `<div class="empty-card">Nincs még feltöltött Excel a konfigurátorhoz.</div>`}
        <div class="settlement-import-actions">
          <button class="secondary" type="button" data-settlement-import-action="back">Vissza</button>
          <button class="primary" type="button" data-settlement-import-action="next-validation" ${canFinish ? "" : "disabled"}>Tovább a validálásra</button>
        </div>
      ` : ""}
      ${step === 4 ? `
        <div class="settlement-import-copy">
          <p class="eyebrow">4. lépés</p>
          <h3>Validálás és betöltés</h3>
          <p class="muted">Itt látszik, hogy a feldolgozás sikerült-e, mit számoltunk ki, és az Excel-Hub ellenőrzés alapján betölthető-e PWA-ra.</p>
        </div>
        ${result?.ok ? `
          <div class="settlement-import-result-grid">
            <div><span>Hónap</span><strong>${escapeHtml(formatMonthLabel(result.month))}</strong></div>
            <div><span>Fájl</span><strong>${escapeHtml(result.sourceFileName || "-")}</strong></div>
            <div><span>Munkalap</span><strong>${escapeHtml(formatCount(result.sheetCount || 0))}</strong></div>
            <div><span>Betöltött sor</span><strong>${escapeHtml(formatCount(result.insertedRows || 0))}</strong></div>
          </div>
          ${renderSettlementImportProcessing(result.processing || {})}
          ${renderSettlementImportValidation(result.validation || {})}
          ${renderSettlementImportPublishedConfig(result.publishedConfig || {})}
        ` : `<div class="empty-card">Nincs még validált feltöltés.</div>`}
        <div class="settlement-import-actions">
          <button class="secondary" type="button" data-settlement-import-action="back">Vissza</button>
          ${result?.publishedConfig?.sessionId
            ? `<button class="primary" type="button" data-settlement-import-action="finish">Befejezés</button>`
            : `<button class="secondary danger" type="button" data-settlement-import-action="delete" ${canFinish ? "" : "disabled"}>Import törlése</button>
              <button class="secondary" type="button" data-settlement-import-action="refresh-validation" ${canFinish ? "" : "disabled"}>Validáció frissítése</button>
              <button class="primary" type="button" data-settlement-import-action="publish" ${canPublish ? "" : "disabled"}>Betöltés PWA-ra</button>`}
        </div>
      ` : ""}
    </div>
  `;
}

async function submitSettlementImport() {
  const fileInput = $("#settlement-import-file");
  const file = fileInput?.files?.[0];
  if (!file) {
    window.alert("Válassz ki egy Excel fájlt.");
    return;
  }
  state.settlementImportUploading = true;
  renderSettlementImportConfig();
  const formData = new FormData();
  formData.set("month", state.settlementImportMonth || previousLocalMonth());
  formData.set("excel_file", file);
  try {
    state.settlementImportResult = await api("/api/admin/settlement-imports/excel", {
      method: "POST",
      body: formData,
      loadingMessage: "Excel feltöltése...",
    });
    state.settlementImportColumnConfig = {};
    state.settlementImportColumnConfigSignature = "";
    state.settlementImportColumnConfigTouched = false;
    state.settlementImportSheetConfig = {};
    state.settlementImportSheetConfigSignature = "";
    state.settlementImportSheetConfigTouched = false;
    state.settlementImportStep = 3;
  } catch (error) {
    window.alert(error.message);
  } finally {
    state.settlementImportUploading = false;
    renderSettlementImportConfig();
  }
}

async function publishSettlementImport() {
  const sessionId = state.settlementImportResult?.sessionId;
  if (!sessionId) return;
  try {
    const payload = await api(`/api/admin/settlement-imports/${encodeURIComponent(sessionId)}/publish`, {
      method: "POST",
      body: JSON.stringify({ month: state.settlementImportMonth || previousLocalMonth(), process: "" }),
      loadingMessage: "PWA forrás beállítása...",
    });
    state.settlementImportResult = {
      ...(state.settlementImportResult || {}),
      publishedConfig: payload.publishedConfig,
    };
    state.settlementDashboard = null;
    renderSettlementImportConfig();
  } catch (error) {
    window.alert(error.message);
  }
}

async function refreshSettlementImportValidation() {
  const sessionId = state.settlementImportResult?.sessionId;
  if (!sessionId) return;
  try {
    const month = encodeURIComponent(state.settlementImportMonth || previousLocalMonth());
    const payload = await api(`/api/admin/settlement-imports/${encodeURIComponent(sessionId)}/validation?month=${month}`, {
      loadingMessage: "Validáció frissítése...",
    });
    state.settlementImportResult = {
      ...(state.settlementImportResult || {}),
      validation: payload.validation || {},
    };
    renderSettlementImportConfig();
  } catch (error) {
    window.alert(error.message);
  }
}

async function deleteSettlementImport() {
  const sessionId = state.settlementImportResult?.sessionId;
  if (!sessionId) return;
  if (!window.confirm("Biztosan törlöd ezt az import sessiont?")) return;
  try {
    await api(`/api/admin/settlement-imports/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
      loadingMessage: "Import törlése...",
    });
    state.settlementImportResult = null;
    state.settlementImportColumnConfig = {};
    state.settlementImportColumnConfigSignature = "";
    state.settlementImportColumnConfigTouched = false;
    state.settlementImportSheetConfig = {};
    state.settlementImportSheetConfigSignature = "";
    state.settlementImportSheetConfigTouched = false;
    state.settlementImportStep = 1;
    state.settlementDashboard = null;
    renderSettlementImportConfig();
  } catch (error) {
    window.alert(error.message);
  }
}

function openSettlementDashboardCourier(courierId) {
  const cleanId = String(courierId || "").trim();
  if (!cleanId) return;
  state.workflowMonth = state.settlementDashboardMonth || previousLocalMonth();
  state.workflowPreviewCourierId = cleanId;
  if (workflowPreviewCourierInput) workflowPreviewCourierInput.value = cleanId;
  if (statisticsPreviewCourierInput) statisticsPreviewCourierInput.value = cleanId;
  if (adminPreviewCourierInput) adminPreviewCourierInput.value = cleanId;
  if ($("#route-details-courier")) $("#route-details-courier").value = cleanId;
  state.workflowProcess = "";
  state.workflowMonthsLoadedFor = "";
  state.workflowMonths = [];
  state.workflow = null;
  state.checkedInvoiceFile = null;
  state.checkedInvoiceMonth = null;
  setAdminPreviewStatus(`Előnézet aktív: ${cleanId}`);
  showSection("settlement");
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

async function completeWorkflowAsAdmin(action) {
  if (!canUseAdminWorkflowActions()) return;
  const actionLabel = {
    settlement: "elszámolást",
    tig: "TIG-et",
    invoice_submit: "számlafeltöltést",
    invoice_check: "számlaellenőrzést",
    invoice_payment: "kifizetést",
    all: "teljes folyamatot",
  }[action] || "műveletet";
  if (action === "all" && !window.confirm("Biztosan lezárod a teljes folyamatot a futár nevében?")) return;
  showWorkflowMessage(`Admin művelet mentése: ${actionLabel}...`);
  try {
    const payload = await api(withPreviewCourier(`/api/admin/workflow/${encodeURIComponent(action)}/complete`), {
      method: "POST",
      body: JSON.stringify({ month: state.workflowMonth, process: state.workflowProcess }),
    });
    state.workflow = payload.workflow;
    renderWorkflow();
    showWorkflowMessage("Admin művelet rögzítve.");
  } catch (error) {
    showWorkflowMessage(error.message, true);
  }
}

async function uploadInvoiceAsAdmin(form) {
  if (!canUseAdminWorkflowActions()) return;
  const submitButton = form.querySelector('button[type="submit"]');
  if (submitButton) submitButton.disabled = true;
  const data = new FormData(form);
  data.set("process", state.workflowProcess || "");
  const uploadedMonth = String(data.get("month") || state.workflowMonth);
  showWorkflowMessage("Admin számlafeltöltés folyamatban...");
  try {
    const payload = await api(withPreviewCourier("/api/admin/invoices/upload"), {
      method: "POST",
      body: data,
      loadingMessage: "Számla feltöltése...",
    });
    state.workflowMonth = uploadedMonth;
    state.workflow = payload.workflow;
    updateWorkflowMonthControl();
    renderWorkflow();
    showWorkflowMessage("A számla bekerült a futár dokumentumtárába, manuális ellenőrzésre vár.");
  } catch (error) {
    showWorkflowMessage(error.message, true);
    const result = $("#admin-invoice-upload-result");
    if (result) result.innerHTML = `<div class="empty-card error-state">${escapeHtml(error.message)}</div>`;
  } finally {
    if (submitButton) submitButton.disabled = false;
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

function attachComplaintWithdrawHandlers() {
  document.querySelectorAll(".complaint-withdraw").forEach((button) => {
    if (button.dataset.bound === "1") return;
    button.dataset.bound = "1";
    button.addEventListener("click", () => withdrawComplaint(button.dataset.complaintId));
  });
}

async function withdrawComplaint(complaintId) {
  if (!complaintId) return;
  showWorkflowMessage("Reklamáció visszavonása…");
  try {
    const payload = await api(`/api/workflow/complaints/${encodeURIComponent(complaintId)}/withdraw`, {
      method: "POST",
    });
    state.workflow = payload.workflow;
    renderWorkflow();
    showWorkflowMessage("A reklamációt visszavontad.");
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
    state.serviceWorkerRegistration = await navigator.serviceWorker.register(`/sw.js?${APP_VERSION}`);
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

function vehicleAssignmentLabel(item = {}) {
  return [item.licensePlate || "-", item.car || "", item.source || ""].filter(Boolean).join(" · ");
}

function vehicleAssignmentStatus(item = {}) {
  const date = String(item.date || "");
  const today = localDate();
  if (date === today) return "Mai kiosztás";
  return date ? "Előzmény" : "Nincs dátum";
}

function vehicleConfigForPlate(plate = "") {
  const normalized = String(plate || "").trim().toUpperCase();
  return (state.vehicleConfigurations || []).find((item) => String(item.licensePlate || "").trim().toUpperCase() === normalized) || null;
}

function vehicleAssignmentWarehouse(item = {}) {
  const configured = vehicleConfigForPlate(item.licensePlate);
  const direct = String(item.warehouse || "").trim().toUpperCase();
  if (direct === "BUD1" || direct === "BUD2") return direct;
  const configuredWarehouse = String(configured?.warehouseCode || "").trim().toUpperCase();
  if (configuredWarehouse === "BUD1" || configuredWarehouse === "BUD2") return configuredWarehouse;
  const carText = String(item.car || "").trim().toUpperCase();
  return ["BUD1", "BUD2"].includes(carText) ? carText : "";
}

function ensureVehicleDetailDialog() {
  let dialog = $("#vehicle-detail-dialog");
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.id = "vehicle-detail-dialog";
  dialog.className = "worker-shift-dialog vehicle-detail-dialog";
  dialog.innerHTML = `
    <div class="worker-shift-dialog-card vehicle-detail-dialog-card">
      <div class="worker-shift-dialog-head">
        <div>
          <span>Autó részletei</span>
          <strong data-vehicle-detail-title>Autó</strong>
          <small data-vehicle-detail-subtitle></small>
        </div>
        <button type="button" class="icon-button" data-vehicle-detail-close aria-label="Bezárás">×</button>
      </div>
      <div data-vehicle-detail-body></div>
      <div class="vehicle-detail-actions">
        <button class="primary" type="button" data-vehicle-condition-open>Felvétel / leadás rögzítése</button>
      </div>
      <section class="vehicle-condition-dialog-section hidden" data-vehicle-condition-wrap>
        <div class="vehicle-dialog-section-head">
          <div><span>ÁLLAPOTELLENŐRZÉS</span><strong>Autó felvétel / leadás</strong></div>
          <button class="secondary" type="button" data-vehicle-condition-close>Vissza</button>
        </div>
        <form id="vehicle-condition-form" class="process-form two-column">
          <label>Rendszám<input id="vehicle-license-plate" name="serial_number" autocomplete="off" required /></label>
          <label>Folyamat
            <select id="vehicle-event-type" name="event_type">
              <option value="handover">Felvétel</option>
              <option value="return">Leadás</option>
            </select>
          </label>
          <label>Autón látható sérülések száma
            <input id="vehicle-damage-count" name="damage_count" type="number" min="0" max="20" step="1" value="0" required />
          </label>
          <div class="vehicle-damage-help">Hibáról készíts fényképet, így az előző állapottal is összehasonlítható.</div>
          <div id="vehicle-damage-photo-fields" class="vehicle-damage-fields full-width"></div>
          <fieldset class="vehicle-checklist full-width">
            <legend>Állapot kérdőív</legend>
            <label>Olajszint<select name="oil_level_status" required><option value="ok">OK</option><option value="not_ok">NEM OK</option></select></label>
            <label>Hűtővíz szintje<select name="coolant_level_status" required><option value="ok">OK</option><option value="not_ok">NEM OK</option></select></label>
            <label>Guminyomás<select name="tire_pressure_status" required><option value="ok">OK</option><option value="not_ok">NEM OK</option></select></label>
            <label>Motorvédő lemez<select name="engine_cover_status" required><option value="ok">OK</option><option value="not_ok">NEM OK</option></select></label>
            <label>Lökhárító<select name="bumper_damage_status" required><option value="ok">OK</option><option value="not_ok">NEM OK</option></select></label>
            <label>Világító berendezések<select name="lights_status" required><option value="ok">OK</option><option value="not_ok">NEM OK</option></select></label>
          </fieldset>
          <label class="full-width">Megjegyzés<textarea id="vehicle-condition-note" name="note" rows="3" placeholder="Kiegészítő megjegyzés, ha szükséges"></textarea></label>
          <button class="primary full-width" type="submit">Autó állapot rögzítése</button>
        </form>
        <p id="vehicle-condition-message" class="updated-at" aria-live="polite"></p>
        <section id="vehicle-condition-history" class="device-history"></section>
      </section>
    </div>
  `;
  document.body.appendChild(dialog);
  dialog.querySelector("[data-vehicle-detail-close]")?.addEventListener("click", () => dialog.close());
  dialog.querySelectorAll("[data-vehicle-condition-close]").forEach((button) => {
    button.addEventListener("click", () => {
      dialog.querySelector("[data-vehicle-condition-wrap]")?.classList.add("hidden");
      dialog.querySelector("[data-vehicle-condition-open]")?.classList.remove("hidden");
    });
  });
  dialog.querySelector("[data-vehicle-condition-open]")?.addEventListener("click", () => {
    dialog.querySelector("[data-vehicle-condition-wrap]")?.classList.remove("hidden");
    dialog.querySelector("[data-vehicle-condition-open]")?.classList.add("hidden");
    dialog.querySelector("#vehicle-license-plate")?.focus();
  });
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  return dialog;
}

function openVehicleDetailDialog(item = {}) {
  const dialog = ensureVehicleDetailDialog();
  const config = vehicleConfigForPlate(item.licensePlate) || item;
  const plate = String(item.licensePlate || config.licensePlate || "-").trim();
  const warehouse = vehicleAssignmentWarehouse(item) || config.warehouseCode || "-";
  const assigned = item.driverName || "Szabad autó";
  dialog.querySelector("[data-vehicle-detail-title]").textContent = plate;
  dialog.querySelector("[data-vehicle-detail-subtitle]").textContent = `${warehouse} · ${assigned}`;
  dialog.querySelector("[data-vehicle-detail-body]").innerHTML = `
    <div class="vehicle-detail-summary">
      <div><span>Raktár</span><strong>${escapeHtml(warehouse)}</strong></div>
      <div><span>Kijelölt futár</span><strong>${escapeHtml(assigned)}</strong></div>
      <div><span>Műszak kezdete</span><strong>${escapeHtml(item.date && item.shiftStart ? `${item.date} ${item.shiftStart}` : "-")}</strong></div>
      <div><span>Műszak vége</span><strong>${escapeHtml(item.shiftEnd || "-")}</strong></div>
      <div><span>Állapot</span><strong>${escapeHtml(config.carStatusLabel || (item.date ? "Kiosztva" : "Szabad"))}</strong></div>
      <div><span>Autó</span><strong>${escapeHtml([config.brand, config.model, item.car].filter(Boolean).join(" ") || "Nincs típusadat")}</strong></div>
    </div>
    <div class="vehicle-detail-section">
      <div class="vehicle-dialog-section-head"><div><span>FELVÉTEL / LEADÁS</span><strong>Használati napló</strong></div><small>${escapeHtml(item.source || "Beosztás és élő adat")}</small></div>
      <div class="vehicle-detail-log"><span>Felvétel</span><strong>${escapeHtml(item.shiftStart ? `${item.date || ""} ${item.shiftStart}` : "Nincs adat")}</strong><span>Leadás</span><strong>Nincs rögzítve</strong></div>
    </div>
    <div class="vehicle-detail-section">
      <div class="vehicle-dialog-section-head"><div><span>ELLENŐRZÉS</span><strong>Korábbi állapotok</strong></div><small>${escapeHtml(config.conditionLabel || "Nincs állapotadat")}</small></div>
      <div class="vehicle-detail-note">A korábbi fotós ellenőrzések és az AI összehasonlítás a rögzítés után jelenik meg.</div>
    </div>
  `;
  const wrap = dialog.querySelector("[data-vehicle-condition-wrap]");
  wrap?.classList.add("hidden");
  dialog.querySelector("[data-vehicle-condition-open]")?.classList.remove("hidden");
  const form = dialog.querySelector("#vehicle-condition-form");
  form?.reset();
  const plateInput = dialog.querySelector("#vehicle-license-plate");
  if (plateInput) plateInput.value = plate;
  state.vehicleReports = [];
  dialog.showModal();
  loadVehicleReports();
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

function vehicleAssignmentRows(items = [], options = {}) {
  if (!items.length) return `<div class="empty-card">Nincs autó-hozzárendelés az adott időszakban.</div>`;
  if (options.interactive !== false) state.vehicleVisibleAssignments = items;
  return items.map((item) => `
    <article class="vehicle-assignment-row vehicle-assignment-card">
      <div>
        <span class="vehicle-row-label">Indulás</span>
        <strong>${escapeHtml(item.shiftStart || "-")}</strong>
        <small>${escapeHtml(item.shiftEnd ? `- ${item.shiftEnd}` : "")}</small>
      </div>
      <div>
        <span class="vehicle-row-label">Futár / rendszám</span>
        <strong>${escapeHtml(item.driverName || "-")}</strong>
        <small>${escapeHtml(item.licensePlate || "-")} · ${escapeHtml(item.car || "Autó")}</small>
      </div>
      <div>
        <span class="vehicle-row-label">Raktár</span>
        <strong>${escapeHtml(vehicleAssignmentWarehouse(item) || "-")}</strong>
        <small>${escapeHtml(vehicleAssignmentStatus(item))}</small>
      </div>
      <div class="vehicle-assignment-actions">
        <span class="vehicle-status-pill ${item.date === localDate() ? "today" : "history"}">${escapeHtml(item.date === localDate() ? "Kiosztva" : "Előzmény")}</span>
        ${options.interactive !== false ? `<button class="secondary vehicle-detail-button" type="button" data-vehicle-assignment-index="${items.indexOf(item)}">Részletek</button>` : ""}
      </div>
    </article>
  `).join("");
}

function vehicleAssignmentSearchText(item) {
  return [
    item?.licensePlate,
    item?.driverName,
    item?.car,
    item?.date,
    item?.shiftStart,
    item?.shiftEnd,
    item?.shiftType,
  ].map((value) => String(value || ""))
    .join(" ")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
}

function filteredVehicleAssignments() {
  const items = state.vehicleAssignments || [];
  const query = String(state.vehicleAssignmentQuery || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
  if (!query) return items;
  return items.filter((item) => vehicleAssignmentSearchText(item).includes(query));
}

function updateVehicleAssignmentResults() {
  const items = filteredVehicleAssignments();
  const result = $("#vehicle-assignment-results");
  const count = $("#vehicle-assignment-count");
  if (count) {
    count.textContent = state.vehicleAssignmentQuery
      ? `${items.length}/${(state.vehicleAssignments || []).length} bejegyzés`
      : `${(state.vehicleAssignments || []).length} bejegyzés`;
  }
  if (result) result.innerHTML = vehicleAssignmentRows(items);
  bindVehicleDetailButtons(result);
}

function vehicleMainAssignments() {
  const date = String(state.vehicleDateFilter || "").trim();
  const warehouse = String(state.vehicleWarehouseFilter || "").trim().toUpperCase();
  return (state.vehicleAssignments || [])
    .filter((item) => !date || String(item.date || "") === date)
    .filter((item) => !warehouse || vehicleAssignmentWarehouse(item) === warehouse)
    .sort((left, right) => String(left.shiftStart || "").localeCompare(String(right.shiftStart || "")));
}

function renderVehicleFreeVehicles() {
  const target = $("#vehicle-free-panel");
  if (!target) return;
  const warehouse = String(state.vehicleWarehouseFilter || "").trim().toUpperCase();
  const assignedPlates = new Set(vehicleMainAssignments().map((item) => String(item.licensePlate || "").trim().toUpperCase()).filter(Boolean));
  const items = (state.vehicleConfigurations || [])
    .filter((item) => item.active !== false)
    .filter((item) => !warehouse || String(item.warehouseCode || "").toUpperCase() === warehouse)
    .filter((item) => !assignedPlates.has(String(item.licensePlate || "").trim().toUpperCase()))
    .sort((left, right) => String(left.licensePlate || "").localeCompare(String(right.licensePlate || ""), "hu"));
  target.innerHTML = `
    <div class="device-history-head">
      <strong>Szabad autók</strong>
      <span>${formatCount(items.length)} autó</span>
    </div>
    ${items.length ? `<div class="vehicle-free-list">${items.map((item) => `
      <article class="vehicle-free-row">
        <div><span>Rendszám</span><strong>${escapeHtml(item.licensePlate || "-")}</strong><small>${escapeHtml([item.brand, item.model].filter(Boolean).join(" ") || "Autó")}</small></div>
        <div><span>Raktár</span><strong>${escapeHtml(item.warehouseCode || "-")}</strong><small>${escapeHtml(item.carStatusLabel || "Szabad")}</small></div>
        <span class="vehicle-status-pill free">Szabad</span>
        <button class="secondary vehicle-detail-button" type="button" data-vehicle-config-plate="${escapeHtml(item.licensePlate || "")}">Részletek</button>
      </article>
    `).join("")}</div>` : `<div class="empty-card">Nincs szabad autó ehhez a naphoz és raktárhoz.</div>`}
  `;
  target.querySelectorAll("[data-vehicle-config-plate]").forEach((button) => {
    button.addEventListener("click", () => openVehicleDetailDialog({
      licensePlate: button.dataset.vehicleConfigPlate,
      ...vehicleConfigForPlate(button.dataset.vehicleConfigPlate),
    }));
  });
}

function renderVehicleAssignments() {
  const target = $("#vehicle-assignment-history");
  if (!target) return;
  const canManage = Boolean(state.user?.canManageVehicles);
  if (!canManage && state.vehicleActiveTab !== "today") state.vehicleActiveTab = "today";
  const assignments = vehicleMainAssignments();
  target.classList.toggle("hidden", state.vehicleActiveTab !== "today");
  $("#vehicle-free-panel")?.classList.toggle("hidden", state.vehicleActiveTab !== "free");
  renderVehicleHrPanel();
  document.querySelectorAll('[data-vehicle-tab="free"], [data-vehicle-tab="search"]').forEach((button) => {
    button.classList.toggle("hidden", !canManage);
  });
  document.querySelectorAll("[data-vehicle-tab]").forEach((button) => {
    button.classList.toggle("active", button.dataset.vehicleTab === state.vehicleActiveTab);
  });
  document.querySelectorAll("[data-vehicle-warehouse]").forEach((button) => {
    button.classList.toggle("active", button.dataset.vehicleWarehouse === state.vehicleWarehouseFilter);
  });
  if (state.vehicleActiveTab === "today") {
    target.innerHTML = `
      <div class="device-history-head">
        <strong>Mai autóbeosztás</strong>
        <span>${formatCount(assignments.length)} autó</span>
      </div>
      ${assignments.length ? `<div class="vehicle-assignment-results">${vehicleAssignmentRows(assignments)}</div>` : `<div class="empty-card">Nincs autóbeosztás ehhez a naphoz és raktárhoz.</div>`}
    `;
    bindVehicleDetailButtons(target);
  }
  if (state.vehicleActiveTab === "free") renderVehicleFreeVehicles();
}

function bindVehicleDetailButtons(target) {
  target?.querySelectorAll("[data-vehicle-assignment-index]").forEach((button) => {
    button.addEventListener("click", () => {
      const item = state.vehicleVisibleAssignments[Number(button.dataset.vehicleAssignmentIndex)];
      if (item) openVehicleDetailDialog(item);
    });
  });
}

async function loadVehicleAssignments(options = {}) {
  const background = Boolean(options.background);
  const target = $("#vehicle-assignment-history");
  if (!target) return;
  if (!background || !(state.vehicleAssignments || []).length) {
    target.innerHTML = `<div class="empty-card">Autó-hozzárendelések betöltése...</div>`;
  }
  try {
    const selectedDate = String(state.vehicleDateFilter || localDate()).trim();
    const today = localDate();
    const endpoint = selectedDate === today
      ? "/api/vehicles/today-assignments"
      : "/api/vehicles/assignments?days=60";
    const payload = await api(withPreviewCourier(endpoint));
    state.vehicleAssignments = payload.items || [];
    renderVehicleAssignments();
  } catch (error) {
    if (!background || !(state.vehicleAssignments || []).length) {
      target.innerHTML = `<div class="notice error">Az autó-hozzárendelések nem tölthetők be: ${escapeHtml(error.message)}</div>`;
    }
  }
}

function renderVehicleHrPanel() {
  const panel = $("#vehicle-hr-panel");
  if (!panel) return;
  panel.classList.toggle("hidden", !state.user?.canManageVehicles || state.vehicleActiveTab !== "search");
  const monthInput = $("#vehicle-hr-month");
  if (monthInput && !monthInput.value) {
    monthInput.value = new Date().toISOString().slice(0, 7);
  }
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
  bindVehicleDetailButtons(target);
}

async function searchVehicleAssignments() {
  const target = $("#vehicle-hr-search-results");
  const plateInput = $("#vehicle-hr-plate");
  const courierSelect = $("#vehicle-hr-courier");
  const monthInput = $("#vehicle-hr-month");
  if (!target || !plateInput || !courierSelect) return;
  const plate = String(plateInput.value || "").trim();
  const courierId = String(courierSelect.value || "").trim();
  const month = String(monthInput?.value || "").trim();
  const query = plate || courierId;
  if (!query) {
    target.innerHTML = `<div class="empty-card">Válassz futárt vagy adj meg rendszámot.</div>`;
    return;
  }
  target.innerHTML = `<div class="empty-card">Keresés folyamatban...</div>`;
  try {
    const params = new URLSearchParams({ query });
    if (month) params.set("month", month);
    const payload = await api(`/api/vehicles/assignments/search?${params.toString()}`);
    state.vehicleSearchResults = payload.items || [];
    renderVehicleSearchResults(payload.lastUsage, state.vehicleSearchResults);
  } catch (error) {
    target.innerHTML = `<div class="notice error">A keresés nem sikerült: ${escapeHtml(error.message)}</div>`;
  }
}

async function loadVehicleReports() {
  const target = $("#vehicle-condition-history");
  if (!target) return;
  const plate = String($("#vehicle-license-plate")?.value || "").trim();
  if (!state.user?.courierId && state.user?.canManageVehicles && !plate) {
    target.innerHTML = `<div class="empty-card">A fotós előzményekhez válassz ki egy rendszámot.</div>`;
    return;
  }
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
  state.vehicleDateFilter = state.vehicleDateFilter || localDate();
  const dateInput = $("#vehicle-dashboard-date");
  if (dateInput && !dateInput.value) dateInput.value = state.vehicleDateFilter;
  $("#vehicle-admin-open")?.classList.toggle("hidden", !state.user?.canManageVehicles);
  renderVehicleHrPanel();
  renderVehicleAssignments();
  await Promise.all([
    loadCourierMasterOptions(),
    loadVehicleAssignments(),
    state.user?.canManageVehicles ? loadVehicleConfigurations() : Promise.resolve(),
  ]);
  renderVehicleAssignments();
  renderVehicleFreeVehicles();
}

function setVehicleConfigMessage(message, isError = false) {
  const target = $("#vehicle-config-message");
  if (!target) return;
  target.textContent = message || "";
  target.classList.toggle("error", Boolean(isError));
}

function renderVehicleConfigSetup() {
  const countiesSelect = $("#vehicle-config-toll-counties");
  if (countiesSelect && !countiesSelect.dataset.loaded) {
    const counties = state.vehicleConfigurationSetup?.counties?.length
      ? state.vehicleConfigurationSetup.counties
      : HUNGARIAN_COUNTIES;
    countiesSelect.innerHTML = counties
      .map((county) => `<option value="${escapeHtml(county)}">${escapeHtml(county)}</option>`)
      .join("");
    countiesSelect.dataset.loaded = "1";
  }
  renderCourierMasterOptions();
  toggleVehicleConfigConditionalFields();
}

function selectedVehicleConfigCounties() {
  const select = $("#vehicle-config-toll-counties");
  return Array.from(select?.selectedOptions || []).map((option) => option.value);
}

function toggleVehicleConfigConditionalFields() {
  const tollType = $("#vehicle-config-toll-type")?.value || "none";
  const countiesWrap = $("#vehicle-config-counties-wrap");
  if (countiesWrap) countiesWrap.classList.toggle("hidden", tollType !== "county");
  if (tollType !== "county") {
    Array.from($("#vehicle-config-toll-counties")?.options || []).forEach((option) => {
      option.selected = false;
    });
  }
  const ownershipType = $("#vehicle-config-ownership")?.value || "own";
  const rentalWrap = $("#vehicle-config-rental-company-wrap");
  if (rentalWrap) rentalWrap.classList.toggle("hidden", ownershipType !== "rented");
  if (ownershipType !== "rented" && $("#vehicle-config-rental-company")) {
    $("#vehicle-config-rental-company").value = "";
  }
}

function fillVehicleConfigForm(item = {}) {
  $("#vehicle-config-jitt-id").value = item.jittCarId || "";
  $("#vehicle-config-hub-id").value = item.hubVehicleId || "";
  $("#vehicle-config-license-plate").value = item.licensePlate || "";
  $("#vehicle-config-brand").value = item.brand || "";
  $("#vehicle-config-model").value = item.model || "";
  $("#vehicle-config-ownership").value = item.ownershipType || "own";
  $("#vehicle-config-rental-company").value = item.rentalCompany || "";
  $("#vehicle-config-warehouse").value = item.warehouseCode || "BUD1";
  $("#vehicle-config-toll-type").value = item.tollVignetteType || "none";
  $("#vehicle-config-toll-from").value = item.tollValidFrom || "";
  $("#vehicle-config-toll-to").value = item.tollValidTo || "";
  $("#vehicle-config-service-from").value = item.serviceFrom || "";
  $("#vehicle-config-service-to").value = item.serviceTo || "";
  $("#vehicle-config-service-location").value = item.serviceLocation || "";
  $("#vehicle-config-status").value = item.carStatus || "assignable";
  $("#vehicle-config-condition-status").value = item.conditionStatus || "ok";
  $("#vehicle-config-condition-description").value = item.conditionDescription || "";
  $("#vehicle-config-min-rounds").value = item.minimumDailyRounds || "";
  $("#vehicle-config-enforce-min-rounds").checked = Boolean(item.enforceMinimumDailyRounds);
  $("#vehicle-config-dedicated-courier").value = item.dedicatedCourierId || "";
  $("#vehicle-config-active").checked = item.active !== false;
  const counties = new Set(item.tollCounties || []);
  Array.from($("#vehicle-config-toll-counties")?.options || []).forEach((option) => {
    option.selected = counties.has(option.value);
  });
  toggleVehicleConfigConditionalFields();
  setVehicleConfigMessage(item.licensePlate ? `${item.licensePlate} szerkesztése.` : "");
}

function vehicleConfigStatusClass(item) {
  if (!item.active) return "muted";
  if (["service", "out_of_order"].includes(item.carStatus)) return "error";
  if (["garage_master", "other"].includes(item.carStatus)) return "attention";
  return "done";
}

function vehicleConfigFilteredItems() {
  const search = String($("#vehicle-config-search")?.value || "").trim().toLocaleLowerCase("hu-HU");
  const warehouse = $("#vehicle-config-filter-warehouse")?.value || "";
  const status = $("#vehicle-config-filter-status")?.value || "";
  return (state.vehicleConfigurations || []).filter((item) => {
    if (warehouse && item.warehouseCode !== warehouse) return false;
    if (status && item.carStatus !== status) return false;
    if (!search) return true;
    return [item.licensePlate, item.jittCarId, item.hubVehicleId, item.dedicatedCourierName, item.dedicatedCourierId]
      .some((value) => String(value || "").toLocaleLowerCase("hu-HU").includes(search));
  });
}

function renderVehicleConfigSummary(items) {
  const setCount = (key, value) => {
    const target = document.querySelector(`[data-vehicle-config-count="${key}"]`);
    if (target) target.textContent = formatCount(value);
  };
  setCount("all", items.length);
  setCount("assignable", items.filter((item) => item.carStatus === "assignable" && item.conditionStatus === "ok").length);
  setCount("attention", items.filter((item) => ["service", "out_of_order"].includes(item.carStatus) || ["attention", "faulty"].includes(item.conditionStatus)).length);
  setCount("dedicated", items.filter((item) => item.dedicatedCourierId).length);
}

function renderVehicleConfigurations() {
  const target = $("#vehicle-config-list");
  if (!target) return;
  const items = state.vehicleConfigurations || [];
  renderVehicleConfigSummary(items);
  const filteredItems = vehicleConfigFilteredItems();
  if (!items.length) {
    target.innerHTML = `<div class="empty-card">Még nem érkezett jármű a Courier Hubból.</div>`;
    return;
  }
  if (!filteredItems.length) {
    target.innerHTML = `<div class="empty-card">A szűrésnek megfelelő jármű nincs.</div>`;
    return;
  }
  target.innerHTML = filteredItems.map((item) => `
    <article class="vehicle-config-row">
      <div>
        <strong>${escapeHtml(item.licensePlate || "-")}</strong>
        <small>${escapeHtml(item.warehouseCode || "-")} · Hub #${escapeHtml(item.hubVehicleId || "-")} · ${escapeHtml([item.brand, item.model].filter(Boolean).join(" ") || "-")}</small>
      </div>
      <div>
        <span class="settlement-dashboard-status ${vehicleConfigStatusClass(item)}">${escapeHtml(item.carStatusLabel || "-")}</span>
        <small>${escapeHtml(item.conditionLabel || "-")}${item.conditionDescription ? ` · ${escapeHtml(item.conditionDescription)}` : ""}${item.hubStatus ? ` · Hub: ${escapeHtml(item.hubStatus)}` : ""}</small>
      </div>
      <div>
        <strong>${item.dedicatedCourierId ? escapeHtml(`${item.dedicatedCourierName || "Futár"} · #${item.dedicatedCourierId}`) : "Nincs kiosztva"}</strong>
        <small>${escapeHtml(item.source || "JITT")}</small>
      </div>
      <div>
        <strong>${escapeHtml(item.tollVignetteLabel || "-")} · ${escapeHtml(item.ownershipLabel || "-")}</strong>
        <small>${escapeHtml((item.tollCounties || []).join(", ") || [item.tollValidFrom, item.tollValidTo].filter(Boolean).join(" - ") || "-")}</small>
      </div>
      <div>
        <small>${item.enforceMinimumDailyRounds ? `Min. napi kör: ${escapeHtml(item.minimumDailyRounds || 0)} ` : "Minimum kör nincs figyelve"}${item.serviceFrom || item.serviceTo ? ` · Szervíz: ${escapeHtml([item.serviceFrom, item.serviceTo].filter(Boolean).join(" - "))}` : ""}${item.serviceLocation ? ` · ${escapeHtml(item.serviceLocation)}` : ""}</small>
      </div>
      <button class="secondary" type="button" data-vehicle-config-edit="${escapeHtml(item.licensePlate || "")}">Szerkesztés</button>
    </article>
  `).join("");
}

async function loadVehicleConfigurations() {
  const target = $("#vehicle-config-list");
  if (!state.user?.canManageVehicles) {
    if (target) target.innerHTML = `<div class="notice error">Ehhez admin vagy HR jogosultság szükséges.</div>`;
    return;
  }
  if (target) target.innerHTML = `<div class="empty-card">Autó konfigurációk betöltése...</div>`;
  try {
    const [, payload] = await Promise.all([
      loadCourierMasterOptions(),
      api("/api/vehicles/configurations"),
    ]);
    state.vehicleConfigurations = payload.items || [];
    state.vehicleConfigurationSetup = payload.setup || null;
    renderVehicleConfigSetup();
    renderVehicleConfigurations();
  } catch (error) {
    if (target) target.innerHTML = `<div class="notice error">Az autó konfigurációk nem tölthetők be: ${escapeHtml(error.message)}</div>`;
  }
}

async function loadScheduleVehicleConfigurations({ force = false } = {}) {
  if (!state.user?.canManageVehicles) return;
  if (!force && state.scheduleVehicleConfigurations?.length) return;
  try {
    const payload = await api("/api/vehicles/configurations", { silentLoading: true });
    state.scheduleVehicleConfigurations = payload.items || [];
    if (!state.vehicleConfigurations?.length) state.vehicleConfigurations = payload.items || [];
    state.vehicleConfigurationSetup = payload.setup || state.vehicleConfigurationSetup;
  } catch (_) {
    state.scheduleVehicleConfigurations = state.scheduleVehicleConfigurations || [];
  }
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

document.querySelectorAll("[data-vehicle-tab]").forEach((button) => {
  button.addEventListener("click", () => {
    state.vehicleActiveTab = button.dataset.vehicleTab || "today";
    renderVehicleAssignments();
  });
});

document.querySelectorAll("[data-vehicle-warehouse]").forEach((button) => {
  button.addEventListener("click", () => {
    state.vehicleWarehouseFilter = button.dataset.vehicleWarehouse || "";
    renderVehicleAssignments();
  });
});

$("#vehicle-dashboard-date")?.addEventListener("change", async (event) => {
  state.vehicleDateFilter = event.currentTarget.value || localDate();
  await loadVehicleAssignments();
});

$("#vehicle-dashboard-refresh")?.addEventListener("click", () => loadVehicleSection());
$("#vehicle-admin-open")?.addEventListener("click", () => showSection("vehicle-config"));

$("#vehicle-hr-search-form")?.addEventListener("submit", (event) => {
  event.preventDefault();
  searchVehicleAssignments();
});

$("#vehicle-config-refresh")?.addEventListener("click", () => loadVehicleConfigurations());
$("#vehicle-config-search")?.addEventListener("input", () => renderVehicleConfigurations());
$("#vehicle-config-filter-warehouse")?.addEventListener("change", () => renderVehicleConfigurations());
$("#vehicle-config-filter-status")?.addEventListener("change", () => renderVehicleConfigurations());
$("#vehicle-config-toll-type")?.addEventListener("change", toggleVehicleConfigConditionalFields);
$("#vehicle-config-ownership")?.addEventListener("change", toggleVehicleConfigConditionalFields);
toggleVehicleConfigConditionalFields();

$("#vehicle-config-list")?.addEventListener("click", (event) => {
  const button = event.target?.closest?.("[data-vehicle-config-edit]");
  if (!button) return;
  const plate = button.getAttribute("data-vehicle-config-edit") || "";
  const item = (state.vehicleConfigurations || []).find((row) => row.licensePlate === plate);
  if (item) {
    fillVehicleConfigForm(item);
    $("#vehicle-config-form")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }
});

$("#vehicle-config-form")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  const form = event.currentTarget;
  const button = form.querySelector('button[type="submit"]');
  const courierSelect = $("#vehicle-config-dedicated-courier");
  const selectedCourier = courierSelect?.selectedOptions?.[0];
  const payload = {
    jitt_car_id: $("#vehicle-config-jitt-id")?.value || "",
    license_plate: $("#vehicle-config-license-plate")?.value || "",
    warehouse_code: $("#vehicle-config-warehouse")?.value || "BUD1",
    brand: $("#vehicle-config-brand")?.value || "",
    model: $("#vehicle-config-model")?.value || "",
    ownership_type: $("#vehicle-config-ownership")?.value || "own",
    rental_company: $("#vehicle-config-rental-company")?.value || "",
    toll_vignette_type: $("#vehicle-config-toll-type")?.value || "none",
    toll_counties: selectedVehicleConfigCounties(),
    toll_valid_from: $("#vehicle-config-toll-from")?.value || "",
    toll_valid_to: $("#vehicle-config-toll-to")?.value || "",
    service_from: $("#vehicle-config-service-from")?.value || "",
    service_to: $("#vehicle-config-service-to")?.value || "",
    service_location: $("#vehicle-config-service-location")?.value || "",
    car_status: $("#vehicle-config-status")?.value || "assignable",
    condition_status: $("#vehicle-config-condition-status")?.value || "ok",
    condition_description: $("#vehicle-config-condition-description")?.value || "",
    minimum_daily_rounds: $("#vehicle-config-min-rounds")?.value ? Number($("#vehicle-config-min-rounds").value) : null,
    enforce_minimum_daily_rounds: Boolean($("#vehicle-config-enforce-min-rounds")?.checked),
    dedicated_courier_id: courierSelect?.value ? Number(courierSelect.value) : null,
    dedicated_courier_name: selectedCourier?.dataset?.name || "",
    active: Boolean($("#vehicle-config-active")?.checked),
  };
  setVehicleConfigMessage("Autó konfiguráció mentése...");
  if (button) button.disabled = true;
  try {
    await api("/api/vehicles/configurations", { method: "POST", body: JSON.stringify(payload) });
    form.reset();
    $("#vehicle-config-active").checked = true;
    Array.from($("#vehicle-config-toll-counties")?.options || []).forEach((option) => {
      option.selected = false;
    });
    toggleVehicleConfigConditionalFields();
    setVehicleConfigMessage("Autó konfiguráció mentve.");
    await loadVehicleConfigurations();
  } catch (error) {
    setVehicleConfigMessage(`A mentés sikertelen: ${error.message}`, true);
  } finally {
    if (button) button.disabled = false;
  }
});

function selectedVehicleDamageCount() {
  const input = $("#vehicle-damage-count");
  const value = Number.parseInt(String(input?.value || "0"), 10);
  return Number.isFinite(value) ? Math.max(0, Math.min(20, value)) : 0;
}

function renderVehicleDamagePhotoFields() {
  const target = $("#vehicle-damage-photo-fields");
  const input = $("#vehicle-damage-count");
  if (!target) return;
  const count = selectedVehicleDamageCount();
  if (input && String(input.value || "") !== String(count)) input.value = String(count);
  if (!count) {
    target.innerHTML = "";
    return;
  }
  target.innerHTML = Array.from({ length: count }, (_, index) => `
    <label class="vehicle-damage-row">
      <strong>${index + 1}. sérülés fotója</strong>
      <input name="photos" type="file" accept="image/png,image/jpeg,image/webp" required />
    </label>
  `).join("");
}

ensureVehicleDetailDialog();

$("#vehicle-damage-count")?.addEventListener("input", renderVehicleDamagePhotoFields);
renderVehicleDamagePhotoFields();

const vehicleConditionForm = $("#vehicle-condition-form");
if (vehicleConditionForm) {
  vehicleConditionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (isAdminPreviewMode()) {
      setVehicleConditionMessage("Admin előnézetben nem rögzíthető autóállapot.", true);
      return;
    }
    const button = vehicleConditionForm.querySelector('button[type="submit"]');
    const damageCount = selectedVehicleDamageCount();
    const photos = Array.from(vehicleConditionForm.querySelectorAll('input[type="file"][name="photos"]'))
      .flatMap((input) => Array.from(input.files || []));
    if (damageCount > 0 && photos.length < damageCount) {
      setVehicleConditionMessage("Minden megadott sérüléshez tölts fel egy fotót.", true);
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
      renderVehicleDamagePhotoFields();
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
    if (submitButton) submitButton.disabled = false;
    return;
  }
  form.append("month", state.workflowMonth);
  form.append("process", state.workflowProcess);
  const selectedCashInvoiceFile = form.get("cash_invoice_file");
  const hasCashInvoiceFile =
    selectedCashInvoiceFile instanceof File && Boolean(selectedCashInvoiceFile.name);
  const invoiceRequirements = state.workflow?.invoiceRequirements || {};
  const cashInvoiceRequired = Boolean(invoiceRequirements.requiresCashInvoice)
    && Number(invoiceRequirements.cashGrossHuf || 0) > 1000;
  const cashOnlyInvoice = Boolean(invoiceRequirements.cashOnlyInvoice);
  if (cashInvoiceRequired && !hasCashInvoiceFile) {
    showWorkflowMessage(`Ehhez a TIG-hez külön KP számla is kell (${formatHuf(invoiceRequirements.cashGrossHuf || 0)}). Töltsd fel a KP számlát is.`, true);
    if (submitButton) submitButton.disabled = false;
    return;
  }
  showWorkflowMessage(
    cashOnlyInvoice
      ? "A KP számla ellenőrzése és tárolása folyamatban…"
      : hasCashInvoiceFile
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

function opsQueueLabel(eventType) {
  return {
    queued: "Sorban áll",
    returned: "Visszaért",
    shift_late: "Műszakból késik",
  }[String(eventType || "").toLowerCase()] || "Nincs jelzés";
}

function shiftSignalLabel(eventType) {
  return {
    shift_late: "Futár: Kések a műszakból",
    coordinator_shift_late: "Jelezett műszakkésés",
    coordinator_vehicle_fault: "Műszaki hibás autó",
    coordinator_waiting_for_car: "Autóra vár",
    coordinator_other: "Egyéb hiba",
  }[String(eventType || "").toLowerCase()] || "Nincs jelzés";
}

function workerHasSignal(item = {}) {
  return Boolean(item.signalEvent || item.giritonLoginMissingAlert);
}

function opsProgress(item) {
  const total = Number(item?.totalStops || item?.live?.totalStops || 0);
  const done = Number(item?.deliveredStops || item?.live?.deliveredStops || 0);
  const safeTotal = Math.max(0, total);
  const safeDone = Math.min(Math.max(0, done), safeTotal || done);
  const percent = safeTotal ? Math.round((safeDone / safeTotal) * 100) : 0;
  return { total: safeTotal, done: safeDone, percent };
}

function opsTimeRange(start, end) {
  const cleanStart = timeOnly(start) || start || "-";
  const cleanEnd = timeOnly(end) || end || "";
  return cleanEnd ? `${cleanStart}-${cleanEnd}` : cleanStart;
}

function opsVehicleText(vehicle) {
  if (!vehicle) return "";
  return vehicleLabel(vehicle);
}

function formatKm(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${formatAverage(number)} km` : "-";
}

function vehicleSmallText(vehicle = {}) {
  if (!vehicle || typeof vehicle === "string") return "";
  return [
    vehicle.fridgeConfig ? `Hűtő: ${vehicle.fridgeConfig}` : "",
    vehicle.plannedKm ? `Tervezett: ${formatKm(vehicle.plannedKm)}` : "",
    vehicle.routeExternalId ? `Route ext.: ${vehicle.routeExternalId}` : "",
    vehicle.cargoRouteId ? `Cargo: ${vehicle.cargoRouteId}` : "",
  ].filter(Boolean).join(" · ");
}

function workerAttendanceLabel(status) {
  if (status === "present") return "Bejött";
  if (status === "absent") return "Nem jött";
  if (status === "sent_home") return "Haza küldték";
  return "Nincs jelölve";
}

function workerShiftTimeText(shift = {}) {
  const start = shift.start || "-";
  return shift.end ? `${start}-${shift.end}` : start;
}

function workerShiftIsPast(shift = {}) {
  if (!shift.date || !shift.end) return false;
  const value = new Date(`${shift.date}T${shift.end}:00`);
  return !Number.isNaN(value.getTime()) && value.getTime() < Date.now();
}

function workerShiftTitle(item = {}) {
  const shifts = Array.isArray(item.shifts) ? item.shifts : [];
  const firstShift = shifts[0] || item;
  return firstShift.shiftName || firstShift.bookingCode || item.shiftName || item.bookingCode || "-";
}

function workerShiftSubtitle(item = {}) {
  const shifts = Array.isArray(item.shifts) ? item.shifts : [];
  const firstShift = shifts[0] || item;
  const parts = [];
  if (shifts.length > 1) parts.push(`${formatCount(shifts.length)} műszak`);
  if (firstShift.start || firstShift.end) parts.push(workerShiftTimeText(firstShift));
  if (firstShift.bookingCode) parts.push(firstShift.bookingCode);
  return parts.join(" · ");
}

function liveRouteSubtitle(live = {}, progress = {}) {
  const orderCount = Number(live.orderCount || live.totalStops || progress.total || 0);
  if (!orderCount) return "Csak beosztás alapján";
  const progressText = progress.total
    ? ` · ${formatCount(progress.done)} / ${formatCount(progress.total)} cím`
    : "";
  return `Megrendelés: ${formatCount(orderCount)} db${progressText}`;
}

function temperatureText(value, status = "") {
  const number = Number(value);
  if (!Number.isFinite(number)) return status || "Hőmérséklet nincs adat";
  return `${formatAverage(number)} °C${status ? ` · ${status}` : ""}`;
}

function minutesText(value) {
  const number = Number(value);
  return Number.isFinite(number) ? `${formatCount(number)} perc` : "-";
}

function timelineTime(value) {
  return value ? shortDateTime(value) : "-";
}

function renderOpsSummary(summary = {}, cards = []) {
  const items = cards.length ? cards : [
    ["Futár", summary.couriers ?? summary.planned ?? 0],
    ["Aktív", summary.activeCouriers ?? summary.active ?? 0],
    ["Hátralévő cím", summary.remainingStops ?? 0],
    ["Késéses cím", summary.lateOpenStops ?? 0],
  ];
  return `<div class="ops-summary">
    ${items.map(([label, value, note]) => `
      <div>
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(typeof value === "string" ? value : formatCount(value || 0))}</strong>
        ${note ? `<small>${escapeHtml(note)}</small>` : ""}
      </div>
    `).join("")}
  </div>`;
}

function opsTemperatureText(item) {
  const value = Number(item?.temperatureCelsius);
  if (!Number.isFinite(value)) return "Hőm.: -";
  return `Hőm.: ${formatAverage(value)} °C`;
}

function liveMapPoints(couriers = []) {
  return couriers
    .map((item) => ({
      courierName: item.courierName || "Futár",
      courierId: item.courierId || "",
      warehouse: item.warehouse || "",
      vehiclePlate: item.vehiclePlate || "",
      temperature: opsTemperatureText(item),
      status: item.status || item.shiftStatus || "Live",
      lat: Number(item.lastLatitude),
      lon: Number(item.lastLongitude),
    }))
    .filter((item) => Number.isFinite(item.lat) && Number.isFinite(item.lon));
}

function liveCourierPriority(item) {
  const current = item?.currentStop || {};
  const isLate = Boolean(item?.lateOpenStops || current.isLate || Number(current.delayMinutes || 0) > 0);
  const isOnRoute = Boolean(item?.activeRouteId || Number(item?.totalStops || 0) || Number(item?.remainingStops || 0));
  return {
    late: isLate ? 0 : 1,
    route: isOnRoute ? 0 : 1,
    remaining: -Number(item?.remainingStops || 0),
    name: String(item?.courierName || ""),
  };
}

function sortLiveCouriers(couriers = []) {
  return [...couriers].sort((left, right) => {
    const a = liveCourierPriority(left);
    const b = liveCourierPriority(right);
    return a.late - b.late
      || a.route - b.route
      || a.remaining - b.remaining
      || a.name.localeCompare(b.name, "hu");
  });
}

function ensureLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (!document.querySelector(`link[href="${LEAFLET_CSS_URL}"]`)) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = LEAFLET_CSS_URL;
    document.head.appendChild(link);
  }
  return new Promise((resolve, reject) => {
    const existingScript = document.querySelector(`script[src="${LEAFLET_JS_URL}"]`);
    if (existingScript) {
      existingScript.addEventListener("load", () => resolve(window.L), { once: true });
      existingScript.addEventListener("error", reject, { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = LEAFLET_JS_URL;
    script.async = true;
    script.onload = () => resolve(window.L);
    script.onerror = reject;
    document.head.appendChild(script);
  });
}

async function renderCoordinatorLeafletMap(couriers = []) {
  const target = $("#coordinator-live-map");
  if (!target) return;
  const points = liveMapPoints(couriers);
  if (state.coordinatorLeafletMap) {
    state.coordinatorLeafletMap.remove();
    state.coordinatorLeafletMap = null;
  }
  if (!points.length) {
    target.innerHTML = `<div class="empty-card">Nincs térképre rakható GPS pozíció.</div>`;
    return;
  }
  try {
    const L = await ensureLeaflet();
    target.innerHTML = "";
    const map = L.map(target, { zoomControl: true });
    state.coordinatorLeafletMap = map;
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap",
    }).addTo(map);
    const bounds = [];
    points.forEach((point) => {
      bounds.push([point.lat, point.lon]);
      const marker = L.marker([point.lat, point.lon]).addTo(map);
      marker.bindPopup(`
        <strong>${escapeHtml(point.courierName)}</strong><br>
        #${escapeHtml(point.courierId)} · ${escapeHtml(point.warehouse)}<br>
        ${escapeHtml(point.vehiclePlate || "Autó nincs")}<br>
        ${escapeHtml(point.temperature)}<br>
        ${escapeHtml(point.status)}
      `);
    });
    map.fitBounds(bounds, { padding: [24, 24], maxZoom: 13 });
    setTimeout(() => map.invalidateSize(), 0);
  } catch (error) {
    target.innerHTML = `<div class="notice error">A térkép nem tölthető be: ${escapeHtml(error.message || "ismeretlen hiba")}</div>`;
  }
}

function renderLiveCourierCard(item) {
  const progress = opsProgress(item);
  const current = item.currentStop || {};
  const next = item.nextStop || {};
  const currentIsLate = Boolean(current.isLate || Number(current.delayMinutes || 0) > 0);
  const hasLateOpenStops = Boolean(item.lateOpenStops || currentIsLate);
  const currentWindow = routeTimeRange(current.windowFrom, current.windowTo);
  const nextWindow = routeTimeRange(next.windowFrom, next.windowTo);
  const currentTiming = current.estimatedArrival || current.plannedArrival || current.realArrival || "";
  const nextTiming = next.estimatedArrival || next.plannedArrival || next.realArrival || "";
  const mapsLink = item.mapsUrl
    ? `<a class="ops-map-link" href="${escapeHtml(item.mapsUrl)}" target="_blank" rel="noopener">Pozíció térképen</a>`
    : `<span class="ops-muted">Nincs GPS pont</span>`;
  return `
    <details class="ops-card ops-live-details ${hasLateOpenStops ? "attention" : ""}" open data-courier-tours="${escapeHtml(item.courierId || "")}">
      <summary class="ops-card-head" data-courier-tours="${escapeHtml(item.courierId || "")}" title="Túráim megnyitása ennél a futárnál">
        <div>
          <strong>${escapeHtml(item.courierName || "Futár")}</strong>
          <small>#${escapeHtml(item.courierId || "-")} · ${escapeHtml(item.warehouse || "-")} · ${escapeHtml(item.vehiclePlate || "Autó nincs")} · ${escapeHtml(opsTemperatureText(item))}</small>
        </div>
        <span>${escapeHtml(item.status || item.shiftStatus || "Live")}</span>
      </summary>
      <div class="ops-live-body">
        <div class="ops-route-row">
          <div><span>Route</span><strong>${escapeHtml(item.activeRouteId || "-")}</strong></div>
          <div><span>Haladás</span><strong>${formatCount(progress.done)} / ${formatCount(progress.total)}</strong></div>
          <div><span>Hátra</span><strong>${formatCount(item.remainingStops || 0)}</strong></div>
        </div>
        <div class="ops-progress-bar"><i style="width:${progress.percent}%"></i></div>
        <div class="ops-detail-grid">
          <div class="${currentIsLate ? "ops-late-box" : ""}"><span>Aktuális cím</span><strong>${escapeHtml(current.address || "Nincs aktuális cím")}</strong><small>${current.position ? `#${escapeHtml(current.position)} · ` : ""}Időkapu: ${currentWindow}</small><small>${escapeHtml(currentTiming ? `Érkezés: ${currentTiming} · ${stopWindowStatusText(current)}` : stopWindowStatusText(current))}</small></div>
          <div><span>Következő cím</span><strong>${escapeHtml(next.address || "Nincs következő cím")}</strong><small>${next.position ? `#${escapeHtml(next.position)} · ` : ""}Időkapu: ${nextWindow}</small><small>${escapeHtml(nextTiming ? `Érkezés: ${nextTiming} · ${stopWindowStatusText(next)}` : stopWindowStatusText(next))}</small></div>
          <div><span>Sor / vissza</span><strong>${escapeHtml(opsQueueLabel(item.queueEvent))}</strong><small>${escapeHtml(shortDateTime(item.queueEventAt || ""))}</small></div>
          <div><span>GPS</span><strong>${mapsLink}</strong><small>${escapeHtml(shortDateTime(item.lastPositionAt || item.updatedAt || ""))}</small></div>
        </div>
      </div>
    </details>
  `;
}

function renderCoordinatorLiveMap() {
  const target = $("#coordinator-live-panel");
  if (!target) return;
  const payload = state.coordinatorLiveMap;
  if (!payload) {
    target.innerHTML = `<div class="empty-card">Live map betöltése...</div>`;
    return;
  }
  const couriers = sortLiveCouriers(payload.couriers || []);
  target.innerHTML = `
    ${renderOpsSummary(payload.summary || {}, [
      ["Live futár", payload.summary?.couriers || 0],
      ["Aktív túra", payload.summary?.activeCouriers || 0],
      ["Hátralévő cím", payload.summary?.remainingStops || 0],
      ["Nyitott késés", payload.summary?.lateOpenStops || 0],
    ])}
    <p class="updated-at">Frissítve: ${escapeHtml(shortDateTime(payload.updatedAt || ""))}</p>
    <div id="coordinator-live-map" class="ops-live-map"></div>
    <div class="ops-card-list">
      ${couriers.length ? couriers.map(renderLiveCourierCard).join("") : `<div class="empty-card">Most nincs mai live-map futár adat.</div>`}
    </div>
  `;
  renderCoordinatorLeafletMap(couriers).catch(() => {});
}

function openCourierTours(courierId) {
  const cleanId = String(courierId || "").trim();
  if (!cleanId) return;
  updatePreviewCourier(cleanId);
  showSection("tours");
}

$("#coordinator-live-panel")?.addEventListener("click", (event) => {
  const link = event.target.closest("a");
  if (link) return;
  const target = event.target.closest("[data-courier-tours]");
  if (!target) return;
  event.preventDefault();
  openCourierTours(target.dataset.courierTours);
});

async function loadCoordinatorLiveMap() {
  const target = $("#coordinator-live-panel");
  if (target && !state.coordinatorLiveMap) target.innerHTML = `<div class="empty-card">Live map betöltése...</div>`;
  try {
    state.coordinatorLiveMap = await api("/api/coordinator/live-map");
    renderCoordinatorLiveMap();
  } catch (error) {
    if (target) target.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
  }
}

function departureAlertClass(item = {}) {
  const alert = String(item.alertLevel || "").toLowerCase();
  if (!item.scanReady || alert === "red") return "attention";
  if (alert === "yellow") return "warning";
  return "";
}

function departureMinutesText(value, label) {
  if (value === null || value === undefined || value === "") return `${label}: -`;
  const minutes = Number(value);
  if (!Number.isFinite(minutes)) return `${label}: -`;
  if (minutes <= 0) return `${label}: most`;
  return `${label}: ${formatCount(minutes)} perc`;
}

function renderDepartureRouteCard(item) {
  const temp = item.temperature || {};
  const tempText = Number.isFinite(Number(temp.value)) ? `${formatAverage(Number(temp.value))} °C` : "-";
  const trolleyText = (item.trolleys || [])
    .slice(0, 4)
    .map((trolley) => `${trolley.type}: ${trolley.trolley || "-"} @ ${trolley.parking || "-"}`)
    .join(" · ");
  const scanText = item.scanReady
    ? "Szkennelés OK"
    : `${formatCount(item.notScannedOrders || 0)} rendelés · ${formatCount(item.notScannedBagEans || 0)} csomag · ${formatCount(item.missingBags || 0)} hiányzó táska`;
  return `
    <article class="departure-card ${departureAlertClass(item)}">
      <div class="ops-card-head">
        <div>
          <strong>${escapeHtml(item.courierName || "Futár")}</strong>
          <small>#${escapeHtml(item.courierId || "-")} · ${escapeHtml(item.warehouse || "-")} · ${item.routeId ? `Route ${escapeHtml(item.routeId)}` : "Nincs aktív route"}</small>
        </div>
        <span>${escapeHtml(item.statusLabel || "-")}</span>
      </div>
      <div class="departure-main">
        <div><span>Rámpa</span><strong>${escapeHtml(item.platformSectionMark || "-")}</strong><small>${escapeHtml(item.licencePlate || "Rendszám nincs")}</small></div>
        <div><span>Indulás</span><strong>${escapeHtml(departureMinutesText(item.minutesToDeparture, "Indulás"))}</strong><small>${escapeHtml(departureMinutesText(item.minutesToLoading, "Pakolás"))}</small></div>
        <div class="${item.scanReady ? "" : "ops-late-box"}"><span>Szkennelés</span><strong>${escapeHtml(scanText)}</strong><small>${formatCount(item.ordersInRoute || 0)} megrendelés a túrában</small></div>
        <div><span>Hőmérséklet</span><strong>${escapeHtml(tempText)}</strong><small>${temp.compliant === false ? "Nem megfelelő" : "OK"}</small></div>
      </div>
      ${trolleyText ? `<p class="departure-trolleys">${escapeHtml(trolleyText)}</p>` : ""}
    </article>
  `;
}

function renderDepartureGroup(title, items) {
  return `
    <section class="departure-group">
      <div class="departure-group-head">
        <h3>${escapeHtml(title)}</h3>
        <span>${formatCount(items.length)} futár</span>
      </div>
      <div class="ops-card-list">
        ${items.length ? items.map(renderDepartureRouteCard).join("") : `<div class="empty-card">Nincs ilyen futár most.</div>`}
      </div>
    </section>
  `;
}

function renderDepartureHelper() {
  const target = $("#departure-helper-panel");
  if (!target) return;
  const payload = state.departureHelper;
  if (!payload) {
    target.innerHTML = `<div class="empty-card">Indulási adatok betöltése...</div>`;
    return;
  }
  const routes = payload.routes || [];
  const onRamp = routes.filter((item) => item.statusGroup === "ramp");
  const waiting = routes.filter((item) => item.statusGroup === "waiting");
  const departed = routes.filter((item) => item.statusGroup === "departed");
  target.innerHTML = `
    ${payload.errors?.length ? `<div class="notice error">${escapeHtml(payload.errors.join(" | "))}</div>` : ""}
    ${renderOpsSummary(payload.summary || {}, [
      ["Összes", payload.summary?.total || 0],
      ["Rámpán", payload.summary?.onRamp || 0],
      ["Várakozik", payload.summary?.waiting || 0],
      ["Nem kész", payload.summary?.notReady || 0],
    ])}
    <p class="updated-at">${escapeHtml(payload.date || "")} · Frissítve: ${escapeHtml(shortDateTime(payload.updatedAt || ""))}</p>
    ${renderDepartureGroup("Rámpán", onRamp)}
    ${renderDepartureGroup("Várakozik", waiting)}
    ${departed.length ? renderDepartureGroup("Elindult, de még raktárnál", departed) : ""}
  `;
}

async function loadDepartureHelper() {
  const target = $("#departure-helper-panel");
  if (target && !state.departureHelper) target.innerHTML = `<div class="empty-card">Indulási adatok betöltése...</div>`;
  try {
    state.departureHelper = await api("/api/coordinator/departure-helper");
    renderDepartureHelper();
  } catch (error) {
    if (target) target.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
  }
}

function ensureWorkerShiftDialog() {
  let dialog = $("#worker-shift-dialog");
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.id = "worker-shift-dialog";
  dialog.className = "worker-shift-dialog";
  dialog.innerHTML = `
    <div class="worker-shift-dialog-card">
      <div class="worker-shift-dialog-head">
        <div>
          <span>Műszakok</span>
          <strong data-worker-shift-title>Futár</strong>
          <small data-worker-shift-subtitle></small>
        </div>
        <button type="button" class="icon-button" data-worker-shift-close aria-label="Bezárás">×</button>
      </div>
      <div class="worker-shift-list" data-worker-shift-list></div>
    </div>
  `;
  document.body.appendChild(dialog);
  dialog.querySelector("[data-worker-shift-close]")?.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  return dialog;
}

function renderWorkerShiftRow(shift = {}, index = 0) {
  const title = shift.shiftName || shift.bookingCode || "Műszak";
  const code = shift.bookingCode ? ` · ${escapeHtml(shift.bookingCode)}` : "";
  const vehicleText = opsVehicleText(shift.vehicle);
  const vehicleDetailText = vehicleSmallText(shift.vehicle);
  const orderCount = Number(shift.orderCount || 0);
  const orderText = workerShiftIsPast(shift)
    ? `<small>Megrendelés: ${orderCount ? `${formatCount(orderCount)} db` : "-"}</small>`
    : "";
  const returnText = [shift.plannedReturn ? `Tervezett vissza: ${timelineTime(shift.plannedReturn)}` : "", shift.realReturn ? `Valós vissza: ${timelineTime(shift.realReturn)}` : ""].filter(Boolean).join(" · ");
  const missText = shift.missedByRoute ? `<small class="route-delay-note">Nem ér vissza erre a műszakra az aktív túra alapján.</small>` : "";
  return `
    <div class="worker-shift-row ${index === 0 ? "first" : ""} ${shift.missedByRoute ? "attention" : ""}">
      <div>
        <span>${index === 0 ? "Első műszak" : `${index + 1}. műszak`}</span>
        <strong>${escapeHtml(title)}</strong>
        <small>${escapeHtml(shift.warehouse || "-")} · Indulás: ${escapeHtml(shift.start || "-")} · Várható vég: ${escapeHtml(shift.end || "-")}${code}</small>
        ${vehicleText ? `<small>Autó: ${escapeHtml([vehicleText, vehicleDetailText].filter(Boolean).join(" · "))}</small>` : ""}
        ${orderText}
        ${returnText ? `<small>${escapeHtml(returnText)}</small>` : ""}
        ${missText}
      </div>
      <div class="worker-shift-status">
        ${scheduleStatusChip(`GIRITON: ${String(shift.giritonStatus || "Nincs adat").toLocaleUpperCase("hu-HU")}`, shift.giritonTone)}
        ${scheduleStatusChip(`MŰSZAKPRO: ${String(shift.muszakproStatus || "Nincs adat").toLocaleUpperCase("hu-HU")}`, shift.muszakproTone)}
      </div>
    </div>
  `;
}

function openWorkerShiftDialog(workerKey) {
  const workers = state.todayWorkers?.workers || [];
  const worker = workers.find((item) => {
    const key = String(workerKey || "");
    return String(item.workerKey || item.courierId || item.courierName || "") === key;
  });
  if (!worker) return;
  const shifts = Array.isArray(worker.shifts) && worker.shifts.length ? worker.shifts : [worker];
  const dialog = ensureWorkerShiftDialog();
  dialog.querySelector("[data-worker-shift-title]").textContent = worker.courierName || "Futár";
  dialog.querySelector("[data-worker-shift-subtitle]").textContent = `#${worker.courierId || "-"} · ${formatCount(shifts.length)} műszak ma`;
  const alternative = worker.alternativeShift
    ? `<div class="notice error">Figyelem: az aktív túra miatt a(z) ${escapeHtml(worker.alternativeShift.shiftName || worker.alternativeShift.bookingCode || worker.alternativeShift.start || "következő")} műszak veszélyben van.</div>`
    : "";
  dialog.querySelector("[data-worker-shift-list]").innerHTML = `${alternative}${shifts.map(renderWorkerShiftRow).join("")}`;
  dialog.showModal();
}

function ensureWorkerInfoDialog() {
  let dialog = $("#worker-info-dialog");
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.id = "worker-info-dialog";
  dialog.className = "worker-shift-dialog";
  dialog.innerHTML = `
    <div class="worker-shift-dialog-card">
      <div class="worker-shift-dialog-head">
        <div>
          <span data-worker-info-label>Részletek</span>
          <strong data-worker-info-title>Futár</strong>
          <small data-worker-info-subtitle></small>
        </div>
        <button type="button" class="icon-button" data-worker-info-close aria-label="Bezárás">×</button>
      </div>
      <div class="worker-shift-list" data-worker-info-body></div>
    </div>
  `;
  document.body.appendChild(dialog);
  dialog.querySelector("[data-worker-info-close]")?.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  return dialog;
}

function openWorkerInfoDialog(workerKey, mode) {
  const workers = state.todayWorkers?.workers || [];
  const worker = workers.find((item) => {
    const key = String(workerKey || "");
    return String(item.workerKey || item.courierId || item.courierName || "") === key;
  });
  if (!worker) return;
  const dialog = ensureWorkerInfoDialog();
  dialog.querySelector("[data-worker-info-title]").textContent = worker.courierName || "Futár";
  dialog.querySelector("[data-worker-info-subtitle]").textContent = `#${worker.courierId || "-"} · ${worker.warehouse || "-"}`;
  const label = mode === "vehicle" ? "Autó" : mode === "route" ? "Live túra" : "Bejelentkezések";
  dialog.querySelector("[data-worker-info-label]").textContent = label;
  dialog.querySelector("[data-worker-info-body]").innerHTML = mode === "vehicle"
    ? renderWorkerVehicleDetails(worker)
    : mode === "route"
      ? renderWorkerRouteDetails(worker)
      : renderWorkerLoginDetails(worker);
  dialog.showModal();
}

function detailRow(label, value, subtext = "") {
  return `<div class="stat-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value || "-")}</strong>${subtext ? `<small>${escapeHtml(subtext)}</small>` : ""}</div>`;
}

function renderWorkerVehicleDetails(worker = {}) {
  const vehicle = worker.vehicle || {};
  const routeDetail = worker.routeDetail || {};
  const vehicleText = opsVehicleText(vehicle) || "-";
  return `
    <div class="stat-breakdown-list">
      ${detailRow("Rendszám", vehicleText)}
      ${detailRow("Hűtő", vehicle.fridgeConfig || routeDetail.fridgeConfig || "-")}
      ${detailRow("Cargo route", vehicle.cargoRouteId || routeDetail.cargoRouteId || "-")}
      ${detailRow("Route external", vehicle.routeExternalId || routeDetail.routeExternalId || "-")}
      ${detailRow("Tervezett km", formatKm(vehicle.plannedKm ?? routeDetail.plannedKm))}
      ${detailRow("Hőmérséklet", temperatureText(worker.temperatureCelsius, worker.temperatureStatus))}
      ${detailRow("Aktuális műszak", workerShiftTitle(worker), workerShiftSubtitle(worker))}
      ${detailRow("Forrás", worker.routeDetail?.source || "Beosztás / live adat")}
    </div>
  `;
}

function renderTimeline(items = []) {
  if (!items.length) return `<div class="empty-card">Nincs sofőrnapló esemény ehhez a túrához.</div>`;
  return `<div class="worker-timeline">
    ${items.map((item) => `
      <div class="worker-timeline-row">
        <time>${escapeHtml(timelineTime(item.at))}</time>
        <div><strong>${escapeHtml(item.label || item.type || "Esemény")}</strong>${item.detail ? `<small>${escapeHtml(item.detail)}</small>` : ""}</div>
      </div>
    `).join("")}
  </div>`;
}

function renderWorkerRouteDetails(worker = {}) {
  const live = worker.live || {};
  const routeDetail = worker.routeDetail || {};
  return `
    <div class="stat-breakdown-list">
      ${detailRow("Túra szám", live.routeId || routeDetail.routeId || "-")}
      ${detailRow("Cargo route", live.cargoRouteId || routeDetail.cargoRouteId || "-")}
      ${detailRow("Route external", live.routeExternalId || routeDetail.routeExternalId || "-")}
      ${detailRow("Megrendelés", live.orderCount ? `${formatCount(live.orderCount)} db` : "-")}
      ${detailRow("Haladás", `${formatCount(live.deliveredStops || 0)} / ${formatCount(live.totalStops || 0)} cím`)}
      ${detailRow("Tervezett km", formatKm(live.plannedKm ?? routeDetail.plannedKm))}
      ${detailRow("Tervezett vissza", timelineTime(live.plannedReturn || routeDetail.plannedReturn))}
      ${detailRow("Valós vissza", timelineTime(live.realReturn || routeDetail.realReturn))}
      ${detailRow("Várakozás túrára", minutesText(live.queueWaitMinutes ?? routeDetail.queueWaitMinutes))}
    </div>
    ${renderTimeline(routeDetail.timeline || [])}
  `;
}

function renderWorkerLoginDetails(worker = {}) {
  const routeDetail = worker.routeDetail || {};
  return `
    <div class="stat-breakdown-list">
      ${detailRow("Giriton-bejelentkezés", worker.giritonLoginTime || "Nincs adat")}
      ${detailRow("Sorba állt", timelineTime(routeDetail.queueStartedAt || worker.queueEventAt))}
      ${detailRow("Túrát kapott", timelineTime(routeDetail.routeAssignedAt))}
      ${detailRow("Indulás a raktárból", timelineTime(routeDetail.departedAt))}
      ${detailRow("Tervezett vissza", timelineTime(routeDetail.plannedReturn))}
      ${detailRow("Valós vissza", timelineTime(routeDetail.realReturn))}
      ${detailRow("Várakozott", minutesText(routeDetail.queueWaitMinutes ?? worker.live?.queueWaitMinutes))}
    </div>
    ${renderTimeline(routeDetail.timeline || [])}
  `;
}

function ensureWorkerSignalDialog() {
  let dialog = $("#worker-signal-dialog");
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.id = "worker-signal-dialog";
  dialog.className = "worker-shift-dialog";
  dialog.innerHTML = `
    <form id="worker-signal-form" class="worker-shift-dialog-card">
      <div class="worker-shift-dialog-head">
        <div>
          <span>Jelzés</span>
          <strong data-worker-signal-title>Futár</strong>
          <small data-worker-signal-subtitle></small>
        </div>
        <button class="secondary icon-button" type="button" data-worker-signal-close>×</button>
      </div>
      <input id="worker-signal-courier-id" type="hidden" />
      <input id="worker-signal-courier-name" type="hidden" />
      <input id="worker-signal-date" type="hidden" />
      <input id="worker-signal-start" type="hidden" />
      <input id="worker-signal-end" type="hidden" />
      <input id="worker-signal-warehouse" type="hidden" />
      <input id="worker-signal-shift-name" type="hidden" />
      <input id="worker-signal-booking-code" type="hidden" />
      <label>
        Mi a gond?
        <select id="worker-signal-type">
          <option value="coordinator_shift_late">Jelezett műszakkésés</option>
          <option value="coordinator_vehicle_fault">Műszaki hibás autó</option>
          <option value="coordinator_waiting_for_car">Autóra vár</option>
          <option value="coordinator_other">Egyéb hiba</option>
        </select>
      </label>
      <label>
        Megjegyzés
        <textarea id="worker-signal-message" rows="3" placeholder="Rövid megjegyzés"></textarea>
      </label>
      <p id="worker-signal-status" class="updated-at"></p>
      <button class="primary" type="submit">Jelzés mentése</button>
    </form>
  `;
  document.body.appendChild(dialog);
  dialog.querySelector("[data-worker-signal-close]")?.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.querySelector("#worker-signal-form")?.addEventListener("submit", submitWorkerSignal);
  return dialog;
}

function openWorkerSignalDialog(workerKey) {
  const workers = state.todayWorkers?.workers || [];
  const worker = workers.find((item) => {
    const key = String(workerKey || "");
    return String(item.workerKey || item.courierId || item.courierName || "") === key;
  });
  if (!worker) return;
  const dialog = ensureWorkerSignalDialog();
  dialog.querySelector("[data-worker-signal-title]").textContent = worker.courierName || "Futár";
  dialog.querySelector("[data-worker-signal-subtitle]").textContent = `#${worker.courierId || "-"} · ${worker.warehouse || "-"} · ${workerShiftTimeText(worker)}`;
  $("#worker-signal-courier-id").value = worker.courierId || "";
  $("#worker-signal-courier-name").value = worker.courierName || "";
  $("#worker-signal-date").value = worker.date || localDate();
  $("#worker-signal-start").value = worker.start || "";
  $("#worker-signal-end").value = worker.end || "";
  $("#worker-signal-warehouse").value = worker.warehouse || "";
  $("#worker-signal-shift-name").value = worker.shiftName || worker.bookingCode || "";
  $("#worker-signal-booking-code").value = worker.bookingCode || "";
  $("#worker-signal-type").value = "coordinator_shift_late";
  $("#worker-signal-message").value = "";
  $("#worker-signal-status").textContent = "";
  dialog.showModal();
}

async function submitWorkerSignal(event) {
  event.preventDefault();
  const status = $("#worker-signal-status");
  status.textContent = "Mentés...";
  try {
    await api("/api/coordinator/today-workers/signal", {
      method: "POST",
      body: JSON.stringify({
        courier_id: $("#worker-signal-courier-id").value,
        courier_name: $("#worker-signal-courier-name").value,
        work_date: $("#worker-signal-date").value,
        start: $("#worker-signal-start").value,
        end: $("#worker-signal-end").value,
        warehouse: $("#worker-signal-warehouse").value,
        shift_name: $("#worker-signal-shift-name").value,
        booking_code: $("#worker-signal-booking-code").value,
        signal_type: $("#worker-signal-type").value,
        message: $("#worker-signal-message").value.trim(),
      }),
    });
    state.todayWorkers = null;
    await loadTodayWorkers();
    status.textContent = "Jelzés mentve.";
    setTimeout(() => $("#worker-signal-dialog")?.close(), 500);
  } catch (error) {
    status.textContent = error.message;
  }
}

function workerSearchText(item = {}) {
  return [
    item.courierName,
    item.courierId,
    item.warehouse,
    item.shiftName,
    item.bookingCode,
    opsVehicleText(item.vehicle),
    item.statusLabel,
    shiftSignalLabel(item.signalEvent),
    item.signalText,
  ].join(" ").toLocaleLowerCase("hu-HU");
}

function renderWorkerAttendanceControls(item = {}) {
  const workerKey = item.workerKey || item.courierId || item.courierName || "";
  const status = item.attendanceStatus || "";
  const savedText = item.attendanceMarkedAt
    ? `Mentve: ${shortDateTime(item.attendanceMarkedAt)}${item.attendanceMarkedBy ? ` · ${item.attendanceMarkedBy}` : ""}`
    : "Még nincs jelölve";
  return `
    <div class="worker-attendance-controls ${status ? "marked" : ""}">
      <div>
        <span>Bejött dolgozni?</span>
        <strong>${escapeHtml(workerAttendanceLabel(status))}</strong>
        <small>${escapeHtml(savedText)}</small>
      </div>
      <div class="worker-attendance-actions">
        <button type="button" class="${status === "present" ? "active" : ""}" data-worker-attendance="${escapeHtml(workerKey)}" data-attendance-status="present">Bejött</button>
        <button type="button" class="${status === "absent" ? "active danger" : ""}" data-worker-attendance="${escapeHtml(workerKey)}" data-attendance-status="absent">Nem jött</button>
      </div>
    </div>
  `;
}

async function setTodayWorkerAttendance(workerKey, attendanceStatus) {
  const workers = state.todayWorkers?.workers || [];
  const worker = workers.find((item) => {
    const key = String(workerKey || "");
    return String(item.workerKey || item.courierId || item.courierName || "") === key;
  });
  if (!worker) return;
  await api("/api/coordinator/today-workers/attendance", {
    method: "POST",
    body: JSON.stringify({
      courier_id: worker.courierId || "",
      courier_name: worker.courierName || "",
      work_date: worker.date || localDate(),
      start: worker.start || "",
      end: worker.end || "",
      warehouse: worker.warehouse || "",
      shift_name: worker.shiftName || worker.bookingCode || "",
      booking_code: worker.bookingCode || "",
      attendance_status: attendanceStatus,
    }),
  });
  state.todayWorkers = null;
  await loadTodayWorkers();
}

function renderWorkerCard(item) {
  const progress = opsProgress(item);
  const live = item.live || {};
  const hasLive = Boolean(live.routeId || live.mapsUrl || Number(live.totalStops || 0));
  const vehicleText = opsVehicleText(item.vehicle);
  const vehicleSubtitle = vehicleSmallText(item.vehicle) || temperatureText(item.temperatureCelsius, item.temperatureStatus);
  const workerKey = item.workerKey || item.courierId || item.courierName || "";
  const giritonLabel = String(item.giritonStatus || "Nincs adat").toLocaleUpperCase("hu-HU");
  const muszakproLabel = String(item.muszakproStatus || "Nincs adat").toLocaleUpperCase("hu-HU");
  const loginAlert = Boolean(item.giritonLoginMissingAlert);
  const loginPresentByRoute = Boolean(item.giritonPresentByRoute);
  const signalAlert = workerHasSignal(item);
  const signalLabel = item.signalEvent ? shiftSignalLabel(item.signalEvent) : (loginAlert ? "Giriton bejelentkezés hiányzik" : "Nincs jelzés");
  const signalSmall = [item.signalText, item.signalAt ? shortDateTime(item.signalAt) : ""].filter(Boolean).join(" · ");
  const loginText = item.giritonLoginTime || ((loginAlert || loginPresentByRoute) ? "Nincs bejelentkezés" : "Nincs adat");
  const loginSubtext = loginPresentByRoute
    ? "✓ Itt van · túra alapján"
    : (item.giritonLoginStatus || (item.isFirstShift ? "Első műszak" : ""));
  const loginBoxClass = loginPresentByRoute ? "ops-present-box" : (loginAlert ? "ops-late-box" : "");
  const mapsLink = live.mapsUrl
    ? `<a class="ops-map-link" href="${escapeHtml(live.mapsUrl)}" target="_blank" rel="noopener">Térkép</a>`
    : "";
  const end = item.end ? `-${escapeHtml(item.end)}` : "";
  return `
    <article class="ops-card ${signalAlert ? "attention" : ""}">
      <div class="ops-card-head">
        <div>
          <strong>${escapeHtml(item.courierName || "Futár")}</strong>
          <small>#${escapeHtml(item.courierId || "-")} · ${escapeHtml(item.warehouse || "-")} · ${escapeHtml(item.start || "-")}${end}</small>
        </div>
        <span>${escapeHtml(item.statusLabel || "-")}</span>
      </div>
      <div class="schedule-chip-row">
        ${scheduleStatusChip(`GIRITON: ${giritonLabel}`, item.giritonTone)}
        ${scheduleStatusChip(`MŰSZAKPRO: ${muszakproLabel}`, item.muszakproTone)}
        ${item.hubStatus ? scheduleStatusChip(`Hub: ${item.hubStatus}`, item.hubTone) : ""}
      </div>
      ${renderWorkerAttendanceControls(item)}
      <div class="ops-detail-grid">
        <button type="button" class="ops-detail-tile ops-shift-trigger" data-worker-shifts="${escapeHtml(workerKey)}"><span>Műszak</span><strong>${escapeHtml(workerShiftTitle(item))}</strong><small>${escapeHtml(workerShiftSubtitle(item))}</small></button>
        <button type="button" class="ops-detail-tile" data-worker-info="${escapeHtml(workerKey)}" data-worker-info-mode="vehicle"><span>Autó</span><strong>${escapeHtml(vehicleText || "-")}</strong><small>${escapeHtml(vehicleSubtitle)}</small></button>
        <button type="button" class="ops-detail-tile" data-worker-info="${escapeHtml(workerKey)}" data-worker-info-mode="route"><span>Live túra</span><strong>${escapeHtml(hasLive ? (live.routeId || "Aktív") : "Nincs live adat")}</strong><small>${escapeHtml(hasLive ? liveRouteSubtitle(live, progress) : "Csak beosztás alapján")}</small></button>
        <button type="button" class="ops-detail-tile ${loginBoxClass}" data-worker-info="${escapeHtml(workerKey)}" data-worker-info-mode="login"><span>Bejelentkezések</span><strong>${escapeHtml(loginText)}</strong><small>${escapeHtml(loginSubtext)}</small></button>
        <button type="button" class="ops-detail-tile worker-signal-trigger ${signalAlert ? "attention" : ""}" data-worker-signal="${escapeHtml(workerKey)}"><span>Jelzés a futártól</span><strong>${escapeHtml(signalLabel)}</strong><small>${escapeHtml(signalSmall || "Kattints jelzés rögzítéséhez")}</small></button>
      </div>
      ${hasLive ? `<div class="ops-worker-foot">
        <div class="ops-progress-bar"><i style="width:${progress.percent}%"></i></div>
        <span>${mapsLink}</span>
      </div>` : ""}
    </article>
  `;
}

function renderTodayWorkers() {
  const target = $("#today-workers-panel");
  if (!target) return;
  const payload = state.todayWorkers;
  if (!payload) {
    target.innerHTML = `<div class="empty-card">Mai műszakok betöltése...</div>`;
    return;
  }
  const workers = payload.workers || [];
  const query = String(state.todayWorkersQuery || "").trim().toLocaleLowerCase("hu-HU");
  const visibleWorkers = query
    ? workers.filter((item) => workerSearchText(item).includes(query))
    : workers;
  target.innerHTML = `
    ${payload.error ? `<div class="notice error">A mai beosztás nem tölthető be: ${escapeHtml(payload.error)}</div>` : ""}
    <div class="ops-toolbar">
      <label class="ops-search">Kereső<input id="today-workers-search" type="search" placeholder="Futár név, ID, műszak, autó..." value="${escapeHtml(state.todayWorkersQuery || "")}" /></label>
    </div>
    ${renderOpsSummary(payload.summary || {}, [
      ["Tervezett", payload.summary?.planned || 0],
      ["Bejött", payload.summary?.present || 0],
      ["Nem jött", payload.summary?.absent || 0],
      ["Aktív", payload.summary?.active || 0],
      ["Sorban", payload.summary?.queued || 0],
      ["Visszaért", payload.summary?.returned || 0],
    ])}
    <p class="updated-at">${escapeHtml(payload.date || "")} · Frissítve: ${escapeHtml(shortDateTime(payload.updatedAt || ""))}</p>
    <div class="ops-card-list">
      ${visibleWorkers.length ? visibleWorkers.map(renderWorkerCard).join("") : `<div class="empty-card">Nincs találat.</div>`}
    </div>
  `;
  $("#today-workers-search")?.addEventListener("input", (event) => {
    state.todayWorkersQuery = event.currentTarget.value || "";
    const cursor = event.currentTarget.selectionStart || state.todayWorkersQuery.length;
    renderTodayWorkers();
    const input = $("#today-workers-search");
    if (input) {
      input.focus();
      input.setSelectionRange(cursor, cursor);
    }
  });
  target.querySelectorAll("[data-worker-shifts]").forEach((button) => {
    button.addEventListener("click", () => openWorkerShiftDialog(button.dataset.workerShifts));
  });
  target.querySelectorAll("[data-worker-signal]").forEach((button) => {
    button.addEventListener("click", () => openWorkerSignalDialog(button.dataset.workerSignal));
  });
  target.querySelectorAll("[data-worker-info]").forEach((button) => {
    button.addEventListener("click", () => openWorkerInfoDialog(button.dataset.workerInfo, button.dataset.workerInfoMode));
  });
  target.querySelectorAll("[data-worker-attendance]").forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await setTodayWorkerAttendance(button.dataset.workerAttendance, button.dataset.attendanceStatus);
      } catch (error) {
        alert(error.message || "A jelenlét mentése nem sikerült.");
        button.disabled = false;
      }
    });
  });
}

async function loadTodayWorkers() {
  const target = $("#today-workers-panel");
  if (target && !state.todayWorkers) target.innerHTML = `<div class="empty-card">Mai műszakok betöltése...</div>`;
  try {
    state.todayWorkers = await api("/api/coordinator/today-workers");
    renderTodayWorkers();
  } catch (error) {
    if (target) target.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
  }
}

function scheduleStatusChip(label, tone) {
  return `<span class="schedule-chip ${escapeHtml(tone || "unknown")}">${escapeHtml(label || "Nincs adat")}</span>`;
}

function selectedScheduleDay(payload) {
  const days = payload?.days || [];
  return days.find((day) => day.date === state.coordinatorScheduleDay)
    || days.find((day) => day.total > 0)
    || days[0]
    || null;
}

function scheduleDayOffset(date) {
  const selected = new Date(`${date}T12:00:00`);
  const today = new Date(`${localDate()}T12:00:00`);
  return Math.round((selected - today) / 86400000);
}

function scheduleDayWeekday(date) {
  const value = new Date(`${date}T12:00:00`);
  if (Number.isNaN(value.getTime())) return "";
  return new Intl.DateTimeFormat("hu-HU", { weekday: "long" }).format(value);
}

function adjacentScheduleDay(payload, date, direction) {
  const days = payload?.days || [];
  const index = days.findIndex((day) => day.date === date);
  if (index < 0) return null;
  return days[index + direction] || null;
}

function scheduleCoverageTone(day = {}) {
  if (!day.capacityKnown || day.coveragePercent === null || day.coveragePercent === undefined) return "unknown";
  const value = Number(day.coveragePercent);
  if (value >= 95) return "good";
  if (value >= 85) return "warn";
  if (value >= 70) return "risk";
  return "bad";
}

function scheduleCoverageText(day = {}) {
  if (!day.capacityKnown || day.coveragePercent === null || day.coveragePercent === undefined) return "-";
  return `${formatCount(day.coveragePercent)}%`;
}

function scheduleSlotText(day = {}) {
  if (!day.capacityKnown) return `${formatCount(day.total || 0)} futár`;
  return `${formatCount(day.bookedSlots || 0)}/${formatCount(day.requiredSlots || 0)}`;
}

function scheduleDayDeltaText(day = {}) {
  if (!day.capacityKnown) return "nincs slot adat";
  const missing = Number(day.missingSlots || 0);
  const extra = Number(day.extraSlots || 0);
  if (missing > 0) return `-${formatCount(missing)} slot`;
  if (extra > 0) return `+${formatCount(extra)} slot`;
  return "rendben";
}

function renderScheduleDayButton(day) {
  const isSelected = day.date === state.coordinatorScheduleDay;
  const tone = scheduleCoverageTone(day);
  const offset = scheduleDayOffset(day.date);
  const offsetText = offset === 0 ? "Ma" : `D${offset > 0 ? "+" : ""}${offset}`;
  return `
    <button class="schedule-day coverage-${tone} ${isSelected ? "active" : ""} ${day.missingSlots || day.missing ? "attention" : ""}" type="button" data-schedule-day="${escapeHtml(day.date)}">
      <span>${escapeHtml(offsetText)}</span>
      <strong>${escapeHtml(day.label || day.date)}</strong>
      <small class="weekday-line">${escapeHtml(scheduleDayWeekday(day.date))}</small>
      <small class="slot-line">${escapeHtml(scheduleSlotText(day))}</small>
      <small class="coverage-pill">${escapeHtml(scheduleCoverageText(day))}</small>
      <small class="day-delta">${escapeHtml(scheduleDayDeltaText(day))}</small>
    </button>
  `;
}

function renderScheduleCalendarDays(days = []) {
  const visibleDays = Array.isArray(days) ? days.filter((day) => day?.date) : [];
  if (!visibleDays.length) return "";
  const firstDate = new Date(`${visibleDays[0].date}T12:00:00`);
  const mondayOffset = Number.isNaN(firstDate.getTime()) ? 0 : (firstDate.getDay() + 6) % 7;
  const cells = [
    ...Array.from({ length: mondayOffset }, () => '<div class="schedule-day-placeholder" aria-hidden="true"></div>'),
    ...visibleDays.map(renderScheduleDayButton),
  ];
  const trailingOffset = (7 - (cells.length % 7)) % 7;
  cells.push(...Array.from({ length: trailingOffset }, () => '<div class="schedule-day-placeholder" aria-hidden="true"></div>'));
  return cells.join("");
}

function renderScheduleWorker(worker) {
  const vehicleText = opsVehicleText(worker.vehicle);
  const end = worker.end ? `-${escapeHtml(worker.end)}` : "";
  const giritonLabel = String(worker.giritonStatus || "Nincs adat").toLocaleUpperCase("hu-HU");
  const muszakproLabel = String(worker.muszakproStatus || "Nincs adat").toLocaleUpperCase("hu-HU");
  const loginAlert = Boolean(worker.giritonLoginMissingAlert);
  const loginText = worker.giritonLoginTime || (loginAlert ? "Nincs bejelentkezés" : "Nincs adat");
  const loginSubtext = worker.giritonLoginStatus || (worker.isFirstShift ? "Első műszak" : "");
  return `
    <details class="ops-card schedule-worker ${loginAlert ? "attention" : ""}">
      <summary class="ops-card-head">
        <div>
          <strong>${escapeHtml(worker.courierName || "Futár")}</strong>
          <small>#${escapeHtml(worker.courierId || "-")} · ${escapeHtml(worker.warehouse || "-")} · ${escapeHtml(worker.start || "-")}${end}</small>
        </div>
        <span>${escapeHtml(worker.shiftName || worker.bookingCode || "Műszak")}</span>
      </summary>
      <div class="ops-live-body">
        <div class="schedule-chip-row">
          ${scheduleStatusChip(`GIRITON: ${giritonLabel}`, worker.giritonTone)}
          ${scheduleStatusChip(`MŰSZAKPRO: ${muszakproLabel}`, worker.muszakproTone)}
          ${worker.hubStatus ? scheduleStatusChip(`Hub: ${worker.hubStatus}`, worker.hubTone) : ""}
        </div>
        <div class="ops-detail-grid">
          <div><span>Műszak</span><strong>${escapeHtml(worker.shiftName || "-")}</strong><small>${escapeHtml(worker.bookingCode || "")}</small></div>
          <div><span>Autó</span><strong>${escapeHtml(vehicleText || "-")}</strong><small>${escapeHtml(worker.vehicle?.source || worker.vehicle?.shiftType || "")}</small></div>
          <div class="${loginAlert ? "ops-late-box" : ""}"><span>Giriton bejelentkezés</span><strong>${escapeHtml(loginText)}</strong><small>${escapeHtml(loginSubtext)}</small></div>
          <div><span>Eltérés</span><strong>${escapeHtml(worker.missingSource || "Nincs jelzett eltérés")}</strong><small>Giriton / MűszakPro összevetés</small></div>
          <div><span>Forrás</span><strong>${escapeHtml(worker.source || "-")}</strong><small>${escapeHtml(worker.date || "")}</small></div>
        </div>
      </div>
    </details>
  `;
}

function scheduleSlotLabel(slot = {}) {
  const free = Number(slot.freeSlots || 0);
  const suffix = free > 1 ? ` · ${formatCount(free)} szabad` : "";
  return `${slot.start || "-"}${slot.end ? `-${slot.end}` : ""}${suffix}`;
}

function scheduleSlotTone(slot = {}) {
  const opened = Number(slot.opened || 0);
  const assigned = Number(slot.assigned || 0);
  const free = Number(slot.freeSlots || 0);
  const status = String(slot.status || "OPEN").toUpperCase();
  if (status === "NOT_UPLOADED") return "missing";
  if (opened <= 0) return "closed";
  if (free > 0 || assigned < opened) return "open";
  if (opened > 0 && assigned >= opened) return "full";
  return "closed";
}

function scheduleSlotStatusText(slot = {}) {
  const tone = scheduleSlotTone(slot);
  if (tone === "full") return "Tele";
  if (tone === "open") return `${formatCount(slot.freeSlots || 0)} szabad`;
  if (tone === "missing") return "Nincs feltöltve";
  return "Nincs nyitott slot";
}

function scheduleSlotCapacityText(slot = {}) {
  if (scheduleSlotTone(slot) === "missing") return `${formatCount(slot.assigned || 0)} beosztva`;
  const opened = Number(slot.opened || 0);
  if (opened <= 0) return "0 · Nincs közzétéve";
  return `${formatCount(slot.assigned || 0)}/${formatCount(opened)}`;
}

function scheduleSlotPreparedText(slot = {}) {
  const status = String(slot.status || "").trim();
  if (status && status.toUpperCase() !== "OPEN") return status;
  if (slot.capacityPublished) return "Közzétéve";
  return "Előkészületben";
}

function vehicleConfigLabel(item = {}) {
  return [
    item.licensePlate || "-",
    [item.brand, item.model].filter(Boolean).join(" "),
    item.carStatusLabel || "",
  ].filter(Boolean).join(" · ");
}

function scheduleVehicleConfigs() {
  return state.scheduleVehicleConfigurations?.length
    ? state.scheduleVehicleConfigurations
    : state.vehicleConfigurations || [];
}

function scheduleVehicleOptions(slot = {}, selectedVehicle = null) {
  const warehouse = String(slot.warehouse || "").trim().toUpperCase();
  const seen = new Set();
  const items = [];
  const add = (item) => {
    const plate = String(item?.licensePlate || "").trim();
    if (!plate || seen.has(plate)) return;
    seen.add(plate);
    items.push(item);
  };
  scheduleVehicleConfigs()
    .filter((item) => item?.active !== false)
    .filter((item) => !warehouse || String(item.warehouseCode || "").toUpperCase() === warehouse)
    .filter((item) => ["assignable", "garage_master", "other"].includes(String(item.carStatus || "assignable")))
    .sort((a, b) => String(a.licensePlate || "").localeCompare(String(b.licensePlate || ""), "hu"))
    .forEach(add);
  if (selectedVehicle) add(selectedVehicle);
  return items;
}

function scheduleRecommendedVehicle(worker = {}, slot = {}) {
  const courierId = String(worker.courierId || "").trim();
  const warehouse = String(slot.warehouse || worker.warehouse || "").trim().toUpperCase();
  const configs = scheduleVehicleConfigs().filter((item) => item?.active !== false);
  const dedicated = configs.find((item) =>
    String(item.dedicatedCourierId || "").trim() === courierId
    && (!warehouse || String(item.warehouseCode || "").toUpperCase() === warehouse)
  );
  if (dedicated) return dedicated;
  const plate = String(worker.vehicle?.licensePlate || "").trim().toUpperCase();
  if (plate) {
    return configs.find((item) => String(item.licensePlate || "").trim().toUpperCase() === plate) || { licensePlate: plate };
  }
  return null;
}

function vehicleConfigAssignmentPayload(item = {}, courierId = "", courierName = "") {
  return {
    jitt_car_id: item.jittCarId || "",
    license_plate: item.licensePlate || "",
    warehouse_code: item.warehouseCode || "BUD1",
    brand: item.brand || "",
    model: item.model || "",
    ownership_type: item.ownershipType || "own",
    rental_company: item.rentalCompany || "",
    toll_vignette_type: item.tollVignetteType || "none",
    toll_counties: item.tollCounties || [],
    toll_valid_from: item.tollValidFrom || "",
    toll_valid_to: item.tollValidTo || "",
    service_from: item.serviceFrom || "",
    service_to: item.serviceTo || "",
    service_location: item.serviceLocation || "",
    car_status: item.carStatus || "assignable",
    condition_status: item.conditionStatus || "ok",
    condition_description: item.conditionDescription || "",
    minimum_daily_rounds: item.minimumDailyRounds || null,
    enforce_minimum_daily_rounds: Boolean(item.enforceMinimumDailyRounds),
    dedicated_courier_id: Number(courierId || 0) || null,
    dedicated_courier_name: courierName || "",
    active: item.active !== false,
  };
}

function scheduleDayVehicleRows(day = {}) {
  const rows = [];
  const seen = new Set();
  (day.slots || []).forEach((slot) => {
    (slot.workers || []).forEach((worker) => {
      const key = `${slot.date || day.date || ""}|${slot.start || ""}|${worker.courierId || worker.courierName || ""}`;
      if (seen.has(key)) return;
      seen.add(key);
      rows.push({ slot, worker });
    });
  });
  const sortMode = state.scheduleVehicleSort || "time";
  return rows.sort((a, b) => (
    sortMode === "routes"
      ? Number(b.worker?.dailyRouteCount || 0) - Number(a.worker?.dailyRouteCount || 0)
        || String(a.worker?.courierName || "").localeCompare(String(b.worker?.courierName || ""), "hu")
        || (Number.isFinite(Number(a.slot?.startMinutes)) ? Number(a.slot?.startMinutes) : 99999)
          - (Number.isFinite(Number(b.slot?.startMinutes)) ? Number(b.slot?.startMinutes) : 99999)
      : sortMode === "name"
        ? String(a.worker?.courierName || "").localeCompare(String(b.worker?.courierName || ""), "hu")
          || (Number.isFinite(Number(a.slot?.startMinutes)) ? Number(a.slot?.startMinutes) : 99999)
            - (Number.isFinite(Number(b.slot?.startMinutes)) ? Number(b.slot?.startMinutes) : 99999)
        : (Number.isFinite(Number(a.slot?.startMinutes)) ? Number(a.slot?.startMinutes) : 99999)
          - (Number.isFinite(Number(b.slot?.startMinutes)) ? Number(b.slot?.startMinutes) : 99999)
          || String(a.worker?.courierName || "").localeCompare(String(b.worker?.courierName || ""), "hu")
  ));
}

function renderScheduleVehicleAssignmentRow(row = {}, index = 0) {
  const slot = row.slot || {};
  const worker = row.worker || {};
  const hasCourierId = Boolean(String(worker.courierId || "").trim());
  const recommendedVehicle = scheduleRecommendedVehicle(worker, slot);
  const vehicleOptions = scheduleVehicleOptions(slot, recommendedVehicle);
  const selectedPlate = String(recommendedVehicle?.licensePlate || worker.vehicle?.licensePlate || "").trim();
  return `
    <article class="schedule-vehicle-row" data-schedule-vehicle-row>
      <div class="schedule-vehicle-row-main">
        <span>${escapeHtml(slot.start || "-")}${slot.end ? `-${escapeHtml(slot.end)}` : ""}</span>
        <strong>${escapeHtml(worker.courierName || "Futár")}</strong>
        <small>#${escapeHtml(worker.courierId || "-")} · ${escapeHtml(worker.shiftName || worker.bookingCode || slot.shiftText || "Műszak")} · ${formatCount(worker.dailyRouteCount || 0)} kör ma</small>
      </div>
      <div class="schedule-vehicle-row-current">
        <span>Jelenlegi / ajánlott</span>
        <strong>${escapeHtml(selectedPlate || "-")}</strong>
        <small>${escapeHtml(recommendedVehicle ? vehicleConfigLabel(recommendedVehicle) : "Nincs beállított ajánlás")}</small>
      </div>
      <div class="schedule-slot-action-row">
        <select data-schedule-vehicle-select ${vehicleOptions.length && hasCourierId ? "" : "disabled"}>
          ${vehicleOptions.length
            ? vehicleOptions.map((item) => `<option value="${escapeHtml(item.licensePlate)}" ${String(item.licensePlate || "") === selectedPlate ? "selected" : ""}>${escapeHtml(vehicleConfigLabel(item))}</option>`).join("")
            : `<option value="">Nincs felvett autó ehhez a raktárhoz</option>`}
        </select>
        <button type="button"
          data-schedule-vehicle-save
          data-work-date="${escapeHtml(slot.date || "")}"
          data-warehouse="${escapeHtml(slot.warehouse || "")}"
          data-courier-id="${escapeHtml(worker.courierId || "")}"
          data-courier-name="${escapeHtml(worker.courierName || "Futár")}"
          ${vehicleOptions.length && hasCourierId ? "" : "disabled"}>
          Mentés
        </button>
      </div>
      <div class="schedule-slot-action-status" data-schedule-vehicle-status role="status" aria-live="polite"></div>
    </article>
  `;
}

function ensureScheduleVehicleDialog() {
  let dialog = $("#schedule-vehicle-dialog");
  if (dialog) return dialog;
  dialog = document.createElement("dialog");
  dialog.id = "schedule-vehicle-dialog";
  dialog.className = "worker-shift-dialog schedule-vehicle-dialog";
  dialog.innerHTML = `
    <div class="worker-shift-dialog-card">
      <div class="worker-shift-dialog-head">
        <div>
          <span>Autóbeosztás</span>
          <strong data-schedule-vehicle-title>Napi autóbeosztás</strong>
          <small data-schedule-vehicle-subtitle></small>
        </div>
        <button type="button" class="icon-btn" data-schedule-vehicle-close>×</button>
      </div>
      <div class="schedule-vehicle-toolbar">
        <label>
          <span>Rendezés</span>
          <select data-schedule-vehicle-sort>
            <option value="time">Műszak kezdése szerint</option>
            <option value="name">Futár név szerint</option>
            <option value="routes">Körszám szerint (4-3-2-1)</option>
          </select>
        </label>
      </div>
      <div class="schedule-vehicle-list" data-schedule-vehicle-list></div>
    </div>
  `;
  document.body.appendChild(dialog);
  dialog.querySelector("[data-schedule-vehicle-close]")?.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  dialog.addEventListener("click", (event) => {
    const button = event.target.closest("[data-schedule-vehicle-save]");
    if (!button) return;
    saveScheduleVehicleAssignment(button);
  });
  dialog.querySelector("[data-schedule-vehicle-sort]")?.addEventListener("change", (event) => {
    state.scheduleVehicleSort = event.target.value || "time";
    renderScheduleVehicleDialogRows(dialog);
  });
  return dialog;
}

function renderScheduleVehicleDialogRows(dialog = ensureScheduleVehicleDialog()) {
  const day = dialog._scheduleVehicleDay || {};
  const rows = scheduleDayVehicleRows(day);
  const sort = dialog.querySelector("[data-schedule-vehicle-sort]");
  if (sort && sort.value !== state.scheduleVehicleSort) sort.value = state.scheduleVehicleSort || "time";
  dialog.querySelector("[data-schedule-vehicle-title]").textContent = day?.date ? dateLabel(day.date) : "Napi autóbeosztás";
  const sortLabel = state.scheduleVehicleSort === "routes" ? "körszám szerint" : state.scheduleVehicleSort === "name" ? "futárnév szerint" : "időrendben";
  dialog.querySelector("[data-schedule-vehicle-subtitle]").textContent = `${formatCount(rows.length)} műszak ${sortLabel}`;
  dialog.querySelector("[data-schedule-vehicle-list]").innerHTML = rows.length
    ? rows.map(renderScheduleVehicleAssignmentRow).join("")
    : `<div class="empty-card compact">Nincs futár ehhez a naphoz.</div>`;
}

function openScheduleVehicleDialog(day = {}) {
  const dialog = ensureScheduleVehicleDialog();
  dialog._scheduleVehicleDay = day;
  renderScheduleVehicleDialogRows(dialog);
  dialog.showModal();
}

async function saveScheduleVehicleAssignment(button) {
  const panel = button.closest("[data-schedule-vehicle-row]");
  const select = panel?.querySelector("[data-schedule-vehicle-select]");
  const status = panel?.querySelector("[data-schedule-vehicle-status]");
  const plate = String(select?.value || "").trim();
  const courierId = button.dataset.courierId || "";
  const courierName = button.dataset.courierName || "Futár";
  const item = scheduleVehicleConfigs().find((row) => String(row.licensePlate || "") === plate);
  if (!item || !courierId) return;
  if (status) {
    status.classList.add("active");
    status.classList.remove("error");
    status.textContent = `${courierName} (#${courierId}) autó beállítása: ${plate}...`;
  }
  button.disabled = true;
  if (select) select.disabled = true;
  try {
    await api("/api/vehicles/configurations", {
      method: "POST",
      body: JSON.stringify(vehicleConfigAssignmentPayload(item, courierId, courierName)),
    });
    await loadScheduleVehicleConfigurations({ force: true });
    if (status) status.textContent = `${courierName} (#${courierId}) ajánlott autója mentve: ${plate}.`;
    loadCoordinatorScheduleDay(state.coordinatorScheduleDay, { keepRendered: true, full: true, preserveScroll: true }).catch(() => {});
  } catch (error) {
    if (status) {
      status.classList.add("active", "error");
      status.textContent = error.message || "Az autó beállítása nem sikerült.";
    }
  } finally {
    button.disabled = false;
    if (select) select.disabled = false;
  }
}

function renderScheduleSlotWorker(worker = {}, slot = {}, day = {}) {
  const phone = String(worker.phoneNumber || "").trim();
  const hasCourierId = Boolean(String(worker.courierId || "").trim());
  const slotHasBookedCapacity = Number(slot.assigned || 0) > 0 && Number(slot.opened || 0) > 0;
  const hubBooked = worker.hubTone === "ok" || String(worker.hubStatus || "").toLowerCase().includes("felvezet") || slotHasBookedCapacity;
  const recommendedVehicle = scheduleRecommendedVehicle(worker, slot);
  const attendanceStatus = String(worker.attendanceStatus || "");
  const sentHome = attendanceStatus === "sent_home";
  const dailyRouteCount = Number(worker.dailyRouteCount || 0);
  const attendanceMeta = worker.attendanceMarkedAt
    ? ` · ${shortDateTime(worker.attendanceMarkedAt)}${worker.attendanceMarkedBy ? ` · ${worker.attendanceMarkedBy}` : ""}`
    : "";
  return `
    <div class="schedule-slot-worker">
      <div class="schedule-slot-worker-head">
        <span>
          <strong>${escapeHtml(worker.courierName || "Futár")}</strong>
          <small>#${escapeHtml(worker.courierId || "-")} · ${escapeHtml(worker.shiftName || worker.bookingCode || "Műszak")} · ${formatCount(dailyRouteCount)} kör ma</small>
          <small>Autó: ${escapeHtml(recommendedVehicle?.licensePlate || worker.vehicle?.licensePlate || "-")}</small>
        </span>
      </div>
      <div class="schedule-chip-row">
        ${scheduleStatusChip(`MűszakPro: ${String(worker.muszakproStatus || "Nincs adat").toLocaleUpperCase("hu-HU")}`, worker.muszakproTone)}
        ${scheduleStatusChip(`Hub: ${String(worker.hubStatus || "Nincs adat").toLocaleUpperCase("hu-HU")}`, worker.hubTone)}
        ${attendanceStatus ? scheduleStatusChip(`Jelenlét: ${workerAttendanceLabel(attendanceStatus)}${attendanceMeta}`, sentHome ? "missing" : "ok") : ""}
      </div>
      <div class="schedule-slot-worker-meta">
        <span>MűszakPro: ${escapeHtml(shortDateTime(worker.muszakproBookedAt || "") || "-")}</span>
        <span>Hub: ${escapeHtml(shortDateTime(worker.hubUploadedAt || "") || "-")}</span>
        ${phone ? `<a href="tel:${escapeHtml(phone)}">${escapeHtml(phone)}</a>` : `<span>Telefon: -</span>`}
      </div>
      ${hubBooked ? `
        <div class="schedule-slot-actions">
          <button type="button"
            data-schedule-delete-prep
            data-work-date="${escapeHtml(slot.date || "")}"
            data-warehouse="${escapeHtml(slot.warehouse || "")}"
            data-shift-template-id="${escapeHtml(slot.shiftTemplateId || "")}"
            data-slot-from="${escapeHtml(slot.start || "")}"
            data-courier-id="${escapeHtml(worker.courierId || "")}"
            data-courier-name="${escapeHtml(worker.courierName || "Futár")}"
            disabled>
            Törlés inaktív
          </button>
          ${sentHome ? `<span class="schedule-sent-home-label">Hazaküldték</span>` : ""}
          <button type="button"
            class="${sentHome ? "active" : ""}"
            data-schedule-sent-home
            data-work-date="${escapeHtml(slot.date || "")}"
            data-warehouse="${escapeHtml(slot.warehouse || "")}"
            data-start="${escapeHtml(slot.start || "")}"
            data-end="${escapeHtml(slot.end || "")}"
            data-booking-code="${escapeHtml(worker.bookingCode || "")}"
            data-shift-name="${escapeHtml(worker.shiftName || worker.bookingCode || "")}"
            data-courier-id="${escapeHtml(worker.courierId || "")}"
            data-courier-name="${escapeHtml(worker.courierName || "Futár")}"
            ${hasCourierId && !sentHome ? "" : "disabled"}>
            ${sentHome ? "Haza küldve" : "Haza küldték"}
          </button>
          <div class="schedule-slot-action-status" data-schedule-action-status role="status" aria-live="polite"></div>
        </div>
      ` : ""}
    </div>
  `;
}

function scheduleRecommendationShiftLabel(shift = {}) {
  const time = `${shift.start || "-"}${shift.end ? `-${shift.end}` : ""}`;
  const name = shift.shiftName || shift.bookingCode || shift.shiftText || "Műszak";
  return `${time} · ${name}`;
}

function renderScheduleSlotRecommendationBadge(item = {}) {
  const needsMove = item.type === "move";
  return `
    <span class="schedule-slot-rec-pill ${needsMove ? "move" : "direct"}">
      ${needsMove ? `<i aria-hidden="true">!</i>` : ""}
      ${escapeHtml(item.courierName || "Futár")}
    </span>
  `;
}

function renderScheduleSlotRecommendationDetail(item = {}) {
  const phone = String(item.phoneNumber || "").trim();
  const current = (item.currentShifts || [])
    .map((shift) => scheduleRecommendationShiftLabel(shift))
    .join(", ");
  const target = scheduleSlotLabel(item.targetSlot || {});
  const move = item.moveSuggestion || {};
  const moveText = item.type === "move"
    ? `${scheduleRecommendationShiftLabel(move.moveFrom || {})} átrakása ide: ${scheduleSlotLabel(move.moveTo || {})}`
    : "Nem kell átszervezni, közvetlenül befér.";
  return `
    <article class="schedule-slot-rec-card ${item.type === "move" ? "move" : "direct"}">
      <div>
        <strong>${item.type === "move" ? `<span class="schedule-rec-alert">!</span>` : ""}${escapeHtml(item.courierName || "Futár")}</strong>
        <small>#${escapeHtml(item.courierId || "-")} · ${escapeHtml(item.warehouse || "-")}</small>
      </div>
      <div class="schedule-slot-rec-lines">
        <span>Cél: ${escapeHtml(target || "-")}</span>
        <span>Most: ${escapeHtml(current || "-")}</span>
        <span>${escapeHtml(moveText)}</span>
      </div>
      <div class="schedule-slot-rec-foot">
        <small>${escapeHtml(item.reason || "")}</small>
        ${phone ? `<a href="tel:${escapeHtml(phone)}">${escapeHtml(phone)}</a>` : `<span>Telefon: -</span>`}
      </div>
    </article>
  `;
}

function renderScheduleSlotRecommendations(slot = {}) {
  const recommendations = slot.recommendations || [];
  const tone = scheduleSlotTone(slot);
  if (!recommendations.length) {
    if (tone !== "open") return "";
    return `
      <div class="schedule-slot-rec-section empty">
        <div class="device-history-head compact">
          <strong>Ajánlás</strong>
          <span>0 találat</span>
        </div>
        <div class="empty-card compact">Nincs ajánlható futár erre a szabad slotra a raktár és a 4 óra 45 perc szabály alapján.</div>
      </div>
    `;
  }
  return `
    <div class="schedule-slot-rec-section">
      <div class="device-history-head compact">
        <strong>Ajánlás</strong>
        <span>${formatCount(recommendations.length)} találat</span>
      </div>
      <div class="schedule-slot-rec-list">${recommendations.map(renderScheduleSlotRecommendationDetail).join("")}</div>
    </div>
  `;
}

function scheduleIdentityText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase();
}

function scheduleBookingCandidates(slot = {}, day = {}) {
  const used = new Set((slot.workers || []).map((worker) =>
    String(worker.courierId || "").trim() || scheduleIdentityText(worker.courierName || "")
  ));
  const items = [];
  const add = (worker = {}, source = "") => {
    const courierId = String(worker.courierId || "").trim();
    const courierName = String(worker.courierName || "Futár").trim();
    const identity = courierId || scheduleIdentityText(courierName);
    if (!identity || used.has(identity)) return;
    if (items.some((item) => item.identity === identity)) return;
    items.push({
      identity,
      courierId,
      courierName,
      source,
      label: `${courierName}${courierId ? ` · #${courierId}` : ""}${source ? ` · ${source}` : ""}`,
    });
  };
  (slot.recommendations || []).forEach((item) => add(item, "ajánlott"));
  (day.workers || [])
    .filter((worker) => !slot.warehouse || worker.warehouse === slot.warehouse)
    .forEach((worker) => add(worker, "napi lista"));
  return items.sort((a, b) => a.label.localeCompare(b.label, "hu"));
}

function renderScheduleSlotBookingPrep(slot = {}, day = {}) {
  if (scheduleSlotTone(slot) !== "open") return "";
  const candidates = scheduleBookingCandidates(slot, day);
  return `
    <div class="schedule-slot-action-panel">
      <div>
        <strong>Foglalás indítása</strong>
        <small>Éles Hub foglalás; siker után a napi Hub adat frissül.</small>
      </div>
      <div class="schedule-slot-action-row">
        <select data-schedule-booking-courier ${candidates.length ? "" : "disabled"}>
          ${candidates.length
            ? candidates.map((item) => `<option value="${escapeHtml(item.identity)}" data-courier-id="${escapeHtml(item.courierId)}" data-courier-name="${escapeHtml(item.courierName)}">${escapeHtml(item.label)}</option>`).join("")
            : `<option value="">Nincs választható futár ebben a napi listában</option>`}
        </select>
        <button type="button"
          data-schedule-booking-prep
          data-work-date="${escapeHtml(slot.date || "")}"
          data-warehouse="${escapeHtml(slot.warehouse || "")}"
          data-shift-template-id="${escapeHtml(slot.shiftTemplateId || "")}"
          data-slot-from="${escapeHtml(slot.start || "")}"
          ${candidates.length ? "" : "disabled"}>
          Foglalás indítása
        </button>
      </div>
      <div class="schedule-slot-action-status" data-schedule-action-status role="status" aria-live="polite"></div>
    </div>
  `;
}

function renderScheduleSlotDetails(slot = {}, day = {}) {
  const workers = slot.workers || [];
  const workerRoundCount = (worker = {}, source = "") => {
    const sourceCount = source === "muszakpro"
      ? Number(worker.dailyMuszakproShiftCount || 0)
      : source === "hub"
        ? Number(worker.dailyHubShiftCount || 0)
        : Number(worker.dailyRouteCount || 0);
    if (sourceCount > 0) return sourceCount;
    const text = `${worker.shiftName || ""} ${worker.bookingCode || ""}`.toLocaleLowerCase("hu-HU");
    const match = text.match(/(\d+)\s*[- ]?\s*kör/);
    return match ? Math.max(1, Number(match[1])) : 1;
  };
  const muszakproCount = workers
    .filter((worker) => worker.muszakproTone === "ok")
    .reduce((total, worker) => total + workerRoundCount(worker, "muszakpro"), 0);
  const hubCount = workers
    .filter((worker) => worker.hubTone === "ok")
    .reduce((total, worker) => total + workerRoundCount(worker, "hub"), 0);
  const muszakproKnown = workers.some((worker) => worker.muszakproTone && worker.muszakproTone !== "unknown");
  const hubKnown = workers.some((worker) => worker.hubTone && worker.hubTone !== "unknown");
  const dailyRouteCount = Math.max(0, ...workers.map((worker) => Number(worker.dailyRouteCount || 0)));
  const routeCountMismatch = muszakproKnown && dailyRouteCount > 0 && muszakproCount !== dailyRouteCount;
  const bookingMismatch = routeCountMismatch || (muszakproKnown && hubKnown && muszakproCount !== hubCount);
  return `
    <div class="schedule-slot-details${bookingMismatch ? " schedule-slot-details-mismatch" : ""}">
      <div class="schedule-slot-detail-grid">
        <div><span>Állapot</span><strong>${escapeHtml(scheduleSlotPreparedText(slot))}</strong></div>
        <div><span>MűszakPro foglalt kör</span><strong>${muszakproCount ? `${formatCount(muszakproCount)} kör` : "-"}</strong></div>
        <div><span>Courier Hub / Kifli foglalt kör</span><strong>${hubKnown ? `${formatCount(hubCount)} kör` : "-"}</strong></div>
      </div>
      ${bookingMismatch ? `<div class="schedule-slot-mismatch-note">Eltérés: napi kör ${formatCount(dailyRouteCount)} · MűszakPro ${formatCount(muszakproCount)} kör${hubKnown ? ` · Hub/Kifli ${formatCount(hubCount)} kör` : ""}</div>` : ""}
      ${workers.length
        ? `<div class="schedule-slot-worker-list">${workers.map((worker) => renderScheduleSlotWorker(worker, slot, day)).join("")}</div>`
        : `<div class="empty-card compact">Nincs ehhez az idősávhoz kapcsolt futáradat.</div>`}
      ${renderScheduleSlotRecommendations(slot)}
      ${renderScheduleSlotBookingPrep(slot, day)}
    </div>
  `;
}

function scheduleSlotDomKey(slot = {}) {
  return [
    slot.date || "",
    slot.warehouse || "",
    slot.blockKey || "",
    slot.shiftTemplateId || "",
    slot.start || "",
    slot.end || "",
  ].join("|");
}

function renderScheduleSlotWorkerPreview(slot = {}) {
  const workers = slot.workers || [];
  if (!workers.length) return "";
  const visibleWorkers = workers.slice(0, 2);
  const moreCount = Math.max(0, workers.length - visibleWorkers.length);
  const chips = visibleWorkers.map((worker) => {
    const courierId = String(worker.courierId || "").trim();
    const routeCount = Number(worker.dailyRouteCount || 0);
    const idText = courierId ? ` #${courierId}` : "";
    return `<span>${escapeHtml(worker.courierName || "Futár")}${escapeHtml(idText)} · ${formatCount(routeCount)} kör ma</span>`;
  });
  if (moreCount) chips.push(`<span>+${formatCount(moreCount)} futár</span>`);
  return `<div class="schedule-slot-worker-preview">${chips.join("")}</div>`;
}

function scheduleSlotMaxRouteCount(slot = {}) {
  return Math.max(0, ...(slot.workers || []).map((worker) => Number(worker.dailyRouteCount || 0)));
}

function renderScheduleSlotRouteAlert(slot = {}) {
  const routeCount = scheduleSlotMaxRouteCount(slot);
  if (routeCount <= 0) return "";
  const level = routeCount > 3 ? "high" : routeCount === 3 ? "medium" : routeCount === 2 ? "low" : "faint";
  return `<span class="schedule-route-alert ${level}" title="${escapeHtml(formatCount(routeCount))} kör ma">!</span>`;
}

function renderScheduleSlotCard(slot = {}, day = {}) {
  const tone = scheduleSlotTone(slot);
  const recommendations = slot.recommendations || [];
  const workerPreview = renderScheduleSlotWorkerPreview(slot);
  const routeAlert = renderScheduleSlotRouteAlert(slot);
  const workers = slot.workers || [];
  const rounds = (worker, source = "") => {
    const sourceCount = source === "muszakpro"
      ? Number(worker.dailyMuszakproShiftCount || 0)
      : source === "hub"
        ? Number(worker.dailyHubShiftCount || 0)
        : Number(worker.dailyRouteCount || 0);
    if (sourceCount > 0) return sourceCount;
    const text = `${worker.shiftName || ""} ${worker.bookingCode || ""}`.toLocaleLowerCase("hu-HU");
    const match = text.match(/(\d+)\s*[- ]?\s*kör/);
    return match ? Math.max(1, Number(match[1])) : 1;
  };
  const muszakproRounds = workers.filter((worker) => worker.muszakproTone === "ok").reduce((total, worker) => total + rounds(worker, "muszakpro"), 0);
  const hubRounds = workers.filter((worker) => worker.hubTone === "ok").reduce((total, worker) => total + rounds(worker, "hub"), 0);
  const muszakproKnown = workers.some((worker) => worker.muszakproTone && worker.muszakproTone !== "unknown");
  const hubKnown = workers.some((worker) => worker.hubTone && worker.hubTone !== "unknown");
  const dailyRouteCount = Math.max(0, ...workers.map((worker) => Number(worker.dailyRouteCount || 0)));
  const routeCountMismatch = muszakproKnown && dailyRouteCount > 0 && muszakproRounds !== dailyRouteCount;
  const bookingMismatch = routeCountMismatch || (muszakproKnown && hubKnown && muszakproRounds !== hubRounds);
  return `
    <details class="schedule-slot-card ${tone}${bookingMismatch ? " booking-mismatch" : ""}" data-schedule-slot="${escapeHtml(scheduleSlotDomKey(slot))}">
      <summary>
        <div>
          <strong>${escapeHtml(slot.start || "-")}${slot.end ? `-${escapeHtml(slot.end)}` : ""}</strong>
          <small>${escapeHtml(slot.shiftText || slot.blockKey || "Műszak")}</small>
          ${workerPreview}
        </div>
        <div>
          <span>Kapacitás</span>
          <b>${escapeHtml(scheduleSlotCapacityText(slot))}</b>
        </div>
        <div class="schedule-slot-status-stack">
          <em>${escapeHtml(scheduleSlotStatusText(slot))}</em>
          ${routeAlert}
        </div>
        ${tone === "open" && recommendations.length
          ? `<div class="schedule-slot-rec-badges">${recommendations.map(renderScheduleSlotRecommendationBadge).join("")}</div>`
          : ""}
      </summary>
      ${renderScheduleSlotDetails(slot, day)}
    </details>
  `;
}

function preserveScrollAfterRender(previousScrollY) {
  if (typeof previousScrollY !== "number") return;
  requestAnimationFrame(() => {
    requestAnimationFrame(() => window.scrollTo({ top: previousScrollY, behavior: "auto" }));
  });
}

function renderScheduleSlots(day = {}) {
  const slots = day.slots || [];
  return `
    <section class="schedule-slots">
      <div class="device-history-head">
        <strong>Napi műszaknaptár</strong>
        <span>${formatCount(slots.length)} idősáv</span>
      </div>
      ${slots.length
        ? `<div class="schedule-slot-grid">${slots.map((slot) => renderScheduleSlotCard(slot, day)).join("")}</div>`
        : `<div class="empty-card">Ehhez a naphoz nincs betöltött részletes slotlista. Futtasd a HUB shift block frissítést erre a napra.</div>`}
    </section>
  `;
}

function renderScheduleRecommendation(item = {}) {
  const phone = String(item.phoneNumber || "").trim();
  const current = (item.currentShifts || [])
    .map((shift) => shift.start || "")
    .filter(Boolean)
    .join(", ");
  const directSlots = (item.recommendedSlots || [])
    .map((slot) => `<span>${escapeHtml(scheduleSlotLabel(slot))}</span>`)
    .join("");
  const moveSuggestions = (item.moveSuggestions || []).map((suggestion) => `
    <div class="schedule-move-row">
      <strong>${escapeHtml(suggestion.newSlot?.start || "-")}</strong>
      <small>${escapeHtml(suggestion.moveFrom?.start || "-")} csúsztatása ide: ${escapeHtml(suggestion.moveTo?.start || "-")}</small>
    </div>
  `).join("");
  return `
    <article class="schedule-recommendation ${item.type === "move" ? "move" : ""}">
      <div>
        <strong>${escapeHtml(item.courierName || "Futár")}</strong>
        <small>#${escapeHtml(item.courierId || "-")} · ${escapeHtml(item.warehouse || "-")} · most: ${escapeHtml(current || "-")}</small>
      </div>
      <div class="schedule-rec-slots">
        ${directSlots || moveSuggestions || `<span>Nincs közvetlen slot</span>`}
      </div>
      <div class="schedule-rec-foot">
        <small>${escapeHtml(item.reason || "")}</small>
        ${phone ? `<a href="tel:${escapeHtml(phone)}">${escapeHtml(phone)}</a>` : `<span>Nincs telefonszám</span>`}
      </div>
    </article>
  `;
}

function renderScheduleRecommendations(day = {}) {
  const recommendations = day.recommendations || [];
  return `
    <section class="schedule-recommendations">
      <div class="device-history-head">
        <strong>Ajánlás</strong>
        <span>${formatCount(recommendations.length)} találat</span>
      </div>
      ${recommendations.length
        ? `<div class="schedule-recommendation-list">${recommendations.map(renderScheduleRecommendation).join("")}</div>`
        : `<div class="empty-card">Nincs ajánlható futár a 4 óra 45 perc szabály és az aktuális raktár alapján.</div>`}
    </section>
  `;
}

function renderCoordinatorScheduleDayDetail(payload, day) {
  const workers = day?.workers || [];
  const previousDay = adjacentScheduleDay(payload, day?.date, -1);
  const nextDay = adjacentScheduleDay(payload, day?.date, 1);
  const dayCoverage = day?.capacityKnown ? scheduleCoverageText(day) : "-";
  const daySlotValue = day?.capacityKnown
    ? `${formatCount(day.bookedSlots || 0)}/${formatCount(day.requiredSlots || 0)}`
    : "-";
  const dayMissingValue = day?.capacityKnown ? formatCount(day.missingSlots || 0) : "-";
  const selectedSlotText = day?.capacityKnown
    ? `${scheduleSlotText(day)} slot · ${scheduleCoverageText(day)}`
    : "Nincs slot adat";
  return `
    ${payload.error ? `<div class="notice error">A beosztás nem tölthető be: ${escapeHtml(payload.error)}</div>` : ""}
    <section class="schedule-day-detail">
      <div class="schedule-day-nav">
        <button class="ghost-btn schedule-back-btn" type="button" data-schedule-back>Vissza a naptárhoz</button>
        <button class="ghost-btn" type="button" data-schedule-prev-day="${escapeHtml(previousDay?.date || "")}" ${previousDay ? "" : "disabled"}>Előző nap</button>
        <button class="ghost-btn" type="button" data-schedule-next-day="${escapeHtml(nextDay?.date || "")}" ${nextDay ? "" : "disabled"}>Következő nap</button>
        <button class="ghost-btn" type="button" data-schedule-vehicles-open ${day?.detailsLoaded ? "" : "disabled"}>Autóbeosztás</button>
      </div>
      <div class="device-history-head">
        <strong>${day ? escapeHtml(dateLabel(day.date)) : "Nincs kiválasztott nap"}</strong>
        <span>${escapeHtml(selectedSlotText)} · ${formatCount(workers.length)} futár</span>
      </div>
      ${renderOpsSummary(day || {}, [
        ["Töltöttség", dayCoverage, "napi slot alapján"],
        ["Slot", daySlotValue, "foglalt / nyitott"],
        ["Hiány", dayMissingValue, "nyitott slot"],
      ])}
      ${day?.detailsLoaded ? renderScheduleSlots(day) : `<div class="empty-card">Napi műszakok betöltése...</div>`}
    </section>
  `;
}

function bindSchedulePrepActions(target) {
  target.querySelector("[data-schedule-vehicles-open]")?.addEventListener("click", async () => {
    await loadScheduleVehicleConfigurations();
    openScheduleVehicleDialog(selectedScheduleDay(state.coordinatorSchedule) || {});
  });
  target.querySelectorAll("[data-schedule-sent-home]").forEach((button) => {
    button.addEventListener("click", async () => {
      const panel = button.closest(".schedule-slot-worker") || button.closest(".schedule-slot-card");
      const status = panel?.querySelector("[data-schedule-action-status]");
      const name = button.dataset.courierName || "Futár";
      const id = button.dataset.courierId || "-";
      if (!id || id === "-") return;
      if (status) {
        status.classList.add("active");
        status.classList.remove("error");
        status.textContent = `${name} (#${id}) haza küldés mentése...`;
      }
      button.disabled = true;
      try {
        const result = await api("/api/coordinator/today-workers/attendance", {
          method: "POST",
          body: JSON.stringify({
            courier_id: id,
            courier_name: name,
            work_date: button.dataset.workDate || "",
            start: button.dataset.start || button.dataset.slotFrom || "",
            end: button.dataset.end || "",
            warehouse: button.dataset.warehouse || "",
            shift_name: button.dataset.shiftName || "",
            booking_code: button.dataset.bookingCode || "",
            attendance_status: "sent_home",
            note: "Beosztásból jelölve: haza küldték.",
          }),
        });
        if (status) {
          status.textContent = result?.discordSent === false
            ? `${name} (#${id}) haza küldve jelölve, de Discord webhook nincs beállítva vagy nem válaszolt.`
            : `${name} (#${id}) haza küldve jelölve, Discord értesítés elküldve.`;
        }
        state.coordinatorScheduleActionActive = false;
        await loadCoordinatorScheduleDay(state.coordinatorScheduleDay, { keepRendered: true, full: true, preserveScroll: true });
      } catch (error) {
        button.disabled = false;
        if (status) {
          status.classList.add("active", "error");
          status.textContent = error.message || "A haza küldés mentése nem sikerült.";
        }
      }
    });
  });
  target.querySelectorAll("[data-schedule-delete-prep]").forEach((button) => {
    button.addEventListener("click", async () => {
      const panel = button.closest(".schedule-slot-worker") || button.closest(".schedule-slot-card");
      const status = panel?.querySelector("[data-schedule-action-status]") || button.closest(".schedule-slot-card")?.querySelector("[data-schedule-action-status]");
      const name = button.dataset.courierName || "Futár";
      const id = button.dataset.courierId || "-";
      if (!id || id === "-") return;
      if (status) {
        status.classList.add("active");
        status.textContent = `${name} (#${id}) nevében törlés indítása...`;
      }
      state.coordinatorScheduleActionActive = true;
      button.disabled = true;
      try {
        const result = await api("/api/coordinator/schedule/hub-shift", {
          method: "POST",
          body: JSON.stringify({
            action: "delete",
            work_date: button.dataset.workDate || "",
            warehouse: button.dataset.warehouse || "",
            shift_template_id: Number(button.dataset.shiftTemplateId || 0),
            slot_from: button.dataset.slotFrom || "",
            courier_id: Number(id),
            courier_name: name,
          }),
        });
        if (status) {
          status.classList.add("active");
          status.textContent = result?.queued
            ? `${name} (#${id}) nevében törlési job elindítva. Állapot lekérése...`
            : `Törlés elküldve a Hubnak: ${name} (#${id}).`;
        }
        if (result?.queued) {
          pollScheduleHubActionJob(result, { status, button, name, id });
        }
      } catch (error) {
        button.disabled = false;
        state.coordinatorScheduleActionActive = false;
        if (status) {
          status.classList.add("active", "error");
          status.textContent = error.message || "A törlés nem sikerült.";
        }
      }
    });
  });
  target.querySelectorAll("[data-schedule-booking-prep]").forEach((button) => {
    button.addEventListener("click", async () => {
      const panel = button.closest(".schedule-slot-action-panel");
      const select = panel?.querySelector("[data-schedule-booking-courier]");
      const selected = select?.selectedOptions?.[0];
      const status = panel?.querySelector("[data-schedule-action-status]");
      const name = selected?.dataset?.courierName || selected?.textContent || "Futár";
      const id = selected?.dataset?.courierId || "-";
      if (!id || id === "-") return;
      if (status) {
        status.classList.add("active");
        status.textContent = `${name} (#${id}) nevében foglalás indítása...`;
      }
      state.coordinatorScheduleActionActive = true;
      button.disabled = true;
      if (select) select.disabled = true;
      try {
        const result = await api("/api/coordinator/schedule/hub-shift", {
          method: "POST",
          body: JSON.stringify({
            action: "book",
            work_date: button.dataset.workDate || "",
            warehouse: button.dataset.warehouse || "",
            shift_template_id: Number(button.dataset.shiftTemplateId || 0),
            slot_from: button.dataset.slotFrom || "",
            courier_id: Number(id),
            courier_name: name,
          }),
        });
        if (status) {
          status.classList.add("active");
          status.textContent = result?.queued
            ? `${name} (#${id}) nevében foglalási job elindítva. Állapot lekérése...`
            : `Foglalás elküldve a Hubnak: ${name} (#${id}).`;
        }
        if (result?.queued) {
          pollScheduleHubActionJob(result, { status, button, select, name, id });
        }
      } catch (error) {
        button.disabled = false;
        if (select) select.disabled = false;
        state.coordinatorScheduleActionActive = false;
        if (status) {
          status.classList.add("active", "error");
          status.textContent = error.message || "A foglalás nem sikerült.";
        }
      }
    });
  });
}

function scheduleHubActionLabel(result) {
  return result?.action === "delete" ? "Törlési" : "Foglalási";
}

function scheduleHubActionJobStatusText(job, result, name, id) {
  const run = job?.run_number ? ` #${job.run_number}` : "";
  const label = scheduleHubActionLabel(result);
  if (!job?.found) return `${name} (#${id}) nevében ${label.toLowerCase()} job keresése...`;
  if (job.status === "completed") {
    if (job.conclusion === "success") return `${name} (#${id}) nevében ${label.toLowerCase()} job sikeres${run}. Frissítés...`;
    return `${name} (#${id}) nevében ${label.toLowerCase()} job sikertelen${run}: ${job.conclusion || "hiba"}.`;
  }
  if (job.status === "in_progress") return `${name} (#${id}) nevében ${label.toLowerCase()} job fut${run}...`;
  return `${name} (#${id}) nevében ${label.toLowerCase()} job várakozik${run}...`;
}

function pollScheduleHubActionJob(result, { status, button, select, name, id, attempt = 0 }) {
  const triggeredAt = result?.triggered_at_iso || result?.triggered_at || "";
  const workflow = result?.workflow || "";
  const label = scheduleHubActionLabel(result);
  if (!triggeredAt) {
    if (status) {
      status.classList.add("active");
      status.textContent = `${name} (#${id}) nevében ${label.toLowerCase()} job elindítva. Pár perc múlva frissíts.`;
    }
    return;
  }
  window.setTimeout(async () => {
    try {
      const query = new URLSearchParams({ triggered_at: triggeredAt, workflow });
      const job = await api(`/api/coordinator/schedule/hub-shift-job-status?${query.toString()}`, {
        silentLoading: true,
      });
      if (status) {
        status.classList.add("active");
        status.classList.toggle("error", job?.status === "completed" && job?.conclusion !== "success");
        status.textContent = scheduleHubActionJobStatusText(job, result, name, id);
      }
      if (job?.status === "completed") {
        state.coordinatorScheduleActionActive = false;
        if (job.conclusion === "success") {
          loadCoordinatorScheduleDay(state.coordinatorScheduleDay, { keepRendered: true, full: true, preserveScroll: true }).catch(() => {});
          return;
        }
        if (button) button.disabled = false;
        if (select) select.disabled = false;
        return;
      }
      if (attempt + 1 >= SCHEDULE_BOOKING_JOB_MAX_POLLS) {
        state.coordinatorScheduleActionActive = false;
        if (status) {
          status.classList.add("active");
          status.textContent = `${name} (#${id}) nevében ${label.toLowerCase()} job még fut vagy nem található. Frissíts később.`;
        }
        if (button) button.disabled = false;
        if (select) select.disabled = false;
        return;
      }
      pollScheduleHubActionJob(result, { status, button, select, name, id, attempt: attempt + 1 });
    } catch (error) {
      if (attempt + 1 >= 3) {
        state.coordinatorScheduleActionActive = false;
        if (status) {
          status.classList.add("active", "error");
          status.textContent = error.message || "A job állapotát nem sikerült lekérni.";
        }
        if (button) button.disabled = false;
        if (select) select.disabled = false;
        return;
      }
      pollScheduleHubActionJob(result, { status, button, select, name, id, attempt: attempt + 1 });
    }
  }, SCHEDULE_BOOKING_JOB_POLL_MS);
}

function renderCoordinatorSchedule() {
  const target = $("#coordinator-schedule-panel");
  if (!target) return;
  const openSlotKeys = new Set(
    Array.from(target.querySelectorAll(".schedule-slot-card[open][data-schedule-slot]"))
      .map((item) => item.getAttribute("data-schedule-slot") || "")
      .filter(Boolean)
  );
  const payload = state.coordinatorSchedule;
  if (!payload) {
    target.innerHTML = `<div class="empty-card">Beosztás betöltése...</div>`;
    return;
  }
  const monthInput = $("#coordinator-schedule-month");
  if (monthInput && !monthInput.value) monthInput.value = payload.month || state.statisticsMonth;
  const day = selectedScheduleDay(payload);
  if (day && state.coordinatorScheduleDay !== day.date) state.coordinatorScheduleDay = day.date;
  const dayCoverage = day?.capacityKnown ? scheduleCoverageText(day) : "-";
  const daySlotValue = day?.capacityKnown
    ? `${formatCount(day.bookedSlots || 0)}/${formatCount(day.requiredSlots || 0)}`
    : "-";
  const dayMissingValue = day?.capacityKnown ? formatCount(day.missingSlots || 0) : "-";
  if (state.coordinatorScheduleView === "day") {
    target.innerHTML = renderCoordinatorScheduleDayDetail(payload, day);
    target.querySelectorAll(".schedule-slot-card[data-schedule-slot]").forEach((item) => {
      if (openSlotKeys.has(item.getAttribute("data-schedule-slot") || "")) item.setAttribute("open", "");
    });
    target.querySelector("[data-schedule-back]")?.addEventListener("click", () => {
      state.coordinatorScheduleView = "calendar";
      renderCoordinatorSchedule();
    });
    target.querySelectorAll("[data-schedule-prev-day], [data-schedule-next-day]").forEach((button) => {
      button.addEventListener("click", () => {
        const selectedDay = button.dataset.schedulePrevDay || button.dataset.scheduleNextDay || "";
        if (!selectedDay) return;
        state.coordinatorScheduleDay = selectedDay;
        state.coordinatorScheduleView = "day";
        loadCoordinatorScheduleDay(selectedDay);
      });
    });
    bindSchedulePrepActions(target);
    return;
  }
  target.innerHTML = `
    ${payload.error ? `<div class="notice error">A beosztás nem tölthető be: ${escapeHtml(payload.error)}</div>` : ""}
    ${renderOpsSummary(day || {}, [
      ["Töltöttség", dayCoverage, "napi slot alapján"],
      ["Slot", daySlotValue, "foglalt / nyitott"],
      ["Hiány", dayMissingValue, "nyitott slot"],
      ["Nap", day ? (day.label || day.date) : "-", "kiválasztva"],
    ])}
    <p class="updated-at">${escapeHtml(payload.month || "")} · Frissítve: ${escapeHtml(shortDateTime(payload.updatedAt || ""))}</p>
    <div class="schedule-day-grid">
      ${renderScheduleCalendarDays(payload.days || [])}
    </div>
  `;
  target.querySelectorAll("[data-schedule-day]").forEach((button) => {
    button.addEventListener("click", () => {
      state.coordinatorScheduleDay = button.dataset.scheduleDay || state.coordinatorScheduleDay;
      state.coordinatorScheduleView = "day";
      loadCoordinatorScheduleDay(state.coordinatorScheduleDay, { preserveScroll: true });
    });
  });
}

function mergeCoordinatorScheduleDay(payload) {
  const incomingDays = payload?.days || [];
  if (!state.coordinatorSchedule || !incomingDays.length) {
    state.coordinatorSchedule = payload;
    return;
  }
  const incomingByDate = new Map(incomingDays.map((day) => [day.date, day]));
  state.coordinatorSchedule.days = (state.coordinatorSchedule.days || []).map((day) =>
    incomingByDate.get(day.date) || day
  );
  state.coordinatorSchedule.updatedAt = payload.updatedAt || state.coordinatorSchedule.updatedAt;
  if (!payload.detailOnly) state.coordinatorSchedule.summary = payload.summary || state.coordinatorSchedule.summary;
}

function mergeCoordinatorScheduleMonth(payload) {
  const previous = state.coordinatorSchedule;
  if (!previous?.days?.length || !payload?.days?.length) {
    state.coordinatorSchedule = payload;
    return;
  }
  const detailedDays = new Map(
    previous.days
      .filter((day) => day?.detailsLoaded)
      .map((day) => [day.date, day])
  );
  state.coordinatorSchedule = {
    ...payload,
    days: payload.days.map((day) => {
      const detailed = detailedDays.get(day.date);
      return detailed ? { ...day, ...detailed } : day;
    }),
  };
}

async function loadCoordinatorSchedule() {
  const target = $("#coordinator-schedule-panel");
  const monthInput = $("#coordinator-schedule-month");
  const warehouseInput = $("#coordinator-schedule-warehouse");
  if (monthInput && !monthInput.value) monthInput.value = new Date().toISOString().slice(0, 7);
  const month = monthInput?.value || new Date().toISOString().slice(0, 7);
  const role = String(state.user?.role || "").toLowerCase();
  const warehouse = role === "admin" ? String(warehouseInput?.value || state.coordinatorScheduleWarehouse || "").trim() : "";
  if (role === "admin" && !warehouse) {
    state.coordinatorSchedule = null;
    if (target) target.innerHTML = `<div class="empty-card">Válassz raktárat, utána indítsd a beosztás lekérést.</div>`;
    return;
  }
  if (target && !state.coordinatorSchedule) target.innerHTML = `<div class="empty-card">Beosztás betöltése...</div>`;
  const requestSeq = ++state.coordinatorScheduleRequestSeq;
  try {
    const warehouseQuery = warehouse ? `&warehouse=${encodeURIComponent(warehouse)}` : "";
    const payload = await api(`/api/coordinator/schedule?month=${encodeURIComponent(month)}${warehouseQuery}`);
    if (requestSeq !== state.coordinatorScheduleRequestSeq) return;
    mergeCoordinatorScheduleMonth(payload);
    if (!state.coordinatorScheduleDay || !String(state.coordinatorScheduleDay).startsWith(month)) {
      state.coordinatorScheduleDay = localDate().startsWith(month) ? localDate() : `${month}-01`;
    }
    renderCoordinatorSchedule();
  } catch (error) {
    if (requestSeq !== state.coordinatorScheduleRequestSeq) return;
    if (target) target.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
  }
}

async function loadCoordinatorScheduleDay(day, options = {}) {
  const target = $("#coordinator-schedule-panel");
  const monthInput = $("#coordinator-schedule-month");
  const warehouseInput = $("#coordinator-schedule-warehouse");
  const month = monthInput?.value || new Date().toISOString().slice(0, 7);
  const role = String(state.user?.role || "").toLowerCase();
  const warehouse = role === "admin" ? String(warehouseInput?.value || state.coordinatorScheduleWarehouse || "").trim() : "";
  const selectedDay = String(day || state.coordinatorScheduleDay || "").slice(0, 10);
  if (!selectedDay) return;
  const requestSeq = ++state.coordinatorScheduleRequestSeq;
  const fast = !options.full;
  const previousScrollY = options.preserveScroll ? window.scrollY : null;
  if (!options.keepRendered) renderCoordinatorSchedule();
  try {
    const warehouseQuery = warehouse ? `&warehouse=${encodeURIComponent(warehouse)}` : "";
    const fastQuery = fast ? "&fast=true" : "";
    const payload = await api(`/api/coordinator/schedule?month=${encodeURIComponent(month)}${warehouseQuery}&day=${encodeURIComponent(selectedDay)}${fastQuery}`);
    if (requestSeq !== state.coordinatorScheduleRequestSeq) return;
    if (!fast) {
      await loadScheduleVehicleConfigurations();
      if (requestSeq !== state.coordinatorScheduleRequestSeq) return;
    }
    mergeCoordinatorScheduleDay(payload);
    state.coordinatorScheduleDay = selectedDay;
    state.coordinatorScheduleView = "day";
    renderCoordinatorSchedule();
    preserveScrollAfterRender(previousScrollY);
    if (fast && !state.coordinatorScheduleActionActive) {
      loadCoordinatorScheduleDay(selectedDay, { keepRendered: true, full: true, preserveScroll: true }).catch(() => {});
    }
  } catch (error) {
    if (requestSeq !== state.coordinatorScheduleRequestSeq) return;
    if (target) target.innerHTML = `<div class="notice error">${escapeHtml(error.message)}</div>`;
  }
}

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

function registrationStatusLabel(status) {
  return {
    new: "Jóváhagyásra vár",
    queued: "Devtest jobra vár",
    approved: "Jóváhagyva",
    rejected: "Elutasítva",
    sent: "Kiküldve",
  }[String(status || "").toLowerCase()] || String(status || "-");
}

function isAdminJobQueued(item) {
  return String(item?.adminNote || "").includes("PWA_JOB_APPROVED");
}

function adminRequestStatus(item) {
  return isAdminJobQueued(item) ? "queued" : String(item?.status || "").toLowerCase();
}

function adminRequestNote(item) {
  return String(item?.adminNote || "").replace("PWA_JOB_APPROVED |", "").trim();
}

function renderAdminRequestCard(item, options) {
  const status = adminRequestStatus(item);
  const canApprove = options.approveStatuses.includes(status);
  const canReject = options.rejectStatuses.includes(status);
  const adminNote = adminRequestNote(item);
  return `
    <article class="financial-card registration-request-card">
      <summary>
        <span>${escapeHtml(registrationStatusLabel(status))}</span>
        <strong>${escapeHtml(item.courierName || "Névtelen futár")}</strong>
      </summary>
      <div class="stat-breakdown-list">
        <div class="stat-row"><span>Futár ID</span><strong>${escapeHtml(item.courierId || "-")}</strong></div>
        <div class="stat-row"><span>E-mail</span><strong>${escapeHtml(item.email || "-")}</strong></div>
        ${item.phoneNumber !== undefined ? `<div class="stat-row"><span>Telefon</span><strong>${escapeHtml(item.phoneNumber || "-")}</strong></div>` : ""}
        <div class="stat-row"><span>Beküldve</span><strong>${item.createdAt ? escapeHtml(new Date(item.createdAt).toLocaleString("hu-HU")) : "-"}</strong></div>
        ${adminNote ? `<div class="stat-row full-row"><span>Megjegyzés</span><strong>${escapeHtml(adminNote)}</strong></div>` : ""}
      </div>
      <div class="request-actions">
        ${canApprove ? `<button class="primary ${options.approveClass}" type="button" data-id="${escapeHtml(item.id)}">${escapeHtml(options.approveLabel)}</button>` : ""}
        ${canReject ? `<button class="secondary ${options.rejectClass}" type="button" data-id="${escapeHtml(item.id)}">Elutasítás</button>` : ""}
      </div>
    </article>
  `;
}

function renderRegistrationRequests() {
  const container = $("#registration-admin-list");
  if (!container) return;
  const rows = state.registrationRequests || [];
  if (!rows.length) {
    container.innerHTML = `
      <div class="process-title">
        <span class="step-code">ID</span>
        <div><h3>Nincs jóváhagyásra váró futár</h3><p>Minden PWA regisztráció feldolgozva.</p></div>
      </div>
    `;
    return;
  }
  container.innerHTML = `
    <div class="process-title">
      <span class="step-code">${rows.length}</span>
      <div><h3>Jóváhagyásra váró futárok</h3><p>Jóváhagyás után bekerülnek a futártörzsbe és megkapják a PWA belépést.</p></div>
    </div>
    <div class="financial-card-grid salary-advance-grid">
      ${rows.map((item) => renderAdminRequestCard(item, {
        approveStatuses: ["new"],
        rejectStatuses: ["new", "queued"],
        approveClass: "registration-approve",
        rejectClass: "registration-reject",
        approveLabel: "Jóváhagyás indítása",
      })).join("")}
    </div>
  `;
}

function renderPasswordResetRequests() {
  const container = $("#password-reset-admin-list");
  if (!container) return;
  const rows = state.passwordResetRequests || [];
  if (!rows.length) {
    container.innerHTML = `
      <div class="process-title">
        <span class="step-code">PW</span>
        <div><h3>Nincs jelszó-visszaállítási kérelem</h3><p>Minden PWA jelszó kérelem feldolgozva.</p></div>
      </div>
    `;
    return;
  }
  container.innerHTML = `
    <div class="process-title">
      <span class="step-code">${rows.length}</span>
      <div><h3>Jelszó-visszaállítási kérelmek</h3><p>A PWA csak jóváhagyásra jelöli, az új jelszót a devtest job küldi ki.</p></div>
    </div>
    <div class="financial-card-grid salary-advance-grid">
      ${rows.map((item) => renderAdminRequestCard(item, {
        approveStatuses: ["new"],
        rejectStatuses: ["new", "queued"],
        approveClass: "password-reset-approve",
        rejectClass: "password-reset-reject",
        approveLabel: "Jelszó reset indítása",
      })).join("")}
    </div>
  `;
}

async function loadRegistrationRequests() {
  const container = $("#registration-admin-list");
  const passwordContainer = $("#password-reset-admin-list");
  if (container) container.innerHTML = `<div class="process-title"><span class="step-code">...</span><div><h3>Regisztrációk betöltése</h3><p>Kérelmek frissítése folyamatban.</p></div></div>`;
  if (passwordContainer) passwordContainer.innerHTML = `<div class="process-title"><span class="step-code">...</span><div><h3>Jelszó kérelmek betöltése</h3><p>Kérelmek frissítése folyamatban.</p></div></div>`;
  try {
    const [payload, passwordPayload] = await Promise.all([
      api("/api/admin/registration-requests?status=all"),
      api("/api/admin/password-reset-requests?status=all"),
    ]);
    state.registrationRequests = (payload.requests || []).filter((item) => ["new", "queued"].includes(adminRequestStatus(item)));
    state.passwordResetRequests = (passwordPayload.requests || []).filter((item) => ["new", "queued"].includes(adminRequestStatus(item)));
    renderRegistrationRequests();
    renderPasswordResetRequests();
  } catch (error) {
    if (container) container.innerHTML = `<div class="empty-card error-state">${escapeHtml(error.message)}</div>`;
    if (passwordContainer) passwordContainer.innerHTML = `<div class="empty-card error-state">${escapeHtml(error.message)}</div>`;
  }
}

$("#registration-admin-refresh")?.addEventListener("click", loadRegistrationRequests);
$("#registration-admin-list")?.addEventListener("click", async (event) => {
  const approveButton = event.target.closest(".registration-approve");
  const rejectButton = event.target.closest(".registration-reject");
  const button = approveButton || rejectButton;
  if (!button) return;
  const requestId = button.dataset.id;
  if (!requestId) return;
  const approving = Boolean(approveButton);
  const adminNote = approving ? "" : window.prompt("Mi legyen az elutasítás oka?") || "";
  if (!approving && !adminNote.trim()) return;
  button.disabled = true;
  try {
    const endpoint = approving ? "approve" : "reject";
    await api(`/api/admin/registration-requests/${encodeURIComponent(requestId)}/${endpoint}`, {
      method: "POST",
      body: JSON.stringify({ admin_note: adminNote.trim() }),
      loadingMessage: approving ? "Futár jóváhagyása..." : "Kérelem elutasítása...",
    });
    state.couriers = [];
    await loadRegistrationRequests();
    await loadCourierMasterOptions();
  } catch (error) {
    button.disabled = false;
    window.alert(error.message);
  }
});

$("#password-reset-admin-list")?.addEventListener("click", async (event) => {
  const approveButton = event.target.closest(".password-reset-approve");
  const rejectButton = event.target.closest(".password-reset-reject");
  const button = approveButton || rejectButton;
  if (!button) return;
  const requestId = button.dataset.id;
  if (!requestId) return;
  const approving = Boolean(approveButton);
  const adminNote = approving ? "" : window.prompt("Mi legyen az elutasítás oka?") || "";
  if (!approving && !adminNote.trim()) return;
  button.disabled = true;
  try {
    const endpoint = approving ? "approve" : "reject";
    await api(`/api/admin/password-reset-requests/${encodeURIComponent(requestId)}/${endpoint}`, {
      method: "POST",
      body: JSON.stringify({ admin_note: adminNote.trim() }),
      loadingMessage: approving ? "Jelszó reset indítása..." : "Kérelem elutasítása...",
    });
    await loadRegistrationRequests();
  } catch (error) {
    button.disabled = false;
    window.alert(error.message);
  }
});

$("#workflow-admin-actions")?.addEventListener("click", (event) => {
  const button = event.target.closest(".admin-workflow-action");
  if (!button) return;
  completeWorkflowAsAdmin(button.dataset.action || "");
});

$("#workflow-admin-actions")?.addEventListener("submit", (event) => {
  const form = event.target.closest("#admin-invoice-upload-form");
  if (!form) return;
  event.preventDefault();
  uploadInvoiceAsAdmin(form);
});

$("#salary-advance-list")?.addEventListener("click", (event) => {
  const button = event.target.closest(".salary-advance-approve");
  if (!button) return;
  approveSalaryAdvanceRequest(button.dataset.id || "");
});

$("#workflow-month").value = state.workflowMonth;
if ($("#settlement-dashboard-month")) $("#settlement-dashboard-month").value = state.settlementDashboardMonth;
const workflowPreviewCourierInput = $("#workflow-preview-courier");
document.addEventListener("input", (event) => {
  const form = event.target.closest("[data-monthly-payment-form]");
  if (!form) return;
  const loaded = state.settlementDashboardPayment;
  if (!loaded?.data) return;
  const invoiceNumber = form.querySelector("[data-monthly-payment-invoice]").value;
  state.settlementDashboardPaymentDrafts[`${loaded.month}:${loaded.courierId}`] = {
    invoiceNumber, adminNote:form.querySelector("[data-monthly-payment-admin-note]").value,
    note:form.querySelector("[data-monthly-payment-note]").value,
    rejectNote:form.querySelector("[data-monthly-payment-reject-note]").value,
  };
  if (!loaded.data.closed) form.querySelector("[data-monthly-payment-reference]").value = `${loaded.courierId}-${invoiceNumber}`.replace(/-$/, "");
});
if (workflowPreviewCourierInput) workflowPreviewCourierInput.value = state.workflowPreviewCourierId;
const statisticsPreviewCourierInput = $("#statistics-preview-courier");
if (statisticsPreviewCourierInput) statisticsPreviewCourierInput.value = state.workflowPreviewCourierId;
const adminPreviewCourierInput = $("#admin-preview-courier");
if (adminPreviewCourierInput) adminPreviewCourierInput.value = state.workflowPreviewCourierId;
renderWorkflowProcessPicker();
$("#statistics-month").value = state.statisticsMonth;
if ($("#admin-statistics-month")) $("#admin-statistics-month").value = state.adminStatisticsMonth;
if ($("#financial-statistics-month")) $("#financial-statistics-month").value = state.financialStatisticsMonth;
if ($("#route-details-month")) $("#route-details-month").value = state.statisticsMonth;
if ($("#route-stats-start")) $("#route-stats-start").value = monthStartDate(state.statisticsMonth);
if ($("#route-stats-end")) $("#route-stats-end").value = monthEndDate(state.statisticsMonth);
$("#coordinator-date").value = localDate();
$("#workflow-month").addEventListener("change", (event) => {
  const requestedMonth = event.target.value || state.workflowMonth;
  const visibleMonths = state.workflowMonths.map((item) => item.month).filter(Boolean);
  state.workflowMonth = visibleMonths.length && !visibleMonths.includes(requestedMonth)
    ? visibleMonths[0]
    : requestedMonth;
  updateWorkflowMonthControl();
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
  if (state.workflowPreviewCourierId) {
    state.workflowMonth = previousLocalMonth();
  }
  if (workflowPreviewCourierInput) workflowPreviewCourierInput.value = state.workflowPreviewCourierId;
  if (statisticsPreviewCourierInput) statisticsPreviewCourierInput.value = state.workflowPreviewCourierId;
  if (adminPreviewCourierInput) adminPreviewCourierInput.value = state.workflowPreviewCourierId;
  if ($("#route-details-courier")) $("#route-details-courier").value = state.workflowPreviewCourierId;
  state.workflowProcess = "";
  state.workflowMonthsLoadedFor = "";
  state.workflowMonths = [];
  state.workflow = null;
  state.statistics = null;
  state.statisticsPrevious = null;
  state.routeDetails = null;
  state.routeShiftReport = null;
  state.routeStatistics = null;
  state.routeDetailsSelectedIndex = 0;
  state.data = null;
  state.currentRoute = null;
  state.billingProfile = null;
  state.deviceReports = [];
  state.vehicleReports = [];
  state.salaryAdvanceRequests = [];
  state.expenseRequests = [];
  state.atmPayments = [];
  state.settlementDashboard = null;
  state.checkedInvoiceFile = null;
  state.checkedInvoiceMonth = null;
  setAdminPreviewStatus(state.workflowPreviewCourierId ? `Előnézet aktív: ${state.workflowPreviewCourierId}` : "Saját profil aktív.");
  if (state.section === "home") loadShifts();
  if (state.section === "settlement" || state.section === "documents") loadWorkflow().then(() => {
    if (state.section === "documents") renderDocumentsSection();
  });
  if (state.section === "statistics") loadStatistics({ resetHistory: true });
  if (state.section === "route-details") {
    renderRouteShiftReport();
    renderRouteStatistics();
    renderRouteDetails();
  }
  if (state.section === "salary-advance") loadSalaryAdvanceRequests();
  if (state.section === "expense") loadExpenseRequests();
  if (state.section === "profile") loadBillingProfile();
  if (state.section === "device") loadDeviceReports();
  if (state.section === "vehicle") loadVehicleReports();
  if (state.section === "tours") loadCurrentRoute();
  if (state.section === "settlement-dashboard") loadSettlementDashboard();
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
    const value = event.currentTarget.value || "";
    updatePreviewCourier(value);
    if (String(value).trim()) showSection("statistics");
  }
});

$("#admin-preview-open")?.addEventListener("click", () => {
  const value = adminPreviewCourierInput?.value || "";
  updatePreviewCourier(value);
  if (String(value).trim()) showSection("statistics");
});

$("#admin-preview-clear")?.addEventListener("click", () => {
  updatePreviewCourier("");
  const role = String(state.user?.role || "").toLowerCase();
  const canOpenAdmin = Boolean(state.user?.canViewSettlementDashboard)
    || ["admin", "superadmin"].includes(role);
  if (canOpenAdmin) {
    showSection("admin-statistics");
    loadAdminStatistics();
  }
});

$("#workflow-refresh").addEventListener("click", () => {
  loadWorkflow();
});

setInterval(() => {
  if (!state.user) return;
  if (!["settlement", "documents"].includes(state.section)) return;
  if (document.hidden) return;
  withSilentLoading(() => loadWorkflow({ background: true })).catch(() => {});
}, 2 * 60 * 1000);

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
  if (event.target.closest("[data-courier-complaints-refresh]")) {
    refreshCourierQualityComplaints();
    return;
  }
  const reclamationButton = event.target.closest("[data-quality-reclamation-topic]");
  if (reclamationButton) {
    openQualityReclamation(reclamationButton.getAttribute("data-quality-reclamation-topic") || "");
    return;
  }
  const dateRow = event.target.closest("[data-quality-date]");
  if (dateRow) {
    const date = dateRow.getAttribute("data-quality-date") || "";
    if (date) {
      state.statisticsDay = date;
      state.statisticsHistoryDate = date;
      renderStatistics();
      window.setTimeout(() => $("#daily-history-card")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
    }
    return;
  }
  const button = event.target.closest("[data-quality-topic]");
  if (!button) return;
  const topic = button.getAttribute("data-quality-topic") || "";
  state.statisticsQualityTopic = state.statisticsQualityTopic === topic ? "" : topic;
  renderStatistics();
});

$("#statistics-quality")?.addEventListener("keydown", (event) => {
  if (!event.target.closest("[data-quality-date]") || !["Enter", " "].includes(event.key)) return;
  event.preventDefault();
  event.target.closest("[data-quality-date]")?.click();
});

$("#statistics-breakdown").addEventListener("submit", (event) => {
  const form = event.target.closest(".route-note-form");
  if (!form) return;
  event.preventDefault();
  saveRouteNote(form);
});

$("#salary-advance-start-date").value = localMonth();
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
    state.workflowMonthsLoadedFor = "";
    state.workflowMonths = [];
    renderSalaryAdvanceRequests();
    form.reset();
    $("#salary-advance-start-date").value = localMonth();
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
  if (state.atmSubmitting || button?.disabled) return;
  state.atmSubmitting = true;
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
    if (button) button.textContent = "ATM befizetés beküldve";
    if (message) message.textContent = "Az ATM befizetés rögzítve.";
  } catch (error) {
    state.atmSubmitting = false;
    if (button) button.disabled = false;
    if (message) message.textContent = error.message;
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
    if (String(state.user.role || "").toLowerCase() === "coordinator") {
      showSection("coordinator-live");
    } else if (String(state.user.role || "").toLowerCase() === "hr") {
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
        ? "E-mail cím frissítve, a kérésed beérkezett. Admin jóváhagyás után küldjük az új jelszót."
        : response.message || "A kérésed beérkezett. Admin jóváhagyás után küldjük az új jelszót."
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
  state.registrationRequests = [];
  state.passwordResetRequests = [];
  state.coordinatorLiveMap = null;
  state.departureHelper = null;
  if (state.coordinatorLeafletMap) {
    state.coordinatorLeafletMap.remove();
    state.coordinatorLeafletMap = null;
  }
  state.todayWorkers = null;
  state.coordinatorSchedule = null;
  state.queueStatus = null;
  state.statistics = null;
  state.routeDetails = null;
  state.routeStatistics = null;
  state.routeShiftReport = null;
  state.routeDetailsSelectedIndex = 0;
  state.game = null;
  state.gameStartedAt = null;
  state.openMuszakproShifts = null;
  state.settlementImportStep = 1;
  state.settlementImportMonth = previousLocalMonth();
  state.settlementImportResult = null;
  state.settlementImportUploading = false;
  state.settlementImportColumnConfig = {};
  state.settlementImportColumnConfigSignature = "";
  state.settlementImportColumnConfigTouched = false;
  state.settlementImportSheetConfig = {};
  state.settlementImportSheetConfigSignature = "";
  state.settlementImportSheetConfigTouched = false;
  renderQueueStatus();
  showLogin();
});

const fullscreenToggle = $("#fullscreen-toggle");
function updateFullscreenToggle() {
  const active = document.body.classList.contains("fullscreen-mode");
  document.body.classList.toggle("fullscreen-mode", active);
  if (!fullscreenToggle) return;
  fullscreenToggle.setAttribute("aria-pressed", String(active));
  fullscreenToggle.textContent = active ? "Normál szélesség" : "Teljes szélesség";
}

fullscreenToggle?.addEventListener("click", () => {
  document.body.classList.toggle("fullscreen-mode");
  updateFullscreenToggle();
});
updateFullscreenToggle();

function loadWebshop() {
  window.JittWebshop.mount({ api, getUser: () => state.user, preview: isAdminPreviewMode, escapeHtml });
  return window.JittWebshop.load();
}
$("#nav-webshop").addEventListener("click", () => showSection("webshop"));
$("#nav-quality-complaints").addEventListener("click", () => showSection("quality-complaints"));
$("#quality-complaints-refresh").addEventListener("click", () => loadQualityComplaints());
$("#quality-complaints-filter").addEventListener("change", () => { state.qualityComplaintOffset = 0; loadQualityComplaints(); });
$("#quality-complaints-prev").addEventListener("click", () => { state.qualityComplaintOffset = Math.max(0, (state.qualityComplaintOffset || 0) - 50); loadQualityComplaints(); });
$("#quality-complaints-next").addEventListener("click", () => { state.qualityComplaintOffset = (state.qualityComplaintOffset || 0) + 50; loadQualityComplaints(); });
$("#refresh").addEventListener("click", loadShifts);
$("#open-muszakpro-refresh").addEventListener("click", toggleOpenMuszakproShifts);
$("#nav-home").addEventListener("click", () => showSection("home"));
$("#nav-settlement").addEventListener("click", () => showSection("settlement"));
$("#nav-statistics").addEventListener("click", () => {
  const role = String(state.user?.role || "").toLowerCase();
  const viewingCourier = Boolean(state.user?.canPreviewCouriers && state.workflowPreviewCourierId);
  const canOpenAdmin = Boolean(state.user?.canViewSettlementDashboard) || ["admin", "superadmin"].includes(role);
  showSection(viewingCourier || !canOpenAdmin ? "statistics" : "admin-statistics");
});
$("#nav-financial-statistics")?.addEventListener("click", () => showSection("financial-statistics"));
$("#admin-statistics-refresh")?.addEventListener("click", () => loadAdminStatistics());
$("#financial-statistics-refresh")?.addEventListener("click", () => loadFinancialStatistics());
$("#admin-statistics-month")?.addEventListener("change", () => loadAdminStatistics());
$("#financial-statistics-month")?.addEventListener("change", () => loadFinancialStatistics());
$("#nav-phonebook").addEventListener("click", () => showSection("phonebook"));
$("#nav-atm").addEventListener("click", () => showSection("atm"));
$("#nav-salary-advance").addEventListener("click", () => showSection("salary-advance"));
$("#nav-expense").addEventListener("click", () => showSection("expense"));
$("#nav-documents").addEventListener("click", () => showSection("documents"));
$("#nav-profile").addEventListener("click", () => showSection("profile"));
$("#nav-device").addEventListener("click", () => showSection("device"));
$("#nav-vehicle").addEventListener("click", () => showSection("vehicle"));
$("#nav-vehicle-config")?.addEventListener("click", () => showSection("vehicle-config"));
$("#nav-tours").addEventListener("click", () => showSection("tours"));
$("#nav-route-details").addEventListener("click", () => showSection("route-details"));
$("#nav-settlement-dashboard")?.addEventListener("click", () => showSection("settlement-dashboard"));
$("#nav-settlement-import-config")?.addEventListener("click", () => showSection("settlement-import-config"));
$("#nav-game").addEventListener("click", () => showSection("game"));
$("#game-refresh")?.addEventListener("click", loadGame);
$("#nav-coordinator-live").addEventListener("click", () => showSection("coordinator-live"));
$("#nav-departure-helper").addEventListener("click", () => showSection("departure-helper"));
$("#nav-today-workers").addEventListener("click", () => showSection("today-workers"));
$("#nav-coordinator-schedule").addEventListener("click", () => showSection("coordinator-schedule"));
$("#coordinator-live-refresh")?.addEventListener("click", loadCoordinatorLiveMap);
$("#departure-helper-refresh")?.addEventListener("click", loadDepartureHelper);
$("#today-workers-refresh")?.addEventListener("click", loadTodayWorkers);
$("#coordinator-schedule-refresh")?.addEventListener("click", () => {
  if (state.coordinatorScheduleView === "day") {
    loadCoordinatorScheduleDay(state.coordinatorScheduleDay, { preserveScroll: true });
  } else {
    loadCoordinatorSchedule();
  }
});
$("#coordinator-schedule-month")?.addEventListener("change", () => {
  state.coordinatorScheduleRequestSeq += 1;
  state.coordinatorSchedule = null;
  state.coordinatorScheduleDay = "";
  state.coordinatorScheduleView = "calendar";
  state.scheduleOpenVehiclePanels.clear();
  loadCoordinatorSchedule();
});
$("#coordinator-schedule-warehouse")?.addEventListener("change", (event) => {
  state.coordinatorScheduleRequestSeq += 1;
  state.coordinatorScheduleWarehouse = event.currentTarget.value || "";
  state.coordinatorSchedule = null;
  state.coordinatorScheduleDay = localDate();
  state.coordinatorScheduleView = "calendar";
  state.scheduleOpenVehiclePanels.clear();
  loadCoordinatorSchedule();
});
$("#nav-coordinator").addEventListener("click", () => showSection("coordinator"));
$("#nav-registration-admin").addEventListener("click", () => showSection("registration-admin"));
$("#settlement-dashboard-refresh")?.addEventListener("click", () => {
  state.settlementDashboard = null;
  state.settlementDashboardDetailCache = {};
  loadSettlementDashboard();
});
$("#settlement-dashboard-month")?.addEventListener("change", (event) => {
  state.settlementDashboardMonth = event.currentTarget.value || previousLocalMonth();
  state.settlementDashboard = null;
  state.settlementDashboardDetailCache = {};
  state.settlementDashboardStatusFilter = "";
  loadSettlementDashboard();
});
$("#settlement-dashboard-panel")?.addEventListener("input", (event) => {
  if (event.target.id !== "settlement-dashboard-search") return;
  const input = event.target;
  const start = input.selectionStart;
  const end = input.selectionEnd;
  state.settlementDashboardQuery = input.value || "";
  renderSettlementDashboard();
  const replacement = $("#settlement-dashboard-search");
  replacement?.focus({ preventScroll: true });
  replacement?.setSelectionRange(start, end);
});
$("#settlement-dashboard-panel")?.addEventListener("click", (event) => {
  if (!event.target.closest("[data-settlement-clear-search]")) return;
  state.settlementDashboardQuery = "";
  renderSettlementDashboard();
  $("#settlement-dashboard-search")?.focus({ preventScroll: true });
});
$("#settlement-import-config-panel")?.addEventListener("change", (event) => {
  const monthInput = event.target.closest("#settlement-import-month");
  if (monthInput) {
    state.settlementImportMonth = monthInput.value || previousLocalMonth();
    state.settlementImportResult = null;
    state.settlementImportColumnConfig = {};
    state.settlementImportColumnConfigSignature = "";
    state.settlementImportColumnConfigTouched = false;
    state.settlementImportSheetConfig = {};
    state.settlementImportSheetConfigSignature = "";
    state.settlementImportSheetConfigTouched = false;
  }
});
$("#settlement-import-config-panel")?.addEventListener("dragstart", (event) => {
  const sheetChip = event.target.closest("[data-settlement-sheet-id]");
  if (sheetChip) {
    state.settlementImportDraggedSheetId = sheetChip.dataset.settlementSheetId || "";
    state.settlementImportDraggedColumnId = "";
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", state.settlementImportDraggedSheetId);
    return;
  }
  const chip = event.target.closest("[data-settlement-column-id]");
  if (!chip) return;
  state.settlementImportDraggedColumnId = chip.dataset.settlementColumnId || "";
  state.settlementImportDraggedSheetId = "";
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", state.settlementImportDraggedColumnId);
});
$("#settlement-import-config-panel")?.addEventListener("dragover", (event) => {
  const dropzone = event.target.closest("[data-settlement-card-key], [data-settlement-sheet-group-key]");
  if (!dropzone) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "move";
});
$("#settlement-import-config-panel")?.addEventListener("drop", (event) => {
  const dropzone = event.target.closest("[data-settlement-card-key], [data-settlement-sheet-group-key]");
  if (!dropzone) return;
  event.preventDefault();
  const sheetId = state.settlementImportDraggedSheetId;
  if (dropzone.dataset.settlementSheetGroupKey !== undefined) {
    if (!sheetId) return;
    const targetKey = dropzone.dataset.settlementSheetGroupKey || "";
    const nextConfig = {};
    for (const [groupKey, ids] of Object.entries(state.settlementImportSheetConfig || {})) {
      nextConfig[groupKey] = (ids || []).filter((id) => id !== sheetId);
    }
    if (targetKey) {
      nextConfig[targetKey] = [...(nextConfig[targetKey] || []), sheetId];
    }
    state.settlementImportSheetConfig = nextConfig;
    state.settlementImportSheetConfigTouched = true;
    state.settlementImportDraggedSheetId = "";
    renderSettlementImportConfig();
    return;
  }
  const columnId = state.settlementImportDraggedColumnId || event.dataTransfer.getData("text/plain");
  if (!columnId) return;
  const targetKey = dropzone.dataset.settlementCardKey || "";
  const nextConfig = {};
  for (const [cardKey, ids] of Object.entries(state.settlementImportColumnConfig || {})) {
    nextConfig[cardKey] = (ids || []).filter((id) => id !== columnId);
  }
  if (targetKey) {
    nextConfig[targetKey] = [...(nextConfig[targetKey] || []), columnId];
  }
  state.settlementImportColumnConfig = nextConfig;
  state.settlementImportColumnConfigTouched = true;
  state.settlementImportDraggedColumnId = "";
  renderSettlementImportConfig();
});
$("#settlement-import-config-panel")?.addEventListener("click", (event) => {
  const removeSheetButton = event.target.closest("[data-settlement-remove-sheet]");
  if (removeSheetButton) {
    const sheetId = removeSheetButton.dataset.settlementRemoveSheet || "";
    const nextConfig = {};
    for (const [groupKey, ids] of Object.entries(state.settlementImportSheetConfig || {})) {
      nextConfig[groupKey] = (ids || []).filter((id) => id !== sheetId);
    }
    state.settlementImportSheetConfig = nextConfig;
    state.settlementImportSheetConfigTouched = true;
    renderSettlementImportConfig();
    return;
  }
  const removeButton = event.target.closest("[data-settlement-remove-column]");
  if (removeButton) {
    const columnId = removeButton.dataset.settlementRemoveColumn || "";
    const nextConfig = {};
    for (const [cardKey, ids] of Object.entries(state.settlementImportColumnConfig || {})) {
      nextConfig[cardKey] = (ids || []).filter((id) => id !== columnId);
    }
    state.settlementImportColumnConfig = nextConfig;
    state.settlementImportColumnConfigTouched = true;
    renderSettlementImportConfig();
    return;
  }
  const actionButton = event.target.closest("[data-settlement-import-action]");
  if (!actionButton) return;
  const action = actionButton.dataset.settlementImportAction;
  if (action === "next") {
    const monthValue = $("#settlement-import-month")?.value || state.settlementImportMonth || previousLocalMonth();
    state.settlementImportMonth = monthValue;
    state.settlementImportStep = 2;
    renderSettlementImportConfig();
    return;
  }
  if (action === "back") {
    state.settlementImportStep = Math.max(1, (state.settlementImportStep || 1) - 1);
    renderSettlementImportConfig();
    return;
  }
  if (action === "upload") {
    submitSettlementImport();
    return;
  }
  if (action === "next-validation") {
    state.settlementImportStep = 4;
    renderSettlementImportConfig();
    return;
  }
  if (action === "publish") {
    publishSettlementImport();
    return;
  }
  if (action === "refresh-validation") {
    refreshSettlementImportValidation();
    return;
  }
  if (action === "delete") {
    deleteSettlementImport();
    return;
  }
  if (action === "finish") {
    state.settlementImportStep = 1;
    state.settlementImportResult = null;
    state.settlementImportColumnConfig = {};
    state.settlementImportColumnConfigSignature = "";
    state.settlementImportColumnConfigTouched = false;
    state.settlementImportSheetConfig = {};
    state.settlementImportSheetConfigSignature = "";
    state.settlementImportSheetConfigTouched = false;
    renderSettlementImportConfig();
  }
});
$("#settlement-dashboard-panel")?.addEventListener("input", (event) => {
  invalidatePilotWorksheet(event.target.closest("[data-pilot-worksheet]"));
});
$("#settlement-dashboard-panel")?.addEventListener("change", (event) => {
  invalidatePilotWorksheet(event.target.closest("[data-pilot-worksheet]"));
});
$("#settlement-dashboard-panel")?.addEventListener("click", (event) => {
  const worksheetAction = event.target.closest("[data-worksheet-preview], [data-worksheet-commit]");
  if (worksheetAction) {
    submitPilotWorksheet(worksheetAction.closest("[data-pilot-worksheet]"), worksheetAction.hasAttribute("data-worksheet-commit"));
    return;
  }
  const changeStatus = event.target.closest("[data-dashboard-change-status]");
  if (changeStatus) {
    event.preventDefault();
    openSettlementDashboardStatusEditor(changeStatus.dataset.dashboardChangeStatus);
    return;
  }
  const editButton = event.target.closest("[data-settlement-dashboard-edit]");
  if (editButton) {
    event.preventDefault();
    event.stopPropagation();
    const courierId = editButton.dataset.settlementDashboardEdit || "";
    if (state.settlementDashboardEditCourierId === courierId) {
      state.settlementDashboardEditCourierId = "";
      renderSettlementDashboard();
      return;
    }
    state.settlementDashboardEditCourierId = courierId;
    state.settlementDashboardExpandedTab = "settlement";
    if (state.settlementDashboardExpandedCourierId === courierId && state.settlementDashboardDetail?.workflow) {
      renderSettlementDashboard();
    } else {
      loadSettlementDashboardCourierDetail(courierId);
    }
    return;
  }
  const addEditorRow = event.target.closest("[data-dashboard-editor-add]");
  if (addEditorRow) {
    const pilot = addEditorRow.closest("[data-pilot-worksheet]");
    addEditorRow.closest("[data-visual-only-editor], [data-pilot-worksheet]")?.querySelector("[data-worksheet-manual-rows]")
      ?.insertAdjacentHTML("beforeend", pilot ? settlementDashboardPilotManualRow() : settlementDashboardManualPreviewRow());
    invalidatePilotWorksheet(pilot);
    return;
  }
  const deleteEditorRow = event.target.closest("[data-dashboard-editor-delete]");
  if (deleteEditorRow) {
    const pilot = deleteEditorRow.closest("[data-pilot-worksheet]");
    deleteEditorRow.closest("[data-dashboard-editor-row]")?.remove();
    invalidatePilotWorksheet(pilot);
    return;
  }
  const filter = event.target.closest("[data-settlement-status-filter]");
  if (filter) {
    const label = filter.dataset.settlementStatusFilter || "";
    state.settlementDashboardStatusFilter = state.settlementDashboardStatusFilter === label ? "" : label;
    renderSettlementDashboard();
    return;
  }
  const tab = event.target.closest("[data-settlement-dashboard-tab]");
  if (tab) {
    state.settlementDashboardExpandedTab = tab.dataset.settlementDashboardTab || "settlement";
    renderSettlementDashboard();
    if (state.settlementDashboardExpandedTab === "tig") {
      loadSettlementDashboardCourierDetail(state.settlementDashboardExpandedCourierId, {includeTig: true});
    }
    if (state.settlementDashboardExpandedTab === "payment") {
      loadSettlementDashboardMonthlyPayment(state.settlementDashboardExpandedCourierId);
    }
    return;
  }
  if (event.target.closest("[data-load-monthly-payment]")) {
    loadSettlementDashboardMonthlyPayment(state.settlementDashboardExpandedCourierId);
    return;
  }
  const closePayment = event.target.closest("[data-close-monthly-payment]");
  if (closePayment) {
    const loaded = state.settlementDashboardPayment;
    const payment = loaded?.data;
    if (!payment?.canClose || loaded.courierId !== state.settlementDashboardExpandedCourierId
        || loaded.month !== (state.settlementDashboardMonth || previousLocalMonth())) return;
    const form = closePayment.closest("[data-monthly-payment-form]");
    const invoiceNumber = form.querySelector("[data-monthly-payment-invoice]").value;
    const note = form.querySelector("[data-monthly-payment-note]").value;
    const adminNote = form.querySelector("[data-monthly-payment-admin-note]").value;
    closePayment.disabled = true;
    api("/api/admin/settlement-payment/close", {
      method:"POST", body:JSON.stringify({month:loaded.month, courierId:loaded.courierId,
        snapshotId:payment.snapshotId, invoiceNumber, note, adminNote}), loadingMessage:"Havi kifizetés lezárása...",
    }).then(async (result) => {
      if (state.settlementDashboardPayment?.courierId === loaded.courierId
          && state.settlementDashboardPayment?.month === loaded.month) {
        state.settlementDashboardPayment = {...loaded, data:result.payment};
      }
      delete state.settlementDashboardDetailCache[`${loaded.month}:${loaded.courierId}`];
      delete state.settlementDashboardPaymentDrafts[`${loaded.month}:${loaded.courierId}`];
      await loadSettlementDashboard();
      renderSettlementDashboard();
    }).catch((error) => {
      window.alert(error.message);
      closePayment.disabled = false;
    });
    return;
  }
  const reopenPayment = event.target.closest("[data-reopen-monthly-payment]");
  if (reopenPayment) {
    const loaded = state.settlementDashboardPayment;
    if (!loaded?.data || loaded.courierId !== state.settlementDashboardExpandedCourierId
        || loaded.month !== (state.settlementDashboardMonth || previousLocalMonth())) return;
    const note = reopenPayment.closest("[data-monthly-payment-form]").querySelector("[data-monthly-payment-reject-note]").value.trim();
    const notifyCourier = reopenPayment.closest("[data-monthly-payment-form]").querySelector("[data-monthly-payment-notify]").checked;
    if (!note) { window.alert("Add meg az elutasítás / visszanyitás indokát."); return; }
    reopenPayment.disabled = true;
    api("/api/admin/settlement-payment/reopen", {
      method:"POST", body:JSON.stringify({month:loaded.month, courierId:loaded.courierId,
        snapshotId:loaded.data.snapshotId, note, notifyCourier}), loadingMessage:"Havi kifizetés visszanyitása...",
    }).then(async (result) => {
      if (state.settlementDashboardPayment?.courierId === loaded.courierId
          && state.settlementDashboardPayment?.month === loaded.month) {
        state.settlementDashboardPayment = {...loaded, data:result.payment};
      }
      delete state.settlementDashboardDetailCache[`${loaded.month}:${loaded.courierId}`];
      await loadSettlementDashboard();
      renderSettlementDashboard();
    }).catch((error) => { window.alert(error.message); reopenPayment.disabled = false; });
    return;
  }
  const openPreview = event.target.closest("[data-settlement-dashboard-open-preview]");
  if (openPreview) {
    openSettlementDashboardCourier(state.settlementDashboardExpandedCourierId || "");
    return;
  }
  const saveComplaint = event.target.closest("[data-save-dashboard-complaint]");
  if (saveComplaint) {
    const complaintId = saveComplaint.dataset.saveDashboardComplaint || "";
    const box = saveComplaint.closest("[data-dashboard-complaint-id]");
    const status = box?.querySelector('[data-complaint-field="status"]')?.value || "resolved";
    const response = box?.querySelector('[data-complaint-field="response"]')?.value || "";
    const courierId = state.settlementDashboardExpandedCourierId;
    const month = state.settlementDashboardMonth || previousLocalMonth();
    saveComplaint.disabled = true;
    api(`/api/admin/workflow/complaints/${encodeURIComponent(complaintId)}`, {
      method: "PATCH",
      body: JSON.stringify({ status, response }),
      loadingMessage: "Reklamáció mentése...",
    }).then(async () => {
      delete state.settlementDashboardDetailCache[`${month}:${courierId}`];
      if (state.settlementDashboardExpandedCourierId === courierId
          && (state.settlementDashboardMonth || previousLocalMonth()) === month) {
        await loadSettlementDashboardCourierDetail(courierId);
        renderSettlementDashboard();
      }
    }).catch((error) => {
      window.alert(error.message);
      saveComplaint.disabled = false;
    });
    return;
  }
  const row = event.target.closest(".settlement-dashboard-row-main[data-courier-id]");
  if (!row) return;
  const courierId = row.dataset.courierId || "";
  if (state.settlementDashboardExpandedCourierId === courierId) {
    state.settlementDashboardExpandedCourierId = "";
    state.settlementDashboardEditCourierId = "";
    state.settlementDashboardDetail = null;
    renderSettlementDashboard();
    return;
  }
  state.settlementDashboardExpandedTab = "settlement";
  loadSettlementDashboardCourierDetail(courierId);
});

document.addEventListener("click", (event) => {
  const editButton = event.target.closest("[data-financial-edit-card]");
  if (editButton) {
    event.preventDefault();
    event.stopPropagation();
    state.financialEditCardKey = editButton.dataset.financialEditCard || "";
    renderWorkflow();
    return;
  }
  const saveButton = event.target.closest("[data-financial-save-card]");
  if (saveButton) {
    event.preventDefault();
    event.stopPropagation();
    saveFinancialCardOverride(saveButton.dataset.financialSaveCard || "");
    return;
  }
  if (event.target.closest("[data-financial-load-snapshots]")) {
    event.preventDefault();
    loadFinancialSnapshotsForRestore();
    return;
  }
  if (event.target.closest("[data-financial-restore-snapshot]")) {
    event.preventDefault();
    restoreFinancialSnapshot();
    return;
  }
  const addButton = event.target.closest("[data-financial-add-item]");
  if (addButton) {
    event.preventDefault();
    addFinancialEditorRow(addButton.dataset.financialAddItem || "");
    return;
  }
  const deleteButton = event.target.closest("[data-financial-delete-row]");
  if (deleteButton) {
    event.preventDefault();
    const row = deleteButton.closest("[data-financial-edit-row]");
    if (!row) return;
    const key = row.querySelector('[data-field="key"]')?.value || "";
    if (key.startsWith("admin_") || key.startsWith("draft_") || key.startsWith("new_")) {
      row.remove();
      return;
    }
    const deleted = row.querySelector('[data-field="deleted"]');
    const amount = row.querySelector('[data-field="amountHuf"]');
    const note = row.querySelector('[data-field="note"]');
    if (deleted) deleted.value = "true";
    if (amount) amount.value = "0";
    if (note && !note.value) note.value = "Admin által törölve";
    row.classList.add("deleted");
  }
});
$("#route-report-open")?.addEventListener("click", openRouteReportDialog);
document.querySelectorAll("[data-route-report-close]").forEach((button) => button.addEventListener("click", closeRouteReportDialog));
$("#route-report-dialog")?.addEventListener("click", (event) => {
  if (event.target === event.currentTarget) closeRouteReportDialog();
});
$("#route-report-dialog")?.addEventListener("click", (event) => {
  const chip = event.target.closest("[data-route-report-field]");
  if (!chip) return;
  const key = chip.dataset.routeReportField;
  const source = chip.dataset.routeReportZoneSource;
  routeReportMoveField(key, source === "selected" ? "available" : "selected");
});
$("#route-report-dialog")?.addEventListener("dragstart", (event) => {
  const chip = event.target.closest("[data-route-report-field]");
  if (!chip) return;
  event.dataTransfer.setData("text/plain", chip.dataset.routeReportField || "");
});
$("#route-report-dialog")?.addEventListener("dragover", (event) => {
  if (event.target.closest("[data-route-report-zone]")) event.preventDefault();
});
$("#route-report-dialog")?.addEventListener("drop", (event) => {
  const zone = event.target.closest("[data-route-report-zone]");
  if (!zone) return;
  event.preventDefault();
  routeReportMoveField(event.dataTransfer.getData("text/plain"), zone.dataset.routeReportZone);
});
$("#route-report-include-summary")?.addEventListener("change", (event) => {
  state.routeDetailsIncludeSummary = event.currentTarget.checked;
  renderRouteDetails();
});
$("#route-report-auto-excel")?.addEventListener("change", (event) => {
  state.routeDetailsAutoExcel = event.currentTarget.checked;
});
$("#route-details-load")?.addEventListener("click", loadRouteDetails);
$("#route-stats-load")?.addEventListener("click", loadRouteStatistics);
$("#route-shift-report-load")?.addEventListener("click", loadRouteShiftReport);
$("#route-details-courier")?.addEventListener("change", () => {
  state.routeDetails = null;
  state.routeShiftReport = null;
  state.routeDetailsSelectedIndex = 0;
  renderRouteShiftReport();
  renderRouteDetails();
});
$("#route-details-query")?.addEventListener("input", (event) => {
  state.routeDetailsQuery = event.currentTarget.value || "";
  state.routeDetailsSelectedIndex = 0;
  renderRouteDetails();
});
$("#route-details-route-id")?.addEventListener("input", (event) => {
  state.routeDetailsRouteId = event.currentTarget.value || "";
  state.routeDetailsSelectedIndex = 0;
  renderRouteDetails();
});
$("#route-details-type")?.addEventListener("change", (event) => {
  state.routeDetailsType = event.currentTarget.value || "all";
  state.routeDetailsSelectedIndex = 0;
  renderRouteDetails();
});
$("#route-details-month")?.addEventListener("change", () => {
  state.routeDetails = null;
  state.routeStatistics = null;
  state.routeShiftReport = null;
  state.routeDetailsSelectedIndex = 0;
  const month = $("#route-details-month")?.value || state.statisticsMonth;
  if ($("#route-stats-start")) $("#route-stats-start").value = monthStartDate(month);
  if ($("#route-stats-end")) $("#route-stats-end").value = monthEndDate(month);
  renderRouteShiftReport();
  renderRouteStatistics();
  renderRouteDetails();
});
["#route-stats-start", "#route-stats-end", "#route-stats-warehouse"].forEach((selector) => {
  $(selector)?.addEventListener("change", () => {
    state.routeStatistics = null;
    state.routeShiftReport = null;
    state.routeDetailsSelectedIndex = 0;
    renderRouteShiftReport();
    renderRouteStatistics();
    renderRouteDetails();
  });
});

setInterval(() => {
  if (document.hidden) return;
  withSilentLoading(() => currentSectionRefresh()).catch(() => {});
}, 5 * 60 * 1000);

setInterval(() => {
  if (!state.user || state.section !== "tours" || document.hidden) return;
  withSilentLoading(() => loadCurrentRoute()).catch(() => {});
}, ROUTE_LIVE_REFRESH_MS);

setInterval(() => {
  if (!state.user || state.section !== "coordinator-live" || document.hidden) return;
  withSilentLoading(() => loadCoordinatorLiveMap()).catch(() => {});
}, COORDINATOR_LIVE_REFRESH_MS);

setInterval(() => {
  if (!state.user || state.section !== "departure-helper" || document.hidden) return;
  withSilentLoading(() => loadDepartureHelper()).catch(() => {});
}, COORDINATOR_LIVE_REFRESH_MS);

setInterval(() => {
  if (!state.user || state.section !== "vehicle" || document.hidden) return;
  withSilentLoading(() => loadVehicleAssignments({ background: true })).catch(() => {});
}, VEHICLE_LIVE_REFRESH_MS);

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
      showSection("coordinator-live");
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
