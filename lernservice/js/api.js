/*
  Daten-Schicht. Zwei Varianten mit identischen Funktionen:
  - "live": Supabase (Konten, Datenbank, Dateispeicher)
  - "demo": alles im localStorage dieses Browsers (Vorschau, solange Supabase nicht eingerichtet ist)
*/
(function () {
  const C = window.APP_CONFIG || {};
  const LIVE = !!(C.SUPABASE_URL && C.SUPABASE_ANON_KEY);
  const BUCKET = "dateien";
  const MAX_FILE = 25 * 1024 * 1024;
  const baseUrl = () => new URL(".", location.href).href;
  const byDate = (a, b) => new Date(a.created_at) - new Date(b.created_at);
  // gleiche Regel wie product_price_cents() in schema.sql
  const priceOf = (product) => (/^paket_/.test(product) ? 1299 : 499);
  const safeName = (n) => (String(n || "datei").normalize("NFKD").replace(/[\u0300-\u036f]/g, "").replace(/[^\w.\-]+/g, "_").slice(-80)) || "datei";

  function tidy(o) {
    o.files = (o.files || []).slice().sort(byDate);
    o.messages = (o.messages || []).slice().sort(byDate);
    o.student = o.student || { name: "", email: "" };
    return o;
  }

  function germanError(e) {
    const m = (e && (e.message || e.error_description || e.msg)) || String(e || "Unbekannter Fehler");
    const map = [
      [/invalid login credentials/i, "E-Mail oder Passwort ist falsch."],
      [/already registered|already been registered|user already exists/i, "Für diese E-Mail gibt es schon ein Konto. Bitte melde dich an."],
      [/password should be at least|password.*(short|length)/i, "Das Passwort muss mindestens 8 Zeichen haben."],
      [/email not confirmed/i, "Bitte bestätige zuerst deine E-Mail-Adresse (Link in deinem Postfach)."],
      [/unable to validate email|invalid email|email address .* is invalid/i, "Bitte gib eine gültige E-Mail-Adresse ein."],
      [/rate limit|too many/i, "Zu viele Versuche. Bitte warte kurz und versuche es erneut."],
      [/payload too large|exceeded the maximum allowed size|too large/i, "Die Datei ist zu groß (max. 25 MB)."],
      [/failed to fetch|network/i, "Keine Verbindung. Bitte prüfe dein Internet."],
      [/row-level security|permission denied/i, "Dafür fehlt dir die Berechtigung."]
    ];
    for (const [re, de] of map) if (re.test(m)) return new Error(de);
    return new Error(m);
  }

  /* ═════════════════════════ LIVE (Supabase) ═════════════════════════ */
  function makeLive() {
    const sb = window.supabase.createClient(C.SUPABASE_URL, C.SUPABASE_ANON_KEY, {
      auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: true }
    });
    const SELECT = "*, student:profiles(name,email), files:order_files(*), messages(*)";
    const urlCache = new Map();
    let me = null;
    const chk = ({ data, error }) => { if (error) throw germanError(error); return data; };

    const api = {
      mode: "live",
      client: sb,
      async session(force) {
        if (me && !force) return me;
        const { data: { session } } = await sb.auth.getSession();
        if (!session) return (me = null);
        const { data: p } = await sb.from("profiles").select("name,email,is_admin").eq("id", session.user.id).maybeSingle();
        me = { id: session.user.id, email: session.user.email, name: (p && p.name) || session.user.user_metadata?.name || "", isAdmin: !!(p && p.is_admin) };
        return me;
      },
      onAuthChange(cb) { sb.auth.onAuthStateChange((ev) => { me = null; cb(ev); }); },
      async signUp({ name, email, password, ref }) {
        const meta = { name };
        if (ref) meta.ref = String(ref).trim().toUpperCase();
        const { data, error } = await sb.auth.signUp({ email, password, options: { data: meta, emailRedirectTo: baseUrl() + "konto.html" } });
        if (error) throw germanError(error);
        if (!data.session) return { needsConfirm: true };
        me = null;
        return { user: await api.session(true) };
      },
      async signIn({ email, password }) {
        chk(await sb.auth.signInWithPassword({ email, password }));
        me = null;
        return api.session(true);
      },
      async signOut() { await sb.auth.signOut(); me = null; },
      async resetPassword(email) { chk(await sb.auth.resetPasswordForEmail(email, { redirectTo: baseUrl() + "login.html#neues-passwort" })); },
      async setPassword(password) { chk(await sb.auth.updateUser({ password })); },
      async updateName(name) {
        const u = await api.session();
        chk(await sb.from("profiles").update({ name }).eq("id", u.id));
        me = null;
      },

      async createOrder(f) {
        return tidy(chk(await sb.from("orders").insert({
          kind: f.kind, product: f.product, subject: f.subject || null, grade: f.grade || null,
          wish: f.wish || null, text_content: f.text_content || null, due_date: f.due_date || null
        }).select(SELECT).single()));
      },
      async uploadFile(order, file, messageId) {
        if (file.size > MAX_FILE) throw new Error("„" + file.name + "“ ist zu groß (max. 25 MB).");
        const u = await api.session();
        const folder = u.isAdmin ? "ergebnis/" : "";
        const path = order.user_id + "/" + order.id + "/" + folder + Date.now() + "-" + Math.random().toString(36).slice(2, 7) + "-" + safeName(file.name);
        const up = await sb.storage.from(BUCKET).upload(path, file, { contentType: file.type || "application/octet-stream", upsert: false });
        if (up.error) throw germanError(up.error);
        return chk(await sb.from("order_files").insert({ order_id: order.id, path, name: file.name || "datei", mime: file.type || "", size: file.size, message_id: messageId || null }).select().single());
      },
      async myOrders() {
        const u = await api.session();
        return chk(await sb.from("orders").select(SELECT).eq("user_id", u.id).order("created_at", { ascending: false })).map(tidy);
      },
      async allOrders() {
        return chk(await sb.from("orders").select(SELECT).order("created_at", { ascending: false })).map(tidy);
      },
      async getOrder(id) {
        return tidy(chk(await sb.from("orders").select(SELECT).eq("id", id).single()));
      },
      async fileUrl(f, download) {
        const key = f.path + (download ? "|dl" : "");
        const hit = urlCache.get(key);
        if (hit && hit.exp > Date.now()) return hit.url;
        const { data, error } = await sb.storage.from(BUCKET).createSignedUrl(f.path, 3600, download ? { download: f.name || true } : undefined);
        if (error) throw germanError(error);
        urlCache.set(key, { url: data.signedUrl, exp: Date.now() + 50 * 60 * 1000 });
        return data.signedUrl;
      },
      async sendMessage(order, body, files) {
        const msg = chk(await sb.from("messages").insert({ order_id: order.id, body: body || "" }).select().single());
        for (const f of files || []) await api.uploadFile(order, f, msg.id);
        return msg;
      },
      async updateOrder(id, patch) {
        return chk(await sb.from("orders").update(patch).eq("id", id).select().single());
      },
      async markPaid(id) { return api.updateOrder(id, { status: "neu", paid_at: new Date().toISOString(), paid_via: "manuell" }); },
      async markRead(orderId) { await sb.rpc("mark_read", { p_order: orderId }); },

      // ── Empfehlungsprogramm ──
      async referralInfo() {
        const u = await api.session();
        const info = chk(await sb.rpc("my_referral_info"));
        const credits = chk(await sb.from("credits").select("*").eq("user_id", u.id).order("created_at", { ascending: false }));
        const payouts = chk(await sb.from("payouts").select("*").eq("user_id", u.id).order("created_at", { ascending: false }));
        return { info, credits, payouts };
      },
      async setReferrer(code) { chk(await sb.rpc("set_referrer", { p_code: code })); },
      async payWithCredit(orderId) { chk(await sb.rpc("pay_with_credit", { p_order: orderId })); },
      async requestPayout(method, details) { chk(await sb.rpc("request_payout", { p_method: method, p_details: details })); },
      async adminReferrals() {
        const credits = chk(await sb.from("credits").select("*, user:profiles!credits_user_id_fkey(name,email), source:profiles!credits_source_user_id_fkey(name,email)").order("created_at", { ascending: false }).limit(500));
        const payouts = chk(await sb.from("payouts").select("*, user:profiles(name,email)").order("created_at", { ascending: false }).limit(200));
        return { credits, payouts };
      },
      async finishPayout(id, paid) { chk(await sb.rpc("admin_finish_payout", { p_id: id, p_paid: !!paid })); },
      async reverseCredit(id) { chk(await sb.rpc("admin_reverse_credit", { p_id: id })); },
      paymentUrl(order, email) {
        const link = order.price_cents >= 1299 ? C.STRIPE_LINK_COMBO : C.STRIPE_LINK_SINGLE;
        if (!link) return null;
        const u = new URL(link);
        u.searchParams.set("client_reference_id", String(order.id));
        if (email) u.searchParams.set("prefilled_email", email);
        return u.href;
      }
    };
    return api;
  }

  /* ═════════════════════════ DEMO (localStorage) ═════════════════════════ */
  function makeDemo() {
    // localStorage kann fehlen oder voll sein (privates Fenster, eingebettete Vorschau) → Speicher im Arbeitsspeicher als Ersatz
    const LS = (function () {
      let real = null;
      try { window.localStorage.setItem("__lk_t", "1"); window.localStorage.removeItem("__lk_t"); real = window.localStorage; } catch (e) { real = null; }
      const mem = new Map();
      return {
        getItem(k) { if (mem.has(k)) return mem.get(k); try { return real ? real.getItem(k) : null; } catch (e) { return null; } },
        setItem(k, v) { mem.set(k, String(v)); try { if (real) real.setItem(k, String(v)); } catch (e) { /* voll – bleibt im Arbeitsspeicher */ } },
        removeItem(k) { mem.delete(k); try { if (real) real.removeItem(k); } catch (e) { /* egal */ } },
        keys() { let ks = []; try { ks = real ? Object.keys(real) : []; } catch (e) { ks = []; } return Array.from(new Set(ks.concat(Array.from(mem.keys())))); }
      };
    })();
    const KEY = "lk_demo_v3", SKEY = "lk_demo_session", FKEY = "lk_demo_file_";
    const now = () => new Date().toISOString();
    const ago = (h) => new Date(Date.now() - h * 3600e3).toISOString();
    const wait = (ms) => new Promise((r) => setTimeout(r, ms || 120));

    function noteSvg(title, lines, hue) {
      const ls = lines.map((t, i) => '<text x="60" y="' + (190 + i * 54) + '" font-size="30" fill="#2b2a33" font-family="Georgia, serif">' + t + "</text>").join("");
      const rules = Array.from({ length: 14 }, (_, i) => '<line x1="0" x2="900" y1="' + (150 + i * 54 + 14) + '" y2="' + (150 + i * 54 + 14) + '" stroke="#c9d6ea" stroke-width="2"/>').join("");
      const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="900" height="680" viewBox="0 0 900 680"><rect width="900" height="680" fill="#fbf8f1"/>' + rules +
        '<line x1="40" x2="40" y1="0" y2="680" stroke="#f0a3a3" stroke-width="2"/><text x="60" y="110" font-size="44" font-weight="bold" fill="hsl(' + hue + ',45%,40%)" font-family="Georgia, serif">' + title + "</text>" + ls + "</svg>";
      return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
    }
    function textData(txt) { return "data:text/plain;charset=utf-8," + encodeURIComponent(txt); }

    const BONUS = 299, MIN_PAYOUT = 1000;
    function newCode(db) {
      const ch = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; let c;
      do { c = Array.from({ length: 6 }, () => ch[Math.floor(Math.random() * ch.length)]).join(""); } while (db.users.some((u) => u.ref_code === c));
      return c;
    }
    const balance = (db, uid) => db.credits.filter((c) => c.user_id === uid).reduce((s, c) => s + c.amount_cents, 0);
    function credit(db, row) { const c = Object.assign({ id: ++db.seq, source_user_id: null, order_id: null, payout_id: null, reverses_id: null, note: null, created_at: now() }, row); db.credits.push(c); return c; }
    // gleiche Regel wie in der Datenbank: Bonus beim ersten echten Kauf des geworbenen Freundes
    function onPaid(db, o, via) {
      o.status = "neu"; o.paid_at = now(); o.paid_via = via;
      const buyer = db.users.find((u) => u.id === o.user_id);
      if (via !== "guthaben" && buyer && buyer.referred_by && buyer.referred_by !== buyer.id &&
          !db.credits.some((c) => c.kind === "empfehlung" && c.source_user_id === buyer.id)) {
        credit(db, { user_id: buyer.referred_by, amount_cents: BONUS, kind: "empfehlung", source_user_id: buyer.id, order_id: o.id, note: "Empfehlung" });
      }
    }

    function seed() {
      const db = { seq: 1000, users: [], orders: [], files: [], messages: [], credits: [], payouts: [] };
      const id = () => ++db.seq;
      const admin = { id: "u-admin", name: "Admin", email: "admin@demo.de", password: "demo1234", isAdmin: true, created_at: ago(500) };
      const mia = { id: "u-mia", name: "Mia Schneider", email: "mia@demo.de", password: "demo1234", isAdmin: false, created_at: ago(300) };
      const leon = { id: "u-leon", name: "Leon Wagner", email: "leon@demo.de", password: "demo1234", isAdmin: false, created_at: ago(200) };
      const ela = { id: "u-ela", name: "Ela Yilmaz", email: "ela@demo.de", password: "demo1234", isAdmin: false, created_at: ago(100) };
      db.users.push(admin, mia, leon, ela);
      db.users.forEach((u) => (u.ref_code = newCode(db)));
      leon.referred_by = mia.id; ela.referred_by = mia.id;
      const mk = (u, o) => { const r = Object.assign({ id: id(), user_id: u.id, price_cents: priceOf(o.product), draft_message: null, due_date: null, text_content: null, wish: "", created_at: ago(o.h), updated_at: ago(o.h), paid_at: o.status === "unbezahlt" ? null : ago(o.h - 0.1) }, o); delete r.h; db.orders.push(r); return r; };
      const file = (o, name, mime, data, fromAdmin, msgId, h) => { const f = { id: id(), order_id: o.id, path: "demo/" + name, name, mime, size: Math.round(data.length * 0.75), from_admin: !!fromAdmin, message_id: msgId || null, created_at: ago(h) }; db.files.push(f); LS.setItem(FKEY + f.id, data); return f; };
      const msg = (o, fromAdmin, body, h, read) => { const m = { id: id(), order_id: o.id, from_admin: fromAdmin, body, created_at: ago(h), read_at: read ? ago(h - 0.5) : null }; db.messages.push(m); return m; };

      const o1 = mk(mia, { kind: "bild", product: "lernzettel", subject: "Biologie", grade: "9", status: "neu", wish: "Bitte einen Lernzettel zur Zellatmung, wir schreiben am Freitag eine Arbeit. Gern mit kleiner Skizze.", h: 3, due_date: new Date(Date.now() + 3 * 864e5).toISOString().slice(0, 10) });
      file(o1, "zellatmung-heft.svg", "image/svg+xml", noteSvg("Zellatmung", ["C6H12O6 + 6 O2 → 6 CO2 + 6 H2O", "1. Glykolyse (Zellplasma)", "2. Citratzyklus (Mitochondrien)", "3. Atmungskette → ATP", "Energie: ca. 36–38 ATP"], 150), false, null, 3);
      const o2 = mk(leon, { kind: "text", product: "zusammenfassung", subject: "Geschichte", grade: "10", status: "neu", wish: "Kurze Zusammenfassung, max. 1 Seite.", h: 7,
        text_content: "Die Weimarer Republik war die erste parlamentarische Demokratie in Deutschland. Sie entstand nach dem Ersten Weltkrieg und der Novemberrevolution 1918. Die Verfassung wurde 1919 in Weimar beschlossen. Von Anfang an hatte die Republik viele Probleme: den Versailler Vertrag, die Inflation 1923, politische Morde und Putschversuche von links und rechts. In den Goldenen Zwanzigern stabilisierte sich die Lage kurzzeitig, doch mit der Weltwirtschaftskrise 1929 stieg die Arbeitslosigkeit stark an …" });
      const o3 = mk(ela, { kind: "bild", product: "paket_referat", subject: "Erdkunde", grade: "8", status: "in_arbeit", wish: "Referat über Vulkane, ca. 8 Folien. Bitte schlichtes Design.", h: 26, draft_message: "Hi Ela, hier ist deine Präsentation …" });
      file(o3, "vulkane-buch.svg", "image/svg+xml", noteSvg("Vulkane", ["Aufbau: Magmakammer, Schlot, Krater", "Schildvulkan vs. Schichtvulkan", "Ring of Fire – Pazifik", "Beispiele: Ätna, Vesuv, Mauna Loa"], 15), false, null, 26);
      file(o3, "vulkane-seite2.svg", "image/svg+xml", noteSvg("Ausbruch", ["Plattentektonik", "Lava, Asche, pyroklastische Ströme", "Frühwarnsysteme"], 15), false, null, 26);
      const o4 = mk(mia, { kind: "text", product: "karteikarten", subject: "Englisch", grade: "9", status: "fertig", wish: "Vokabeln Unit 4 als Karteikarten bitte.", h: 80, text_content: "environment – Umwelt\nto reduce – verringern\nwaste – Müll, Abfall\nsustainable – nachhaltig\nclimate change – Klimawandel" });
      msg(o4, true, "Hi Mia! Hier sind deine Karteikarten zu Unit 4. Viel Erfolg beim Lernen! 🍀", 60, false);
      file(o4, "karteikarten-unit4.txt", "text/plain", textData("VORNE: environment\nHINTEN: Umwelt\n\nVORNE: to reduce\nHINTEN: verringern\n\nVORNE: waste\nHINTEN: Müll, Abfall\n\nVORNE: sustainable\nHINTEN: nachhaltig\n\nVORNE: climate change\nHINTEN: Klimawandel\n"), true, db.messages[db.messages.length - 1].id, 60);
      mk(leon, { kind: "text", product: "uebungsfragen", subject: "Mathe", grade: "10", status: "unbezahlt", wish: "Übungsaufgaben zu quadratischen Funktionen.", h: 1, text_content: "Scheitelpunktform, p-q-Formel, Nullstellen" });
      const o6 = mk(ela, { kind: "bild", product: "mindmap", subject: "Deutsch", grade: "8", status: "fertig", wish: "Mindmap zu den Figuren aus „Tschick“.", h: 120 });
      // Empfehlungen: Mia hat Leon + Ela geworben, Jonas vier Freunde (und will sich auszahlen lassen)
      credit(db, { user_id: mia.id, amount_cents: BONUS, kind: "empfehlung", source_user_id: leon.id, order_id: o2.id, note: "Empfehlung", created_at: ago(7) });
      credit(db, { user_id: mia.id, amount_cents: BONUS, kind: "empfehlung", source_user_id: ela.id, order_id: o3.id, note: "Empfehlung", created_at: ago(26) });
      const jonas = { id: "u-jonas", name: "Jonas Becker", email: "jonas@demo.de", password: "demo1234", isAdmin: false, created_at: ago(400), ref_code: newCode(db) };
      db.users.push(jonas);
      ["Paul Richter", "Lina Hoffmann", "Noah Klein", "Emma Wolf"].forEach((n, i) => {
        const f = { id: "u-f" + i, name: n, email: n.split(" ")[0].toLowerCase() + "@demo.de", password: "demo1234", isAdmin: false, created_at: ago(300 - i * 20), ref_code: newCode(db), referred_by: jonas.id };
        db.users.push(f);
        const fo = mk(f, { kind: "text", product: ["lernzettel", "karteikarten", "zusammenfassung", "powerpoint"][i], subject: "Mathe", grade: "10", status: "archiv", wish: "", h: 290 - i * 20, text_content: "Archivierter Beispielauftrag.", paid_via: "stripe" });
        credit(db, { user_id: jonas.id, amount_cents: BONUS, kind: "empfehlung", source_user_id: f.id, order_id: fo.id, note: "Empfehlung", created_at: ago(290 - i * 20) });
      });
      const pay = { id: ++db.seq, user_id: jonas.id, amount_cents: 4 * BONUS, method: "paypal", details: "jonas.becker@paypal.de", status: "offen", created_at: ago(5), done_at: null };
      db.payouts.push(pay);
      credit(db, { user_id: jonas.id, amount_cents: -4 * BONUS, kind: "auszahlung", payout_id: pay.id, note: "Auszahlung angefordert", created_at: ago(5) });
      file(o6, "tschick-notizen.svg", "image/svg+xml", noteSvg("Tschick – Figuren", ["Maik Klingenberg – Ich-Erzähler", "Tschick (Andrej) – neuer Mitschüler", "Isa – trifft die beiden auf der Müllkippe"], 280), false, null, 120);
      msg(o6, true, "Hier ist deine Mindmap. Sag Bescheid, wenn du noch etwas ergänzt haben möchtest!", 100, true);
      return db;
    }

    function load() {
      try { const db = JSON.parse(LS.getItem(KEY)); if (db && db.users) return db; } catch (e) { /* neu anlegen */ }
      const db = seed(); save(db); return db;
    }
    function save(db) { LS.setItem(KEY, JSON.stringify(db)); }
    const current = (db) => db.users.find((u) => u.id === LS.getItem(SKEY)) || null;
    const pub = (u) => u && { id: u.id, email: u.email, name: u.name, isAdmin: !!u.isAdmin };
    function full(db, o) {
      const u = db.users.find((x) => x.id === o.user_id) || {};
      return tidy(Object.assign({}, o, {
        student: { name: u.name, email: u.email },
        files: db.files.filter((f) => f.order_id === o.id),
        messages: db.messages.filter((m) => m.order_id === o.id)
      }));
    }
    function need(db, admin) {
      const u = current(db);
      if (!u) throw new Error("Bitte melde dich an.");
      if (admin && !u.isAdmin) throw new Error("Dafür fehlt dir die Berechtigung.");
      return u;
    }
    const readAsDataURL = (file) => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(file); });

    const api = {
      mode: "demo",
      async session() { return pub(current(load())); },
      onAuthChange() {},
      async signUp({ name, email, password, ref }) {
        await wait(250);
        const db = load();
        email = String(email).trim().toLowerCase();
        if (db.users.some((u) => u.email === email)) throw new Error("Für diese E-Mail gibt es schon ein Konto. Bitte melde dich an.");
        const referrer = ref ? db.users.find((x) => x.ref_code === String(ref).trim().toUpperCase()) : null;
        const u = { id: "u-" + Date.now(), name, email, password, isAdmin: false, created_at: now(), ref_code: newCode(db), referred_by: referrer ? referrer.id : null };
        db.users.push(u); save(db); LS.setItem(SKEY, u.id);
        return { user: pub(u) };
      },
      async signIn({ email, password }) {
        await wait(250);
        const db = load();
        const u = db.users.find((x) => x.email === String(email).trim().toLowerCase() && x.password === password);
        if (!u) throw new Error("E-Mail oder Passwort ist falsch.");
        LS.setItem(SKEY, u.id);
        return pub(u);
      },
      async signOut() { LS.removeItem(SKEY); },
      async resetPassword() { await wait(300); },
      async setPassword(pw) { const db = load(); need(db).password = pw; save(db); },
      async updateName(name) { const db = load(); need(db).name = name; save(db); },

      async createOrder(f) {
        await wait(200);
        const db = load(); const u = need(db);
        const o = { id: ++db.seq, user_id: u.id, kind: f.kind, product: f.product, subject: f.subject || null, grade: f.grade || null, wish: f.wish || null, text_content: f.text_content || null, due_date: f.due_date || null, status: "unbezahlt", price_cents: priceOf(f.product), paid_at: null, draft_message: null, created_at: now(), updated_at: now() };
        db.orders.push(o); save(db);
        return full(db, o);
      },
      async uploadFile(order, file, messageId) {
        if (file.size > MAX_FILE) throw new Error("„" + file.name + "“ ist zu groß (max. 25 MB).");
        const db = load(); const u = need(db);
        const rec = { id: ++db.seq, order_id: order.id, path: "demo/" + safeName(file.name), name: file.name || "datei", mime: file.type || "", size: file.size, from_admin: !!u.isAdmin, message_id: messageId || null, created_at: now() };
        try { LS.setItem(FKEY + rec.id, await readAsDataURL(file)); } catch (e) { /* Speicher voll – in der Vorschau egal */ }
        db.files.push(rec); save(db);
        return rec;
      },
      async myOrders() { await wait(); const db = load(); const u = need(db); return db.orders.filter((o) => o.user_id === u.id).sort((a, b) => -byDate(a, b)).map((o) => full(db, o)); },
      async allOrders() { await wait(); const db = load(); need(db, true); return db.orders.slice().sort((a, b) => -byDate(a, b)).map((o) => full(db, o)); },
      async getOrder(id) {
        await wait(); const db = load(); const u = need(db);
        const o = db.orders.find((x) => x.id === Number(id));
        if (!o || (!u.isAdmin && o.user_id !== u.id)) throw new Error("Auftrag nicht gefunden.");
        return full(db, o);
      },
      async fileUrl(f) { return LS.getItem(FKEY + f.id) || ""; },
      async sendMessage(order, body, files) {
        const db = load(); const u = need(db);
        const m = { id: ++db.seq, order_id: order.id, from_admin: !!u.isAdmin, body: body || "", created_at: now(), read_at: null };
        db.messages.push(m); save(db);
        for (const f of files || []) await api.uploadFile(order, f, m.id);
        return m;
      },
      async updateOrder(id, patch) {
        const db = load(); need(db, true);
        const o = db.orders.find((x) => x.id === Number(id));
        Object.assign(o, patch, { updated_at: now() }); save(db);
        return o;
      },
      async markPaid(id) {
        const db = load(); need(db, true);
        const o = db.orders.find((x) => x.id === Number(id));
        if (o && o.status === "unbezahlt") { onPaid(db, o, "manuell"); save(db); }
      },
      async demoPay(id) {
        await wait(700);
        const db = load(); const u = need(db);
        const o = db.orders.find((x) => x.id === Number(id) && x.user_id === u.id);
        if (o && o.status === "unbezahlt") { onPaid(db, o, "stripe"); save(db); }
      },

      // ── Empfehlungsprogramm (Demo, gleiche Regeln wie die Datenbank) ──
      async referralInfo() {
        await wait(); const db = load(); const u = need(db);
        const earned = db.credits.filter((c) => c.user_id === u.id && c.kind === "empfehlung");
        return {
          info: {
            code: u.ref_code, has_referrer: !!u.referred_by,
            can_set_referrer: !u.referred_by && !db.orders.some((o) => o.user_id === u.id && o.status !== "unbezahlt"),
            balance_cents: balance(db, u.id), invited: db.users.filter((x) => x.referred_by === u.id).length,
            bought: earned.length, earned_cents: earned.reduce((s, c) => s + c.amount_cents, 0),
            bonus_cents: BONUS, min_payout_cents: MIN_PAYOUT
          },
          credits: db.credits.filter((c) => c.user_id === u.id).sort((a, b) => -byDate(a, b)),
          payouts: db.payouts.filter((p) => p.user_id === u.id).sort((a, b) => -byDate(a, b))
        };
      },
      async setReferrer(code) {
        const db = load(); const u = need(db);
        const ref = db.users.find((x) => x.ref_code === String(code || "").trim().toUpperCase());
        if (!ref) throw new Error("Diesen Empfehlungscode gibt es nicht.");
        if (ref.id === u.id) throw new Error("Du kannst dich nicht selbst empfehlen.");
        if (ref.referred_by === u.id) throw new Error("Ihr könnt euch nicht gegenseitig empfehlen.");
        if (db.orders.some((o) => o.user_id === u.id && o.status !== "unbezahlt")) throw new Error("Ein Code kann nur vor dem ersten Kauf eingetragen werden.");
        if (u.referred_by) throw new Error("Du hast schon einen Empfehlungscode eingetragen.");
        u.referred_by = ref.id; save(db);
      },
      async payWithCredit(orderId) {
        await wait(300); const db = load(); const u = need(db);
        const o = db.orders.find((x) => x.id === Number(orderId) && x.user_id === u.id);
        if (!o) throw new Error("Auftrag nicht gefunden.");
        if (o.status !== "unbezahlt") throw new Error("Dieser Auftrag ist schon bezahlt.");
        if (balance(db, u.id) < o.price_cents) throw new Error("Nicht genug Guthaben.");
        credit(db, { user_id: u.id, amount_cents: -o.price_cents, kind: "bezahlung", order_id: o.id, note: "Auftrag mit Guthaben bezahlt" });
        onPaid(db, o, "guthaben"); save(db);
      },
      async requestPayout(method, details) {
        await wait(300); const db = load(); const u = need(db);
        const bal = balance(db, u.id);
        if (bal < MIN_PAYOUT) throw new Error("Auszahlung ist erst ab dem Mindestbetrag möglich.");
        const p = { id: ++db.seq, user_id: u.id, amount_cents: bal, method, details: String(details).trim(), status: "offen", created_at: now(), done_at: null };
        db.payouts.push(p);
        credit(db, { user_id: u.id, amount_cents: -bal, kind: "auszahlung", payout_id: p.id, note: "Auszahlung angefordert" });
        save(db);
      },
      async adminReferrals() {
        await wait(); const db = load(); need(db, true);
        const who = (id) => { const x = db.users.find((u) => u.id === id); return x ? { name: x.name, email: x.email } : null; };
        return {
          credits: db.credits.slice().sort((a, b) => -byDate(a, b)).map((c) => Object.assign({}, c, { user: who(c.user_id), source: who(c.source_user_id) })),
          payouts: db.payouts.slice().sort((a, b) => -byDate(a, b)).map((p) => Object.assign({}, p, { user: who(p.user_id) }))
        };
      },
      async finishPayout(id, paid) {
        const db = load(); need(db, true);
        const p = db.payouts.find((x) => x.id === Number(id));
        if (!p || p.status !== "offen") throw new Error("Diese Auszahlung ist schon erledigt.");
        p.status = paid ? "ausgezahlt" : "abgelehnt"; p.done_at = now();
        if (!paid) credit(db, { user_id: p.user_id, amount_cents: p.amount_cents, kind: "korrektur", payout_id: p.id, note: "Auszahlung abgelehnt – Guthaben zurückgebucht" });
        save(db);
      },
      async reverseCredit(id) {
        const db = load(); need(db, true);
        const c = db.credits.find((x) => x.id === Number(id));
        if (!c || c.kind !== "empfehlung") throw new Error("Nur Empfehlungs-Gutschriften können storniert werden.");
        if (!db.credits.some((x) => x.reverses_id === c.id)) credit(db, { user_id: c.user_id, amount_cents: -c.amount_cents, kind: "korrektur", reverses_id: c.id, note: "Empfehlungs-Bonus storniert" });
        save(db);
      },
      async markRead(orderId) {
        const db = load(); const u = need(db);
        db.messages.forEach((m) => { if (m.order_id === Number(orderId) && !m.read_at && m.from_admin !== !!u.isAdmin) m.read_at = now(); });
        save(db);
      },
      paymentUrl(order) { return "bezahlen.html?order=" + order.id; },
      demoReset() {
        LS.keys().filter((k) => k.startsWith("lk_demo")).forEach((k) => LS.removeItem(k));
      }
    };
    return api;
  }

  window.API = LIVE ? makeLive() : makeDemo();
})();
