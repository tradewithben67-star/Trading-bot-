# BENGX VIP — alles für die Telegram-Gruppe

Die geschlossene Gruppe. Nur wer von dir einen Link bekommt, kommt rein.
**Jedes** Signal, sofort, mit Begründung (Sweep, BOS, FVG) und dem
Chance-Risiko-Verhältnis.

Der Inner Circle ist das Gegenstück: offen für alle, zwei Signale am Tag,
knapp und ohne Begründung.

---

## 1. Anlegen

Telegram → Menü → **Neue Gruppe** → dich selbst hinzufügen → Name:

```
BENGX VIP
```

> **Mach ALLE Gruppeneinstellungen zuerst, und trag die Kennung erst
> danach ein.** Berechtigungen und langsamer Modus verwandeln eine
> einfache Gruppe still in eine Supergruppe, und dabei bekommt sie eine
> **neue** Chat-Kennung. Die alte in `bot/.env` zeigt dann ins Leere.

Gruppe öffnen → Name antippen → **Bearbeiten**:

- **Gruppentyp:** **Privat** — das ist der wichtigste Schalter. Keine
  öffentliche Adresse, kein `t.me/…`-Name. Wer rein will, braucht einen
  Link von dir.
- **Verlauf für neue Mitglieder:** Sichtbar. Wer bezahlt hat, soll sofort
  sehen, was in den letzten Wochen lief. Das rechtfertigt den Preis.
- **Einladungslinks:** Den automatisch erzeugten Haupt-Link **widerrufen**
  (antippen → Link widerrufen). Du gibst nur Einzellinks aus, die der Bot
  macht. Ein Haupt-Link, der einmal irgendwo auftaucht, ist für immer
  draußen.

---

## 2. Beschreibung

Telegram erlaubt 255 Zeichen. Diese hat 236:

```
Gold, XAU/USD. Jedes Signal sofort: Einstieg, Stop, Ziel, Begründung und
Chance-Risiko-Verhältnis. Jedes Ergebnis wird gepostet, auch die
Verluste. Geschlossen, nur auf Einladung. Keine Anlageberatung.
```

---

## 3. Angeheftete Nachricht

Nach dem Senden antippen → **Anpinnen** → „Alle benachrichtigen" aus.

```
BENGX VIP

Du bist drin. Hier läuft jedes Signal, das ich nehme — nicht zwei am
Tag, sondern alle.

WAS DU BEKOMMST
Einstieg, Stop, Ziel, dazu die Begründung (Sweep, BOS, FVG, Order Block)
und das Chance-Risiko-Verhältnis. Sobald ein Trade zu ist, hängt das
Ergebnis als Antwort direkt unter dem Signal — Ziel oder Stop, mit Pips.

WIE DU ES BENUTZT
Rechne deine Positionsgröße aus DEINEM Konto, nicht aus meinem. Nimm den
Stop ernst; er steht vor dem Einstieg fest, nicht danach. Ist der Kurs
schon weggelaufen, lass das Signal aus. Was weg ist, ist weg.

WAS ICH NICHT MACHE
Keine Gewinnversprechen. Keine Anlageberatung. Ein Signal ist meine
eigene Entscheidung, keine Empfehlung an dich. Ich sage dir nie, wie
viel du setzen sollst.

REGELN
1. Nichts aus dieser Gruppe geht nach draußen. Keine Weiterleitung,
   keine Screenshots in anderen Gruppen, kein Vorlesen im Stream.
   Wer das macht, fliegt raus — ohne Rückfrage und ohne Erstattung.
2. Kein Werben, keine Links, keine Broker-Empfehlungen.
3. Keine Privatnachrichten an andere Mitglieder. Wer dich hier anschreibt
   und dir etwas verkaufen will, ist ein Betrüger. Melde ihn mir.
4. Fragen zum Setup: jederzeit. Fragen, wann der nächste Trade kommt:
   wenn er da ist, steht er hier.

DEIN ZUGANG
Dein Einladungslink gilt genau einmal und läuft nach 24 Stunden ab. Gib
ihn nicht weiter — er funktioniert ohnehin nur für dich.

Ich bin Ben, 18, aus Deutschland, handle seit einem Jahr ausschließlich
Gold. Alles über mich und die Bots: [Website-Adresse]

Der Handel mit Gold und Hebelprodukten kann zum Totalverlust führen.
```

---

## 4. Berechtigungen

Gruppe → Name antippen → **Bearbeiten** → **Berechtigungen**.

Zahlende Mitglieder dürfen mehr als die offene Gruppe, aber nicht alles:

| Einstellung             | Wert | Warum |
|-------------------------|------|-------|
| Nachrichten senden      | **An** | Fragen sollen möglich sein |
| Medien senden           | **An** | Charts zeigen gehört dazu |
| Sticker und GIFs        | Aus | |
| Umfragen                | Aus | |
| Links einbetten         | **Aus** | sonst wirbt jemand seinen Kanal |
| Andere hinzufügen       | **Aus** | **wichtig** — sonst holt ein Mitglied Freunde rein |
| Gruppeninfo ändern      | Aus | |
| Nachrichten anpinnen    | Aus | |
| **Langsamer Modus**     | 15 Sekunden | |

„Andere hinzufügen: Aus" ist hier der entscheidende Punkt. Steht er an,
kann jedes Mitglied beliebig viele Leute hereinholen, und du verkaufst
nichts mehr.

---

## 5. Deinen Bot als Administrator einsetzen

Derselbe Bot wie im Inner Circle.

1. Gruppe → **Mitglieder hinzufügen** → deinen Bot suchen → hinzufügen.
2. In der Mitgliederliste antippen → **Zum Administrator befördern**.
3. Rechte einschalten:
   - Nachrichten löschen
   - Nutzer sperren
   - **Nutzer einladen** ← ohne das gibt es keine Einladungslinks
   - Nachrichten anpinnen

---

## 6. Kennung eintragen

Schreib etwas in die Gruppe, dann `einrichten.bat` — die Einrichtung
erkennt beide Gruppen und fragt, welche welche ist. Oder von Hand in
`bot/.env`:

```
TELEGRAM_VIP_CHAT_ID=-1001234567890
```

Mehr braucht VIP nicht. Alle Einstellungen für Verzug und Fenster
betreffen nur den Inner Circle; VIP bekommt immer alles, immer sofort.

---

## 7. Erste Nachricht in der Gruppe

```
Die Gruppe steht.

Ab jetzt landet hier jedes Signal, das ich nehme — mit Begründung und
CRV, und mit dem Ergebnis darunter, sobald der Trade zu ist.

Ich zeige jede Zahl. Auch die Wochen, die schlecht laufen. Wer nur
Gewinne sehen will, ist hier falsch.

Fragen zum Setup könnt ihr jederzeit stellen.
```

---

## 8. Jemanden einladen

Schreib dem Assistenten normal:

```
lade den Max in VIP
```

Du bekommst einen Link zurück, der **genau einmal** gilt und nach 24
Stunden abläuft. Den schickst du der Person privat.

Rauswerfen:

```
wirf 123456789 aus VIP
```

Das sperrt **nicht** dauerhaft — mit einem neuen Link darf die Person
wieder rein. Für einen echten Rauswurf nimmst du in Telegram
**Sperren** statt des Bots.

Die Zahlen-Kennung eines Mitglieds siehst du, wenn du in der
Mitgliederliste auf die Person tippst, oder wenn der Assistent dir eine
Meldung von der Website weiterleitet.

---

## 9. Wen du reinlässt

Du lädst von Hand ein — es gibt keine Zahlungsprüfung im Bot. Das heißt:

- Führ eine eigene Liste, wer bezahlt hat und bis wann. Eine Tabelle
  reicht. Ohne Liste weißt du nach zwei Monaten nicht mehr, wer dran ist.
- Lass den Link erst raus, wenn das Geld da ist. Nicht vorher.
- Setz dir eine Erinnerung, wann die Zahlung erneuert werden muss.

Wenn du das später nicht mehr von Hand machen willst, sag Bescheid —
dann baue ich die Zahlung an und der Bot lädt selbst ein und entfernt
bei Kündigung. Das braucht ein Geschäftskonto und ein paar Tage Vorlauf.

---

## 10. Worauf du achten solltest

**Der Preis steht noch nicht fest.** Du hast mir keinen genannt, deshalb
steht in keiner Nachricht eine Zahl. Sag mir einen, dann trage ich ihn
überall ein, wo er hingehört.

**Weitergeleitete Signale sind dein größtes Risiko.** Ein Mitglied, das
deine Signale in eine andere Gruppe kopiert, kostet dich alle künftigen
Kunden. Deshalb steht es als Regel 1 in der angehefteten Nachricht, und
deshalb ist „Andere hinzufügen" aus.

**Poste die Verluste auch hier.** Gerade hier. Wer bezahlt, merkt sofort,
wenn etwas fehlt — und verliert dann das Vertrauen in alles andere.

**Sobald Geld fließt, bist du gewerblich tätig.** Gewerbeanmeldung und
Steuererklärung, auch mit 18. Dazu die Grenze zur Anlageberatung: ein
Signal mit klarem Hinweis „meine eigene Entscheidung, keine Empfehlung"
ist etwas anderes als eine persönliche Empfehlung für jemandes Depot.
Für Letzteres braucht man eine BaFin-Erlaubnis. Red mit einem
Steuerberater, bevor der erste Euro ankommt. Ich bin kein Anwalt; das
ist keine Rechtsberatung.
