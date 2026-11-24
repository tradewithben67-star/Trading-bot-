/* Gemeinsame Helfer für alle Seiten */
(function () {
  const C = window.APP_CONFIG || {};

  // ── Icons (Strichgrafiken im Stil von Lucide) ──
  const P = {
    arrowUp: '<path d="M12 19V5"/><path d="m5 12 7-7 7 7"/>',
    image: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.1-3.1a2 2 0 0 0-2.8 0L6 21"/>',
    text: '<path d="M4 7V5h16v2"/><path d="M9 19h6"/><path d="M12 5v14"/>',
    crop: '<path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M18 22V8a2 2 0 0 0-2-2H2"/>',
    rotate: '<path d="M21 12a9 9 0 1 1-9-9c2.5 0 4.8 1 6.5 2.7L21 8"/><path d="M21 3v5h-5"/>',
    sliders: '<path d="M4 21v-7"/><path d="M4 10V3"/><path d="M12 21v-9"/><path d="M12 8V3"/><path d="M20 21v-5"/><path d="M20 12V3"/><path d="M2 14h4"/><path d="M10 8h4"/><path d="M18 16h4"/>',
    pencil: '<path d="M21.2 6.8a2.8 2.8 0 0 0-4-4L3.8 16.2 3 21l4.8-.8Z"/><path d="m15 5 4 4"/>',
    undo: '<path d="M9 14 4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>',
    download: '<path d="M12 15V3"/><path d="m7 10 5 5 5-5"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>',
    attach: '<path d="m21.4 11-8.6 8.6a5.7 5.7 0 0 1-8-8l8.5-8.6a3.8 3.8 0 0 1 5.4 5.4l-8.6 8.6a1.9 1.9 0 0 1-2.7-2.7l8-8"/>',
    chevronLeft: '<path d="m15 18-6-6 6-6"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>',
    inbox: '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.7 4H7.3a2 2 0 0 0-1.8 1.1Z"/>',
    mail: '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    x: '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    user: '<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>',
    plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
    send: '<path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    folder: '<path d="M4 20h16a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-8l-2-3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    archive: '<rect x="2" y="3" width="20" height="5" rx="1"/><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8"/><path d="M10 12h4"/>',
    card: '<rect x="2" y="5" width="20" height="14" rx="2"/><path d="M2 10h20"/>',
    copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    gift: '<rect x="3" y="8" width="18" height="4" rx="1"/><path d="M12 8v13"/><path d="M19 12v7a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2v-7"/><path d="M7.5 8a2.5 2.5 0 0 1 0-5C10 3 12 8 12 8s2-5 4.5-5a2.5 2.5 0 0 1 0 5"/>',
    share: '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.6 13.5 6.8 4"/><path d="m15.4 6.5-6.8 4"/>',
    wallet: '<path d="M19 7V4a1 1 0 0 0-1-1H5a2 2 0 0 0 0 4h15a1 1 0 0 1 1 1v4h-3a2 2 0 0 0 0 4h3a1 1 0 0 0 1-1v-2"/><path d="M3 5v14a2 2 0 0 0 2 2h15a1 1 0 0 0 1-1v-4"/>',
    globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20"/>',
    // Produkte
    presentation: '<path d="M2 3h20"/><path d="M21 3v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V3"/><path d="m7 21 5-5 5 5"/>',
    notebook: '<path d="M2 6h4"/><path d="M2 10h4"/><path d="M2 14h4"/><path d="M2 18h4"/><rect x="4" y="2" width="16" height="20" rx="2"/><path d="M16 2v20"/>',
    summary: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
    cards: '<rect x="2" y="6" width="15" height="14" rx="2"/><path d="M7 3h13a2 2 0 0 1 2 2v11"/>',
    mindmap: '<circle cx="12" cy="12" r="3"/><circle cx="4" cy="5" r="2"/><circle cx="20" cy="5" r="2"/><circle cx="4" cy="19" r="2"/><circle cx="20" cy="19" r="2"/><path d="m6 6.5 3.7 3.5"/><path d="m18 6.5-3.7 3.5"/><path d="m6 17.5 3.7-3.5"/><path d="m18 17.5-3.7-3.5"/>',
    quiz: '<circle cx="12" cy="12" r="10"/><path d="M9.1 9a3 3 0 0 1 5.8 1c0 2-3 3-3 3"/><path d="M12 17h.01"/>',
    write: '<path d="M12 20h9"/><path d="M16.4 3.6a2.1 2.1 0 1 1 3 3L7 19l-4 1 1-4Z"/>',
    handout: '<path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z"/><path d="M8 12h8"/><path d="M8 16h5"/><path d="M8 8h3"/>'
  };
  function icon(name, cls) {
    return '<svg class="i' + (cls ? " " + cls : "") + '" viewBox="0 0 24 24" aria-hidden="true">' + (P[name] || "") + "</svg>";
  }

  // ── Leistungen ──
  const PRODUCTS = [
    { id: "powerpoint", name: "PowerPoint", long: "PowerPoint-Präsentation", icon: "presentation", desc: "Fertige Folien für dein Referat – klar gegliedert, mit passenden Stichpunkten." },
    { id: "lernzettel", name: "Lernzettel", long: "Lernzettel", icon: "notebook", desc: "Das Wichtigste auf einen Blick – perfekt für die letzte Wiederholung vor der Arbeit." },
    { id: "zusammenfassung", name: "Zusammenfassung", long: "Zusammenfassung", icon: "summary", desc: "Langes Kapitel, kurzer Text: die Kernaussagen verständlich zusammengefasst." },
    { id: "karteikarten", name: "Karteikarten", long: "Karteikarten", icon: "cards", desc: "Frage vorne, Antwort hinten – zum Ausdrucken oder für deine Lern-App." },
    { id: "mindmap", name: "Mindmap", long: "Mindmap", icon: "mindmap", desc: "Zusammenhänge sichtbar machen – ein Thema als übersichtliche Grafik." },
    { id: "uebungsfragen", name: "Übungsfragen", long: "Übungsfragen mit Lösungen", icon: "quiz", desc: "Teste dich selbst: Aufgaben im Stil deiner nächsten Klassenarbeit, inkl. Lösungen." },
    { id: "text", name: "Text überarbeiten", long: "Text schreiben / überarbeiten", icon: "write", desc: "Rechtschreibung, Ausdruck, Aufbau – dein Text wird klarer und besser." },
    { id: "handout", name: "Referat-Handout", long: "Handout fürs Referat", icon: "handout", desc: "Eine Seite für deine Mitschüler – kompakt, sauber und gut lesbar." }
  ];
  const productById = (id) => PRODUCTS.find((p) => p.id === id) || { id, name: id, long: id, icon: "file" };

  const SUBJECTS = ["Deutsch", "Englisch", "Mathe", "Biologie", "Chemie", "Physik", "Geschichte", "Erdkunde", "Politik / Sozialkunde", "Wirtschaft", "Religion / Ethik", "Französisch", "Latein", "Spanisch", "Informatik", "Kunst", "Musik", "Sport", "Sonstiges"];
  const GRADES = ["5", "6", "7", "8", "9", "10", "11", "12", "13", "Berufsschule", "Studium", "Sonstiges"];

  const STATUS = {
    unbezahlt: "Unbezahlt",
    neu: "Neu",
    in_arbeit: "In Arbeit",
    fertig: "Fertig",
    archiv: "Archiv"
  };
  const STATUS_STUDENT = { unbezahlt: "Zahlung offen", neu: "Eingegangen", in_arbeit: "In Arbeit", fertig: "Fertig", archiv: "Abgeschlossen" };

  // ── Format ──
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmtDate = (d) => d ? new Date(d).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" }) : "";
  const fmtDateTime = (d) => d ? new Date(d).toLocaleString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "";
  const fmtSize = (b) => !b ? "" : b < 1024 * 1024 ? Math.max(1, Math.round(b / 1024)) + " KB" : (b / 1024 / 1024).toFixed(1).replace(".", ",") + " MB";
  const isImage = (f) => /^image\//.test(f.mime || "") || /\.(png|jpe?g|webp|gif|heic)$/i.test(f.name || "");
  const badge = (status, student) => '<span class="badge badge-' + esc(status) + '">' + esc((student ? STATUS_STUDENT : STATUS)[status] || status) + "</span>";
  const orderNo = (o) => "#" + String(o.id).padStart(4, "0");
  const eur = (cents) => ((cents || 0) / 100).toLocaleString("de-DE", { style: "currency", currency: "EUR" });

  // ── Empfehlungscode aus dem Link (?ref=CODE) merken, bis sich jemand registriert ──
  const REF_KEY = "lk_ref";
  function getRef() { try { return localStorage.getItem(REF_KEY) || ""; } catch (e) { return ""; } }
  function clearRef() { try { localStorage.removeItem(REF_KEY); } catch (e) { /* egal */ } }
  (function captureRef() {
    const r = new URLSearchParams(location.search).get("ref");
    if (r && /^[A-Za-z0-9]{4,12}$/.test(r)) { try { localStorage.setItem(REF_KEY, r.toUpperCase()); } catch (e) { /* egal */ } }
  })();
  const refLink = (code) => new URL("index.html?ref=" + encodeURIComponent(code), location.href).href;

  // ── Toast ──
  function toast(msg, isErr) {
    let wrap = document.querySelector(".toast-wrap");
    if (!wrap) { wrap = document.createElement("div"); wrap.className = "toast-wrap"; wrap.setAttribute("role", "status"); document.body.appendChild(wrap); }
    const t = document.createElement("div");
    t.className = "toast" + (isErr ? " err" : "");
    t.innerHTML = icon(isErr ? "info" : "check") + "<span>" + esc(msg) + "</span>";
    wrap.appendChild(t);
    setTimeout(() => t.remove(), isErr ? 6000 : 3500);
  }

  // ── Seitenname einsetzen ──
  function applySiteName() {
    document.querySelectorAll("[data-site-name]").forEach((el) => (el.textContent = C.SITE_NAME || "Lernkiste"));
    document.querySelectorAll("[data-price]").forEach((el) => (el.textContent = C.PRICE_LABEL || "7,99 €"));
    document.querySelectorAll("[data-bonus]").forEach((el) => (el.textContent = C.REFERRAL_BONUS_LABEL || "2,99 €"));
    document.querySelectorAll("[data-min-payout]").forEach((el) => (el.textContent = C.MIN_PAYOUT_LABEL || "10,00 €"));
    document.querySelectorAll("[data-delivery]").forEach((el) => (el.textContent = C.DELIVERY_TEXT || ""));
    document.querySelectorAll("[data-contact]").forEach((el) => { el.textContent = C.CONTACT_EMAIL; if (el.tagName === "A") el.href = "mailto:" + C.CONTACT_EMAIL; });
    document.querySelectorAll("[data-year]").forEach((el) => (el.textContent = new Date().getFullYear()));
    if (document.title.includes("{SITE}")) document.title = document.title.replace("{SITE}", C.SITE_NAME || "Lernkiste");
    document.querySelectorAll("[data-icon]").forEach((el) => { el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon)); el.removeAttribute("data-icon"); });
  }

  // ── Vorschau-Hinweis ──
  function demoBar() {
    if (!window.API || window.API.mode !== "demo" || document.querySelector(".demo-bar")) return;
    const bar = document.createElement("div");
    bar.className = "demo-bar";
    bar.innerHTML = "<b>Vorschau-Modus</b> – Daten bleiben nur in diesem Browser. Admin-Test: <b>admin@demo.de</b> / <b>demo1234</b> <button type=\"button\">Demo zurücksetzen</button>";
    bar.querySelector("button").onclick = () => { window.API.demoReset(); location.reload(); };
    document.body.prepend(bar);
  }

  function onScrollHeader() {
    const h = document.querySelector(".site-header");
    if (!h) return;
    const f = () => h.classList.toggle("scrolled", window.scrollY > 8);
    window.addEventListener("scroll", f, { passive: true }); f();
  }

  // Header-Buttons je nach Login-Status
  async function renderAuthNav() {
    const slot = document.querySelector("[data-auth-slot]");
    if (!slot) return null;
    const user = await window.API.session().catch(() => null);
    if (user) {
      const target = user.isAdmin ? "admin.html" : "konto.html";
      slot.innerHTML = '<a class="btn btn-sm" href="' + target + '">' + icon(user.isAdmin ? "inbox" : "user") + (user.isAdmin ? "Admin" : "Mein Konto") + "</a>";
    } else {
      slot.innerHTML = '<a class="btn btn-sm" href="login.html">Anmelden</a>';
    }
    return user;
  }

  function setRangeFill(input) {
    const min = +input.min || 0, max = +input.max || 100;
    input.style.setProperty("--p", ((input.value - min) / (max - min)) * 100 + "%");
  }

  window.UI = { eur, getRef, clearRef, refLink, icon, PRODUCTS, productById, SUBJECTS, GRADES, STATUS, STATUS_STUDENT, esc, fmtDate, fmtDateTime, fmtSize, isImage, badge, orderNo, toast, applySiteName, demoBar, onScrollHeader, renderAuthNav, setRangeFill };

  document.addEventListener("DOMContentLoaded", () => { applySiteName(); demoBar(); onScrollHeader(); });
})();
