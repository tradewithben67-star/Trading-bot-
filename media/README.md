# media

Hier liegen die Mediendateien der Seite.

## Vorstellungsvideo

Lege dein Video als **`ben-vorstellung.mp4`** in diesen Ordner. Die Seite bindet es
automatisch ein, sobald die Datei da ist — im Abschnitt **B — Ben**.

* Format: MP4 (H.264 / AAC), damit es in allen Browsern läuft
* Seitenverhältnis: 16:9
* Größe: möglichst unter 50 MB, sonst lädt die Seite langsam

Ohne Datei zeigt der Abschnitt einen Platzhalter mit der Schaltfläche
„Video jetzt ansehen“, über die sich eine lokale Datei zur Vorschau öffnen lässt.

## TikTok-Videos (`tiktok/`)

Hochformat 9:16 (1080×1920, 60 fps) mit Ton, gebaut aus `tools/videos/welt.html`.
Design: schwarz, Lila, Chrom und Silber – schwarzer Spiegelboden mit feinem
Raster, Kerzen aus Chrom (steigt) und Lila (fällt), leuchtende Linien, Karten
aus dunklem Glas, eine durchgehende Kamerafahrt.

| Datei | Inhalt |
| --- | --- |
| `01-trading-erklaert.mp4` | Was ist Trading? Kerzen, Angebot & Nachfrage, Trend, Long/Short, Stop-Loss (32 s) |
| `02-bos.mp4` | Kerzen lesen (Aufbau, steigend/fallend, vier Kerzen-Typen), dann BOS: Docht allein reicht nicht, erst der Schluss über dem letzten Hoch (33 s) |
| `03-choch.mp4` | Kerzen lesen, dann CHoCH: kein neues Hoch, Schluss unter dem letzten höheren Tief (33 s) |

Neu bauen (rund 35–40 Minuten je Video, vier Browser nehmen parallel auf):

    node tools/videos/welt-rendern.js                                              # 01
    node tools/videos/welt-rendern.js media/tiktok/02-bos.mp4 "kerzen-film.html?film=bos"
    node tools/videos/welt-rendern.js media/tiktok/03-choch.mp4 "kerzen-film.html?film=choch"

Die Kerzen-Filme teilen sich ein Gerüst (`tools/videos/kerzen-film.html`) und
den Anfang „Kerzen lesen“ (`tools/videos/filme/kerzen-intro.js`). Ein neuer
Film ist eine Datei `tools/videos/filme/<name>.js`, aufgerufen mit `?film=<name>`.

Zum Abfilmen vom Bildschirm `tools/videos/welt.html` im Browser öffnen und auf
Vollbild stellen – die Animation läuft dort in Echtzeit in Schleife, ein Klick
startet sie von vorn.

`tools/videos/vendor/three-paket.min.js` ist three.js 0.159 samt Bloom,
Spiegelboden und abgerundeten Kästen als ein Skript; die Quelle und der
Bau-Befehl stehen in `three-paket.js` daneben.
