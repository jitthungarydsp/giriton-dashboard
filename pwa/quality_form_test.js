// Browser-only form preparation. Never submits or changes complaint state.
function qualityComplaintFormUrl(item, category, routeId = "", licensePlate = "") {
  const categories = {
    "Túra alatti késés": ["Túra alatti késés / Route delay", 1629541155, 139333198, 1757898114],
    "Futárbüntetés": ["Futár büntetés / Courier penalty", 229683135, 2026925449, 727698089],
    "Pénztárca/tankolás": ["Pénztárca, tankolás / Wallet, refuel", 1148502456, 1198182622, 688354749],
    "Elszámolás": ["Elszámolás / Invoice", 1609979400, 275666129, 949548968],
    "Jármű": ["Jármű / Vehicle", null, null, 179972591],
    "Műszak": ["Műszak / Shift", 871178890, 1494998302, 2121626944]
  };
  if (!Object.hasOwn(categories, category)) throw new Error("Válassz érvényes kategóriát.");
  const name = String(item.courier_name || "").trim();
  const courierId = String(item.courier_id || "").trim();
  const message = String(item.message || "").trim();
  if (!name || !courierId || message.length < 5) throw new Error("Hiányos futáradatok vagy indoklás.");
  routeId = routeId.trim(); licensePlate = licensePlate.trim().toUpperCase();
  if (category === "Túra alatti késés" && !routeId) throw new Error("Add meg a túraszámot / Cargo ID-t.");
  if (category === "Jármű" && !licensePlate) throw new Error("Add meg a rendszámot.");
  const items = item.affected_items || [];
  const dates = [...new Set(items.map(row => row.date).filter(Boolean))];
  if (dates.length !== 1) throw new Error("Egy űrlap egy érintett naphoz tartozhat.");
  const description = [`JITT reklamáció: ${item.id}`, `Dátum: ${dates[0]}`, `Futár: ${name} (#${courierId})`, "", message,
    ...items.map(row => `${row.label || ""} · ${row.note || ""}`)].join("\n");
  const [label, courierEntry, nameEntry, descriptionEntry] = categories[category];
  const url = new URL("https://docs.google.com/forms/d/e/1FAIpQLSdizw4bsOc0bEgapo8qXcrsV6ui2Nsjaois0YSpHynTFe3NsQ/viewform");
  url.searchParams.set("usp", "pp_url");
  const fields = {493012323: "Just in Time Kft.", 608543996: label, [descriptionEntry]: description};
  if (courierEntry) { fields[courierEntry] = courierId; fields[nameEntry] = name; }
  if (category === "Túra alatti késés") fields[584723978] = routeId;
  if (category === "Jármű") fields[1445819589] = licensePlate;
  for (const [entry, value] of Object.entries(fields)) url.searchParams.set(`entry.${entry}`, value);
  return url.href;
}

function qualityFormTestUrl() {
  const url = new URL("https://docs.google.com/forms/d/e/1FAIpQLSdizw4bsOc0bEgapo8qXcrsV6ui2Nsjaois0YSpHynTFe3NsQ/viewform");
  const fields = {
    usp: "pp_url",
    "entry.493012323": "Just in Time Kft.",
    "entry.608543996": "Túra alatti késés / Route delay",
    "entry.1629541155": "999999",
    "entry.139333198": "Teszt Elek – kitalált tesztadat",
    "entry.584723978": "TESZT-0001",
    "entry.1757898114": "TESZT – KITALÁLT ADATOK, NEM VALÓS REKLAMÁCIÓ.\nA tesztútvonalon 15 perces késést szimulálunk egy kitalált közlekedési torlódás miatt. Ez kizárólag a PWA automatikus űrlapkitöltésének ellenőrzésére szolgál. Nem kérünk intézkedést."
  };
  for (const [key, value] of Object.entries(fields)) url.searchParams.set(key, value);
  return url.href;
}

function openQualityFormTest() {
  window.open(qualityFormTestUrl(), "_blank", "noopener,noreferrer");
}
