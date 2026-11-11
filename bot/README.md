# Dauerläufer

Der Bot aus dem Bereich **X** der Website. Er handelt XAU/USD nach einem festen
Regelwerk: er prüft jede abgeschlossene Kerze, und wenn Trend, Stärke,
Volatilität, Handelszeit und Risiko zusammenpassen, nimmt er den Ausbruch mit.
In allen anderen Lagen tut er nichts.

Reines Standard-Python ab 3.11. Keine Abhängigkeiten, kein `pip install`.

## Schnellstart

```bash
cd bot

python3 -m bengx_bot rules              # das Regelwerk im Klartext
python3 -m bengx_bot selftest           # Mechanik auf erfundenen Daten prüfen
python3 -m unittest discover -s tests -t .   # 89 Tests

cp config.example.toml config.toml      # anpassen
python3 -m bengx_bot --config config.toml backtest --csv data/xauusd_h1.csv
python3 -m bengx_bot --config config.toml paper --once
```

## Das Regelwerk

Ein Signal entsteht **nur**, wenn alle fünf Bedingungen gleichzeitig zutreffen:

| | Bedingung | Warum |
| --- | --- | --- |
| 1 | **Trend** — Kurs über EMA(200), und der EMA steigt über 20 Kerzen | hält von Gegenbewegungen fern |
| 2 | **Stärke** — ADX(14) ≥ 18 | in der Seitwärtsphase scheitert jeder Ausbruch |
| 3 | **Volatilität** — ATR(14) zwischen 25 und 400 Pips | zu ruhig lohnt nicht, zu wild sprengt jeden Stop |
| 4 | **Handelszeit** — 07:00–20:00 UTC, freitags bis 19:00, nie am Wochenende | die dünne asiatische Nacht erzeugt Fehlausbrüche |
| 5 | **Ausbruch** — Schluss über dem Hoch der letzten 20 Kerzen | das eigentliche Signal |

Für Short gilt jede Bedingung spiegelbildlich.

Nach dem Einstieg:

* **Stop** 2 × ATR vom Einstieg — der Abstand misst sich an der Bewegung des
  Marktes, nicht an einer festen Zahl.
* **Teilziel** bei 1,5 R: die Hälfte geht raus, der Stop wandert auf Einstand.
  Ab da kann der Trade nicht mehr ins Minus drehen.
* **Trailing** danach 2,5 × ATR vom höchsten Punkt — nur enger, nie wieder weiter.
* **Zeitstop** nach 48 Kerzen ohne Entscheidung.
* **Wochenende** freitags ab 19:00 UTC alles glatt: über Nacht von Freitag auf
  Montag reißen Kurslücken jeden Stop.

Das Regelwerk ist Trendfolge, wie sie für Rohstoffe seit Jahrzehnten beschrieben
wird: in Richtung des übergeordneten Trends, Einstieg auf den Ausbruch,
Positionsgröße und Stop an der Volatilität. Die konkreten Zahlen stehen in
`config.toml` und sind bewusst nicht in den Code eingebrannt.

## Risiko steht über der Strategie

Die Strategie darf einen Trade *anfragen*. Ob er zustande kommt, entscheidet
`risk.py` — und das kann die Strategie nicht umgehen:

| Grenze | Standard |
| --- | --- |
| Risiko je Position | 0,5 % des Kontos |
| gleichzeitige Positionen | 2 |
| Tagesverlust | ab 2 % kein neuer Einstieg bis zum nächsten Tag |
| Drawdown-Bremse | ab 8 % halbe Positionsgröße |
| Drawdown-Stopp | ab 15 % gar kein Einstieg mehr |
| Pause | 12 Kerzen nach 2 Verlusten in Folge |

Die Positionsgröße ergibt sich aus Kontostand und Stop-Abstand, nie aus einer
festen Stückzahl: `Größe = Kapital × Risiko ÷ Stop-Abstand`.

**Not-Aus:** Datei `state/KILLSWITCH` anlegen. Beim nächsten Durchlauf schließt
der Bot alles zum Marktkurs und eröffnet nichts mehr, bis die Datei weg ist.

## Backtest

```bash
python3 -m bengx_bot --config config.toml backtest --csv data/xauusd_h1.csv --save
```

Gerechnet wird mit Spread, Slippage und Kommission aus `[costs]` und ohne Blick
in die Zukunft: ein Signal entsteht erst auf der *geschlossenen* Kerze, eine
Position wird frühestens ab der nächsten Kerze verwaltet, und liegen Stop und
Ziel in derselben Kerze, zählt der Stop.

`--save` legt den Bericht unter `state/backtests/<fingerabdruck>.json` ab. Der
Fingerabdruck ist ein Hash über alles, was das Ergebnis beeinflusst — Markt,
Kosten, Strategie, Risiko. **Wer eine Regel ändert, muss neu nachrechnen**, denn
der Live-Betrieb verlangt einen Bericht zu genau diesem Fingerabdruck. Das ist
die Zusage von der Website, hier im Code durchgesetzt.

### Kursdaten

Eine CSV mit den Spalten Zeit, Open, High, Low, Close und optional Volumen:

```csv
time,open,high,low,close,volume
2024-01-02T08:00:00Z,2063.21,2068.40,2061.80,2067.10,14820
```

Spaltennamen dürfen abweichen (`date`, `timestamp`, `o/h/l/c` …), Zeiten dürfen
ISO-Text oder Unix-Zeitstempel sein, Zeiten ohne Zone gelten als UTC. Im
Repository liegen **keine** Kursdaten — die kommen vom Broker oder Datenanbieter.

## Betrieb

```bash
python3 -m bengx_bot --config config.toml paper --once    # ein Durchlauf, z. B. per Cron
python3 -m bengx_bot --config config.toml paper --loop    # durchgängig
```

Der Runner verarbeitet nur Kerzen, die seit dem letzten Lauf dazugekommen sind,
und sichert Kapitalstand, offene Positionen und die zuletzt gesehene Kerze in
`state/state.json`. Ein Neustart eröffnet deshalb nichts doppelt. Gehört der
gespeicherte Zustand zu einem anderen Regelwerk, bricht der Bot ab, statt mit
fremden Positionen weiterzurechnen.

Nach jedem Durchlauf schreibt er `signals.json` — genau das Format, das die
Website im Bereich **G** liest. Die Kette ist damit geschlossen: Kerze → Signal
→ Position → Protokoll → Website.

## Echtes Geld

Noch nicht möglich, und das ist Absicht. `live` prüft der Reihe nach:

1. `live.enabled = true` muss bewusst gesetzt sein.
2. Ein Backtest-Bericht zum aktuellen Fingerabdruck muss vorliegen.
3. Ein Broker-Anschluss muss eingetragen sein.

An Punkt 3 bricht es ab: ein echter Anschluss braucht Zugangsdaten und gehört in
eine eigene Klasse nach dem Vorbild von `Broker` in `broker.py` — mit den
Schlüsseln aus der Umgebung, niemals im Repository. Bis dahin läuft alles auf
dem Papierkonto, mit demselben Code.

## Aufbau

| Datei | Aufgabe |
| --- | --- |
| `indicators.py` | EMA, ATR, RSI, ADX, Donchian — ohne numpy |
| `model.py` | Kerze, Signal, Position, Trade |
| `config.py` | TOML laden, prüfen, Fingerabdruck bilden |
| `strategy.py` | das Regelwerk |
| `risk.py` | Positionsgröße und alle Grenzen |
| `broker.py` | Papierkonto mit Kosten, Schnittstelle für echte Broker |
| `engine.py` | Positionsführung — Backtest und Live teilen sich diesen Code |
| `backtest.py` | Durchlauf über historische Kerzen plus Kennzahlen |
| `journal.py` | Protokoll als JSONL, Ausgabe für die Website |
| `state.py` | Zustand über Neustarts hinweg |
| `runner.py` | Betrieb, Not-Aus, Live-Sperre |
| `cli.py` | Kommandozeile |

Backtest und Live benutzen **dieselbe** `engine.py`. Was der Test prüft, läuft
später auch wirklich so.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

89 Tests. Sie decken die Indikatoren, jede einzelne Regel, die Risikogrenzen,
die Kostenrechnung des Brokers, die Ausstiegslogik (kein Blick in die Zukunft,
Stop vor Ziel, Trailing nur enger), den Backtest, das Protokollformat und die
Live-Sperre ab.

## Was dieser Bot nicht ist

Er ist **kein Versprechen auf Gewinn**. Das Regelwerk ist sauber umgesetzt und
getestet — ob es auf echten Golddaten Geld verdient, zeigt erst ein Backtest auf
echten Kursen und danach ein langer Lauf auf dem Papierkonto. Die Zahlen aus
`selftest` und `--synthetic` stammen aus einem Zufallspfad und sagen über den
Markt nichts aus.

Keine Anlageberatung. Der Handel mit Gold und Hebelprodukten kann zum
Totalverlust führen.
