/* Sieben Filme zur Marktstruktur. Alles haengt allein an der Bildnummer. */
(function(){
"use strict";
var T = window.__werkzeug, K = window.__kerzen;
var W = T.W, H = T.H, g = T.g;
var sanft = T.sanft, sp = T.spanne, txt = T.schrift, lin = T.linie;
var rahmen = T.rahmen, titel = T.titel, abspann = T.abspann, f = T.f;
var chart = K.chart, pegel = K.pegel, zone = K.zone, pfeil = K.pfeil, satz = K.satz;
var leuchte = K.leuchte, fen = T.fenster, schild = T.schildchen;

var BLAU = "#7FB2FF", LILA = "#C39BFF";

function film(name, kapitel, nummer, kurse, opt, male){
  window.__szenen[name] = function(b){
    if (titel(b, opt.gross, opt.klein, 80)) return;
    rahmen(kapitel, nummer);
    var ch = chart(kurse, opt.chart || {});
    var wachsen = sp(b, 85, 85 + kurse.length * 11);
    ch.bis(Math.min(kurse.length, wachsen * kurse.length), 1);
    male(b, ch);
    abspann(b, opt.ende || 540, opt.schluss);
  };
}

/* ============ 04 Liquiditaet ============ */
film("liquiditaet", "Liquidität", "04", [
  [100,103,99,102],[102,105,101,104],[104,108,103,107],[107,112,106,111],
  [111,120,110,119],[119,120,114,115],[115,120,113,119],[119,120,116,117],
  [117,119,112,114],[114,120,113,119],
  [119,126,118,116],
  [116,117,110,111],[111,113,106,107]
], {
  gross: "Liquidität", klein: "Wo die Stopps der anderen liegen",
  schluss: "Erst der Griff, dann die Bewegung.", ende: 545
}, function(b, ch){
  var a1 = sanft(sp(b, 240, 285));
  pegel(ch, 120, "Gleiche Hochs", T.GOLD, a1, true);
  satz("Vier Mal derselbe Widerstand. Darüber liegen die Stopps.", fen(b, 250, 370));

  var a2 = sanft(sp(b, 300, 340));
  zone(ch, 4, 12, 126, 120, "rgba(239,196,94,.14)", "rgba(239,196,94,.45)", a2, "Liquidität");

  var a3 = sanft(sp(b, 370, 400));
  leuchte(ch, 10, T.ROT, a3);
  satz("Der Kurs greift darüber, holt sie ab —", fen(b, 382, 545));
  satz("und schließt wieder darunter. Das ist der Sweep.", fen(b, 428, 545), true);

  var a4 = sanft(sp(b, 455, 490));
  pfeil(ch.x(10), ch.y(126) - 26, ch.x(10), ch.y(126) - 6, T.ROT, a4);
});

/* ============ 05 BOS ============ */
film("bos", "Break of Structure", "05", [
  [100,104,99,103],[103,106,101,105],[105,110,104,109],
  [109,110,104,105],[105,107,102,103],
  [103,108,102,107],[107,112,106,111],
  [111,115,110,114],[114,118,113,117]
], {
  gross: "BOS", klein: "Break of Structure — der Trend geht weiter",
  schluss: "BOS heißt: der Trend bleibt.", ende: 530
}, function(b, ch){
  var a1 = sanft(sp(b, 230, 270));
  pegel(ch, 110, "Letztes Hoch", BLAU, a1, true);
  satz("Der Markt steigt: höhere Hochs, höhere Tiefs.", fen(b, 235, 355));

  var a2 = sanft(sp(b, 300, 330));
  if (a2 > 0){
    txt("höheres Tief", ch.x(4), ch.y(102) + 28, f(T.DATEN, 13), T.DIM, "center", a2);
  }

  var a3 = sanft(sp(b, 360, 395));
  leuchte(ch, 6, T.GRUEN, a3);
  satz("Dieses Hoch wird mit einem Schluss überboten —", fen(b, 365, 530));
  satz("das ist der Bruch der Struktur.", fen(b, 408, 530), true);

  var a4 = sanft(sp(b, 420, 455));
  if (a4 > 0) schild("BOS", ch.x(6) - 22, ch.y(110) - 40, f(T.ANZEIGE, 26), T.GRUEN, a4);
});

/* ============ 06 CHoCH ============ */
film("choch", "Change of Character", "06", [
  [100,104,99,103],[103,108,102,107],[107,112,106,111],
  [111,112,106,107],
  [107,111,106,110],[110,113,108,109],
  [109,110,104,105],
  [105,106,100,101],[101,103,97,98]
], {
  gross: "CHoCH", klein: "Change of Character — der Trend dreht",
  schluss: "CHoCH heißt: die Richtung hat sich geändert.", ende: 530
}, function(b, ch){
  var a1 = sanft(sp(b, 230, 270));
  pegel(ch, 106, "Letztes höheres Tief", LILA, a1, true);
  satz("Noch steigt der Markt — höhere Hochs, höhere Tiefs.", fen(b, 235, 345));

  var a2 = sanft(sp(b, 350, 385));
  leuchte(ch, 6, LILA, a2);
  satz("Dann fällt der Schluss unter das letzte höhere Tief.", fen(b, 355, 530));
  satz("Nicht nur eine Delle — der Charakter hat gewechselt.", fen(b, 408, 530), true);

  var a3 = sanft(sp(b, 405, 440));
  if (a3 > 0) schild("CHoCH", ch.x(6) - 44, ch.y(106) + 56, f(T.ANZEIGE, 26), LILA, a3);
  var a4 = sanft(sp(b, 455, 495));
  pfeil(ch.x(7), ch.y(104), ch.x(8), ch.y(98), T.ROT, a4);
});

/* ============ 07 FVG ============ */
film("fvg", "Fair Value Gap", "07", [
  [100,102,99,101],[101,110,101,109],[109,112,105,111],
  [111,113,108,109],[109,110,104,106],
  [106,112,105,111],[111,116,110,115]
], {
  gross: "FVG", klein: "Fair Value Gap — die Lücke im Kurs",
  schluss: "Der Markt holt sich die Lücke zurück.", ende: 530
}, function(b, ch){
  var a1 = sanft(sp(b, 210, 250));
  if (a1 > 0){
    leuchte(ch, 1, T.GRUEN, a1 * .7);
    txt("eine schnelle Kerze", ch.x(1), ch.o - 16, f(T.DATEN, 13), T.DIM, "center", a1);
  }
  satz("Drei Kerzen. Die mittlere läuft weg.", fen(b, 215, 285));

  var a2 = sanft(sp(b, 280, 330));
  zone(ch, 1, 6, 105, 102, "rgba(85,214,166,.16)", "rgba(85,214,166,.5)", a2, "Fair Value Gap");
  satz("Zwischen dem Hoch der ersten und dem Tief der dritten", fen(b, 292, 400));
  satz("bleibt ein Bereich, in dem gar nicht gehandelt wurde.", fen(b, 330, 400), true);

  var a3 = sanft(sp(b, 400, 440));
  if (a3 > 0){
    leuchte(ch, 4, T.GOLD, a3 * .6);
    pfeil(ch.x(4), ch.y(112), ch.x(4), ch.y(105), T.GOLD, a3);
    txt("Rücklauf", ch.x(4), ch.y(113) - 12, f(T.DATEN, 13), T.GOLD, "center", a3);
  }
  var a4 = sanft(sp(b, 460, 500));
  pfeil(ch.x(5), ch.y(106), ch.x(6), ch.y(115), T.GRUEN, a4);
});

/* ============ 08 IFVG ============ */
film("ifvg", "Inversed FVG", "08", [
  [100,102,99,101],[101,110,101,109],[109,112,105,111],
  [111,112,107,108],[108,109,103,104],
  [104,105,99,100],
  [100,104,99,103],[103,105,101,102],
  [102,103,97,98],[98,100,94,95]
], {
  gross: "IFVG", klein: "Wenn die Lücke die Seite wechselt",
  schluss: "Gebrochene Unterstützung wird Widerstand.", ende: 560
}, function(b, ch){
  var a1 = fen(b, 230, 395, 34);
  zone(ch, 1, 4, 105, 102, "rgba(85,214,166,.16)", "rgba(85,214,166,.5)", a1, "FVG");
  satz("Erst eine ganz normale Lücke nach oben.", fen(b, 235, 310));

  var a2 = sanft(sp(b, 310, 350));
  leuchte(ch, 5, T.ROT, a2);
  satz("Dann schließt der Kurs komplett darunter.", fen(b, 318, 375));

  var a3 = sanft(sp(b, 370, 415));
  zone(ch, 1, 9, 105, 102, "rgba(255,142,126,.17)", "rgba(255,142,126,.55)", a3, "IFVG");
  satz("Damit dreht sie: was getragen hat, drückt jetzt.", fen(b, 382, 560));

  satz("Von unten kommt der Kurs zurück — und prallt ab.", fen(b, 440, 560), true);
  var a4 = sanft(sp(b, 450, 495));
  if (a4 > 0){
    pfeil(ch.x(7), ch.y(99), ch.x(7), ch.y(104), T.ROT, a4);
    txt("abgewiesen", ch.x(7), ch.y(98) - 10, f(T.DATEN, 13), T.ROT, "center", a4);
  }
});

/* ============ 09 Order Block ============ */
film("orderblock", "Order Block", "09", [
  [106,107,104,105],[105,106,102,103],
  [103,112,102,111],[111,116,110,115],
  [115,116,111,112],[112,113,106,107],
  [107,113,105,112],[112,118,111,117]
], {
  gross: "Order Block", klein: "Die letzte Kerze vor der Bewegung",
  schluss: "Dort ist der Markt gedreht — dort schaut er wieder hin.", ende: 545
}, function(b, ch){
  var a1 = sanft(sp(b, 215, 255));
  leuchte(ch, 1, T.ROT, a1 * .55);
  satz("Die letzte fallende Kerze, bevor es nach oben geht.", fen(b, 220, 285));

  var a2 = sanft(sp(b, 285, 330));
  zone(ch, 1, 7, 105, 103, "rgba(239,196,94,.16)", "rgba(239,196,94,.5)", a2, null);
  if (a2 > 0.6) schild("Order Block", ch.links(2) + 6, ch.y(103) + 26, f(T.DATEN, 14), T.GOLD, (a2 - 0.6) / 0.4);
  satz("Ihr Körper bleibt als Bereich stehen.", fen(b, 295, 545));

  var a3 = sanft(sp(b, 370, 410));
  pfeil(ch.x(5), ch.y(113), ch.x(5), ch.y(106), T.GOLD, a3);

  var a4 = sanft(sp(b, 430, 475));
  if (a4 > 0){
    pfeil(ch.x(6), ch.y(105), ch.x(7), ch.y(117), T.GRUEN, a4);
    txt("Reaktion", ch.x(7), ch.y(118) - 14, f(T.DATEN, 13), T.GRUEN, "center", a4);
  }
});

/* ============ 10 Supply & Demand ============ */
film("angebot", "Angebot und Nachfrage", "10", [
  [100,101,98,99],[99,108,99,107],
  [107,113,106,112],[112,118,111,117],
  [117,118,112,113],[113,114,108,109],
  [109,110,104,105],[105,106,100,101],
  [101,107,100,106],[106,112,105,111]
], {
  gross: "Angebot und Nachfrage", klein: "Wo der Kurs schnell weggelaufen ist",
  schluss: "Wo es schnell ging, ist jemand groß eingestiegen.", ende: 560
}, function(b, ch){
  var a1 = sanft(sp(b, 230, 275));
  zone(ch, 0, 9, 100, 98, "rgba(85,214,166,.15)", "rgba(85,214,166,.5)", a1, "Nachfrage");
  satz("Von hier ist der Kurs in einem Zug nach oben gelaufen.", fen(b, 235, 320));

  var a2 = sanft(sp(b, 320, 365));
  zone(ch, 3, 9, 118, 116, "rgba(255,142,126,.15)", "rgba(255,142,126,.5)", a2, "Angebot");
  satz("Und von dort genauso schnell wieder nach unten.", fen(b, 330, 400));

  satz("Kommt er zurück, trifft er auf dieselben Aufträge.", fen(b, 410, 560), true);
  var a3 = sanft(sp(b, 400, 445));
  pfeil(ch.x(7), ch.y(106), ch.x(7), ch.y(100), T.GRUEN, a3);

  var a4 = sanft(sp(b, 465, 510));
  if (a4 > 0){
    pfeil(ch.x(8), ch.y(101), ch.x(9), ch.y(111), T.GRUEN, a4);
    txt("der Markt kommt zurück und reagiert", ch.x(6), ch.o - 16,
        f(T.DATEN, 13), T.DIM, "center", a4);
  }
});
})();
