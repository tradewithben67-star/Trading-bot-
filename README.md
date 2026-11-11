# BENGX

Statische Website für **BENGX** — Ben, regelbasierter Handel, Gold und der XAU Bot.
Eine Datei, kein Build, keine Abhängigkeiten.

## Aufbau

Links steht der Name **BENGX** als Buchstabenleiste. Jeder Buchstabe öffnet einen Abschnitt —
per Klick oder indem man den Buchstaben auf der Tastatur drückt:

| Taste | Abschnitt | Inhalt |
| --- | --- | --- |
| **B** | Ben | Über mich und das Vorstellungsvideo |
| **E** | Entdecken | Lernen: Grundlagen, Risiko, Praxis |
| **N** | Neue Mitglieder | Einstieg in drei Schritten |
| **G** | Gold | Der Markt XAU/USD |
| **X** | XAU Bot | Der Bot, der Gold nach Regeln handelt |

Jeder Abschnitt hat eine eigene Adresse (`#ben`, `#entdecken`, `#mitglieder`, `#gold`, `#xaubot`),
lässt sich also direkt verlinken. Mit den Pfeiltasten blättert man durch die Abschnitte,
unten rechts führt eine Weiter-Zeile zum nächsten.

## Dateien

| Datei | Zweck |
| --- | --- |
| `index.html` | Die komplette Seite: Markup, CSS und JavaScript inline |
| `media/` | Mediendateien, u. a. das Vorstellungsvideo |

## Lokal ansehen

```bash
python3 -m http.server 8000
# danach http://localhost:8000 öffnen
```

## Veröffentlichen über GitHub Pages

1. **Settings → Pages** öffnen.
2. Unter *Build and deployment* als Quelle **Deploy from a branch** wählen.
3. Branch wählen, Ordner `/ (root)`, dann **Save**.

Die Seite liegt danach unter `https://<benutzername>.github.io/<repository>/`.
Für eine eigene Domain eine Datei `CNAME` mit der Domain ins Wurzelverzeichnis legen.

## Gestaltung

Schwarz als Grund, Chrom und Gold als einzige Farben. Alle Werte stehen als Tokens
im `:root`-Block oben im `<style>`:

* `--chrome` — der Silberverlauf für Buchstaben und Überschriften
* `--gilt` — der Goldverlauf für den aktiven Buchstaben, „Gold“ und „XAU Bot“
* `--gold` — der Goldton für Beschriftungen, Rahmen und Schaltflächen
* `--fg`, `--fg-dim`, `--line` — Text und Linien

Der Hintergrund (`.bg`) liegt in sieben Schichten übereinander, ohne eine einzige Bilddatei:

| Schicht | Was sie macht |
| --- | --- |
| `.bg__grid` | feines Raster, zu den Rändern hin ausgeblendet |
| `.bg__glow--gold` | goldenes Licht oben links, wandert langsam |
| `.bg__glow--steel` | kühles Licht unten rechts, wandert gegenläufig |
| `.bg__sheen` | schräger Chromschimmer, zieht langsam durchs Bild |
| `.bg__dust` | feiner Gold- und Silberstaub auf einem Canvas |
| `.bg__grain` | Korn als SVG-Rauschen |
| `.bg__vig` | Vignette, die die Ränder abdunkelt |

Alle Bewegungen stehen still, sobald das Gerät auf „weniger Bewegung" steht, und der
Staub pausiert, wenn der Tab im Hintergrund liegt. Die Anzahl der Staubkörner richtet
sich nach der Fenstergröße.

## Noch einzutragen

Alle offenen Stellen stehen auf der Seite in Gold und eckigen Klammern,
z. B. `[Jahr]`, `[Ort]`, `[dein Handle]`. Im Quelltext findest du sie über die
Klasse `ph`:

```bash
grep -n 'class="ph"' index.html
```

Dazu kommen: die echte E-Mail-Adresse (`hallo@bengx.de` ist ein Platzhalter),
das Vorstellungsvideo unter `media/ben-vorstellung.mp4` sowie die Funktionen
von Entdecken, Neue Mitglieder und XAU Bot.

## Hinweis

Die Seite ist keine Anlageberatung. Handel mit Gold, Hebelprodukten und Kryptowerten
kann zum Totalverlust führen.
