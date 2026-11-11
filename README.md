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
| **N** | Neue Mitglieder | Einstieg in drei Schritten, Konto bei Tradequo |
| **G** | Signale | Das neueste Signal, Winrate und Pips von heute, dahinter die Historie |
| **X** | Bots | Drei Bots zur Auswahl, einzeln oder mehrere zugleich |

Dazu kommt ein sechster, **nicht öffentlicher** Abschnitt: der **Assistent**
(Taste `a` oder der Eintrag im Fuß). Er erscheint nur, wenn die Seite erkennt,
dass jemand sie bearbeiten darf; Besucher sehen ihn nicht und erreichen ihn auch
nicht über die Adresse.

Jeder Abschnitt hat eine eigene Adresse (`#ben`, `#entdecken`, `#mitglieder`, `#gold`, `#xaubot`),
lässt sich also direkt verlinken. Mit den Pfeiltasten blättert man durch die Abschnitte,
unten rechts führt eine Weiter-Zeile zum nächsten.

## Dateien

| Datei | Zweck |
| --- | --- |
| `index.html` | Die komplette Seite: Markup, CSS und JavaScript inline |
| `konsole.html` | Bot-Konsole: Einstellungen für die drei Bots, erzeugt die `config.toml` |
| `media/` | Mediendateien, u. a. das Vorstellungsvideo |
| `signals.json` | Die Signale für die Fassung auf dem eigenen Server |
| `bot/` | Der Dauerläufer: der Handelsbot als lauffähiges Python-Programm |

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

## Assistent

Ein Chat auf der Seite selbst, der mit Claude spricht und dabei **die echten
Daten dieser Seite liest**. Er hat fünf Werkzeuge:

| Werkzeug | Was es tut |
| --- | --- |
| `kennzahlen` | rechnet Anzahl, Trefferquote, Pips und offene Positionen für heute, Woche, Monat oder alles |
| `signale_lesen` | gibt einzelne Signale mit Richtung, Einstieg, Stop, Ziel und Ergebnis zurück |
| `seitenstand` | Überblick: letztes Signal, wie lange es her ist, offene Positionen, offene Aufgaben |
| `aufgabe_anlegen` | notiert ein Problem oder einen Wunsch in der Sammlung `tasks` |
| `aufgaben_lesen` | listet die Aufgaben auf |

Er darf nichts erfinden: für jede Zahl muss er ein Werkzeug benutzen. Ändern
kann er nichts — er notiert, und Claude Code liest die Liste später aus.

Bilder versteht er; aus einem Video holt die Seite bis zu drei Einzelbilder und
schickt die mit. An WhatsApp, Instagram, E-Mail oder Besucherzahlen kommt er
nicht heran, und er sagt das auch.

Chatverlauf und Aufgaben liegen in der Datenbank der Seite unter Regeln, die
beides auf Bearbeiter beschränken — ein Besucher sieht sie nicht, selbst wenn
die Seite öffentlich geteilt wird.

## Bots (X)

Drei Bots stehen zur Auswahl:

| Bot | Arbeitsweise |
| --- | --- |
| Signal-Kopierer | Spiegelt jedes Signal aus **G**, mit eigener Positionsgröße — **gebaut, liegt unter `bot/`** |
| Dauerläufer | Trendfolge auf Stundenkerzen — **gebaut, liegt unter `bot/`** |
| Swing | 1h-Liquiditäts-Sweep, 5m-Fortsetzung, Einstieg in die 1m-Lücke — **gebaut, liegt unter `bot/`** |

Wer die Seite besucht, kann einen nehmen oder mehrere. Die Auswahl merkt sich die Seite: angemeldet
im eigenen, privaten Bereich des Datenspeichers (den sonst niemand sieht, auch der
Inhaber nicht), sonst im Browser des Besuchers.

Alle drei Bots sind fertig gebaut und liegen als Python-Programm unter
[`bot/`](bot/README.md): drei Regelwerke auf gemeinsamer Maschine, dazu
Risikogrenzen, Backtest, Papierkonto, Protokoll und Not-Aus — 171 Tests. Er schreibt `signals.json` in genau dem
Format, das der Bereich **G** liest — die Kette vom Signal bis zur Seite ist
damit geschlossen. Echtes Geld fasst er erst an, wenn ein Backtest über echte
Golddaten vorliegt und ein Broker angebunden ist; beides erzwingt er selbst.

Die Auswahl auf der Seite ist bis zur Broker-Anbindung eine Merkliste.

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

## Bot-Konsole

`konsole.html` ist eine eigene Seite, auf der sich die drei Bots einstellen
lassen: jeder Wert mit Erklärung, Einheit und Standardwert, dieselben Grenzen
wie im Bot selbst, und daneben zwei Ansichten, die live mitlaufen — das
Regelwerk in Klartext und die fertige `config.toml` zum Kopieren.

Die Konsole schreibt nichts auf die Platte. Sie baut die Datei, kopiert wird
von Hand nach `bot/config.toml`. Ändert sich eine Regel, ändert sich der
Fingerabdruck, und der Bot verlangt vor dem Live-Betrieb einen neuen Backtest.

## Gestaltung

Schwarz als Grund, Chrom und Gold als einzige Farben. Alle Werte stehen als Tokens
im `:root`-Block oben im `<style>`:

* `--chrome` — der Silberverlauf für Buchstaben und Überschriften
* `--gilt` — der Goldverlauf für den aktiven Buchstaben, „Gold“ und „XAU Bot“
* `--gold` — der Goldton für Beschriftungen, Rahmen und Schaltflächen
* `--fg`, `--fg-dim`, `--line` — Text und Linien

Der Hintergrund ist **Mondgestein** — nicht gemalt, sondern gerechnet, ohne
eine einzige Bilddatei:

| Schritt | Was passiert |
| --- | --- |
| Höhenfeld | sechs Oktaven Gradientenrauschen ergeben das Grundrelief |
| Krater | Schüssel, flacher Wall und Auswurfdecke; die Ränder sind leicht unrund. Wenige große statt vieler kleiner — sonst wird die Fläche unruhig |
| Steine | kleine steile Buckel, die eigene Schatten werfen |
| Licht | Normalen aus dem Gefälle, Sonne flach über dem Horizont |
| Schatten | Strahlmarsch entlang der Sonnenrichtung; weich abgedunkelt statt pechschwarz |
| Albedo | heller Staub auf Kraterrändern, dunklere Flächen dazwischen |

Gerechnet wird in Häppchen von zehn Millisekunden pro Bild, sonst stünde die
Seite beim Laden eine Sekunde lang. Darüber liegen eine dunkle Decke und eine
Vignette: die Fläche soll zu sehen sein, aber der Text gewinnt.

Die Auflösung richtet sich nach dem Fenster und ist gedeckelt; bei einer
Größenänderung wird neu gerechnet, aber erst nach einer kurzen Ruhepause.

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
