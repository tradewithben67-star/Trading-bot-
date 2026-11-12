# BENGX Inner Circle — alles für die Telegram-Gruppe

Die offene Gruppe. Jeder darf rein. Zwei Gratis-Signale am Tag, die aus
VIP kommen — verzögert, knapp, mit dem Hinweis auf VIP darunter.

VIP ist das Gegenstück: bezahlt, nur auf deine Einladung, jedes Signal
sofort und mit Begründung.

---

## 1. Anlegen

Telegram → Menü → **Neue Gruppe** → dich selbst hinzufügen → Name:

```
BENGX Inner Circle
```

Danach die Gruppe öffnen → Name antippen → **Bearbeiten**:

- **Gruppentyp:** Öffentlich
- **Link:** `t.me/bengx_inner` (oder was frei ist — notier dir, was du
  genommen hast)
- **Verlauf für neue Mitglieder:** Sichtbar. Wer reinkommt, soll die
  letzten Signale und Ergebnisse sehen. Das ist dein bester Verkäufer.

---

## 2. Beschreibung

Telegram erlaubt 255 Zeichen. Diese hat 243:

```
Gold, XAU/USD. Zwei Signale am Tag, kostenlos — Einstieg, Stop, Ziel.
Jedes Ergebnis wird gepostet, auch die Verluste. Wer alle Signale sofort
und mit Begründung will: VIP, nur auf Einladung. Keine Anlageberatung.
```

---

## 3. Angeheftete Nachricht

Nach dem Senden antippen → **Anpinnen** → „Alle benachrichtigen" aus.

```
BENGX Inner Circle

Hier läuft Gold. Nur Gold, XAU/USD — kein Krypto, keine Aktien, keine
zehn Paare nebenher.

WAS DU HIER BEKOMMST
Zwei Signale am Tag, kostenlos. Einstieg, Stop, Ziel. Jedes Ergebnis
wird gepostet — auch wenn es ein Verlust war. Besonders dann.

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
TELEGRAM_INNER_VERZUG=20
TELEGRAM_INNER_PRO_TAG=2
```

- `TELEGRAM_INNER_VERZUG` — Minuten Vorsprung für VIP, bevor dasselbe
  Signal in den Inner Circle geht. 20 ist ein guter Wert: lang genug,
  dass VIP etwas wert bleibt, kurz genug, dass das Signal noch gilt.
- `TELEGRAM_INNER_PRO_TAG` — wie viele am Tag. 2, wie besprochen.
  0 schaltet den Inner Circle ab.

---

## 7. Erste Nachricht in der Gruppe

Nach dem Anpinnen, damit die Gruppe nicht leer wirkt:

```
Die Gruppe ist offen.

Ab heute kommen hier zwei Signale am Tag auf Gold. Einstieg, Stop,
Ziel — und das Ergebnis, sobald der Trade zu ist.

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
- Nach dem Ja geht es **sofort an VIP**, mit Begründung und CRV.
- **20 Minuten später** geht dasselbe Signal in den Inner Circle —
  knapp, ohne Begründung, mit dem VIP-Hinweis darunter.
- Sind die zwei für heute schon raus, geht das Signal **nur an VIP**,
  und der Assistent sagt dir das.
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
Signale am Tag sind genug, damit Leute sehen, dass es funktioniert, und
wenig genug, dass VIP sich lohnt. Wenn du mehr durchlässt, kauft
niemand.

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
