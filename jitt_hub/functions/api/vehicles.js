const TABLES = {
  assignments: "dsp_vehicle_assignments",
  stories: "mart_dsp_route_stories",
  service: "dsp_vehicle_service_status",
  liveRawCandidates: ["raw_dsp_live_drivers", "dsp_drivers_live_raw"],
  liveKmCandidates: ["stg_dsp_route_km_latest", "dsp_route_km_latest"]
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
  const actual = String(request.headers.get("x-hub-report-token") || "").trim();
  return actual && actual === expected;
}

function isoDate(value) {
  const text = String(value || "").slice(0, 10);
  return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : new Date().toISOString().slice(0, 10);
}

function addDays(dateText, days) {
  const date = new Date(`${dateText}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null && String(value).trim() !== "") ?? null;
}

function clean(value) {
  return String(value ?? "").trim();
}

function plateKey(value) {
  return clean(value).toUpperCase().replace(/[^A-Z0-9]/g, "");
}

function asNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

async function readSupabase(env, table, filters = [], order = "", limit = 5000) {
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

    const response = await fetch(url, {
      headers: {
        apikey: key,
        authorization: `Bearer ${key}`,
        "Range-Unit": "items",
        Range: `${from}-${Math.min(from + pageSize - 1, limit - 1)}`
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

async function readFirstAvailable(env, tables, filters = [], order = "", limit = 5000) {
  for (const table of tables) {
    const rows = await readSupabase(env, table, filters, order, limit);
    if (rows.length) return { table, rows };
  }
  return { table: tables[0] || "", rows: [] };
}

function assignmentWarehouse(row) {
  return firstValue(
    row.warehouse,
    row.warehouse_name,
    row.warehouseName,
    row.response_json?.warehouse,
    row.response_json?.raw?.raktar,
    row.response_json?.raw?.warehouse
  );
}

function assignmentDateTime(workDate, timeValue) {
  const date = isoDate(workDate);
  const time = clean(timeValue);
  if (!time) return date;
  if (time.includes("T")) return time;
  return `${date}T${time.length === 5 ? `${time}:00` : time}`;
}

function baseVehicle(row) {
  const plate = firstValue(row.license_plate, row.vehicle_plate, row.plate);
  const car = firstValue(row.car, row.vehicle_model, row.vehicle, row.vehicle_type);
  const key = plateKey(plate) || `CAR:${clean(car).toUpperCase()}`;
  return { key, plate: clean(plate), car: clean(car) };
}

function ensureVehicle(map, seed) {
  if (!seed.key) return null;
  if (!map.has(seed.key)) {
    map.set(seed.key, {
      key: seed.key,
      plate: seed.plate || "",
      car: seed.car || "",
      status: "Nincs adat",
      warehouse: "",
      currentDriver: "",
      currentAssignmentDate: "",
      currentShiftStart: "",
      currentShiftEnd: "",
      shiftType: "",
      odometerKm: null,
      lastKmDate: "",
      nextServiceAt: "",
      servicePlace: "",
      serviceNote: "",
      actualDriver: "",
      actualWarehouse: "",
      actualPlate: "",
      actualState: "",
      actualSeenAt: "",
      actualShiftName: "",
      actualRouteAssignedAt: "",
      active: null,
      assignments: []
    });
  }
  const vehicle = map.get(seed.key);
  if (!vehicle.plate && seed.plate) vehicle.plate = seed.plate;
  if (!vehicle.car && seed.car) vehicle.car = seed.car;
  return vehicle;
}

function liveRowDate(row) {
  return clean(firstValue(row.fetched_at, row.last_seen_at, row.updated_at, row.created_at));
}

function latestLiveRows(rows) {
  const byDriver = new Map();
  for (const row of rows) {
    const driverId = clean(firstValue(row.driver_id, row.courier_id));
    const key = driverId || `${clean(row.courier_name)}:${plateKey(row.license_plate)}`;
    if (!key) continue;
    const currentSeen = liveRowDate(row);
    const previous = byDriver.get(key);
    if (!previous || currentSeen > liveRowDate(previous)) byDriver.set(key, row);
  }
  return Array.from(byDriver.values());
}

function applyLive(vehicle, row) {
  vehicle.actualDriver = clean(firstValue(row.courier_name, row.driver_name));
  vehicle.actualWarehouse = clean(firstValue(row.warehouse_name, row.warehouse));
  vehicle.actualPlate = clean(firstValue(row.license_plate, row.vehicle_plate, row.plate));
  vehicle.actualState = clean(firstValue(row.current_state, row.status));
  vehicle.actualSeenAt = liveRowDate(row);
  vehicle.actualShiftName = clean(row.shift_name);
  vehicle.actualRouteAssignedAt = clean(row.route_assigned_at);
  vehicle.active = row.active ?? vehicle.active;
  if (!vehicle.plate && vehicle.actualPlate) vehicle.plate = vehicle.actualPlate;
  if (!vehicle.warehouse && vehicle.actualWarehouse) vehicle.warehouse = vehicle.actualWarehouse;
}

function applyService(vehicle, row) {
  vehicle.nextServiceAt = clean(firstValue(row.next_service_at, row.next_service_date, row.service_date));
  vehicle.servicePlace = clean(firstValue(row.service_place, row.next_service_place, row.workshop));
  vehicle.serviceNote = clean(firstValue(row.service_note, row.note, row.comment));
  vehicle.serviceStatus = clean(firstValue(row.status, row.service_status));
  const km = asNumber(firstValue(row.odometer_km, row.current_km, row.km));
  if (km !== null) vehicle.odometerKm = km;
  if (!vehicle.car) vehicle.car = clean(firstValue(row.car, row.vehicle_model, row.vehicle));
  if (!vehicle.warehouse) vehicle.warehouse = clean(row.warehouse);
}

function finalizeVehicle(vehicle, targetDate) {
  const sorted = vehicle.assignments.slice().sort((a, b) => {
    const left = `${a.workDate} ${a.shiftStart || ""}`;
    const right = `${b.workDate} ${b.shiftStart || ""}`;
    return left.localeCompare(right);
  });
  const todayAssignments = sorted.filter((item) => item.workDate === targetDate);
  const nextAssignments = sorted.filter((item) => item.workDate >= targetDate).slice(0, 5);
  const lastAssignment = sorted.filter((item) => item.workDate <= targetDate).pop();
  const current = todayAssignments[0] || nextAssignments[0] || lastAssignment;

  if (current) {
    vehicle.currentDriver = current.driverName;
    vehicle.currentAssignmentDate = current.workDate;
    vehicle.currentShiftStart = current.shiftStart;
    vehicle.currentShiftEnd = current.shiftEnd;
    vehicle.shiftType = current.shiftType;
    vehicle.warehouse = current.warehouse || vehicle.warehouse;
  }

  const serviceDue = vehicle.nextServiceAt && vehicle.nextServiceAt <= targetDate;
  if (serviceDue) vehicle.status = "Szerviz esedékes";
  else if (todayAssignments.length) vehicle.status = "Kiosztva";
  else if (nextAssignments.length) vehicle.status = "Tervezve";
  else vehicle.status = "Szabad";

  return {
    ...vehicle,
    assignments: nextAssignments,
    assignmentCount: sorted.length
  };
}

function buildVehicles(targetDate, assignmentRows, storyRows, serviceRows, liveRows) {
  const vehicles = new Map();
  for (const row of assignmentRows) {
    const seed = baseVehicle(row);
    const vehicle = ensureVehicle(vehicles, seed);
    if (!vehicle) continue;
    vehicle.assignments.push({
      workDate: isoDate(row.work_date),
      driverName: clean(row.driver_name),
      warehouse: clean(assignmentWarehouse(row)),
      shiftStart: clean(row.shift_start),
      shiftEnd: clean(row.shift_end),
      shiftType: clean(row.shift_type),
      startsAt: assignmentDateTime(row.work_date, row.shift_start)
    });
  }

  const latestKm = new Map();
  for (const row of storyRows) {
    const key = plateKey(row.vehicle_plate);
    if (!key) continue;
    const km = asNumber(row.mileage_km);
    if (km === null) continue;
    const existing = latestKm.get(key);
    const rowDate = isoDate(row.work_date);
    if (!existing || rowDate > existing.date) {
      latestKm.set(key, { km, date: rowDate, car: clean(row.vehicle_model) });
    }
    ensureVehicle(vehicles, { key, plate: clean(row.vehicle_plate), car: clean(row.vehicle_model) });
  }

  for (const [key, kmRow] of latestKm) {
    const vehicle = vehicles.get(key);
    if (!vehicle) continue;
    if (vehicle.odometerKm === null) vehicle.odometerKm = kmRow.km;
    vehicle.lastKmDate = kmRow.date;
    if (!vehicle.car) vehicle.car = kmRow.car;
  }

  for (const row of serviceRows) {
    const seed = baseVehicle({
      license_plate: firstValue(row.vehicle_plate, row.license_plate, row.plate),
      car: firstValue(row.car, row.vehicle_model, row.vehicle)
    });
    const vehicle = ensureVehicle(vehicles, seed);
    if (!vehicle) continue;
    applyService(vehicle, row);
  }

  for (const row of latestLiveRows(liveRows)) {
    const seed = baseVehicle({
      license_plate: firstValue(row.license_plate, row.vehicle_plate, row.plate),
      car: firstValue(row.car, row.vehicle_model, row.vehicle)
    });
    const vehicle = ensureVehicle(vehicles, seed);
    if (!vehicle) continue;
    applyLive(vehicle, row);
  }

  return Array.from(vehicles.values())
    .map((vehicle) => finalizeVehicle(vehicle, targetDate))
    .sort((a, b) => `${a.warehouse} ${a.plate || a.car}`.localeCompare(`${b.warehouse} ${b.plate || b.car}`, "hu"));
}

export async function onRequestGet({ request, env }) {
  try {
    if (!isAuthorized(request, env)) return json({ error: "Unauthorized" }, 401);

    const url = new URL(request.url);
    const targetDate = isoDate(url.searchParams.get("date"));
    const fromDate = addDays(targetDate, -45);
    const toDate = addDays(targetDate, 21);

    const liveFrom = `${targetDate}T00:00:00Z`;
    const liveTo = `${addDays(targetDate, 1)}T23:59:59Z`;

    const [assignments, stories, services, liveRaw, liveKm] = await Promise.all([
      readSupabase(
        env,
        TABLES.assignments,
        [["work_date", `gte.${fromDate}`], ["work_date", `lte.${toDate}`]],
        "work_date.asc,driver_name.asc,shift_start.asc",
        15000
      ),
      readSupabase(
        env,
        TABLES.stories,
        [["work_date", `gte.${fromDate}`], ["work_date", `lte.${targetDate}`], ["vehicle_plate", "not.is.null"]],
        "work_date.desc,updated_at.desc",
        15000
      ),
      readSupabase(env, TABLES.service, [], "vehicle_plate.asc", 5000),
      readFirstAvailable(
        env,
        TABLES.liveRawCandidates,
        [["fetched_at", `gte.${liveFrom}`], ["fetched_at", `lte.${liveTo}`]],
        "fetched_at.desc",
        10000
      ),
      readFirstAvailable(
        env,
        TABLES.liveKmCandidates,
        [["last_seen_at", `gte.${liveFrom}`], ["last_seen_at", `lte.${liveTo}`]],
        "last_seen_at.desc",
        10000
      )
    ]);

    const liveRows = [...liveRaw.rows, ...liveKm.rows];
    const vehicles = buildVehicles(targetDate, assignments, stories, services, liveRows);
    const totals = {
      vehicles: vehicles.length,
      assigned: vehicles.filter((vehicle) => vehicle.status === "Kiosztva").length,
      planned: vehicles.filter((vehicle) => vehicle.status === "Tervezve").length,
      free: vehicles.filter((vehicle) => vehicle.status === "Szabad").length,
      serviceDue: vehicles.filter((vehicle) => vehicle.status === "Szerviz esedékes").length,
      warehouses: Array.from(new Set(vehicles.map((vehicle) => vehicle.warehouse).filter(Boolean))).length
    };

    return json({
      generatedAt: new Date().toISOString(),
      targetDate,
      source: {
        assignments: assignments.length,
        routeStories: stories.length,
        serviceRows: services.length,
        liveRows: liveRows.length,
        liveRawTable: liveRaw.table,
        liveKmTable: liveKm.table
      },
      totals,
      vehicles
    });
  } catch (error) {
    return json({ error: error.message || String(error) }, 500);
  }
}
