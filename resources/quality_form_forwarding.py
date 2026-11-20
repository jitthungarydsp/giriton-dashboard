"""Validated, immutable payloads for the Kifli complaint form. No browser credentials here."""
from datetime import date

FORM_URL = 'https://docs.google.com/forms/d/e/1FAIpQLSdizw4bsOc0bEgapo8qXcrsV6ui2Nsjaois0YSpHynTFe3NsQ/viewform'
CATEGORIES = {
    'Túra alatti késés': ('Túra alatti késés / Route delay', 238065601, 641973316, 846736866),
    'Futárbüntetés': ('Futár büntetés / Courier penalty', 1021385934, 681385102, 194924023),
    'Pénztárca/tankolás': ('Pénztárca, tankolás / Wallet, refuel', 299427093, 443981510, 1410602956),
    'Elszámolás': ('Elszámolás / Invoice', 1042152329, 851097138, 476241842),
    'Jármű': ('Jármű / Vehicle', None, None, 134600445),
    'Műszak': ('Műszak / Shift', 1192314507, 1563649714, 506940950),
}


def build_payload(complaint, category='', route_id='', license_plate='', *, description=None, draft=False):
    items = complaint.get('affected_items') or []
    category = category or next((row.get('category') for row in items if row.get('category')), '')
    category = category or ('Műszak' if complaint.get('topic') in {'lateShift', 'noShow'} else 'Túra alatti késés')
    if category not in CATEGORIES:
        raise ValueError('Válassz érvényes reklamációkategóriát.')
    dates = sorted({date.fromisoformat(str(row.get('date') or '')).isoformat() for row in items})
    if len(dates) != 1:
        raise ValueError('Egy beküldés egy naphoz tartozhat.')
    courier_id, name = str(complaint.get('courier_id') or '').strip(), str(complaint.get('courier_name') or '').strip()
    if not courier_id or not name:
        raise ValueError('Hiányzik a futár neve vagy azonosítója.')
    routes = list(dict.fromkeys(str(row.get('routeId') or '').strip() for row in items if str(row.get('routeId') or '').strip()))
    route_id = route_id.strip() or ', '.join(routes)
    if complaint.get('topic') in {'cleanedTimeWindowLate', 'uncleanedTimeWindowLate'}:
        if len(routes) != 1 or any(not str(row.get('routeId') or '').strip() for row in items):
            raise ValueError('A reklamációhoz pontosan egy Route ID szükséges. A több túrás régi ügyet előbb külön kell rendezni.')
        if route_id != routes[0]:
            raise ValueError('A továbbítás Route ID-ja nem térhet el a reklamációhoz mentett túrától.')
        if any(char.isspace() or char in ',;' for char in route_id):
            raise ValueError('Pontosan egy Route ID adható meg, elválasztó nélkül.')
    if not draft and category == 'Túra alatti késés' and not route_id:
        raise ValueError('Túra alatti késéshez túraszám vagy Cargo ID szükséges.')
    license_plate = license_plate.strip().upper()
    if not draft and category == 'Jármű' and not license_plate:
        raise ValueError('Járműpanaszhoz rendszám szükséges.')
    message = str(complaint.get('message') or '').strip()
    if len(message) < 5:
        raise ValueError('Hiányzó reklamációindoklás.')
    if description is None:
        description = f"JITT reklamáció: {complaint['id']}\nDátum: {dates[0]}\nFutár: {name} (#{courier_id})\nRoute ID: {route_id or 'Nincs megadva'}\n\n{message}"
        for row in items:
            description += f"\n{row.get('label', '')} · {row.get('note', '')}"
    else:
        description = description.strip()
        if len(description) < 5:
            raise ValueError('Legalább 5 karakteres továbbítási szöveg szükséges.')
    return dict(complaint_id=str(complaint['id']), category=category, courier_id=courier_id,
                courier_name=name, work_date=dates[0], route_id=route_id, license_plate=license_plate,
                description=description, attachment_count=len(complaint.get('attachments') or []))


def answers(payload):
    label, courier_item, name_item, description_item = CATEGORIES[payload['category']]
    fields = {description_item: payload['description']}
    if courier_item:
        fields.update({courier_item: payload['courier_id'], name_item: payload['courier_name']})
    if payload['category'] == 'Túra alatti késés':
        fields[1693548540] = payload['route_id']
    if payload['category'] == 'Jármű':
        fields[792409908] = payload['license_plate']
    return label, fields
