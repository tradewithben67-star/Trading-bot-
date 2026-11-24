# BENGX KI

Ein eigenes neuronales Netz für Kerzen, von Grund auf gebaut. Es nutzt kein
fertiges Modell und keine fremden Gewichte: Alles, was die KI weiß, lernt sie
selbst aus deinen Kursdaten.

Das Gehirn ist ein **Transformer**, dasselbe Prinzip wie in großen
Sprachmodellen. Die „Wörter“ sind hier Kerzen. PyTorch liefert nur die
Rechenbausteine. Aufbau, Aufmerksamkeit, Lernen und Prüfen stehen vollständig
im Ordner `bengx_ki/`.

## Starten

Windows: **`KI.bat`** doppelklicken. Fehlt PyTorch, wird es beim ersten Mal
installiert. Danach erscheint ein Menü.

Kommandozeile, im Ordner `bot`:

```bash
pip install torch                                     # einmalig

python3 -m bengx_ki lernprobe --gegenprobe            # beweist, dass sie lernt
python3 -m bengx_ki trainieren --csv data/xauusd_h1.csv
python3 -m bengx_ki vorhersage --csv data/xauusd_h1.csv
python3 -m bengx_ki testen     --csv data/neuere_kerzen.csv
```

Das Modell landet in `ki/modell.pt`. Der Ordner wird nicht eingecheckt.

Die Kursdatei ist dieselbe CSV wie für den Backtest des Bots: Spalten Zeit,
Open, High, Low, Close und optional Volumen, z. B. als Export aus MT5. Je mehr
Kerzen, desto besser. Unter etwa 10.000 Stundenkerzen lernt sie kaum etwas.

## Chat, Chart und Warum

**Chat in jedem Bereich.** Auf den Seiten Analyse, Indikatoren und Strategie
und auf der eigenen Seite **Chat** schreibt man mit der KI wie mit einem
Menschen. Das Sprechen übernimmt Claude (Anthropic). Gerechnet wird nur mit
den eigenen Werkzeugen: Claude ruft die Analyse des eigenen Netzes, den
Strategie-Test, die Indikatoren, den Formel-Baukasten, die Kerzen und den
Verlauf auf und erklärt die Ergebnisse. Was dabei entsteht, erscheint als
Karte mit Chart unter der Antwort.

Einrichtung: einen API-Schlüssel von console.anthropic.com in `bot/.env`
eintragen und die Oberfläche neu starten:

```
ANTHROPIC_API_KEY=sk-ant-...
```

Jede Chat-Nachricht kostet bei Anthropic Geld, meist wenige Cent. Deshalb hat
der Chat ein eigenes Kontingent je Abo (Start 30, Pro 300, Elite 1.500
Nachrichten im Monat; Inhaber ohne Grenze). Startet die KI im Chat eine
Analyse, verbraucht das zusätzlich das Kontingent des Modells. Als Modell
dient `claude-opus-5-5`; ein anderes lässt sich mit `BENGX_KI_CLAUDE_MODELL`
einstellen. Lehnt das Modell eine Anfrage aus Sicherheitsgründen ab, springt
automatisch ein anderes ein (server-seitiger Rückfall).

**Echter Chart.** Jede Analyse zeigt die letzten 120 Kerzen mit EMA 50,
Einstieg, Ziel und Stop und dem Zeitraum, den die KI nach vorn schaut.

**Warum dieses Setup.** Zwei Messungen am Netz, keine erfundene Begründung:

- *Fokus*: Auf welche Kerzen die jüngste Kerze über alle Blöcke hinweg
  geachtet hat (Aufmerksamkeit, durchgerollt). Die drei wichtigsten sind im
  Chart nummeriert.
- *Was die Richtung trägt*: Wie viele Prozentpunkte die Wahrscheinlichkeit
  fällt, wenn man dem Netz eine Merkmalsgruppe wegnimmt (Kerzenform,
  Bewegung, Abstand zum Durchschnitt, Unruhe, Volumen, Uhrzeit).

**Eigene Indikatoren.** Unter Indikatoren baut man eigene aus einer Formel,
etwa `ema(close, 20)`, `rsi(close, 14) < 30` oder
`crossover(ema(close, 50), ema(close, 200))`. Linien erscheinen im Chart,
Oszillatoren darunter. Eine Bedingung wird im Chart markiert und gemessen:
Wie oft traf sie zu, und kam danach zuerst das Ziel oben oder der Stop
unten? Formeln werden sicher ausgewertet (eigene Zerlegung, kein `eval`).
Man kann Indikatoren auch einfach im Chat beschreiben; die KI baut und prüft
sie dann selbst.

## Recht, Datenschutz, Barrierefreiheit

Die Oberfläche bringt alles mit, was eine App vor dem Start braucht. Die
Rechtstexte sind **Vorlagen** und keine Rechtsberatung. Vor dem Start mit
zahlenden Kunden sollte eine Fachperson sie prüfen; die wichtigsten Punkte
dafür stehen in der Oberfläche unter **Rechtliches** und in
`bengx_ki/rechtliches.py` (`PRUEFEN`).

| Punkt | Umsetzung |
| --- | --- |
| Impressum, Betreiberangaben | Seite „Impressum“ (§ 5 DDG); Angaben trägt der Inhaber unter **Rechtliches** ein, bis dahin Warnung auf der Übersicht und beim Start mit `--offen` |
| Datenschutzerklärung | Seite „Datenschutz“: Daten, Zwecke, Rechtsgrundlagen, Speicherdauer, Anthropic als Empfänger, Drittland, Rechte |
| Nutzungsbedingungen | Seite „Nutzungsbedingungen“, mit Risikohinweis und „keine Anlageberatung“ |
| Widerruf und Erstattung | Seite „Widerruf“: Widerrufsbelehrung, Muster-Formular, automatische Gutschrift bei Fehlern |
| Cookies, Cookie-Hinweis | Seite „Cookies“; Hinweis mit zwei gleichwertigen Knöpfen „Nur Notwendiges“ / „Komfort erlauben“; ohne Zustimmung landet nur Notwendiges im Browser |
| Zustimmung in Formularen | Beim ersten Anmelden drei leere Kästchen (Alter, Bedingungen, Datenschutz); Zeitpunkt und Fassung werden gespeichert; neue Fassung = neue Zustimmung |
| Altersgrenze | ab 18, als Pflicht-Bestätigung |
| Nur nötige Daten | kein E-Mail, keine Anschrift von Kunden, Passwort nur als Hash, keine IP-Protokolle; der Name geht nicht an Anthropic |
| Drittanbieter | nur Anthropic (Chat) und PyTorch (läuft lokal); die Seite lädt nichts von fremden Servern (Content-Security-Policy) |
| Keine Dark Patterns | gleichwertige Knöpfe, keine vorausgewählten Kästchen, Löschen ohne Hürden, Grenzen klar benannt, Modellwahl springt nicht heimlich um |
| Keine versteckten Kosten | Abschnitt „Was es kostet“ unter Nutzung & Abo |
| Keine Fake-Bewertungen, keine unbelegten Versprechen | keine Bewertungen; Testergebnisse als Test gekennzeichnet; Risikohinweis bei Anmeldung und jeder Analyse |
| Alternativtexte | Charts mit Beschreibung für Screenreader, Symbole als Schmuck markiert |
| Kontrast | Textfarben mit mindestens 4,5 : 1 in Hell und Dunkel (WCAG AA) |
| Tastatur | sichtbarer Fokus, „Zum Inhalt springen“, Einträge per Enter, Detailblatt als Dialog mit Fokusrückgabe, Escape schließt |
| Abmeldelink | es gibt keine Newsletter oder Werbe-Nachrichten; in der Datenschutzerklärung festgehalten |
| Bildrechte | die Oberfläche nutzt keine Fremdbilder |
| Datenlöschung | Konto → „Meine Daten herunterladen“ (JSON) und „Konto löschen“, sofort und vollständig; Verlauf und Chats nach 365 Tagen automatisch gelöscht |

## Drei Modelle

| Modell | Blick | Aufbau | Gewichte | Verbrauch |
| --- | --- | --- | --- | --- |
| **Mini** | 32 Kerzen | 2 Blöcke · 2 Köpfe · Breite 32 | ca. 27.000 | × 1 |
| **Standard** | 64 Kerzen | 3 Blöcke · 4 Köpfe · Breite 64 | ca. 155.000 | × 3 |
| **Max** | 128 Kerzen | 4 Blöcke · 6 Köpfe · Breite 96 | ca. 461.000 | × 10 |

Alle drei sind derselbe Transformer, nur verschieden groß. Ein größeres Modell
kann längere und feinere Muster erfassen, braucht aber mehr Daten und lernt auf
zu wenig Daten eher auswendig. Ob Max auf deinen Kursen wirklich besser ist,
zeigt nur der Vergleich unter **Strategie**. Max trainiert auch deutlich
länger: auf 4 Rechenkernen etwa 30 s pro Durchgang je 4.000 Beispiele.

```bash
python3 -m bengx_ki trainieren --csv data/xauusd_h1.csv --modell mini
python3 -m bengx_ki trainieren --csv data/xauusd_h1.csv --modell max
```

Die Modelle liegen in `ki/modelle/mini.pt`, `standard.pt` und `max.pt`. Ein
Modell aus der ersten Fassung (`ki/modell.pt`) wird beim nächsten Start
automatisch zu Standard.

## Oberfläche

```bash
python3 -m bengx_ki oberflaeche --csv data/xauusd_h1.csv
python3 -m bengx_ki oberflaeche --lernprobe          # ohne CSV, zum Ausprobieren
```

Unter Windows: `KI.bat`, Punkt 5. Der Browser öffnet sich unter
`http://127.0.0.1:8765/`. Beim **ersten Öffnen legst du den Inhaber an**, also
dich selbst. Danach braucht jeder Name und Passwort.

| Bereich | Was dort passiert |
| --- | --- |
| **Übersicht** | Abo, bereite Modelle, letzter Kurs, letzte Analyse, letzte Aktionen |
| **Analyse** | Modell wählen (Mini, Standard, Max), Einschätzung mit Einstieg, Stop und Ziel |
| **Indikatoren** | Kurve mit EMA 50/200, dazu RSI, ADX, ATR und 20er-Kanal, frei |
| **Strategie** | Modell wählen und auf unbekannten Kerzen testen, alle drei im Vergleich |
| **Verlauf** | jede Aktion mit allen Details; Kunden sehen nur ihre eigenen |
| **Modelle** | Steckbrief jedes Modells; der Inhaber trainiert hier mit Live-Protokoll |
| **Nutzung & Abo** | Kontingent je Modell, Abos im Vergleich, Kosten, Buchungen |
| **Nutzer** | nur Inhaber: Nutzer anlegen, Abo ändern, Passwort setzen, löschen; Namen antippen zeigt Nutzung, Verlauf und Buchungen dieses Nutzers |

Die Oberfläche ist schwarz-weiß, mit hellem und dunklem Modus, und läuft auch
auf dem Handy-Bildschirm.

## Inhaber und Kunden

* Der **Inhaber** hat keine Grenzen. Er trainiert, verwaltet Nutzer und sieht
  den Verlauf aller. Seine Nutzung wird trotzdem gezählt.
* **Kunden** haben ein Abo. Jedes Modell hat darin sein eigenes
  Monatskontingent. Ist es aufgebraucht, **hört dieses Modell auf**, bis zum
  Monatsersten. Die anderen Modelle laufen weiter. Steht 0 im Abo, ist das
  Modell gesperrt.

| Tokens im Monat | Start | Pro | Elite |
| --- | --- | --- | --- |
| Mini | 100 | 1.000 | unbegrenzt |
| Standard | 30 | 600 | 3.000 |
| Max | – | 200 | 1.000 |
| Preis | folgt | folgt | folgt |

| Kosten | Mini | Standard | Max |
| --- | --- | --- | --- |
| KI-Analyse | 1 | 3 | 10 |
| Strategie-Test | 5 | 15 | 50 |
| Indikatoren | frei | frei | frei |

Mit Start sind das also 100 Analysen mit Mini und 10 mit Standard im Monat.
Fehlt etwas, etwa ein trainiertes Modell, wird nichts verbraucht. Scheitert
eine Aktion unterwegs, kommt der Verbrauch zurück. Mengen, Kosten und Preise
stehen oben in `bengx_ki/konto.py`, die Modelle in `bengx_ki/modelle.py`.

Nutzer gehen auch über die Kommandozeile:

```bash
python3 -m bengx_ki nutzer                            # alle, mit Verbrauch
python3 -m bengx_ki nutzer anlegen Anna --abo pro     # fragt nach dem Passwort
python3 -m bengx_ki nutzer abo Anna elite
python3 -m bengx_ki nutzer passwort Anna
python3 -m bengx_ki nutzer loeschen Anna
```

## Sicherheit und Betrieb im Netz

* Passwörter werden nur als PBKDF2-Hash gespeichert. Nach 5 Fehlversuchen
  pausiert die Anmeldung für diesen Namen eine Minute.
* Die Sitzung steckt in einem Cookie (`HttpOnly`, `SameSite=Strict`). Nach
  einem Neustart des Servers meldet man sich neu an.
* Ohne `--offen` ist der Server nur auf dem eigenen Rechner erreichbar. Mit
  `--offen` hört er im ganzen Netz. **Fürs Internet nur hinter HTTPS** (z. B.
  Caddy oder nginx davor), sonst gehen Passwörter offen über die Leitung.
* Den Inhaber kann man nur am eigenen Rechner anlegen, nie aus dem Netz.
* Bezahlung gibt es noch nicht: Abos vergibt der Inhaber.

Alles Laufende liegt im Ordner `ki/`: `modelle/`, `nutzer.json`,
`nutzung.json`, `verlauf.jsonl`. Der Ordner wird nicht eingecheckt.

## Was die KI lernt

Für jede Kerze stellt sie eine Frage: **Wird von hier aus zuerst das Ziel oben
oder der Stop unten erreicht?** Beide liegen 1,5 × ATR entfernt
(`--abstand`). Wird innerhalb von 24 Kerzen (`--horizont`) keins von beiden
erreicht, lautet die Antwort „seitwärts“.

Dazu sieht sie die letzten 64 Kerzen (`--fenster`). Jede Kerze ist durch
12 Zahlen beschrieben, alle im Verhältnis zur ATR statt in Dollar: Rendite,
Körper, Dochte, Spanne, Abstand zum EMA 50, Unruhe, Volumen, Uhrzeit und
Wochentag.

## Die vier Teile

| Datei | Teil | Was passiert |
| --- | --- | --- |
| `merkmale.py` | Übersetzen | Kerzen werden zu Zahlen, und es entsteht die Antwort, die gelernt werden soll |
| `gehirn.py` | Gehirn | Einbettung, Aufmerksamkeit mit Zukunftsmaske, Blöcke, Kopf |
| `training.py` | Lernen | zeitlicher Schnitt, Lernschleife, Abbruch vor dem Auswendiglernen, Speichern |
| `auswertung.py` | Prüfen | Trefferquote gegen Raten, Handel gegen „immer kaufen“ |
| `lernprobe.py` | Beweis | erfundene Kurse mit verstecktem Muster |
| `dienste.py` | Aktionen | Analyse mit Chart und Begründung, Indikatoren, Strategie-Test |
| `eigene.py` | Baukasten | eigene Indikatoren aus Formeln, sicher ausgewertet und gemessen |
| `chat.py` | Chat | Claude mit den eigenen Werkzeugen, Gespräche je Nutzer und Bereich |
| `rechtliches.py` | Recht | Impressum, Datenschutz, Nutzungsbedingungen, Widerruf, Cookies; Betreiberangaben |
| `modelle.py` | Modellfamilie | Mini, Standard, Max: Größe und Verbrauch |
| `konto.py` | Nutzung | Kontingente je Modell und Abo, Buchungen |
| `nutzer.py` | Nutzer | Konten, Passwort-Hashes, Sitzungen |
| `verlauf.py` | Historie | jede Aktion mit Nutzer und Modell in `ki/verlauf.jsonl` |
| `server.py`, `oberflaeche.html` | Oberfläche | Webserver und Seite, ohne weitere Abhängigkeiten |

## Warum man den Ergebnissen trauen kann

Bei Trading-KIs ist der häufigste Fehler, dass sie heimlich in die Zukunft
schauen. Dann sieht der Test großartig aus, und live geht alles verloren. Hier
ist das an vier Stellen verhindert, die letzten drei sind durch Tests
abgesichert:

1. **Zeitlicher Schnitt statt Mischen**: 70 % lernen, 15 % prüfen, 15 % testen,
   in dieser Reihenfolge. An jeder Grenze fällt eine Lücke von `horizont`
   Kerzen weg.
2. **Normierung nur aus dem Lern-Teil**: Mittelwert und Streuung kommen nicht
   aus späteren Daten.
3. **Zukunftsmaske in der Aufmerksamkeit**: Keine Kerze im Fenster sieht eine
   spätere.
4. **Merkmale nur aus der Vergangenheit**: Kürzt man die Daten, ändert sich an
   älteren Zeilen nichts.

Die **Gegenprobe** (`lernprobe --gegenprobe`) lernt zusätzlich auf reinem
Zufall. Dort darf die KI nichts finden, und sie findet auch nichts. Würde sie
dort glänzen, hätte sie geschummelt.

## Ergebnis der Lernprobe

Getestet auf 4.000 erfundenen Kerzen, die die KI nie gesehen hat, mit einem
versteckten Muster (Hammer → steigt, Sternschnuppe → fällt):

| | Trefferquote | Summe |
| --- | --- | --- |
| KI ab 70 % Sicherheit | 73 % | +28 R in 60 Trades |
| KI ab 60 % Sicherheit | 63 % | +89 R in 339 Trades |
| immer kaufen | 50 % | +5 R in 536 Trades |

Das beweist nur, dass die KI ein vorhandenes Muster findet. Ob echte
Goldkurse eines enthalten, zeigt erst das Training auf deinen Daten.

## Was diese KI nicht ist

* **Keine Gelddruckmaschine.** Echte Märkte sind fast Zufall. Ein Vorsprung
  von wenigen Prozent wäre schon sehr gut, und oft gibt es keinen.
* **Ohne Gebühren gerechnet.** Spread und Kommission fressen bei einem Ziel
  von 1,5 ATR einen spürbaren Teil.
* **Kein Ersatz für Regeln.** Am besten dient sie als Filter für die Signale
  des Dauerläufers, nicht als eigener Bot. Das ist der nächste Ausbauschritt.
* **Erst auf Papier.** Nur `testen` auf Kerzen *nach* dem Lernzeitraum zeigt,
  ob sie wirklich etwas kann.
