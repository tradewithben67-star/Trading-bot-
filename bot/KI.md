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

## Oberfläche

```bash
python3 -m bengx_ki oberflaeche --csv data/xauusd_h1.csv
python3 -m bengx_ki oberflaeche --lernprobe          # ohne CSV, zum Ausprobieren
```

Unter Windows: `KI.bat`, Punkt 5. Der Browser öffnet sich unter
`http://127.0.0.1:8765/`. Die Oberfläche ist schwarz-weiß, mit hellem und
dunklem Modus, und läuft auch auf dem Handy-Bildschirm.

| Bereich | Was dort passiert |
| --- | --- |
| **Übersicht** | Tokens, Modellstand, letzter Kurs, letzte Analyse, letzte Aktionen |
| **Analyse** | Einschätzung der KI für die jüngste Kerze, mit Einstieg, Stop und Ziel |
| **Indikatoren** | Kurve mit EMA 50/200, dazu RSI, ADX, ATR und 20er-Kanal mit Deutung |
| **Strategie** | die Regeln der KI, Test auf unbekannten Kerzen, neu trainieren mit Live-Protokoll |
| **Verlauf** | jede Aktion der KI mit allen Details, filterbar; Antippen öffnet sie |
| **Modell** | Steckbrief des Gehirns und seine Prüfung nach dem Training |
| **Tokens & Abo** | Guthaben, Abos, was was kostet, Aufladen, alle Buchungen |

Der Server hört nur auf dem eigenen Rechner (127.0.0.1) und hat noch keine
Anmeldung. Bevor Abonnenten ihn nutzen, braucht er Anmeldung, ein Konto je
Nutzer und eine Bezahlung.

## Tokens und Abos

Jede Aktion kostet Tokens:

| Aktion | Tokens |
| --- | --- |
| Indikatoren lesen | 1 |
| KI-Analyse | 5 |
| Strategie testen | 10 |
| KI neu trainieren | 50 |

| Abo | Tokens im Monat | Preis |
| --- | --- | --- |
| Start | 200 | folgt |
| Pro | 2.000 | folgt |
| Elite | 10.000 | folgt |

* Das **Abo-Guthaben** wird zu jedem Monatsbeginn neu gesetzt. Der Rest verfällt.
* **Aufgeladene** Tokens verfallen nie. Abgebucht wird zuerst vom Abo.
* Fehlt etwas, z. B. das Modell, wird gar nicht erst abgebucht. Scheitert eine
  Aktion unterwegs, kommen die Tokens zurück.
* Mengen, Kosten und Preise stehen oben in `bengx_ki/konto.py`.

```bash
python3 -m bengx_ki tokens                   # Stand und letzte Buchungen
python3 -m bengx_ki tokens --aufladen 500
python3 -m bengx_ki tokens --abo pro
```

Modell, Tokens (`konto.json`) und Verlauf (`verlauf.jsonl`) liegen im Ordner
`ki/`. Er wird nicht eingecheckt.

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
| `dienste.py` | Aktionen | Analyse, Indikatoren, Strategie-Test als Daten |
| `konto.py` | Tokens | Guthaben, Abos, Buchungen |
| `verlauf.py` | Historie | jede Aktion als Zeile in `ki/verlauf.jsonl` |
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
