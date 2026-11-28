/* Angebot und Nachfrage – Supply & Demand (33 s).
   Nachfrage: von hier ging es schnell hoch. Angebot: von hier ging es schnell runter.
   Der Preis kommt zurueck und reagiert an beiden Zonen. */
FILMKERN(function(E){
  var v = E.v, sp = E.sp, F = E.farben, h = E.h, sym = E.symbol;
  var intro = KERZEN_INTRO(E, { klein: "Zonen", gross: "Supply & Demand" });

  var D = [
    [104, 103, 104.6, 102.4], [103, 101.4, 103.4, 101], [101.4, 101.8, 102.2, 100.6], [101.8, 101.2, 102.1, 100.5],
    [101.2, 106.8, 107.2, 101],       /* 4: schneller Anstieg aus der Nachfrage */
    [106.8, 110.2, 110.6, 106.4], [110.2, 111, 111.6, 109.6], [111, 110.6, 111.8, 110.2],
    [110.6, 105.6, 111, 105.2],       /* 8: schneller Fall aus dem Angebot */
    [105.6, 104, 105.8, 103.4],
    [104, 102.4, 104.4, 101.9],       /* 10: zurueck an der Nachfrage */
    [102.4, 105.4, 105.8, 102], [105.4, 108.4, 108.8, 105],
    [108.4, 110.6, 111.2, 108],       /* 13: zurueck am Angebot */
    [110.6, 108.4, 111.4, 108]        /* 14: abgewiesen */
  ];
  var ch = E.chart(D, { x0: 0, abstand: .72, breite: .46, y0: .5, mass: .25, basis: 99 });
  var x = ch.x, y = ch.y;
  E.sockel(x(7), 0, 11.9, 1.5);

  var ZEIT = [430, 443, 456, 469, 482, 506, 520, 533, 548, 576, 640, 682, 696, 740, 760];
  var DAUER = [16, 16, 16, 16, 24, 16, 16, 16, 24, 16, 20, 16, 16, 18, 22];
  ZEIT.forEach(function(z){ E.ereignis(z, "kerze"); });
  var UNTEN = 660, OBEN = 782;
  E.ereignis(UNTEN, "treffer"); E.ereignis(OBEN, "treffer");

  var nachfrage = E.zone(x(2) - .3, x(14) + .6, y(100.5), y(102.2), F.SILBER);
  var angebot = E.zone(x(6) - .3, x(14) + .6, y(109.6), y(111.8), F.LILA_HELL);
  var w1 = E.welle(v(x(10), y(102), .5), "#ffffff"), w2 = E.welle(v(x(14), y(111.2), .5));

  var karten = intro.karten.concat([
    { von: 440, bis: 538, html: '<div class="klein">Demand</div>' + h("Nachfrage") + '<p>Von hier ist der Preis in einem Zug <b>nach oben</b> gelaufen.</p>' },
    { von: 542, bis: 622, html: '<div class="klein">Supply</div>' + h("Angebot") + '<p>Und von dort genauso schnell <b>nach unten</b>.</p>' },
    { von: 626, bis: 700, html: h("Warum dort?") + '<p>In diesen Zonen lagen <b>große Aufträge</b>. Ein Teil davon ist oft noch offen.</p>' },
    { von: 704, bis: 776, art: "unten", html: '<div class="zeile">' + sym("chrom", "↑") + h("Zurück an der Nachfrage") + '</div><p>Käufer steigen wieder ein – der Preis springt hoch.</p>' },
    { von: 786, bis: 846, art: "unten", html: '<div class="zeile">' + sym("lila", "↓") + h("Zurück am Angebot") + '</div><p>Verkäufer warten dort – der Preis prallt ab.</p>' },
    { von: 850, bis: 926, html: '<div class="klein">Merke</div>' + h("Wo es schnell ging, war jemand groß dabei") + '<p>Nachfrage unten, Angebot oben – kommt der Preis zurück, reagiert er oft.</p>' }
  ]);
  var tags = intro.tags.concat([
    { von: 500, bis: 620, ort: v(x(4), y(107.2) + .1, 0), text: "schneller Anstieg", farbe: F.SILBER, mitte: true },
    { von: 530, bis: 940, ort: v(x(3) + .3, y(101.35), .5), text: "Nachfrage", farbe: F.SILBER },
    { von: 574, bis: 700, ort: v(x(8) + .3, y(105.6), .3), text: "schneller Fall", farbe: F.LILA_HELL },
    { von: 604, bis: 940, ort: v(x(7) + .3, y(110.7), .5), text: "Angebot", farbe: F.LILA_HELL },
    { von: UNTEN + 4, bis: 776, ort: v(x(10), y(101.9) - .1, 0), text: "Reaktion", farbe: F.SILBER, mitte: true, unter: true },
    { von: OBEN + 4, bis: 900, ort: v(x(14), y(111.4) + .1, 0), text: "abgewiesen", farbe: F.LILA_HELL, mitte: true }
  ]);
  var keys = intro.keys.concat([
    [452, v(1.6, 2.8, 10),   v(1.6, 2.0, 0), "f", 2.2],
    [540, v(3.2, 3.0, 10.6), v(3.2, 2.3, 0)],
    [620, v(4.4, 3.0, 11.5), v(4.4, 2.4, 0)],
    [700, v(6.2, 2.8, 11),   v(6.2, 2.1, 0)],
    [790, v(8.4, 3.0, 11),   v(8.4, 2.4, 0)],
    [850, v(5.05, 3.0, 24),  v(5.05, 2.3, 0), "f", .8],
    [990, v(5.05, 2.9, 23),  v(5.05, 2.3, 0)]
  ]);

  return {
    laenge: 990, karten: karten, tags: tags, keys: keys,
    schluss: { von: 930, titel: "Angebot & Nachfrage erklärt.", text: "Als Nächstes: der Order Block." },
    update: function(b){
      intro.update(b);
      ch.bilde(b, ZEIT, DAUER);
      nachfrage.zeichne(sp(b, 512, 542));
      angebot.zeichne(sp(b, 580, 610));
      nachfrage.puls(b >= UNTEN ? Math.max(0, 1 - (b - UNTEN) / 28) : 0);
      angebot.puls(b >= OBEN ? Math.max(0, 1 - (b - OBEN) / 28) : 0);
      ch.kerzen[4].leuchte(E.weich(Math.min(sp(b, 496, 506), 1 - sp(b, 530, 542))) * .8);
      ch.kerzen[8].leuchte(E.weich(Math.min(sp(b, 566, 576), 1 - sp(b, 600, 612))) * .8);
      ch.kerzen[10].leuchte(E.weich(Math.min(sp(b, UNTEN - 6, UNTEN + 4), 1 - sp(b, 690, 704))));
      ch.kerzen[14].leuchte(E.weich(Math.min(sp(b, OBEN - 6, OBEN + 4), 1 - sp(b, 830, 846))));
      w1.stelle(b, UNTEN); w2.stelle(b, OBEN);
      E.blitz(b, OBEN);
    }
  };
});
