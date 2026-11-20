# Wo hakt's?

Eine Website für den Alltag: Man klickt sein Problem an und bekommt ein Werkzeug, das es löst.
Für alle, nicht nur für eine Zielgruppe: Geld und Haushalt, Wohnen und Energie, Unterwegs, Küche, Lernen, Job und Trading.
Eine Datei (`index.html`), kein Build, keine Abhängigkeiten, keine Cookies, keine fremden Schriften.

Aussehen: weißer Hintergrund, die Startseite zeigt jedes Thema als Karte mit Symbol und Bereichsfarbe. Ein Klick auf eine Karte öffnet das Werkzeug mit allen Informationen. Farben stehen als Tokens oben im `:root`-Block, die Bereichsfarben in den `[data-c=…]`-Regeln, die Symbole in `ICONS` im Skript.

## Themen

| Adresse | Problem | Werkzeug |
| --- | --- | --- |
| `#haushaltsgeld` | Wo bleibt mein Geld jeden Monat? | Einnahmen und Ausgaben nach der 50-30-20-Regel, mit Balken und Spartipps |
| `#kosten-teilen` | Wer schuldet wem wie viel? | Gruppenausgaben fair aufteilen, möglichst wenige Überweisungen, zum Kopieren |
| `#abos` | Welche Abos und Verträge kosten mich am meisten? | Abo-Check: Kosten pro Jahr, Sparpotenzial, Hinweise zum Kündigen |
| `#stromkosten` | Was kostet mich ein Gerät an Strom? | Geräte mit Watt und Nutzung, Kosten pro Jahr |
| `#fahrtkosten` | Was kostet die Fahrt und wie teilen wir sie auf? | Sprit- oder Ladekosten pro Person |
| `#rezept` | Wie rechne ich ein Rezept auf mehr Personen um? | Zutatenliste umrechnen, versteht Brüche, rundet Eier auf |
| `#sparziel` | Wie lange muss ich sparen, bis ich mir das leisten kann? | Dauer bis zum Ziel mit Zinsen, nötige Rate bis zum Wunschtermin |
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
4. Für Listen mit beliebig vielen Zeilen (wie Abos, Geräte, Ausgaben) gibt es `rowList({...})`;
   die Abos zeigen, wie man es benutzt.

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
* Beispielpreise für Strom (35 ct/kWh), Sprit (1,75 €/l) und Tagesgeld-Zinsen (2 %)
* Preise und Haken im Verzeichnis (`TOOLS` im Skript)

## Ansehen

Mit GitHub Pages liegt die Seite unter `https://<benutzername>.github.io/<repository>/hilfe/`.
Lokal: `python3 -m http.server 8000` im Wurzelverzeichnis, dann `http://localhost:8000/hilfe/`.
