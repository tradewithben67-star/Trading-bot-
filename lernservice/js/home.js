/* Startseite: Bestellformular */
(function () {
  const { icon, PRODUCTS, SUBJECTS, GRADES, esc, toast, fmtSize } = window.UI;
  const $ = (s) => document.querySelector(s);
  const state = { kind: "bild", product: null, files: [], user: null };

  // Leistungen + Produktauswahl
  $("#features").innerHTML = PRODUCTS.map((p) => '<div class="feature"><div class="fi">' + icon(p.icon) + "</div><h3>" + esc(p.long) + "</h3><p>" + esc(p.desc) + "</p></div>").join("");
  $("#products").innerHTML = PRODUCTS.map((p) => '<button type="button" class="product" role="radio" aria-checked="false" data-id="' + p.id + '">' + icon(p.icon) + "<span>" + esc(p.name) + "</span></button>").join("");
  $("#products").addEventListener("click", (e) => {
    const b = e.target.closest(".product"); if (!b) return;
    state.product = b.dataset.id;
    document.querySelectorAll(".product").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
  });
  // Klick auf Leistung unten → im Formular auswählen
  document.querySelectorAll("#features .feature").forEach((el, i) => {
    el.style.cursor = "pointer";
    el.addEventListener("click", () => { document.querySelectorAll(".product")[i].click(); $("#bestellen").scrollIntoView({ behavior: "smooth" }); });
  });
  $("#subject").insertAdjacentHTML("beforeend", SUBJECTS.map((s) => "<option>" + esc(s) + "</option>").join(""));
  $("#grade").insertAdjacentHTML("beforeend", GRADES.map((g) => '<option value="' + esc(g) + '">' + (/^\d+$/.test(g) ? "Klasse " + g : esc(g)) + "</option>").join(""));
  $("#due").min = new Date().toISOString().slice(0, 10);

  // Produkt per URL vorwählen (?paket=lernzettel)
  const pre = new URLSearchParams(location.search).get("paket");
  if (pre) { const b = document.querySelector('.product[data-id="' + CSS.escape(pre) + '"]'); if (b) b.click(); }

  // Bild / Text umschalten
  document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
    state.kind = b.dataset.kind;
    document.querySelectorAll(".seg button").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
    $("#pane-bild").classList.toggle("hidden", state.kind !== "bild");
    $("#pane-text").classList.toggle("hidden", state.kind !== "text");
  }));
  $("#textContent").addEventListener("input", (e) => ($("#textCount").textContent = e.target.value.length.toLocaleString("de-DE") + " Zeichen"));

  // Dateien
  function addFiles(list) {
    for (const f of list) {
      if (!/^image\//.test(f.type) && f.type !== "application/pdf") { toast("„" + f.name + "“ ist kein Bild oder PDF.", true); continue; }
      if (f.size > 25 * 1024 * 1024) { toast("„" + f.name + "“ ist zu groß (max. 25 MB).", true); continue; }
      if (state.files.length >= 10) { toast("Maximal 10 Dateien pro Auftrag.", true); break; }
      state.files.push(f);
    }
    renderThumbs();
  }
  function renderThumbs() {
    $("#thumbs").innerHTML = state.files.map((f, i) => {
      const inner = /^image\//.test(f.type) ? '<img alt="" src="' + URL.createObjectURL(f) + '">' : '<div class="file-ph">' + icon("file") + "<br>" + esc(f.name) + "</div>";
      return '<div class="thumb" title="' + esc(f.name) + " · " + fmtSize(f.size) + '">' + inner + '<button type="button" aria-label="Entfernen" data-i="' + i + '">' + icon("x") + "</button></div>";
    }).join("");
  }
  $("#thumbs").addEventListener("click", (e) => { const b = e.target.closest("button[data-i]"); if (b) { state.files.splice(+b.dataset.i, 1); renderThumbs(); } });
  $("#fileInput").addEventListener("change", (e) => { addFiles(e.target.files); e.target.value = ""; });
  const dz = $("#dropzone");
  ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
  ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
  dz.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));

  // Eingeladen von einem Freund?
  const ref = window.UI.getRef();
  if (ref) {
    $("#refNote").innerHTML = icon("gift") + "<span>Du wurdest von einem Freund eingeladen (Code <b>" + esc(ref) + "</b>). Mit deinem ersten Auftrag hilfst du ihm – danach kannst du selbst Freunde werben.</span>";
    $("#refNote").classList.remove("hidden");
  }

  // Login-Status
  async function refreshAuth() {
    state.user = await window.UI.renderAuthNav();
    const u = state.user;
    $("#accountFields").classList.toggle("hidden", !!u);
    $("#loggedAs").classList.toggle("hidden", !u);
    if (u) {
      $("#loggedAs").innerHTML = "<span>Angemeldet als <b>" + esc(u.name || u.email) + "</b></span>" + '<button type="button" class="btn btn-ghost btn-sm" id="logoutBtn">Abmelden</button>';
      $("#logoutBtn").onclick = async () => { await window.API.signOut(); refreshAuth(); };
    }
  }
  refreshAuth();

  // Absenden
  const errBox = $("#formError");
  const fail = (msg, el) => { errBox.textContent = msg; errBox.classList.remove("hidden"); if (el) el.focus(); return false; };
  function validate() {
    errBox.classList.add("hidden");
    if (state.kind === "bild" && !state.files.length) return fail("Bitte lade mindestens ein Bild hoch.");
    if (state.kind === "text" && $("#textContent").value.trim().length < 20) return fail("Bitte füge deinen Text ein (mindestens 20 Zeichen).", $("#textContent"));
    if (!state.product) return fail("Bitte wähle aus, was du bekommen möchtest.");
    if (!state.user) {
      if (!$("#name").value.trim()) return fail("Bitte gib deinen Namen ein.", $("#name"));
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test($("#email").value.trim())) return fail("Bitte gib eine gültige E-Mail-Adresse ein.", $("#email"));
      if ($("#password").value.length < 8) return fail("Das Passwort muss mindestens 8 Zeichen haben.", $("#password"));
    }
    if (!$("#c1").checked || !$("#c2").checked) return fail("Bitte bestätige die beiden Kästchen.");
    return true;
  }

  $("#bestellen").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!validate()) return;
    const btn = $("#submitBtn");
    const label = btn.textContent;
    const step = (t) => (btn.textContent = t);
    btn.disabled = true;
    try {
      if (!state.user) {
        step("Konto wird erstellt …");
        const r = await window.API.signUp({ name: $("#name").value.trim(), email: $("#email").value.trim(), password: $("#password").value, ref: window.UI.getRef() });
        window.UI.clearRef();
        if (r.needsConfirm) {
          fail("Fast geschafft! Wir haben dir eine E-Mail geschickt. Bestätige deine Adresse, melde dich an und sende den Auftrag dann noch einmal ab.");
          btn.disabled = false; step(label); return;
        }
        state.user = r.user;
      }
      if (state.user.isAdmin) throw new Error("Du bist als Admin angemeldet. Teste Bestellungen bitte mit einem Schüler-Konto.");
      step("Auftrag wird angelegt …");
      const order = await window.API.createOrder({
        kind: state.kind, product: state.product,
        subject: $("#subject").value, grade: $("#grade").value,
        wish: $("#wish").value.trim(), due_date: $("#due").value || null,
        text_content: state.kind === "text" ? $("#textContent").value.trim() : null
      });
      if (state.kind === "bild") {
        for (let i = 0; i < state.files.length; i++) {
          step("Datei " + (i + 1) + " von " + state.files.length + " wird hochgeladen …");
          await window.API.uploadFile(order, state.files[i]);
        }
      }
      step("Weiterleitung zur Bezahlung …");
      const url = window.API.paymentUrl(order, state.user.email);
      location.href = url || "konto.html#auftrag/" + order.id;
    } catch (err) {
      fail(err.message || String(err));
      btn.disabled = false; step(label);
      refreshAuth();
    }
  });
})();
