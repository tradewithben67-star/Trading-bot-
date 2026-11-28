/* IFVG – Inverse Fair Value Gap (33 s).
   Erst ein normales FVG nach oben, dann schliesst eine Kerze komplett darunter.
   Die Luecke dreht: aus Unterstuetzung wird Widerstand, der Preis prallt von unten ab. */
FILMKERN(function(E){
  var v = E.v, sp = E.sp, F = E.farben, h = E.h, sym = E.symbol;
  var intro = KERZEN_INTRO(E, { klein: "Preis-Lücken", gross: "IFVG – Inverse Fair Value Gap" });

  var D = [
    [100, 101.2, 101.8, 99.6],
    [101.2, 102.2, 103, 100.8],       /* 1: Hoch 103 */
    [102.2, 108.6, 109, 102],         /* 2: schnelle Kerze */
    [108.6, 110, 110.8, 105.4],       /* 3: Tief 105.4 -> FVG 103 bis 105.4 */
    [110, 108.2, 110.4, 107.8], [108.2, 106, 108.5, 105.6],
    [106, 101.6, 106.2, 101.2],       /* 6: schliesst komplett darunter -> IFVG */
    [101.6, 100.8, 102.2, 100.2], [100.8, 103.6, 104.2, 100.6],
    [103.6, 102.6, 104.9, 102.2],     /* 9: Docht in die Luecke, abgewiesen */
    [102.6, 100, 102.8, 99.6], [100, 98.4, 100.3, 98]
  ];
  var ch = E.chart(D, { x0: 0, abstand: .72, breite: .46, y0: .8, mass: .25, basis: 99 });
  var x = ch.x, y = ch.y;
  E.sockel(x(5.5), 0, 9.9, 1.5);

  var ZEIT = [430, 443, 458, 482, 548, 562, 600, 700, 714, 732, 784, 798];
  var DAUER = [16, 16, 22, 18, 16, 16, 30, 16, 16, 24, 16, 16];
  ZEIT.forEach(function(z){ E.ereignis(z, "kerze"); });
  var BRUCH = 630, ABPRALL = 756;
  E.ereignis(BRUCH, "treffer"); E.ereignis(ABPRALL, "tick");

  var luecke = E.zone(x(1) - .25, x(11) + .6, y(103), y(105.4), F.SILBER);
  var welle = E.welle(v(x(6), y(103), .5));
  var welle2 = E.welle(v(x(9), y(104.9), .5));

  var karten = intro.karten.concat([
    { von: 440, bis: 538, html: h("Erst ein normales FVG") + '<p>Schnelle Bewegung nach oben – zwischen Kerze 1 und 3 bleibt eine <b>Lücke</b>.</p>' },
    { von: 542, bis: 620, html: h("Normalerweise: Unterstützung") + '<p>Kommt der Preis zurück, erwarten viele eine Reaktion <b>nach oben</b>.</p>' },
    { von: BRUCH + 2, bis: 724, html: '<div class="klein">Inversion</div>' + h("IFVG ⚠") + '<p>Die Kerze schließt <b>komplett unter</b> der Lücke. Jetzt dreht sie: aus Unterstützung wird <b>Widerstand</b>.</p>' },
    { von: 728, bis: 836, art: "unten", html: '<div class="zeile">' + sym("lila", "↓") + h("Von unten getestet") + '</div><p>Der Preis kommt zurück an die Lücke – und <b>prallt ab</b>.</p>' },
    { von: 840, bis: 926, html: '<div class="klein">Merke</div>' + h("IFVG = gedrehte Lücke") + '<p>Wird ein FVG komplett durchbrochen, wirkt es danach in die <b>andere Richtung</b>.</p>' }
  ]);
  var tags = intro.tags.concat([
    { von: 512, bis: BRUCH, ort: v(x(4) + .05, y(104.2), .5), text: "FVG", farbe: F.SILBER, gross: true },
    { von: BRUCH + 4, bis: 900, ort: v(x(4) + .05, y(104.2), .5), text: "IFVG", farbe: F.LILA_HELL, gross: true },
    { von: BRUCH + 4, bis: 724, ort: v(x(6) - .3, y(101.6), .3), text: "Schluss darunter", farbe: F.LILA_HELL, links: true },
    { von: ABPRALL + 4, bis: 880, ort: v(x(9), y(104.9) + .12, 0), text: "abgewiesen", farbe: F.LILA_HELL, mitte: true }
  ]);
  var keys = intro.keys.concat([
    [452, v(1.4, 3.0, 8.8),  v(1.3, 2.2, 0), "f", 2.2],
    [560, v(2.4, 3.1, 9.2),  v(2.4, 2.3, 0)],
    [660, v(3.6, 2.9, 9.8),  v(3.6, 2.1, 0)],
    [760, v(5.2, 2.7, 10.2), v(5.2, 1.9, 0)],
    [830, v(6.0, 2.6, 10.4), v(6.0, 1.8, 0)],
    [866, v(4.0, 2.9, 21.5), v(3.95, 2.2, 0), "f", .8],
    [990, v(3.95, 2.8, 20.5), v(3.95, 2.2, 0)]
  ]);

  return {
    laenge: 990, karten: karten, tags: tags, keys: keys,
    schluss: { von: 930, titel: "IFVG erklärt.", text: "Gebrochene Unterstützung wird Widerstand." },
    update: function(b){
      intro.update(b);
      ch.bilde(b, ZEIT, DAUER);
      luecke.zeichne(sp(b, 500, 536));
      var dreh = E.raus(sp(b, BRUCH, BRUCH + 14));
      if (b < BRUCH) luecke.farbe(F.SILBER, 1.3);
      else luecke.farbe(F.LILA_HELL, 1.3 + dreh * .9);
      luecke.puls(Math.max(b >= BRUCH ? Math.max(0, 1 - (b - BRUCH) / 30) : 0,
                           b >= ABPRALL ? Math.max(0, 1 - (b - ABPRALL) / 24) * .7 : 0));
      ch.kerzen[6].leuchte(E.weich(Math.min(sp(b, BRUCH - 6, BRUCH + 4), 1 - sp(b, 710, 724))));
      ch.kerzen[9].leuchte(E.weich(Math.min(sp(b, ABPRALL - 6, ABPRALL + 4), 1 - sp(b, 860, 876))));
      welle.stelle(b, BRUCH); welle2.stelle(b, ABPRALL);
      E.blitz(b, BRUCH);
    }
  };
});
