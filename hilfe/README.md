# Wo hakt's?

Eine Website, auf der man sein Problem anklickt und ein Werkzeug bekommt, das es löst.
Eine Datei (`index.html`), kein Build, keine Abhängigkeiten, keine Cookies, keine fremden Schriften.

## Themen

| Adresse | Problem | Werkzeug |
| --- | --- | --- |
| `#positionsgroesse` | Wie viel darf ich pro Trade riskieren? | Rechner für Gold, Forex, Aktien, Krypto: Lots/Stück, Verlust, CRV, nötige Trefferquote |
| `#klassenkasse` | Reicht unser Geld für Abiball oder Klassenfahrt? | Budgetplaner mit eigenen Posten, Betrag pro Person und Monat |
| `#auszug` | Kann ich mir die eigene Wohnung oder WG leisten? | Start- und Monatskosten gegen Einkommen, Notgroschen |
| `#lernplan` | Ich schaffe meinen Stoff bis zur Prüfung nicht. | Lernplan mit Wiederholungen nach 1, 3 und 7 Lerntagen |
| `#lernmethode` | Welche Lernmethode passt zu meinem Stoff? | Entscheidungshilfe mit drei Fragen |
| `#bewerbung` | Wie fange ich mit der Bewerbung an? | Checkliste plus Anschreiben-Gerüst zum Kopieren |
| `#lerntools` | Welches kostenlose Tool hilft mir beim Lernen? | Kuratiertes Verzeichnis mit Filter |
| `#impressum`, `#datenschutz` | | Pflichtseiten |

Startseite: Suchfeld (sucht in Frage, Text und Stichwörtern) und Filter nach Bereich.
Eingaben und Haken bleiben im Browser des Besuchers (`localStorage`, Schlüssel `wh:…`)
und lassen sich unter Datenschutz löschen.

## Ein neues Thema hinzufügen

1. In `index.html` eine neue `<section id="v-meinthema" data-view data-tool hidden>` anlegen
   (am einfachsten eine bestehende kopieren).
2. Im Skript in `TOPICS` einen Eintrag ergänzen (`id`, `cat`, `frage`, `text`, `typ`, `dauer`, `tags`).
3. Eine Rechenfunktion schreiben und in `CALC` unter `'v-meinthema'` eintragen.
   Felder mit `data-save` werden automatisch gespeichert und mit „Beispiel wiederherstellen“ zurückgesetzt.

## Vor dem Veröffentlichen eintragen

Alle offenen Stellen stehen in eckigen Klammern und haben die Klasse `ph`:

```bash
grep -n 'class="ph"' hilfe/index.html
```

* **Impressum**: Name und ladungsfähige Anschrift (kein Postfach), E-Mail.
* **Datenschutz**: der Hoster (bei GitHub Pages: GitHub Inc., USA).
* **Kontakt-Adresse** im Kasten „Dein Problem ist nicht dabei?“.
* **Partnerlinks** in den Kästen „Anzeige“ und der Featured-Eintrag im Verzeichnis.
  Partnerlinks immer als Werbung gekennzeichnet lassen.

Impressum und Datenschutz sind Vorlagen und ersetzen keine Rechtsberatung.

## Werte, die altern

Stand November 2026, einmal im Jahr prüfen:

* Deutschlandticket 63 € (Feld `az-ticket`)
* Rundfunkbeitrag 18,36 € pro Wohnung (Hinweis unter „Jeden Monat“)
* Kindergeld 259 € (Feld `az-kindergeld`)
* Preise und Haken im Verzeichnis (`TOOLS` im Skript)

## Ansehen

Mit GitHub Pages liegt die Seite unter `https://<benutzername>.github.io/<repository>/hilfe/`.
Lokal: `python3 -m http.server 8000` im Wurzelverzeichnis, dann `http://localhost:8000/hilfe/`.
