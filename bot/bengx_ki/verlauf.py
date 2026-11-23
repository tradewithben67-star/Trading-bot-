"""Die Historie: alles, was die KI je getan hat, eine Zeile pro Ereignis.

Gespeichert als JSON-Lines (`ki/verlauf.jsonl`): jede Zeile ein Eintrag,
nur angehängt, nie umgeschrieben. So geht auch bei einem Absturz höchstens
die letzte Zeile verloren.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


class Verlauf:
    def __init__(self, pfad: str | Path) -> None:
        self.pfad = Path(pfad)
        self._sperre = threading.Lock()

    def eintragen(self, bereich: str, titel: str, daten: dict, tokens: int = 0) -> dict:
        e = {
            "id": uuid.uuid4().hex[:12],
            "zeit": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "bereich": bereich,
            "titel": titel,
            "tokens": tokens,
            "daten": daten,
        }
        with self._sperre:
            self.pfad.parent.mkdir(parents=True, exist_ok=True)
            with self.pfad.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        return e

    def _alle(self) -> list[dict]:
        if not self.pfad.exists():
            return []
        raus = []
        with self.pfad.open(encoding="utf-8") as fh:
            for zeile in fh:
                try:
                    raus.append(json.loads(zeile))
                except json.JSONDecodeError:
                    continue            # halb geschriebene letzte Zeile
        return raus

    def liste(self, bereich: str | None = None, anzahl: int = 500) -> list[dict]:
        """Neueste zuerst, ohne die großen Detaildaten."""
        with self._sperre:
            alle = self._alle()
        if bereich:
            alle = [e for e in alle if e["bereich"] == bereich]
        return [{k: v for k, v in e.items() if k != "daten"}
                | {"kurz": e["daten"].get("kurz", "")}
                for e in reversed(alle[-anzahl:])]

    def holen(self, eid: str) -> dict | None:
        with self._sperre:
            for e in self._alle():
                if e["id"] == eid:
                    return e
        return None

    def letzter(self, bereich: str) -> dict | None:
        with self._sperre:
            for e in reversed(self._alle()):
                if e["bereich"] == bereich:
                    return e
        return None

    def zaehlen(self) -> dict[str, int]:
        with self._sperre:
            alle = self._alle()
        z: dict[str, int] = {}
        for e in alle:
            z[e["bereich"]] = z.get(e["bereich"], 0) + 1
        return z
