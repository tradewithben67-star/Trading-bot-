# Meldestelle einrichten

Damit du eine Telegram-Nachricht bekommst, wenn jemand auf der Website
einen Bot auswählt und seinen Kontakt hinterlässt.

## Warum überhaupt eine Zwischenstation

Der Telegram-Token darf **niemals** in die Website. Jeder Besucher kann
den Quelltext einer Seite lesen. Mit deinem Token könnte er Nachrichten
in deinem Namen schicken, den Not-Aus auslösen oder Leute aus deinen
Gruppen werfen.

Dein Rechner ist von außen nicht erreichbar — deshalb hält diese kleine
Stelle im Netz den Token, und die Website kennt nur ihre Adresse.

## Schritt für Schritt (etwa fünf Minuten, kostenlos, ohne Kreditkarte)

1. **Konto anlegen** auf `dash.cloudflare.com` — E-Mail und Passwort
   reichen.

2. Links auf **Workers & Pages**, dann **Create** → **Start with Hello
   World!** → **Deploy**. Gib ihm einen Namen, zum Beispiel
   `bengx-meldestelle`.

3. **Code einsetzen:** auf **Edit code**, alles markieren, löschen, und
   den Inhalt von `worker.js` aus diesem Ordner einfügen. Dann
   **Deploy**.

4. **Geheimnisse eintragen:** Settings → Variables and Secrets.
   Zweimal **Add** mit Typ **Secret**:

   | Name               | Wert                                      |
   |--------------------|-------------------------------------------|
   | `TELEGRAM_TOKEN`   | derselbe Token wie in `bot/.env`          |
   | `TELEGRAM_CHAT_ID` | deine Chat-Kennung aus `bot/.env`         |

   Dazu einmal **Add** mit Typ **Variable** (kein Geheimnis):

   | Name       | Wert                                               |
   |------------|----------------------------------------------------|
   | `HERKUNFT` | `https://claude.ai,https://tradewithben67-star.github.io` |

   Trag dort jede Adresse ein, unter der deine Seite läuft, mit Komma
   getrennt und ohne Leerzeichen. Steht eine Adresse nicht drin, lehnt
   die Meldestelle sie ab — das ist Absicht.

5. **Adresse kopieren.** Oben steht etwas wie
   `https://bengx-meldestelle.deinname.workers.dev`.

6. **In die Website eintragen:** in `index.html` die Zeile

   ```js
   var MELDESTELLE="";
   ```

   ändern zu

   ```js
   var MELDESTELLE="https://bengx-meldestelle.deinname.workers.dev";
   ```

   Solange sie leer ist, erscheint auf der Seite **kein Formular** und es
   werden **keine Daten erhoben**. Das ist der Zustand von jetzt.

## Probe

Website öffnen, einen Bot auswählen, Name und Telegram-Namen eintragen,
absenden. Es muss sofort eine Nachricht in deinem Telegram ankommen.

Kommt nichts: in Cloudflare auf den Worker, Reiter **Logs**. Dort steht
der Grund. `503` heißt, die Geheimnisse fehlen. `403` heißt, die Adresse
der Website steht nicht in `HERKUNFT`.

## Was die Meldestelle absichtlich nicht tut

- Sie gibt Telegram-Fehler nicht nach außen weiter. Die könnten den
  Token verraten.
- Sie schickt den Text ohne Formatierung. So kann niemand über das
  Namensfeld Befehle oder Links einschleusen.
- Sie nimmt nur Meldungen von den Adressen in `HERKUNFT` an.
- Sie kürzt jedes Feld hart ab, damit niemand dein Telegram mit einer
  riesigen Nachricht zumüllt.

Sie hat **keine** Begrenzung der Anzahl pro Stunde. Wenn jemand deine
Worker-Adresse findet und sie in Massen aufruft, kann er dir viele
Nachrichten schicken. Falls das je passiert: in Cloudflare den Worker
kurz löschen oder `HERKUNFT` leeren, dann sag mir Bescheid — dann baue
ich eine Sperre ein.
