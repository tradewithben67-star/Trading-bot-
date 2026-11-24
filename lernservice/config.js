/*
  ┌──────────────────────────────────────────────────────────────┐
  │  EINSTELLUNGEN – nur diese Datei musst du anpassen.          │
  │  Solange SUPABASE_URL leer ist, läuft die Seite im           │
  │  Vorschau-Modus mit Demo-Daten (nur in deinem Browser).      │
  └──────────────────────────────────────────────────────────────┘
*/
window.APP_CONFIG = {
  // Name deiner Seite (erscheint oben links, im Titel und im Admin-Bereich)
  SITE_NAME: "Lernkiste",

  // Preise – nur für die Anzeige. Die echten Preise stehen in deinen zwei
  // Stripe-Zahlungslinks und in supabase/schema.sql (product_price_cents).
  PRICE_SINGLE_LABEL: "4,99 €",   // eine einzelne Leistung
  PRICE_COMBO_LABEL: "12,99 €",   // ein Kombi-Paket (3 passende Leistungen)
  COMBO_SAVING_LABEL: "1,98 €",   // 3 × 4,99 € − 12,99 €

  // Empfehlungsprogramm – nur Anzeige. Die echten Beträge stehen in supabase/schema.sql
  // (Funktionen referral_bonus_cents und min_payout_cents).
  REFERRAL_BONUS_LABEL: "2,99 €",
  MIN_PAYOUT_LABEL: "10,00 €",

  // Lieferzeit, die Schülern angezeigt wird
  DELIVERY_TEXT: "in der Regel innerhalb von 48 Stunden",

  // Supabase → Project Settings → API  (URL + "anon public" Key)
  SUPABASE_URL: "",
  SUPABASE_ANON_KEY: "",

  // Stripe → Zahlungslinks (beginnen mit https://buy.stripe.com/...)
  STRIPE_LINK_SINGLE: "",   // Link über 4,99 €
  STRIPE_LINK_COMBO: "",    // Link über 12,99 €

  // Kontakt-E-Mail (für FAQ / Rechtliches)
  CONTACT_EMAIL: "kontakt@example.de"
};
