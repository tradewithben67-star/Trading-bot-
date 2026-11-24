/* Schülerbereich: Aufträge, Postfach, Konto */
(async function () {
  const { icon, esc, fmtDate, fmtDateTime, fmtSize, isImage, badge, orderNo, productById, toast } = window.UI;
  const view = document.getElementById("view");
  let user = null, orders = [], paidPolls = 0;
  let paidFlash = new URLSearchParams(location.search).get("bezahlt") === "1";
  if (paidFlash) history.replaceState(null, "", location.pathname + location.hash);

  user = await API.session().catch(() => null);
  if (!user) { location.replace("login.html?next=konto.html"); return; }
  if (user.isAdmin) { location.replace("admin.html"); return; }
  document.getElementById("uName").textContent = user.name || "Schüler";
  document.getElementById("uEmail").textContent = user.email;
  document.querySelector(".side-foot").insertAdjacentHTML("beforeend", '<button class="btn btn-ghost btn-sm" id="logout">' + icon("logout") + "Abmelden</button>");
  document.getElementById("logout").onclick = async () => { await API.signOut(); location.href = "index.html"; };

  const unreadOf = (o) => o.messages.filter((m) => m.from_admin && !m.read_at).length;
  const studentFiles = (o) => o.files.filter((f) => !f.from_admin);

  async function load() {
    orders = await API.myOrders();
    const n = orders.reduce((s, o) => s + unreadOf(o), 0);
    const el = document.getElementById("unread");
    el.textContent = n; el.classList.toggle("hidden", !n);
  }

  // Dateien als Links (signierte URLs vorher holen, damit iPad/iPhone keine Pop-ups blockieren)
  async function fileLinks(files) {
    const urls = await Promise.all(files.map((f) => API.fileUrl(f, true).catch(() => "")));
    return files.map((f, i) => '<a class="file" href="' + esc(urls[i]) + '" download="' + esc(f.name) + '" target="_blank" rel="noopener">' + icon("download") + '<span class="fn">' + esc(f.name) + '</span><span class="fs">' + fmtSize(f.size) + "</span></a>").join("");
  }

  function setNav(name) {
    document.querySelectorAll(".side-nav a").forEach((a) => a.setAttribute("aria-current", a.dataset.view === name ? "page" : "false"));
  }

  async function route() {
    const h = location.hash.replace(/^#/, "") || "auftraege";
    window.scrollTo(0, 0);
    try {
      if (h.startsWith("auftrag/")) { setNav("auftraege"); return await showOrder(Number(h.split("/")[1])); }
      if (h === "postfach") { setNav("postfach"); return await showInbox(); }
      if (h === "konto") { setNav("konto"); return showAccount(); }
      setNav("auftraege"); await showOrders();
    } catch (e) {
      view.innerHTML = '<div class="empty">' + icon("info") + "<h3>Das hat nicht geklappt</h3><p>" + esc(e.message) + '</p><a class="btn" href="#auftraege">Zurück</a></div>';
    }
  }
  window.addEventListener("hashchange", route);

  /* ── Meine Aufträge ── */
  async function showOrders() {
    await load();
    let html = '<div class="main-head"><h1>Meine Aufträge</h1><a class="btn btn-primary" href="index.html#bestellen">' + icon("plus") + "Neuer Auftrag</a></div>";
    if (paidFlash) html += '<div class="notice" style="margin-bottom:20px">' + icon("check") + "<span><b>Danke für deine Bestellung!</b> Sobald die Zahlung bestätigt ist, fange ich an. Das Ergebnis kommt in dein Postfach.</span></div>";
    if (!orders.length) {
      html += '<div class="empty">' + icon("folder") + "<h3>Noch keine Aufträge</h3><p>Lade ein Bild oder einen Text hoch und wähle aus, was du bekommen möchtest.</p>" + '<a class="btn btn-primary" href="index.html#bestellen">Ersten Auftrag starten</a></div>';
      view.innerHTML = html; return;
    }
    html += '<div class="grid">' + orders.map((o) => {
      const p = productById(o.product);
      const unread = unreadOf(o);
      const preview = o.kind === "text"
        ? '<div class="txt">' + esc((o.text_content || "").slice(0, 260)) + "</div>"
        : '<span data-thumb="' + o.id + '">' + icon("image") + "</span>";
      return '<a class="sub-card" href="#auftrag/' + o.id + '"><div class="preview">' + preview +
        (unread ? '<span class="flag"><span class="dot"></span>' + unread + " neue Nachricht" + (unread > 1 ? "en" : "") + "</span>" : "") +
        '</div><div class="body"><div class="top"><b>' + esc(p.long) + "</b>" + badge(o.status, true) + '</div><div class="meta">' + orderNo(o) + " · " + (o.kind === "bild" ? "Bild" : "Text") + (o.subject ? " · " + esc(o.subject) : "") + " · " + fmtDate(o.created_at) + "</div></div>" +
        (o.status === "unbezahlt" ? '<div class="actions"><span class="btn btn-primary btn-sm" style="width:100%">Jetzt bezahlen</span></div>' : "") + "</a>";
    }).join("") + "</div>";
    view.innerHTML = html;
    // Vorschaubilder nachladen
    for (const o of orders) {
      const img = studentFiles(o).find(isImage);
      const slot = view.querySelector('[data-thumb="' + o.id + '"]');
      if (img && slot) API.fileUrl(img).then((u) => { if (u) slot.outerHTML = '<img alt="" src="' + esc(u) + '">'; }).catch(() => {});
    }
  }

  /* ── Auftrag im Detail ── */
  async function showOrder(id) {
    const o = await API.getOrder(id);
    const p = productById(o.product);
    if (unreadOf(o)) { API.markRead(o.id).then(load); }
    const st = o.status;
    const steps = [["Bestellt", true], ["Bezahlt", st !== "unbezahlt"], ["In Arbeit", ["in_arbeit", "fertig", "archiv"].includes(st)], ["Fertig", ["fertig", "archiv"].includes(st)]];
    const mine = studentFiles(o);
    const imgs = mine.filter(isImage), others = mine.filter((f) => !isImage(f));
    const imgUrls = await Promise.all(imgs.map((f) => API.fileUrl(f).catch(() => "")));

    let payBox = "";
    if (st === "unbezahlt") {
      const url = API.paymentUrl(o, user.email);
      payBox = url
        ? '<div class="notice warn">' + icon("card") + '<span style="flex:1">Dieser Auftrag ist noch nicht bezahlt. Ich fange an, sobald die Zahlung da ist.</span></div><a class="btn btn-primary btn-lg" href="' + esc(url) + '">' + icon("card") + "Jetzt bezahlen</a>"
        : '<div class="notice warn">' + icon("info") + "<span>Die Online-Bezahlung wird gerade eingerichtet. Du bekommst Bescheid, sobald du bezahlen kannst.</span></div>";
    }
    if (paidFlash) {
      payBox = '<div class="notice">' + icon("check") + "<span><b>Danke!</b> Deine Zahlung ist eingegangen" + (st === "unbezahlt" ? " und wird gerade bestätigt – das dauert meist nur ein paar Sekunden." : ".") + " Das Ergebnis kommt in dein Postfach.</span></div>";
      paidFlash = false;
      if (st === "unbezahlt" && paidPolls++ < 12) setTimeout(() => { if (location.hash === "#auftrag/" + o.id) { paidFlash = true; showOrder(o.id); } }, 5000);
    }

    const thread = o.messages.map((m) => {
      const att = o.files.filter((f) => f.message_id === m.id);
      return { m, att };
    });
    const threadHtml = await Promise.all(thread.map(async ({ m, att }) =>
      '<div class="msg' + (m.from_admin ? "" : " mine") + '"><div class="who"><b>' + (m.from_admin ? esc(window.APP_CONFIG.SITE_NAME) : "Du") + "</b><span>" + fmtDateTime(m.created_at) + "</span></div>" +
      (m.body ? '<div class="txt">' + esc(m.body) + "</div>" : "") + (att.length ? '<div class="files">' + (await fileLinks(att)) + "</div>" : "") + "</div>"));

    view.innerHTML =
      '<div class="detail-head"><a class="icon-btn" href="#auftraege" aria-label="Zurück">' + icon("chevronLeft") + '</a><div style="flex:1;min-width:0"><h1>' + esc(p.long) + '</h1><div class="muted" style="font-size:14px">Auftrag ' + orderNo(o) + " · " + fmtDateTime(o.created_at) + "</div></div>" + badge(st, true) + "</div>" +
      '<div class="stepper" style="margin-bottom:22px">' + steps.map(([t, d]) => '<div class="' + (d ? "done" : "") + '">' + t + "</div>").join("") + "</div>" +
      '<div class="detail-grid"><div style="display:grid;gap:20px">' +
        (payBox ? '<div style="display:grid;gap:12px">' + payBox + "</div>" : "") +
        '<section class="panel"><h2>Deine Einsendung</h2>' +
          (o.kind === "text" ? '<div class="text-doc">' + esc(o.text_content) + "</div>" : "") +
          (imgs.length ? '<div class="img-list">' + imgs.map((f, i) => '<a href="' + esc(imgUrls[i]) + '" target="_blank" rel="noopener"><img alt="' + esc(f.name) + '" src="' + esc(imgUrls[i]) + '"></a>').join("") + "</div>" : "") +
          (others.length ? '<div class="files">' + (await fileLinks(others)) + "</div>" : "") +
          '<dl class="kv"><dt>Paket</dt><dd>' + esc(p.long) + "</dd>" + (o.subject ? "<dt>Fach</dt><dd>" + esc(o.subject) + "</dd>" : "") + (o.grade ? "<dt>Klasse</dt><dd>" + esc(o.grade) + "</dd>" : "") + (o.due_date ? "<dt>Gewünscht bis</dt><dd>" + fmtDate(o.due_date) + "</dd>" : "") + "<dt>Preis</dt><dd>" + (o.price_cents / 100).toFixed(2).replace(".", ",") + " €</dd></dl>" +
          (o.wish ? '<div><div class="section-label">Dein Wunsch</div><div class="quote">' + esc(o.wish) + "</div></div>" : "") +
        "</section></div>" +
        '<section class="panel"><h2>Nachrichten &amp; Ergebnis</h2>' +
          (threadHtml.length ? '<div class="thread">' + threadHtml.join("") + "</div>" : '<p class="muted" style="font-size:14px">Noch keine Nachrichten. Sobald dein Ergebnis fertig ist, erscheint es hier und in deinem Postfach.</p>') +
          (st !== "unbezahlt" ? '<form class="reply" id="reply"><textarea class="textarea" id="replyText" rows="3" placeholder="Rückfrage oder Nachricht schreiben …"></textarea><div class="row"><button class="btn btn-primary btn-sm" type="submit">' + icon("send") + "Senden</button></div></form>" : "") +
        "</section></div>";

    const form = document.getElementById("reply");
    if (form) form.onsubmit = async (e) => {
      e.preventDefault();
      const t = document.getElementById("replyText").value.trim();
      if (!t) return;
      form.querySelector("button").disabled = true;
      try { await API.sendMessage(o, t); toast("Nachricht gesendet."); showOrder(o.id); }
      catch (x) { toast(x.message, true); form.querySelector("button").disabled = false; }
    };
  }

  /* ── Postfach ── */
  async function showInbox() {
    await load();
    const items = [];
    orders.forEach((o) => o.messages.filter((m) => m.from_admin).forEach((m) => items.push({ o, m, att: o.files.filter((f) => f.message_id === m.id) })));
    items.sort((a, b) => new Date(b.m.created_at) - new Date(a.m.created_at));
    let html = '<div class="main-head"><h1>Postfach</h1></div>';
    if (!items.length) {
      view.innerHTML = html + '<div class="empty">' + icon("inbox") + "<h3>Dein Postfach ist leer</h3><p>Hier landen deine fertigen Ergebnisse und Nachrichten von mir.</p></div>";
      return;
    }
    const allAtt = items.flatMap((x) => x.att);
    const urls = await Promise.all(allAtt.map((f) => API.fileUrl(f, true).catch(() => "")));
    const urlOf = (f) => urls[allAtt.indexOf(f)];
    html += '<div class="mail-list">' + items.map(({ o, m, att }) =>
      '<div class="mail' + (m.read_at ? "" : " unread") + '" data-order="' + o.id + '" role="link" tabindex="0"><div class="ico">' + icon(att.length ? "attach" : "mail") + "</div><div style='min-width:0'>" +
      '<div class="top"><b>' + (m.read_at ? "" : '<span class="dot"></span>') + esc(productById(o.product).long) + ' <span class="faint" style="font-weight:400">' + orderNo(o) + '</span></b><span class="date">' + fmtDateTime(m.created_at) + "</span></div>" +
      '<div class="txt">' + esc(m.body || (att.length ? "Dein Ergebnis ist da." : "")) + "</div>" +
      (att.length ? '<div class="att">' + att.map((f) => '<a class="att-chip" href="' + esc(urlOf(f)) + '" download="' + esc(f.name) + '" target="_blank" rel="noopener">' + icon("download") + esc(f.name) + "</a>").join("") + "</div>" : "") +
      "</div></div>").join("") + "</div>";
    view.innerHTML = html;
    view.querySelectorAll(".mail").forEach((el) => {
      const open = (e) => { if (e.target.closest("a")) return; location.hash = "auftrag/" + el.dataset.order; };
      el.addEventListener("click", open);
      el.addEventListener("keydown", (e) => { if (e.key === "Enter") open(e); });
    });
  }

  /* ── Konto ── */
  function showAccount() {
    view.innerHTML = '<div class="main-head"><h1>Konto</h1></div><div style="display:grid;gap:20px;max-width:520px">' +
      '<form class="panel" id="nameForm"><h2>Profil</h2><div class="field"><label for="nm">Name</label><input class="input" id="nm" value="' + esc(user.name) + '"></div><div class="field"><label>E-Mail</label><input class="input" value="' + esc(user.email) + '" disabled></div><div><button class="btn btn-primary btn-sm" type="submit">Speichern</button></div></form>' +
      '<form class="panel" id="pwForm"><h2>Passwort ändern</h2><div class="field"><label for="pw">Neues Passwort</label><input class="input" type="password" id="pw" autocomplete="new-password" placeholder="Mindestens 8 Zeichen"></div><div><button class="btn btn-sm" type="submit">Passwort ändern</button></div></form>' +
      '<div class="panel"><h2>Hilfe</h2><p class="muted" style="font-size:14px">Fragen zu einem Auftrag? Schreib mir direkt im Auftrag. Sonst erreichst du mich unter <a data-contact></a>.</p></div></div>';
    UI.applySiteName();
    document.getElementById("nameForm").onsubmit = async (e) => {
      e.preventDefault();
      const n = document.getElementById("nm").value.trim(); if (!n) return;
      try { await API.updateName(n); user.name = n; document.getElementById("uName").textContent = n; toast("Gespeichert."); } catch (x) { toast(x.message, true); }
    };
    document.getElementById("pwForm").onsubmit = async (e) => {
      e.preventDefault();
      const pw = document.getElementById("pw").value;
      if (pw.length < 8) return toast("Das Passwort muss mindestens 8 Zeichen haben.", true);
      try { await API.setPassword(pw); document.getElementById("pw").value = ""; toast("Passwort geändert."); } catch (x) { toast(x.message, true); }
    };
  }

  // Beim Zurückkehren in die App neu laden (z. B. nach dem Bezahlen)
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible" && !document.activeElement.matches("textarea,input")) route(); });
  route();
})();
