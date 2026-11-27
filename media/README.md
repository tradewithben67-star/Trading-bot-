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

Neu bauen (rund 30 Minuten, vier Browser nehmen parallel auf):

    node tools/videos/welt-rendern.js

Zum Abfilmen vom Bildschirm `tools/videos/welt.html` im Browser öffnen und auf
Vollbild stellen – die Animation läuft dort in Echtzeit in Schleife, ein Klick
startet sie von vorn.

`tools/videos/vendor/three-paket.min.js` ist three.js 0.159 samt Bloom,
Spiegelboden und abgerundeten Kästen als ein Skript; die Quelle und der
Bau-Befehl stehen in `three-paket.js` daneben.
