"""Export selected route-detail columns, always including the route identifier."""
from datetime import datetime
from zoneinfo import ZoneInfo

# Same keys and headers as ROUTE_REPORT_FIELDS in pwa/app.js.
COLUMNS = {'routeId': ('Route ID', 'routeId'),
 'date': ('Munkanap', 'date'),
 'courierId': ('Futár ID', 'courierId'),
 'courierName': ('Futár neve', 'courierName'),
 'warehouse': ('Raktár', 'warehouse'),
 'warehouseAddress': ('Raktár cím', 'warehouseAddress'),
 'shiftName': ('Műszak', 'shiftName'),
 'shiftStart': ('Műszak kezdés', 'shiftStartAt'),
 'shiftEnd': ('Műszak vége', 'shiftEndAt'),
 'shiftAvailable': ('Elérhető', 'shiftAvailableAt'),
 'queueStarted': ('Sorbaállt', 'queueStartedAt'),
 'actualShiftStart': ('Tényleges kezdés', 'actualShiftStartAt'),
 'routeAssigned': ('Túrát kapott', 'routeAssignedAt'),
 'plannedDeparture': ('Tervezett indulás', 'plannedDepartureAt'),
 'departed': ('Indulás', 'departedAt'),
 'plannedReturn': ('Tervezett vissza', 'plannedReturnAt'),
 'returned': ('Visszaérkezés', 'returnedAt'),
 'routeType': ('Túratípus', 'routeTypeLabel'),
 'orders': ('Címek', 'orders'),
 'stops': ('Stopok', 'stops'),
 'waiting': ('Várakozás', 'waitingMinutes'),
 'plannedLoading': ('Terv bepakolás', 'plannedLoadingMinutes'),
 'loading': ('Bepakolás', 'loadingMinutes'),
 'plannedRouteTime': ('Terv túraidő', 'plannedRouteMinutes'),
 'routeTime': ('Túra bepakolás nélkül', 'routeMinutes'),
 'fullTime': ('Túra bepakolással', 'totalMinutes'),
 'over5h': ('5h+', 'totalMinutes'),
 'delay': ('Késés', 'routeDelayCount'),
 'delayMinutes': ('Késés perc', 'routeDelayMinutes'),
 'plannedKm': ('Tervezett km', 'hubPlannedKm'),
 'hubMileageKm': ('Hub km', 'hubMileageKm'),
 'actualKm': ('Tényleges km', 'actualKm'),
 'googleRouteKm': ('Google km', 'googleRouteKm'),
 'distance': ('Számolt km', ''),
 'distanceDelta': ('Km eltérés', 'distanceDeltaKm'),
 'distanceSource': ('Km forrás', 'distanceSource'),
 'nextShift': ('Következő műszak', 'nextShiftSameDay'),
 'vehiclePlate': ('Rendszám', 'vehiclePlate'),
 'vehicleModel': ('Autó', 'vehicleModel'),
 'kifliVehicle': ('Kiflis autó', 'kifliVehicle'),
 'tip': ('Borravaló', 'tipHuf'),
 'tipSource': ('Tip forrás', 'tipSource'),
 'dataSource': ('Forrás', 'dataSource'),
 'narrative': ('Összefoglaló', 'narrative')}


def selected_columns(value):
    keys = value.split(',')
    if not keys or any(key not in COLUMNS for key in keys) or len(keys) != len(set(keys)):
        raise ValueError('Érvénytelen vagy ismétlődő riportoszlop.')
    if 'routeId' not in keys:
        keys.insert(0, 'routeId')
    return keys


def export_value(row, key):
    prop = COLUMNS[key][1]
    value = row.get(prop)
    if key == 'distance':
        value = row.get('calculatedRouteKm')
        if value is None:
            value = (row.get('routeDistance') or {}).get('distanceKm')
    elif key == 'distanceSource':
        value = row.get('distanceSource') or row.get('distanceStatus')
    elif key == 'vehicleModel':
        value = row.get('vehicleModel') or row.get('vehicleLabel')
    elif key == 'over5h':
        return 'Igen' if float(row.get('totalMinutes') or row.get('routeMinutes') or 0) > 300 else 'Nem'
    if key in {'shiftStart','shiftEnd','shiftAvailable','queueStarted','actualShiftStart','routeAssigned','plannedDeparture','departed','plannedReturn','returned'} and value:
        try:
            stamp = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
            if stamp.tzinfo:
                stamp = stamp.astimezone(ZoneInfo('Europe/Budapest'))
            return stamp.strftime('%m. %d. %H:%M')
        except ValueError:
            return str(value)
    if key in {'plannedRouteTime','routeTime','fullTime'} and value is not None:
        minutes = round(float(value))
        return f'{minutes // 60}:{minutes % 60:02d}'
    # Keep numbers numeric in Excel, but never interpret source text as formulas.
    if isinstance(value, str) and value.startswith(('=', '+', '-', '@')):
        return "'" + value
    return value


def populate_selected_sheet(sheet, rows, columns):
    keys = selected_columns(columns)
    sheet.append([COLUMNS[key][0] for key in keys])
    for row in rows:
        sheet.append([export_value(row, key) for key in keys])
