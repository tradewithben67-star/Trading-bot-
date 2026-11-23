"""Nutzer, Passwörter und Anmeldung.

Zwei Rollen:

* **inhaber** — keine Grenzen, darf trainieren und Nutzer verwalten.
  Der erste Nutzer, der angelegt wird, ist immer der Inhaber.
* **kunde** — hat ein Abo und damit Grenzen je Modell.

Passwörter werden nie gespeichert, nur ein PBKDF2-Hash mit eigenem Salz.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .konto import ABOS

RUNDEN = 200_000
_NAME = re.compile(r"^[\wÄÖÜäöüß.\- ]{2,32}$")


def hash_bilden(passwort: str, salz: bytes | None = None) -> str:
    salz = salz or os.urandom(16)
    h = hashlib.pbkdf2_hmac("sha256", passwort.encode(), salz, RUNDEN)
    return f"pbkdf2${RUNDEN}${salz.hex()}${h.hex()}"


def hash_pruefen(passwort: str, gespeichert: str) -> bool:
    try:
        _, runden, salz, h = gespeichert.split("$")
    except ValueError:
        return False
    neu = hashlib.pbkdf2_hmac("sha256", passwort.encode(), bytes.fromhex(salz), int(runden))
    return hmac.compare_digest(neu.hex(), h)


def _oeffentlich(n: dict) -> dict:
    return {k: v for k, v in n.items() if k != "hash"}


class Nutzerliste:
    def __init__(self, pfad: str | Path) -> None:
        self.pfad = Path(pfad)
        self._sperre = threading.Lock()
        self._d: list[dict] = (json.loads(self.pfad.read_text(encoding="utf-8"))
                               if self.pfad.exists() else [])

    def _sichern(self) -> None:
        self.pfad.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.pfad.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._d, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.pfad)

    def leer(self) -> bool:
        with self._sperre:
            return not self._d

    def anlegen(self, name: str, passwort: str, abo: str = "start") -> dict:
        name = (name or "").strip()
        if not _NAME.match(name):
            raise ValueError("Name: 2 bis 32 Zeichen, Buchstaben, Zahlen, Punkt, Strich.")
        if len(passwort or "") < 8:
            raise ValueError("Das Passwort braucht mindestens 8 Zeichen.")
        if abo not in ABOS:
            raise ValueError(f"Unbekanntes Abo: {abo}. Möglich: {', '.join(ABOS)}")
        with self._sperre:
            if any(n["name"].lower() == name.lower() for n in self._d):
                raise ValueError(f"Den Namen {name} gibt es schon.")
            n = {
                "id": uuid.uuid4().hex[:12],
                "name": name,
                "rolle": "kunde" if self._d else "inhaber",
                "abo": abo,
                "erstellt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "hash": hash_bilden(passwort),
            }
            self._d.append(n)
            self._sichern()
            return _oeffentlich(n)

    def pruefen(self, name: str, passwort: str) -> dict | None:
        with self._sperre:
            n = next((n for n in self._d if n["name"].lower() == (name or "").strip().lower()), None)
        if n is None:
            hash_pruefen(passwort or "", hash_bilden("x"))   # gleich lang rechnen
            return None
        return _oeffentlich(n) if hash_pruefen(passwort or "", n["hash"]) else None

    def holen(self, nid: str) -> dict | None:
        with self._sperre:
            n = next((n for n in self._d if n["id"] == nid), None)
            return _oeffentlich(n) if n else None

    def liste(self) -> list[dict]:
        with self._sperre:
            return [_oeffentlich(n) for n in self._d]

    def _aendern(self, nid: str, **felder) -> dict:
        with self._sperre:
            n = next((n for n in self._d if n["id"] == nid), None)
            if n is None:
                raise ValueError("Nutzer nicht gefunden.")
            n.update(felder)
            self._sichern()
            return _oeffentlich(n)

    def abo_setzen(self, nid: str, abo: str) -> dict:
        if abo not in ABOS:
            raise ValueError(f"Unbekanntes Abo: {abo}. Möglich: {', '.join(ABOS)}")
        return self._aendern(nid, abo=abo)

    def passwort_setzen(self, nid: str, passwort: str) -> dict:
        if len(passwort or "") < 8:
            raise ValueError("Das Passwort braucht mindestens 8 Zeichen.")
        return self._aendern(nid, hash=hash_bilden(passwort))

    def loeschen(self, nid: str) -> None:
        with self._sperre:
            n = next((n for n in self._d if n["id"] == nid), None)
            if n is None:
                raise ValueError("Nutzer nicht gefunden.")
            if n["rolle"] == "inhaber":
                raise ValueError("Der Inhaber kann nicht gelöscht werden.")
            self._d.remove(n)
            self._sichern()


class Sitzungen:
    """Wer gerade angemeldet ist. Nur im Speicher: nach einem Neustart neu anmelden."""

    DAUER = 30 * 24 * 3600

    def __init__(self) -> None:
        self._d: dict[str, tuple[str, float]] = {}
        self._fehler: dict[str, tuple[int, float]] = {}
        self._sperre = threading.Lock()

    def neu(self, nid: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._sperre:
            self._d[token] = (nid, time.time() + self.DAUER)
        return token

    def wer(self, token: str | None) -> str | None:
        if not token:
            return None
        with self._sperre:
            e = self._d.get(token)
            if e is None or e[1] < time.time():
                self._d.pop(token, None)
                return None
            return e[0]

    def beenden(self, token: str | None) -> None:
        with self._sperre:
            self._d.pop(token or "", None)

    def alle_beenden(self, nid: str) -> None:
        with self._sperre:
            for t in [t for t, (n, _) in self._d.items() if n == nid]:
                del self._d[t]

    # Bremse gegen Passwort-Raten: nach 5 Fehlversuchen 60 s Pause je Name.
    def gesperrt(self, name: str) -> bool:
        with self._sperre:
            anzahl, bis = self._fehler.get(name.lower(), (0, 0.0))
            return anzahl >= 5 and bis > time.time()

    def fehlversuch(self, name: str) -> None:
        with self._sperre:
            anzahl, bis = self._fehler.get(name.lower(), (0, 0.0))
            if bis and bis < time.time():
                anzahl = 0
            self._fehler[name.lower()] = (anzahl + 1, time.time() + 60)

    def erfolg(self, name: str) -> None:
        with self._sperre:
            self._fehler.pop(name.lower(), None)
