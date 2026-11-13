# Den Bot ans Konto bringen — Schritt für Schritt

Einmal durch, etwa 30 Minuten. **Alles passiert auf deinem Windows-Rechner.**

> **Warum Windows:** Der Bot handelt über MetaTrader 5, und das dafür nötige
> Paket `MetaTrader5` gibt es nur für Windows. Auf Mac und Linux läuft der Bot,
> aber nur auf dem Papierkonto.

> **Demokonto, nicht Echtgeld.** Der Bot handelt an einem Übungskonto ohne
> Vorbedingung. An einem Echtgeldkonto verlangt er einen Backtest über echte
> Golddaten — den gibt es noch nicht, und das ist keine Einstellung, die man
> wegklicken kann.

---

## Teil 1 — Python installieren

Überspringen, wenn schon da: Windows-Taste drücken, `cmd` eingeben, im
schwarzen Fenster `py -3 --version` tippen. Kommt eine Versionsnummer ab
**3.11**, ist alles gut.

1. **[python.org/downloads/windows](https://www.python.org/downloads/windows/)**
   öffnen und den obersten *Windows installer (64-bit)* laden.
2. Installer starten. **Ganz unten das Häkchen bei
   „Add python.exe to PATH" setzen** — ohne das findet Windows Python später
   nicht.
3. *Install Now*, fertig.

---

## Teil 2 — MetaTrader 5 und ein Demokonto

1. **MT5 holen.** Am besten von **Tradequo selbst** (dort ist ihr Server schon
   eingetragen). Geht auch allgemein über
   **[metatrader5.com/de/download](https://www.metatrader5.com/de/download)**.
2. Installieren und starten.
3. **Demokonto anlegen:** Menü *Datei → Konto eröffnen*, den Broker suchen,
   **Demokonto** wählen. MT5 zeigt dir danach **Kontonummer, Passwort und
   Server** — **diese drei aufschreiben**, du brauchst sie in Teil 4.
4. **Algo-Handel erlauben:** *Extras → Optionen → Expert Advisors* →
   Häkchen bei **„Algorithmischen Handel erlauben"**. Ohne das lehnt MT5
   jede Order des Bots ab.
5. **Gold-Symbol:** Musst du nicht suchen — `konto.bat` in Teil 5 sagt dir,
   wie dein Broker Gold nennt, und listet die Namen zum Abschreiben auf.
   Wer trotzdem nachsehen will: Fenster *Marktübersicht* (Strg+M).
6. **Chart öffnen:** Gold doppelklicken, Zeitrahmen **M1**. Dadurch lädt MT5
   die Kursgeschichte, die der Bot braucht.

**MT5 muss laufen und angemeldet sein, solange der Bot handelt.**

---

## Teil 3 — Den Bot herunterladen

Der Code liegt noch im Zweig zur offenen Pull-Request, nicht im Hauptzweig:

1. **[Diesen Zweig als ZIP laden](https://github.com/tradewithben67-star/Trading-bot-/archive/refs/heads/claude/practical-gates-l1vda5.zip)**
2. ZIP **entpacken**, zum Beispiel nach `C:\BENGX`.
3. In den Ordner **`bot`** hineingehen. Dort liegen `konto.bat` und
   `handeln.bat` — die brauchst du gleich.

Die zugehörige Pull-Request:
**[#1](https://github.com/tradewithben67-star/Trading-bot-/pull/1)**

---

## Teil 4 — Zugangsdaten eintragen

1. **`konto.bat` doppelklicken.** Beim ersten Mal legt es `.env` an und öffnet
   sie im Editor.
2. **Ganz unten** die drei Zeilen aus Teil 2 ausfüllen:

   ```
   MT5_LOGIN=12345678
   MT5_PASSWORD=dein-Handelspasswort
   MT5_SERVER=Tradequo-Demo
   ```

   * **Handelspasswort**, nicht das Investorpasswort — das darf nicht handeln.
   * Der Servername muss **genau** so geschrieben sein wie in MT5.
   * Kein Leerzeichen um das `=`, keine Anführungszeichen.
3. Speichern und schließen.

`.env` steht in `.gitignore` und verlässt deinen Rechner nicht.

---

## Teil 5 — Verbindung prüfen (hier wird nichts gehandelt)

**`konto.bat` noch einmal doppelklicken.** Es installiert beim ersten Mal das
MT5-Paket und zeigt dann:

```
Konto      12345678 bei Tradequo-Demo
Art        Demokonto
Kapital    10000.00 EUR (Hebel 1:100)
Handel     erlaubt

Symbol     XAUUSD
Ein Lot    100 Unzen
Menge      0.01 bis 50 Lots, Schritt 0.01
Spread     3.0 Pips (2000.00 / 2000.30)
Serverzeit UTC+2.0 Stunden

Bei 0.50% Risiko und 25 Pips Stop:
  20.00 Unzen = 0.2 Lots je Trade
```

**Das ist der Prüfpunkt.** Steht da „Demokonto" und eine Lotgröße, geht es
weiter. Sonst unten in der Fehlertabelle nachsehen.

> **Wichtig:** Steht bei *Art* **ECHTGELDKONTO**, hör hier auf. Der Bot würde
> ohnehin nicht handeln, aber du solltest wissen, dass du das falsche Konto
> verbunden hast.

---

## Teil 6 — Einstellen

`config.toml` im Ordner `bot` mit dem Editor öffnen (hat `konto.bat` schon
angelegt). Vier Stellen ändern:

```toml
[bot]
name = "einzelschuss"            # welcher Bot laufen soll

[einzelschuss]
trigger = "ausbruch"             # fürs Erste: kein Kalender nötig

[mt5]
symbol = "XAUUSD"                # dein Name aus Teil 2, Schritt 5

[live]
enabled = true                   # sonst handelt er nicht
broker = "mt5"
```

**Warum `trigger = "ausbruch"`:** So braucht der Bot keine Terminliste. Er
behandelt jede Minutenkerze, die aus der Ruhe ausbricht, als Ereignis. Das
läuft sofort. Die Kalender-Fassung kommt in Teil 8.

**Welcher Bot?** `einzelschuss` ist der aus dem TikTok. Es gehen auch
`dauerlaeufer` (Trendfolge, braucht `timeframe_minutes = 60` unter `[mt5]`),
`swing` oder `kopierer`.

---

## Teil 7 — Laufen lassen

**`handeln.bat` doppelklicken.** Es prüft erst die Verbindung und startet den
Bot nur, wenn sie steht. Dann:

```
Konto 12345678 bei Tradequo-Demo — Demokonto
Symbol XAUUSD, Takt 60 s. Not-Aus: Datei state/KILLSWITCH anlegen.

[2026-11-13T15:04:00] {'status': 'ok', 'bars': 1500, 'new': 1, 'closed': 0, ...}
```

**Das Fenster offen lassen.** Solange es läuft, handelt der Bot.

### Not-Aus

Eine leere Datei **`state\KILLSWITCH`** anlegen (Rechtsklick → Neu →
Textdokument, dann so umbenennen, dass kein `.txt` dranhängt). Beim nächsten
Durchlauf wird alles geschlossen und nichts Neues eröffnet. Zum Weitermachen
die Datei wieder löschen.

Das Fenster zu schließen stoppt nur den Bot — **offene Positionen bleiben
offen.** Die siehst du in MT5 und schließt sie dort von Hand.

---

## Teil 8 — Zusehen und lernen

Nach ein paar Tagen, im schwarzen Fenster im Ordner `bot`:

```
py -3 -m bengx_bot --config config.toml lernen
```

Das zeigt, was die Trades sagen — und schlägt Änderungen vor. **Der Bot ändert
nichts von selbst**, und das ist Absicht: bei zwei Terminen am Tag sind vierzig
Trades im Monat zu wenig, um daraus einen Parameter zu schätzen. Jeder Befund
nennt seine Stückzahl; unter acht Fällen steht dabei, dass es nicht reicht.

### Auf echte Termine umstellen

Wenn du den Nachrichtenhandel willst statt der Ausbrüche:

1. Datei `bot\news.json` anlegen (Vorlage: `news.example.json`).
2. Termine eintragen, **Zeiten in UTC**:

   ```json
   { "events": [
     { "time": "2026-11-18T13:30:00Z", "name": "CPI",  "impact": "hoch" },
     { "time": "2026-12-04T13:30:00Z", "name": "NFP",  "impact": "hoch" },
     { "time": "2026-12-09T19:00:00Z", "name": "FOMC", "impact": "hoch" }
   ] }
   ```

   Die Termine findest du im Wirtschaftskalender, z. B.
   **[ForexFactory](https://www.forexfactory.com/calendar)** oder
   **[Investing.com](https://de.investing.com/economic-calendar/)** — dort auf
   die roten (wichtigen) Termine achten und die Zeitzone auf UTC stellen.
3. In `config.toml` zurückstellen auf `trigger = "kalender"`.

---

## Wenn etwas klemmt

| Meldung | Was zu tun ist |
| --- | --- |
| `Das Paket MetaTrader5 ist nicht da` | Du bist nicht auf Windows. Dort geht es nicht. |
| `MetaTrader 5 lässt sich nicht öffnen` | MT5 läuft nicht, ist nicht angemeldet, oder Login/Passwort/Server in `.env` stimmen nicht. **Handels-**, nicht Investorpasswort. |
| `Das Konto … darf nicht handeln` | *Extras → Optionen → Expert Advisors* → Algo-Handel erlauben. |
| `Das Symbol 'XAUUSD' kennt dein Broker nicht` | Die Meldung **listet die Gold-Symbole deines Brokers gleich mit auf** — eine davon in `config.toml` unter `[mt5] symbol` eintragen, im Zweifel die oberste. Alle Symbole sehen: `py -3 -m bengx_bot --config config.toml konto --symbole` |
| `Keine Kerzen für …` | In MT5 den M1-Chart für Gold öffnen, damit die Historie lädt. |
| `Der letzte Tick … ist X Stunden entfernt` | Markt ist zu (Wochenende). Warten — oder in `config.toml` `server_utc_offset_hours = 2` eintragen. |
| `Die Position wäre 0.0050 Lots groß` | Das Konto ist zu klein für das eingestellte Risiko. Ab ~500 € geht es bei 25 Pips Stop; darunter braucht es ein **Cent-Konto**. |
| `Für dieses Regelwerk liegt kein Backtest vor` | Du hast ein **Echtgeldkonto** verbunden. Nimm ein Demokonto. |
| `live.enabled steht auf false` | In `config.toml` unter `[live]` auf `true` setzen. |
| `Kalender nicht gefunden: news.json` | Entweder `news.json` anlegen (Teil 8) oder `trigger = "ausbruch"` setzen. |

---

## Was du dabei im Kopf behalten solltest

**Niemand weiß, ob der Bot Geld verdient.** Es gibt keinen Backtest über echte
Golddaten. Die Zahlen aus dem Selbsttest stammen aus erfundenen Kursen und
sagen über den Markt nichts.

**Der Einzelschuss prüft auf MT5 vorerst die Mechanik, nicht das Regelwerk.**
Der Bot bewertet fertige Minutenkerzen und schickt dann eine Marktorder; ein
echter Nachrichten-EA legt Stop-Order ins Terminal, die genau an der Stufe
auslösen. In einem Probelauf lagen die Einstiege im Mittel **21 Pips neben der
Stufe** — bei 15 Pips Orderabstand ist das nicht mehr dieselbe Strategie.
`lernen` meldet das von selbst, sobald es auftritt.

**Deshalb: Demokonto.** Erst wenn über Wochen Zahlen zusammengekommen sind und
ein Backtest über echte Golddaten vorliegt, lohnt das Gespräch über echtes
Geld.

Handel mit Gold und Hebelprodukten kann zum Totalverlust führen. Das hier ist
keine Anlageberatung.
