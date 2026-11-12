# BENGX Inner Circle — alles für die Telegram-Gruppe

Die offene Gruppe. Jeder darf rein. Zwei Gratis-Signale am Tag, direkt
aus VIP: **eins in der London-Sitzung, eins in der New-York-Sitzung.**
Zur selben Zeit wie in VIP, damit sie mitgehandelt werden können, aber
knapp und ohne Begründung, mit dem Hinweis auf VIP darunter.

VIP ist das Gegenstück: bezahlt, nur auf deine Einladung, **jedes**
Signal mit Begründung und Chance-Risiko-Verhältnis.

Der Unterschied ist die Menge, nicht die Zeit. Mit Vorsprung für VIP
wäre der Einstieg weg, bevor der Inner Circle ihn sieht — dann könnte
dort niemand mithandeln und auch niemand sehen, dass es funktioniert.

---

## 1. Anlegen

Telegram → Menü → **Neue Gruppe** → dich selbst hinzufügen → Name:

```
BENGX Inner Circle
```

> **Stell den Gruppentyp ein, BEVOR du die Kennung einträgst.** Sobald
> eine einfache Gruppe öffentlich wird, macht Telegram still eine
> Supergruppe daraus — und vergibt dabei eine **neue** Chat-Kennung. Die
> alte in `bot/.env` zeigt dann ins Leere. Erst den Typ setzen, dann
> `einrichten.bat`.

Gruppe öffnen → Name antippen → **Bearbeiten**:

- **Gruppentyp:** Öffentlich
- **Link:** `t.me/bengx_inner` (oder was frei ist — notier dir, was du
  genommen hast)
- **Verlauf für neue Mitglieder:** Sichtbar. Wer reinkommt, soll die
  letzten Signale und Ergebnisse sehen. Das ist dein bester Verkäufer.

---

## 2. Beschreibung

Telegram erlaubt 255 Zeichen. Diese hat 243:

```
Gold, XAU/USD. Zwei Signale am Tag, kostenlos: eins in London, eins in
New York. Einstieg, Stop, Ziel, zum Mithandeln. Jedes Ergebnis wird
gepostet, auch die Verluste. Alle Signale mit Begründung: VIP, nur auf
Einladung. Keine Anlageberatung.
```

---

## 3. Angeheftete Nachricht

Nach dem Senden antippen → **Anpinnen** → „Alle benachrichtigen" aus.

```
BENGX Inner Circle

Hier läuft Gold. Nur Gold, XAU/USD — kein Krypto, keine Aktien, keine
zehn Paare nebenher.

WAS DU HIER BEKOMMST
Zwei Signale am Tag, kostenlos: eins in der London-Sitzung, eins in
der New-York-Sitzung. Zur selben Zeit, zu der sie auch in VIP stehen —
du kannst sie also wirklich mitnehmen. Einstieg, Stop, Ziel. Jedes
Ergebnis wird gepostet, auch wenn es ein Verlust war. Besonders dann.

WAS DU HIER NICHT BEKOMMST
Keine Gewinnversprechen. Keine Kontoverdopplung. Keine Anlageberatung.
Ein Signal ist meine eigene Entscheidung, keine Empfehlung an dich.

WIE DU ES BENUTZT
Nimm den Stop ernst. Rechne deine Positionsgröße aus deinem Konto, nicht
aus meinem. Und wenn der Kurs schon weggelaufen ist: lass es. Was weg
ist, ist weg.

REGELN
1. Kein Werben, keine Links, keine Privatnachrichten an andere.
2. Keine fremden Signale, keine Broker-Empfehlungen.
3. Fragen zum Markt: gern. Fragen nach Gewinnversprechen: nein.
4. Wer andere abzieht, fliegt sofort und dauerhaft.

Ich bin Ben, 18, aus Deutschland, handle seit einem Jahr ausschließlich
Gold. Alles über mich und die Bots: [Website-Adresse]

VIP
Alle Signale, sofort, mit Begründung — Sweep, BOS, FVG. Nur auf
Einladung. Wenn du rein willst, schreib mir: @[dein Telegram-Name]

Der Handel mit Gold und Hebelprodukten kann zum Totalverlust führen.
```

---

## 4. Berechtigungen

Gruppe → Name antippen → **Bearbeiten** → **Berechtigungen**.

Damit niemand die Gruppe zumüllt, aber reden erlaubt bleibt:

| Einstellung             | Wert |
|-------------------------|------|
| Nachrichten senden      | **An** |
| Medien senden           | Aus |
| Sticker und GIFs        | Aus |
| Umfragen                | Aus |
| Links einbetten         | **Aus** |
| Andere hinzufügen       | Aus |
| Gruppeninfo ändern      | Aus |
| Nachrichten anpinnen    | Aus |
| **Langsamer Modus**     | **30 Sekunden** |

„Links einbetten" aus ist wichtig: so kann niemand seinen eigenen Kanal
oder einen Broker-Link in deiner Gruppe bewerben.

---

## 5. Deinen Bot als Administrator einsetzen

1. Gruppe → Name antippen → **Mitglieder hinzufügen** → deinen Bot suchen
   (der Name von @BotFather) → hinzufügen.
2. Dann denselben Bot in der Mitgliederliste antippen → **Zum
   Administrator befördern**.
3. Diese Rechte einschalten:
   - Nachrichten löschen
   - Nutzer sperren
   - **Nutzer einladen** ← ohne das kann er keine Einladungslinks machen
   - Nachrichten anpinnen

Ohne Administratorrechte kann der Bot in der Gruppe nichts tun.

---

## 6. Kennung eintragen

Schreib irgendetwas in die Gruppe, dann:

```
cd bot
einrichten.bat
```

Die Einrichtung erkennt die Gruppe von selbst und fragt dich, welche
welche ist. Alternativ von Hand in `bot/.env`:

```
TELEGRAM_INNER_CHAT_ID=-1001234567890
TELEGRAM_INNER_VERZUG=0
TELEGRAM_FREI_LONDON=09:00-15:30
TELEGRAM_FREI_NEWYORK=15:30-23:00
```

- `TELEGRAM_INNER_VERZUG` — Minuten Vorsprung für VIP. **0**, also
  gleichzeitig: nur so können die Leute im Inner Circle den Trade
  wirklich mitnehmen. Falls du VIP später doch einen Vorsprung geben
  willst, trag hier Minuten ein.
- `TELEGRAM_FREI_LONDON` und `TELEGRAM_FREI_NEWYORK` — die beiden
  Sitzungsfenster in deutscher Zeit. Je Fenster geht **genau ein**
  Gratis-Signal raus. London endet dort, wo New York beginnt, damit
  jedes Signal in höchstens ein Fenster fällt.

---

## 7. Erste Nachricht in der Gruppe

Nach dem Anpinnen, damit die Gruppe nicht leer wirkt:

```
Die Gruppe ist offen.

Ab heute kommen hier zwei Signale am Tag auf Gold: eins in der
London-Sitzung, eins in der New-York-Sitzung. Einstieg, Stop, Ziel —
und das Ergebnis, sobald der Trade zu ist.

Sie gehen zur selben Zeit raus wie in VIP. Ihr könnt sie also
mitnehmen, nicht nur hinterherschauen.

Ich fange bei null an und zeige jede Zahl. Wenn eine Woche schlecht
läuft, steht das hier genauso wie eine gute.

Fragen zum Markt könnt ihr stellen. Fragen, wie viel man verdient,
beantworte ich nicht — das weiß niemand.
```

---

## 8. Was danach von selbst läuft

Sobald die Kennungen in `bot/.env` stehen und `starten.bat` läuft:

- Du gibst dem Assistenten ein Signal durch, normal geschrieben:
  „long 4012, stop 4004, ziel 4029, 1h sweep und 1m bos"
- Er zeigt dir, wie es in **beiden** Gruppen aussehen würde, und wartet
  auf dein Ja.
- Nach dem Ja geht es **an beide Gruppen gleichzeitig**: an VIP mit
  Begründung und CRV, in den Inner Circle knapp und ohne Begründung,
  mit dem VIP-Hinweis darunter.
- Ist das Signal das zweite in derselben Sitzung, oder liegt es
  ausserhalb beider Fenster (nachts, Asien), geht es **nur an VIP** —
  und der Assistent sagt dir den Grund.
- Sagst du später „das Signal ist im Ziel", hängt das Ergebnis als
  Antwort unter dem ursprünglichen Signal — in jeder Gruppe, die es
  bekommen hat.

---

## 9. Jemanden in VIP einladen

Schreib dem Assistenten:

```
lade den Max in VIP
```

Er schickt dir einen Link, der **genau einmal** gilt und nach 24 Stunden
abläuft. Den gibst du weiter.

Rauswerfen geht genauso: „wirf 123456789 aus VIP". Das sperrt nicht
dauerhaft — mit einem neuen Link darf die Person wieder rein.

---

## 10. Woran du denken solltest

**Der Inner Circle ist dein Schaufenster, nicht dein Produkt.** Zwei
Signale am Tag sind genug, damit Leute mithandeln und sehen, dass es
funktioniert — und wenig genug, dass VIP sich lohnt. Wenn du mehr
durchlässt, kauft niemand.

**Eins je Sitzung, nicht die ersten zwei des Tages.** Sonst entscheidet
der Zufall: liegen morgens zwei schwache Signale und nachmittags das
gute, sähe der Inner Circle nur die schwachen. So ist in jeder
wichtigen Handelszeit eins dabei.

**Deshalb gehen die zwei ohne Verzug raus.** Ein Signal, das man nicht
mehr mitnehmen kann, überzeugt niemanden. Der Unterschied zu VIP ist
die Menge und die Begründung, nicht der Vorsprung.

**Poste die Verluste.** Eine Gruppe, in der nur Gewinne stehen, glaubt
dir keiner. Der Bot macht das automatisch — lass ihn.

**Mit 18 und Geld von anderen:** Sobald du für VIP Geld nimmst, bist du
gewerblich tätig. Das heißt in Deutschland Gewerbeanmeldung und
Steuererklärung. Außerdem: Finger weg von allem, was nach
Anlageberatung oder Vermögensverwaltung aussieht — dafür braucht man
eine Erlaubnis der BaFin. Signale mit klarem Hinweis „keine
Anlageberatung, meine eigene Entscheidung" sind etwas anderes als
„kauf jetzt dies für dein Depot". Halt die Grenze ein, und red mit
einem Steuerberater, bevor der erste Euro fließt. Ich bin kein Anwalt;
das ist keine Rechtsberatung.
