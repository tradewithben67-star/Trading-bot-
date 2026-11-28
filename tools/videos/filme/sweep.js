/* Liquidity Sweep (33 s): gleiche Hochs, Stopps darueber, ein Docht holt sie ab,
   die Kerze schliesst wieder darunter, danach die Gegenbewegung. */
FILMKERN(function(E){
  var v = E.v, sp = E.sp, F = E.farben, h = E.h, sym = E.symbol;
  var intro = KERZEN_INTRO(E, { klein: "Liquidität", gross: "Liquidity Sweep" });

  var D = [
    [103, 105.5, 106, 102.6], [105.5, 108.6, 109, 105.2], [108.6, 109.6, 110, 108.2], [109.6, 107.4, 109.9, 107],
    [107.4, 106.2, 107.8, 105.8], [106.2, 108.8, 109.2, 106], [108.8, 109.5, 110, 108.5], [109.5, 107.8, 109.8, 107.5],
    [107.8, 109.3, 109.6, 107.6], [109.3, 109.6, 110, 109],
    [109.6, 108.6, 111.8, 108.3],     /* 10: Docht ueber 110, Schluss darunter = Sweep */
    [108.6, 105.8, 108.9, 105.4], [105.8, 103.6, 106, 103.2], [103.6, 102.4, 104, 102]
  ];
  var ch = E.chart(D, { x0: 0, abstand: .72, breite: .46, y0: .6, mass: .25, basis: 99 });
  var x = ch.x, y = ch.y;
  E.sockel(x(6.5), 0, 11.2, 1.5);

  var ZEIT = [430, 443, 456, 469, 482, 495, 508, 521, 534, 547, 650, 760, 774, 788];
  var DAUER = [16, 16, 16, 16, 16, 16, 16, 16, 16, 16, 40, 16, 16, 16];
  ZEIT.forEach(function(z){ E.ereignis(z, "kerze"); });
  var SWEEP = 690;
  E.ereignis(SWEEP, "treffer");

  var linie = E.niveau(x(2) - .3, x(13) + .6, y(110), F.SILBER, .3);
  var liq = E.zone(x(2) - .3, x(13) + .6, y(110.08), y(111.3), F.LILA_HELL);
  var welle = E.welle(v(x(10), y(111.5), .4));

  /* Stopps als kleine Lichtpunkte ueber den Hochs */
  var r = E.zufall(5), stopps = [];
  for (var i = 0; i < 14; i++){
    var s = E.teil(new E.THREE.SphereGeometry(.055, 16, 12), E.mat.leucht(F.LILA_HELL, 2.2),
      x(2) + r() * (x(9.6) - x(2)), y(110.25) + r() * (y(111.15) - y(110.25)), .1 + r() * .3, false);
    s.userData.start = 600 + i * 2; s.userData.weg = 676 + Math.abs(s.position.x - x(10)) * 3;
    stopps.push(s);
  }

  var karten = intro.karten.concat([
    { von: 440, bis: 548, html: h("Gleiche Hochs") + '<p>Der Preis stößt mehrmals an <b>dieselbe Stelle</b> – und kommt nicht durch.</p>' },
    { von: 552, bis: 646, html: h("Darüber liegt Liquidität") + '<p>Über den Hochs warten viele <b>Stop-Loss</b>- und Kauf-Aufträge.</p>' },
    { von: SWEEP + 2, bis: 784, html: '<div class="klein">Liquidity Sweep</div>' + h("Sweep ✓") + '<p>Der Docht holt die Stopps über den Hochs ab – und die Kerze <b>schließt wieder darunter</b>.</p>' },
    { von: 790, bis: 846, art: "unten", html: '<div class="zeile">' + sym("lila", "↓") + h("Danach die Gegenbewegung") + '</div><p>Die Liquidität ist abgeholt – der Preis dreht.</p>' },
    { von: 848, bis: 926, html: '<div class="klein">Merke</div>' + h("Sweep oder Ausbruch?") + '<p>Beim Sweep schließt die Kerze <b>zurück im Bereich</b>. Ein echter Ausbruch <b>schließt darüber</b>.</p>' }
  ]);
  var tags = intro.tags.concat([
    { von: 472, bis: 640, ort: v(x(2), y(110) + .1, 0), text: "1", farbe: F.SILBER, mitte: true },
    { von: 524, bis: 640, ort: v(x(6), y(110) + .1, 0), text: "2", farbe: F.SILBER, mitte: true },
    { von: 563, bis: 640, ort: v(x(9), y(110) + .1, 0), text: "3", farbe: F.SILBER, mitte: true },
    { von: 610, bis: 690, ort: v(x(6), y(111.3) + .1, 0), text: "Stopps", farbe: F.LILA_HELL, mitte: true },
    { von: SWEEP + 4, bis: 784, ort: v(x(10) - .25, y(111.8), .3), text: "Docht holt Stopps", farbe: F.LILA_HELL, links: true },
    { von: SWEEP + 10, bis: 784, ort: v(x(10) - .3, y(108.6), .3), text: "Schluss darunter", farbe: F.SILBER, links: true }
  ]);
  var keys = intro.keys.concat([
    [452, v(1.8, 2.9, 10),   v(1.8, 2.1, 0), "f", 2.2],
    [552, v(4.0, 3.1, 10.6), v(4.0, 2.4, 0)],
    [640, v(4.3, 3.2, 12.4), v(4.3, 2.5, 0)],
    [720, v(6.3, 3.2, 10.6), v(6.3, 2.6, 0)],
    [800, v(7.4, 2.8, 10.8), v(7.4, 2.2, 0)],
    [850, v(4.75, 3.0, 22.5), v(4.7, 2.3, 0), "f", .8],
    [990, v(4.7, 2.9, 21.5),  v(4.7, 2.3, 0)]
  ]);

  return {
    laenge: 990, karten: karten, tags: tags, keys: keys,
    schluss: { von: 930, titel: "Liquidity Sweep erklärt.", text: "Erst die Stopps, dann die Bewegung." },
    update: function(b){
      intro.update(b);
      ch.bilde(b, ZEIT, DAUER);
      linie.zeichne(sp(b, 552, 578));
      liq.zeichne(sp(b, 590, 618));
      liq.puls(b >= SWEEP ? Math.max(0, 1 - (b - SWEEP) / 30) : 0);
      stopps.forEach(function(s){
        var a = E.feder(sp(b, s.userData.start, s.userData.start + 10)) * (1 - E.raus(sp(b, s.userData.weg, s.userData.weg + 8)));
        s.visible = a > .01; s.scale.setScalar(Math.max(.001, a));
      });
      ch.kerzen[10].leuchte(E.weich(Math.min(sp(b, SWEEP - 6, SWEEP + 4), 1 - sp(b, 770, 784))));
      welle.stelle(b, SWEEP);
      E.blitz(b, SWEEP);
    }
  };
});
