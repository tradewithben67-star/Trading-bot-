#!/usr/bin/env python3
"""Baut zwischen den zwei Fassungen jeder Seite hin und her.

Im Repository steht die vollstaendige Seite (index.html, konsole.html).
Ein Artifact braucht dieselbe Seite ohne Geruest: kein <!doctype>, kein
<head>, kein <body> - das setzt die Veroeffentlichung selbst davor.

    python3 tools/bauen.py artifact index.html  ZIEL.html   # Geruest abziehen
    python3 tools/bauen.py seite    QUELLE.html index.html  # Geruest anlegen

Ohne das Skript laufen die beiden Fassungen auseinander, und eine
Aenderung landet nur auf einer von beiden.
"""
import sys
import pathlib

KOPF = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="description" content="{beschreibung}">
<meta name="theme-color" content="#000000">
"""

BESCHREIBUNG = {
    "index.html": "BENGX - Ben, 18, aus Deutschland, handelt seit einem Jahr "
                  "ausschliesslich Gold. Signale, Lernbereich und Bots.",
    "konsole.html": "BENGX Bot-Konsole - die drei Bots einstellen: "
                    "Signal-Kopierer, Dauerlaeufer und Swing.",
}


def artifact(text: str) -> str:
    """Vollstaendige Seite -> Artifact-Rumpf."""
    i = text.index("<title>")
    rumpf = text[i:]
    for weg in ("</head>\n<body>\n", "</head>\n<body>", "</head><body>"):
        rumpf = rumpf.replace(weg, "", 1)
    for weg in ("</body>\n</html>\n", "</body>\n</html>", "</body></html>"):
        if rumpf.rstrip().endswith(weg.strip()):
            rumpf = rumpf.rstrip()[: -len(weg.strip())].rstrip() + "\n"
            break
    return rumpf


def seite(text: str, name: str) -> str:
    """Artifact-Rumpf -> vollstaendige Seite."""
    if text.lstrip().startswith("<!doctype"):
        text = artifact(text)
    kopf = KOPF.format(beschreibung=BESCHREIBUNG.get(name, "BENGX"))
    i = text.index("</style>") + len("</style>")
    return kopf + text[:i] + "\n</head>\n<body>" + text[i:].rstrip() + "\n</body>\n</html>\n"


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[1] not in ("artifact", "seite"):
        print(__doc__)
        return 2
    richtung, quelle, ziel = sys.argv[1], pathlib.Path(sys.argv[2]), pathlib.Path(sys.argv[3])
    text = quelle.read_text(encoding="utf-8")
    raus = artifact(text) if richtung == "artifact" else seite(text, ziel.name)
    ziel.write_text(raus, encoding="utf-8")
    print(f"{quelle} -> {ziel}  ({len(raus)} Zeichen)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
