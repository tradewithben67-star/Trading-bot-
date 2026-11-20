# Wo hakt's beim Kaufen?

Eine Website rund um **Kaufsucht**. Die Startseite zeigt nur vier Karten auf weißem Grund,
jede mit Symbol und kurzem Namen. Alles Weitere erscheint erst nach dem Klick: Tipps in einer
ruhigen Spalte, am Ende jeder Seite die Wege zum Rechner und zu Hilfe & Beratung.
„Zurück“ führt dorthin, wo man herkam.

Eine Datei (`index.html`), kein Build, keine Abhängigkeiten, keine Cookies, keine Werbung, keine fremden Schriften.

## Die vier Karten

| Adresse | Karte | Dahinter |
| --- | --- | --- |
| `#laden` | Einkaufen im Laden | Tipps, auch zu Sale und Rabatten |
| `#online` | Online-Shopping | Tipps, auch zu Social Media, Apps und Spielen |
| `#gefuehle` | Kaufen aus Frust | Tipps, auch zu Heimlichkeit und ungenutzten Sachen |
| `#schulden` | Schulden & Raten | Tipps zu Ratenkauf, „später zahlen“, Dispo und Schuldnerberatung |

Erst hinter den Karten erreichbar: `#kassensturz` (Rechner: Einkommen, feste Kosten, Einkäufe,
Schulden, Vorschlag für ein Kaufbudget) und `#hilfe` (Beratungsstellen und Telefonnummern), außerdem
`#selbstcheck` (10 Aussagen, keine Diagnose), `#kaufbremse` (Fragen vor dem Kauf, Warteliste),
`#tagebuch` (Kauftagebuch), `#abos` (Abo-Check) und `#angehoerige` (Tipps für Angehörige).
Ältere Adressen (`#rabatte`, `#social`, `#apps`, `#heimlich`, `#horten`, `#ratenkauf`) leiten auf die
zusammengefasste Karte weiter.

Jede Tipp-Seite hat denselben Aufbau:

1. **Kennst du das?** zum Antippen, mit Rückmeldung, wie viel davon zutrifft
2. **Warum das passiert**, bei „Kaufen aus Frust“ mit dem Kreislauf zum Durchklicken
   (Auslöser → Drang → Kauf → Reue → neues Tief, jeweils mit „Hier aussteigen“)
3. **Was sofort hilft**, jeder Tipp mit „+ Plan“
4. ein Satz für den Moment
5. ein **Mini-Werkzeug** zum Thema:

   | Seite | Werkzeug |
   | --- | --- |
   | Einkaufen im Laden | Sale-Check: echter Rabatt oder nur Ausgabe? |
   | Online-Shopping | Paket-Rechner mit Schiebereglern |
   | Kaufen aus Frust | Impuls-Pause: Gefühl wählen, 20-Minuten-Timer, passende Ideen |
   | Schulden & Raten | Schuldenliste mit Reihenfolge und Brief-Vorlage „Ratenzahlung anfragen“ |
   | Für Angehörige | Gesprächsstarter mit Ich-Botschaft zum Kopieren |

6. **Was auf Dauer hilft**, ebenfalls mit „+ Plan“
7. **Gut zu wissen**: drei Fragen und Antworten zum Aufklappen
8. **Nächster Schritt**: Rechner und Hilfe & Beratung, dazu „Mein Plan“

**Mein Plan** (`#plan`) sammelt alle Tipps, die man mit „+ Plan“ ausgewählt hat, zum Abhaken.
Der **Rechner** hat zusätzlich einen Schieberegler „Was wäre, wenn du weniger kaufst?“.

Die Texte stehen im Skript in `TOPICS` (Grundinhalt) und `EXTRA` (Fragen, Mini-Werkzeug).
Ob ein Eintrag auf der Startseite erscheint, bestimmt `start` (die Zahl ist die Reihenfolge).

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
