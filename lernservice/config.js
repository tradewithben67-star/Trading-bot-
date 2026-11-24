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

  // Preis – nur für die Anzeige. Der echte Preis steht in deinem Stripe-Zahlungslink.
  PRICE_LABEL: "7,99 €",

  // Lieferzeit, die Schülern angezeigt wird
  DELIVERY_TEXT: "in der Regel innerhalb von 48 Stunden",

  // Supabase → Project Settings → API  (URL + "anon public" Key)
  SUPABASE_URL: "",
  SUPABASE_ANON_KEY: "",

  // Stripe → Zahlungslinks → dein 7,99 €-Link (beginnt mit https://buy.stripe.com/...)
  STRIPE_PAYMENT_LINK: "",

  // Kontakt-E-Mail (für FAQ / Rechtliches)
  CONTACT_EMAIL: "kontakt@example.de"
};
