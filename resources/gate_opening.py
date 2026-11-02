"""Server-only Twilio gate calls; never automatically retry a chargeable request."""
import re
import threading
import time


class GateOpeningError(Exception):
    def __init__(self, status_code, message):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def twilio_client(sid, token):
    from twilio.rest import Client
    from twilio.http.http_client import TwilioHttpClient
    return Client(sid, token, http_client=TwilioHttpClient(timeout=20, max_retries=0))


class GateOpeningService:
    COOLDOWN = 60

    def __init__(self, setting, client_factory=twilio_client, clock=time.monotonic):
        self.setting, self.client_factory, self.clock = setting, client_factory, clock
        self.lock = threading.Lock()
        self.requests = {}
        self.last_started = None

    def settings(self):
        return {
            "sid": self.setting("TWILIO_ACCOUNT_SID"),
            "token": self.setting("TWILIO_AUTH_TOKEN"),
            "to": self.setting("TWILIO_GATE_TO") or "+36501213800",
            "from": self.setting("TWILIO_GATE_FROM") or "+4915888623971",
            "url": self.setting("TWILIO_GATE_TWIML_URL") or "https://webhooks.twilio.com/v1/Voice/Template/voice_speech_recognition",
        }

    def configuration(self):
        cfg = self.settings()
        configured = bool(re.fullmatch(r"AC[0-9a-fA-F]{32}", cfg["sid"]) and cfg["token"]
                          and all(re.fullmatch(r"\+[1-9]\d{7,14}", cfg[k]) for k in ("to", "from"))
                          and cfg["url"].startswith("https://"))
        with self.lock:
            remaining = max(0, self.COOLDOWN - (self.clock() - self.last_started)) if self.last_started is not None else 0
        return {"configured": configured, "cooldownSeconds": int(remaining + .999)}

    def open(self, request_id, owner):
        if not self.configuration()["configured"]:
            raise GateOpeningError(503, "A Twilio kapunyitás még nincs megfelelően beállítva. Kérjük, ellenőrizd a szerver beállításait.")
        now = self.clock()
        with self.lock:
            self.requests = {key: value for key, value in self.requests.items() if now - value["time"] < 3600}
            previous = self.requests.get(request_id)
            if previous:
                if previous["owner"] != owner:
                    raise GateOpeningError(409, "Ez a kérésazonosító már használatban van.")
                if previous.get("result"):
                    return previous["result"]
                raise GateOpeningError(409, "Ezt a híváskérést már elküldtük. Ellenőrizd a Twilio hívásnaplót; automatikusan nem ismételjük meg.")
            if self.last_started is not None and now - self.last_started < self.COOLDOWN:
                raise GateOpeningError(429, "Kapunyitást legfeljebb percenként lehet indítani. Kérjük, várj egy kicsit.")
            self.requests[request_id] = record = {"time": now, "owner": owner}
            self.last_started = now
        cfg = self.settings()
        try:
            call = self.client_factory(cfg["sid"], cfg["token"]).calls.create(
                url=cfg["url"], to=cfg["to"], from_=cfg["from"], timeout=20)
            if not getattr(call, "sid", None) or getattr(call, "status", "") in {"failed", "canceled", "busy", "no-answer"}:
                raise ValueError("Call was not accepted")
            result = {"ok": True, "callSid": call.sid, "status": str(call.status),
                      "message": "A kapunyitó híváskérést a Twilio fogadta.", "cooldownSeconds": self.COOLDOWN}
        except ImportError:
            raise GateOpeningError(503, "A Twilio csomag nincs telepítve a szerveren.") from None
        except Exception:
            raise GateOpeningError(502, "A hívás indítását nem sikerült visszaigazolni. Újrapróbálás előtt ellenőrizd a Twilio hívásnaplót.") from None
        with self.lock:
            record["result"] = result
        return result
