# Whop-Clips: Kriterien rein, fertige Clips raus

Du fügst die Bedingungen einer Clipping-Kampagne ein (Text und/oder Screenshots).
GitHub sucht dann selbst das Material, geht jedes Video bzw. jeden Stream durch,
sucht die besten Momente aus und schneidet die Clips genau nach den Vorgaben:
Länge, Anzahl, Format (MP4/MOV/WebM) und bei Bedarf Hochformat. Dazu kommt der
fertige Text mit den Quell-Links für Whop.

## So benutzt du es (iPhone)

1. github.com → dein Repo → **Issues** → **New issue** → **Whop-Auftrag**.
2. Ins Feld **Kriterien** den Text der Kampagne einfügen und/oder die Screenshots
   anhängen. Optional: Name, bestimmte Kanäle/Streams, Anzahl.
3. **Submit**. Nach ca. 10–20 Minuten steht im Issue ein Kommentar:
   - **Download-Link** → Clip antippen → Teilen → **In Dateien sichern**
   - darunter der **Text zum Kopieren**: die Links für das Feld „Links“ und die
     „Hinweise für Prüfer“
4. In Whop: **Bilder oder Videos hochladen** → *Durchsuchen* → Clips auswählen.
5. Andere Clips gewünscht? Im Issue `nochmal` kommentieren. Stellen, die schon
   verwendet wurden, nimmt er nicht noch einmal.

Ist Telegram für die Clip-Fabrik eingerichtet, kommen die Clips zusätzlich dort an.

## Woher die Clips kommen

| Was du angibst | Was passiert |
|---|---|
| nichts (nur Kriterien) | Suche auf YouTube nach Specials, Podcasts, Interviews der Person |
| YouTube-Kanal | die letzten Streams (sonst Videos) des Kanals |
| Twitch-Kanal | die meistgesehenen Clips der letzten 7 Tage **und** die letzten Streams |
| einzelnes Video / einzelner Stream | genau dieses |

Jedes Video wird über sein Transkript durchgesehen. YouTube liefert Untertitel und
die Kurve „am häufigsten wiederholt“ mit. Bei Twitch und Kick hört er den Ton selbst
ab (die ersten 3 Stunden eines Streams).

## Einmal einrichten

Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Name | Wofür | Nötig? |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude liest die Screenshots und sucht die lustigsten Momente aus. Ohne Schlüssel: nur Text-Kriterien, Auswahl nach Lachern im Transkript | dringend empfohlen |
| `YOUTUBE_COOKIES` | Falls YouTube die GitHub-Server blockiert („confirm you're not a bot“) | nur bei Bedarf |

Den Schlüssel bekommst du auf console.anthropic.com → *API Keys*. Ein Auftrag mit
5 Clips kostet je nach Länge der Videos ein paar Cent bis etwa 1 €.

**YouTube-Cookies** (am PC): In Chrome/Firefox die Erweiterung „Get cookies.txt
LOCALLY“ installieren, bei YouTube angemeldet sein (am besten mit einem
Zweitkonto), auf youtube.com die Erweiterung öffnen → *Export* → den ganzen Inhalt
der Datei als Secret `YOUTUBE_COOKIES` einfügen.

## Am eigenen Rechner

```bash
pip install -r clipper/requirements.txt      # dazu ffmpeg installieren
export ANTHROPIC_API_KEY=...                  # optional
python clipper/whop.py --kriterien auftrag.txt --bild screen1.png --bild screen2.png
python clipper/whop.py --person "Shane Gillis" --anzahl 5
python clipper/whop.py --person Papaplatte --quelle https://www.twitch.tv/papaplatte
```

Die Clips liegen danach in `clipper/whop_ausgabe/`, zusammen mit `einreichung.txt`
und `alle_clips.zip`. Am eigenen Rechner blockiert YouTube praktisch nie.

## Wichtig

- **Den Nachweis-Stream machst du selbst.** Viele Kampagnen (auch die mit Shane
  Gillis) verlangen eine 5-minütige Bildschirmaufnahme, in der du Material
  durchsiehst und einen Clip selbst schneidest. Das kann und soll dieses Programm
  nicht übernehmen. Prüf außerdem, ob die Kampagne Werkzeuge wie dieses erlaubt.
  Wird Handarbeit verlangt, riskierst du sonst die Auszahlung.
- Sieh dir jeden Clip vor dem Einreichen an. Die Auswahl ist gut, aber nicht unfehlbar.
- Nur öffentlich zugängliches Material, die Quelle steht immer dabei.
