# BENGX

Statische Website für **BENGX** — Ben, regelbasierter Handel, Gold und der XAU Bot.
Eine Datei, kein Build, keine Abhängigkeiten.

## Aufbau

Links steht der Name **BENGX** als Buchstabenleiste. Jeder Buchstabe öffnet einen Abschnitt —
per Klick oder indem man den Buchstaben auf der Tastatur drückt:

| Taste | Abschnitt | Inhalt |
| --- | --- | --- |
| **B** | Ben | Über Ben und das Vorstellungsvideo |
| **E** | Entdecken | Lernen: Grundlagen, Risiko, Praxis |
| **N** | Neue Mitglieder | Einstieg in drei Schritten |
| **G** | Signale | Das neueste Signal, Winrate und Pips von heute, dahinter die Historie |
| **X** | Bots | Drei Bots zur Auswahl, einzeln oder mehrere zugleich |

Jeder Abschnitt hat eine eigene Adresse (`#ben`, `#entdecken`, `#mitglieder`, `#gold`, `#xaubot`),
lässt sich also direkt verlinken. Mit den Pfeiltasten blättert man durch die Abschnitte,
unten rechts führt eine Weiter-Zeile zum nächsten.

## Dateien

| Datei | Zweck |
| --- | --- |
| `index.html` | Die komplette Seite: Markup, CSS und JavaScript inline |
| `media/` | Mediendateien, u. a. das Vorstellungsvideo |
| `signals.json` | Die Signale für die Fassung auf dem eigenen Server |

## Signale (G)

Der Bereich **G** hat zwei Ansichten:

* **Aktuell** — nur das neueste Signal, dazu Winrate, Pips und Anzahl von heute.
* **Historie** — Winrate, Pips und Anzahl über alles, darunter die Tabelle aller Signale.

Woher die Signale kommen, hängt davon ab, wo die Seite läuft:

* **Auf der claude.ai-Seite** liegen sie im Datenspeicher der Seite. Wer die Seite
  bearbeiten darf, bekommt dort zwei Formulare eingeblendet: eines veröffentlicht ein
  neues Signal, eines schließt das laufende mit Ergebnis und Pips. Alle, die die Seite
  offen haben, sehen die Änderung sofort. Lesen darf jeder, schreiben nur der Inhaber
  und Bearbeiter.
* **Auf dem eigenen Server** (GitHub Pages) gibt es diesen Speicher nicht. Dort liest
  die Seite `signals.json` neben `index.html`. Ein Signal ist ein Eintrag in der Liste
  `signals`; die Felder stehen in der Datei selbst beschrieben. Nach dem Commit ist es
  auf der Seite.

Ein Signal hat diese Felder:

| Feld | Bedeutung |
| --- | --- |
| `side` | `long` oder `short` |
| `entry`, `sl`, `tp` | Einstieg, Stop, Ziel |
| `status` | `offen`, `gewonnen`, `verloren` oder `be` (Break-even) |
| `pips` | Zahl; bei Verlust negativ, solange offen 0 |
| `openedAt`, `closedAt` | Zeitpunkte als ISO-8601, `closedAt` sonst `null` |
| `note` | kurze Begründung, optional |

Die Winrate zählt nur geschlossene Signale und lässt Break-even außen vor.
„Heute" richtet sich nach dem Ausstieg, bei offenen Signalen nach dem Einstieg.

## Bots (X)

Drei Bots stehen zur Auswahl:

| Bot | Arbeitsweise |
| --- | --- |
| Signal-Kopierer | Übernimmt jedes Signal aus **G** eins zu eins |
| Dauerläufer | Handelt durchgängig nach Studien und den Regelwerken erfahrener Gold-Trader, jede Strategie vorher im Backtest geprüft |
| Swing | Handelt nach Bens eigenem Regelwerk, wenige Positionen, längere Haltedauer |

Wer die Seite besucht, kann einen nehmen oder mehrere. Die Auswahl merkt sich die Seite: angemeldet
im eigenen, privaten Bereich des Datenspeichers (den sonst niemand sieht, auch der
Inhaber nicht), sonst im Browser des Besuchers.

Die Bots handeln noch nicht — die Auswahl ist bisher eine Merkliste.

## Lokal ansehen

```bash
python3 -m http.server 8000
# danach http://localhost:8000 öffnen
```

## Veröffentlichen über GitHub Pages

1. **Settings → Pages** öffnen.
2. Unter *Build and deployment* als Quelle **Deploy from a branch** wählen.
3. Branch wählen, Ordner `/ (root)`, dann **Save**.

Die Seite liegt danach unter `https://<benutzername>.github.io/<repository>/`.
Für eine eigene Domain eine Datei `CNAME` mit der Domain ins Wurzelverzeichnis legen.

## Gestaltung

Schwarz als Grund, Chrom und Gold als einzige Farben. Alle Werte stehen als Tokens
im `:root`-Block oben im `<style>`:

* `--chrome` — der Silberverlauf für Buchstaben und Überschriften
* `--gilt` — der Goldverlauf für den aktiven Buchstaben, „Gold“ und „XAU Bot“
* `--gold` — der Goldton für Beschriftungen, Rahmen und Schaltflächen
* `--fg`, `--fg-dim`, `--line` — Text und Linien

Der Hintergrund (`.bg`) liegt in sieben Schichten übereinander, ohne eine einzige Bilddatei:

| Schicht | Was sie macht |
| --- | --- |
| `.bg__grid` | feines Raster, zu den Rändern hin ausgeblendet |
| `.bg__glow--gold` | goldenes Licht oben links, wandert langsam |
| `.bg__glow--steel` | kühles Licht unten rechts, wandert gegenläufig |
| `.bg__sheen` | schräger Chromschimmer, zieht langsam durchs Bild |
| `.bg__dust` | feiner Gold- und Silberstaub auf einem Canvas |
| `.bg__grain` | Korn als SVG-Rauschen |
| `.bg__vig` | Vignette, die die Ränder abdunkelt |

Alle Bewegungen stehen still, sobald das Gerät auf „weniger Bewegung" steht, und der
Staub pausiert, wenn der Tab im Hintergrund liegt. Die Anzahl der Staubkörner richtet
sich nach der Fenstergröße.

## Noch einzutragen

Alle offenen Stellen stehen auf der Seite in Gold und eckigen Klammern,
z. B. `[%]` oder `[4h / 1d]`. Im Quelltext findest du sie über die Klasse `ph`:

```bash
grep -n 'class="ph"' index.html
```

Dazu kommen: die echte E-Mail-Adresse (`hallo@bengx.de` ist ein Platzhalter),
das Vorstellungsvideo unter `media/ben-vorstellung.mp4` sowie die Funktionen
von Entdecken, Neue Mitglieder und den Bots.

Eine Angabe altert: die Kachel **Erfahrung** bei B steht auf `1 Jahr`.
Sie gehört einmal im Jahr hochgezählt.

## Hinweis

Die Seite ist keine Anlageberatung. Handel mit Gold, Hebelprodukten und Kryptowerten
kann zum Totalverlust führen.
