# Lernkiste – Einrichtung nur mit iPad oder Handy

Alles hier geht **im Browser (Safari)**. Du brauchst keinen Computer und keinen eigenen Server.

| Teil | Dienst | Kosten |
|---|---|---|
| Webseite | **Netlify** (holt die Dateien aus GitHub) | kostenlos |
| Konten, Datenbank, Dateien | **Supabase** | kostenlos (Free-Plan) |
| Bezahlung (4,99 € einzeln / 12,99 € Kombi) | **Stripe** (2 Zahlungslinks) | nur Gebühr pro Zahlung |

> Solange Schritt 2 noch nicht erledigt ist, läuft die Seite im **Vorschau-Modus** mit Beispieldaten.
> Du kannst sie so schon ansehen und alles ausprobieren. Admin-Test: `admin@demo.de` / `demo1234`.

---

## Schritt 1 – Webseite online stellen (Netlify)

1. Öffne **app.netlify.com** → „Sign up“ → **mit GitHub anmelden**.
2. „Add new site“ → „Import an existing project“ → **GitHub** → Repository `Trading-bot-` wählen.
3. Branch: den Branch mit der Lernkiste (oder `main`, nachdem du den Pull Request gemergt hast).
4. **Base directory:** `lernservice` eintragen, alles andere leer lassen (die Datei `netlify.toml` erledigt den Rest).
5. „Deploy“. Nach ca. 30 Sekunden bekommst du eine Adresse wie `https://irgendwas.netlify.app`.
   Unter „Site configuration → Change site name“ kannst du sie ändern, z. B. `lernkiste.netlify.app`.

Bei jeder Änderung in GitHub aktualisiert Netlify die Seite automatisch.

---

## Schritt 2 – Konten und Datenbank (Supabase)

1. Öffne **supabase.com** → „Start your project“ → mit GitHub anmelden.
2. „New project“ → Name `lernkiste` → sicheres Datenbank-Passwort (gut aufheben) → **Region: Frankfurt (eu-central-1)**.
3. Links **SQL Editor** → „New query“.
4. Öffne in GitHub die Datei `lernservice/supabase/schema.sql` → Button „Raw“ → alles markieren und kopieren.
5. In Supabase einfügen → **Run**. Es sollte „Success“ erscheinen.
6. Links **Authentication → Sign In / Providers → Email**:
   - **„Confirm email“ ausschalten** (empfohlen: Schüler können dann direkt bestellen, ohne zuerst eine Bestätigungsmail zu öffnen).
7. **Authentication → URL Configuration:**
   - Site URL: `https://DEINE-SEITE.netlify.app`
   - Redirect URLs: `https://DEINE-SEITE.netlify.app/**`
8. **Project Settings → API** (bzw. „API Keys“): Kopiere die **Project URL** und den **anon public Key** (oder den „publishable“ Key).

### config.js ausfüllen

1. In GitHub die Datei `lernservice/config.js` öffnen → **Stift-Symbol** (Bearbeiten).
2. Eintragen:
   ```js
   SUPABASE_URL: "https://xxxx.supabase.co",
   SUPABASE_ANON_KEY: "eyJhbGciOi...",
   ```
   Hier kannst du auch `SITE_NAME` (Name deiner Seite) und `CONTACT_EMAIL` ändern.
3. „Commit changes“. Netlify aktualisiert die Seite automatisch. Danach ist der Vorschau-Modus aus.

> Der anon-Key darf öffentlich sein. Die Sicherheit kommt von den Regeln in `schema.sql`: Jeder Schüler sieht nur seine eigenen Aufträge und Dateien.
> Den **service_role**/„secret“-Key trägst du **niemals** in `config.js` ein!

---

## Schritt 3 – Dich selbst zum Admin machen

1. Auf deiner Seite → „Anmelden“ → **Registrieren** mit deiner eigenen E-Mail.
2. In Supabase → **SQL Editor** → New query:
   ```sql
   update public.profiles set is_admin = true where email = 'deine@email.de';
   ```
   → Run.
3. Abmelden, wieder anmelden → du landest automatisch im **Admin-Eingang** (`/admin.html`).

**Tipp:** Öffne `/admin.html` in Safari → Teilen-Symbol → **„Zum Home-Bildschirm“**. Dann hast du deinen Eingang wie eine App auf dem iPad.

---

## Schritt 4 – Bezahlung mit Stripe (4,99 € / 12,99 €)

> Stripe erfordert, dass du volljährig bist (oder ein Elternteil das Konto führt) und du brauchst für regelmäßige Verkäufe meist ein Gewerbe. Siehe „Wichtig“ unten.

1. **dashboard.stripe.com** → Konto erstellen. Oben bleibst du erst einmal im **Testmodus**.
2. **Produktkatalog → Produkt hinzufügen**, zweimal:
   - „Einzel-Leistung“, Preis **4,99 EUR**, einmalig
   - „Kombi-Paket“, Preis **12,99 EUR**, einmalig
3. **Zahlungslinks → Neu**, für **jedes** der beiden Produkte einen Link:
   - „Kunden können die Menge anpassen“: **aus**
   - Reiter „Nach der Zahlung“ → **„Kunden auf eure Website weiterleiten“** →
     `https://DEINE-SEITE.netlify.app/konto.html?bezahlt=1`
   - Erstellen → Link kopieren (`https://buy.stripe.com/test_...`)
4. In GitHub `config.js` eintragen → Commit:
   ```js
   STRIPE_LINK_SINGLE: "https://buy.stripe.com/...",   // 4,99 €
   STRIPE_LINK_COMBO:  "https://buy.stripe.com/...",   // 12,99 €
   ```
   Die Seite wählt automatisch den richtigen Link. Der Webhook prüft, dass der bezahlte Betrag zum Auftrag passt.
   Wer ein Kombi-Paket bestellt, aber nur 4,99 € bezahlt, bekommt seinen Auftrag also nicht freigeschaltet.

**Preise ändern:** Neue Stripe-Links anlegen, in `schema.sql` die Funktion `product_price_cents` anpassen (499 / 1299) und das Skript erneut ausführen.
Danach in `config.js` die Anzeige anpassen (`PRICE_SINGLE_LABEL`, `PRICE_COMBO_LABEL`, `COMBO_SAVING_LABEL`).
Die Kombi-Pakete selbst (Name, Inhalt) stehen in `js/common.js` unter `COMBOS`.

Unter Einstellungen → Zahlungsmethoden kannst du Apple Pay, Google Pay, Klarna, PayPal usw. einschalten.

---

## Schritt 5 – Zahlung automatisch bestätigen (Webhook)

Damit ein bezahlter Auftrag automatisch als **„Neu“** in deinem Eingang erscheint:

**A) Funktion in Supabase anlegen**
1. Supabase → **Edge Functions** → „Deploy a new function“ → **„Via Editor“**.
2. Name: `stripe-webhook`
3. Den kompletten Inhalt von `lernservice/supabase/stripe-webhook.ts` (in GitHub → „Raw“ → kopieren) einfügen → **Deploy**.
4. In den Einstellungen der Funktion **„Verify JWT“ (bzw. „Enforce JWT verification“) AUSSCHALTEN** → speichern.
   (Stripe kann sich nicht bei Supabase anmelden. Die Funktion prüft stattdessen die Stripe-Signatur.)

**B) Webhook in Stripe anlegen**
1. Stripe → **Entwickler → Webhooks → Endpunkt hinzufügen**.
2. URL: `https://DEIN-PROJEKT.supabase.co/functions/v1/stripe-webhook`
3. Ereignisse: `checkout.session.completed` und `checkout.session.async_payment_succeeded`.
4. Speichern → **„Signaturgeheimnis“** anzeigen und kopieren (`whsec_...`).

**C) Geheimnis in Supabase speichern**
1. Supabase → **Edge Functions → Secrets** → Neu:
   Name `STRIPE_WEBHOOK_SECRET`, Wert `whsec_...` → speichern.

**Testen:** Bestelle als Testschüler und bezahle mit der Testkarte `4242 4242 4242 4242`, beliebiges zukünftiges Datum, beliebiger CVC.
Der Auftrag sollte nach wenigen Sekunden im Admin-Eingang als **Neu** erscheinen.

**Live gehen:** In Stripe auf „Live-Modus“ umschalten und die Schritte 4 + 5B dort **noch einmal** machen (neuer Zahlungslink, neuer Webhook, neues `whsec_`). Dann `config.js` und das Secret in Supabase aktualisieren.

> Ohne Webhook funktioniert die Seite trotzdem. Du siehst die Zahlung dann in Stripe und klickst im Admin bei dem Auftrag auf **„Als bezahlt markieren“**. Das geht auch, wenn jemand bar oder per PayPal bezahlt hat.

---

## Empfehlungsprogramm (Freunde werben)

Ist automatisch dabei, sobald du `schema.sql` ausgeführt hast.

**Hast du `schema.sql` schon vor dem Empfehlungsprogramm ausgeführt?** Dann führe die (neue) Datei einfach **noch einmal komplett** im SQL Editor aus. Das ist gefahrlos, deine Daten bleiben erhalten. Bestehende Konten bekommen dabei automatisch einen Code.
Die Edge Function `stripe-webhook` bitte ebenfalls mit dem neuen Code neu deployen.

**So funktioniert es:**
- Jeder Schüler findet unter **Konto → Freunde werben** seinen Link (`…/index.html?ref=CODE`) und kann ihn direkt per WhatsApp & Co. teilen.
- Meldet sich ein Freund über den Link an (oder trägt den Code ein) und **bezahlt seinen ersten Auftrag**, bekommt der Werber automatisch **2,99 € Guthaben**. Das gibt es pro Freund einmal.
- Guthaben kann man **für eigene Aufträge einlösen** (Button „Mit Guthaben bezahlen“) oder sich **ab 10 € auszahlen lassen** (PayPal oder Überweisung).
- Du siehst die Auszahlungswünsche im Admin unter **Empfehlungen**. Geld per PayPal oder Bank schicken, dann auf **„Ausgezahlt“** tippen.
  „Ablehnen“ bucht das Guthaben zurück.
- Wurde ein Auftrag erstattet oder war es Betrug (z. B. Zweitkonto), kannst du dort den Bonus **stornieren**.

**Schutz vor Missbrauch (automatisch):** Man kann sich nicht selbst werben. Zwei Personen können sich nicht gegenseitig werben. Den Code kann man nur vor dem ersten Kauf eintragen. Bei Zahlung mit Guthaben gibt es keinen Bonus. Und niemand kann sich selbst Guthaben gutschreiben.

**Beträge ändern:** In `schema.sql` die Zahlen in `referral_bonus_cents` (299) und `min_payout_cents` (1000) ändern und das Skript erneut ausführen.
Danach die Anzeige in `config.js` anpassen (`REFERRAL_BONUS_LABEL`, `MIN_PAYOUT_LABEL`).

**Rechnung (Stripe-Gebühr ca. 0,25 € + 1,5 %):**

| Erster Kauf eines geworbenen Freundes | Einnahme | − Stripe | − Bonus | bleibt dir |
|---|---|---|---|---|
| Einzeln | 4,99 € | ≈ 0,32 € | 2,99 € | **≈ 1,68 €** |
| Kombi-Paket | 12,99 € | ≈ 0,44 € | 2,99 € | **≈ 9,56 €** |

Jeder weitere Kauf des Freundes bringt dir wieder den vollen Betrag (ca. 4,67 € bzw. 12,55 €).

---

## Schritt 6 – Rechtstexte ausfüllen

In GitHub `lernservice/recht.html` öffnen und alle `[Platzhalter]` ersetzen (Name, Adresse, Kleinunternehmer-Hinweis …).
In Deutschland brauchst du für eine Verkaufsseite ein **Impressum**, eine **Datenschutzerklärung**, **AGB** und eine **Widerrufsbelehrung**.
Die Vorlagen sind nur ein Startpunkt, keine Rechtsberatung.

---

## So arbeitest du jeden Tag

1. **Eingang** öffnen (`/admin.html`). Neue bezahlte Aufträge haben das Abzeichen **Neu**.
2. Auftrag antippen. Du siehst Name, E-Mail, Datum, Paket, Fach, Klasse, Wunschtermin und den Wunsch des Schülers.
3. Bilder kannst du direkt drehen, aufhellen, Kontrast/Sättigung ändern oder etwas markieren (Stift).
   Mit 📎 hängst du das bearbeitete Bild als Ergebnis an.
4. Dein fertiges Ergebnis (PowerPoint, PDF, Word …) über **„Dateien hinzufügen“** auswählen.
   Auf dem iPad kannst du dafür auch Dateien aus der Dateien-App oder iCloud nehmen.
5. Nachricht schreiben → **„Fertig & zurückschicken“**. Der Schüler findet alles sofort in seinem **Postfach**.
6. Rückfragen: Nachricht schreiben → **„Nur Nachricht senden“**. Antworten des Schülers erscheinen im Verlauf. Die Karte im Eingang zeigt dann „Neue Nachricht“.

---

## Wichtig

- **Supabase Free** pausiert ein Projekt nach 7 Tagen ohne Aufrufe. Wenn das passiert, im Supabase-Dashboard auf „Restore“ tippen.
  Sobald regelmäßig Bestellungen kommen, passiert das nicht mehr.
- **Gewerbe & Steuern:** Wer regelmäßig verkauft, muss in Deutschland normalerweise ein Gewerbe anmelden.
  Als Kleinunternehmer (§ 19 UStG) weist du keine Umsatzsteuer aus.
  Wenn du unter 18 bist, brauchst du dafür die Zustimmung deiner Eltern (und meist das Familiengericht). Sprich vorher mit ihnen.
- **Inhalte:** Die Materialien sind zum Lernen gedacht. Das steht auch so in den FAQ und den AGB.
- **Speicher:** Free-Plan = 1 GB Dateien. Alte Aufträge kannst du ins **Archiv** schieben.
  Dateien löschst du in Supabase unter Storage → `dateien`.

## Dateien im Überblick

```
lernservice/
├── config.js            ← deine Einstellungen (nur diese Datei anpassen)
├── index.html           ← Startseite + Bestellformular
├── login.html           ← Anmelden / Registrieren / Passwort vergessen
├── konto.html           ← Schülerbereich: Aufträge, Postfach, Konto
├── admin.html           ← dein Eingang + Bearbeiten & Zurückschicken
├── bezahlen.html        ← nur Vorschau-Modus (live geht es direkt zu Stripe)
├── recht.html           ← Impressum, Datenschutz, AGB, Widerruf (ausfüllen!)
├── css/style.css        ← Design
├── js/                  ← Logik (api.js = Datenbank, admin.js, konto.js, home.js)
├── fonts/, vendor/      ← Schriften & Supabase-Bibliothek (lokal, DSGVO-freundlich)
└── supabase/
    ├── schema.sql       ← in Supabase SQL Editor einfügen
    └── stripe-webhook.ts← als Edge Function einfügen
```
