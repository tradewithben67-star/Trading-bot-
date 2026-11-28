/* CHoCH – Change of Character (33 s).
   Aufwaertstrend, letztes hoeheres Tief als Linie, kein neues Hoch mehr,
   dann schliesst eine Kerze unter dem Tief (CHoCH). */
FILMKERN(function(E){
  var v = E.v, sp = E.sp, F = E.farben, h = E.h, sym = E.symbol;
  var intro = KERZEN_INTRO(E, { klein: "Marktstruktur", gross: "CHoCH – Change of Character" });

  var D = [
    [100, 102.4, 103, 99.5], [102.4, 105, 105.6, 102], [105, 104, 105.4, 103.4], [104, 107.8, 108.3, 103.8],
    [107.8, 110, 110.6, 107.4], [110, 107.6, 110.2, 107.2], [107.6, 106.2, 108, 105.8], [106.2, 107, 107.4, 105.2],
    [107, 109.4, 109.9, 106.8],
    [109.4, 108.8, 110.1, 108.2],     /* 9: kein neues Hoch */
    [108.8, 106.4, 109, 106],
    [106.4, 104, 106.6, 103.6],       /* 11: Schluss unter 105.2 = CHoCH */
    [104, 104.6, 105.3, 103.8], [104.6, 102.2, 104.8, 101.8]
  ];
  var ch = E.chart(D, { x0: 0, abstand: .72, breite: .46, y0: .6, mass: .25, basis: 99 });
  var x = ch.x, y = ch.y;
  E.sockel(x(6.5), 0, 11.3, 1.5);

  var ZEIT = [430, 443, 456, 469, 482, 495, 508, 521, 585, 600, 676, 692, 746, 760];
  var DAUER = [16, 16, 16, 16, 16, 16, 16, 16, 16, 18, 16, 24, 16, 16];
  ZEIT.forEach(function(z){ E.ereignis(z, "kerze"); });
  var BRUCH = 716;
  E.ereignis(BRUCH, "treffer");

  var tief = E.niveau(x(7) - .3, x(13) + .6, y(105.2), F.SILBER, .3);
  var zick = E.linie([v(x(0), y(99.5), -.32), v(x(4), y(110.6), -.32), v(x(7), y(105.2), -.32), v(x(9), y(110.1), -.32), v(x(13), y(101.8), -.32)], .028);
  var welle = E.welle(v(x(11), y(105.2), .4));

  var karten = intro.karten.concat([
    { von: 440, bis: 540, html: h("Aufwärtstrend") + '<p>Höhere Hochs, höhere Tiefs – die <b>Käufer</b> haben die Kontrolle.</p>' },
    { von: 546, bis: 618, html: h("Die wichtige Linie") + '<p>Das <b>letzte höhere Tief</b>. Solange es hält, bleibt der Trend intakt.</p>' },
    { von: 622, bis: 704, art: "unten", html: '<div class="zeile">' + sym("lila", "!") + h("Kein neues Hoch") + '</div><p>Der Preis schafft es nicht mehr höher – die <b>Käufer werden schwächer</b>.</p>' },
    { von: BRUCH + 2, bis: 808, html: '<div class="klein">Change of Character</div>' + h("CHoCH ⚠") + '<p>Die Kerze schließt <b>unter dem letzten höheren Tief</b>: Der Charakter des Markts ändert sich.</p>' },
    { von: 838, bis: 926, html: '<div class="klein">Merke</div>' + h("BOS oder CHoCH?") + '<p><b>BOS:</b> Der Trend geht weiter. <b>CHoCH:</b> erstes Zeichen, dass er dreht – noch keine Garantie.</p>' }
  ]);
  var tags = intro.tags.concat([
    { von: 500, bis: 830, ort: v(x(4), y(110.6) + .12, 0), text: "Hoch", farbe: F.SILBER, mitte: true },
    { von: 540, bis: 830, ort: v(x(7), y(105.2) - .12, 0), text: "letztes höheres Tief", farbe: F.LILA_HELL, mitte: true, unter: true },
    { von: 622, bis: 830, ort: v(x(9), y(110.1) + .12, 0), text: "kein neues Hoch", farbe: F.LILA_HELL, mitte: true },
    { von: BRUCH + 4, bis: 808, ort: v(x(11) - .3, y(104), .3), text: "Schluss darunter", farbe: F.LILA_HELL, gross: true, links: true },
    { von: 790, bis: 960, ort: v(x(13), y(101.8) - .12, 0), text: "tieferes Tief", farbe: F.LILA_HELL, mitte: true, unter: true }
  ]);
  var keys = intro.keys.concat([
    [452, v(2.0, 2.9, 9.4),  v(1.9, 2.0, 0), "f", 2.2],
    [530, v(3.0, 3.2, 9.8),  v(3.0, 2.4, 0)],
    [610, v(4.9, 3.5, 10.2), v(5.0, 2.8, 0)],
    [700, v(6.4, 3.4, 10.2), v(6.5, 2.6, 0)],
    [800, v(7.6, 3.0, 10.8), v(7.7, 2.2, 0)],
    [840, v(5.0, 3.2, 25.5), v(4.95, 2.5, 0), "f", .8],
    [990, v(4.95, 3.0, 24.4), v(4.95, 2.5, 0)]
  ]);

  return {
    laenge: 990, karten: karten, tags: tags, keys: keys,
    schluss: { von: 930, titel: "CHoCH erklärt.", text: "Erst die Struktur lesen, dann handeln." },
    update: function(b){
      intro.update(b);
      ch.bilde(b, ZEIT, DAUER);
      tief.zeichne(sp(b, 548, 574));
      var nach = E.raus(sp(b, BRUCH, BRUCH + 16));
      if (b < BRUCH) tief.farbe("#ffffff", 1.1);
      else tief.farbe(F.LILA_HELL, 1.6 + nach + Math.max(0, 1 - (b - BRUCH) / 30) * 2);
      ch.kerzen[9].leuchte(E.weich(Math.min(sp(b, 616, 630), 1 - sp(b, 690, 704))) * .8);
      ch.kerzen[11].leuchte(E.weich(Math.min(sp(b, BRUCH - 4, BRUCH + 6), 1 - sp(b, 792, 808))));
      welle.stelle(b, BRUCH);
      E.blitz(b, BRUCH);
      zick.zeichne(E.weich(sp(b, 842, 888)));
    }
  };
});
