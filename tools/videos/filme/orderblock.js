/* Order Block (33 s): die letzte fallende Kerze vor dem starken Anstieg (mit BOS),
   ihr Koerper wird zur Zone, der Preis kommt zurueck und reagiert. */
FILMKERN(function(E){
  var v = E.v, sp = E.sp, F = E.farben, h = E.h, sym = E.symbol;
  var intro = KERZEN_INTRO(E, { klein: "Zonen", gross: "Order Block" });

  var D = [
    [107, 106, 107.4, 105.6], [106, 104.6, 106.3, 104.2],
    [104.6, 103.2, 105, 102.8],       /* 2: letzte fallende Kerze = Order Block (Koerper 103.2 bis 104.6) */
    [103.2, 108.4, 108.8, 103],       /* 3: starker Anstieg */
    [108.4, 111.2, 111.6, 108],       /* 4: schliesst ueber 107.4 = BOS */
    [111.2, 110.4, 111.8, 110], [110.4, 107.6, 110.6, 107.2], [107.6, 105.4, 107.8, 105],
    [105.4, 104.2, 105.6, 103.6],     /* 8: zurueck im Order Block */
    [104.2, 107.8, 108.2, 103.9], [107.8, 111, 111.4, 107.5], [111, 113.4, 113.8, 110.7]
  ];
  var ch = E.chart(D, { x0: 0, abstand: .72, breite: .46, y0: .6, mass: .25, basis: 99 });
  var x = ch.x, y = ch.y;
  E.sockel(x(5.5), 0, 9.9, 1.5);

  var ZEIT = [430, 443, 456, 476, 506, 640, 654, 668, 684, 726, 740, 754];
  var DAUER = [16, 16, 16, 24, 18, 16, 16, 16, 20, 16, 16, 16];
  ZEIT.forEach(function(z){ E.ereignis(z, "kerze"); });
  var BOS = 524, TAP = 704;
  E.ereignis(BOS, "tick"); E.ereignis(TAP, "treffer");

  var hoch = E.niveau(x(0) - .3, x(4) + .5, y(107.4), F.SILBER, .3);
  var ob = E.zone(x(2) - .25, x(11) + .6, y(103.2), y(104.6), F.SILBER);
  var welle = E.welle(v(x(8), y(104), .5), "#ffffff");

  var karten = intro.karten.concat([
    { von: 440, bis: 520, html: h("Order Block") + '<p>Die <b>letzte fallende Kerze</b>, bevor der Preis kräftig nach oben läuft.</p>' },
    { von: 524, bis: 608, html: h("Hier sind Große eingestiegen") + '<p>In dieser Kerze haben große Käufer ihre Aufträge platziert – danach ging es schnell hoch, sogar mit <b>BOS</b>.</p>' },
    { von: 612, bis: 700, html: h("Der Körper wird zur Zone") + '<p>Von <b>Eröffnung bis Schluss</b> dieser Kerze ziehst du einen Bereich nach rechts.</p>' },
    { von: 706, bis: 790, art: "unten", html: '<div class="zeile">' + sym("chrom", "↑") + h("Rücklauf in den Order Block") + '</div><p>Der Preis kommt zurück – die Käufer verteidigen ihre Zone.</p>' },
    { von: 846, bis: 926, html: '<div class="klein">Merke</div>' + h("Ursprung der Bewegung") + '<p>Am stärksten mit BOS danach. Nach unten genauso: die <b>letzte steigende Kerze</b> vor dem Fall.</p>' }
  ]);
  var tags = intro.tags.concat([
    { von: 498, bis: 600, ort: v(x(3) + .3, y(106), .3), text: "starker Anstieg", farbe: F.SILBER },
    { von: BOS + 2, bis: 610, ort: v(x(4), y(111.6) + .1, 0), text: "BOS", farbe: F.SILBER, mitte: true, gross: true },
    { von: 528, bis: 612, ort: v(x(2), y(102.8) - .1, 0), text: "letzte fallende Kerze", farbe: F.LILA_HELL, mitte: true, unter: true },
    { von: 630, bis: 940, ort: v(x(3) + .3, y(103.9), .5), text: "Order Block", farbe: F.SILBER, gross: true },
    { von: TAP + 4, bis: 790, ort: v(x(8), y(103.6) - .1, 0), text: "Reaktion", farbe: F.SILBER, mitte: true, unter: true }
  ]);
  var keys = intro.keys.concat([
    [452, v(1.4, 2.8, 9.6),  v(1.4, 2.0, 0), "f", 2.2],
    [530, v(2.4, 3.0, 10.4), v(2.4, 2.3, 0)],
    [620, v(3.0, 2.9, 11),   v(3.0, 2.2, 0)],
    [700, v(4.8, 2.7, 10.8), v(4.8, 2.0, 0)],
    [790, v(6.0, 3.0, 11),   v(6.0, 2.3, 0)],
    [848, v(4.0, 3.0, 20.5), v(4.0, 2.3, 0), "f", .8],
    [990, v(4.0, 2.9, 19.5), v(4.0, 2.3, 0)]
  ]);

  return {
    laenge: 990, karten: karten, tags: tags, keys: keys,
    schluss: { von: 930, titel: "Order Block erklärt.", text: "Dort ist der Markt gedreht – dort schaut er wieder hin." },
    update: function(b){
      intro.update(b);
      ch.bilde(b, ZEIT, DAUER);
      hoch.zeichne(sp(b, 470, 490) * (1 - sp(b, 600, 616)));
      hoch.farbe("#ffffff", 1.1 + (b > BOS ? Math.max(0, 1 - (b - BOS) / 26) * 2 : 0));
      ch.kerzen[2].leuchte(E.weich(Math.min(sp(b, 524, 536), 1 - sp(b, 640, 656))));
      ob.zeichne(sp(b, 616, 646));
      ob.puls(b >= TAP ? Math.max(0, 1 - (b - TAP) / 28) : 0);
      ch.kerzen[8].leuchte(E.weich(Math.min(sp(b, TAP - 6, TAP + 4), 1 - sp(b, 776, 790))));
      welle.stelle(b, TAP);
      E.blitz(b, TAP, "rgba(220,220,235,.25)");
    }
  };
});
