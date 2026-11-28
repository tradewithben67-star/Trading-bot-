/* Marktstruktur (36 s): Aufwaertstrend (HH/HL), Abwaertstrend (LH/LL), Seitwaerts (Range). */
FILMKERN(function(E){
  var v = E.v, sp = E.sp, F = E.farben, h = E.h;
  var intro = KERZEN_INTRO(E, { klein: "Grundlagen", gross: "Marktstruktur" });

  var D = [
    [100, 102, 102.4, 99.6], [102, 104.6, 105, 101.8], [104.6, 103, 104.9, 102.6], [103, 106.4, 106.8, 102.8],
    [106.4, 108.2, 108.6, 106], [108.2, 106.2, 108.4, 105.8], [106.2, 109.6, 110, 106], [109.6, 111, 111.4, 109.2],
    [111, 108.2, 111.2, 107.8], [108.2, 106.6, 108.5, 106.2], [106.6, 108.8, 109.2, 106.4], [108.8, 105.4, 109, 105],
    [105.4, 103.6, 105.6, 103.2], [103.6, 105.8, 106.2, 103.4], [105.8, 102.4, 106, 102],
    [102.4, 104.2, 104.6, 102.2], [104.2, 103, 104.5, 102.6], [103, 104, 104.4, 102.3], [104, 102.8, 104.6, 102.4], [102.8, 103.9, 104.5, 102.3]
  ];
  var ch = E.chart(D, { x0: 0, abstand: .62, breite: .4, y0: .6, mass: .26, basis: 99 });
  var x = ch.x, y = ch.y;
  E.sockel(x(9.5), 0, 13.6, 1.5);

  var ZEIT = [];
  for (var i = 0; i < 8; i++) ZEIT.push(430 + i * 14);
  for (i = 8; i < 15; i++) ZEIT.push(580 + (i - 8) * 14);
  for (i = 15; i < 20; i++) ZEIT.push(730 + (i - 15) * 14);
  ZEIT.forEach(function(z){ E.ereignis(z, "kerze"); });
  function fertig(i){ return ZEIT[i] + 14; }

  var hoch = function(i){ return v(x(i), y(D[i][2]), -.3); }, tief = function(i){ return v(x(i), y(D[i][3]), -.3); };
  var auf = E.linie([tief(0), hoch(1), tief(2), hoch(4), tief(5), hoch(7)], .026, E.mat.leucht(F.SILBER, 1.5));
  var ab = E.linie([hoch(7), tief(9), hoch(10), tief(12), hoch(13), tief(14)], .026);
  var range = E.zone(x(14) - .2, x(19) + .5, y(102.2), y(104.6), F.SILBER);

  function tag(i, oben, text, farbe){
    return { von: fertig(i) + 2, bis: 1000, ort: oben ? v(x(i), y(D[i][2]) + .1, 0) : v(x(i), y(D[i][3]) - .1, 0),
             text: text, farbe: farbe, mitte: true, unter: !oben };
  }
  var karten = intro.karten.concat([
    { von: 440, bis: 572, html: '<div class="klein">1 · Aufwärtstrend</div>' + h("Höher und höher") + '<p><b>Höhere Hochs</b> (HH) und <b>höhere Tiefs</b> (HL) – die Käufer führen.</p>' },
    { von: 590, bis: 722, html: '<div class="klein">2 · Abwärtstrend</div>' + h("Tiefer und tiefer") + '<p><b>Tiefere Hochs</b> (LH) und <b>tiefere Tiefs</b> (LL) – die Verkäufer führen.</p>' },
    { von: 740, bis: 850, html: '<div class="klein">3 · Seitwärts</div>' + h("Range") + '<p>Weder höher noch tiefer – der Preis pendelt zwischen einem <b>Hoch</b> und einem <b>Tief</b>.</p>' },
    { von: 866, bis: 1000, html: '<div class="klein">Merke</div>' + h("Struktur zuerst") + '<p>Erst die Richtung erkennen – dann BOS, CHoCH, FVG und Order Blocks darin lesen.</p>' }
  ]);
  var tags = intro.tags.concat([
    tag(2, false, "HL", F.SILBER), tag(4, true, "HH", F.SILBER), tag(5, false, "HL", F.SILBER), tag(7, true, "HH", F.SILBER),
    tag(10, true, "LH", F.LILA_HELL), tag(12, false, "LL", F.LILA_HELL), tag(13, true, "LH", F.LILA_HELL), tag(14, false, "LL", F.LILA_HELL),
    { von: 832, bis: 1000, ort: v(x(16.5), y(104.6) + .1, 0), text: "Range", farbe: F.SILBER, mitte: true, gross: true }
  ]);
  var keys = intro.keys.concat([
    [452,  v(1.6, 3.0, 10),   v(1.6, 2.2, 0), "f", 2.2],
    [545,  v(3.4, 3.5, 10.8), v(3.4, 2.8, 0)],
    [600,  v(4.6, 3.6, 11.4), v(4.6, 2.9, 0)],
    [700,  v(7.2, 3.2, 11.4), v(7.2, 2.5, 0)],
    [810,  v(10.2, 2.6, 10.6), v(10.2, 1.8, 0)],
    [862,  v(5.95, 3.0, 29.5), v(5.95, 2.3, 0), "f", .8],
    [1080, v(5.95, 2.9, 28),   v(5.95, 2.3, 0)]
  ]);

  return {
    laenge: 1080, karten: karten, tags: tags, keys: keys,
    schluss: { von: 1010, titel: "Marktstruktur erklärt.", text: "Hochs und Tiefs zeigen dir, wer gerade führt." },
    update: function(b){
      intro.update(b);
      ch.bilde(b, ZEIT);
      auf.zeichne(E.weich(sp(b, 545, 578)));
      ab.zeichne(E.weich(sp(b, 690, 724)));
      range.zeichne(sp(b, 800, 832));
    }
  };
});
