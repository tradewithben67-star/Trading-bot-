// ════════════════════════════════════════════════════════════════════
//  Supabase Edge Function: "stripe-webhook"
//  Markiert einen Auftrag als bezahlt, sobald Stripe die Zahlung meldet.
//
//  Einrichten (alles im Browser, siehe ANLEITUNG.md, Schritt 5):
//   1. Supabase → Edge Functions → "Deploy a new function" → "Via Editor"
//   2. Name: stripe-webhook  → diesen kompletten Code einfügen → Deploy
//   3. In den Function-Einstellungen "Verify JWT" AUSSCHALTEN
//   4. Edge Functions → Secrets: STRIPE_WEBHOOK_SECRET = whsec_...
// ════════════════════════════════════════════════════════════════════

const WEBHOOK_SECRET = Deno.env.get("STRIPE_WEBHOOK_SECRET") ?? "";
const SUPABASE_URL = Deno.env.get("SUPABASE_URL") ?? "";
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY") ?? "";
const PRICE_CENTS = 799;

async function hmacHex(key: string, message: string): Promise<string> {
  const enc = new TextEncoder();
  const k = await crypto.subtle.importKey("raw", enc.encode(key), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", k, enc.encode(message));
  return Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, "0")).join("");
}

function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

// Prüft die Stripe-Signatur (Header "Stripe-Signature: t=...,v1=...")
async function verifyStripe(body: string, header: string | null): Promise<boolean> {
  if (!header || !WEBHOOK_SECRET) return false;
  const pairs = header.split(",").map((p) => p.trim().split("="));
  const t = pairs.find(([k]) => k === "t")?.[1];
  const sigs = pairs.filter(([k]) => k === "v1").map(([, v]) => v);
  if (!t || sigs.length === 0) return false;
  if (Math.abs(Date.now() / 1000 - Number(t)) > 300) return false; // max. 5 Minuten alt
  const expected = await hmacHex(WEBHOOK_SECRET, `${t}.${body}`);
  return sigs.some((s) => safeEqual(s, expected));
}

Deno.serve(async (req) => {
  if (req.method !== "POST") return new Response("Stripe-Webhook ist aktiv.");

  const body = await req.text();
  if (!(await verifyStripe(body, req.headers.get("stripe-signature")))) {
    return new Response("Ungültige Signatur", { status: 400 });
  }

  const event = JSON.parse(body);
  if (event.type === "checkout.session.completed" || event.type === "checkout.session.async_payment_succeeded") {
    const s = event.data.object;
    const orderId = Number(s.client_reference_id);
    const ok = s.payment_status === "paid" && Number.isInteger(orderId) && orderId > 0 &&
      s.currency === "eur" && Number(s.amount_total) >= PRICE_CENTS;

    if (ok) {
      const res = await fetch(`${SUPABASE_URL}/rest/v1/orders?id=eq.${orderId}&status=eq.unbezahlt`, {
        method: "PATCH",
        headers: {
          apikey: SERVICE_KEY,
          Authorization: `Bearer ${SERVICE_KEY}`,
          "Content-Type": "application/json",
          Prefer: "return=minimal",
        },
        body: JSON.stringify({ status: "neu", paid_at: new Date().toISOString(), paid_via: "stripe", stripe_session_id: s.id }),
      });
      if (!res.ok) return new Response("Datenbank-Fehler: " + (await res.text()), { status: 500 }); // Stripe versucht es dann erneut
    } else {
      console.log("Ignoriert (nicht bezahlt / keine Auftragsnummer / falscher Betrag):", s.id, s.client_reference_id, s.amount_total);
    }
  }

  return new Response(JSON.stringify({ received: true }), { headers: { "Content-Type": "application/json" } });
});
