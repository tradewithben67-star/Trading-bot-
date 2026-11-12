/* BENGX — Meldestelle.
 *
 * Nimmt eine Interessensmeldung von der Website entgegen und schickt sie
 * als Telegram-Nachricht an Ben. Laeuft als Cloudflare Worker.
 *
 * Warum es diese Zwischenstation ueberhaupt gibt:
 * Der Telegram-Token darf niemals in die Website. Jeder Besucher koennte
 * ihn im Quelltext lesen und damit den Bot uebernehmen — Nachrichten in
 * Bens Namen schicken, den Not-Aus ausloesen, Mitglieder rauswerfen.
 * Bens Rechner ist von aussen nicht erreichbar, also haelt diese kleine
 * Stelle den Token, und die Website kennt nur ihre Adresse.
 *
 * Eintragen als Geheimnis (Secret), NICHT hier im Code:
 *   TELEGRAM_TOKEN     derselbe Token wie in bot/.env
 *   TELEGRAM_CHAT_ID   Bens eigene Chat-Kennung
 *
 * Als normale Variable (Variable, kein Geheimnis):
 *   HERKUNFT           erlaubte Adressen, mit Komma getrennt, z. B.
 *                      https://tradewithben67-star.github.io,https://claude.ai
 */

const GRENZE = {name: 60, telegram: 40, bots: 5, botname: 40, seite: 80};

function erlaubt(env) {
  return String(env.HERKUNFT || "")
    .split(",").map(s => s.trim()).filter(Boolean);
}

function kopf(env, herkunft) {
  const liste = erlaubt(env);
  const h = {
    "Vary": "Origin",
    "Access-Control-Allow-Methods": "POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
  if (herkunft && liste.includes(herkunft)) {
    h["Access-Control-Allow-Origin"] = herkunft;
  }
  return h;
}

/* Alles, was von draussen kommt, wird gekuerzt und von Steuerzeichen
   befreit. Als reiner Text verschickt — kein parse_mode, damit niemand
   ueber Markdown etwas einschleusen kann. */
function sauber(wert, laenge) {
  return String(wert == null ? "" : wert)
    .replace(/[\u0000-\u001F\u007F]/g, " ")
    .trim()
    .slice(0, laenge);
}

export default {
  async fetch(anfrage, env) {
    const herkunft = anfrage.headers.get("Origin") || "";
    const h = kopf(env, herkunft);

    if (anfrage.method === "OPTIONS") {
      return new Response(null, {status: 204, headers: h});
    }
    if (anfrage.method !== "POST") {
      return new Response("Nur POST.", {status: 405, headers: h});
    }
    /* Ohne erlaubte Herkunft gar nicht erst weiterlesen. */
    if (!h["Access-Control-Allow-Origin"]) {
      return new Response("Herkunft nicht erlaubt.", {status: 403, headers: h});
    }
    if (!env.TELEGRAM_TOKEN || !env.TELEGRAM_CHAT_ID) {
      return new Response("Noch nicht eingerichtet.", {status: 503, headers: h});
    }

    const roh = await anfrage.text();
    if (roh.length > 4096) {
      return new Response("Zu lang.", {status: 413, headers: h});
    }
    let daten;
    try { daten = JSON.parse(roh); } catch {
      return new Response("Kein JSON.", {status: 400, headers: h});
    }

    const name = sauber(daten.name, GRENZE.name);
    const telegram = sauber(daten.telegram, GRENZE.telegram);
    const seite = sauber(daten.seite, GRENZE.seite);
    const bots = Array.isArray(daten.bots)
      ? daten.bots.slice(0, GRENZE.bots).map(b => sauber(b, GRENZE.botname)).filter(Boolean)
      : [];

    if (name.length < 2 || telegram.length < 3) {
      return new Response("Name und Telegram-Name fehlen.", {status: 400, headers: h});
    }

    const zeit = new Date().toLocaleString("de-DE", {
      timeZone: "Europe/Berlin", dateStyle: "short", timeStyle: "short",
    });
    const text =
      "Neues Interesse\n\n" +
      name + "\n" +
      telegram + "\n\n" +
      (bots.length ? "Bots: " + bots.join(", ") : "Kein Bot angegeben") + "\n" +
      zeit + (seite ? " · " + seite : "");

    const antwort = await fetch(
      "https://api.telegram.org/bot" + env.TELEGRAM_TOKEN + "/sendMessage",
      {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          chat_id: env.TELEGRAM_CHAT_ID,
          text,
          disable_web_page_preview: true,
        }),
      });

    if (!antwort.ok) {
      /* Den Grund nicht nach draussen geben — er koennte den Token oder
         die Chat-Kennung verraten. Nur ins Protokoll. */
      console.error("Telegram antwortet", antwort.status, await antwort.text());
      return new Response("Konnte nicht zugestellt werden.", {status: 502, headers: h});
    }
    return new Response(null, {status: 204, headers: h});
  },
};
