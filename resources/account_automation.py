"""Queue processing without importing the Streamlit application or changing passwords."""
import hashlib
import secrets
from urllib.parse import urlsplit


def enabled():
    from resources.email_sender import get_setting
    return get_setting('PWA_ACCOUNT_AUTOMATION_ENABLED').lower() == 'true'


def rpc(name, payload=None):
    from resources.pwa_users_db import _request
    result = _request('POST', 'rpc/' + name, payload=payload or {})
    # PostgREST returns JSON null for the successful RETURNS void finish RPC.
    if result is None and name != 'pwa_auth_finish':
        raise RuntimeError('Az automatikus fiókkezelés DB-migrációja nem érhető el.')
    return result


def enqueue(kind, request_id, actor='admin'):
    return rpc('pwa_auth_enqueue', {'p_kind': kind, 'p_request_id': int(request_id), 'p_actor': actor})


def dispatch_pending(job, request=None, dispatch=None):
    """Claim one immediate dispatch per queued job; the schedule is the fallback."""
    if job.get('state') != 'queued':
        return {**job, 'dispatch': 'not_queued'}
    if request is None:
        from resources.pwa_users_db import _request
        request = _request
    if dispatch is None:
        from resources.github_actions import dispatch_workflow
        dispatch = dispatch_workflow
    try:
        claimed = request('PATCH', 'pwa_account_jobs', params={
            'id': 'eq.' + str(job['id']), 'state': 'eq.queued', 'note': 'eq.'},
            payload={'note': 'GitHub-job indítása kérve.'}, prefer='return=representation')
        if not claimed:
            return {**job, 'dispatch': 'already_requested'}
        dispatch('pwa-account-automation.yml', inputs={'enqueue_existing': 'false'})
        return {**job, 'dispatch': 'accepted'}
    except Exception:
        # The request and DB queue remain valid; never expose provider secrets/errors.
        return {**job, 'dispatch': 'scheduled_fallback'}


def queue_and_dispatch(kind, request_id, actor='automatic'):
    if not enabled():
        return {'dispatch': 'disabled'}
    return dispatch_pending(enqueue(kind, request_id, actor))


def public_url(value):
    parsed = urlsplit(str(value).strip())
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('PWA_PUBLIC_URL: érvényes HTTPS alkalmazáscím szükséges, útvonal nélkül.')
    if parsed.hostname.endswith('.example.com'):
        raise ValueError('A PWA_PUBLIC_URL nem lehet mintacím.')
    return str(value).strip().rstrip('/')


def process_one(call, send, base_url):
    base_url = public_url(base_url)
    jobs = call('pwa_auth_claim', {})
    if not jobs:
        return 'idle'
    job = jobs[0]
    token = secrets.token_urlsafe(32)
    prepared = call('pwa_auth_prepare', {'p_job': job['id'], 'p_hash': hashlib.sha256(token.encode()).hexdigest()})
    if not prepared.get('ready'):
        return 'manual'
    # Only the hash is stored. The token stays in memory and in the recipient's email.
    link = base_url + '/#set-password=' + token
    text = (f"Kedves {prepared['username']}!\n\n"
            f"Felhasználóneved: {prepared['username']}\n"
            f"Az alábbi egyszer használható hivatkozáson állíthatod be a jelszavad:\n{link}\n\n"
            "A link 30 percig érvényes. A meglévő jelszavad a sikeres beállításig változatlan.\n"
            "Ha nem te kérted, ne használd a linket.\n\nJittFutár")
    try:
        send(prepared['email'], 'JittFutár – jelszó beállítása', text)
    except Exception:
        call('pwa_auth_finish', {'p_job': job['id'], 'p_sent': False})
        return 'uncertain'
    # A missing acknowledgement must not cause another email or a password reset.
    call('pwa_auth_finish', {'p_job': job['id'], 'p_sent': True})
    return 'sent'
