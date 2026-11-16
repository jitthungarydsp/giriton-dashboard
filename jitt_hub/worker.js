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

async function loginWithPwa(request, env) {
  const body = await request.json().catch(() => null);
  const username = String(body?.username || "").trim();
  const password = String(body?.password || "");
  if (!username || !password) {
    return jsonResponse({ error: "Felhasználónév és jelszó szükséges." }, 400);
  }

  const account = await findPwaUser(env, username);
  if (!account || account.active !== true || !(await verifyPwaPassword(password, account.password_hash))) {
    return authenticatedJson({ error: "Hibás felhasználónév vagy jelszó." }, 401);
  }
  const user = publicPwaUser(account);
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

  const response = await fetch(url, {
    headers: {
      apikey: supabaseKey,
      authorization: `Bearer ${supabaseKey}`,
      "accept-profile": schema,
    },
  });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${schema}.${table}: HTTP ${response.status} ${text.slice(0, 500)}`);
  }
  return text ? JSON.parse(text) : [];
}

function statusForRow(row, closure) {
  if (row.invoiceIssueCount > 0) {
    return "Számlaellenőrzés";
  }
  if (closure?.status === "done") {
    return "Kifizethető";
  }
  const payable = money(row.payable_huf);
  if (payable <= 0) {
    return "Eltérés";
  }
  if (payable > 600000) {
    return "Számlaellenőrzés";
  }
  return "Teljesítés-összesítőre vár";
}

function buildCourierRow(row, profile, workload, closure, { missingSummary = false } = {}) {
  const base = money(row.courier_base_rate_huf);
  const tip = money(row.tip_huf);
  const delay = money(row.delay_bonus_huf);
  const compliance = money(row.compliance_bonus_huf);
  const otherBonus = money(row.other_route_bonus_huf);
  const importedBonus = money(row.imported_bonus_huf);
  const manualBonus = money(row.manual_bonus_huf);
  const customerRating = money(row.customer_rating_bonus_huf);
  const loyalty = money(row.loyalty_bonus_huf);
  const correctionIncome = money(row.correction_bonus_huf || row.correction_income_huf);
  const bonus = delay + compliance + otherBonus + importedBonus + manualBonus + customerRating + loyalty + correctionIncome;
  const payable = money(closure?.payable_huf || row.payable_huf);
  const income = base + tip + bonus;
  // The import's total appears as monthly_malus_huf. Detailed imported/manual
  // columns are optional, so calculate the same net amount as the PWA does.
  const monthlyMalus = Math.abs(money(row.monthly_malus_huf || row.malus_huf));
  const manualMalus = Math.abs(money(row.manual_malus_huf));
  const importedMalus = Math.abs(money(row.imported_malus_huf)) || Math.max(monthlyMalus - manualMalus, 0);
  const malus = importedMalus + manualMalus;
  const atm = Math.abs(money(row.atm_deduction_huf || row.imported_atm_deduction_huf));
  const otherExpense = Math.abs(money(row.other_expense_huf));
  const salaryAdvance = Math.abs(money(row.salary_advance_huf));
  const reserve = Math.abs(money(row.target_reserve_topup_huf || row.reserve_addition_huf || row.reserve_deduction_huf));
  const insurance = Math.abs(money(row.insurance_fee_huf));
  const correctionDeduction = Math.abs(money(row.correction_deduction_huf));
  const otherDeduction = otherExpense + correctionDeduction;
  const deductions = malus + atm + otherDeduction + salaryAdvance + reserve + insurance;
  const routeCount = Number(workload?.completed_route_count || row.route_count || 0);
  const orderCount = Number(workload?.order_count || row.order_count || 0);

  return {
    courierId: key(row.courier_id),
    courierName: key(row.driver_name || profile?.courier_name || workload?.courier_name),
    email: key(profile?.email || profile?.billing_email),
    warehouse: key(profile?.warehouse_name || "BUD"),
    status: missingSummary ? "Elszámolásra vár" : statusForRow(row, closure),
    routeCount,
    orderCount,
    base,
    tip,
    bonus,
    delay,
    compliance,
    otherBonus,
    importedBonus,
    manualBonus,
    customerRating,
    loyalty,
    malus,
    importedMalus,
    manualMalus,
    atm,
    salaryAdvance,
    reserve,
    insurance,
    otherDeduction,
    income,
    deductions,
    payable,
    closureStatus: key(closure?.status),
    bookedShiftCount: Number(workload?.booked_shift_count || 0),
    advanceBookedShiftCount: Number(workload?.advance_booked_shift_count || 0),
    giritonShiftCount: Number(workload?.giriton_shift_count || 0),
    invoiceIssueCount: Number(row.invoiceIssueCount || 0),
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

  const [profiles, workloads, closures, discrepancies, discrepancyCoverage, processMetricRows, activePwaUsers] = await Promise.all([
    numericIdFilter
      ? supabaseFetch(env, PUBLIC_SCHEMA, "courier_master", {
          select: "courier_id,courier_name,email,billing_email,warehouse_name",
          courier_id: `in.(${numericIdFilter})`,
          limit,
        }).catch(() => [])
      : [],
    idFilter
      ? supabaseFetch(env, SETTLEMENT_SCHEMA, "courier_monthly_workload_summary", {
          select: "courier_id,courier_name,period_start,booked_shift_count,giriton_shift_count,completed_route_count,order_count",
          period_start: `eq.${periodStart}`,
          courier_id: `in.(${idFilter})`,
          limit,
        }).catch(() => [])
      : [],
    idFilter
      ? supabaseFetch(env, SETTLEMENT_SCHEMA, "courier_monthly_closure", {
          select: "courier_id,courier_name,period_start,payable_huf,status,invoice_number,closed_at",
          period_start: `eq.${periodStart}`,
          courier_id: `in.(${idFilter})`,
          limit,
        }).catch(() => [])
      : [],
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
    supabaseFetch(env, PUBLIC_SCHEMA, "pwa_users", {
      select: "courier_id,username,active",
      active: "eq.true",
      limit: 10000,
    }).catch(() => []),
  ]);

  const summaryCourierIds = new Set(courierIds);
  const missingPwaUsers = activePwaUsers.filter((user) => {
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
    };
    return buildCourierRow(
      row,
      profileById.get(key(row.courier_id)),
      workloadById.get(key(row.courier_id)),
      closureById.get(key(row.courier_id)),
    );
  });
  missingPwaUsers.forEach((user) => {
    couriers.push(buildCourierRow(
      { courier_id: user.courier_id, driver_name: user.username },
      profileById.get(key(user.courier_id)),
      undefined,
      undefined,
      { missingSummary: true },
    ));
  });

  const totals = couriers.reduce(
    (acc, row) => {
      acc.couriers += 1;
      acc.routes += row.routeCount;
      acc.orders += row.orderCount;
      acc.income += row.income;
      acc.deductions += row.deductions;
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
    selectedCourier: couriers[0] || null,
  });
}

export default {
  async fetch(request, env) {
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
