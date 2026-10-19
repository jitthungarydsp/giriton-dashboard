"""Reuse database HTTP connections without sharing mutable sessions across threads."""
from threading import local

import requests


_sessions = local()
_adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=32, max_retries=0)


def database_http_session():
    session = getattr(_sessions, "session", None)
    if session is None:
        session = requests.Session()
        # The adapter owns the connection pool. Sessions keep headers/cookies
        # isolated, while short-lived executor threads reuse that same pool.
        session.mount("https://", _adapter)
        session.mount("http://", _adapter)
        _sessions.session = session
    return session


def database_http_request(method, url, **kwargs):
    return database_http_session().request(method, url, **kwargs)
