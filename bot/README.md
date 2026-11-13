# Die Bots

Die vier Bots aus dem Bereich **X** der Website, alle auf XAU/USD:

| `[bot] name` | Bot | Zeitrahmen | Idee |
| --- | --- | --- | --- |
| `dauerlaeufer` | **Dauerläufer** | 1h | Trendfolge: Ausbruch im gerichteten Markt |
| `swing` | **Swing** | 1m (+5m, 1h) | Liquiditäts-Sweep, Fortsetzung, Einstieg in die Lücke |
| `einzelschuss` | **Einzelschuss** | 1m | zwei Order um eine Nachricht, eine wird gehandelt |
| `kopierer` | **Signal-Kopierer** | beliebig | spiegelt Bens Signale aus einer `signals.json` |

Alle erfüllen dieselbe Schnittstelle und teilen sich Maschine, Risikosteuerung,
Backtest, Protokoll und Not-Aus. Reines Standard-Python ab 3.11. Für den Handel selbst gibt es keine
Abhängigkeiten; nur das freie Schreiben in Telegram braucht `anthropic`.

## Schnellstart

```bash
cd bot

python3 -m bengx_bot rules              # Regelwerk des Dauerläufers
python3 -m bengx_bot --bot swing rules  # Regelwerk des Swing-Bots
python3 -m bengx_bot --bot einzelschuss rules
python3 -m bengx_bot --bot kopierer rules
python3 -m bengx_bot konto              # Verbindung zu MetaTrader 5 prüfen
python3 -m bengx_bot lernen             # was die bisherigen Trades sagen
python3 -m bengx_bot selftest           # Mechanik auf erfundenen Daten prüfen
python3 -m unittest discover -s tests -t .   # 438 Tests

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

## Einzelschuss

Das Vorbild läuft als MetaTrader-EA auf XAU/USD: zwei Order um eine Nachricht,
**eine** davon wird ausgeführt, die andere gestrichen. Kein Nachkaufen, kein
Netz, keine Verdopplung — daher der Name.

| Schritt | Was passiert |
| --- | --- |
| 1 | **Scharfmachen** — 60 s vor dem Termin steht der Referenzkurs fest: der Schluss der letzten Kerze, die davor fertig ist. Darüber und darunter liegt je eine Stop-Order, 15 Pips entfernt |
| 2 | **Ruhe davor** — war die Spanne der letzten 15 Minuten größer als 60 Pips, wird nicht gehandelt. Eine laufende Bewegung sägt die Straddle auf, bevor die Nachricht da ist |
| 3 | **Einzelschuss** — die erste Seite, die berührt wird, wird gehandelt; die andere Order verfällt im selben Augenblick |
| 4 | **Frist** — wird in 5 Minuten keine Seite berührt, verfallen beide. Der Termin ist dann vorbei |

Stop und Ziel stehen in **Pips**, nicht in ATR: bei einer Nachricht geht es um
die ersten Minuten, nicht um die Tagesvolatilität. Beide messen sich an der
Orderstufe, nicht am Fill — dort, wo sie in der Plattform eingetragen würden.

### Woher die Termine kommen

```toml
trigger = "kalender"     # Termine aus news.json
trigger = "ausbruch"     # ohne Kalender
```

Mit **Kalender** liest der Bot `news.json`; `news.example.json` zeigt das
Format. Gehandelt wird nur, was in `impacts` steht — üblich sind CPI, PPI, NFP
und FOMC. Ein unlesbarer Zeitstempel in der Datei bricht den Lauf ab, statt
stillschweigend einen Termin zu verschlucken, an dem der Bot dann nicht handelt.

Mit **Ausbruch** braucht er keine Datei: eine Minutenkerze, deren Spanne 3 × ATR
erreicht und mindestens 30 Pips misst, gilt selbst als Ereignis. Die Order
liegen dann über ihrem Hoch und unter ihrem Tief. Das ist der Weg, wenn niemand
den Kalender pflegt.

### Zwei Dinge, die den Backtest ehrlich halten

**Beide Seiten in einer Minute.** Werden Kauf- und Verkaufsstufe in derselben
Minutenkerze berührt, ist aus Kerzendaten nicht zu erkennen, welche zuerst kam.
Dann gilt die ungünstige Annahme (`tie_break = "pessimistic"`): gehandelt wird
die Seite *gegen* die Richtung der Kerze — also die, die anschließend in den
Stop läuft. `"skip"` lässt solche Termine stattdessen aus; das sieht hübscher
aus, als es ist, weil es gerade die Fehlausbrüche entfernt.

**Der Stop in der Eröffnungsminute.** Bei allen anderen Bots wird der Stop erst
ab der Kerze nach dem Einstieg geprüft — bei Stundenkerzen wäre alles andere
geraten. Der Einzelschuss schaltet das ab (`stop_on_entry_bar`): bei einer
Nachricht fallen Einstieg und Stop oft in dieselbe Minute, und wer das übergeht,
schönt den Backtest genau an der Stelle, auf die es ankommt.

Dazu kommt `news_slippage_pips`: ein Aufschlag auf den Fill, weil im
Nachrichtenmoment keine Stop-Order zum Wunschkurs füllt. Er geht gegen die
eigene Richtung, vergrößert damit das gerechnete Risiko und schlägt so auch auf
die Positionsgröße durch. Lieber zu hoch ansetzen als zu niedrig.

### Grenzen

Höchstens 2 Termine am Tag, mindestens 30 Minuten zwischen zwei Trades, und pro
Termin genau ein Trade — auch wenn er sofort in den Stop läuft. Es gibt kein
zweites Mal.

Der Bot braucht **Minutenkerzen** in `data.csv`.

## Am Konto: MetaTrader 5

Tradequo läuft über MetaTrader 5. Der Anschluss steht in `mt5.py` und erfüllt
dieselbe Schnittstelle wie das Papierkonto — die Maschine merkt keinen
Unterschied, der Markt schon.

**Nur unter Windows.** Das Paket `MetaTrader5` gibt es für kein anderes System.
Auf Linux und Mac bleibt der Bot auf dem Papierkonto; der Anschluss lässt sich
dort bis auf den letzten Schritt prüfen, aber nicht betreiben.

### In sechs Schritten

1. **MetaTrader 5 installieren**, Demokonto beim Broker anlegen, im Terminal
   anmelden. Unter *Extras → Optionen → Expert Advisors* den **Algo-Handel
   erlauben**.
2. **Symbolnamen nachsehen.** Im Fenster *Marktübersicht* steht, wie dein
   Broker Gold nennt: `XAUUSD`, `XAUUSD.r`, `GOLD`, `GOLD.m` — das kommt in
   `config.toml` unter `[mt5] symbol`.
3. **`.env` ausfüllen** (`.env.example` zeigt alles): `MT5_LOGIN`,
   `MT5_PASSWORD` (das Handels-, nicht das Investorpasswort) und `MT5_SERVER`.
   Die Datei steht in `.gitignore` und verlässt deinen Rechner nicht.
4. **`konto.bat` doppelklicken.** Das handelt nichts, sondern zeigt nur, ob
   die Verbindung steht — und was der Bot an diesem Konto handeln *würde*.
5. **`config.toml`** aus `config.example.toml` anlegen, `[bot] name` auf den
   gewünschten Bot stellen, `[live] enabled = true` und `broker = "mt5"`.
6. **`handeln.bat` doppelklicken.** Es prüft erst die Verbindung und startet
   den Bot nur, wenn sie steht.

Not-Aus: die Datei `state/KILLSWITCH` anlegen. Beim nächsten Durchlauf wird
alles geschlossen und nichts Neues eröffnet. `/aus` in Telegram tut dasselbe.

### Demokonto und Echtgeld

Der Bot fragt **MT5 selbst**, was für ein Konto das ist — nicht die
Konfiguration.

| Konto | Backtest nötig? |
| --- | --- |
| Demo- oder Wettbewerbskonto | nein, `live.allow_demo_without_backtest` steht auf `true` |
| Echtgeldkonto | **immer**, und daran ändert kein Schalter etwas |

Ausprobieren ist der Sinn eines Demokontos. Echtes Geld wird vorher
nachgerechnet.

### Was der Anschluss richtig macht

* **Unzen und Lots.** Der Bot rechnet in Unzen, MT5 in Lots; bei Gold ist ein
  Lot meist 100 Unzen. Wer das verwechselt, handelt das Hundertfache.
  Gerundet wird **ab**, und was unter der Mindestmenge landet, wird nicht
  gehandelt — mit Begründung.

  Praktisch heißt das: Mit 0,5 % Risiko und 25 Pips Stop braucht es rund
  **500 € Kapital**, damit überhaupt eine handelbare Menge herauskommt. Darunter
  bleibt der Bot stehen. Genau deshalb empfehlen die Leute, die solche Bots
  verkaufen, ein **Cent-Konto** — dort wiegt ein Lot ein Hundertstel.

* **Serverzeit.** Die meisten Broker stellen ihren Server auf UTC+2 oder UTC+3.
  Der Einzelschuss hängt an Terminen in UTC; zwei Stunden Versatz und er
  handelt die falsche Minute. Der Bot misst den Versatz am laufenden Kurs.
  Am Wochenende geht das nicht — dann `mt5.server_utc_offset_hours` eintragen.

* **Der Broker schließt, nicht der Bot.** Stop und Ziel liegen als echte SL/TP
  im Terminal. Die meisten Trades enden dort. Jeder Durchlauf gleicht deshalb
  zuerst ab, was das Terminal seit dem letzten Mal geschlossen hat, und holt
  es ins Protokoll. Ohne das stünde dort nur, was die Maschine selbst
  geschlossen hat — und das wären ausgerechnet die wenigsten.

* **Gebucht wird der Fill.** Nicht der Kurs, den die Strategie wollte. Der
  Unterschied ist die Slippage, und die gehört ins Protokoll, nicht ins
  Vergessen.

* **Fremde Trades bleiben fremd.** Der Bot fasst nur Positionen mit seiner
  eigenen `magic`-Kennung an. Was du von Hand öffnest, rührt er nicht an.

### Einzelschuss am Terminal

Hier liegt die wichtigste Einschränkung, und sie ist eine Frage der Bauart.

Die Maschine bewertet **abgeschlossene** Minutenkerzen und schickt danach eine
**Marktorder**. Zwischen dem Augenblick, in dem die Orderstufe berührt wird,
und der Order liegt damit bis zu eine Minute — ausgerechnet die, in der sich
der Kurs am schnellsten bewegt. Ein echter Nachrichten-EA legt stattdessen
**Stop-Order ins Terminal**, die genau an der Stufe auslösen.

Was das ausmacht, misst der Bot selbst. In einem Probelauf gegen ein
nachgebautes Terminal lagen die Einstiege im Mittel **21 Pips neben der
Stufe** — bei einem Orderabstand von 15 und einem Stop von 25 Pips ist das
nicht mehr dieselbe Strategie.

`python -m bengx_bot lernen` meldet das als eigenen Befund, sobald es auftritt.
Solange es auftritt, gilt: **der Einzelschuss auf MT5 prüft die Mechanik, nicht
das Regelwerk.** Wer das dicht haben will, braucht echte Pending-Order mit
Gegenseitig-Löschen — das ist der nächste Bauabschnitt und steht noch aus.

Die anderen drei Bots trifft das kaum: Dauerläufer, Swing und Kopierer hängen
nicht an einer Stufe, die auf die Sekunde getroffen werden muss.

## Aus Fehlern lernen

```bash
python3 -m bengx_bot lernen
```

Der Bot **verstellt keine Regel selbst**, und das ist Absicht. Bei höchstens
zwei Terminen am Tag kommen im Monat vierzig Trades zusammen. Aus vierzig
Zahlen lässt sich kein Parameter schätzen, der morgen noch gilt — man fittet
Rauschen. Eine Automatik, die nach drei Verlusten den Abstand verstellt, hätte
am Ende ein Regelwerk, das zu genau diesen drei Verlusten passt. Dazu käme,
dass sie still ändert, wogegen du gerade prüfst: der Fingerabdruck wandert,
der Backtest gilt nicht mehr, und niemand weiß hinterher, welche Fassung
welche Zahlen gemacht hat.

Stattdessen hält jeder Trade sein Umfeld fest — Termin, Richtung, Spread beim
Einstieg, Slippage, Abweichung von der gewollten Stufe, Haltedauer — und
`lernen` rechnet daraus Befunde:

| Befund | Was dahintersteckt |
| --- | --- |
| Order füllen schlechter als gerechnet | `news_slippage_pips` ist zu optimistisch |
| Der Bot steigt woanders ein, als er will | die Bauart oben — Marktorder statt Stop-Order |
| Spread beim Einstieg breiter als angenommen | `costs.spread_pips` schönt den Backtest |
| Order werden vom ersten Ausschlag abgeholt | `offset_pips` zu eng |
| Positionen an der Mindestmenge | das Konto trägt das eingestellte Risiko nicht |
| Termin X kostet bisher | Kandidat zum Streichen aus `news.json` |
| Die meisten Trades laufen in den Zeitstop | die Bewegung kam gar nicht |

Jeder Befund nennt **seine Stückzahl**. Unter acht Fällen steht ausdrücklich
dabei, dass es für eine Aussage nicht reicht. Ein Muster aus drei Trades ist
kein Muster.

Was du übernehmen willst, trägst du selbst ein — in `config.toml` oder in der
Bot-Konsole — und rechnest danach neu nach.

## Assistent in Telegram

Ein Bot, dem man normal schreibt. Er läuft auf derselben Maschine wie der
Handelsbot und liest dessen Protokoll, Zustand und Aufgaben.

**Unter Windows:** `einrichten.bat` doppelklicken, danach `starten.bat`.
Hakt etwas: `pruefen.bat` — es sagt, welcher Token gilt, welche Modelle dein
Schlüssel benutzen darf und was der Anbieter wirklich antwortet.
**Unter macOS oder Linux:**

```bash
python3 einrichten.py    # legt .env an und holt die Chat-Kennung selbst
python3 -m bengx_bot telegram
```

`einrichten.py` fragt nach dem Token, prüft ihn gegen Telegram, wartet auf
deine erste Nachricht an den Bot, trägt die Chat-Kennung automatisch ein und
sagt dir, welche Pakete noch fehlen. Der Token wird dabei nicht angezeigt und
landet nur in `.env`.

Von Hand geht es auch: `cp .env.example .env` und ausfüllen.

**Wer antwortet — Gemini oder Claude:**

| | Gemini (Google) | Claude (Anthropic) |
| --- | --- | --- |
| Kosten | kostenloses Kontingent | kostet, getrennt vom Claude-Abo |
| Schlüssel | aistudio.google.com | platform.claude.com |
| Paket | `pip install google-genai` | `pip install anthropic` |
| Antworten, Werkzeuge, Bilder | ja | ja |
| Websuche | ja (Google-Suche) | ja (Claudes Suche) |
| Am Code weiterbauen | nein | ja |
| Daten | beim kostenlosen Kontingent wertet Google die Inhalte zur Verbesserung seiner Dienste aus | nicht zum Training |

Einer von beiden reicht. Es wird der genommen, für den ein Schlüssel da ist;
sind beide da, gewinnt Claude. `BENGX_ANBIETER=gemini` erzwingt die Wahl.
Beide bekommen dieselben Werkzeuge und dieselbe Anweisung — was der Bot
**kann**, hängt also nicht daran, wer antwortet, nur wie gut.

**Was du brauchst — drei Dinge:**

1. **Einen Bot-Token.** In Telegram [@BotFather](https://t.me/BotFather) anschreiben,
   `/newbot`, Namen vergeben, Token kopieren → `TELEGRAM_TOKEN` in `.env`.
2. **Deine Chat-Kennung.** `TELEGRAM_CHAT_ID` leer lassen, den Bot starten, ihm
   schreiben — er nennt dir die Kennung. Eintragen, neu starten. **Nur dieser
   Chat wird bedient**, alle anderen bekommen eine Absage. Ohne diesen Schritt
   könnte jeder, der den Bot findet, deinen Not-Aus betätigen.
3. **Einen Schlüssel für Gemini oder Claude**, wenn er frei antworten soll.
   Ohne laufen die Befehle trotzdem. Das Einrichtungsprogramm fragt, welchen
   du willst.

`.env` steht in `.gitignore` und gehört dort auch hin. Token und Schlüssel
niemals in den Code.

Er sucht auch im Netz, wenn es um Kurse, Termine oder Nachrichten geht — über
die Suche des jeweiligen Anbieters, ohne weiteren Dienst und ohne zweiten
Schlüssel. Abschalten mit `BENGX_WEBSUCHE=0`.

### Am Code weiterbauen

**Nur mit Claude.** Schreibst du „baue an der Website weiter“ oder „repariere
das“, startet auf derselben Maschine ein richtiger Coding-Agent ([Claude Agent
SDK](https://code.claude.com/docs/en/agent-sdk)): er liest die Dateien, ändert
sie, führt die Tests aus und committet.

```bash
pip install claude-agent-sdk
# in .env:  BENGX_CODER=1
```

**Standardmäßig aus.** Vier Grenzen sind eingebaut, weil beim Bauen niemand
danebensitzt:

| Grenze | Standard |
| --- | --- |
| Muss eingeschaltet werden | `BENGX_CODER=1` |
| Arbeitet nur in einem Ordner | `BENGX_REPO`, sonst nirgends |
| Höchstens so viele Schritte | 40 |
| Höchstens so viel Geld je Auftrag | 2 US-Dollar |
| Abbruch nach | 15 Minuten |

Dazu steht in seiner Anweisung: **kein `git push`**, keine Zugangsdaten
anfassen, nichts unter `state/` ändern, und nach jeder Änderung am Bot die
Tests laufen lassen. Committen darf er; nach außen schiebst du selbst.

Weil das Minuten dauert, meldet er sich sofort („ich fange an“) und schickt am
Ende, was er geändert hat.

**Befehle:**

| Befehl | Was er tut |
| --- | --- |
| `/stand` | Kapital, offene Positionen, Zahlen von heute und gesamt, Not-Aus |
| `/signale [heute\|woche\|monat\|alles]` | die letzten Signale mit Pips und Grund |
| `/regeln [bot]` | das Regelwerk im Klartext |
| `/aufgabe <text>` | Problem notieren; Claude Code arbeitet die Liste ab |
| `/aufgaben` | offene Aufgaben zeigen |
| `/aus` / `/an` | Not-Aus setzen und wieder lösen |
| `/neu` | Gesprächsfaden vergessen |

Alles andere geht an Claude, zusammen mit einem Abschnitt **LAGE** aus den
echten Zahlen des Bots. Die Anweisung verbietet ihm, Zahlen zu schätzen: steht
etwas nicht in der Lage, sagt er das. **Bilder** sieht er sich an — ein
Screenshot vom Chart oder von einer Fehlermeldung reicht.

Der Bot fragt bei Telegram nach draußen (langer Abruf) und braucht deshalb
**keine öffentliche Adresse**, keinen Server und keine Portfreigabe. Er muss
nur laufen: auf deinem Rechner, einem Raspberry Pi oder einem kleinen Server.

Das Modell ist `claude-opus-5-5` mit niedrigem Aufwand — schnell und günstig für
kurze Antworten. Über `BENGX_MODEL` und `BENGX_EFFORT` änderbar.

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

`live` prüft der Reihe nach:

1. `live.enabled = true` muss bewusst gesetzt sein.
2. `live.broker` muss ein Anschluss sein, den es gibt — eingebaut ist `"mt5"`.
3. **Was für ein Konto das ist, sagt MT5 selbst.** Meldet es ein Übungskonto,
   darf der Bot ohne Backtest handeln. Meldet es Echtgeld, muss ein
   Backtest-Bericht zum aktuellen Fingerabdruck vorliegen — und das lässt sich
   nicht abschalten.

Der Anschluss steht in `mt5.py` und ist fertig; wie man ihn einrichtet, steht
oben unter [Am Konto: MetaTrader 5](#am-konto-metatrader-5). **Er läuft nur
unter Windows**, weil es das Paket `MetaTrader5` nur dort gibt.

Für einen anderen Broker gehört eine eigene Klasse nach dem Vorbild von
`Broker` in `broker.py` daneben — mit den Zugangsdaten aus der Umgebung,
niemals im Repository. Zu bauen sind vier Methoden; `PaperBroker` und
`MT5Broker` zeigen beide, was sie zurückgeben müssen.

Ein Hinweis zum Wochenende: Tradequo bietet mit **GOLD247** seit September 2026
auch samstags und sonntags Gold an. Beide Bots stellen freitags trotzdem glatt
(`friday_cutoff_hour`), weil am Wochenende die Spreads weiter und die Umsätze
dünner sind. Wer das ändern will, setzt die Stunde hoch — und sollte vorher
nachrechnen, was die breiteren Spreads kosten.

## Aufbau

| Datei | Aufgabe |
| --- | --- |
| `indicators.py` | EMA, ATR, RSI, ADX, Donchian — ohne numpy |
| `model.py` | Kerze, Signal, Position, Trade |
| `config.py` | TOML laden, prüfen, Fingerabdruck bilden |
| `strategy.py` | Regelwerk des Dauerläufers |
| `swing.py` | Regelwerk des Swing-Bots |
| `news.py` | Regelwerk des Einzelschuss samt Kalender |
| `mt5.py` | Anschluss an MetaTrader 5: Order, Kerzen, Konto, Abgleich |
| `lernen.py` | wertet die Trades aus und schlägt Änderungen vor |
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
| `report.py` | Lagebericht aus Protokoll, Zustand und Aufgaben |
| `assistant.py` | der Chat-Teil: Werkzeuge, Anweisung, Gesprächsfaden |
| `llm.py` | die beiden Anbieter Gemini und Claude hinter einer Schnittstelle |
| `telegram.py` | Telegram-Anbindung, langer Abruf, Befehle |
| `cli.py` | Kommandozeile |
| `einrichten.py` | Einrichtung: .env anlegen, Token prüfen, Chat-Kennung holen |
| `einrichten.bat`, `starten.bat`, `pruefen.bat` | zum Doppelklicken unter Windows |
| `konto.bat`, `handeln.bat` | Verbindung prüfen, Bot am Konto starten |

Backtest und Live benutzen **dieselbe** `engine.py`. Was der Test prüft, läuft
später auch wirklich so.

## Tests

```bash
python3 -m unittest discover -s tests -t .
```

438 Tests. Sie decken die Indikatoren, jede einzelne Regel aller vier Bots, die
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
