/* Die drei Erklaerfilme fuer "Lernen, Schritt fuer Schritt".
   Alles haengt allein an der Bildnummer. */
(function(){
"use strict";
var T = window.__werkzeug, K = window.__kerzen;
var W = T.W, H = T.H, g = T.g;
var klar = T.klar, sanft = T.sanft, sp = T.spanne, txt = T.schrift;
var lin = T.linie, box = T.kasten, rahmen = T.rahmen, titel = T.titel;
var abspann = T.abspann, f = T.f;

/* ============ 01 Grundlagen ============ */
window.__szenen["grundlagen"] = function(b){
  if (titel(b, "Grundlagen", "Was eine Kerze dir sagt", 90)) return;
  rahmen("Grundlagen", "01");
  var kurse = K.KURSE, n = kurse.length;
  var l = 120, r = W - 120, o = 150, u = H - 150;
  var min = 95, max = 128;
  var skala = function(p){ return u - (p - min) / (max - min) * (u - o); };
  var breite = (r - l) / n;

  /* 90-230: Die Linie laeuft durch. Ein Chart ist erst einmal nur das. */
  if (b < 240){
    var t = sanft(sp(b, 95, 215));
    var bis = t * (n - 1);
    g.save(); g.strokeStyle = T.GOLD; g.lineWidth = 2.4; g.beginPath();
    for (var i = 0; i <= Math.floor(bis); i++){
      var x = l + i * breite + breite / 2, y = skala(kurse[i][3]);
      if (i === 0) g.moveTo(x, y); else g.lineTo(x, y);
    }
    var fr = bis - Math.floor(bis), j = Math.floor(bis);
    if (j < n - 1){
      var x1 = l + j * breite + breite / 2, y1 = skala(kurse[j][3]);
      var x2 = l + (j + 1) * breite + breite / 2, y2 = skala(kurse[j + 1][3]);
      g.lineTo(x1 + (x2 - x1) * fr, y1 + (y2 - y1) * fr);
    }
    g.stroke(); g.restore();
    txt("Der Kurs von Gold, Stunde für Stunde.", l, o - 28, f(T.TEXT, 20), T.MID, "left", sanft(sp(b, 100, 130)));
    return;
  }

  /* 240-330: Aus der Linie werden Kerzen. */
  if (b < 360){
    var t2 = sanft(sp(b, 245, 330));
    for (var i2 = 0; i2 < n; i2++){
      var kk = kurse[i2];
      var x3 = l + i2 * breite + breite * .18;
      K.kerze(x3, breite * .64, kk[0], kk[1], kk[2], kk[3], skala, t2);
    }
    g.save(); g.globalAlpha = 1 - t2;
    g.strokeStyle = T.GOLD; g.lineWidth = 2.4; g.beginPath();
    for (var i3 = 0; i3 < n; i3++){
      var x4 = l + i3 * breite + breite / 2, y4 = skala(kurse[i3][3]);
      if (i3 === 0) g.moveTo(x4, y4); else g.lineTo(x4, y4);
    }
    g.stroke(); g.restore();
    txt("Jeder Punkt ist in Wahrheit eine Kerze.", l, o - 28, f(T.TEXT, 20), T.MID, "left", sanft(sp(b, 250, 280)));
    return;
  }

  /* 360-640: Eine Kerze gross, beschriftet. */
  if (b < 660){
    var e = sanft(sp(b, 365, 410));
    var o2 = 112, h2 = 126, l2 = 104, s2 = 122;
    var mx = 330, mb = 120;
    var sk2 = function(p){ return 560 - (p - 100) / 30 * 360; };
    for (var i4 = 0; i4 < n; i4++){
      var kk2 = kurse[i4];
      var x5 = l + i4 * breite + breite * .18;
      K.kerze(x5, breite * .64, kk2[0], kk2[1], kk2[2], kk2[3], skala, (1 - e) * .5);
    }
    g.save(); g.globalAlpha = e;
    K.kerze(mx, mb, o2, h2, l2, s2, sk2, 1);
    g.restore();

    var pfeile = [
      [430, "Hoch",      sk2(h2), "Der höchste Kurs in dieser Stunde."],
      [500, "Schluss",   sk2(s2), "Wo die Stunde geendet hat."],
      [570, "Eröffnung", sk2(o2), "Wo sie begonnen hat."],
      [630, "Tief",      sk2(l2), "Der tiefste Kurs in dieser Stunde."]
    ];
    for (var p = 0; p < pfeile.length; p++){
      var a2 = sanft(sp(b, pfeile[p][0], pfeile[p][0] + 26));
      if (a2 <= 0) continue;
      var yy = pfeile[p][2];
      lin(mx + mb + 10, yy, mx + mb + 60 + 90 * a2, yy, T.GOLD_D, 1, a2 * .9);
      txt(pfeile[p][1], mx + mb + 164, yy - 6, f(T.DATEN, 16), T.GOLD, "left", a2);
      txt(pfeile[p][3], mx + mb + 164, yy + 18, f(T.TEXT, 16), T.MID, "left", a2 * .9);
    }
    var ag = sanft(sp(b, 596, 626));
    if (ag > 0){
      txt("Grün: der Schluss liegt über der Eröffnung.", 120, H - 110, f(T.TEXT, 18), T.GRUEN, "left", ag);
      txt("Rot: darunter.", 620, H - 110, f(T.TEXT, 18), T.ROT, "left", ag);
    }
    return;
  }

  /* 660-780: Zurueck zum ganzen Bild. */
  for (var i5 = 0; i5 < n; i5++){
    var kk3 = kurse[i5];
    var x6 = l + i5 * breite + breite * .18;
    K.kerze(x6, breite * .64, kk3[0], kk3[1], kk3[2], kk3[3], skala, sanft(sp(b, 665, 700)));
  }
  txt("Mehr ist ein Chart nicht: viele solcher Kerzen nebeneinander.",
      l, o - 28, f(T.TEXT, 20), T.MID, "left", sanft(sp(b, 670, 700)));
  abspann(b, 760, "Lies die Kerze, bevor du handelst.");
};

/* ============ 02 Risiko ============ */
window.__szenen["risiko"] = function(b){
  if (titel(b, "Risiko", "Wie groß du handeln darfst", 90)) return;
  rahmen("Risiko", "02");
  var l = 120;

  /* Konto */
  var a1 = sanft(sp(b, 95, 130));
  txt("Dein Konto", l, 170, f(T.DATEN, 14), T.DIM, "left", a1);
  txt("10.000 EUR", l, 222, f(T.ANZEIGE, 50), T.FG, "left", a1);
  box(l, 250, (W - 240) * a1, 26, 6, "rgba(255,255,255,.07)", T.LINIE, 1);

  /* Ein Prozent */
  var a2 = sanft(sp(b, 150, 200));
  if (a2 > 0){
    box(l, 250, (W - 240) * .01 * 14 * a2, 26, 6, "rgba(239,196,94,.5)", null, 1);
    txt("1 % = 100 EUR. Mehr riskierst du in keinem Trade.",
        l, 316, f(T.TEXT, 21), T.MID, "left", a2);
  }

  /* Rechnung */
  var zeilen = [
    [240, "Einstieg", "4.000,00"],
    [275, "Stop",     "3.990,00"],
    [310, "Abstand",  "10,00 USD"],
    [360, "Größe",    "0,10 Lot"]
  ];
  for (var i = 0; i < zeilen.length; i++){
    var a3 = sanft(sp(b, zeilen[i][0], zeilen[i][0] + 24));
    if (a3 <= 0) continue;
    var y = 400 + i * 46;
    var gold = i === 3;
    txt(zeilen[i][1], l, y, f(T.DATEN, 15), gold ? T.GOLD : T.DIM, "left", a3);
    txt(zeilen[i][2], l + 230, y, f(T.DATEN, gold ? 22 : 18),
        gold ? T.GOLD : T.FG, "right", a3);
    lin(l, y + 14, l + 230, y + 14, T.LINIE, 1, a3 * .7);
  }
  var a4 = sanft(sp(b, 396, 430));
  if (a4 > 0){
    txt("Bei 0,10 Lot kostet 1 USD Bewegung 10 EUR.", l + 300, 446, f(T.TEXT, 19), T.MID, "left", a4);
    txt("10 USD Stop × 10 EUR = 100 EUR. Genau dein 1 %.", l + 300, 476, f(T.TEXT, 19), T.FG, "left", a4);
  }

  /* Fuenf Verluste: 1 % gegen 5 % */
  if (b >= 470){
    var a5 = sanft(sp(b, 470, 505));
    g.save(); g.globalAlpha = a5;
    g.fillStyle = "#000"; g.fillRect(0, 96, W, H - 162);
    g.restore();
    txt("Fünf Verluste hintereinander", l, 190, f(T.ANZEIGE, 36), T.FG, "left", a5);
    txt("Das passiert. Die Frage ist nur, was danach noch da ist.",
        l, 226, f(T.TEXT, 19), T.MID, "left", a5);

    var stand = Math.min(5, Math.floor(sp(b, 520, 700) * 6));
    var faelle = [[0.01, "1 % je Trade", T.GRUEN], [0.05, "5 % je Trade", T.ROT]];
    for (var ff = 0; ff < 2; ff++){
      var kap = 10000;
      for (var v = 0; v < stand; v++) kap *= (1 - faelle[ff][0]);
      var yy = 300 + ff * 130;
      txt(faelle[ff][1], l, yy, f(T.DATEN, 15), T.DIM, "left", a5);
      var voll = W - 240;
      box(l, yy + 16, voll, 34, 6, "rgba(255,255,255,.05)", T.LINIE, a5);
      box(l, yy + 16, voll * (kap / 10000), 34, 6,
          ff ? "rgba(255,142,126,.42)" : "rgba(85,214,166,.38)", null, a5);
      txt(Math.round(kap).toLocaleString("de-DE") + " EUR",
          l + voll, yy + 2, f(T.DATEN, 20), faelle[ff][2], "right", a5);
    }
    txt("Nach fünf Verlusten: " + (stand >= 5 ? "9.510 gegen 7.738 EUR." : "…"),
        l, 580, f(T.TEXT, 20), T.MID, "left", sanft(sp(b, 690, 720)));
  }
  abspann(b, 760, "Der Stop steht vor dem Einstieg fest.");
};

/* ============ 03 Praxis ============ */
window.__szenen["praxis"] = function(b){
  if (titel(b, "Praxis", "Papierkonto, Protokoll, Auswertung", 90)) return;
  rahmen("Praxis", "03");
  var l = 120;
  var trades = [
    ["Mo", "Long",  "+42",  1], ["Mo", "Short", "-18",  0],
    ["Di", "Long",  "+67",  1], ["Mi", "Long",  "-23",  0],
    ["Mi", "Short", "+31",  1], ["Do", "Short", "-19",  0],
    ["Do", "Long",  "+58",  1], ["Fr", "Long",  "+24",  1]
  ];
  txt("Jeder Trade wird aufgeschrieben — auch die schlechten.",
      l, 150, f(T.TEXT, 20), T.MID, "left", sanft(sp(b, 95, 130)));

  var kopf = sanft(sp(b, 120, 150));
  var sp1 = l, sp2 = l + 110, sp3 = l + 260, sp4 = l + 400;
  txt("Tag", sp1, 200, f(T.DATEN, 13), T.DIM, "left", kopf);
  txt("Richtung", sp2, 200, f(T.DATEN, 13), T.DIM, "left", kopf);
  txt("Pips", sp3, 200, f(T.DATEN, 13), T.DIM, "right", kopf);
  txt("Ergebnis", sp4, 200, f(T.DATEN, 13), T.DIM, "right", kopf);
  lin(l, 212, sp4 + 20, 212, T.LINIE, 1, kopf);

  var gezeigt = 0, summe = 0, siege = 0;
  for (var i = 0; i < trades.length; i++){
    var ab = 170 + i * 42;
    var a = sanft(sp(b, ab, ab + 22));
    if (a <= 0) continue;
    gezeigt = i + 1;
    summe += parseInt(trades[i][2], 10);
    siege += trades[i][3];
    var y = 248 + i * 36;
    var farbe = trades[i][3] ? T.GRUEN : T.ROT;
    txt(trades[i][0], sp1, y, f(T.DATEN, 16), T.MID, "left", a);
    txt(trades[i][1], sp2, y, f(T.DATEN, 16), T.FG, "left", a);
    txt(trades[i][2], sp3, y, f(T.DATEN, 16), farbe, "right", a);
    txt(trades[i][3] ? "Ziel" : "Stop", sp4, y, f(T.DATEN, 16), T.DIM, "right", a);
    lin(l, y + 12, sp4 + 20, y + 12, T.LINIE, 1, a * .5);
  }

  /* Kurve rechts */
  var kx = 700, kb = W - 820, ky = 250, kh = 260;
  var ak = sanft(sp(b, 200, 240));
  if (ak > 0){
    txt("Kapitalkurve", kx, 200, f(T.DATEN, 13), T.DIM, "left", ak);
    lin(kx, ky + kh, kx + kb, ky + kh, T.LINIE, 1, ak);
    var lauf = 0, punkte = [[kx, ky + kh - 40]];
    for (var p = 0; p < gezeigt; p++){
      lauf += parseInt(trades[p][2], 10);
      punkte.push([kx + (p + 1) / trades.length * kb, ky + kh - 40 - lauf * .9]);
    }
    if (punkte.length > 1){
      g.save(); g.globalAlpha = ak;
      g.strokeStyle = T.GOLD; g.lineWidth = 2.4; g.beginPath();
      for (var q = 0; q < punkte.length; q++){
        if (q === 0) g.moveTo(punkte[q][0], punkte[q][1]);
        else g.lineTo(punkte[q][0], punkte[q][1]);
      }
      g.stroke();
      g.lineTo(punkte[punkte.length - 1][0], ky + kh);
      g.lineTo(kx, ky + kh); g.closePath();
      g.fillStyle = "rgba(239,196,94,.1)"; g.fill();
      g.restore();
    }
  }

  /* Kennzahlen */
  var az = sanft(sp(b, 520, 560));
  if (az > 0 && gezeigt > 0){
    var kacheln = [
      ["Trades", String(gezeigt)],
      ["Winrate", Math.round(siege / gezeigt * 100) + " %"],
      ["Pips", (summe >= 0 ? "+" : "") + summe]
    ];
    for (var kk = 0; kk < 3; kk++){
      var bx = kx + kk * ((kb + 20) / 3), bw = (kb + 20) / 3 - 14;
      box(bx, 560, bw, 92, 12, "rgba(10,10,12,.7)", T.LINIE, az);
      txt(kacheln[kk][0], bx + 16, 588, f(T.DATEN, 12), T.DIM, "left", az);
      txt(kacheln[kk][1], bx + 16, 630, f(T.ANZEIGE, 30), T.FG, "left", az);
    }
  }
  abspann(b, 760, "Erst wenn das Protokoll stimmt, kommt echtes Geld.");
};
})();
