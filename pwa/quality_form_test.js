// Test-only preview: no approval, API request, or complaint state change.
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
