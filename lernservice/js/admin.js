/* Admin: Eingang + Bearbeiten & Zurückschicken */
(async function () {
  const { icon, esc, fmtDate, fmtDateTime, fmtSize, isImage, badge, orderNo, productById, toast, setRangeFill, eur } = window.UI;
  const view = document.getElementById("view");
  const SITE = window.APP_CONFIG.SITE_NAME;

  const me = await API.session().catch(() => null);
  if (!me) { location.replace("login.html?next=admin.html"); return; }
  if (!me.isAdmin) { location.replace("konto.html"); return; }
  document.getElementById("logout").onclick = async () => { await API.signOut(); location.href = "index.html"; };

  const VIEWS = {
    eingang: { title: "Eingang", match: (o) => ["neu", "in_arbeit", "fertig"].includes(o.status) },
    bearbeitung: { title: "In Bearbeitung", match: (o) => o.status === "in_arbeit" },
    fertig: { title: "Fertig & verschickt", match: (o) => o.status === "fertig" },
    archiv: { title: "Archiv", match: (o) => o.status === "archiv" },
    unbezahlt: { title: "Unbezahlt", match: (o) => o.status === "unbezahlt" }
  };
  let orders = [], kindFilter = "alle", query = "", lastList = "eingang";
  const unreadOf = (o) => o.messages.filter((m) => !m.from_admin && !m.read_at).length;

  async function load() {
    orders = await API.allOrders();
    const n = (s) => orders.filter((o) => o.status === s).length;
    const ce = document.getElementById("c-eingang"); ce.textContent = n("neu"); ce.classList.toggle("hidden", !n("neu"));
    document.getElementById("c-bearbeitung").textContent = n("in_arbeit") || "";
    document.getElementById("c-fertig").textContent = n("fertig") || "";
    document.getElementById("c-unbezahlt").textContent = n("unbezahlt") || "";
    refreshPayoutCount();
  }
  async function refreshPayoutCount() {
    try {
      const { payouts } = await API.adminReferrals();
      const open = payouts.filter((p) => p.status === "offen").length;
      const el = document.getElementById("c-payouts"); el.textContent = open; el.classList.toggle("hidden", !open);
    } catch (e) { /* Empfehlungs-Tabellen evtl. noch nicht eingerichtet */ }
  }
  function setNav(v) { document.querySelectorAll(".side-nav a").forEach((a) => a.setAttribute("aria-current", a.dataset.view === v ? "page" : "false")); }

  async function route() {
    const h = location.hash.replace(/^#/, "") || "eingang";
    view.classList.remove("flush");
    view.onclick = null;
    window.scrollTo(0, 0);
    try {
      if (h.startsWith("auftrag/")) { setNav(lastList); return await openEditor(Number(h.split("/")[1])); }
      if (h === "empfehlungen") { setNav("empfehlungen"); await load(); return await showReferrals(); }
      lastList = VIEWS[h] ? h : "eingang";
      setNav(lastList);
      await load();
      renderList();
    } catch (e) {
      view.innerHTML = '<div class="empty">' + icon("info") + "<h3>Fehler</h3><p>" + esc(e.message) + '</p><a class="btn" href="#eingang">Zum Eingang</a></div>';
    }
  }
  window.addEventListener("hashchange", route);

  /* ═══════════ Liste (Eingang) ═══════════ */
  function renderList() {
    const v = VIEWS[lastList];
    view.innerHTML =
      '<div class="main-head"><h1>' + esc(v.title) + '</h1><label class="search">' + icon("search") + '<span class="sr-only">Suchen</span><input class="input" id="q" type="search" placeholder="Suchen nach Name oder E-Mail" value="' + esc(query) + '"></label></div>' +
      '<div class="toolbar"><div class="chips" id="kinds">' + [["alle", "Alle"], ["bild", "Bilder"], ["text", "Texte"]].map(([k, t]) => '<button class="chip" aria-pressed="' + (kindFilter === k) + '" data-k="' + k + '">' + t + "</button>").join("") + "</div></div>" +
      '<div id="cards"></div>';
    document.getElementById("q").addEventListener("input", (e) => { query = e.target.value; renderCards(); });
    document.getElementById("kinds").addEventListener("click", (e) => {
      const b = e.target.closest(".chip"); if (!b) return;
      kindFilter = b.dataset.k;
      document.querySelectorAll("#kinds .chip").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      renderCards();
    });
    renderCards();
  }

  function renderCards() {
    const q = query.trim().toLowerCase();
    const list = orders.filter(VIEWS[lastList].match)
      .filter((o) => kindFilter === "alle" || o.kind === kindFilter)
      .filter((o) => !q || (o.student.name || "").toLowerCase().includes(q) || (o.student.email || "").toLowerCase().includes(q) || orderNo(o).includes(q));
    const box = document.getElementById("cards");
    if (!list.length) {
      box.innerHTML = '<div class="empty">' + icon("inbox") + "<h3>Nichts da</h3><p>" + (q ? "Keine Treffer für deine Suche." : "Hier ist gerade nichts.") + "</p></div>";
      return;
    }
    box.innerHTML = '<div class="grid">' + list.map((o) => {
      const p = productById(o.product);
      const unread = unreadOf(o);
      const preview = o.kind === "text" ? '<div class="txt">' + esc((o.text_content || "").slice(0, 260)) + "</div>" : '<span data-thumb="' + o.id + '">' + icon("image") + "</span>";
      const due = o.due_date ? " · bis " + fmtDate(o.due_date) : "";
      return '<a class="sub-card" href="#auftrag/' + o.id + '"><div class="preview">' + preview +
        (unread ? '<span class="flag"><span class="dot"></span>Neue Nachricht</span>' : "") +
        '</div><div class="body"><div class="top"><b>' + esc(o.student.name || o.student.email || "Unbekannt") + "</b>" + badge(o.status) + "</div>" +
        '<div class="meta">' + (o.kind === "bild" ? "Bild" : "Text") + " · " + esc(p.name) + " · " + fmtDate(o.created_at) + esc(due) + "</div></div></a>";
    }).join("") + "</div>";
    for (const o of list) {
      const f = o.files.find((x) => !x.from_admin && isImage(x));
      const slot = box.querySelector('[data-thumb="' + o.id + '"]');
      if (f && slot) API.fileUrl(f).then((u) => { if (u) slot.outerHTML = '<img alt="" src="' + esc(u) + '">'; }).catch(() => {});
    }
  }

  /* ═══════════ Editor (Bearbeiten) ═══════════ */
  async function openEditor(id) {
    const o = await API.getOrder(id);
    if (unreadOf(o)) API.markRead(o.id);
    const p = productById(o.product);
    const sFiles = o.files.filter((f) => !f.from_admin);
    const imgs = sFiles.filter(isImage);
    const docs = sFiles.filter((f) => !isImage(f));
    const pending = []; // Ergebnis-Dateien, die beim Zurückschicken hochgeladen werden
    const isImg = o.kind === "bild" && imgs.length > 0;
    view.classList.add("flush");

    const daysLeft = o.due_date ? Math.ceil((new Date(o.due_date) - new Date()) / 864e5) : null;
    const tools = isImg
      ? [["rotate", "rotate", "Drehen"], ["adjust", "sliders", "Anpassen"], ["draw", "pencil", "Zeichnen"], ["reset", "undo", "Zurücksetzen"], ["sep"], ["download", "download", "Bild herunterladen"], ["attach", "attach", "Als Ergebnis anhängen"]]
      : o.kind === "text" ? [["copy", "copy", "Text kopieren"], ["txt", "download", "Als .txt herunterladen"]] : [];

    view.innerHTML =
      '<div class="editor">' +
      '<div class="editor-top"><a class="icon-btn" href="#' + lastList + '" aria-label="Zurück">' + icon("chevronLeft") + "</a>" +
        '<div class="ttl"><h1>Einsendung von ' + esc(o.student.name || "Unbekannt") + '</h1><div class="sub">' + esc(o.student.email) + " · " + fmtDateTime(o.created_at) + " · " + orderNo(o) + "</div></div>" +
        '<div class="acts"><button class="btn" id="saveDraft">Entwurf speichern</button><button class="btn btn-primary" id="sendDone">Fertig &amp; zurückschicken</button></div></div>' +
      '<div class="editor-body">' +
        '<div class="toolrail" id="rail">' + tools.map((t) => t[0] === "sep" ? '<div class="tool-sep"></div>' : '<button class="tool" data-tool="' + t[0] + '" title="' + t[2] + '" aria-label="' + t[2] + '"' + (t[0] === "adjust" || t[0] === "draw" ? ' aria-pressed="' + (t[0] === "adjust") + '"' : "") + ">" + icon(t[1]) + "</button>").join("") + "</div>" +
        '<div class="stage" id="stage"></div>' +
        '<aside class="side-panel">' +
          "<div><div class=\"section-label\">Wunsch des Absenders</div>" +
            (o.wish ? '<div class="quote">' + esc(o.wish) + "</div>" : '<div class="quote faint">Kein zusätzlicher Wunsch angegeben.</div>') +
            '<dl class="kv" style="margin-top:12px"><dt>Paket</dt><dd><b>' + esc(p.combo ? p.name : p.long) + "</b></dd>" +
            (p.combo ? '<dt>Liefern</dt><dd class="contents">' + p.items.map((i) => '<span class="item-chip">' + icon(productById(i).icon) + esc(productById(i).name) + "</span>").join("") + "</dd>" : "") +
            "<dt>Preis</dt><dd>" + eur(o.price_cents) + "</dd>" +
            (o.subject ? "<dt>Fach</dt><dd>" + esc(o.subject) + "</dd>" : "") + (o.grade ? "<dt>Klasse</dt><dd>" + esc(o.grade) + "</dd>" : "") +
            (o.due_date ? "<dt>Bis</dt><dd class=\"" + (daysLeft <= 2 ? "due-soon" : "") + "\">" + fmtDate(o.due_date) + (daysLeft != null ? " (" + (daysLeft < 0 ? "überfällig" : daysLeft === 0 ? "heute" : "noch " + daysLeft + " T.") + ")" : "") + "</dd>" : "") +
            "<dt>Bezahlt</dt><dd>" + (o.paid_at ? fmtDateTime(o.paid_at) : '<span class="badge badge-unbezahlt">offen</span>') + "</dd></dl></div>" +
          (isImg ? '<div id="adjustBox"><div class="section-label">Anpassen</div>' + [["b", "Helligkeit"], ["c", "Kontrast"], ["s", "Sättigung"]].map(([k, t]) => '<div class="slider"><div class="lbl"><span>' + t + '</span><span id="v-' + k + '">0</span></div><input type="range" min="-100" max="100" value="0" data-adj="' + k + '" aria-label="' + t + '"></div>').join("") + "</div>" +
            '<div id="penBox" class="hidden"><div class="section-label">Stift</div><div class="swatches">' + ["#b5a6f6", "#ff5c5c", "#ffd84d", "#33c27a", "#ffffff", "#111111"].map((c, i) => '<button style="background:' + c + '" data-color="' + c + '" aria-label="Farbe ' + c + '" aria-pressed="' + (i === 1) + '"></button>').join("") + "</div></div>" : "") +
          '<div><div class="section-label">Ergebnis-Dateien</div><div class="files" id="pendingList"></div>' +
            '<label class="btn btn-sm" style="margin-top:10px;position:relative">' + icon("plus") + 'Dateien hinzufügen<input type="file" id="resultInput" multiple style="position:absolute;inset:0;opacity:0;cursor:pointer" accept=".pptx,.ppt,.key,.pdf,.docx,.doc,.odt,.odp,.txt,.csv,.xlsx,.apkg,.zip,image/*"></label>' +
            '<p class="pending-note" style="margin-top:8px">PowerPoint, PDF, Word, Bilder … werden beim Zurückschicken hochgeladen.</p></div>' +
          '<div><div class="section-label">Nachricht an den Absender</div><textarea class="textarea" id="msg" rows="4" placeholder="z. B. Hier ist dein fertiger Lernzettel – viel Erfolg!">' + esc(o.draft_message || "") + '</textarea>' +
            '<button class="btn btn-ghost btn-sm" id="askOnly" style="margin-top:6px;padding:0">' + icon("send") + "Nur Nachricht senden (Rückfrage)</button></div>" +
          '<div><div class="section-label">Status</div><div class="status-chips" id="statusChips">' +
            (o.status === "unbezahlt"
              ? badge("unbezahlt") + ' <button class="btn btn-sm" id="markPaid" style="opacity:1">Als bezahlt markieren</button>'
              : ["neu", "in_arbeit", "fertig", "archiv"].map((s) => '<button data-s="' + s + '" aria-pressed="' + (o.status === s) + '">' + badge(s) + "</button>").join("")) +
          "</div></div>" +
          '<div><div class="section-label">Verlauf</div><div class="thread" id="thread"></div></div>' +
        "</aside>" +
      "</div></div>";

    // ── Verlauf ──
    const thread = document.getElementById("thread");
    if (!o.messages.length) thread.innerHTML = '<p class="faint" style="font-size:13.5px">Noch keine Nachrichten.</p>';
    else {
      const parts = await Promise.all(o.messages.map(async (m) => {
        const att = o.files.filter((f) => f.message_id === m.id);
        const urls = await Promise.all(att.map((f) => API.fileUrl(f, true).catch(() => "")));
        return '<div class="msg' + (m.from_admin ? " mine" : "") + '"><div class="who"><b>' + (m.from_admin ? "Du" : esc(o.student.name || "Schüler")) + "</b><span>" + fmtDateTime(m.created_at) + "</span></div>" +
          (m.body ? '<div class="txt">' + esc(m.body) + "</div>" : "") +
          (att.length ? '<div class="files">' + att.map((f, i) => '<a class="file" href="' + esc(urls[i]) + '" target="_blank" rel="noopener" download="' + esc(f.name) + '">' + icon("file") + '<span class="fn">' + esc(f.name) + '</span><span class="fs">' + fmtSize(f.size) + "</span></a>").join("") + "</div>" : "") + "</div>";
      }));
      thread.innerHTML = parts.join("");
    }

    // ── Ergebnis-Dateien ──
    function renderPending() {
      document.getElementById("pendingList").innerHTML = pending.length
        ? pending.map((f, i) => '<div class="file">' + icon("file") + '<span class="fn">' + esc(f.name) + '</span><span class="fs">' + fmtSize(f.size) + '</span><button type="button" data-rm="' + i + '" aria-label="Entfernen">' + icon("x") + "</button></div>").join("")
        : '<p class="faint" style="font-size:13.5px">Noch keine Datei angehängt.</p>';
    }
    renderPending();
    document.getElementById("pendingList").addEventListener("click", (e) => { const b = e.target.closest("[data-rm]"); if (b) { pending.splice(+b.dataset.rm, 1); renderPending(); } });
    document.getElementById("resultInput").addEventListener("change", (e) => {
      for (const f of e.target.files) { if (f.size > 25 * 1024 * 1024) toast("„" + f.name + "“ ist zu groß (max. 25 MB).", true); else pending.push(f); }
      e.target.value = ""; renderPending();
    });

    // ── Bühne ──
    const stage = document.getElementById("stage");
    let editor = null;
    const docLinks = async () => docs.length ? '<div class="files" style="width:min(660px,100%)">' + (await Promise.all(docs.map(async (f) => '<a class="file" target="_blank" rel="noopener" href="' + esc(await API.fileUrl(f, true).catch(() => "")) + '">' + icon("file") + '<span class="fn">' + esc(f.name) + '</span><span class="fs">' + fmtSize(f.size) + "</span></a>"))).join("") + "</div>" : "";

    if (o.kind === "text") {
      stage.style.justifyContent = "flex-start";
      stage.innerHTML = '<div style="width:min(760px,100%);display:grid;gap:10px"><div class="stage-info">Eingesendeter Text · <b>' + (o.text_content || "").length.toLocaleString("de-DE") + " Zeichen</b></div><div class=\"text-doc\">" + esc(o.text_content) + "</div></div>" + (await docLinks());
    } else if (isImg) {
      stage.innerHTML = '<div class="canvas-wrap" id="cwrap"><canvas id="cv" aria-label="Hochgeladenes Bild"></canvas></div>' +
        '<div class="stage-info" id="sinfo"></div>' +
        (imgs.length > 1 ? '<div class="strip" id="strip">' + imgs.map((f, i) => '<button aria-pressed="' + (i === 0) + '" data-i="' + i + '" aria-label="Bild ' + (i + 1) + '"><span data-strip="' + i + '"></span></button>').join("") + "</div>" : "") + (await docLinks());
      editor = makeEditor(document.getElementById("cv"), document.getElementById("cwrap"), document.getElementById("sinfo"));
      const urls = await Promise.all(imgs.map((f) => API.fileUrl(f).catch(() => "")));
      editor.load(urls[0], imgs[0].name);
      if (imgs.length > 1) {
        urls.forEach((u, i) => { const s = stage.querySelector('[data-strip="' + i + '"]'); if (s && u) s.outerHTML = '<img alt="" src="' + esc(u) + '">'; });
        document.getElementById("strip").addEventListener("click", (e) => {
          const b = e.target.closest("button[data-i]"); if (!b) return;
          document.querySelectorAll("#strip button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
          editor.load(urls[+b.dataset.i], imgs[+b.dataset.i].name);
        });
      }
      document.querySelectorAll("[data-adj]").forEach((r) => {
        setRangeFill(r);
        r.addEventListener("input", () => { setRangeFill(r); document.getElementById("v-" + r.dataset.adj).textContent = r.value; editor.adjust(r.dataset.adj, +r.value); });
      });
      document.querySelectorAll("#penBox [data-color]").forEach((b) => b.addEventListener("click", () => {
        document.querySelectorAll("#penBox [data-color]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        editor.color = b.dataset.color;
      }));
    } else {
      stage.innerHTML = '<div class="stage-ph">' + icon("image") + "<span>Keine Bilder in dieser Einsendung</span></div>" + (await docLinks());
    }

    // ── Werkzeuge ──
    document.getElementById("rail").addEventListener("click", async (e) => {
      const b = e.target.closest(".tool"); if (!b) return;
      const t = b.dataset.tool;
      if (t === "copy") { try { await navigator.clipboard.writeText(o.text_content || ""); toast("Text kopiert."); } catch (x) { toast("Kopieren nicht möglich.", true); } }
      if (t === "txt") downloadBlob(new Blob([o.text_content || ""], { type: "text/plain;charset=utf-8" }), "text-" + o.id + ".txt");
      if (!editor) return;
      if (t === "rotate") editor.rotate();
      if (t === "reset") { editor.reset(); document.querySelectorAll("[data-adj]").forEach((r) => { r.value = 0; setRangeFill(r); document.getElementById("v-" + r.dataset.adj).textContent = "0"; }); }
      if (t === "adjust") { document.getElementById("adjustBox").scrollIntoView({ behavior: "smooth", block: "center" }); }
      if (t === "draw") {
        const on = !editor.drawing; editor.setDrawing(on);
        b.setAttribute("aria-pressed", String(on));
        document.querySelector('[data-tool="adjust"]').setAttribute("aria-pressed", String(!on));
        document.getElementById("penBox").classList.toggle("hidden", !on);
      }
      if (t === "download" || t === "attach") {
        try {
          const file = await editor.exportFile();
          if (t === "download") downloadBlob(file, file.name);
          else { pending.push(file); renderPending(); toast("Bearbeitetes Bild angehängt."); }
        } catch (x) { toast(x.message, true); }
      }
    });

    // ── Status ──
    const chips = document.getElementById("statusChips");
    chips.addEventListener("click", async (e) => {
      if (e.target.closest("#markPaid")) {
        if (!confirm("Diesen Auftrag als bezahlt markieren? (z. B. bei Barzahlung oder PayPal)")) return;
        try { await API.markPaid(o.id); toast("Als bezahlt markiert."); openEditor(o.id); } catch (x) { toast(x.message, true); }
        return;
      }
      const b = e.target.closest("button[data-s]"); if (!b) return;
      try {
        await API.updateOrder(o.id, { status: b.dataset.s });
        o.status = b.dataset.s;
        chips.querySelectorAll("button[data-s]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        toast("Status: " + window.UI.STATUS[b.dataset.s]);
      } catch (x) { toast(x.message, true); }
    });

    // ── Speichern / Senden ──
    const msgEl = document.getElementById("msg");
    document.getElementById("saveDraft").onclick = async (e) => {
      const btn = e.currentTarget; btn.disabled = true;
      try {
        const patch = { draft_message: msgEl.value };
        if (o.status === "neu") patch.status = "in_arbeit";
        await API.updateOrder(o.id, patch);
        if (patch.status) { o.status = patch.status; chips.querySelectorAll("button[data-s]").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.s === o.status))); }
        toast("Entwurf gespeichert" + (pending.length ? " – Dateien werden erst beim Zurückschicken hochgeladen." : "."));
      } catch (x) { toast(x.message, true); }
      btn.disabled = false;
    };

    document.getElementById("askOnly").onclick = async (e) => {
      const t = msgEl.value.trim();
      if (!t) return toast("Schreib zuerst eine Nachricht.", true);
      const btn = e.currentTarget; btn.disabled = true;
      try {
        await API.sendMessage(o, t, []);
        await API.updateOrder(o.id, { draft_message: null });
        toast("Nachricht an " + (o.student.name || "Schüler") + " gesendet.");
        openEditor(o.id);
      } catch (x) { toast(x.message, true); btn.disabled = false; }
    };

    document.getElementById("sendDone").onclick = async (e) => {
      if (o.status === "unbezahlt" && !confirm("Dieser Auftrag ist noch nicht bezahlt. Trotzdem verschicken?")) return;
      if (!pending.length && !confirm("Es ist keine Ergebnis-Datei angehängt. Nur die Nachricht verschicken?")) return;
      const btn = e.currentTarget, label = btn.textContent; btn.disabled = true;
      try {
        btn.textContent = pending.length ? "Lade " + pending.length + " Datei" + (pending.length > 1 ? "en" : "") + " hoch …" : "Wird gesendet …";
        await API.sendMessage(o, msgEl.value.trim() || "Hier ist dein fertiges Ergebnis! Viel Erfolg beim Lernen.", pending);
        await API.updateOrder(o.id, { status: "fertig", draft_message: null });
        toast("An " + (o.student.name || "den Schüler") + " verschickt – liegt jetzt im Postfach.");
        location.hash = lastList;
      } catch (x) { toast(x.message, true); btn.disabled = false; btn.textContent = label; }
    };
  }

  /* ═══════════ Empfehlungen & Auszahlungen ═══════════ */
  async function showReferrals() {
    const { credits, payouts } = await API.adminReferrals();
    const open = payouts.filter((p) => p.status === "offen");
    const bonuses = credits.filter((c) => c.kind === "empfehlung");
    const reversed = new Set(credits.filter((c) => c.reverses_id).map((c) => c.reverses_id));
    const totalBal = credits.reduce((s, c) => s + c.amount_cents, 0);
    const METHOD = { paypal: "PayPal", ueberweisung: "Überweisung" };
    const who = (u) => u ? "<b>" + esc(u.name || "—") + '</b><div class="faint" style="font-size:12.5px">' + esc(u.email || "") + "</div>" : '<span class="faint">gelöscht</span>';

    view.innerHTML =
      '<div class="main-head"><h1>Empfehlungen</h1></div>' +
      '<div class="stat-row" style="margin-bottom:24px">' +
        '<div class="stat hl"><span class="k">Offene Auszahlungen</span><span class="v">' + eur(open.reduce((s, p) => s + p.amount_cents, 0)) + "</span></div>" +
        '<div class="stat"><span class="k">Geworbene Käufer</span><span class="v">' + bonuses.length + "</span></div>" +
        '<div class="stat"><span class="k">Boni gesamt</span><span class="v">' + eur(bonuses.filter((c) => !reversed.has(c.id)).reduce((s, c) => s + c.amount_cents, 0)) + "</span></div>" +
        '<div class="stat"><span class="k">Guthaben aller Schüler</span><span class="v">' + eur(totalBal) + "</span></div></div>" +

      '<h2 style="font-size:19px;margin-bottom:6px">Auszahlungsanfragen</h2>' +
      '<p class="muted" style="font-size:14px;margin-bottom:12px">Schick das Geld per PayPal oder Überweisung und tippe dann auf „Ausgezahlt“. „Ablehnen“ bucht das Guthaben zurück.</p>' +
      (payouts.length ? '<div class="table-wrap" style="margin-bottom:32px"><table class="table"><thead><tr><th>Datum</th><th>Schüler</th><th class="num">Betrag</th><th>An</th><th></th></tr></thead><tbody>' +
        payouts.map((p) => "<tr><td>" + fmtDate(p.created_at) + "</td><td>" + who(p.user) + '</td><td class="num"><b>' + eur(p.amount_cents) + "</b></td>" +
          "<td>" + METHOD[p.method] + '<div class="copyable">' + esc(p.details) + "</div></td>" +
          '<td><div class="acts">' + (p.status === "offen"
            ? '<button class="btn btn-sm" data-copy="' + esc(p.details) + '">' + icon("copy") + '</button><button class="btn btn-sm btn-primary" data-pay="' + p.id + '">' + icon("check") + 'Ausgezahlt</button><button class="btn btn-sm btn-ghost" data-reject="' + p.id + '">Ablehnen</button>'
            : '<span class="badge badge-' + p.status + '">' + (p.status === "ausgezahlt" ? "Ausgezahlt " + fmtDate(p.done_at) : "Abgelehnt") + "</span>") + "</div></td></tr>").join("") +
        "</tbody></table></div>"
        : '<div class="empty" style="margin-bottom:32px">' + icon("wallet") + "<p>Keine Auszahlungsanfragen.</p></div>") +

      '<h2 style="font-size:19px;margin-bottom:12px">Empfehlungs-Boni</h2>' +
      (bonuses.length ? '<div class="table-wrap"><table class="table"><thead><tr><th>Datum</th><th>Werber</th><th>Geworbener Freund</th><th>Auftrag</th><th class="num">Bonus</th><th></th></tr></thead><tbody>' +
        bonuses.map((c) => "<tr><td>" + fmtDate(c.created_at) + "</td><td>" + who(c.user) + "</td><td>" + who(c.source) + "</td><td>" +
          (c.order_id ? '<a href="#auftrag/' + c.order_id + '">#' + String(c.order_id).padStart(4, "0") + "</a>" : "—") + '</td><td class="num">' + eur(c.amount_cents) + '</td><td><div class="acts">' +
          (reversed.has(c.id) ? '<span class="badge badge-abgelehnt">Storniert</span>' : '<button class="btn btn-sm btn-ghost" data-reverse="' + c.id + '">Stornieren</button>') + "</div></td></tr>").join("") +
        "</tbody></table></div>"
        : '<div class="empty">' + icon("gift") + "<p>Noch keine Empfehlungen. Sobald ein geworbener Freund seinen ersten Auftrag bezahlt, erscheint der Bonus hier.</p></div>");

    view.onclick = async (e) => {
      const b = e.target.closest("button"); if (!b || !view.contains(b)) return;
      try {
        if (b.dataset.copy != null) { await navigator.clipboard.writeText(b.dataset.copy).then(() => toast("Kopiert."), () => toast("Kopieren nicht möglich.", true)); return; }
        if (b.dataset.pay) { if (!confirm("Hast du das Geld überwiesen? Als ausgezahlt markieren?")) return; await API.finishPayout(+b.dataset.pay, true); toast("Als ausgezahlt markiert."); }
        else if (b.dataset.reject) { if (!confirm("Auszahlung ablehnen? Das Guthaben wird zurückgebucht.")) return; await API.finishPayout(+b.dataset.reject, false); toast("Abgelehnt – Guthaben zurückgebucht."); }
        else if (b.dataset.reverse) { if (!confirm("Diesen Bonus stornieren (z. B. weil der Auftrag erstattet wurde)?")) return; await API.reverseCredit(+b.dataset.reverse); toast("Bonus storniert."); }
        else return;
        refreshPayoutCount(); showReferrals();
      } catch (x) { toast(x.message, true); }
    };
  }

  function downloadBlob(blob, name) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
  }

  /* ═══════════ Bild-Editor (Canvas) ═══════════ */
  function makeEditor(canvas, wrap, info) {
    const ctx = canvas.getContext("2d");
    const MAX = 2400;
    const ed = { img: null, name: "bild", adj: { b: 0, c: 0, s: 0 }, drawing: false, color: "#ff5c5c" };
    let last = null;

    function showInfo() {
      const r = canvas.getBoundingClientRect();
      const z = canvas.width ? Math.round((r.width / canvas.width) * 100) : 100;
      info.innerHTML = "Werkzeug: <b>" + (ed.drawing ? "Zeichnen" : "Anpassen") + "</b> · " + z + " %";
    }
    function paint() {
      const img = ed.img; if (!img) return;
      const k = Math.min(1, MAX / Math.max(img.naturalWidth, img.naturalHeight));
      canvas.width = Math.round(img.naturalWidth * k) || 800;
      canvas.height = Math.round(img.naturalHeight * k) || 600;
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      requestAnimationFrame(showInfo);
    }
    function applyFilter() {
      const { b, c, s } = ed.adj;
      canvas.style.filter = "brightness(" + (1 + b / 100) + ") contrast(" + (1 + c / 100) + ") saturate(" + (1 + s / 100) + ")";
    }
    ed.load = (url, name) => new Promise((res) => {
      ed.name = (name || "bild").replace(/\.[^.]+$/, "");
      const img = new Image();
      if (/^https?:/.test(url)) img.crossOrigin = "anonymous";
      img.onload = () => { ed.img = img; paint(); res(); };
      img.onerror = () => { info.textContent = "Bild konnte nicht geladen werden."; res(); };
      img.src = url;
    });
    ed.reset = () => { ed.adj = { b: 0, c: 0, s: 0 }; applyFilter(); paint(); };
    ed.adjust = (k, v) => { ed.adj[k] = v; applyFilter(); };
    ed.rotate = () => {
      const tmp = document.createElement("canvas");
      tmp.width = canvas.height; tmp.height = canvas.width;
      const t = tmp.getContext("2d");
      t.translate(tmp.width, 0); t.rotate(Math.PI / 2); t.drawImage(canvas, 0, 0);
      canvas.width = tmp.width; canvas.height = tmp.height;
      ctx.drawImage(tmp, 0, 0);
      requestAnimationFrame(showInfo);
    };
    ed.setDrawing = (on) => { ed.drawing = on; wrap.classList.toggle("drawing", on); showInfo(); };

    const pos = (e) => { const r = canvas.getBoundingClientRect(); return [(e.clientX - r.left) * canvas.width / r.width, (e.clientY - r.top) * canvas.height / r.height]; };
    canvas.addEventListener("pointerdown", (e) => {
      if (!ed.drawing) return;
      e.preventDefault(); canvas.setPointerCapture(e.pointerId);
      last = pos(e);
      ctx.fillStyle = ed.color; ctx.beginPath(); ctx.arc(last[0], last[1], Math.max(2, canvas.width / 400), 0, Math.PI * 2); ctx.fill();
    });
    canvas.addEventListener("pointermove", (e) => {
      if (!ed.drawing || !last) return;
      const p = pos(e);
      ctx.strokeStyle = ed.color; ctx.lineWidth = Math.max(4, canvas.width / 200); ctx.lineCap = "round"; ctx.lineJoin = "round";
      ctx.beginPath(); ctx.moveTo(last[0], last[1]); ctx.lineTo(p[0], p[1]); ctx.stroke();
      last = p;
    });
    ["pointerup", "pointercancel", "pointerleave"].forEach((ev) => canvas.addEventListener(ev, () => (last = null)));
    window.addEventListener("resize", showInfo);

    // Export mit echten Pixel-Anpassungen (gleiche Formeln wie die CSS-Vorschau)
    ed.exportFile = () => new Promise((res, rej) => {
      const out = document.createElement("canvas");
      out.width = canvas.width; out.height = canvas.height;
      const o = out.getContext("2d");
      o.fillStyle = "#fff"; o.fillRect(0, 0, out.width, out.height);
      o.drawImage(canvas, 0, 0);
      const { b, c, s } = ed.adj;
      if (b || c || s) {
        let data;
        try { data = o.getImageData(0, 0, out.width, out.height); } catch (e) { return rej(new Error("Dieses Bild kann im Browser nicht exportiert werden.")); }
        const d = data.data, kb = 1 + b / 100, kc = 1 + c / 100, ks = 1 + s / 100;
        for (let i = 0; i < d.length; i += 4) {
          let r = (d[i] * kb - 128) * kc + 128, g = (d[i + 1] * kb - 128) * kc + 128, bl = (d[i + 2] * kb - 128) * kc + 128;
          const l = 0.2126 * r + 0.7152 * g + 0.0722 * bl;
          d[i] = l + (r - l) * ks; d[i + 1] = l + (g - l) * ks; d[i + 2] = l + (bl - l) * ks;
        }
        o.putImageData(data, 0, 0);
      }
      try {
        out.toBlob((blob) => blob ? res(new File([blob], ed.name + "-bearbeitet.jpg", { type: "image/jpeg" })) : rej(new Error("Export fehlgeschlagen.")), "image/jpeg", 0.92);
      } catch (e) { rej(new Error("Dieses Bild kann im Browser nicht exportiert werden.")); }
    });
    return ed;
  }

  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && !location.hash.startsWith("#auftrag/")) route(); });
  route();
})();
