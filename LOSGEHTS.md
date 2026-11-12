# Bot fertig machen — Schritt für Schritt

Einmal durch, etwa 20 Minuten. **Die Reihenfolge ist wichtig.**

---

## Teil 1 — Die zwei Gruppen (in Telegram)

### 1. Beide Gruppen anlegen

Menü → **Neue Gruppe** → nur dich selbst hinzufügen → Namen vergeben:

```
BENGX VIP
BENGX Inner Circle
```

### 2. Alle Einstellungen machen — jetzt, nicht später

Für **jede** Gruppe: Name antippen → **Bearbeiten**

| | VIP | Inner Circle |
|---|---|---|
| Gruppentyp | Privat | Privat |
| Verlauf für Neue | Sichtbar | Sichtbar |

Dann **Berechtigungen**, auch für jede Gruppe:

| | VIP | Inner Circle |
|---|---|---|
| Nachrichten senden | An | An |
| Medien senden | An | Aus |
| Links einbetten | **Aus** | **Aus** |
| **Andere hinzufügen** | **Aus** | Aus |
| Gruppeninfo ändern | Aus | Aus |
| Langsamer Modus | 15 Sek. | 30 Sek. |

> **Warum jetzt und nicht später:** Jede dieser Einstellungen verwandelt
> eine einfache Gruppe still in eine Supergruppe — und dabei ändert sich
> ihre Kennung. Trägst du die Kennung vorher ein, zeigt sie danach ins
> Leere und der Bot postet nirgends mehr hin.

### 3. Bei VIP: den Haupt-Link widerrufen

Gruppeninfo → **Einladungslinks** → Haupt-Link antippen → **Widerrufen**.

Sonst kursiert ein Link, der für immer gilt. Zugang zu VIP gibt es nur
über die Einzellinks, die dein Bot auf Zuruf macht.

Beim **Inner Circle lässt du den Link stehen** — den verteilst du später
selbst.

### 4. Den Bot in beide Gruppen holen

Gruppe → **Mitglieder hinzufügen** → deinen Bot suchen (der Name von
@BotFather) → hinzufügen.

Dann in der Mitgliederliste auf den Bot tippen → **Zum Administrator
befördern** → diese Rechte an:

- Nachrichten löschen
- Nutzer sperren
- **Nutzer einladen** ← ohne das gibt es keine Einladungslinks
- Nachrichten anpinnen

### 5. In jede Gruppe einmal schreiben

Irgendetwas, zum Beispiel `test`. Der Bot muss die Gruppe gesehen haben,
sonst findet er sie im nächsten Teil nicht.

---

## Teil 2 — Der Bot (auf deinem Rechner)

### 6. Neueste Fassung holen

https://github.com/tradewithben67-star/Trading-bot-/archive/HEAD.zip

Herunterladen, **entpacken** (Rechtsklick → Alle extrahieren). Seit
deinem letzten Download hat sich viel geändert.

Deine alten Zugangsdaten gehen nicht verloren — die Einrichtung fragt,
ob sie sie aus der vorherigen Entpackung übernehmen soll.

### 7. `LOSGEHTS.bat` doppelklicken

Eine Datei, die alles der Reihe nach macht: einrichten, prüfen, und
**nur bei grün** starten. Fehlt Python, bietet sie an, es zu
installieren — dann danach noch einmal doppelklicken.

Sie führt dich durch fünf Schritte:

1. **Token** — von @BotFather. Rechtsklick fügt ein.
2. **Deine Chat-Kennung** — schreib deinem Bot privat „hallo", er
   erkennt sie selbst.
3. **Deine Gruppen** — sag Ja, er findet beide und fragt, welche welche
   ist. Beim Vorsprung für VIP: **0** eingeben.
4. **Wer antwortet** — `1` für Gemini, dann deinen Schlüssel einfügen.
5. **Am Code weiterbauen** — kommt nur bei Claude, überspring es.

Danach prüft sie von selbst. Fehlt etwas, **startet sie den Bot nicht**
und sagt dir genau, was. Mach davon ein Foto und schick es mir.

Ist alles da, läuft der Bot sofort los. Das Fenster **offen lassen** —
schließt du es, ist er aus.

Die einzelnen Dateien gibt es weiterhin, falls du nur einen Schritt
willst: `einrichten.bat`, `pruefen.bat`, `starten.bat`.

<details>
<summary>Der alte Weg mit drei Doppelklicks</summary>

### `einrichten.bat` doppelklicken

Im Ordner `bot`. Fehlt Python, bietet das Fenster an, es selbst zu
installieren — dann danach **noch einmal** doppelklicken.

Es führt dich durch fünf Schritte:

1. **Token** — von @BotFather. Rechtsklick fügt ein.
2. **Deine Chat-Kennung** — schreib deinem Bot privat „hallo", er
   erkennt sie selbst.
3. **Deine Gruppen** — sag Ja, er findet beide und fragt, welche welche
   ist. Beim Vorsprung für VIP: **0** eingeben.
4. **Wer antwortet** — `1` für Gemini, dann deinen Schlüssel einfügen.
5. **Am Code weiterbauen** — kommt nur bei Claude, überspring es.

### `pruefen.bat` doppelklicken

Sagt dir, ob dein Gemini-Schlüssel wirklich funktioniert. Das wissen wir
bis heute nicht.

### `starten.bat` doppelklicken

Das Fenster **offen lassen**. Solange es läuft, antwortet dein Bot.
Schließt du es, ist er aus.

</details>

---

## Teil 3 — Probe

### 10. Schreib deinem Bot privat

```
wie läuft es
```

Er muss mit Zahlen antworten, nicht mit einer Fehlermeldung.

### 11. Ein Testsignal

```
long 4012, stop 4004, ziel 4029, 1h sweep und 1m bos
```

Er zeigt dir, wie es in **beiden** Gruppen aussieht, und fragt, ob er es
verschicken soll. Sag **nein** — es war nur eine Probe.

Schau dir die Vorschau genau an: VIP mit Begründung und CRV, Inner
Circle knapp mit dem VIP-Hinweis darunter. Stimmt das, ist alles
richtig verbunden.

### 12. Angeheftete Nachrichten setzen

Die Texte stehen in `gruppen/VIP.md` und `gruppen/INNER-CIRCLE.md`.
Kopieren, in die Gruppe schicken, antippen → **Anpinnen** → „Alle
benachrichtigen" **aus**.

---

## Danach

Der Bot läuft, solange `starten.bat` offen ist. Du gibst Signale normal
durch, er fragt nach, du sagst ja.

Was noch offen ist:

- **Der Preis für VIP.** Steht nirgends, weil du mir keinen genannt hast.
- **Der Inner-Circle-Link auf der Website.** Schick ihn mir, dann baue
  ich ihn ein — gerade führt von der Seite kein Weg in deine Gruppe.
- **Die Meldestelle** für Interessenten von der Website
  (`tools/meldestelle/EINRICHTEN.md`). Kannst du machen, wenn das hier
  läuft.
