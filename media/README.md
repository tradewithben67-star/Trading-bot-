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

Hochformat 9:16 (1080×1920, 30 fps) mit Ton, gebaut aus `tools/videos/welt.html`:
eine helle 3D-Stadt, durch die die Kamera ohne Schnitt fliegt, dazu Karten,
die mit Feder ins Bild springen.

| Datei | Inhalt |
| --- | --- |
| `01-trading-erklaert.mp4` | Was ist Trading? Kerzen, Angebot & Nachfrage, Trend, Long/Short, Stop-Loss (32 s) |

Neu bauen:

    node tools/videos/welt-rendern.js

Zum Abfilmen vom Bildschirm `tools/videos/welt.html` im Browser öffnen und auf
Vollbild stellen – die Animation läuft dort in Echtzeit in Schleife, ein Klick
startet sie von vorn.
