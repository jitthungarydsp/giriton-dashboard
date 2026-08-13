const TABLES = {
  stories: "mart_dsp_route_stories",
  quality: "dsp_courier_shift_quality_report",
  qualityDaily: "dsp_courier_quality_daily"
};

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store"
    }
  });
}

function isAuthorized(request, env) {
  const expected = String(env.HUB_REPORT_TOKEN || "").trim();
  if (!expected) return false;
  const cookieToken = String(request.headers.get("cookie") || "")
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith("hub_report_token="))
    ?.slice("hub_report_token=".length);
  const actual = String(request.headers.get("x-hub-report-token") || (cookieToken ? decodeURIComponent(cookieToken) : "")).trim();
  return actual && actual === expected;
}

function parseMonth(value) {
  const month = String(value || "").trim();
  return /^\d{4}-\d{2}$/.test(month) ? month : "2026-07";
}

function monthStart(month) {
  return `${month}-01`;
}

function nextMonth(month) {
  const [year, rawMonth] = month.split("-").map(Number);
  const date = new Date(Date.UTC(year, rawMonth, 1));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}-01`;
}

function asNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : 0;
}

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && value !== "") ?? null;
}

function dayKey(value) {
  return String(value || "").slice(0, 10);
}

function cleanCourierId(value) {
  return String(value ?? "").trim();
}

function sameShift(story, shift) {
  if (!story || !shift) return false;
  if (story.shift_id && shift.booking_code && String(story.shift_id) === String(shift.booking_code)) return true;
  if (story.shift_name && shift.shift_name && String(story.shift_name) === String(shift.shift_name)) return true;
  if (story.shift_start && shift.shift_start_at) {
    return String(story.shift_start).slice(0, 16) === String(shift.shift_start_at).slice(0, 16);
  }
  return false;
}

async function readSupabase(env, table, filters, order = "", limit = 5000) {
  const supabaseUrl = String(env.SUPABASE_URL || "").replace(/\/$/, "");
  const key = env.SUPABASE_SERVICE_ROLE_KEY || env.SUPABASE_ANON_KEY;

  if (!supabaseUrl || !key) {
    throw new Error("Hianyzik a SUPABASE_URL vagy SUPABASE_SERVICE_ROLE_KEY / SUPABASE_ANON_KEY beallitas.");
  }

  const rows = [];
  const pageSize = 1000;

  for (let from = 0; from < limit; from += pageSize) {
    const url = new URL(`${supabaseUrl}/rest/v1/${table}`);
    url.searchParams.set("select", "*");
    for (const [name, value] of filters) url.searchParams.append(name, value);
    if (order) url.searchParams.set("order", order);

    const to = Math.min(from + pageSize - 1, limit - 1);
    const response = await fetch(url, {
      headers: {
        apikey: key,
        authorization: `Bearer ${key}`,
        "Range-Unit": "items",
        Range: `${from}-${to}`
      }
    });

    if (response.status === 404) return [];

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`${table}: ${response.status} ${text.slice(0, 500)}`);
    }

    const chunk = await response.json();
    rows.push(...chunk);
    if (chunk.length < pageSize) break;
  }

  return rows;
}

function routeFrom(story, quality) {
  return {
    routeId: firstValue(story?.route_id, quality?.route_id),
    routeType: firstValue(story?.route_type, quality?.route_type),
    assignmentMode: firstValue(story?.assignment_mode, quality?.assignment_mode),
    assignedAt: firstValue(story?.assigned_at, quality?.assigned_at),
    routeDurationMinutes: firstValue(
      story?.total_route_minutes,
      story?.real_route_minutes,
      story?.planned_route_minutes,
      quality?.planned_route_minutes
    ),
    addressCount: firstValue(story?.address_count, quality?.address_count, quality?.order_count),
    plannedReturnAt: firstValue(story?.planned_return, quality?.planned_return_at),
    realReturnAt: firstValue(story?.real_return, quality?.real_return_at),
    timeWindowLateCount: firstValue(story?.time_window_late_count, quality?.time_window_late_count),
    timeWindowLateTotalMinutes: firstValue(story?.time_window_late_total_minutes, quality?.time_window_late_total_minutes),
    plannedDepartureAt: firstValue(story?.planned_departure, quality?.planned_departure_at),
    realDepartureAt: firstValue(story?.real_departure, quality?.real_departure_at)
  };
}

function buildReport(month, storyRows, qualityRows, qualityDailyRows) {
  const couriers = new Map();
  const storiesByCourierDate = new Map();

  function ensureCourier(row) {
    const courierId = cleanCourierId(row.courier_id);
    if (!courierId) return null;
    if (!couriers.has(courierId)) {
      couriers.set(courierId, {
        courierId,
        name: row.courier_name || `Futar #${courierId}`,
        warehouse: firstValue(row.warehouse_name, row.warehouse, ""),
        orders: 0,
        routes: 0,
        delayBonus: 0,
        complianceBonus: 0,
        shifts: []
      });
    }
    const courier = couriers.get(courierId);
    courier.name = firstValue(row.courier_name, courier.name, `Futar #${courierId}`);
    courier.warehouse = firstValue(row.warehouse_name, row.warehouse, courier.warehouse, "");
    return courier;
  }

  for (const story of storyRows) {
    const key = `${cleanCourierId(story.courier_id)}|${dayKey(story.work_date)}`;
    if (!storiesByCourierDate.has(key)) storiesByCourierDate.set(key, []);
    storiesByCourierDate.get(key).push(story);
  }

  const matchedRouteKeys = new Set();
  for (const quality of qualityRows) {
    const courier = ensureCourier(quality);
    if (!courier) continue;
    const sameDayStories = storiesByCourierDate.get(`${cleanCourierId(quality.courier_id)}|${dayKey(quality.work_date)}`) || [];
    const matchedStories = sameDayStories.filter((story) =>
      (quality.route_id && story.route_id && String(story.route_id) === String(quality.route_id)) || sameShift(story, quality)
    );
    const routeSources = matchedStories.length ? matchedStories : (quality.route_id ? [null] : []);

    for (const story of matchedStories) {
      if (story.route_id) matchedRouteKeys.add(`${cleanCourierId(story.courier_id)}|${dayKey(story.work_date)}|${story.route_id}`);
    }

    courier.shifts.push({
      workDate: dayKey(quality.work_date),
      shiftKey: quality.shift_key,
      shiftName: firstValue(quality.shift_name, quality.shift_key),
      shiftStartAt: quality.shift_start_at,
      shiftEndAt: quality.shift_end_at,
      availableAt: firstValue(quality.available_at, matchedStories[0]?.available_for_shift_since),
      queueStartedAt: firstValue(quality.queue_started_at, matchedStories[0]?.queue_started_at),
      checkedInAt: firstValue(quality.queue_started_at, quality.available_at, matchedStories[0]?.queue_started_at, matchedStories[0]?.available_for_shift_since),
      noShow: Boolean(quality.no_show),
      noShowReason: quality.no_show_reason || "",
      qualityNote: quality.quality_ok ? "OK" : "",
      routes: routeSources.map((story) => routeFrom(story, quality))
    });
  }

  for (const story of storyRows) {
    const routeKey = `${cleanCourierId(story.courier_id)}|${dayKey(story.work_date)}|${story.route_id}`;
    if (matchedRouteKeys.has(routeKey)) continue;
    const courier = ensureCourier(story);
    if (!courier) continue;

    courier.shifts.push({
      workDate: dayKey(story.work_date),
      shiftKey: firstValue(story.shift_id, story.shift_name, story.shift_start),
      shiftName: firstValue(story.shift_name, story.shift_start, "Muszak"),
      shiftStartAt: story.shift_start,
      shiftEndAt: story.shift_end,
      availableAt: story.available_for_shift_since,
      queueStartedAt: story.queue_started_at,
      checkedInAt: firstValue(story.queue_started_at, story.available_for_shift_since),
      noShow: false,
      noShowReason: "",
      qualityNote: "",
      routes: [routeFrom(story, null)]
    });
  }

  for (const row of qualityDailyRows) {
    const courier = ensureCourier(row);
    if (!courier) continue;
    courier.orders = Math.max(courier.orders, asNumber(firstValue(row.orders, row.order_count)));
    courier.routes = Math.max(courier.routes, asNumber(firstValue(row.routes, row.route_count)));
    courier.delayBonus += asNumber(firstValue(row.courier_delay_bonus_huf, row.delay_bonus, row.delay_bonus_amount, row.delay_fee, row.delay_amount));
    courier.complianceBonus += asNumber(firstValue(row.courier_compliance_bonus_huf, row.compliance_bonus, row.compliance_bonus_amount, row.compliance_fee, row.compliance_amount));
  }

  for (const courier of couriers.values()) {
    courier.shifts.sort((a, b) => String(a.shiftStartAt || a.workDate).localeCompare(String(b.shiftStartAt || b.workDate)));
    const routeRows = courier.shifts.flatMap((shift) => shift.routes || []);
    const routeIds = new Set(routeRows.map((route) => route.routeId).filter(Boolean));
    courier.routes = courier.routes || routeIds.size || routeRows.length;
    courier.orders = courier.orders || routeRows.reduce((sum, route) => sum + asNumber(route.addressCount), 0);
  }

  const sortedCouriers = [...couriers.values()].sort((a, b) => a.name.localeCompare(b.name, "hu"));
  const totals = sortedCouriers.reduce((acc, courier) => {
    acc.orders += asNumber(courier.orders);
    acc.routes += asNumber(courier.routes);
    acc.delayBonus += asNumber(courier.delayBonus);
    acc.complianceBonus += asNumber(courier.complianceBonus);
    return acc;
  }, { orders: 0, routes: 0, delayBonus: 0, complianceBonus: 0 });

  return {
    month,
    source: "supabase",
    generatedAt: new Date().toISOString(),
    totals,
    couriers: sortedCouriers
  };
}

export async function onRequestGet({ request, env }) {
  if (!isAuthorized(request, env)) {
    return json({ error: "Nincs jogosultsag a riport adatokhoz. Add meg a belso riport kulcsot." }, 401);
  }

  try {
    const url = new URL(request.url);
    const month = parseMonth(url.searchParams.get("month"));
    const start = monthStart(month);
    const end = nextMonth(month);
    const courierId = cleanCourierId(url.searchParams.get("courierId"));
    const filters = [
      ["work_date", `gte.${start}`],
      ["work_date", `lt.${end}`]
    ];

    if (courierId) filters.push(["courier_id", `eq.${courierId}`]);

    const [storyRows, qualityRows, qualityDailyRows] = await Promise.all([
      readSupabase(env, TABLES.stories, filters, "work_date.asc,courier_id.asc,assigned_at.asc", 10000),
      readSupabase(env, TABLES.quality, filters, "work_date.asc,courier_id.asc,shift_start_at.asc", 10000),
      readSupabase(env, TABLES.qualityDaily, filters, "work_date.asc,courier_id.asc", 10000).catch(() => [])
    ]);

    return json(buildReport(month, storyRows, qualityRows, qualityDailyRows));
  } catch (error) {
    return json({ error: error.message || "Ismeretlen riport hiba." }, 500);
  }
}
