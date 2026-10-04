const SETTLEMENT_SCHEMA = "settlement";
const PUBLIC_SCHEMA = "public";

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
  return "TIG-re vár";
}

function buildCourierRow(row, profile, workload, closure) {
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
  const malus = Math.abs(money(row.malus_huf));
  const importedMalus = Math.abs(money(row.imported_malus_huf));
  const manualMalus = Math.abs(money(row.manual_malus_huf));
  const atm = Math.abs(money(row.atm_deduction_huf || row.imported_atm_deduction_huf));
  const otherExpense = Math.abs(money(row.other_expense_huf));
  const salaryAdvance = Math.abs(money(row.salary_advance_huf));
  const reserve = Math.abs(money(row.target_reserve_topup_huf));
  const insurance = Math.abs(money(row.insurance_fee_huf));
  const correctionDeduction = Math.abs(money(row.correction_deduction_huf));
  const deductions = malus + importedMalus + manualMalus + atm + otherExpense + salaryAdvance + reserve + insurance + correctionDeduction;
  const routeCount = Number(workload?.completed_route_count || row.route_count || 0);
  const orderCount = Number(workload?.order_count || row.order_count || 0);

  return {
    courierId: key(row.courier_id),
    courierName: key(row.driver_name || profile?.courier_name || workload?.courier_name),
    email: key(profile?.email || profile?.billing_email),
    warehouse: key(profile?.warehouse_name || "BUD"),
    status: statusForRow(row, closure),
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
    atm,
    salaryAdvance,
    reserve,
    insurance,
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

  const [profiles, workloads, closures, discrepancies, discrepancyCoverage] = await Promise.all([
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
  ]);

  const profileById = new Map(profiles.map((row) => [key(row.courier_id), row]));
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

  const totals = couriers.reduce(
    (acc, row) => {
      acc.couriers += 1;
      acc.routes += row.routeCount;
      acc.orders += row.orderCount;
      acc.income += row.income;
      acc.deductions += row.deductions;
      acc.payable += row.payable;
      acc.issues += row.status === "Eltérés" ? 1 : 0;
      acc.tigWait += row.status === "TIG-re vár" ? 1 : 0;
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
    selectedCourier: couriers[0] || null,
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/settlement-dashboard") {
      if (request.method !== "GET") {
        return jsonResponse({ error: "Read-only endpoint. Use GET." }, 405);
      }
      try {
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
