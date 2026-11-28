/* Gemeinsamer Anfang aller Kerzen-Filme (Bild 0 bis 420, 14 s):
   1. Titel  2. Aufbau einer Kerze  3. steigend oder fallend
   4. vier Kerzen-Typen und was sie aussagen.
   Liegt links in der Welt (x < -25), der Film selbst baut bei x >= 0. */
window.KERZEN_INTRO = function(E, titel){
  var v = E.v, sp = E.sp, F = E.farben, h = E.h, sym = E.symbol;
  var ENDE = 420;

  /* 1 und 2: eine grosse steigende Kerze */
  var gross = { y0: .45, mass: .32, basis: 98, breite: .9 };
  var A = E.kerze(100, 106, 108, 98, Object.assign({ x: -40 }, gross));
  var Bk = E.kerze(106, 101, 107.2, 99.4, Object.assign({ x: -38.5 }, gross));
  E.sockel(-39.25, 0, 3.6, 1.8);
  var ya = A.y, yb = Bk.y;

  /* 4: vier Typen nebeneinander */
  var typ = { y0: .45, mass: .3, basis: 98, breite: .62 };
  var TX = [-31.95, -30.65, -29.35, -28.05];
  var T = [
    E.kerze(99, 106.6, 107.1, 98.6, Object.assign({ x: TX[0] }, typ)),     /* grosser Koerper */
    E.kerze(100.6, 99.7, 107, 99.3, Object.assign({ x: TX[1] }, typ)),      /* langer Docht oben */
    E.kerze(104.6, 105.7, 106.1, 98.6, Object.assign({ x: TX[2] }, typ)),   /* langer Docht unten */
    E.kerze(102.5, 102.6, 105.2, 100, Object.assign({ x: TX[3] }, typ))     /* Doji */
  ];
  E.sockel(-30, 0, 5.6, 1.6);
  var TYP_ZEIT = [250, 292, 334, 376];

  var karten = [
    { von: 4, bis: 88, art: "titel", html: '<div class="klein">' + titel.klein + '</div>' + h(titel.gross) },
    { von: 40, bis: 92, art: "unten", html: '<div class="zeile">' + sym("lila", "?") + h("Zuerst: die Kerze") + '</div><p>Was sagt dir eine einzelne Kerze?</p>' },
    { von: 94, bis: 172, art: "", html: h("Aufbau einer Kerze") + '<p>Der <b>Körper</b> reicht von Eröffnung bis Schluss. Die <b>Dochte</b> zeigen Hoch und Tief.</p>' },
    { von: 176, bis: 244, art: "", html: h("Steigend oder fallend") + '<p>Die Farbe zeigt dir, wer gewonnen hat.</p>' },
    { von: 186, bis: 244, art: "unten", html: '<div class="legende">' +
        '<div><i style="background:linear-gradient(180deg,#fff,#9EA2AE)"></i><div>Chrom: Schluss über Eröffnung<br><span>Preis gestiegen – Käufer gewinnen</span></div></div>' +
        '<div><i style="background:' + F.LILA + '"></i><div>Lila: Schluss unter Eröffnung<br><span>Preis gefallen – Verkäufer gewinnen</span></div></div></div>' },
    { von: 248, bis: 418, art: "", html: '<div class="klein">Kerzen lesen</div>' + h("Was jede Kerze dir sagt") },
    { von: TYP_ZEIT[0], bis: TYP_ZEIT[1], art: "unten", html: '<div class="zeile">' + sym("chrom", "1") + h("Großer Körper") + '</div><p>Eine Seite hat klar gewonnen – eine <b>starke Bewegung</b>.</p>' },
    { von: TYP_ZEIT[1], bis: TYP_ZEIT[2], art: "unten", html: '<div class="zeile">' + sym("lila", "2") + h("Langer Docht oben") + '</div><p>Der Preis war oben – <b>Verkäufer</b> haben ihn wieder runtergedrückt.</p>' },
    { von: TYP_ZEIT[2], bis: TYP_ZEIT[3], art: "unten", html: '<div class="zeile">' + sym("chrom", "3") + h("Langer Docht unten") + '</div><p>Der Preis war unten – <b>Käufer</b> haben ihn wieder hochgekauft.</p>' },
    { von: TYP_ZEIT[3], bis: 418, art: "unten", html: '<div class="zeile">' + sym("lila", "4") + h("Winziger Körper") + '</div><p><b>Unentschieden</b> – keine Seite hat gewonnen.</p>' }
  ];
  var r = .5;
  var tags = [
    { von: 100, bis: 172, ort: v(-40 + r, ya(108), 0), text: "Hoch", farbe: F.GRAU },
    { von: 108, bis: 172, ort: v(-40 + r, ya(106), .45), text: "Schluss", farbe: F.SILBER },
    { von: 116, bis: 172, ort: v(-40 + r, ya(100), .45), text: "Eröffnung", farbe: F.SILBER },
    { von: 124, bis: 172, ort: v(-40 + r, ya(98), 0), text: "Tief", farbe: F.GRAU },
    { von: 136, bis: 172, ort: v(-40 - r, ya(103), .45), text: "Körper", farbe: F.LILA_HELL, links: true },
    { von: 144, bis: 172, ort: v(-40 - .1, ya(107), 0), text: "Docht", farbe: F.LILA_HELL, links: true },
    { von: 200, bis: 244, ort: v(-38.5 + r, yb(106), .45), text: "Eröffnung", farbe: F.LILA_HELL },
    { von: 208, bis: 244, ort: v(-38.5 + r, yb(101), .45), text: "Schluss", farbe: F.LILA_HELL },
    { von: TYP_ZEIT[0] + 4, bis: TYP_ZEIT[1], ort: v(TX[0], typ.y0 + (107.1 - 98) * .3 + .15, 0), text: "Stark", farbe: F.SILBER, mitte: true },
    { von: TYP_ZEIT[1] + 4, bis: TYP_ZEIT[2], ort: v(TX[1], typ.y0 + (107 - 98) * .3 + .15, 0), text: "Ablehnung oben", farbe: F.LILA_HELL, mitte: true },
    { von: TYP_ZEIT[2] + 4, bis: TYP_ZEIT[3], ort: v(TX[2], typ.y0 + (106.1 - 98) * .3 + .15, 0), text: "Ablehnung unten", farbe: F.SILBER, mitte: true },
    { von: TYP_ZEIT[3] + 4, bis: 418, ort: v(TX[3], typ.y0 + (105.2 - 98) * .3 + .15, 0), text: "Unentschieden", farbe: F.LILA_HELL, mitte: true }
  ];
  var keys = [
    [0,   v(-38.7, 2.7, 6.6),  v(-39.85, 2.15, 0)],
    [92,  v(-39.1, 2.45, 7.2), v(-39.75, 2.1, 0)],
    [172, v(-39.5, 2.35, 7.7), v(-39.65, 2.1, 0)],
    [202, v(-38.6, 2.6, 9.6),  v(-39.15, 2.1, 0), "f", .8],
    [244, v(-39.5, 2.45, 9.2), v(-39.2, 2.1, 0)],
    [266, v(-30, 2.7, 13.6),   v(-30, 1.8, 0), "f"],
    [418, v(-30.1, 2.55, 13.0), v(-30, 1.8, 0)]
  ];
  E.ereignis(12, "kerze"); E.ereignis(182, "kerze");
  [0, 1, 2, 3].forEach(function(i){ E.ereignis(262 + i * 4, "kerze"); });

  return {
    ende: ENDE, karten: karten, tags: tags, keys: keys,
    update: function(b){
      A.stelle(sp(b, 12, 52));
      Bk.stelle(sp(b, 182, 206));
      T.forEach(function(k, i){ k.stelle(sp(b, 262 + i * 4, 284 + i * 4)); });
      T.forEach(function(k, i){
        var a = Math.min(sp(b, TYP_ZEIT[i], TYP_ZEIT[i] + 8), 1 - sp(b, (TYP_ZEIT[i + 1] || 418) - 6, TYP_ZEIT[i + 1] || 418));
        k.leuchte(E.weich(a));
      });
      A.leuchte(E.weich(Math.min(sp(b, 128, 140), 1 - sp(b, 160, 172))) * .6);
    }
  };
};
