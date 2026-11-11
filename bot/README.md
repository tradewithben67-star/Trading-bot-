# Die Bots

Die drei Bots aus dem Bereich **X** der Website, alle auf XAU/USD:

| `[bot] name` | Bot | Zeitrahmen | Idee |
| --- | --- | --- | --- |
| `dauerlaeufer` | **Dauerläufer** | 1h | Trendfolge: Ausbruch im gerichteten Markt |
| `swing` | **Swing** | 1m (+5m, 1h) | Liquiditäts-Sweep, Fortsetzung, Einstieg in die Lücke |
| `kopierer` | **Signal-Kopierer** | beliebig | spiegelt Bens Signale aus einer `signals.json` |

Beide erfüllen dieselbe Schnittstelle und teilen sich Maschine, Risikosteuerung,
Backtest, Protokoll und Not-Aus. Reines Standard-Python ab 3.11, keine
Abhängigkeiten, kein `pip install`.

## Schnellstart

```bash
cd bot

python3 -m bengx_bot rules              # Regelwerk des Dauerläufers
python3 -m bengx_bot --bot swing rules  # Regelwerk des Swing-Bots
python3 -m bengx_bot --bot kopierer rules
python3 -m bengx_bot selftest           # Mechanik auf erfundenen Daten prüfen
python3 -m unittest discover -s tests -t .   # 171 Tests

cp config.example.toml config.toml      # anpassen
python3 -m bengx_bot --config config.toml backtest --csv data/xauusd_h1.csv
python3 -m bengx_bot --config config.toml paper --once
```

## Dauerläufer

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

## Swing

Ein Modell über drei Zeitrahmen. Jede Stufe hat eine Frist; läuft sie ab oder
kommt ein neuer Sweep, beginnt alles von vorn.

| Stufe | Zeitrahmen | Was passieren muss | Frist |
| --- | --- | --- | --- |
| 1 | **1h** | Eine Stundenkerze sticht unter das jüngste offene Swing-Tief und schließt wieder darüber — die Liquidität ist abgeräumt | — |
| 2 | **5m** | Eine Fortsetzungskerze bestätigt die Richtung: fester Körper, Schluss über dem Hoch der Vorkerze | 120 min |
| 3 | **1m** | Bruch der Struktur (Schluss über dem letzten bestätigten Swing-Hoch) **oder** eine Fair-Value-Gap | 60 min |
| 4 | **1m** | Einstieg: Pullback in die Lücke (Limit in der Mitte) **oder** Entstehung einer invertierten Lücke | 60 min |

Short läuft spiegelbildlich: Sweep über ein Swing-Hoch, Schluss darunter.

**Fair-Value-Gap**: drei Kerzen, bei denen das Tief der dritten über dem Hoch
der ersten liegt. In dieser Zone wurde nicht gehandelt — der Kurs kommt
erfahrungsgemäß zurück, um sie zu füllen. Der Einstieg ist ein Limit darin.

**Invertierte Lücke (IFVG)**: eine gegenläufige Gap, durch die der Kurs
schließt. Damit dreht ihre Bedeutung — was vorher Widerstand war, trägt jetzt
von unten. Der Einstieg erfolgt zu diesem Schluss.

Stop: unter dem Tief, das sich seit dem Sweep gebildet hat, plus Puffer
(`stop_source = "structure"`). Alternativ unter dem Sweep-Tief selbst
(`"sweep"`) — das liegt oft so weit weg, dass `max_stop_pips` den Trade
ablehnt, und genau das soll die Grenze leisten. Ziel: 3 R, Teilverkauf bei
1,5 R, danach Trailing.

Der Swing-Bot braucht **Minutenkerzen** in `data.csv`. Die Fünf-Minuten- und
Stundenkerzen rechnet er selbst daraus, auf vollen Vielfachen ausgerichtet; eine
noch laufende Kerze benutzt er nie.

## Signal-Kopierer

Er denkt sich nichts aus: er liest Bens Signale und spiegelt sie. Die Quelle ist
dieselbe `signals.json`, die die Website im Bereich **G** liest — als Datei auf
der Platte oder über eine Adresse im Netz (`copy.source = "http"`).

**Übernommen** werden Richtung, Stop und Ziel. **Nicht übernommen** werden zwei
Dinge, und das ist der Kern:

* **Die Positionsgröße.** Sie kommt aus dem eigenen Kontostand und dem eigenen
  Risiko je Trade. Bens Größe passt auf Bens Konto, nicht auf deins.
* **Der Einstiegskurs um jeden Preis.** Ist der Kurs seit Bens Einstieg
  weggelaufen, steigt der Bot nicht hinterher, sondern lässt das Signal aus
  (`entry_mode = "limit"`, Toleranz über `max_slippage_pips`). Wer chasen will,
  stellt auf `"market"`.

Ein Signal wird ausgelassen, wenn es älter als `max_age_minutes` ist, der Kurs
zu weit weg ist, es beim Eintreffen schon geschlossen war, der Stop-Abstand
außerhalb der Grenzen liegt oder Bens Stop auf der falschen Seite des eigenen
Einstiegs läge. Jeder Grund steht im Protokoll — der Bot verschweigt nicht, was
er ausgelassen hat.

Schließt Ben, schließt der Kopierer mit (`close_with_source`). Der eigene Stop
hat trotzdem Vorrang: wird er in derselben Kerze getroffen, gilt er.

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
| `strategy.py` | Regelwerk des Dauerläufers |
| `swing.py` | Regelwerk des Swing-Bots |
| `copier.py` | Signal-Kopierer samt Datei- und HTTP-Quelle |
| `timeframes.py` | 5m und 1h aus Minutenkerzen, Swing-Punkte, Sweeps, FVGs |
| `bots.py` | welcher Bot läuft |
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

171 Tests. Sie decken die Indikatoren, jede einzelne Regel aller drei Bots, die
Zeitrahmen-Aggregation, Swing-Punkte, Sweeps und Lücken, die Risikogrenzen, die
Kostenrechnung des Brokers, die Ausstiegslogik (kein Blick in die Zukunft, Stop
vor Ziel, Trailing nur enger), den Backtest, das Protokollformat und die
Live-Sperre ab.

Beim Kopierer läuft ein Test die ganze Kette: der Dauerläufer handelt, seine
Signale gehen als `signals.json` hinaus, der Kopierer liest sie und spiegelt
jedes einzelne — mit anderem Konto und anderer Größe.

Beim Swing-Bot prüft ein Test ausdrücklich, dass derselbe Einstieg entsteht,
wenn man die Daten vorher abschneidet: der Ablauf wird aus den Kerzen
gerechnet und nicht über Aufrufe angesammelt. Nach einem Neustart handelt der
Bot deshalb genauso wie im Backtest.

## Was dieser Bot nicht ist

Sie sind **kein Versprechen auf Gewinn**. Die Regelwerke sind sauber umgesetzt
und getestet — ob sie auf echten Golddaten Geld verdienen, zeigt erst ein
Backtest auf echten Kursen und danach ein langer Lauf auf dem Papierkonto. Die Zahlen aus
`selftest` und `--synthetic` stammen aus einem Zufallspfad und sagen über den
Markt nichts aus.

Keine Anlageberatung. Der Handel mit Gold und Hebelprodukten kann zum
Totalverlust führen.
