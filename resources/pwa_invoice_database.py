"""One explicitly closed public-schema HTTP client per invoice operation.

Supabase.schema() creates a new PostgREST HTTP client on each call in supported
SDK versions. Do not use it repeatedly for a sheet-by-sheet comparison.
"""
from contextlib import contextmanager


class PublicInvoiceDatabase:
    def __init__(self, rest):
        self.rest = rest

    def schema(self, name):
        if name != "public":
            raise ValueError("The isolated invoice store uses only the public schema.")
        return self.rest


@contextmanager
def invoice_database(url, service_key):
    from postgrest import SyncPostgrestClient
    if not url or not service_key:
        from resources.pwa_invoice_raw import RawImportError
        raise RawImportError("Hiányzik az elkülönített Excel-tároló adatbázis-beállítása.", 503)
    # Own this client for the operation. __exit__ closes it even after a failed
    # query; no auth/realtime/storage clients or extra TLS pools are created.
    with SyncPostgrestClient(
        url.rstrip("/") + "/rest/v1", schema="public", timeout=30,
        headers={"apikey": service_key, "Authorization": f"Bearer {service_key}"},
    ) as rest:
        yield PublicInvoiceDatabase(rest)
