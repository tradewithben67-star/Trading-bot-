# BenGx — Website

Statische Website für **BenGx**, eine Marke für regelbasierten, automatisierten Handel.
Eine einzige Datei, keine Build-Schritte, keine Abhängigkeiten.

## Inhalt

| Datei | Zweck |
| --- | --- |
| `index.html` | Die komplette Seite: Markup, CSS und JavaScript inline |
| `README.md` | Diese Datei |

Die Seite ist auf Deutsch und umfasst: Hero mit Beispiel-Positionsübersicht, laufendes Kursband,
drei Strategie-Vorlagen, ein Backtest-Protokoll mit Kapitalkurve, den vierstufigen Signalablauf,
die Risikogrenzen samt Not-Aus, drei Preispakete, ein Anfrageformular und den Risikohinweis.

## Lokal ansehen

```bash
python3 -m http.server 8000
# danach http://localhost:8000 öffnen
```

Ein Doppelklick auf `index.html` funktioniert ebenfalls.

## Veröffentlichen über GitHub Pages

1. Im Repository **Settings → Pages** öffnen.
2. Unter *Build and deployment* als Quelle **Deploy from a branch** wählen.
3. Branch auf den gewünschten Branch und Ordner auf `/ (root)` stellen, dann **Save**.

Die Seite ist danach unter `https://<benutzername>.github.io/<repository>/` erreichbar.
Für eine eigene Domain eine Datei `CNAME` mit der Domain im Repository-Wurzelverzeichnis anlegen.

## Anpassen

* **Farben und Schriften**: alle Werte stehen als Tokens im `:root`-Block oben im `<style>`.
  Helles Thema in `:root`, dunkles Thema in den beiden darunterliegenden Blöcken —
  beide anpassen, damit die Seite in jedem Thema stimmt.
* **Texte**: direkt im Markup, jeder Abschnitt hat eine `id` (`strategien`, `ergebnis`,
  `ablauf`, `risiko`, `preise`, `zugang`).
* **Kursband und Kapitalkurve**: die Arrays `ticks` und `eq` im `<script>` am Dateiende.
* **Formular**: `submit` wird im Browser abgefangen und zeigt nur eine Bestätigung an.
  Für echten Versand die Adresse eines Formulardienstes oder einer eigenen API eintragen.

## Hinweis zu den Zahlen

Sämtliche Kurse, Positionen und Kennzahlen sind **Demo-Daten** zur Veranschaulichung des
Berichtsformats. Sie sind keine erzielten Ergebnisse und keine Prognose. Die Seite ist
keine Anlageberatung.
