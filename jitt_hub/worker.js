const SETTLEMENT_SCHEMA = "settlement";
const PUBLIC_SCHEMA = "public";
const HUB_SESSION_COOKIE = "jitt_hub_session";
const HUB_SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 30;

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function cleanEnv(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function cookieValue(request, name) {
  const cookieHeader = request.headers.get("cookie") || "";
  const cookie = cookieHeader
    .split(";")
    .map((value) => value.trim())
    .find((value) => value.startsWith(`${name}=`));
  return cookie ? cookie.slice(name.length + 1) : "";
}

function base64UrlEncode(value) {
  const bytes = value instanceof Uint8Array ? value : new TextEncoder().encode(String(value));
  let binary = "";
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function base64UrlDecode(value) {
  const base64 = String(value || "").replace(/-/g, "+").replace(/_/g, "/");
  const binary = atob(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="));
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

function normalizedLogin(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .trim()
    .toLocaleLowerCase()
    .replace(/\s+/g, " ");
}

function publicPwaUser(row) {
  const username = key(row?.username);
  const role = key(row?.role || "user");
  const isDashboardAdmin = ["admin", "superadmin"].includes(role.toLowerCase()) || normalizedLogin(username) === "admin";
  return {
    username,
    courierId: key(row?.courier_id || row?.courierId),
    role,
    canViewSettlementDashboard: isDashboardAdmin,
  };
}

async function signingKey(env) {
  const secret = cleanEnv(env.SUPABASE_READ_KEY || env.SUPABASE_SERVICE_ROLE_KEY);
  if (!secret) throw new Error("Missing SUPABASE_READ_KEY.");
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(`jitthub-session-v1:${secret}`),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

function sameBytes(left, right) {
  if (left.length !== right.length) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) difference |= left[index] ^ right[index];
  return difference === 0;
}

async function verifyPwaPassword(password, storedHash) {
  const [scheme, iterations, saltBase64, expectedBase64] = String(storedHash || "").split("$", 4);
  if (scheme !== "pbkdf2_sha256" || !/^\d+$/.test(iterations) || !saltBase64 || !expectedBase64) return false;
  try {
    const expected = base64UrlDecode(expectedBase64.replace(/\+/g, "-").replace(/\//g, "_"));
    const passwordKey = await crypto.subtle.importKey("raw", new TextEncoder().encode(password), "PBKDF2", false, ["deriveBits"]);
    const actual = new Uint8Array(await crypto.subtle.deriveBits({
      name: "PBKDF2",
      hash: "SHA-256",
      salt: base64UrlDecode(saltBase64.replace(/\+/g, "-").replace(/\//g, "_")),
      iterations: Number(iterations),
    }, passwordKey, expected.length * 8));
    return sameBytes(actual, expected);
  } catch {
    return false;
  }
}

async function findPwaUser(env, username) {
  const select = "courier_id,username,role,active,password_hash";
  const exactRows = await supabaseFetch(env, PUBLIC_SCHEMA, "pwa_users", {
    select,
    username: `eq.${username}`,
    limit: 1,
  });
  if (exactRows[0]) return exactRows[0];
  const wanted = normalizedLogin(username);
  const rows = await supabaseFetch(env, PUBLIC_SCHEMA, "pwa_users", { select, limit: 10000 });
  return rows.find((row) => normalizedLogin(row.username) === wanted) || null;
}

async function createHubSession(user, env) {
  const payload = base64UrlEncode(JSON.stringify({ user, expiresAt: Date.now() + HUB_SESSION_MAX_AGE_SECONDS * 1000 }));
  const signature = new Uint8Array(await crypto.subtle.sign("HMAC", await signingKey(env), new TextEncoder().encode(payload)));
  return `${payload}.${base64UrlEncode(signature)}`;
}

async function readHubSession(request, env) {
  const token = cookieValue(request, HUB_SESSION_COOKIE);
  const [payload, signature] = token.split(".", 2);
  if (!payload || !signature) return null;
  try {
    const valid = await crypto.subtle.verify("HMAC", await signingKey(env), base64UrlDecode(signature), new TextEncoder().encode(payload));
    if (!valid) return null;
    const data = JSON.parse(new TextDecoder().decode(base64UrlDecode(payload)));
    return Number(data?.expiresAt || 0) > Date.now() ? data.user || null : null;
  } catch {
    return null;
  }
}

function hasSettlementDashboardAccess(user) {
  return Boolean(user && user.canViewSettlementDashboard);
}

async function currentPwaUser(request, env) {
  return readHubSession(request, env);
}

async function requireDashboardUser(request, env) {
  const user = await currentPwaUser(request, env);
  if (!user) return { error: jsonResponse({ error: "Bejelentkezés szükséges." }, 401) };
  if (!hasSettlementDashboardAccess(user)) {
    return { error: jsonResponse({ error: "Ehhez az oldalhoz admin jogosultság szükséges." }, 403) };
  }
  return { user };
}

function authenticatedJson(payload, status, sessionToken = "") {
  const headers = new Headers({
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
  });
  if (sessionToken) {
    headers.set("set-cookie", `${HUB_SESSION_COOKIE}=${sessionToken}; Max-Age=${HUB_SESSION_MAX_AGE_SECONDS}; Path=/; HttpOnly; Secure; SameSite=Lax`);
  }
  return new Response(JSON.stringify(payload), { status, headers });
}

async function authenticateAgainstPwa(env, username, password) {
  // The PWA backend is the source of truth for credentials.  In particular it
  // still supports the legacy user store while the account migration is in
  // progress; checking the Supabase table only would reject a valid PWA login.
  const pwaUrl = cleanEnv(env.PWA_API_URL || "https://futar.jitt.hu");
  const response = await fetch(`${pwaUrl}/api/login`, {
    method: "POST",
    headers: { "content-type": "application/json", accept: "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (response.status === 401) return null;
  if (!response.ok) {
    throw new Error(`PWA belépési szolgáltatás hibája (${response.status}).`);
  }
  const payload = await response.json().catch(() => null);
  if (!payload?.user) throw new Error("A PWA belépési szolgáltatás érvénytelen választ adott.");
  return publicPwaUser(payload.user);
}

async function loginWithPwa(request, env) {
  const body = await request.json().catch(() => null);
  const username = String(body?.username || "").trim();
  const password = String(body?.password || "");
  if (!username || !password) {
    return jsonResponse({ error: "Felhasználónév és jelszó szükséges." }, 400);
  }

  const user = await authenticateAgainstPwa(env, username, password);
  if (!user) {
    return authenticatedJson({ error: "Hibás felhasználónév vagy jelszó." }, 401);
  }
  if (!hasSettlementDashboardAccess(user)) {
    return authenticatedJson({ error: "Ehhez az oldalhoz admin jogosultság szükséges." }, 403);
  }
  return authenticatedJson({ user }, 200, await createHubSession(user, env));
}

async function dashboardSession(request, env) {
  const result = await requireDashboardUser(request, env);
  if (result.error) return result.error;
  return jsonResponse({ user: result.user });
}

function logoutHub() {
  return new Response(JSON.stringify({ ok: true }), {
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "set-cookie": `${HUB_SESSION_COOKIE}=; Max-Age=0; Path=/; HttpOnly; Secure; SameSite=Lax`,
    },
  });
}

function parseMonth(value) {
  const text = String(value || "").trim();
  const match = text.match(/^(\d{4})-(\d{2})(?:-\d{2})?$/);
  if (match) {
    return `${match[1]}-${match[2]}-01`;
  }
  const now = new Date();
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-01`;
}

function monthEnd(periodStart) {
  const [year, month] = periodStart.split("-").map(Number);
  return new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10);
}

function money(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? Math.round(number) : 0;
}

function metricNumber(value) {
  return value === null || value === undefined ? null : Number(value);
}

function key(value) {
  return String(value || "").trim();
}

function formatIdList(values) {
  return values
    .map((value) => key(value))
    .filter(Boolean)
    .map((value) => `"${value.replace(/"/g, '\\"')}"`)
    .join(",");
}

function formatNumericIdList(values) {
  return values
    .map((value) => key(value))
    .filter((value) => /^\d+$/.test(value))
    .join(",");
}

async function supabaseFetch(env, schema, table, params) {
  const supabaseUrl = cleanEnv(env.SUPABASE_URL);
  const supabaseKey = cleanEnv(env.SUPABASE_READ_KEY || env.SUPABASE_ANON_KEY || env.SUPABASE_SERVICE_ROLE_KEY);
  if (!supabaseUrl || !supabaseKey) {
    throw new Error("Missing SUPABASE_URL or SUPABASE_READ_KEY.");
  }

  const url = new URL(`${supabaseUrl}/rest/v1/${table}`);
  Object.entries(params || {}).forEach(([name, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(name, String(value));
    }
  });

  const requested = Number(params?.limit || 1000);
  const rows = [];
  while (rows.length < requested) {
    const size = Math.min(500, requested - rows.length);
    url.searchParams.set("limit", String(size));
    url.searchParams.set("offset", String(rows.length));
    const response = await fetch(url, { headers: {
      apikey: supabaseKey, authorization: `Bearer ${supabaseKey}`, "accept-profile": schema,
    }});
    const text = await response.text();
    if (!response.ok) throw new Error(`${schema}.${table}: HTTP ${response.status} ${text.slice(0,500)}`);
    const batch = text ? JSON.parse(text) : [];
    rows.push(...batch);
    if (batch.length < size) break;
  }
  return rows;
}

function settlementWasReset(states) {
  const settlement = states?.settlement || {};
  return key(settlement.status).toLowerCase() !== "done" && (
    /új pénzügyi snapshot|uj penzugyi snapshot/i.test(settlement.status_note || "") ||
    key(settlement.updated_by).toLowerCase() === "finance-snapshot-refresh"
  );
}

function statusForRow(row, closure) {
  const label = key(row.dashboardStatus);
  const states = row.workflowStates;
  if (states) {
    if (label === "Reklamáció") return label;
    if (settlementWasReset(states)) return "Elszámolás elfogadásra vár";
    if (key(states.invoice_payment?.status).toLowerCase() === "done" || closure?.status === "done") return "Kifizetve";
  }
  return ({ "TIG-re vár": "Teljesítés-összesítőre vár", "TIG elfogadásra vár": "Teljesítés-összesítő áttekintésre vár" })[label] || label || "Állapot nem elérhető";
}

const settlementWorkflowKeys = ['settlement','tig','invoice_submit','invoice_check','invoice_payment'];

function courierWorkflowProgress(row, closure) {
  const states = row.workflowStates || {};
  const readyAt = {
    'Elszámolás készül':0, 'Elszámolás':0, 'Elszámolás elfogadásra vár':0,
    'Teljesítés-összesítőre vár':1, 'Teljesítés-összesítő áttekintésre vár':1,
    'Számlafeltöltésre vár':2, 'Számla ellenőrzésre vár':3, 'Kifizetésre vár':4, 'Kifizetve':5,
  };
  if (settlementWasReset(states)) return {completed:[],current:'settlement'};
  const label = statusForRow(row, closure);
  const currentIndex = closure?.status === 'done' || states.invoice_payment?.status === 'done' ? 5 : readyAt[label];
  const completed = settlementWorkflowKeys.filter((action,index) => index < currentIndex || states[action]?.status === 'done');
  const hasEvidence = currentIndex !== undefined || settlementWorkflowKeys.some(action => Boolean(states[action]?.status));
  return {completed,current:hasEvidence ? settlementWorkflowKeys.find(action => !completed.includes(action)) || null : null};
}

async function loadLatestFinanceSnapshots(env, periodStart, courierId, { trendOnly = false } = {}) {
  // Load the whole month's identities, including couriers without an import row.
  const select = trendOnly ? 'id,courier_id,version' : 'id,courier_id,courier_name,warehouse_label,version,metadata,created_at';
  let parents;
  if(trendOnly) {
    try {
      parents = await supabaseFetch(env, SETTLEMENT_SCHEMA, 'rpc/pwa_dashboard_latest_finance_snapshots', {
        p_period_start:periodStart,select,courier_id:courierId?`eq.${courierId}`:undefined,order:'courier_id.asc',limit:100000,
      });
    } catch(error) {
      // Older installations may not yet expose the read-only projection.
      // Real database/network errors must not be disguised as missing data.
      if(!/HTTP (400|403|404)\b/.test(String(error.message)))throw error;
    }
  }
  parents ??= await supabaseFetch(env, SETTLEMENT_SCHEMA, "courier_finance_snapshot", {
    select,
    period_start: `eq.${periodStart}`,
    courier_id: courierId ? `eq.${courierId}` : undefined,
    order: "courier_id.asc,version.desc,created_at.desc,id.desc", limit: 100000,
  });
  const latest = new Map();
  for (const row of parents) if (!latest.has(key(row.courier_id))) latest.set(key(row.courier_id), row);
  const snapshots = [...latest.values()];
  // Only fetch item rows for the latest versions, not every historical version.
  const batchSize=trendOnly?100:40;
  for (let offset = 0; offset < snapshots.length; offset += batchSize) {
    const batch = snapshots.slice(offset, offset + batchSize);
    const items = await supabaseFetch(env, SETTLEMENT_SCHEMA, "courier_finance_snapshot_item", {
      select: trendOnly?'snapshot_id,section,item_key,amount_value,amount_kind':"snapshot_id,section,item_key,item_label,amount_value,amount_kind,note,display_order",
      ...(trendOnly?{section:'eq.finance',amount_kind:'eq.huf',item_key:'in.(delay_bonus,compliance_bonus,address_bonus_kifli,kiflis_bonus_malus,monthly_bonus,monthly_malus,bonus_malus,manual_bonus,manual_malus,customer_rating,loyalty_bonus)'}:{}),
      snapshot_id: `in.(${batch.map(row => row.id).join(",")})`, order: "id.asc", limit: 100000,
    });
    for (const row of batch) row.items = items.filter(item => item.snapshot_id === row.id);
  }
  return snapshots;
}

async function loadSalaryAdvanceAdditions(env, periodStart, courierId) {
  const months=(Array.isArray(periodStart)?periodStart:[periodStart]).map(value=>value.slice(0,7)).sort();
  const [lastYear,lastMonth]=months[months.length-1].split('-').map(Number);
  const end=new Date(Date.UTC(lastYear,lastMonth,1)).toISOString().slice(0,10);
  const dateFilter={and:`(start_date.gte.${months[0]}-01,start_date.lt.${end})`, ...(courierId ? {courier_id:`eq.${courierId}`} : {})};
  const [plans, requests] = await Promise.all([
    supabaseFetch(env, SETTLEMENT_SCHEMA, "courier_salary_advance_plan", {
      select: "id,courier_id,courier_name,requested_amount_huf,start_date,status", ...dateFilter,status:'in.(open,done)',order: "id.asc", limit: 10000,
    }),
    supabaseFetch(env, SETTLEMENT_SCHEMA, "courier_salary_advance_request", {
      select: "id,courier_id,courier_name,requested_amount_huf,start_date,status,plan_id", ...dateFilter,plan_id:'is.null',status:'in.(approved,paid,closed)',order: "id.asc", limit: 10000,
    }),
  ]);
  // A linked request and its repayment plan represent the same advance.
  return [...plans.filter(row => ["open","done"].includes(key(row.status).toLowerCase())),
    ...requests.filter(row => !row.plan_id && ["approved","paid","closed"].includes(key(row.status).toLowerCase()))]
    .filter(row => months.includes(key(row.start_date).slice(0,7)));
}

function snapshotAmountMap(snapshot) {
  const amounts = new Map();
  for (const item of snapshot?.items || []) {
    if (item?.section === "finance" && item?.amount_kind === "huf") {
      amounts.set(key(item.item_key), money(item.amount_value));
    }
  }
  return amounts;
}

function buildCourierRow(row, profile, workload, closure, snapshot, processMetric, { missingSummary = false } = {}) {
  // A PWA finance snapshot is the published, immutable financial source.  The
  // old profile view misses later manual corrections, which made the Hub show
  // a different total from the courier's actual settlement card.
  const values = snapshotAmountMap(snapshot);
  const metadata = snapshot?.metadata && typeof snapshot.metadata === "object" ? snapshot.metadata : {};
  const snapshotHasFinance = values.size > 0;
  const amount = (snapshotKey, fallback) => snapshotHasFinance
    ? money(values.get(snapshotKey) ?? 0) : money(fallback);
  const base = amount("base", row.courier_base_rate_huf);
  const tip = amount("tip", row.tip_huf);
  const delay = amount("delay_bonus", row.delay_bonus_huf);
  const compliance = amount("compliance_bonus", row.compliance_bonus_huf);
  const otherBonus = amount("address_bonus_kifli", row.other_route_bonus_huf);
  const kifliNet = amount("kiflis_bonus_malus", row.imported_bonus_huf - Math.abs(money(row.imported_malus_huf)));
  const importedBonus = values.has("kiflis_bonus_malus") ? Math.max(kifliNet, 0) : amount("monthly_bonus", row.imported_bonus_huf);
  const manualNet = amount("bonus_malus", row.manual_bonus_huf - Math.abs(money(row.manual_malus_huf)));
  const jittBonus = values.has("bonus_malus") ? Math.max(manualNet, 0) : amount("manual_bonus", row.manual_bonus_huf);
  const customerRating = amount("customer_rating", row.customer_rating_bonus_huf);
  const loyalty = amount("loyalty_bonus", row.loyalty_bonus_huf);
  const correctionNet = amount("correction", (row.correction_bonus_huf || row.correction_income_huf) - Math.abs(money(row.correction_deduction_huf)));
  const correctionIncome = values.has("correction_income") ? amount("correction_income", 0) : Math.max(correctionNet, 0);
  const bonus = delay + compliance + otherBonus + importedBonus + jittBonus + customerRating + loyalty;
  const monthlyMalus = values.has("kiflis_bonus_malus") ? Math.abs(Math.min(kifliNet, 0)) : values.has("monthly_malus")
    ? Math.abs(amount("monthly_malus", 0)) : Math.abs(Math.min(kifliNet, 0)) || Math.abs(money(row.imported_malus_huf || row.malus_huf));
  const jittMalus = values.has("bonus_malus") ? Math.abs(Math.min(manualNet, 0)) : values.has("manual_malus")
    ? Math.abs(amount("manual_malus", 0)) : Math.abs(Math.min(manualNet, 0)) || Math.abs(money(row.manual_malus_huf));
  const malus = monthlyMalus + jittMalus;
  const atm = Math.abs(Math.min(amount("atm_effect", -Math.abs(money(row.atm_deduction_huf || row.imported_atm_deduction_huf))), 0));
  const otherExpense = Math.abs(amount("other_expense", row.other_expense_huf));
  const salaryAdvance = Math.abs(amount("salary_advance", row.salary_advance_huf));
  const reserve = Math.abs(amount("reserve", row.target_reserve_topup_huf || row.reserve_addition_huf || row.reserve_deduction_huf));
  const insurance = Math.abs(amount("insurance_fee", row.insurance_fee_huf));
  const correctionDeduction = values.has("correction_deduction")
    ? Math.abs(amount("correction_deduction", 0)) : Math.abs(Math.min(correctionNet, 0));
  const otherDeduction = otherExpense + correctionDeduction;
  const income = values.has("income") ? amount("income", 0)
    : money(metadata.income_total ?? (base + tip + bonus));
  const deductions = Math.abs(values.has("deductions") ? amount("deductions", 0)
    : money(metadata.deduction_total ?? -(malus + atm + otherExpense + salaryAdvance + reserve + insurance)));
  // Corrections are stored separately in the PWA worksheet.  They must still
  // be part of the total negative financial effect shown in the Hub.
  const deductionImpact = processMetric?.closure_snapshot?.finance_available ? money(processMetric.deductions_huf) : deductions + correctionDeduction;
  const payable = values.has("payable") ? amount("payable", 0)
    : money(metadata.payable_total ?? closure?.payable_huf ?? row.payable_huf);
  const routeCount = Number(workload?.completed_route_count || row.route_count || 0);
  const orderCount = Number(workload?.order_count || row.order_count || 0);
  const metric = processMetric || {};

  return {
    courierId: key(row.courier_id),
    courierName: key(snapshot?.courier_name || row.driver_name || profile?.courier_name || workload?.courier_name),
    email: key(profile?.email || profile?.billing_email),
    warehouse: key(snapshot?.warehouse_label || profile?.warehouse_name || "BUD"),
    status: statusForRow(row, closure),
    workflowProgress: courierWorkflowProgress(row, closure),
    routeCount,
    orderCount,
    base,
    tip,
    bonus,
    delay,
    compliance,
    otherBonus,
    performanceBonus: delay + compliance + otherBonus + customerRating + loyalty,
    salaryAdvanceAdded: money(row.salaryAdvanceAdded),
    importedBonus,
    manualBonus: jittBonus,
    customerRating,
    loyalty,
    malus,
    importedMalus: monthlyMalus,
    manualMalus: jittMalus,
    jittBonus,
    jittMalus,
    correctionIncome,
    correctionDeduction,
    atm,
    salaryAdvance,
    reserve,
    insurance,
    otherDeduction,
    income,
    deductions,
    deductionImpact,
    payable,
    snapshotIsPublished: snapshotHasFinance,
    financeSnapshotId: snapshotHasFinance ? snapshot.id : null,
    closureStatus: key(closure?.status),
    bookedShiftCount: Number(workload?.booked_shift_count || 0),
    advanceBookedShiftCount: Number(workload?.advance_booked_shift_count || 0),
    giritonShiftCount: Number(workload?.giriton_shift_count || 0),
    invoiceIssueCount: Number(row.invoiceIssueCount || 0),
    processMetric: {
      hasData: Boolean(metric.courier_metric_id),
      financialComplaintCount: Number(metric.financial_complaint_count || 0),
      respondedComplaintCount: Number(metric.responded_complaint_count || 0),
      responseAverageHours: metricNumber(metric.response_average_hours),
      responseTimedCount: metric.closure_snapshot?.response_timed_count ?? null,
      openingToSettlementHours: metricNumber(metric.opening_to_settlement_hours),
      hasOpeningToSettlement: metric.opening_to_settlement_hours !== null && metric.opening_to_settlement_hours !== undefined,
      settlementToTigHours: metricNumber(metric.settlement_to_tig_hours),
      hasSettlementToTig: metric.settlement_to_tig_hours !== null && metric.settlement_to_tig_hours !== undefined,
      tigToInvoiceHours: metricNumber(metric.tig_to_invoice_hours),
      hasTigToInvoice: metric.tig_to_invoice_hours !== null && metric.tig_to_invoice_hours !== undefined,
      invoiceToPaidHours: metricNumber(metric.invoice_to_paid_hours),
      hasInvoiceToPaid: metric.invoice_to_paid_hours !== null && metric.invoice_to_paid_hours !== undefined,
      openingToPaidHours: metricNumber(metric.opening_to_paid_hours),
    },
  };
}

async function settlementDashboard(request, env) {
  const requestUrl = new URL(request.url);
  const periodStart = parseMonth(requestUrl.searchParams.get("month"));
  const periodEnd = monthEnd(periodStart);
  const limit = Math.min(Math.max(Number(requestUrl.searchParams.get("limit") || 120), 1), 500);

  const summaryRows = await supabaseFetch(env, SETTLEMENT_SCHEMA, "vw_courier_month_profile_snapshot", {
    select: "*",
    period_month: `eq.${periodStart}`,
    order: "payable_huf.desc",
    limit,
  });

  const courierIds = [...new Set(summaryRows.map((row) => key(row.courier_id)).filter(Boolean))];
  const idFilter = formatIdList(courierIds);
  const numericIdFilter = formatNumericIdList(courierIds);

  const [profiles, workloads, closures, discrepancies, discrepancyCoverage, processMetricRows, courierProcessMetricRows, activePwaUsers, financeSnapshots, workflowDashboardRows, metricMonths, workflowStates, advanceAdditions, complaintRows] = await Promise.all([
    numericIdFilter
      ? supabaseFetch(env, PUBLIC_SCHEMA, "courier_master", {
          select: "courier_id,courier_name,email,billing_email,warehouse_name",
          courier_id: `in.(${numericIdFilter})`,
          limit,
        }).catch(() => [])
      : [],
    supabaseFetch(env, SETTLEMENT_SCHEMA, "courier_monthly_workload_summary", {
          select: "courier_id,courier_name,period_start,booked_shift_count,giriton_shift_count,completed_route_count,order_count",
          period_start: `eq.${periodStart}`,
          limit,
        }).catch(() => []),
    supabaseFetch(env, SETTLEMENT_SCHEMA, "courier_monthly_closure", {
          select: "courier_id,courier_name,period_start,payable_huf,status,invoice_number,closed_at",
          period_start: `eq.${periodStart}`,
          limit,
        }).catch(() => []),
    supabaseFetch(env, SETTLEMENT_SCHEMA, "vw_invoice_discrepancy_list", {
      select: "courier_id,courier_name,period_start,invoice_kind_label,issue_type,expected_amount_huf,uploaded_invoice_amount_huf,difference_huf,invoice_number",
      period_start: `eq.${periodStart}`,
      limit: 50,
    }).catch(() => []),
    supabaseFetch(env, SETTLEMENT_SCHEMA, "vw_invoice_discrepancy_coverage", {
      select: "*",
      period_start: `eq.${periodStart}`,
      limit: 1,
    }).catch(() => []),
    supabaseFetch(env, SETTLEMENT_SCHEMA, "monthly_process_metric_summary", {
      select: "*",
      period_start: `eq.${periodStart}`,
      limit: 1,
    }).catch(() => []),
    supabaseFetch(env, SETTLEMENT_SCHEMA, "courier_monthly_process_metric", {
          select: "courier_metric_id,courier_id,courier_name,deductions_huf,malus_huf,other_deductions_huf,closure_snapshot,financial_complaint_count,responded_complaint_count,response_average_hours,opening_to_settlement_hours,settlement_to_tig_hours,tig_to_invoice_hours,invoice_to_paid_hours,opening_to_paid_hours",
          period_start: `eq.${periodStart}`,
          limit: 10000,
        }).catch(() => []),
    supabaseFetch(env, PUBLIC_SCHEMA, "pwa_users", {
      select: "courier_id,username,active",
      active: "eq.true",
      limit: 10000,
    }).catch(() => []),
    loadLatestFinanceSnapshots(env, periodStart),
    supabaseFetch(env, SETTLEMENT_SCHEMA, "vw_admin_settlement_dashboard_fast", {
      select: "courier_id,dashboard_status_label",
      period_start: `eq.${periodStart}`, limit: 10000,
    }).catch(() => []),
    supabaseFetch(env, SETTLEMENT_SCHEMA, "monthly_process_metric_summary", {
      select: "period_start", order: "period_start.desc", limit: 1000,
    }),
    supabaseFetch(env, PUBLIC_SCHEMA, "peopleforce_card_statuses", {
      select: "courier_id,action_key,status,status_note,updated_by",
      document_month: `eq.${periodStart}`, order: "id.asc", limit: 10000,
    }).catch(() => null),
    loadSalaryAdvanceAdditions(env, periodStart),
    supabaseFetch(env,PUBLIC_SCHEMA,'peopleforce_complaints',{
      select:'id,courier_id,status',document_month:`eq.${periodStart}`,status:'in.(new,open,in_progress)',order:'id.asc',limit:10000,
    }).catch(()=>null),
  ]);

  const summaryCourierIds = new Set(courierIds);
  const candidates = new Map(activePwaUsers.map(user => [key(user.courier_id), user]));
  for (const advance of advanceAdditions) if (!candidates.has(key(advance.courier_id))) candidates.set(key(advance.courier_id), {courier_id:advance.courier_id,username:advance.courier_name || advance.courier_id});
  for (const snapshot of financeSnapshots) if (!candidates.has(key(snapshot.courier_id))) candidates.set(key(snapshot.courier_id), {courier_id:snapshot.courier_id,username:snapshot.courier_name || snapshot.courier_id});
  for (const metric of courierProcessMetricRows) if (!candidates.has(key(metric.courier_id))) candidates.set(key(metric.courier_id), {courier_id:metric.courier_id,username:metric.courier_name});
  const missingPwaUsers = [...candidates.values()].filter((user) => {
    const courierId = key(user.courier_id);
    const username = key(user.username);
    return /^\d+$/.test(courierId) && Boolean(username) && !summaryCourierIds.has(courierId);
  });
  const missingNumericIds = formatNumericIdList(missingPwaUsers.map((user) => user.courier_id));
  const missingProfiles = missingNumericIds
    ? await supabaseFetch(env, PUBLIC_SCHEMA, "courier_master", {
        select: "courier_id,courier_name,email,billing_email,warehouse_name",
        courier_id: `in.(${missingNumericIds})`,
        limit: 10000,
      }).catch(() => [])
    : [];

  const profileById = new Map([...profiles, ...missingProfiles].map((row) => [key(row.courier_id), row]));
  const workloadById = new Map(workloads.map((row) => [key(row.courier_id), row]));
  const closureById = new Map(closures.map((row) => [key(row.courier_id), row]));
  const advanceAddedById = new Map();
  for (const row of advanceAdditions) {
    const cid = key(row.courier_id);
    advanceAddedById.set(cid, (advanceAddedById.get(cid)||0) + Math.max(money(row.requested_amount_huf),0));
  }
  const statesById = new Map();
  for (const state of workflowStates || []) {
    if (key(state.action_key).startsWith("process:")) continue;
    const cid = key(state.courier_id);
    if (!statesById.has(cid)) statesById.set(cid, {});
    statesById.get(cid)[state.action_key] = state;
  }
  const workflowById = new Map(workflowDashboardRows.map(row => [key(row.courier_id),row.dashboard_status_label]));
  const courierProcessMetricById = new Map(courierProcessMetricRows.map((row) => [key(row.courier_id), row]));
  const financeSnapshotByCourier = new Map();
  financeSnapshots.forEach((snapshot) => {
    const courierId = key(snapshot.courier_id);
    if (courierId && !financeSnapshotByCourier.has(courierId)) {
      financeSnapshotByCourier.set(courierId, snapshot);
    }
  });
  const discrepancyCountByCourier = new Map();
  discrepancies.forEach((row) => {
    const courierId = key(row.courier_id);
    discrepancyCountByCourier.set(courierId, (discrepancyCountByCourier.get(courierId) || 0) + 1);
  });

  const couriers = summaryRows.map((sourceRow) => {
    const row = {
      ...sourceRow,
      route_count: sourceRow.completed_route_count || sourceRow.route_count,
      order_count: sourceRow.workload_order_count || sourceRow.order_count,
      invoiceIssueCount: discrepancyCountByCourier.get(key(sourceRow.courier_id)) || 0,
      dashboardStatus: workflowById.get(key(sourceRow.courier_id)),
      salaryAdvanceAdded: advanceAddedById.get(key(sourceRow.courier_id)) || 0,
      workflowStates: workflowStates ? statesById.get(key(sourceRow.courier_id)) || {} : null,
    };
    return buildCourierRow(
      row,
      profileById.get(key(row.courier_id)),
      workloadById.get(key(row.courier_id)),
      closureById.get(key(row.courier_id)),
      financeSnapshotByCourier.get(key(row.courier_id)),
      courierProcessMetricById.get(key(row.courier_id)),
    );
  });
  missingPwaUsers.forEach((user) => {
    couriers.push(buildCourierRow(
      { courier_id: user.courier_id, driver_name: user.username, dashboardStatus: workflowById.get(key(user.courier_id)), workflowStates: workflowStates ? statesById.get(key(user.courier_id)) || {} : null, salaryAdvanceAdded: advanceAddedById.get(key(user.courier_id)) || 0 },
      profileById.get(key(user.courier_id)),
      workloadById.get(key(user.courier_id)),
      closureById.get(key(user.courier_id)),
      financeSnapshotByCourier.get(key(user.courier_id)),
      courierProcessMetricById.get(key(user.courier_id)),
      { missingSummary: true },
    ));
  });

  applyCourierComplaintState(couriers,complaintRows,workflowStates);
  const totals = couriers.reduce(
    (acc, row) => {
      acc.couriers += 1;
      acc.routes += row.routeCount;
      acc.orders += row.orderCount;
      acc.income += row.income;
      acc.deductions += row.deductionImpact;
      acc.payable += row.payable;
      acc.issues += row.status === "Eltérés" ? 1 : 0;
      acc.tigWait += row.status === "Teljesítés-összesítőre vár" ? 1 : 0;
      acc.invoiceCheck += row.status === "Számlaellenőrzés" ? 1 : 0;
      acc.payableReady += row.status === "Kifizethető" ? 1 : 0;
      return acc;
    },
    { couriers: 0, routes: 0, orders: 0, income: 0, deductions: 0, payable: 0, issues: 0, tigWait: 0, invoiceCheck: 0, payableReady: 0 },
  );

  return jsonResponse({
    source: "supabase",
    periodStart,
    periodEnd,
    generatedAt: new Date().toISOString(),
    totals,
    couriers,
    discrepancies,
    discrepancyCoverage: discrepancyCoverage[0] || null,
    processMetrics: processMetricRows[0] || null,
    availableMonths: metricMonths.map(row => key(row.period_start).slice(0,7)),
    selectedCourier: couriers[0] || null,
  });
}

function trendMonths(periodStart) {
  const [year, month] = periodStart.split('-').map(Number);
  return [-2,-1,0].map(offset => new Date(Date.UTC(year,month-1+offset,1)).toISOString().slice(0,10));
}

async function loadSettlementTrends(periodStart, env) {
  const months = trendMonths(periodStart);
  const [summaries,advanceRows,...monthlySnapshots] = await Promise.all([supabaseFetch(env, SETTLEMENT_SCHEMA, 'monthly_process_metric_summary', {
    select: 'period_start,complaint_total,response_average_hours,source_counts,calculated_at',
    period_start: `in.(${months.join(',')})`, order: 'period_start.asc', limit: 3,
  }),loadSalaryAdvanceAdditions(env,months),...months.map(month=>loadLatestFinanceSnapshots(env,month,undefined,{trendOnly:true}))]);
  const rows = months.map((month,index) => {
    const snapshots=monthlySnapshots[index],advances=advanceRows.filter(row=>key(row.start_date).slice(0,7)===month.slice(0,7));
    const summary = summaries.find(row => row.period_start === month);
    const financial = snapshots.map(snapshot => buildCourierRow({courier_id:snapshot.courier_id},null,null,null,snapshot,null));
    const sum = field => financial.reduce((total,row)=>total+Number(row[field]||0),0);
    const timed = Number(summary?.source_counts?.response_timed_count || 0);
    return {
      month: month.slice(0,7), complaintCount: summary ? Number(summary.complaint_total) : null,
      responseAverageHours: summary && timed > 0 ? Number(summary.response_average_hours) : null,
      responseTimedCount: timed, bonusHuf: snapshots.length ? sum('bonus') : null,
      jittBonusHuf: snapshots.length ? sum('jittBonus') : null,
      kifliBonusHuf: snapshots.length ? sum('importedBonus') : null,
      malusHuf: snapshots.length ? sum('malus') : null,
      advanceCount: advances.filter(row=>money(row.requested_amount_huf)>0).length,
      advanceAmountHuf: advances.reduce((total,row)=>total+Math.max(money(row.requested_amount_huf),0),0),
      financeCoveredCouriers: snapshots.length,
      courierCount: summary?.source_counts?.courier_month_count ?? null,
      metricsCalculatedAt: summary?.calculated_at || null,
    };
  });
  return {source:'supabase',generatedAt:new Date().toISOString(),months:rows};
}

// Used only after the route's admin check. A bounded, one-minute cache also
// shares concurrent reads; failed queries are never cached as valid results.
const settlementTrendCache=new Map();
const SETTLEMENT_TREND_TTL_MS=60000;
async function settlementTrends(request, env) {
  const periodStart=parseMonth(new URL(request.url).searchParams.get('month'));
  const cacheKey=[cleanEnv(env.SUPABASE_URL),cleanEnv(env.SUPABASE_READ_KEY||env.SUPABASE_ANON_KEY||env.SUPABASE_SERVICE_ROLE_KEY),periodStart].join('|');
  let entry=settlementTrendCache.get(cacheKey);
  if(entry&&entry.expiresAt>Date.now())return jsonResponse(await entry.promise);
  if(settlementTrendCache.size>=12)settlementTrendCache.delete(settlementTrendCache.keys().next().value);
  entry={expiresAt:Infinity};
  entry.promise=loadSettlementTrends(periodStart,env).then(payload=>{entry.expiresAt=Date.now()+SETTLEMENT_TREND_TTL_MS;return payload}).catch(error=>{
    if(settlementTrendCache.get(cacheKey)===entry)settlementTrendCache.delete(cacheKey);
    throw error;
  });
  settlementTrendCache.set(cacheKey,entry);
  return jsonResponse(await entry.promise);
}

const budapestDayFormatter = new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Budapest',year:'numeric',month:'2-digit',day:'2-digit'});
function budapestDay(value = new Date()) {
  return budapestDayFormatter.format(value);
}

function courier360Identity(request) {
  const url=new URL(request.url), courierId=key(url.searchParams.get('courier'));
  if(!/^\d{1,12}$/.test(courierId)) throw Object.assign(new Error('Érvényes futár ID szükséges.'),{status:400});
  const date=url.searchParams.get('date')||budapestDay();
  if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!Number.isFinite(Date.parse(date))||new Date(date).toISOString().slice(0,10)!==date) throw Object.assign(new Error('Érvényes operatív dátum szükséges.'),{status:400});
  const month=key(url.searchParams.get('month')||date.slice(0,7));
  if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) throw Object.assign(new Error('Érvényes elszámolási hónap szükséges.'),{status:400});
  return {courierId,date,periodStart:month+'-01'};
}

const financeDrilldownCards = {
  base: ['Alapdíj'], tip: ['Borravaló'],
  importedBonus: ['Kiflis levonások / bónuszok'], importedMalus: ['Kiflis levonások / bónuszok'],
  jittBonus: ['JITT bónusz / malus'], jittMalus: ['JITT bónusz / malus'],
  correctionIncome: ['Korrekció +', 'Korrekció'], correctionDeduction: ['Korrekció -', 'Korrekció'],
  atm: ['ATM hatás'], salaryAdvance: ['Fizetés előleg', 'Fizetéselőleg'],
  reserve: ['Céltartalék 10%', 'Céltartalék'], insurance: ['Biztosítási díj', 'Biztosítás'],
};

function financeDrilldownRows(card, values) {
  const rows = [];
  for (const item of values) {
    if (!item || typeof item !== 'object') continue;
    const raw = item['Összeg'] ?? item.Osszeg ?? item.amount_value ?? item.amountHuf;
    if (raw === null || raw === undefined || raw === '') continue;
    const number = typeof raw === 'number' ? raw : Number(String(raw).replace(/\s|Ft/gi, '').replace(',', '.'));
    if (!Number.isFinite(number)) continue;
    const unit = item['Egységösszeg'];
    const calculation = item['Számítás'] || (item.Darab != null && unit != null ? `${item.Darab} × ${unit} Ft` : '');
    rows.push({label: key(item['Tétel'] || item['Megnevezés'] || item.item_label || card), amount: money(number),
      note: [calculation, item['Megjegyzés'] || item.note, item['Érvényesség']].map(key).filter(Boolean).join(' · ')});
  }
  return rows;
}

async function courierFinanceBreakdown(request, env) {
  const {courierId, periodStart} = courier360Identity(request);
  const url = new URL(request.url);
  if (url.searchParams.get('kind') === 'advance') {
    const rows = await loadSalaryAdvanceAdditions(env, periodStart, courierId);
    return jsonResponse({items: rows.map(row => ({label: 'Fizetési előleg', amount: money(row.requested_amount_huf), note: key(row.start_date)}))});
  }
  const id = key(url.searchParams.get('snapshot'));
  if (!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id)) return jsonResponse({error:'Érvényes mentett elszámolás szükséges.'},400);
  const snapshots = await supabaseFetch(env, SETTLEMENT_SCHEMA, 'courier_finance_snapshot', {
    select:'id,version,created_at',id:`eq.${id}`,courier_id:`eq.${courierId}`,period_start:`eq.${periodStart}`,limit:1,
  });
  if (!snapshots.length) return jsonResponse({error:'A kártyához tartozó mentett elszámolás nem érhető el.'},404);
  const sources = await supabaseFetch(env, SETTLEMENT_SCHEMA, 'courier_finance_snapshot_source', {
    select:'payload',snapshot_id:`eq.${id}`,source_key:'eq.card_drilldowns',limit:1,
  });
  const cards = sources[0]?.payload || {};
  const items = Object.fromEntries(Object.entries(financeDrilldownCards).map(([field, names]) => [field, names.flatMap(name => {
    const rows = cards[name];
    return Array.isArray(rows) ? [financeDrilldownRows(name, rows)] : [];
  }).find(rows => rows.length) || []]));
  const routes = cards['Körök / túrák'];
  if (Array.isArray(routes)) {
    const tips = financeDrilldownRows('Borravaló', routes.map(row => ({
      amount_value: row?.['Borravaló'], item_label: row?.['Route ID'] ? `Route ID ${row['Route ID']}` : 'Túra', note: row?.['Excel dátum'],
    }))).filter(row => row.amount);
    if (tips.length) items.tipByRoute = tips;
  }
  return jsonResponse({snapshot: snapshots[0], items});
}

function courier360Fresh(at, now = new Date()) {
  const ms=Date.parse(at),age=(now.getTime()-ms)/60000;
  return Number.isFinite(ms)&&age>=-2&&age<=20;
}

function budapestMidnightUtc(date) {
  // Derive the Budapest offset on the requested date, including summer time.
  const noon=new Date(date+'T12:00:00Z');
  const hour=Number(new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Budapest',hour:'2-digit',hour12:false}).format(noon));
  return new Date(Date.parse(date+'T00:00:00Z')-(hour-12)*3600000).toISOString();
}

function courier360Json(value) {
  if(typeof value==='string'){try{return JSON.parse(value)}catch{return {}}}
  return value&&typeof value==='object'?value:{};
}

function courier360Name(value) {
  return normalizedLogin(value).replace(/\b\d+\b/g,'').replace(/\s+/g,' ').trim();
}

const COMPLAINT_ASSIGNMENT_PREFIX='internal_complaint_assignment:';
function applyCourierComplaintState(couriers,complaints,states){
  const cases=new Map();
  for(const row of complaints||[]){if(!['new','open','in_progress'].includes(row.status))continue;const cid=key(row.courier_id);if(!cases.has(cid))cases.set(cid,[]);cases.get(cid).push(row)}
  const assignments=new Map();
  for(const state of states||[]){const value=complaintAssignment(state);if(value&&key(state.courier_id)===key(value.courierId))assignments.set(value.complaintId,value)}
  for(const courier of couriers){
    const active=cases.get(key(courier.courierId))||[];
    if(active.some(row=>row.status==='in_progress'))courier.status='Reklamáció / Folyamatban';
    courier.complaintAssignees=[...new Set(active.map(row=>assignments.get(key(row.id))?.assignee?.name).filter(Boolean))];
    courier.complaintAssignee=courier.complaintAssignees.join(', ');
    courier.complaintStateAvailable=complaints!==null&&states!==null;
  }
}
function complaintAssignment(row) {
  const value=courier360Json(row?.status_note);
  return row?.action_key?.startsWith(COMPLAINT_ASSIGNMENT_PREFIX)&&value.schemaVersion===1&&value.complaintId===row.action_key.slice(COMPLAINT_ASSIGNMENT_PREFIX.length)?value:null;
}
async function complaintAssignees(env) {
  const users=await supabaseFetch(env,PUBLIC_SCHEMA,'pwa_users',{courier_id:'eq.7644',active:'eq.true',select:'username,email,role',limit:1});
  const gurzo=users.find(row=>['admin','superadmin'].includes(key(row.role).toLowerCase()));
  const validEmail=value=>/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(key(value));
  return [{key:'bagoly_zoltan',name:'Bagoly Zoltán',email:'zoltan.bagoly@jitt.hu'},
    {key:'gurzo_balazs',name:'Gurzó Balázs',email:validEmail(gurzo?.email)?key(gurzo.email):null}];
}

function courier360Stops(route, storedStops=[]) {
  const raw=storedStops.length?storedStops:route.checkpoints||route.stopProgress||route.stops||[];
  if(!Array.isArray(raw))return [];
  return raw.filter(row=>row&&typeof row==='object').map((row,index)=>{
    const data={...courier360Json(row.stop_json),...row};
    const state=key(data.state||data.status).toUpperCase();
    const completed=['COMPLETED','DELIVERED','FINISHED','DONE'].includes(state)||Boolean(data.deliveredAt||data.realDepartureTime);
    const address=data.address||data.fullAddress||data.addressText||data.street;
    return {position:Number(data.sequence||data.position||data.stopPosition||index+1),orderId:key(data.order_id||data.orderId||data.customerOrderId||data.id),
      address:typeof address==='string'?address:null,state:completed?'COMPLETED':state||'UNKNOWN',
      windowFrom:data.deliverSince||data.customerSlotFrom||data.windowFrom||data.timeWindowFrom||null,
      windowTo:data.deliverTill||data.customerSlotTo||data.windowTo||data.timeWindowTo||null,
      plannedArrival:data.planned_arrival_at||data.plannedArrivalAt||data.plannedArrivalTime||null,
      estimatedArrival:data.estimatedArrivalAt||data.estimatedArrivalTime||data.eta||null,
      actualArrival:data.actual_arrival_at||data.actualArrivalAt||data.realArrivalTime||null,
      delayMinutes:metricNumber(data.delay_minutes??data.delayMinutes??data.deltaMinutes),
      note:key(data.deliveryNote||data.deliveryInstructions||data.customerNote),
      fetchedAt:row.fetched_at||null};
  }).sort((a,b)=>a.position-b.position);
}

function courier360RouteObjects(value, depth=0) {
  if(!value||typeof value!=='object'||depth>8)return [];
  if(Array.isArray(value))return value.flatMap(row=>courier360RouteObjects(row,depth+1));
  const isRoute=Boolean(value.cargoRouteId||value.routeExternalId||value.routeId||value.route_id)||
    Boolean(value.id&&(value.checkpoints||value.stopProgress));
  return [...(isRoute?[value]:[]),...Object.values(value).filter(v=>v&&typeof v==='object').flatMap(v=>courier360RouteObjects(v,depth+1))];
}

function courier360RouteActive({date, routeId, activityAt, returned, state}) {
  const activityMatches = !activityAt || !Number.isFinite(Date.parse(activityAt)) || budapestDay(new Date(activityAt)) === date;
  return Boolean(routeId && activityMatches && !returned &&
    ['ON_ROUTE','ON_TOUR','DELIVERING','SLIPPING','LATE','RETURNING','DRIVING','DEPARTED','IN_PROGRESS','ACTIVE','ON_THE_WAY','IN_ROUTE'].includes(state));
}

function courier360Working({fresh, routeActive, attendanceFresh, attended, state}) {
  if (fresh && state === 'NO_SHOW') return {working: false, label: 'Nem jelent meg'};
  if (fresh && routeActive) return {working: true, label: 'Túrán'};
  if (fresh && state === 'LOADING') return {working: true, label: 'Rakodik'};
  if (attendanceFresh && attended.checkin_end) return {working: false, label: 'Giritonból kijelentkezett'};
  if (attendanceFresh && attended.checkin_start) return {working: true, label: 'Giritonba bejelentkezve'};
  if (fresh && ['NO_SHOW','OFFLINE','FINISHED','INACTIVE'].includes(state))
    return {working: false, label: state === 'NO_SHOW' ? 'Hub: nem érkezett meg' : 'Nincs aktív munkavégzés'};
  if (attendanceFresh && /didn.t come|absent|nem érkezett/i.test(attended.activity_status || ''))
    return {working: false, label: 'Giriton: nem érkezett meg'};
  return {working: null, label: fresh ? 'Friss Hub-jelzés · ' + (state || 'ismeretlen állapot') : 'Nincs friss adat'};
}

function courier360ShiftEnabled(row) {
  return row.active !== false && !['cancelled','canceled','deleted','torolt','torolve'].includes(normalizedLogin(row.status));
}

function courier360BuildOperational({date,now,monitor=[],detail=[],map=[],stops=[],statistics=[],checkins=[],attendance=[],bookings=[],giritonShifts=[]}) {
  const sameDay=row=>row.fetched_at&&budapestDay(new Date(row.fetched_at))===date;
  const newest=rows=>[...rows].sort((a,b)=>key(b.fetched_at||b.updated_at).localeCompare(key(a.fetched_at||a.updated_at)))[0];
  const signals=[...monitor.map(r=>({...r,source:'Hub monitoring'})),...map.map(r=>({...r,source:'Hub térkép'}))].filter(sameDay);
  const signal=newest(signals), rawDetail=newest(detail.filter(sameDay));
  const payload=courier360Json(rawDetail?.response_json);
  const signalJson=courier360Json(signal?.courier_json);
  const routeIds=[signal?.route_id,...(Array.isArray(signal?.route_ids)?signal.route_ids:[]),signalJson.cargoRouteId,signalJson.routeExternalId].filter(Boolean).map(String);
  const routes=courier360RouteObjects(payload);
  // Never attach another route's stops to the route in the newest monitoring signal.
  const route=routes.find(row=>routeIds.includes(key(row.cargoRouteId||row.routeExternalId||row.routeId||row.route_id||row.id)))||
    (!routeIds.length?(routes.find(row=>Boolean(row.checkpoints||row.stopProgress||row.stops))||{...courier360Json(payload.shift),stops:payload.stops}):
      routeIds.includes(key(rawDetail?.route_id))?{...courier360Json(payload.shift),stops:payload.stops}:null)||{};
  const routeId=key(signal?.route_id||signalJson.cargoRouteId||signalJson.routeExternalId||route.cargoRouteId||route.routeExternalId||route.routeId||rawDetail?.route_id||routeIds[0]);
  const matchingStops=routeId?stops.filter(row=>key(row.route_id)===routeId&&sameDay(row)):[];
  const routeStops=routeId?courier360Stops(route,matchingStops):[];
  const stopsUpdatedAt=newest(matchingStops)?.fetched_at||(routeStops.length?rawDetail?.fetched_at:null)||null;
  const stopsFresh=Boolean(date===budapestDay(now)&&courier360Fresh(stopsUpdatedAt,now));
  const dailyStats=statistics.filter(row=>row.work_date===date);
  const routeStat=dailyStats.find(row=>key(row.route_id)===routeId)||{};
  const lastSourceAt=signal?.fetched_at||rawDetail?.fetched_at||null;
  const fresh=Boolean(lastSourceAt&&date===budapestDay(now)&&courier360Fresh(lastSourceAt,now));
  const shiftState=key(signal?.shift_status||signalJson.shiftStatus).toUpperCase();
  const state=shiftState==='NO_SHOW'?'NO_SHOW':key(signal?.status||signalJson.status||route.status).toUpperCase();
  const returned=route.realReturn||route.actualReturnAt||route.finishedAt||routeStat.returned_at||null;
  const departed=route.realDeparture||route.departedAt||routeStat.departed_at||signal?.departed_at||null;
  const activityAt=route.actualStartAt||route.plannedStartAt||route.departedAt||route.plannedDepartureAt||signalJson.plannedStartAt;
  const routeActive=courier360RouteActive({date,routeId,activityAt,returned,state});
  const attended=newest(attendance.map(row=>({...row,fetched_at:row.updated_at})))||null;
  const attendanceFresh=Boolean(attended&&date===budapestDay(now)&&courier360Fresh(attended.updated_at,now));
  const {working,label}=courier360Working({fresh,routeActive,attendanceFresh,attended,state});
  const nextStop=routeStops.find(stop=>!['COMPLETED','REJECTED','CANCELLED','CANCELED'].includes(stop.state))||null;
  const activeBookings=bookings.filter(courier360ShiftEnabled);
  const shifts=activeBookings.map(row=>({date:row.work_date,start:row.slot_from,end:row.slot_to,warehouse:row.warehouse_code||key(row.warehouse_id),
    label:row.shift_text,source:'Hub beosztott kezdési idősáv',updatedAt:row.last_seen_at||row.updated_at,isArrivalSlot:true}));
  for(const row of giritonShifts.filter(courier360ShiftEnabled))
    shifts.push({date:row.work_date,start:row.start_time,end:row.end_time,warehouse:row.warehouse,label:row.status,source:'Giriton beosztás',updatedAt:row.fetched_at||row.updated_at,isArrivalSlot:false});
  shifts.sort((a,b)=>(a.date+key(a.start)).localeCompare(b.date+key(b.start)));
  const seen=new Set(),uniqueShifts=shifts.filter(row=>{const key=[row.date,row.start,row.warehouse,row.source].join('|');if(seen.has(key))return false;seen.add(key);return true;});
  const nowParts=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Budapest',hour:'2-digit',minute:'2-digit',hour12:false}).format(now);
  const upcoming=uniqueShifts.find(row=>row.date>budapestDay(now)||(row.date===budapestDay(now)&&key(row.start).slice(0,5)>nowParts))||null;
  const logs=[];
  for(const container of [payload,payload.shift,route])for(const event of container?.log||container?.logs||container?.events||[]){
    if(typeof event!=='object')continue;
    const eventAt=event.occurredAt||event.createdAt||event.created_at||event.timestamp||event.time||null;
    if(eventAt&&Number.isFinite(Date.parse(eventAt))&&budapestDay(new Date(eventAt))!==date)continue;
    logs.push({at:eventAt,
      label:key(event.label||event.text||event.type||event.eventType||event.name),detail:key(event.message||event.description),source:'Hub napló'});
  }
  for(const row of checkins)logs.push({at:row.created_at,label:key(row.event_type),detail:key(row.shift_name||row.warehouse),source:'Futár műszakjelzés'});
  const stamp=(field,label)=>{for(const row of dailyStats)if(row[field])logs.push({at:row[field],label,detail:'Túra #'+row.route_id,source:'Hub túrastatisztika'})};
  stamp('queue_started_at','Sorbaállás');stamp('actual_shift_start_at','Tényleges műszakkezdés');stamp('departed_at','Raktári indulás');stamp('returned_at','Raktári visszaérkezés');
  logs.sort((a,b)=>key(a.at).localeCompare(key(b.at)));
  return {date,currentWorking:working,label,fresh,lastSourceAt,hubStatus:state||null,attendance:attended,attendanceFresh,
    liveStatus:fresh?courier360MonitorStatus(state,shiftState,routeActive,working):null,
    liveDelay:fresh?metricNumber(signalJson.delayMinutes):null,
    route:routeId?{id:routeId,status:state,warehouse:signal?.warehouse_code||rawDetail?.warehouse_code||null,stops:routeStops,
      totalStops:signal?.stops_total??(routeStops.length||null),completedStops:signal?.deliveries_completed??routeStops.filter(row=>row.state==='COMPLETED').length,
      nextStop:routeActive&&fresh&&stopsFresh?nextStop:null,lastKnownNextStop:nextStop,active:routeActive&&fresh,stopsFresh,stopsUpdatedAt,
      departedAt:departed,returnedAt:returned,plannedReturn:route.plannedReturn||route.plannedReturnAt||routeStat.planned_return_at||null,
      vehiclePlate:signal?.vehicle_plate||route.vehiclePlate||routeStat.vehicle_plate||null,updatedAt:lastSourceAt}:null,
    shifts:uniqueShifts,nextShift:upcoming,dayStatistics:dailyStats,logs};
}

const courierAttendanceClock = new Intl.DateTimeFormat('en-GB',{
  timeZone:'Europe/Budapest',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23',
});

function courierAttendanceBoard({date,now,hub,giriton,attendance,directory}) {
  const byId = new Map();
  const byName = new Map();
  const nameById = new Map();
  const validId = value => /^\d{1,12}$/.test(key(value)) ? key(value) : '';
  const register = (id,name) => {
    if (!id) return;
    const normalized = courier360Name(name);
    if (!normalized) return;
    if (!nameById.has(id)) nameById.set(id,key(name));
    if (!byName.has(normalized)) byName.set(normalized,new Set());
    byName.get(normalized).add(id);
  };
  for (const row of [...directory,...hub,...giriton]) register(validId(row.courier_id),row.courier_name);

  const getCourier = (id,name) => {
    if (!byId.has(id)) byId.set(id,{courierId:validId(id),courierName:nameById.get(id) || key(name),shifts:[],checkin:'',checkout:'',uncertain:false});
    return byId.get(id);
  };
  let unmatchedShifts = 0;
  for (const row of [...hub,...giriton]) {
    if (!courier360ShiftEnabled(row) || normalizedLogin(row.status) === 'ures') continue;
    const name = courier360Name(row.courier_name);
    const names = byName.get(name);
    const id = validId(row.courier_id) || (names?.size === 1 ? [...names][0] : name && 'name:'+name);
    const start = scheduleTime(row.start_time || row.slot_from);
    const warehouse = key(row.warehouse_code || row.warehouse).trim().toUpperCase().match(/\bBUD[12]\b/)?.[0] || '';
    if (!id || !start) { unmatchedShifts++; continue; }
    const courier = getCourier(id,row.courier_name);
    if (names?.size > 1 && !courier.courierId) courier.uncertain = true;
    if (!courier.shifts.some(shift=>shift.start===start && shift.warehouse===warehouse)) courier.shifts.push({start,warehouse});
  }

  for (const row of attendance) {
    const info = courier360Json(row.response_json);
    const explicitId = validId(info.courier_id || info.courier?.courier_id || info.courier?.courierId);
    const name = courier360Name(row.courier_name);
    const names = byName.get(name);
    const checkin = scheduleTime(row.checkin_start);
    if (!checkin) continue;
    if (!explicitId && names?.size > 1) {
      for (const candidate of names) if (byId.has(candidate)) byId.get(candidate).uncertain = true;
      continue;
    }
    const id = explicitId || (names?.size === 1 ? [...names][0] : name && 'name:'+name);
    if (!id) continue;
    const checkout = scheduleTime(row.checkin_end);
    const courier = getCourier(id,row.courier_name);
    if (!courier.checkin || checkin < courier.checkin) courier.checkin = checkin;
    if (checkout > courier.checkout) courier.checkout = checkout;
  }

  const syncedAt = attendance[0]?.fetched_at || null;
  const syncAge = +now - Date.parse(syncedAt);
  const attendanceFresh = syncedAt !== null && syncAge >= 0 && syncAge <= 30*60000;
  const [hour,minute,second] = courierAttendanceClock.format(now).split(':').map(Number);
  const currentMinute = hour*60 + minute + second/60;
  const priority = {overdue:0,due:1,upcoming:2,unknown:3,arrived:4};
  const couriers = [...byId.values()].map(({uncertain,...courier}) => {
    courier.shifts.sort((a,b)=>a.start.localeCompare(b.start)||a.warehouse.localeCompare(b.warehouse));
    const [startHour,startMinute] = (courier.shifts[0]?.start || '').split(':').map(Number);
    const untilStart = startHour*60 + startMinute - currentMinute;
    const status = courier.checkin ? 'arrived' : untilStart > 30 ? 'upcoming' :
      !attendanceFresh || uncertain ? 'unknown' : untilStart <= 0 ? 'overdue' : 'due';
    return {...courier,status};
  });
  couriers.sort((a,b)=>priority[a.status]-priority[b.status] ||
    (a.shifts[0]?.start || '99:99').localeCompare(b.shifts[0]?.start || '99:99') ||
    a.courierName.localeCompare(b.courierName,'hu'));
  return {date,syncedAt,attendanceFresh,unmatchedShifts,couriers};
}

async function courierAttendanceData(env,now = new Date()) {
  const date = budapestDay(now);
  const day = {work_date:'eq.'+date,order:'id.asc',limit:3000};
  const results = await Promise.allSettled([
    supabaseFetch(env,PUBLIC_SCHEMA,'courier_hub_shift_bookings_raw',{
      ...day,dsp_id:'eq.8',warehouse_id:'in.(1,2)',select:'courier_id,courier_name,warehouse_code,slot_from,status,active',
    }),
    supabaseFetch(env,PUBLIC_SCHEMA,'giriton_shifts_raw',{
      ...day,select:'courier_id,courier_name,warehouse,start_time,status',
    }),
    supabaseFetch(env,PUBLIC_SCHEMA,'giriton_attendance_raw',{
      ...day,source_name:'eq.giriton-attendance-robot',order:'fetched_at.desc,id.asc',
      select:'courier_name,checkin_start,checkin_end,response_json,fetched_at',
    }),
    supabaseFetch(env,PUBLIC_SCHEMA,'courier_master',{
      select:'courier_id,courier_name',order:'courier_id.asc',limit:6000,
    }),
  ]);
  const [hub,giriton,attendance,directory] = results.map(result=>result.value || []);
  if (results.slice(0,3).every(result=>result.status==='rejected')) {
    return jsonResponse({error:'A mai jelenléti adatok most nem tölthetők be.'},502);
  }
  const partial = results.some((result,index)=>result.status==='rejected' || result.value.length >= (index === 3 ? 6000 : day.limit));
  return jsonResponse({...courierAttendanceBoard({date,now,hub,giriton,attendance,directory}),partial});
}

async function courier360CalendarShifts(env,courierId,date) {
  const month = date.slice(0,7);
  const first = month+'-01';
  const [year,number] = month.split('-').map(Number);
  const end = new Date(Date.UTC(year,number,1)).toISOString().slice(0,10);
  const params = {courier_id:`eq.${courierId}`,and:`(work_date.gte.${first},work_date.lt.${end})`,order:'id.asc',limit:1000};
  const results = await Promise.allSettled([
    supabaseFetch(env,PUBLIC_SCHEMA,'courier_hub_shift_bookings_raw',{...params,select:'work_date,status,active'}),
    supabaseFetch(env,PUBLIC_SCHEMA,'giriton_shifts_raw',{...params,select:'work_date,status'}),
  ]);
  if (results.every(result=>result.status==='rejected')) return jsonResponse({error:'A havi műszakok nem tölthetők be.'},502);
  const rows = results.flatMap(result=>result.value || []);
  return jsonResponse({courierId,month,dates:[...new Set(rows.filter(courier360ShiftEnabled).map(row=>row.work_date))].sort(),
    partial:results.some(result=>result.status==='rejected'||result.value.length===params.limit)});
}

async function courier360Data(request, env, now = new Date()) {
  const {courierId,date,periodStart}=courier360Identity(request);
  const scope = new URL(request.url).searchParams.get('scope');
  if (scope === 'calendar') return courier360CalendarShifts(env,courierId,date);
  const dayOnly = scope === 'day';
  const sources=[];
  const safe=async(table,schema,params)=>{
    try{const rows=await supabaseFetch(env,schema,table,params);sources.push({table,available:true,count:rows.length});return rows;}
    catch{sources.push({table,available:false,count:null});return [];}
  };
  const monthly = (...args)=>dayOnly ? [] : safe(...args);
  const sameId={courier_id:`eq.${courierId}`};
  const endDate=dayOnly ? date : new Date(Date.parse(date)+31*86400000).toISOString().slice(0,10);
  const [profiles,masters,monitor,detail,map,storedStops,statistics,checkins,allAttendance,bookings,giritonShifts,complaints,documents,states,acceptances,metrics,closures,snapshots,advanceAdditions,dashboardRows] = await Promise.all([
    safe('courier_master',PUBLIC_SCHEMA,{...sameId,select:dayOnly?'courier_id,courier_name':'courier_id,courier_name,warehouse_name,company_name,bank_account_number',order:'courier_id.asc',limit:1}),
    safe('courier_hub_master',PUBLIC_SCHEMA,{...sameId,select:'courier_id,courier_name,user_number,giriton_person_id,warehouse_code,vehicle_registration_number,fetched_at',order:'fetched_at.desc',limit:4}),
    safe('courier_hub_live_monitoring_courier_snapshot_latest',PUBLIC_SCHEMA,{...sameId,select:'courier_id,route_id,status,shift_status,warehouse_code,deliveries_completed,stops_total,vehicle_plate,departed_at,courier_json,fetched_at',order:'fetched_at.desc',limit:4}),
    safe('courier_hub_live_monitoring_courier_latest',PUBLIC_SCHEMA,{...sameId,select:'courier_id,route_id,warehouse_code,response_json,fetched_at',status_code:'eq.200',order:'fetched_at.desc',limit:4}),
    safe('courier_hub_live_map_courier_latest',PUBLIC_SCHEMA,{...sameId,select:'courier_id,status,shift_status,warehouse_code,deliveries_completed,stops_total,vehicle_plate,route_ids,courier_json,fetched_at',order:'fetched_at.desc',limit:4}),
    dayOnly ? [] : safe('courier_hub_live_map_stop_latest',PUBLIC_SCHEMA,{...sameId,select:'route_id,order_id,sequence,address,planned_arrival_at,actual_arrival_at,state,delay_minutes,stop_json,fetched_at',and:`(fetched_at.gte.${budapestMidnightUtc(date)},fetched_at.lt.${budapestMidnightUtc(new Date(Date.parse(date)+86400000).toISOString().slice(0,10))})`,order:'fetched_at.desc,route_id.asc,sequence.asc',limit:2000}),
    safe('courier_hub_route_statistics',PUBLIC_SCHEMA,{...sameId,select:'work_date,route_id,warehouse_code,queue_started_at,actual_shift_start_at,departed_at,returned_at,planned_return_at,vehicle_plate,orders,stops,source_updated_at',work_date:`eq.${date}`,order:'route_id.asc',limit:100}),
    safe('courier_shift_checkins',PUBLIC_SCHEMA,{...sameId,select:'work_date,event_type,created_at,warehouse,shift_name',work_date:`eq.${date}`,order:'created_at.asc',limit:200}),
    safe('giriton_attendance_raw',PUBLIC_SCHEMA,{select:'courier_name,activity_status,checkin_start,checkin_end,updated_at',work_date:`eq.${date}`,order:'courier_name.asc',limit:2000}),
    safe('courier_hub_shift_bookings_raw',PUBLIC_SCHEMA,{...sameId,select:'work_date,warehouse_code,warehouse_id,shift_text,slot_from,slot_to,status,active,last_seen_at,updated_at',and:`(work_date.gte.${date},work_date.lte.${endDate})`,order:'work_date.asc,slot_from.asc',limit:1000}),
    safe('giriton_shifts_raw',PUBLIC_SCHEMA,{...sameId,select:'work_date,start_time,end_time,warehouse,status,fetched_at',and:`(work_date.gte.${date},work_date.lte.${endDate})`,order:'work_date.asc,start_time.asc',limit:1000}),
    monthly('peopleforce_complaints',PUBLIC_SCHEMA,{...sameId,select:'id,document_type,document_month,message,status,created_by,created_at,admin_response,responded_at,responded_by',document_month:`eq.${periodStart}`,order:'created_at.desc',limit:1000}),
    monthly('peopleforce_documents',PUBLIC_SCHEMA,{...sameId,select:'id,document_type,title,file_name,mime_type,file_size,note,uploaded_by,uploaded_at',document_month:`eq.${periodStart}`,order:'uploaded_at.desc',limit:300}),
    monthly('peopleforce_card_statuses',PUBLIC_SCHEMA,{...sameId,select:'action_key,status,status_note,updated_by,created_at,updated_at',document_month:`eq.${periodStart}`,order:'updated_at.desc',limit:100}),
    monthly('pwa_workflow_acceptance_snapshots',SETTLEMENT_SCHEMA,{...sameId,select:'id,action_key,process_id,payable_huf,tig_final_total_huf,accepted_at,accepted_by',period_start:`eq.${periodStart}`,order:'accepted_at.asc',limit:300}),
    monthly('courier_monthly_process_metric',SETTLEMENT_SCHEMA,{...sameId,select:'*',period_start:`eq.${periodStart}`,limit:1}),
    monthly('courier_monthly_closure',SETTLEMENT_SCHEMA,{...sameId,select:'status,payable_huf,closed_at,closed_by,reopened_at,reopened_by,recipient_name,bank_account_number,payment_note,invoice_number,snapshot',period_start:`eq.${periodStart}`,limit:1}),
    dayOnly ? [] : loadLatestFinanceSnapshots(env,periodStart,courierId).then(rows=>{sources.push({table:'courier_finance_snapshot',available:true,count:rows.length});return rows}).catch(()=>{sources.push({table:'courier_finance_snapshot',available:false,count:null});return []}),
    dayOnly ? [] : loadSalaryAdvanceAdditions(env,periodStart).then(rows=>{sources.push({table:'Fizetési előlegek',available:true,count:rows.length});return rows}).catch(()=>{sources.push({table:'Fizetési előlegek',available:false,count:null});return []}),
    monthly('vw_admin_settlement_dashboard_fast',SETTLEMENT_SCHEMA,{select:'courier_id,dashboard_status_label',period_start:`eq.${periodStart}`,order:'courier_id.asc',limit:10000}),
  ]);
  if(!profiles.length&&!masters.length&&!snapshots.length&&!metrics.length&&!monitor.length) return jsonResponse({error:'A futárhoz nem található adat.'},404);
  const names=new Set([...profiles,...masters,...snapshots].map(row=>courier360Name(row.courier_name)).filter(Boolean));
  const matchedAttendance=allAttendance.filter(row=>names.has(courier360Name(row.courier_name)));
  const attendanceNames=new Set(matchedAttendance.map(row=>key(row.courier_name)));
  const attendance=attendanceNames.size>1?[]:matchedAttendance;
  if(attendanceNames.size>1)sources.push({table:'Giriton névazonosítás',available:false,count:null});
  const operational=courier360BuildOperational({date,now,monitor,detail,map,stops:storedStops,statistics,checkins,attendance,bookings,giritonShifts});
  if (dayOnly) return jsonResponse({courier:{id:courierId},date,operational,sources});
  const financeSnapshot=snapshots[0]||null;
  const paymentSources=financeSnapshot?await safe('courier_finance_snapshot_source',SETTLEMENT_SCHEMA,{
    snapshot_id:`eq.${financeSnapshot.id}`,source_key:'in.(tig_breakdown,courier_profile)',select:'source_key,payload',limit:10,
  }):[];
  const [complaintNotes,historyParents,assignees]=await Promise.all([
    safe('peopleforce_complaint_notes',PUBLIC_SCHEMA,{...sameId,period_start:`eq.${periodStart}`,select:'note,updated_by,updated_at',limit:1}),
    safe('courier_finance_snapshot',SETTLEMENT_SCHEMA,{...sameId,period_start:`eq.${periodStart}`,select:'id,version,previous_snapshot_id,created_at,created_by',order:'version.desc,created_at.desc,id.desc',limit:2}),
    complaintAssignees(env).catch(()=>[{key:'bagoly_zoltan',name:'Bagoly Zoltán',email:'zoltan.bagoly@jitt.hu'},{key:'gurzo_balazs',name:'Gurzó Balázs',email:null}]),
  ]);
  const previousParent=historyParents[0]?.id===financeSnapshot?.id?historyParents.find(row=>row.id===historyParents[0].previous_snapshot_id):null;
  const previousItems=previousParent?await safe('courier_finance_snapshot_item',SETTLEMENT_SCHEMA,{snapshot_id:`eq.${previousParent.id}`,section:'eq.finance',amount_kind:'eq.huf',select:'item_key,item_label,amount_value,section,amount_kind',limit:500}):[];
  const assignments=states.filter(row=>key(row.action_key).startsWith(COMPLAINT_ASSIGNMENT_PREFIX));
  const publicStates=states.filter(row=>!key(row.action_key).startsWith(COMPLAINT_ASSIGNMENT_PREFIX));
  const workflowStates=Object.fromEntries(publicStates.filter(row=>!key(row.action_key).startsWith('process:')).map(row=>[row.action_key,row]));
  const closure=closures[0]||null;
  const finance=financeSnapshot?buildCourierRow({courier_id:courierId,workflowStates,dashboardStatus:dashboardRows.find(row=>key(row.courier_id)===courierId)?.dashboard_status_label,salaryAdvanceAdded:advanceAdditions.filter(row=>key(row.courier_id)===courierId).reduce((s,r)=>s+money(r.requested_amount_huf),0)},profiles[0],null,closure,financeSnapshot,metrics[0]):null;
  const eventLog=[...operational.logs,...publicStates.map(row=>({at:row.updated_at,label:row.action_key+' · '+row.status,detail:row.status_note,actor:row.updated_by,source:'Elszámolási folyamat'})),
    ...acceptances.map(row=>({at:row.accepted_at,label:row.action_key+' elfogadása',detail:`Elfogadott összeg: ${row.payable_huf ?? row.tig_final_total_huf ?? '—'} Ft`,actor:row.accepted_by,source:'Elfogadási mentés'}))]
    .sort((a,b)=>key(b.at).localeCompare(key(a.at)));
  return jsonResponse({courier:{id:courierId,name:key(profiles[0]?.courier_name||masters[0]?.courier_name||financeSnapshot?.courier_name||courierId),warehouse:key(profiles[0]?.warehouse_name||masters[0]?.warehouse_code)},
    date,periodStart,generatedAt:now.toISOString(),operational,finance,financeSnapshot:financeSnapshot?{id:financeSnapshot.id,version:financeSnapshot.version,createdAt:financeSnapshot.created_at,items:financeSnapshot.items}:null,
    complaints:complaints.filter(row=>key(row.status).toLowerCase()!=='deleted'),complaintNote:complaintNotes[0]||null,
    complaintAssignees:assignees,complaintAssignments:Object.fromEntries(assignments.map(row=>{const value=complaintAssignment(row);return [value?.complaintId,value]}).filter(([id,value])=>id&&value)),
    financeComparison:courier360FinanceComparison(financeSnapshot,previousParent,previousItems),documents,workflowStates,acceptances,closure,processMetric:metrics[0]||null,eventLog,sources,
    payment:courier360Payment({courierId,periodStart,profile:profiles[0],snapshot:financeSnapshot,paymentSources,documents,workflowStates,processStates:states,closure,acceptances,complaints,sources})});
}

function courier360FinanceComparison(snapshot,previous,previousItems=[]) {
  if(!snapshot||!previous||!previousItems.length)return {available:false,rows:[]};
  const before=new Map(previousItems.map(row=>[row.item_key,row])),after=new Map((snapshot.items||[]).filter(row=>row.section==='finance'&&row.amount_kind==='huf').map(row=>[row.item_key,row]));
  const rows=[...new Set([...before.keys(),...after.keys()])].map(name=>{
    const old=before.get(name),current=after.get(name),oldAmount=paymentNumber(old?.amount_value),newAmount=paymentNumber(current?.amount_value);
    return {key:name,label:current?.item_label||old?.item_label||name,beforeHuf:oldAmount,afterHuf:newAmount,differenceHuf:oldAmount!==null&&newAmount!==null?newAmount-oldAmount:null};
  }).filter(row=>row.beforeHuf!==row.afterHuf);
  return {available:true,before:{id:previous.id,version:previous.version,createdAt:previous.created_at,createdBy:previous.created_by},after:{id:snapshot.id,version:snapshot.version,createdAt:snapshot.created_at},rows};
}

async function courier360AssignComplaint(body,env,user,executionContext) {
  const courierId=key(body.courierId),month=key(body.month),id=key(body.complaintId),operationId=key(body.operationId);
  if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(operationId))return jsonResponse({error:'Hiányzó műveletazonosító. Frissítsd az ablakot.'},422);
  const [complaints,rows,assignees]=await Promise.all([
    supabaseFetch(env,PUBLIC_SCHEMA,'peopleforce_complaints',{id:`eq.${id}`,courier_id:`eq.${courierId}`,document_month:`eq.${month}-01`,select:'id,status,courier_name,message',limit:1}),
    supabaseFetch(env,PUBLIC_SCHEMA,'peopleforce_card_statuses',{courier_id:`eq.${courierId}`,document_month:`eq.${month}-01`,action_key:`eq.${COMPLAINT_ASSIGNMENT_PREFIX}${id}`,select:'action_key,status,status_note,updated_at',limit:1}),
    complaintAssignees(env),
  ]);
  const complaint=complaints[0],old=rows[0],previous=complaintAssignment(old);
  if(!complaint||complaint.status==='deleted')return jsonResponse({error:'A reklamáció nem található.'},404);
  if(previous?.assignmentId===operationId)return jsonResponse({ok:true,assignment:previous,message:'A felelős kijelölése már mentve van.'});
  if(['closed','resolved'].includes(complaint.status))return jsonResponse({error:'Lezárt reklamációt előbb nyiss vissza.'},409);
  if(old&&!previous)return jsonResponse({error:'A felelős mentése nem értelmezhető. Frissítsd az adatokat.'},409);
  if(key(body.expectedAssignmentId)!==key(previous?.assignmentId))return jsonResponse({error:'A felelőst időközben módosították. Frissítsd az ablakot.'},409);
  if(previous?.notification?.status==='sending')return jsonResponse({error:'Az értesítés küldése folyamatban van. Kérlek, várj a felelős módosításával.'},409);
  const assignee=assignees.find(row=>row.key===body.assigneeKey);
  if(!assignee?.email)return jsonResponse({error:'Ehhez a felelőshöz nincs ellenőrzött e-mail-cím.'},422);
  if(previous?.assignee?.key===assignee.key&&previous.assignee.email===assignee.email&&['pending','sent'].includes(previous.notification?.status))return jsonResponse({ok:true,assignment:previous,message:'Ez a felelős már ki van jelölve; nem küldtünk ismételt értesítést.'});
  const now=new Date().toISOString(),link=new URL('https://jitthub.jitthub.workers.dev/');
  link.searchParams.set('courier',courierId);link.searchParams.set('month',month);link.searchParams.set('complaint',id);
  const value={schemaVersion:1,complaintId:id,courierId,month,assignmentId:operationId,assignee,assignedAt:now,assignedBy:user.username,
    courierName:key(complaint.courier_name)||courierId,complaintMessage:key(complaint.message),hubUrl:link.href,
    notes:previous?.notes||[],notesRevision:previous?.notesRevision||'',
    notification:{status:'pending',queuedAt:now,sentAt:null},
    history:[...(previous?.history||[]),...(previous?[{assignee:previous.assignee,assignedAt:previous.assignedAt,assignedBy:previous.assignedBy,notification:previous.notification}]:[])].slice(-30)};
  const url=new URL(`${cleanEnv(env.SUPABASE_URL)}/rest/v1/peopleforce_card_statuses`),method=old?'PATCH':'POST';
  const data={courier_id:courierId,courier_name:value.courierName,document_month:month+'-01',action_key:COMPLAINT_ASSIGNMENT_PREFIX+id,status:'open',status_note:JSON.stringify(value),updated_by:user.username,updated_at:now};
  if(old)for(const [name,filter]of Object.entries({courier_id:`eq.${courierId}`,document_month:`eq.${month}-01`,action_key:`eq.${data.action_key}`,updated_at:`eq.${old.updated_at}`,status:`eq.${old.status}`}))url.searchParams.set(name,filter);
  else url.searchParams.set('on_conflict','courier_id,document_month,action_key');
  const credential=cleanEnv(env.SUPABASE_READ_KEY||env.SUPABASE_SERVICE_ROLE_KEY);
  const response=await fetch(url,{method,headers:{apikey:credential,authorization:`Bearer ${credential}`,'content-profile':PUBLIC_SCHEMA,'accept-profile':PUBLIC_SCHEMA,'content-type':'application/json',prefer:old?'return=representation':'resolution=ignore-duplicates,return=representation'},body:JSON.stringify(data)});
  const saved=await response.json().catch(()=>null);
  if(!response.ok||!Array.isArray(saved)||saved.length!==1)return jsonResponse({error:'A kijelölés nem igazolható, vagy időközben módosult. Frissítsd az ablakot.'},409);
  // Wake the PWA host if its free instance is asleep. Delivery itself is owned
  // by the persisted queue and the PWA's existing SMTP/Resend configuration.
  if(executionContext?.waitUntil){
    const wakeUrl=new URL('/api/health',cleanEnv(env.PWA_API_URL||'https://futar.jitt.hu'));
    executionContext.waitUntil(fetch(wakeUrl,{headers:{accept:'application/json'},signal:AbortSignal.timeout(25000)}).catch(()=>{}));
  }
  return jsonResponse({ok:true,assignment:value,message:'A felelős mentve. Az e-mailes értesítés küldésre vár.'});
}

async function courier360ComplaintAction(request,env,user,executionContext) {
  if(request.headers.get('origin')!==new URL(request.url).origin)return jsonResponse({error:'Érvénytelen kérésforrás.'},403);
  if(!request.headers.get('content-type')?.includes('application/json'))return jsonResponse({error:'JSON kérés szükséges.'},415);
  const body=await request.json().catch(()=>null),courierId=key(body?.courierId),month=key(body?.month),id=key(body?.complaintId),action=key(body?.action);
  if(!/^\d{1,12}$/.test(courierId)||!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)||! /^[0-9a-f-]{36}$/i.test(id)||!['start','respond','close','reopen','note','assign'].includes(action))return jsonResponse({error:'Hiányzó vagy hibás reklamációs azonosítók.'},400);
  if(action==='assign')return courier360AssignComplaint(body,env,user,executionContext);
  const rows=await supabaseFetch(env,PUBLIC_SCHEMA,'peopleforce_complaints',{id:`eq.${id}`,courier_id:`eq.${courierId}`,document_month:`eq.${month}-01`,select:'id,status,admin_response,responded_at',limit:1});
  const row=rows[0];if(!row||row.status==='deleted')return jsonResponse({error:'A reklamáció nem található.'},404);
  const noteRows=await supabaseFetch(env,PUBLIC_SCHEMA,'peopleforce_complaint_notes',{courier_id:`eq.${courierId}`,period_start:`eq.${month}-01`,select:'note,updated_at',limit:1});
  let oldNote=noteRows[0];const now=new Date().toISOString();
  const supabaseUrl=cleanEnv(env.SUPABASE_URL),supabaseKey=cleanEnv(env.SUPABASE_READ_KEY||env.SUPABASE_SERVICE_ROLE_KEY);
  const headers={apikey:supabaseKey,authorization:`Bearer ${supabaseKey}`,'content-profile':PUBLIC_SCHEMA,'accept-profile':PUBLIC_SCHEMA,'content-type':'application/json',prefer:'return=representation'};
  const filter=value=>value==null?'is.null':`eq.${value}`;
  async function writeNote(text){
    const url=new URL(`${supabaseUrl}/rest/v1/peopleforce_complaint_notes`);let method='POST';
    if(oldNote){method='PATCH';url.searchParams.set('courier_id',`eq.${courierId}`);url.searchParams.set('period_start',`eq.${month}-01`);url.searchParams.set('updated_at',filter(oldNote.updated_at));}
    else url.searchParams.set('on_conflict','period_start,courier_id');
    const response=await fetch(url,{method,headers:{...headers,...(!oldNote?{prefer:'resolution=ignore-duplicates,return=representation'}:{})},body:JSON.stringify({courier_id:courierId,period_start:month+'-01',note:text,updated_by:user.username,updated_at:now})});
    const saved=await response.json().catch(()=>null);const ok=response.ok&&Array.isArray(saved)&&saved.length===1;if(ok)oldNote={note:text,updated_at:now};return ok;
  }
  if(action==='note'){
    const note=String(body.note??'').trim();if(note.length>20000)return jsonResponse({error:'A belső megjegyzés túl hosszú.'},422);
    if(String(body.expectedNote??'')!==String(oldNote?.note??''))return jsonResponse({error:'A havi belső megjegyzést időközben módosították. Frissítsd az ablakot.'},409);
    return await writeNote(note)?jsonResponse({ok:true}):jsonResponse({error:'A megjegyzés nem menthető, vagy időközben megváltozott. Frissítsd az ablakot.'},409);
  }
  if(!body.expected||row.status!==body.expected.status||(row.admin_response??null)!==(body.expected.adminResponse??null)||(row.responded_at??null)!==(body.expected.respondedAt??null))return jsonResponse({error:'A reklamáció időközben megváltozott. Frissítsd az ablakot.'},409);
  const closed=['closed','resolved'].includes(row.status);
  if(closed&&action!=='reopen'||!closed&&action==='reopen')return jsonResponse({error:'Az ügy állapota nem engedi ezt a műveletet.'},409);
  const responseText=key(body.response);
  if(['respond','close','reopen'].includes(action)&&(!responseText||responseText.length>5000))return jsonResponse({error:'Adj meg legfeljebb 5000 karakteres választ vagy indoklást.'},422);
  if(action==='close'){
    if(!['accepted','partial','rejected'].includes(body.decision)||body.financeReviewed!==true)return jsonResponse({error:'Add meg az eredményt, és ellenőrizd a pénzügyi hatást.'},422);
    const snapshots=await loadLatestFinanceSnapshots(env,month+'-01',courierId);
    if((snapshots[0]?.id||'')!==(body.snapshotId||''))return jsonResponse({error:'A pénzügyi mentés megváltozott. Ellenőrizd újra a pénzügyi hatást.'},409);
  }
  const update={status:({start:'in_progress',respond:'open',close:'closed',reopen:'open'})[action]};
  if(action==='reopen'){update.admin_response=null;update.responded_at=null;update.responded_by=null;}
  if(action==='respond'||action==='close'){update.admin_response=(action==='close'?`Eredmény: ${{accepted:'Elfogadva',partial:'Részben elfogadva',rejected:'Elutasítva'}[body.decision]}.\n`:'')+responseText;update.responded_at=now;update.responded_by=user.username;}
  const preparation=`${now} | Ügy ${id} | ${user.username} | Művelet előkészítve: ${action}${responseText?' | '+responseText:''}${row.admin_response?'\nKorábbi válasz megőrizve: '+row.admin_response:''}`;
  if(!await writeNote([oldNote?.note,preparation].filter(Boolean).join('\n\n')))return jsonResponse({error:'Az ügyintézési bejegyzés nem őrizhető meg. Frissítsd az ablakot; az ügy állapota nem változott.'},409);
  const url=new URL(`${supabaseUrl}/rest/v1/peopleforce_complaints`);
  for(const [name,value] of Object.entries({id:`eq.${id}`,courier_id:`eq.${courierId}`,document_month:`eq.${month}-01`,status:filter(row.status),admin_response:filter(row.admin_response),responded_at:filter(row.responded_at)}))url.searchParams.set(name,value);
  const result=await fetch(url,{method:'PATCH',headers,body:JSON.stringify(update)}),saved=await result.json().catch(()=>null);
  if(!result.ok||!Array.isArray(saved)||saved.length!==1)return jsonResponse({error:'A módosítás nem igazolható. Frissítsd az ablakot.'},409);
  const event=`${now} | Ügy ${id} | ${user.username} | Művelet megtörtént: ${row.status} → ${update.status}`;
  let audit=false;try{audit=await writeNote([oldNote?.note,event].filter(Boolean).join('\n\n'));}catch{}
  return jsonResponse({ok:true,...(!audit?{warning:'Az ügy mentve, de a havi belső napló bejegyzése nem sikerült.'}:{})});
}

// Read the saved TIG, never recalculate money from an incomplete courier list.
function paymentNumber(value) {
  if(value===null||value===undefined||String(value).trim()==='')return null;
  const n=Number(value);return Number.isFinite(n)?Math.round(n):null;
}
function paymentDocumentProcess(document) {
  return key(document?.document_type).match(/^process:([a-z0-9_-]+):/i)?.[1]||key(document?.note).match(/Folyamat azonosító:\s*([a-z0-9_-]+)/i)?.[1]||'';
}
function paymentDocumentMode(document,periodStart='') {
  const type=key(document.document_type),note=key(document.note);
  const process=paymentDocumentProcess(document);
  if(process)return process===`kp_invoice_${periodStart.slice(0,7).replace('-','')}`&&(type==='invoice'||type===`process:${process}:invoice`)?'cash':null;
  if(!['invoice','cash_invoice','kp_invoice'].includes(type))return null;
  return ['cash_invoice','kp_invoice'].includes(type)||/^\s*kp\s/i.test(key(document.title))||
    /kp[_ -]sz[aá]mla/i.test(key(document.file_name))||/fizet[eé]si m[oó]d\s*:\s*(kp\b|k[eé]szp[eé]nz)/i.test(note)?'cash':'transfer';
}
function paymentDocumentAmount(document) {
  // Upload metadata is not a new PDF validation. Keep that distinction in the UI.
  const match=key(document?.note).match(/(?:brutt[óo]\s+[öo]sszesen|[öo]sszeg)\s*:\s*([0-9\s\u00a0.,]+)\s*Ft/i);
  if(!match)return null;
  const value=match[1].replace(/[\s\u00a0]/g,'').replace(/\.(?=\d{3}(?:[.,]|$))/g,'').replace(',','.');
  return paymentNumber(value);
}
function paymentInvoiceNumber(document) {
  const title=key(document?.title).replace(/^(?:kp\s+)?sz[aá]mla\s*/i,'');
  return title||'';
}
function courier360Payment({courierId,periodStart,profile={},snapshot,paymentSources=[],documents=[],workflowStates={},processStates=[],closure,acceptances=[],complaints=[],sources=[]}) {
  const source=name=>courier360Json(paymentSources.find(row=>row.source_key===name)?.payload);
  const tig=source('tig_breakdown'),savedProfile=source('courier_profile');
  const latest={};
  const monthlyDocuments=documents.filter(d=>!paymentDocumentProcess(d)||paymentDocumentMode(d,periodStart)==='cash');
  for(const document of [...monthlyDocuments].sort((a,b)=>key(b.uploaded_at).localeCompare(key(a.uploaded_at))||key(b.id).localeCompare(key(a.id)))){
    const mode=paymentDocumentMode(document,periodStart);if(mode&&!latest[mode])latest[mode]=document;
  }
  const check=workflowStates.invoice_check||{},closed=closure?.status==='done'||workflowStates.invoice_payment?.status==='done';
  const compare=mode=>{
    const expected=paymentNumber(tig[mode==='cash'?'cashGrossHuf':'finalTotalHuf']),document=latest[mode]||null,actual=paymentDocumentAmount(document);
    const difference=expected!==null&&actual!==null?actual-expected:null;
    const result=!document?(mode==='cash'&&expected===0?'not_required':'missing'):difference===null?'unknown':Math.abs(difference)<=1?'match':'mismatch';
    // A newer upload must not inherit an older invoice's successful check.
    const process=paymentDocumentProcess(document),documentCheck=process?processStates.find(row=>row.action_key===`process:${process}:invoice_check`)||{}:check;
    const checkedAt=Date.parse(documentCheck.updated_at),uploadedAt=Date.parse(document?.uploaded_at);
    const checked=Boolean(document&&Number.isFinite(checkedAt)&&Number.isFinite(uploadedAt)&&checkedAt>=uploadedAt);
    return {expectedHuf:expected,actualHuf:actual,differenceHuf:difference,result,document,
      amountSource:actual===null?null:'upload_note',check:checked?documentCheck:null};
  };
  const transfer=compare('transfer'),cash=compare('cash');
  const payableItem=(snapshot?.items||[]).find(item=>item.section==='finance'&&item.item_key==='payable');
  const amount=closure?.status==='done'?paymentNumber(closure.payable_huf):paymentNumber(payableItem?.amount_value);
  const invoiceNumber=key(closure?.invoice_number)||paymentInvoiceNumber(latest.transfer);
  const bankAccount=key(closure?.status==='done'?closure.bank_account_number:profile?.bank_account_number);
  const recipientName=key(closure?.status==='done'?closure.recipient_name:profile?.company_name)||key(profile?.courier_name||savedProfile.courier_name);
  const blocking=[];
  const failed=sources.filter(row=>row.available===false&&['courier_master','courier_finance_snapshot','courier_finance_snapshot_source','peopleforce_documents','peopleforce_card_statuses','courier_monthly_closure'].includes(row.table));
  if(failed.length)blocking.push('Egyes kifizetési források nem érhetők el.');
  if(!snapshot||amount===null)blocking.push('Hiányzik a mentett havi kifizetendő összeg.');
  if(!bankAccount)blocking.push('Hiányzik a kedvezményezett bankszámlaszáma.');
  if(!recipientName)blocking.push('Hiányzik a kedvezményezett neve.');
  if(check.status!=='done'&&workflowStates.manual_invoice_skip?.status!=='done')blocking.push('A számla még nincs jóváhagyva.');
  if(check.status==='open')blocking.push('A számlaellenőrzés nyitott.');
  if([transfer,cash].some(item=>item.document&&(!item.check||item.check.status!=='done'))&&workflowStates.manual_invoice_skip?.status!=='done')blocking.push('Az aktuális számlák jóváhagyása még nincs rögzítve.');
  if(!invoiceNumber)blocking.push('Hiányzik az átutalásos számla sorszáma.');
  if(cash.result==='missing'&&cash.expectedHuf>0&&workflowStates.manual_invoice_skip?.status!=='done')blocking.push('Hiányzik a szükséges KP-s számla.');
  if(transfer.result==='mismatch'||cash.result==='mismatch')blocking.push('A rögzített számlaösszeg eltér a teljesítésigazolástól.');
  const events=[];
  const add=(at,label,detail,actor,kind='event')=>{if(at)events.push({at,label,detail:detail||'',actor:actor||'',kind})};
  const labels={settlement:'Elszámolás',tig:'Teljesítésigazolás',invoice_submit:'Számlafeltöltés',invoice_check:'Számlaellenőrzés',invoice_payment:'Kifizetés'};
  for(const row of acceptances.filter(row=>!key(row.process_id)))add(row.accepted_at,`${labels[row.action_key]||row.action_key} elfogadva`,'Elfogadási mentés',row.accepted_by);
  for(const document of monthlyDocuments)add(document.uploaded_at,`${paymentDocumentMode(document,periodStart)==='cash'?'KP-s számla':paymentDocumentMode(document,periodStart)==='transfer'?'Átutalásos számla':'Dokumentum'} feltöltve`,key(document.title||document.file_name),document.uploaded_by);
  for(const row of complaints.filter(row=>!key(row.document_type).startsWith('process:')&&key(row.status)!=='deleted')){
    add(row.created_at,'Reklamáció érkezett',row.message,'','complaint');
    add(row.responded_at,'Reklamáció megválaszolva',row.admin_response,row.responded_by,'complaint');
  }
  for(const [action,row] of Object.entries(workflowStates))if(labels[action])add(row.updated_at,`${labels[action]} · ${row.status==='done'?'Kész':row.status==='open'?'Nyitott':row.status}`,row.status_note,row.updated_by,'current_state');
  for(const row of processStates)if(row.action_key===`process:kp_invoice_${periodStart.slice(0,7).replace('-','')}:invoice_check`)add(row.updated_at,`KP-s számla ellenőrzése · ${row.status==='done'?'Kész':'Nyitott'}`,row.status_note,row.updated_by,'current_state');
  add(closure?.closed_at,'Kifizetés rögzítve',key(courier360Json(closure?.snapshot).close_note),closure?.closed_by);
  add(closure?.reopened_at,'Havi kifizetés visszanyitva','',closure?.reopened_by);
  events.sort((a,b)=>key(b.at).localeCompare(key(a.at)));
  return {snapshotId:snapshot?.id||'',snapshotVersion:snapshot?.version??null,amountHuf:amount,
    recipientName,bankAccount,invoiceNumber,paymentNote:key(closure?.status==='done'?closure.payment_note:'')||[courierId,invoiceNumber].filter(Boolean).join('-'),
    closed,closedAt:closure?.status==='done'?closure.closed_at:workflowStates.invoice_payment?.status==='done'?workflowStates.invoice_payment.updated_at:null,
    closedBy:closure?.status==='done'?closure.closed_by:workflowStates.invoice_payment?.status==='done'?workflowStates.invoice_payment.updated_by:null,
    transfer,cash,tigBreakdown:tig,tigDocuments:monthlyDocuments.filter(d=>['tig','performance_certificate'].includes(key(d.document_type))),
    canClose:!closed&&blocking.length===0,blockingReasons:blocking,events,periodStart};
}

async function courier360ClosePayment(request,env,user) {
  if(request.headers.get('origin')!==new URL(request.url).origin)return jsonResponse({error:'Érvénytelen kérésforrás.'},403);
  if(!request.headers.get('content-type')?.includes('application/json'))return jsonResponse({error:'JSON kérés szükséges.'},415);
  const body=await request.json().catch(()=>null);
  if(!/^\d{1,12}$/.test(key(body?.courierId))||!/^\d{4}-(0[1-9]|1[0-2])$/.test(key(body?.month))||! /^[0-9a-f-]{36}$/i.test(key(body?.snapshotId)))return jsonResponse({error:'Hiányzó vagy hibás kifizetési azonosítók.'},400);
  const url=new URL('/api/courier360',request.url);url.searchParams.set('courier',body.courierId);url.searchParams.set('month',body.month);url.searchParams.set('date',budapestDay(new Date()));
  const response=await courier360Data(new Request(url),env),data=await response.json();
  if(!response.ok)return jsonResponse(data,response.status);
  const payment=data.payment;
  if(payment.closed)return jsonResponse({ok:true,alreadyClosed:true});
  if(payment.snapshotId!==body.snapshotId)return jsonResponse({error:'A mentett elszámolás megváltozott. Nyisd meg újra a kifizetést.'},409);
  if(!payment.canClose)return jsonResponse({error:payment.blockingReasons.join(' ')},409);
  const note=key(body.note);
  if(note.length>2000||!note||!note.replace(/\D/g,'').includes(String(Math.abs(payment.amountHuf))))return jsonResponse({error:'A megjegyzés kötelező, és tartalmaznia kell a kifizetendő összeget.'},422);
  const supabaseUrl=cleanEnv(env.SUPABASE_URL),supabaseKey=cleanEnv(env.SUPABASE_READ_KEY||env.SUPABASE_SERVICE_ROLE_KEY);
  // Reuse the existing transactional closure: no independent Hub financial writes.
  const result=await fetch(`${supabaseUrl}/rest/v1/rpc/pwa_close_monthly_payment`,{method:'POST',headers:{
    apikey:supabaseKey,authorization:`Bearer ${supabaseKey}`,'content-profile':SETTLEMENT_SCHEMA,'accept-profile':SETTLEMENT_SCHEMA,'content-type':'application/json',
  },body:JSON.stringify({p_courier_id:body.courierId,p_period_start:body.month+'-01',p_snapshot_id:body.snapshotId,p_invoice_number:payment.invoiceNumber,p_note:note,p_actor:user.username})});
  const payload=await result.json().catch(()=>null);
  if(!result.ok||!payload?.ok)return jsonResponse({error:result.status===409?'Az elszámolás időközben megváltozott. Frissítsd az ablakot.':'A kifizetés lezárása nem sikerült. A meglévő adminisztrátori kifizetési felületen ellenőrizd a feltételeket.'},409);
  return jsonResponse({ok:true,alreadyClosed:Boolean(payload.alreadyClosed)});
}

function normalizePaymentBankAccount(value) {
  const text=String(value??'').trim(),digits=text.replace(/[\s-]/g,'');
  if(!/^[0-9\s-]{8,40}$/.test(text)||![16,24,32].includes(digits.length))return null;
  return digits.match(/.{8}/g).join('-');
}
async function courier360SaveBankAccount(request,env,user) {
  if(request.headers.get('origin')!==new URL(request.url).origin)return jsonResponse({error:'Érvénytelen kérésforrás.'},403);
  if(!request.headers.get('content-type')?.includes('application/json'))return jsonResponse({error:'JSON kérés szükséges.'},415);
  const body=await request.json().catch(()=>null),courierId=key(body?.courierId),account=normalizePaymentBankAccount(body?.bankAccount);
  if(!/^\d{1,12}$/.test(courierId))return jsonResponse({error:'Érvénytelen futárazonosító.'},400);
  if(!account)return jsonResponse({error:'Adj meg 16, 24 vagy 32 számjegyet; szóköz és kötőjel használható.'},422);
  const rows=await supabaseFetch(env,PUBLIC_SCHEMA,'courier_master',{select:'courier_id,bank_account_number',courier_id:`eq.${courierId}`,limit:1});
  const profile=rows[0];if(!profile)return jsonResponse({error:'A futár törzsadata nem található.'},404);
  if(key(profile.bank_account_number))return normalizePaymentBankAccount(profile.bank_account_number)===account?jsonResponse({ok:true,alreadySaved:true}):jsonResponse({error:'A futárnak már van bankszámlaszáma. Frissítsd az ablakot; a meglévő adat itt nem írható felül.'},409);
  const supabaseUrl=cleanEnv(env.SUPABASE_URL),supabaseKey=cleanEnv(env.SUPABASE_READ_KEY||env.SUPABASE_SERVICE_ROLE_KEY),now=new Date().toISOString();
  const url=new URL(`${supabaseUrl}/rest/v1/courier_master`);
  url.searchParams.set('courier_id',`eq.${courierId}`);url.searchParams.set('bank_account_number',profile.bank_account_number==null?'is.null':`eq.${profile.bank_account_number}`);url.searchParams.set('select','courier_id');
  const headers={apikey:supabaseKey,authorization:`Bearer ${supabaseKey}`,'content-profile':PUBLIC_SCHEMA,'accept-profile':PUBLIC_SCHEMA,'content-type':'application/json',prefer:'return=representation'};
  // Compare-and-set fills only the missing value, including during concurrent edits.
  const response=await fetch(url,{method:'PATCH',headers,body:JSON.stringify({bank_account_number:account,billing_data_source:'jitt_hub_admin',billing_data_updated_at:now,updated_at:now})});
  if(!response.ok)return jsonResponse({error:'A bankszámlaszám nem menthető. Próbáld újra.'},502);
  const saved=await response.json().catch(()=>null);
  if(!Array.isArray(saved)||saved.length!==1)return jsonResponse({error:'A törzsadat időközben megváltozott. Frissítsd az ablakot.'},409);
  let auditSaved=false;
  try{const audit=await fetch(`${supabaseUrl}/rest/v1/courier_profile_change_log`,{method:'POST',headers:{...headers,'content-profile':SETTLEMENT_SCHEMA,'accept-profile':SETTLEMENT_SCHEMA,prefer:'return=minimal'},body:JSON.stringify({courier_id:courierId,changed_fields:{bank_account_number:{old:profile.bank_account_number||'',new:account}},changed_by:user.username,created_at:now})});auditSaved=audit.ok;}catch{}
  return jsonResponse({ok:true,...(!auditSaved?{warning:'A bankszámlaszám mentve, de a külön változásnapló bejegyzése nem sikerült.'}:{})});
}

let courier360LiveCache;
async function courier360SharedHeaders(env) {
  const token = cleanEnv(env.SUPABASE_SERVICE_ROLE_KEY || env.SUPABASE_READ_KEY);
  const base = cleanEnv(env.SUPABASE_URL);
  if (!token || !base) return [];
  try {
    const response = await fetch(base+'/storage/v1/object/authenticated/hub-session-cache/session.json',{
      headers:{apikey:token,authorization:`Bearer ${token}`},redirect:'error',signal:AbortSignal.timeout(4000),
    });
    if (!response.ok) return [];
    const payload = await response.json();
    return [payload.headers,payload.backupHeaders].flatMap(source=>{
      const cookie = key(source?.Cookie), authorization = key(source?.Authorization);
      return cookie || authorization ? [{...(cookie ? {cookie} : {}),...(authorization ? {authorization} : {})}] : [];
    });
  } catch { return []; }
}

function courier360DirectMonitor(env) {
  const cookie = key(env.COURIER_HUB_COOKIE);
  const authorization = key(env.COURIER_HUB_AUTHORIZATION);
  if (courier360LiveCache?.until > Date.now()) return courier360LiveCache.promise;
  const promise = courier360SharedHeaders(env).then(candidates=>{
    if (cookie || authorization) candidates.push({...(cookie ? {cookie} : {}),...(authorization ? {authorization} : {})});
    return Promise.all([1,2].map(async id => {
      const url = `https://courier-hub.kifli.hu/services/courier-hub-service/external/warehouses/${id}/live-monitoring-dashboard?dspId=8`;
      for (const headers of candidates) {
        try {
          const response = await fetch(url,{headers:{accept:'application/json',...headers},redirect:'error',signal:AbortSignal.timeout(5500)});
          if (response.status === 401 || response.status === 403) continue;
          if (!response.ok) return null;
          const payload = await response.json();
          const rows = Array.isArray(payload) ? payload : payload.couriers;
          if (!Array.isArray(rows)) return null;
          const fetched_at = new Date().toISOString();
          return {warehouse:`BUD${id}`,fetched_at,rows:rows.map(row=>({
            courier_id:row.courierId,courier_name:row.name || row.courierName,route_id:row.cargoRouteId || row.routeExternalId,
            status:row.status,shift_status:row.shiftStatus,delay_minutes:row.delayMinutes,
            warehouse_code:`BUD${id}`,courier_json:row,fetched_at,direct:true,
          }))};
        } catch { return null; }
      }
      return null;
    }));
  }).then(results=>results.filter(Boolean));
  courier360LiveCache = {until:Date.now()+15000,promise};
  return promise;
}

function courier360MonitorStatus(state, shiftState, routeActive, working) {
  if (state === 'NO_SHOW' || shiftState === 'NO_SHOW') return 'Nem jelent meg';
  if (['SLIPPING','LATE'].includes(state)) return 'Csúszik';
  if (state === 'IDLE') return 'Tétlen';
  if (routeActive) return 'Túrán';
  if (state === 'LOADING') return 'Rakodik';
  if (working) return 'Műszakban';
  return '';
}

async function courier360ActiveCouriers(env, now = new Date(), includeAll = false) {
  const date = budapestDay(now);
  const recent = includeAll ? budapestMidnightUtc(date) : new Date(+now - 20 * 60000).toISOString();
  const common = 'courier_id,courier_name,status,warehouse_code,courier_json,fetched_at';
  const liveParams = {dsp_id:'eq.8', warehouse_id:'in.(1,2)', fetched_at: `gte.${recent}`, order: 'fetched_at.desc,courier_id.asc,warehouse_id.asc,dsp_id.asc', limit: 2000};
  const results = await Promise.allSettled([
    supabaseFetch(env, PUBLIC_SCHEMA, 'courier_hub_live_monitoring_courier_snapshot_latest', {
      ...liveParams, select: `${common},route_id,departed_at,shift_status,delay_minutes`,
    }),
    supabaseFetch(env, PUBLIC_SCHEMA, 'courier_hub_live_map_courier_latest', {
      ...liveParams, select: `${common},route_ids,shift_status`,
    }),
    supabaseFetch(env, PUBLIC_SCHEMA, 'giriton_attendance_raw', {
      select: 'courier_name,activity_status,checkin_start,checkin_end,updated_at',
      work_date: `eq.${date}`, updated_at: `gte.${recent}`, order: 'updated_at.desc,id.asc', limit: 2000,
    }),
    supabaseFetch(env, PUBLIC_SCHEMA, 'courier_hub_route_statistics', {
      select: 'courier_id,work_date,route_id,returned_at',
      work_date: `eq.${date}`, returned_at: 'not.is.null', order: 'courier_id.asc,route_id.asc', limit: 2000,
    }),
    courier360DirectMonitor(env),
  ]);
  const [monitor, map, attendance, statistics, direct] = results.map(result => result.value || []);
  if (!direct.length && results.slice(0, 3).every(result => result.status === 'rejected')) {
    return jsonResponse({error: 'Az élő futárstátuszok most nem érhetők el.'}, 502);
  }
  const directWarehouses = new Set(direct.map(source=>source.warehouse));
  const snapshotRows = [...monitor,...map].filter(row=>!directWarehouses.has(row.warehouse_code));
  const group = new Map();
  function record(id) {
    if (!group.has(id)) group.set(id, {signals: [], statistics: [], attendance: []});
    return group.get(id);
  }
  for (const [source, rows] of [['signals', [...snapshotRows,...direct.flatMap(source=>source.rows)]], ['statistics', statistics]]) {
    for (const row of rows) {
      const id = key(row.courier_id);
      if (/^\d{1,12}$/.test(id)) record(id)[source].push(row);
    }
  }
  let attendanceUnavailable = false;
  if (attendance.length) {
    try {
      const directory = await supabaseFetch(env, PUBLIC_SCHEMA, 'courier_master', {
        select: 'courier_id,courier_name', order: 'courier_id.asc', limit: 10000,
      });
      const idsByName = new Map();
      for (const row of directory) {
        const name = courier360Name(row.courier_name), id = key(row.courier_id);
        if (!name || !/^\d{1,12}$/.test(id)) continue;
        if (!idsByName.has(name)) idsByName.set(name, new Set());
        idsByName.get(name).add(id);
      }
      for (const row of attendance) {
        const ids = idsByName.get(courier360Name(row.courier_name));
        if (ids?.size === 1) record(ids.values().next().value).attendance.push(row);
      }
    } catch { attendanceUnavailable = true; }
  }
  const couriers = [];
  for (const [id, sources] of group) {
    const signal = sources.signals
      .filter(row => (includeAll || courier360Fresh(row.fetched_at, now)) && budapestDay(new Date(row.fetched_at)) === date)
      .sort((a, b) => Date.parse(b.fetched_at) - Date.parse(a.fetched_at))[0];
    const info = courier360Json(signal?.courier_json);
    const shiftState = key(signal?.shift_status || info.shiftStatus).toUpperCase();
    const state = shiftState === 'NO_SHOW' ? 'NO_SHOW' : key(signal?.status || info.status).toUpperCase();
    const routeId = key(signal?.route_id || info.cargoRouteId || info.routeExternalId ||
      (Array.isArray(signal?.route_ids) ? signal.route_ids[0] : null));
    const returned = sources.statistics.find(row => key(row.route_id) === routeId)?.returned_at;
    const routeActive = courier360RouteActive({date, routeId, activityAt: info.plannedStartAt, returned, state});
    const sameAttendanceName = new Set(sources.attendance.map(row => key(row.courier_name))).size === 1;
    const attended = sameAttendanceName ? sources.attendance[0] : null;
    const fresh = courier360Fresh(signal?.fetched_at,now);
    const attendanceFresh = courier360Fresh(attended?.updated_at,now);
    const {working} = courier360Working({state,routeActive,fresh:Boolean(signal),attended,attendanceFresh});
    const status = courier360MonitorStatus(state,shiftState,routeActive,working);
    if ((!includeAll && working !== true) || (!status && !signal)) continue;
    const name = sources.signals[0]?.courier_name || sources.attendance[0]?.courier_name;
    const optionalNumber = value => value == null || value === '' ? null : metricNumber(value);
    couriers.push({courierId:id,courierName:signal?.courier_name || name || 'Futár',status:status || 'Nincs aktív jelzés',
      working:working === true,routeActive,routeId:routeId || null,
      stale:!(signal ? fresh : attendanceFresh),
      delayMinutes:optionalNumber(signal?.delay_minutes ?? info.delayMinutes),
      completedStops:optionalNumber(info.deliveriesCompleted),totalStops:optionalNumber(info.stopsTotal),
      at:signal?.fetched_at || attended?.updated_at || null,
      source:signal?.direct ? 'Kifli Hub · közvetlen' : signal ? 'Kifli Hub · mentett pillanatkép' : 'Giriton'});
  }
  couriers.sort((a, b) => Number(b.status === 'Túrán') - Number(a.status === 'Túrán') ||
    a.courierName.localeCompare(b.courierName, 'hu') || a.courierId.localeCompare(b.courierId));
  return jsonResponse({couriers, partial: attendanceUnavailable || results.some(result => result.status === 'rejected'),
    directWarehouses:[...directWarehouses]});
}

async function courier360Profile(request, env) {
  const courierId = key(new URL(request.url).searchParams.get('courier'));
  if (!/^\d{1,12}$/.test(courierId)) return jsonResponse({error: 'Érvényes futárazonosító szükséges.'}, 400);
  const [profile] = await supabaseFetch(env, PUBLIC_SCHEMA, 'courier_master', {
    select: 'courier_id,courier_name,phone_number,warehouse_name,company_name,company_address,tax_number,bank_account_number,billing_email,billing_data_updated_at',
    courier_id: `eq.${courierId}`, limit: 1,
  });
  if (!profile) return jsonResponse({error: 'Ehhez a futárhoz nincs rögzített adatlap.'}, 404);
  return jsonResponse({profile});
}

async function courier360Document(request,env) {
  const url=new URL(request.url),id=key(url.searchParams.get('id')),courier=key(url.searchParams.get('courier'));
  if(!/^[0-9a-f-]{36}$/i.test(id)||!/^\d{1,12}$/.test(courier))return jsonResponse({error:'Érvénytelen dokumentumazonosító.'},400);
  const rows=await supabaseFetch(env,PUBLIC_SCHEMA,'peopleforce_documents',{select:'file_name,mime_type,file_size,file_content_base64',id:`eq.${id}`,courier_id:`eq.${courier}`,limit:1});
  const row=rows[0];if(!row?.file_content_base64)return jsonResponse({error:'A dokumentum tartalma nem elérhető.'},404);
  if(Number(row.file_size)>20000000||row.file_content_base64.length>28000000)return jsonResponse({error:'A dokumentum túl nagy a megnyitáshoz.'},413);
  const bytes=Uint8Array.from(atob(row.file_content_base64),c=>c.charCodeAt(0));
  const mime=['application/pdf','image/png','image/jpeg','text/plain'].includes(row.mime_type)?row.mime_type:'application/octet-stream';
  const disposition=mime==='application/octet-stream'?'attachment':'inline';
  return new Response(bytes,{headers:{'content-type':mime,'cache-control':'no-store','x-content-type-options':'nosniff',
    'content-disposition':`${disposition}; filename*=UTF-8''${encodeURIComponent(key(row.file_name)||'dokumentum')}`}});
}

async function dailyAbsences(env, date) {
  const work_date = `eq.${date}`;
  const [attendance, hub] = await Promise.allSettled([
    supabaseFetch(env, PUBLIC_SCHEMA, 'pwa_today_worker_attendance', {
      select: 'courier_id,courier_name,warehouse,shift_name,start_time,attendance_status',
      work_date, order: 'start_time.asc,id.asc', limit: 10000,
    }),
    supabaseFetch(env, PUBLIC_SCHEMA, 'raw_jitt_invoice_perf_couriers_daily', {
      select: 'courier_id,courier_name,warehouse_code,did_not_come_count',
      work_date, dsp_code: 'eq.JIT', order: 'warehouse_id.asc,courier_id.asc,source_name.asc,dsp_id.asc', limit: 10000,
    }),
  ]);
  if (attendance.status === 'rejected' && hub.status === 'rejected') throw new Error('Attendance sources unavailable');
  const manualRows = attendance.value || [];
  const hubRows = hub.value || [];
  const affected = new Map();
  function getCourier(row) {
    const id = key(row.courier_id);
    if (!affected.has(id)) affected.set(id, {courier_id: id, courier_name: row.courier_name, attendance: [], hub: Object.create(null)});
    const courier = affected.get(id);
    courier.courier_name ||= row.courier_name;
    return courier;
  }
  for (const row of manualRows.filter(row => row.attendance_status === 'absent')) {
    getCourier(row).attendance.push({warehouse: row.warehouse, shift: row.shift_name, start: row.start_time});
  }
  for (const row of hubRows.filter(row => row.did_not_come_count > 0)) {
    const courier = getCourier(row);
    const warehouse = key(row.warehouse_code) || '—';
    courier.hub[warehouse] = Math.max(courier.hub[warehouse] || 0, Number(row.did_not_come_count));
  }
  return {
    rows: [...affected.values()],
    ...(attendance.status === 'rejected' || hub.status === 'rejected'
      ? {note: 'Az egyik jelenléti forrás nem érhető el.'}
      : {}),
    ...(manualRows.length === 0 && hubRows.length === 0 ? {empty: 'A mai napra még nincs jelenléti adat.'} : {}),
  };
}

async function dailySalaryAdvances(env) {
  const [plans, installments, requests] = await Promise.all([
    supabaseFetch(env, SETTLEMENT_SCHEMA, 'courier_salary_advance_plan', {
      select: 'id,courier_id,courier_name,requested_amount_huf,start_date',
      status: 'eq.open', order: 'start_date.asc,id.asc', limit: 10000,
    }),
    supabaseFetch(env, SETTLEMENT_SCHEMA, 'courier_salary_advance_installment', {
      select: 'plan_id,period_start,amount_huf',
      status: 'eq.open', order: 'period_start.asc,id.asc', limit: 10000,
    }),
    supabaseFetch(env, SETTLEMENT_SCHEMA, 'courier_salary_advance_request', {
      select: 'id,courier_id,courier_name,requested_amount_huf,start_date,status',
      status: 'in.(approved,paid)', plan_id: 'is.null', order: 'start_date.asc,id.asc', limit: 10000,
    }),
  ]);
  const balances = new Map();
  for (const row of installments) {
    if (!balances.has(row.plan_id)) balances.set(row.plan_id, {remaining: 0, nextPeriod: row.period_start});
    balances.get(row.plan_id).remaining += money(row.amount_huf);
  }
  return [
    ...plans.map(row => ({...row, status: 'plan', ...balances.get(row.id)})),
    ...requests,
  ];
}

async function dailyTasks(env, user, now = new Date()) {
  const date = budapestDay(now);
  const canManageQuality = ['admin', 'superadmin'].includes(user.role.toLowerCase());
  const sourceEnv = {...env, SUPABASE_READ_KEY: env.SUPABASE_SERVICE_ROLE_KEY || env.SUPABASE_READ_KEY};
  const [quality, settlement, shifts, absences, payments, advances] = await Promise.allSettled([
    canManageQuality ? supabaseFetch(sourceEnv, PUBLIC_SCHEMA, 'pwa_quality_complaints', {
      select: 'id,courier_id,courier_name,topic,status,created_at,affected_items',
      status: 'in.(new,open,in_review)', forwarded_at: 'is.null',
      order: 'created_at.asc,id.asc', limit: 10000,
    }) : null,
    supabaseFetch(env, PUBLIC_SCHEMA, 'peopleforce_complaints', {
      select: 'id,courier_id,courier_name,document_month,document_type,status,created_at',
      status: 'in.(new,open,in_progress)', order: 'created_at.asc,id.asc', limit: 10000,
    }),
    supabaseFetch(sourceEnv, PUBLIC_SCHEMA, 'vw_muszakpro_hub_shift_time_mismatch', {
      select: 'courier_id,courier_name,warehouse_code,muszakpro_shift_start_time,hub_booking_shift_start_time,comparison_reason,comparison_status',
      work_date: `eq.${date}`, comparison_status: 'neq.PONTOS',
      order: 'muszakpro_shift_start_time.asc,warehouse_code.asc,courier_id.asc,muszakpro_source_row.asc,muszakpro_serial.asc',
      limit: 10000,
    }),
    dailyAbsences(sourceEnv, date),
    supabaseFetch(sourceEnv, SETTLEMENT_SCHEMA, 'vw_admin_settlement_dashboard_fast', {
      select: 'courier_id,courier_name,period_start,warehouse,payable_huf',
      dashboard_status_label: 'eq.Kifizetésre vár', payable_huf: 'gt.0',
      order: 'period_start.asc,courier_id.asc', limit: 10000,
    }),
    dailySalaryAdvances(sourceEnv),
  ]);
  const section = result => result.status === 'fulfilled' ? {rows: result.value} : {error: 'Az adatok nem tölthetők be.'};
  return jsonResponse({
    date, generatedAt: now.toISOString(),
    quality: canManageQuality ? section(quality) : {error: 'Reklamációkezelő jogosultság szükséges.'},
    settlement: section(settlement),
    shifts: section(shifts),
    absences: absences.status === 'fulfilled' ? absences.value : section(absences),
    payments: section(payments),
    advances: section(advances),
  });
}

function scheduleTime(value) {
  const match = key(value).match(/(?:^|\D)([01]?\d|2[0-3]):([0-5]\d)(?!\d)/);
  return match ? match[1].padStart(2,'0') + ':' + match[2] : '';
}

function scheduleEmail(value) {
  return key(value).toLowerCase().replace(/\s+/g,'');
}

function scheduleTimestamp(value) {
  if (value == null || value === '') return null;
  const text = key(value);
  if (/^\d{10}(?:\d{3})?$/.test(text)) return new Date(Number(text) * (text.length === 10 ? 1000 : 1)).toISOString();
  // MűszakPro stores some local wall times as text. Preserve those separately from ISO instants.
  if (/^20\d\d[./-]\s*\d{1,2}[./-]\s*\d{1,2}\.?\s+\d{1,2}:\d{2}(?::\d{2})?$/.test(text)) return text;
  return /^20\d{2}-\d{2}-\d{2}T.*(?:Z|[+-]\d{2}:?\d{2})$/.test(text) && Number.isFinite(Date.parse(text)) ? text : null;
}

function scheduleIsCancelled(row) {
  return Boolean(row.cancelled_at || /torol|cancel|delet|inactive/.test(normalizedLogin(row.status + ' ' + row.event_type)));
}

const scheduleSheetIds = {BUD1:30983345,BUD2:723813954};
const scheduleSheetCache = new Map();

function scheduleCsv(text) {
  const rows = [];
  let row = [], field = '', quoted = false;
  for (let i=0;i<text.length;i++) {
    const char = text[i];
    if (char === '"') {
      if (quoted && text[i+1] === '"') { field += '"'; i++; }
      else quoted = !quoted;
    } else if (!quoted && (char === ',' || char === '\n' || char === '\r')) {
      row.push(field);
      field = '';
      if (char !== ',') {
        if (char === '\r' && text[i+1] === '\n') i++;
        rows.push(row);
        row = [];
      }
    } else field += char;
  }
  if (quoted) throw new Error('Hiányos Google Sheets export.');
  if (row.length || field) rows.push([...row,field]);
  return rows;
}

async function loadScheduleSheet(warehouse) {
  const cached = scheduleSheetCache.get(warehouse);
  if (cached?.until > Date.now()) return cached.promise;
  const promise = (async()=>{
    const url = 'https://docs.google.com/spreadsheets/d/1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg/export?format=csv&gid='+scheduleSheetIds[warehouse];
    const response = await fetch(url);
    if (!response.ok) throw Error('RobotShift export unavailable');
    const [header,...rows] = scheduleCsv(await response.text());
    const columns = ['Dátum','Raktár','BlockKey','DSP ID','Template név','Slot kezdete','KIFLI_BOOKING','MUSZAKPRO_BOOKING'].map(name=>header?.indexOf(name) ?? -1);
    if (columns.includes(-1)) throw Error('RobotShift export headers do not match');
    return rows.map(row=>columns.map(index=>key(row[index]))).filter(row=>row[1] === warehouse && row[2]);
  })();
  scheduleSheetCache.set(warehouse,{until:Date.now()+60000,promise});
  try { return await promise; }
  catch (error) { if (scheduleSheetCache.get(warehouse)?.promise === promise) scheduleSheetCache.delete(warehouse); throw error; }
}

async function loadScheduleLog(warehouse, first) {
  const dates = Array.from({length:7},(_,index)=>new Date(Date.parse(first+'T12:00:00Z')+index*86400000).toISOString().slice(0,10));
  const dateQuery = dates.map(date=>`D contains '${date}'`).join(' or ');
  const query = new URLSearchParams({gid:'1961182696',tqx:'out:csv',headers:'1',
    tq:`select A,B,C,D where D contains '${warehouse}' and (${dateQuery})`});
  const response = await fetch('https://docs.google.com/spreadsheets/d/1xtvIH4fbO7C-q_BUdBaTuDnPKAwgq694l2k5TxVBxOg/gviz/tq?'+query);
  if (!response.ok) throw Error('MűszakPro LOG unavailable');
  const [header,...rows] = scheduleCsv(await response.text());
  if (header?.join('|') !== 'Időpont|Felhasználó|Művelet|Adatok') throw Error('MűszakPro LOG export headers do not match');
  return rows.flatMap(([at,user_email,operation,raw_shift_data])=>{
    const shift_date = raw_shift_data?.match(/D[áa]tum:\s*(\d{4}-\d{2}-\d{2})/i)?.[1];
    const shift_time = raw_shift_data?.match(/M[űu]szak:\s*([^,]+)/i)?.[1];
    const targetWarehouse = raw_shift_data?.match(/Rakt[áa]r:\s*(BUD[12])/i)?.[1]?.toUpperCase();
    const booked_at = scheduleTimestamp(at);
    return targetWarehouse === warehouse && dates.includes(shift_date) && shift_time && booked_at
      ? [{shift_date,shift_time,user_email,operation,booked_at,raw_shift_data}] : [];
  });
}

function scheduleLogOrder(value) {
  const local = value.match(/^(\d{4})[./-]\s*(\d{1,2})[./-]\s*(\d{1,2})\.?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (!local) return Date.parse(value);
  return Date.UTC(+local[1],+local[2]-1,+local[3],+local[4],+local[5],+(local[6] || 0));
}

function buildScheduleWeek(warehouse, blocks, hub, bookings, logs, sheetRows = [], identity = []) {
  const byBlock = new Map(), byTime = new Map(), days = {};
  const dayTime = (day, time) => day + '|' + time;
  function addShift(row, missingBlock = false) {
    const list = days[row.work_date] ||= [];
    const time = scheduleTime(row.slot_from || row.shift_text);
    const entry = {id: row.id, time, name: row.template_name || row.shift_text || 'Műszak',
      assigned: row.assigned, uncertain: missingBlock, people: []};
    list.push(entry);
    return entry;
  }
  const hubKey = row => [row.work_date,row.dsp_id,row.block_key].join('|');
  for (const block of blocks) {
    const row = addShift(block);
    byBlock.set(hubKey(block), row);
    const k = dayTime(block.work_date, row.time);
    if (!byTime.has(k)) byTime.set(k, []);
    byTime.get(k).push(row);
  }
  for (const row of hub) {
    if (!row.active) continue;
    const k = hubKey(row);
    if (!byBlock.has(k)) {
      byBlock.set(k, addShift({...row,id:k}, true));
    }
    const entry = byBlock.get(k);
    const assignedAt = scheduleTimestamp(row.assigned_at);
    entry.people.push({id:key(row.courier_id), name:key(row.courier_name), email:scheduleEmail(row.email),
      hub:true, muszakpro:false, assignedAt, firstSeenAt:assignedAt ? null : row.first_seen_at || null});
  }
  const logGroups = new Map();
  for (const log of logs) {
    const operation = normalizedLogin(log.operation);
    const text = key(log.raw_shift_data);
    const member = text.match(/Fut.r:\s*([^\s,)]+@[^\s,)]+)/i)?.[1];
    const proxy = text.match(/Proxy:\s*([^\s,)]+@[^\s,)]+)/i)?.[1];
    const user = scheduleEmail(log.user_email);
    const target = scheduleEmail(member || user);
    const time = scheduleTime(log.shift_time);
    // Only booking/deletion events enter this sequence. Requests and Q-column adjustments are different actions.
    if (!target || !time || !log.booked_at || !/^(?:foglalas(?:\s|$)|(?:radir )?torles(?:\s|$))/.test(operation)) continue;
    const match = dayTime(log.shift_date,time) + '|' + target;
    const previous = logGroups.get(match);
    if (!previous || scheduleLogOrder(log.booked_at) >= scheduleLogOrder(previous.at)) {
      logGroups.set(match, {at:log.booked_at, actor:scheduleEmail(proxy || user), booked:operation.startsWith('foglalas')});
    }
  }
  const latest = new Map(), alone = new Map();
  for (const row of bookings) {
    const time = scheduleTime(row.shift_text);
    if (!time) continue;
    const identity = scheduleEmail(row.email) || key(row.courier_id);
    const key = JSON.stringify([row.work_date,time,identity || row.id,normalizedLogin(row.shift_text)]);
    const current = latest.get(key);
    const version = row.cancelled_at || row.updated_at || row.created_at || '';
    if (!current || Date.parse(version) >= Date.parse(current.version)) latest.set(key,{row,time,version});
  }
  for (const {row,time} of latest.values()) {
    if (scheduleIsCancelled(row)) continue;
    const match = dayTime(row.work_date,time);
    const candidates = byTime.get(match) || [];
    const name = normalizedLogin(row.shift_text).replace(/[\W_]+/g,'');
    const named = candidates.filter(candidate => normalizedLogin(candidate.name).replace(/[\W_]+/g,'') === name);
    const id = key(row.courier_id), email = scheduleEmail(row.email);
    const includesCourier = candidates.filter(candidate => candidate.people.some(person => id && person.id === id || email && person.email === email));
    let entry = candidates.length === 1 ? candidates[0] : named.length === 1 ? named[0] : includesCourier.length === 1 ? includesCourier[0] : null;
    if (!entry) {
      for (const candidate of candidates) candidate.uncertain = true;
      const separate = match + '|' + name;
      if (!alone.has(separate)) alone.set(separate, addShift({...row,id:separate}, true));
      entry = alone.get(separate);
    }
    const matching = entry.people.filter(person => id && person.id === id || email && person.email === email);
    if (matching.length > 1) entry.uncertain = true;
    const person = matching.length === 1 ? matching[0] : {id, name:key(row.courier_name), email, hub:false};
    if (matching.length !== 1) entry.people.push(person);
    person.id ||= id;
    person.name ||= key(row.courier_name);
    person.muszakpro = true;
    const event = email && logGroups.get(match+'|'+email);
    person.log = event?.booked ? {actor:event.actor || null,at:event.at} : null;
  }
  const identityByGiriton = new Map();
  for (const row of identity) {
    const giriton = key(row.giriton_person_id).toLowerCase();
    if (!giriton || !row.courier_id) continue;
    const existing = identityByGiriton.get(giriton);
    if (existing !== null && (!existing || key(existing.courier_id) === key(row.courier_id))) identityByGiriton.set(giriton,row);
    else identityByGiriton.set(giriton,null);
  }
  const sheetTokens = value => [...new Set(value.split(';').map(token=>token.trim().toLowerCase()).filter(Boolean))];
  for (const [work_date,,block_key,dsp_id,template_name,slot_from,q,r] of sheetRows) {
    const group = hubKey({work_date,dsp_id,block_key});
    let shift = byBlock.get(group);
    if (!shift) {
      shift = addShift({work_date,slot_from,template_name,id:group});
      byBlock.set(group,shift);
    }
    const qIds = new Set(sheetTokens(q)), rIds = new Set(sheetTokens(r));
    const previous = new Map(shift.people.filter(person=>person.id).map(person=>[person.id,person]));
    shift.sheet = true;
    shift.uncertain = false;
    shift.people = [...new Set([...qIds,...rIds])].map(giritonId=>{
      const profile = identityByGiriton.get(giritonId);
      const id = key(profile?.courier_id);
      const existing = previous.get(id);
      const hub = qIds.has(giritonId), muszakpro = rIds.has(giritonId);
      const log = muszakpro && profile?.email && logGroups.get(dayTime(work_date,shift.time)+'|'+scheduleEmail(profile.email));
      if (!id) shift.uncertain = true;
      return {id,giritonId,name:existing?.name || key(profile?.name_without_identifier || profile?.name_json),
        hub,muszakpro,assignedAt:hub ? existing?.assignedAt : null,firstSeenAt:hub ? existing?.firstSeenAt : null,
        log:muszakpro ? existing?.log || (log?.booked ? {actor:log.actor || null,at:log.at} : null) : null};
    });
  }
  // A MűszakPro booking whose start cannot be paired with a sheet block stays
  // visible with an uncertain status, with no inferred assignment to a different slot.
  for (const list of Object.values(days)) {
    list.sort((a,b)=>a.time.localeCompare(b.time)||a.name.localeCompare(b.name,'hu'));
    for (const shift of list) {
      const hubCount = shift.people.filter(person=>person.hub).length;
      if (!shift.sheet) shift.uncertain ||= shift.assigned != null && Number(shift.assigned) > hubCount;
      shift.people.forEach(person => { delete person.email; });
    }
  }
  return {warehouse,days};
}

async function scheduleWeek(request, env) {
  const url = new URL(request.url);
  const warehouse = url.searchParams.get('warehouse');
  const start = url.searchParams.get('week') || '';
  const timestamp = Date.parse(start + 'T00:00:00Z');
  if (!['BUD1','BUD2'].includes(warehouse) || !/^\d{4}-\d{2}-\d{2}$/.test(start) || !Number.isFinite(timestamp) ||
    new Date(timestamp).toISOString().slice(0,10) !== start || new Date(timestamp).getUTCDay() !== 1) {
    return jsonResponse({error:'Érvényes raktár és hétfői kezdődátum szükséges.'},400);
  }
  const end = new Date(timestamp + 7*86400000).toISOString().slice(0,10);
  const bounds = column => `(${column}.gte.${start},${column}.lt.${end})`;
  const base = {and:bounds('work_date'), limit:6000};
  const sources = {...env, SUPABASE_READ_KEY:env.SUPABASE_SERVICE_ROLE_KEY || env.SUPABASE_READ_KEY};
  const [blocks,hub,bookings,logRows,sheetExport,identity,directLog] = await Promise.all([
    supabaseFetch(sources,PUBLIC_SCHEMA,'courier_hub_shift_blocks_raw',{...base,warehouse_code:`eq.${warehouse}`,order:'id.asc',
      select:'id,work_date,dsp_id,block_key,template_name,slot_from,assigned'}),
    supabaseFetch(sources,PUBLIC_SCHEMA,'courier_hub_shift_bookings_raw',{...base,warehouse_code:`eq.${warehouse}`,order:'id.asc',
      select:'work_date,dsp_id,block_key,slot_from,shift_text,courier_id,courier_name,email,active,first_seen_at,assigned_at:subscription_json->>assignedAt'}),
    supabaseFetch(sources,PUBLIC_SCHEMA,'raw_muszakpro_bookings',{...base,warehouse:`ilike.${warehouse}*`,order:'id.asc',
      select:'id,work_date,shift_text,email,courier_id,courier_name,status,event_type,cancelled_at,created_at,updated_at'}),
    supabaseFetch(sources,SETTLEMENT_SCHEMA,'courier_loyalty_booking_log',{and:bounds('shift_date'),warehouse:`ilike.${warehouse}*`,order:'source_row.asc,source_key.asc',limit:8000,
      select:'shift_date,shift_time,user_email,operation,booked_at,raw_shift_data,fetched_at'}).catch(()=>null),
    loadScheduleSheet(warehouse).catch(()=>null),
    supabaseFetch(sources,PUBLIC_SCHEMA,'courier_hub_courier_identity_raw',{
      select:'courier_id,giriton_person_id,name_without_identifier,name_json,email',order:'courier_id.asc',limit:6000,
    }).catch(()=>null),
    loadScheduleLog(warehouse,start).catch(()=>null),
  ]);
  if (blocks.length >= 6000 || hub.length >= 6000 || bookings.length >= 6000 || logRows?.length >= 8000) {
    return jsonResponse({error:'A heti adatsor nem tölthető be teljes egészében.'},502);
  }
  const sheetRows = (sheetExport || []).filter(row=>row[0]>=start && row[0]<end);
  const sheetAvailable = Boolean(sheetRows.length && identity?.length && identity.length<6000);
  return jsonResponse({...buildScheduleWeek(warehouse,blocks,hub,bookings,directLog ?? logRows ?? [],sheetAvailable ? sheetRows : [],identity || []),sheetAvailable,
    logDirect:directLog !== null,logAvailable:directLog !== null || logRows !== null,
    logUpdatedAt: (logRows || []).reduce((last,row)=>key(row.fetched_at)>last?key(row.fetched_at):last,'') || null});
}

export default {
  async fetch(request, env, executionContext) {
    const url = new URL(request.url);

    if (url.pathname === "/api/login") {
      if (request.method !== "POST") return jsonResponse({ error: "Use POST." }, 405);
      try {
        return await loginWithPwa(request, env);
      } catch (error) {
        return jsonResponse({ error: `A PWA-belépés nem érhető el: ${error instanceof Error ? error.message : String(error)}` }, 502);
      }
    }

    if (url.pathname === "/api/me") {
      if (request.method !== "GET") return jsonResponse({ error: "Use GET." }, 405);
      try {
        return await dashboardSession(request, env);
      } catch (error) {
        return jsonResponse({ error: `A PWA-munkamenet nem ellenőrizhető: ${error instanceof Error ? error.message : String(error)}` }, 502);
      }
    }

    if (url.pathname === "/api/logout") {
      if (request.method !== "POST") return jsonResponse({ error: "Use POST." }, 405);
      return logoutHub();
    }

    if (['/api/courier360-payment-close','/api/courier360-bank-account','/api/courier360-complaint'].includes(url.pathname)) {
      if(request.method!=='POST')return jsonResponse({error:'Use POST.'},405);
      const access=await requireDashboardUser(request,env);if(access.error)return access.error;
      try{return url.pathname.endsWith('complaint')?await courier360ComplaintAction(request,env,access.user,executionContext):url.pathname.endsWith('bank-account')?await courier360SaveBankAccount(request,env,access.user):await courier360ClosePayment(request,env,access.user)}
      catch{return jsonResponse({error:'A művelet nem menthető. Frissítsd az adatokat és ellenőrizd a források elérhetőségét.'},500)}
    }

    if (url.pathname === '/api/daily-tasks') {
      if (request.method !== 'GET') return jsonResponse({error: 'Csak olvasási kérés támogatott.'}, 405);
      const access = await requireDashboardUser(request, env);
      if (access.error) return access.error;
      return dailyTasks(env, access.user);
    }

    if (url.pathname === '/api/courier-reki') {
      if(request.method!=='GET')return jsonResponse({error:'Csak olvasási kérés támogatott.'},405);
      const access=await requireDashboardUser(request,env);
      if(access.error)return access.error;
      if(!['admin','superadmin'].includes(access.user.role.toLowerCase()))return jsonResponse({error:'Reklamációkezelő jogosultság szükséges.'},403);
      const month=url.searchParams.get('month')||'';
      if(!/^20[0-9]{2}-(0[1-9]|1[0-2])$/.test(month))return jsonResponse({error:'Érvénytelen hónap.'},400);
      const start=month+'-01';
      const [year,number]=month.split('-').map(Number);
      const end=new Date(Date.UTC(year,number,1)).toISOString().slice(0,10);
      const qualityEnv={...env,SUPABASE_READ_KEY:env.SUPABASE_SERVICE_ROLE_KEY||env.SUPABASE_READ_KEY};
      try{
        const createdRange=`(created_at.gte.${budapestMidnightUtc(start)},created_at.lt.${budapestMidnightUtc(end)})`;
        const [cases,excel,couriers,alerts,shifts,resolutions]=await Promise.all([
          supabaseFetch(qualityEnv,PUBLIC_SCHEMA,'pwa_quality_complaints',{
            work_month:'eq.'+start,select:'id,courier_id,courier_name,topic,status,created_at,forwarded_at,responded_at,message,admin_response,affected_items',
            order:'created_at.desc,id.desc',limit:10000,
          }),
          supabaseFetch(qualityEnv,SETTLEMENT_SCHEMA,'route_delay_form_draft',{
            state:'eq.sent',and:`(submitted_at.gte.${budapestMidnightUtc(start)},submitted_at.lt.${budapestMidnightUtc(end)})`,
            select:'id,courier_id,courier_name,route_id,work_date,submitted_at,source_filename,source_row',order:'submitted_at.desc,id.desc',limit:10000,
          }),
          supabaseFetch(qualityEnv,PUBLIC_SCHEMA,'courier_master',{select:'courier_id,courier_name',order:'courier_id.asc',limit:10000}),
          supabaseFetch(qualityEnv,PUBLIC_SCHEMA,'courier_route_alerts',{
            select:'id,courier_id,courier_name,route_id,alert_type,message,status,created_at',
            alert_type:'in.(delay,bag_missing,problem)',and:createdRange,order:'created_at.desc,id.desc',limit:10000,
          }),
          supabaseFetch(qualityEnv,PUBLIC_SCHEMA,'courier_shift_checkins',{
            select:'id,courier_id,courier_name,work_date,shift_name,event_type,created_at',event_type:'in.(shift_late,coordinator_shift_late)',
            and:`(work_date.gte.${start},work_date.lt.${end})`,order:'created_at.desc,id.desc',limit:10000,
          }),
          supabaseFetch(qualityEnv,PUBLIC_SCHEMA,'peopleforce_card_statuses',{
            select:'action_key',document_month:'eq.'+start,status:'eq.done',
            action_key:'like.internal_complaint_assignment:duplicate-signal:*',order:'action_key.asc',limit:10000,
          }),
        ]);
        const linked=new Set(cases.flatMap(row=>(row.affected_items||[]).map(item=>`${item.signalKind}:${item.signalId}`)));
        const duplicates=new Set(resolutions.map(row=>row.action_key.split('duplicate-signal:')[1]));
        const signals=[...alerts.map(row=>({...row,kind:'route'})),...shifts.map(row=>({...row,kind:'shift'}))]
          .filter(row=>row.status!=='auto'&&!linked.has(row.kind+':'+row.id)&&!duplicates.has(row.kind+':'+row.id));
        return jsonResponse({cases,excel,couriers,signals});
      }catch{return jsonResponse({error:'A reklamációs lista most nem tölthető be.'},502);}
    }

    if (url.pathname === '/api/courier-finance-breakdown') {
      if (request.method !== 'GET') return jsonResponse({error:'Csak olvasási kérés támogatott.'},405);
      const access = await requireDashboardUser(request,env);
      if (access.error) return access.error;
      try { return await courierFinanceBreakdown(request, env); }
      catch (error) { return jsonResponse({error:error.status === 400 ? error.message : 'A tételbontás nem tölthető be.'},error.status === 400 ? 400 : 500); }
    }

    if (url.pathname === '/api/schedule-week') {
      if (request.method !== 'GET') return jsonResponse({error:'Csak olvasási kérés támogatott.'},405);
      const access = await requireDashboardUser(request,env);
      if (access.error) return access.error;
      try { return await scheduleWeek(request,env); }
      catch { return jsonResponse({error:'A beosztás adatai most nem tölthetők be.'},502); }
    }

    if (url.pathname === '/api/courier-attendance') {
      if (request.method !== 'GET') return jsonResponse({error:'Csak olvasási kérés támogatott.'},405);
      const access = await requireDashboardUser(request,env);
      if (access.error) return access.error;
      return courierAttendanceData(env);
    }

    if (url.pathname === '/api/courier360-active') {
      if (request.method !== 'GET') return jsonResponse({error: 'Csak olvasási kérés támogatott.'}, 405);
      const access = await requireDashboardUser(request, env);
      if (access.error) return access.error;
      return courier360ActiveCouriers(env,new Date(),url.searchParams.get('scope') === 'all');
    }

    if (url.pathname === '/api/courier360-profile') {
      if (request.method !== 'GET') return jsonResponse({error: 'Csak olvasási kérés támogatott.'}, 405);
      const access = await requireDashboardUser(request, env);
      if (access.error) return access.error;
      try { return await courier360Profile(request, env); }
      catch { return jsonResponse({error: 'A futár adatlapja most nem tölthető be.'}, 502); }
    }

    if (["/api/courier360","/api/courier360-document"].includes(url.pathname)) {
      if(request.method!=="GET")return jsonResponse({error:'Read-only endpoint. Use GET.'},405);
      const access=await requireDashboardUser(request,env);if(access.error)return access.error;
      try{return url.pathname.endsWith('-document')?await courier360Document(request,env):await courier360Data(request,env)}
      catch(error){return jsonResponse({error:error instanceof Error?error.message:String(error)},error.status===400?400:500)}
    }

    if (url.pathname === "/api/settlement-trends") {
      if (request.method !== "GET") return jsonResponse({error:"Read-only endpoint. Use GET."},405);
      try {
        const access = await requireDashboardUser(request, env);
        if (access.error) return access.error;
        return await settlementTrends(request,env);
      } catch (error) {
        return jsonResponse({error:error instanceof Error ? error.message : String(error)},500);
      }
    }

    if (url.pathname === "/api/settlement-dashboard") {
      if (request.method !== "GET") {
        return jsonResponse({ error: "Read-only endpoint. Use GET." }, 405);
      }
      try {
        const access = await requireDashboardUser(request, env);
        if (access.error) return access.error;
        return await settlementDashboard(request, env);
      } catch (error) {
        return jsonResponse(
          {
            source: "error",
            error: error instanceof Error ? error.message : String(error),
          },
          500,
        );
      }
    }

    return env.ASSETS.fetch(request);
  },
};
