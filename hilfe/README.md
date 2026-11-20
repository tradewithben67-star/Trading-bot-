# Wo hakt's beim Kaufen?

Eine Website rund um **Kaufsucht**. Auf der Startseite steht jeder Problembereich als Karte.
Ein Klick auf eine Karte öffnet Tipps, Hintergründe und Wege zur Beratung.
Dazu kommen Werkzeuge: Selbstcheck, Kassensturz-Rechner, Kauf-Bremse mit Warteliste,
Kauftagebuch und Abo-Check.

Eine Datei (`index.html`), kein Build, keine Abhängigkeiten, keine Cookies, keine Werbung, keine fremden Schriften.

## Karten

| Adresse | Bereich | Karte |
| --- | --- | --- |
| `#laden` | Wo ich kaufe | Ich kaufe im Laden mehr, als ich wollte. |
| `#online` | Wo ich kaufe | Ich bestelle ständig online. |
| `#social` | Wo ich kaufe | Ich kaufe, was ich auf Social Media sehe. |
| `#rabatte` | Wo ich kaufe | Bei Sale und Rabatt kann ich nicht Nein sagen. |
| `#apps` | Wo ich kaufe | Ich gebe Geld in Apps, Spielen und Abos aus. |
| `#gefuehle` | Gefühle & Verhalten | Ich kaufe, wenn es mir schlecht geht. |
| `#heimlich` | Gefühle & Verhalten | Ich verstecke Einkäufe vor anderen. |
| `#horten` | Gefühle & Verhalten | Bei mir stapeln sich Dinge, die ich nie benutze. |
| `#ratenkauf` | Geld & Schulden | Ich kaufe auf Rechnung, in Raten oder „später zahlen“. |
| `#schulden` | Geld & Schulden | Ich habe den Überblick über meine Schulden verloren. |
| `#abos` | Geld & Schulden | Abo-Check |
| `#selbstcheck` | Werkzeuge | Selbstcheck mit 10 Aussagen (keine Diagnose) |
| `#kassensturz` | Werkzeuge | Rechner: Einkommen, feste Kosten, Einkäufe, Schulden, Vorschlag für ein Kaufbudget |
| `#kaufbremse` | Werkzeuge | Sechs Fragen vor dem Kauf, Arbeitszeit hinter dem Preis, Warteliste |
| `#tagebuch` | Werkzeuge | Kauftagebuch mit Auswertung nach Gefühlen |
| `#angehoerige` | Hilfe & Beratung | Jemand, der mir nahesteht, kauft zu viel. |
| `#hilfe` | Hilfe & Beratung | Beratungsstellen und Telefonnummern |

Jede Tipp-Karte hat denselben Aufbau: „Kennst du das?“, „Warum das passiert“, „Was sofort hilft“,
„Was auf Dauer hilft“, ein Satz für den Moment und Links zu passenden Werkzeugen.
Die Texte stehen im Skript im Feld `TOPICS`. Eine neue Karte ist ein neuer Eintrag dort
(dazu ein Symbol in `ICONS`).

## Hilfe-Kontakte (Stand November 2026, einmal im Jahr prüfen)

* Telefonseelsorge 0800 111 0 111, 0800 111 0 222, 116 123
* Suchthilfeverzeichnis der DHS: suchthilfeverzeichnis.de
* Digitale Suchtberatung: suchtberatung.digital
* Selbsthilfe über NAKOS: nakos.de
* Schuldnerberatung, Online-Beratung der Caritas: caritas.de/schuldnerberatung
* Terminservicestelle 116 117, Nummer gegen Kummer 116 111, Notruf 112

Die Sucht- & Drogen-Hotline ist bewusst nicht aufgeführt: Für 2026 gibt es widersprüchliche
Angaben zur Rufnummer. Erst eintragen, wenn die aktuelle Nummer bestätigt ist.

## Daten

Selbstcheck-Antworten, Rechnerwerte, Kauftagebuch und Warteliste bleiben nur im Browser
des Besuchers (`localStorage`, Schlüssel `wh:…`). Unter Datenschutz lässt sich alles löschen.

## Vor dem Veröffentlichen eintragen

```bash
grep -n 'class="ph"' hilfe/index.html
```

* **Impressum**: Name, ladungsfähige Anschrift (kein Postfach), E-Mail.
* **Datenschutz**: der Hoster (bei GitHub Pages: GitHub Inc., USA).
* **Kontakt-Adresse** im Kasten „Dir fehlt ein Thema?“.

Impressum und Datenschutz sind Vorlagen und ersetzen keine Rechtsberatung.
Die Inhalte ersetzen keine Beratung oder Therapie; das steht auch im Fuß jeder Seite.

## Aussehen

Weißer Hintergrund, Karten mit Symbol und Bereichsfarbe. Farben stehen als Tokens im `:root`-Block,
die Bereichsfarben in den `[data-c=…]`-Regeln.

## Ansehen

Mit GitHub Pages liegt die Seite unter `https://<benutzername>.github.io/<repository>/hilfe/`.
Lokal: `python3 -m http.server 8000` im Wurzelverzeichnis, dann `http://localhost:8000/hilfe/`.
