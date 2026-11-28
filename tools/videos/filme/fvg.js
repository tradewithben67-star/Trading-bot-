/* FVG – Fair Value Gap (33 s).
   Drei Kerzen, die mittlere laeuft weg. Zwischen dem Hoch von Kerze 1 und
   dem Tief von Kerze 3 bleibt eine Luecke. Der Preis kommt zurueck und reagiert. */
FILMKERN(function(E){
  var v = E.v, sp = E.sp, F = E.farben, h = E.h, sym = E.symbol;
  var intro = KERZEN_INTRO(E, { klein: "Preis-Lücken", gross: "FVG – Fair Value Gap" });

  var D = [
    [100, 101.2, 101.8, 99.6],
    [101.2, 102.2, 103, 100.8],       /* 1: Hoch 103 */
    [102.2, 108.6, 109, 102],         /* 2: die schnelle Kerze */
    [108.6, 110, 110.8, 105.4],       /* 3: Tief 105.4 -> Luecke 103 bis 105.4 */
    [110, 111.2, 111.8, 109.4], [111.2, 108.4, 111.5, 108], [108.4, 106, 108.6, 105.6],
    [106, 104.6, 106.3, 103.8],       /* 7: laeuft in die Luecke */
    [104.6, 107.6, 108, 104.3], [107.6, 110.4, 110.8, 107.3], [110.4, 112.6, 113, 110]
  ];
  var ch = E.chart(D, { x0: 0, abstand: .72, breite: .46, y0: .6, mass: .25, basis: 99 });
  var x = ch.x, y = ch.y;
  E.sockel(x(5), 0, 9.2, 1.5);

  var ZEIT = [430, 443, 470, 508, 700, 714, 728, 744, 790, 804, 818];
  var DAUER = [16, 16, 30, 20, 16, 16, 16, 20, 16, 16, 16];
  ZEIT.forEach(function(z){ E.ereignis(z, "kerze"); });
  var TREFFER = 764;
  E.ereignis(TREFFER, "treffer");

  var luecke = E.zone(x(1) - .25, x(10) + .6, y(103), y(105.4), F.SILBER);
  var welle = E.welle(v(x(7), y(104.2), .5), "#ffffff");

  var karten = intro.karten.concat([
    { von: 440, bis: 528, html: h("Fair Value Gap") + '<p>Eine <b>Lücke im Kurs</b> – sie entsteht durch eine sehr schnelle Bewegung.</p>' },
    { von: 532, bis: 612, html: h("Drei Kerzen") + '<p>Die <b>mittlere Kerze</b> läuft so schnell weg, dass eine Lücke bleibt.</p>' },
    { von: 616, bis: 700, html: h("Die Lücke") + '<p>Zwischen dem <b>Hoch von Kerze 1</b> und dem <b>Tief von Kerze 3</b> wurde kaum gehandelt.</p>' },
    { von: 704, bis: 790, html: h("Der Markt kommt zurück") + '<p>Oft läuft der Preis später in die Lücke zurück, um sie zu füllen.</p>' },
    { von: 798, bis: 880, art: "unten", html: '<div class="zeile">' + sym("chrom", "↑") + h("Reaktion aus der Lücke") + '</div><p>Die Käufer steigen dort wieder ein – der Preis dreht nach oben.</p>' },
    { von: 846, bis: 926, html: '<div class="klein">Merke</div>' + h("FVG = Lücke nach schneller Bewegung") + '<p>Der Preis kehrt oft dorthin zurück und reagiert. Nach unten funktioniert es genauso.</p>' }
  ]);
  var tags = intro.tags.concat([
    { von: 500, bis: 612, ort: v(x(2), y(109) + .12, 0), text: "schnelle Kerze", farbe: F.SILBER, mitte: true },
    { von: 534, bis: 612, ort: v(x(1), y(100.8) - .12, 0), text: "1", farbe: F.LILA_HELL, mitte: true, unter: true },
    { von: 540, bis: 612, ort: v(x(2), y(102) - .12, 0), text: "2", farbe: F.LILA_HELL, mitte: true, unter: true },
    { von: 546, bis: 612, ort: v(x(3), y(105.4) - .12, 0), text: "3", farbe: F.LILA_HELL, mitte: true, unter: true },
    { von: 618, bis: 700, ort: v(x(1), y(103) + .12, 0), text: "Hoch Kerze 1", farbe: F.GRAU, mitte: true },
    { von: 626, bis: 700, ort: v(x(3) + .3, y(105.4), .3), text: "Tief Kerze 3", farbe: F.GRAU },
    { von: 652, bis: 900, ort: v(x(4) + .1, y(104.2), .5), text: "FVG", farbe: F.SILBER, gross: true },
    { von: 768, bis: 860, ort: v(x(7), y(103.8) - .12, 0), text: "zurück in der Lücke", farbe: F.LILA_HELL, mitte: true, unter: true }
  ]);
  var keys = intro.keys.concat([
    [452, v(1.3, 2.6, 8.6),  v(1.2, 1.7, 0), "f", 2.2],
    [612, v(1.3, 2.8, 9.2),  v(1.3, 1.9, 0)],
    [700, v(1.9, 2.9, 9.6),  v(1.9, 2.0, 0)],
    [780, v(4.4, 2.9, 10.2), v(4.4, 2.1, 0)],
    [840, v(5.4, 3.1, 10.6), v(5.4, 2.4, 0)],
    [870, v(3.7, 3.0, 20.5), v(3.65, 2.3, 0), "f", .8],
    [990, v(3.65, 2.9, 19.5), v(3.65, 2.3, 0)]
  ]);

  return {
    laenge: 990, karten: karten, tags: tags, keys: keys,
    schluss: { von: 930, titel: "FVG erklärt.", text: "Als Nächstes: IFVG – wenn die Lücke die Seite wechselt." },
    update: function(b){
      intro.update(b);
      ch.bilde(b, ZEIT, DAUER);
      var trio = E.weich(Math.min(sp(b, 530, 542), 1 - sp(b, 600, 614)));
      [1, 2, 3].forEach(function(i){ ch.kerzen[i].leuchte(trio * .8); });
      ch.kerzen[2].leuchte(Math.max(trio * .8, E.weich(Math.min(sp(b, 488, 500), 1 - sp(b, 520, 532)))));
      luecke.zeichne(sp(b, 628, 662));
      luecke.puls(Math.max(E.weich(Math.min(sp(b, 640, 656), 1 - sp(b, 680, 700))) * .6,
                           b >= TREFFER ? Math.max(0, 1 - (b - TREFFER) / 26) : 0));
      ch.kerzen[7].leuchte(E.weich(Math.min(sp(b, TREFFER - 6, TREFFER + 4), 1 - sp(b, 846, 860))));
      welle.stelle(b, TREFFER);
      E.blitz(b, TREFFER, "rgba(220,220,235,.25)");
    }
  };
});
