"""Read verified partner decisions from the archived mail; never write finances."""
from datetime import datetime
from email.utils import parseaddr
import re
import unicodedata


UUID_PATTERN = r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}'
CASE_ID = re.compile(r'(?:JITT\s+reklam[áa]ci[óo]\s*:\s*|\[JITT:)(' + UUID_PATTERN + r')', re.I)
REFERENCE = re.compile(r'(?im)^\s*Panasz\s+azonos[íi]t[óo]\s*:\s*(P-\d{6}-\d+)\s*$')
DECISION = re.compile(r'(?im)^\s*D[öo]nt[ée]s\s*:\s*([^\r\n]+)')
OUTCOMES = {'elfogadva': 'accepted', 'elutasitva': 'rejected', 'reszben elfogadva': 'partially_accepted'}


def folded(value):
    return ''.join(c for c in unicodedata.normalize('NFD', str(value or '')) if not unicodedata.combining(c)).strip().casefold()


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (ValueError, TypeError, OverflowError):
        return None


def parse_decision(row):
    if parseaddr(str(row.get('sender') or ''))[1].casefold() != 'noreply@appsheet.com':
        return None
    subject, body = str(row.get('subject') or ''), str(row.get('body_text') or '')
    if not re.match(r'^Panasz\s+elb[íi]r[áa]lva\s*:', subject, re.I):
        return None
    decision_matches = list(DECISION.finditer(body))
    outcomes = {OUTCOMES.get(folded(match[1])) for match in decision_matches}
    if len(outcomes) != 1 or None in outcomes:
        return None
    outcome = next(iter(outcomes))
    subject_outcome = OUTCOMES.get(folded(re.split(r'\s+[-–]\s+', subject)[-1]))
    if subject_outcome and subject_outcome != outcome:
        return None
    case_ids = {value.lower() for value in CASE_ID.findall(subject + '\n' + body)}
    if len(case_ids) > 1:
        return None
    references = set(REFERENCE.findall(body))
    if len(references) > 1:
        return None
    courier_ids = set(re.findall(r'(?im)^Fut[áa]r\s*:[^\r\n]*\(\s*#?(\d{3,8})\s*\)', body))
    if len(courier_ids) > 1 or courier_ids and str(row.get('courier_id') or '') not in courier_ids:
        return None
    at = timestamp(row.get('received_at'))
    if at is None:
        return None
    # Only the explicit decision reason is shared, never the mailbox or full mail.
    reason = re.search(r'(?ims)^Indokl[áa]s\s*:\s*(.*?)(?=^\s*(?:K[ée]rj[üu]k\b|[ÜU]dv[öo]zlettel\b|Sent from\b)|\Z)', body[decision_matches[-1].end():])
    reason_text = reason[1].strip()[:5000] if reason else ''
    return {'status': outcome, 'reason': reason_text, 'respondedAt': row['received_at'],
            'reference': next(iter(references), ''), '_caseId': next(iter(case_ids), ''),
            '_courierId': str(row.get('courier_id') or ''), '_at': at}


def attach_partner_decisions(rest, complaints, courier_id=None):
    if not complaints:
        return
    groups = {}
    for item in complaints:
        item.pop('partnerDecision', None)
        item.pop('partnerDecisionWarning', None)
        if courier_id is not None and item.get('courier_id') is not None and str(item['courier_id']) != str(courier_id):
            continue
        cid = str(courier_id if courier_id is not None else item.get('courier_id') or '')
        if cid and re.fullmatch(UUID_PATTERN, str(item.get('id') or ''), re.I):
            groups.setdefault(cid, []).append(item)
    eligible = [(cid, item) for cid, items in groups.items() if cid.isdecimal() for item in items]
    decisions = []
    references = {}
    for cid, item in eligible:
        reference = str(item.get('forwarding_reference') or '')
        if reference:
            references.setdefault((cid, reference), set()).add(str(item['id']).lower())
    # Batch all couriers together to avoid a separate HTTP request per courier.
    for offset in range(0, len(eligible), 15):
        batch = eligible[offset:offset + 15]
        courier_ids = sorted({cid for cid, _ in batch})
        terms = []
        for _, item in batch:
            terms += ['body_text.ilike.*' + item['id'] + '*', 'subject.ilike.*' + item['id'] + '*']
            reference = str(item.get('forwarding_reference') or '')
            if re.fullmatch(r'P-\d{6}-\d+', reference):
                terms.append('body_text.ilike.*' + reference + '*')
        page_offset = 0
        while True:
            rows = rest('GET', 'complaint_email_responses', params={
                'select': 'subject,sender,body_text,courier_id,received_at',
                'courier_id': 'eq.' + courier_ids[0] if len(courier_ids) == 1 else 'in.(' + ','.join(courier_ids) + ')',
                'or': '(' + ','.join(terms) + ')',
                'order': 'received_at.desc,mailbox.asc,gmail_id.asc', 'limit': '100', 'offset': str(page_offset)}) or []
            decisions.extend(value for row in rows if str(row.get('courier_id')) in courier_ids and (value := parse_decision(row)))
            if len(rows) < 100:
                break
            page_offset += 100
            if page_offset >= 10000:
                raise RuntimeError('A Kifli-válaszok teljes listája nem ellenőrizhető.')
    for cid, items in groups.items():
        for item in items:
            created_at = timestamp(item.get('created_at'))
            matches = [value for value in decisions if value['_courierId'] == cid and
                       (value['_caseId'] == str(item['id']).lower() or not value['_caseId'] and value['reference'] and value['reference'] == item.get('forwarding_reference') and len(references.get((cid, value['reference']), set())) == 1) and
                       (created_at is None or value['_at'] >= created_at)]
            if not matches:
                continue
            latest = max(value['_at'] for value in matches)
            newest = [value for value in matches if value['_at'] == latest]
            if len({value['status'] for value in newest}) > 1:
                item['partnerDecisionWarning'] = 'Azonos időpontú, eltérő Kifli-döntések ellenőrizendők.'
                continue
            item['partnerDecision'] = {key: value for key, value in newest[0].items() if not key.startswith('_')}
