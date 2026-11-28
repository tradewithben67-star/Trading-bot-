/* BOS – Break of Structure (33 s).
   Aufwaertstrend, letztes Hoch als Linie, eine Kerze sticht nur mit dem
   Docht darueber (kein BOS), die naechste schliesst darueber (BOS). */
FILMKERN(function(E){
  var v = E.v, sp = E.sp, F = E.farben, h = E.h, sym = E.symbol;
  var intro = KERZEN_INTRO(E, { klein: "Marktstruktur", gross: "BOS – Break of Structure" });

  var D = [
    [100, 102, 102.6, 99.4], [102, 104.5, 105, 101.6], [104.5, 103.8, 105.4, 103.2], [103.8, 107.5, 108, 103.5],
    [107.5, 109.4, 110, 107], [109.4, 107.6, 109.8, 107.2], [107.6, 106, 108, 105.6], [106, 106.6, 107.2, 105],
    [106.6, 109.2, 110.8, 106.3],     /* 8: nur der Docht ueber 110 */
    [109.2, 112.5, 113, 108.8],       /* 9: Schluss ueber 110 = BOS */
    [112.5, 114.4, 115, 112], [114.4, 113.2, 114.8, 112.6], [113.2, 115.6, 116, 113]
  ];
  var ch = E.chart(D, { x0: 0, abstand: .72, breite: .46, y0: .6, mass: .25, basis: 99 });
  var x = ch.x, y = ch.y;
  E.sockel(x(6), 0, 10.6, 1.5);

  var ZEIT = [430, 443, 456, 469, 482, 495, 508, 521, 592, 690, 742, 756, 770];
  var DAUER = [16, 16, 16, 16, 16, 16, 16, 16, 24, 24, 16, 16, 16];
  ZEIT.forEach(function(z){ E.ereignis(z, "kerze"); });
  var BRUCH = 714;
  E.ereignis(BRUCH, "treffer");

  var hoch = E.niveau(x(4) - .3, x(12) + .6, y(110), F.SILBER, .3);
  var zick = E.linie([v(x(0), y(99.4), -.32), v(x(4), y(110), -.32), v(x(7), y(105), -.32), v(x(12), y(116), -.32)], .028);
  var welle = E.welle(v(x(9), y(110), .4));

  var karten = intro.karten.concat([
    { von: 440, bis: 540, html: h("Marktstruktur") + '<p>Im Aufwärtstrend macht der Preis <b>höhere Hochs</b> und <b>höhere Tiefs</b>.</p>' },
    { von: 546, bis: 616, html: h("Das letzte Hoch") + '<p>Diese Linie ist die Struktur. Was passiert, wenn der Preis sie bricht?</p>' },
    { von: 618, bis: 702, art: "unten", html: '<div class="zeile">' + sym("lila", "✕") + h("Nur ein Docht darüber") + '</div><p>Noch <b>kein BOS</b> – es zählt, wo die Kerze <b>schließt</b>.</p>' },
    { von: BRUCH + 2, bis: 806, html: '<div class="klein">Break of Structure</div>' + h("BOS ✓") + '<p>Die Kerze schließt <b>über dem letzten Hoch</b>: Der Aufwärtstrend geht weiter.</p>' },
    { von: 838, bis: 926, html: '<div class="klein">Merke</div>' + h("BOS = Trend bestätigt") + '<p>Schluss über dem letzten Hoch. Im Abwärtstrend genauso – nur nach unten.</p>' }
  ]);
  var tags = intro.tags.concat([
    { von: 500, bis: 830, ort: v(x(4), y(110) + .12, 0), text: "letztes Hoch", farbe: F.SILBER, mitte: true },
    { von: 540, bis: 830, ort: v(x(7), y(105) - .12, 0), text: "höheres Tief", farbe: F.LILA_HELL, mitte: true, unter: true },
    { von: 618, bis: 702, ort: v(x(8) + .25, y(110.8), .3), text: "nur Docht", farbe: F.LILA_HELL },
    { von: BRUCH + 4, bis: 806, ort: v(x(9) + .3, y(112.5), .3), text: "Schluss darüber", farbe: F.SILBER, gross: true },
    { von: 792, bis: 960, ort: v(x(12), y(116) + .12, 0), text: "neues Hoch", farbe: F.SILBER, mitte: true }
  ]);
  var keys = intro.keys.concat([
    [452, v(2.0, 2.9, 9.4),  v(1.9, 2.0, 0), "f", 2.2],
    [530, v(3.0, 3.2, 9.8),  v(3.0, 2.4, 0)],
    [600, v(4.6, 3.6, 10.2), v(4.7, 2.9, 0)],
    [700, v(5.7, 3.9, 10.2), v(5.8, 3.2, 0)],
    [800, v(6.7, 4.3, 10.8), v(6.8, 3.6, 0)],
    [840, v(4.45, 3.3, 24.5), v(4.35, 2.7, 0), "f", .8],
    [990, v(4.35, 3.1, 23.4), v(4.35, 2.7, 0)]
  ]);

  return {
    laenge: 990, karten: karten, tags: tags, keys: keys,
    schluss: { von: 930, titel: "BOS erklärt.", text: "Als Nächstes: CHoCH – wenn der Trend dreht." },
    update: function(b){
      intro.update(b);
      ch.bilde(b, ZEIT, DAUER);
      hoch.zeichne(sp(b, 548, 574));
      var nach = E.raus(sp(b, BRUCH, BRUCH + 16));
      hoch.farbe("#ffffff", 1.1 + nach * 1.6 + (b > BRUCH ? Math.max(0, 1 - (b - BRUCH) / 30) * 2 : 0));
      ch.kerzen[8].leuchte(E.weich(Math.min(sp(b, 612, 626), 1 - sp(b, 690, 702))) * .8);
      ch.kerzen[9].leuchte(E.weich(Math.min(sp(b, BRUCH - 4, BRUCH + 6), 1 - sp(b, 790, 806))));
      welle.stelle(b, BRUCH);
      E.blitz(b, BRUCH, "rgba(220,220,235,.35)");
      zick.zeichne(E.weich(sp(b, 842, 886)));
    }
  };
});
