# Clip-Fabrik

Macht durchgehend (alle 30 Minuten) TikTok-Clips von **18 deutschen
Streamern** (Rohat, Trymacs, Zarbex, Eligella, Papaplatte, gTasty, LetsHugo,
Gleggmire, CoachLim, MontanaBlack, NoWay, BastiGHG, HandOfBlood, Tolkin,
KrokoBoss, Nooreax, Knossi, Gronkh) und schickt sie dir per Telegram. Läuft
auf den Servern von GitHub, dein iPad muss dafür nicht an sein.

## Was passiert bei jedem Lauf

1. Für jeden Streamer werden die **meistgesehenen Twitch-Clips der letzten
   48 Stunden** geholt. Die Zuschauer haben die besten Momente damit
   schon ausgesucht.
2. Clips, die schon gemacht wurden, werden übersprungen.
3. Pro Streamer werden die **3 besten neuen** Clips geschnitten (ab 100 Aufrufen):
   - Hochformat 1080×1920 (TikTok-Format)
   - unscharfer Hintergrund, Spielbild groß in der Mitte
   - Clip-Titel groß oben
   - **automatische Untertitel** (gelb, Wort für Wort, so wie bei
     erfolgreichen Clip-Kanälen)
   - Credit `twitch.tv/<streamer>` im Bild
4. Zu jedem Video gibt es eine fertige **Beschreibung mit Hashtags**.
5. Alles landet unter **Releases** in deinem Repo, auf Wunsch auch
   direkt in **Telegram**.

## Einmal einschalten (iPad, ca. 5 Minuten)

1. **Pull Request zusammenführen.** In der GitHub-App oder auf github.com:
   Pull Requests → „Clip-Fabrik“ → *Merge*. Erst danach laufen die
   Uhrzeiten von allein, weil GitHub die Automatik nur aus dem
   Hauptzweig startet.
2. **Ersten Lauf von Hand starten:** github.com → dein Repo → **Actions**
   → „Clips machen“ → **Run workflow**. Nach etwa 5–10 Minuten ist er fertig.
3. **Clips abholen:** Repo → **Releases** → „Clips <Datum>“. Video antippen
   → laden → *In Fotos sichern* → in TikTok hochladen → Beschreibung aus
   den Release-Notizen kopieren.

### Clips per Telegram bekommen

1. In Telegram **@BotFather** öffnen → `/newbot` → Namen ausdenken
   (z. B. „Meine Clips“) → Benutzernamen, der auf `bot` endet.
   BotFather schickt dir einen **Token** (sieht aus wie `123456:ABC-...`).
2. Auf github.com: Repo → **Settings** → **Secrets and variables** →
   **Actions** → **New repository secret**
   - Name: `CLIPS_TELEGRAM_BOT_TOKEN`
   - Secret: den Token von BotFather einfügen → **Add secret**
3. In Telegram deinen neuen Bot öffnen und **Start** drücken
   (bzw. `/start` schreiben).

Beim nächsten Lauf schreibt dir der Bot „✅ Verbunden!“, danach kommt jeder
neue Clip als Video mit fertiger Beschreibung. Gefällt er dir: Video
gedrückt halten → Speichern → in TikTok posten. Sonst einfach ignorieren.

Den Token **nie** in einen Chat kopieren, nur in GitHub als Secret.

### Optional: offizielle Twitch-API

Funktioniert auch ohne. Wenn die Clip-Liste mal leer bleibt: auf
dev.twitch.tv eine App anlegen und `TWITCH_CLIENT_ID` und
`TWITCH_CLIENT_SECRET` als Secrets eintragen.

## Anpassen (`clipper/config.json`)

| Feld | Bedeutung |
|---|---|
| `streamer` | Name + Twitch-Kanal. Weitere einfach dazuschreiben. |
| `max_clips_pro_lauf` | Obergrenze pro Lauf, reihum über alle Streamer verteilt |
| `clips_pro_streamer` | wie viele neue Clips pro Streamer und Lauf (alle 30 Min.) |
| `mindest_aufrufe` | schwächere Clips werden ignoriert |
| `max_alter_stunden` | wie alt ein Clip höchstens sein darf |
| `hashtags`, `hashtags_pro_streamer` | landen in der Beschreibung |
| `untertitel` | `false` = ohne Untertitel (schneller) |

Die Uhrzeiten stehen in `.github/workflows/clips.yml` (`cron`). Weil GitHubs
Zeitplan oft verspätet oder gar nicht startet, stößt jeder Lauf zusätzlich
selbst den nächsten an (ca. 30 Minuten nach seinem Start).

**Anhalten:** Actions → „Clips machen“ → „…“ (oben rechts) → **Disable workflow**.
**Wieder starten:** dort **Enable workflow**, dann einmal **Run workflow**.

## Wichtig

Die Clips gehören den Streamern. Credit steht immer drin. Prüfe die
Clip-Regeln des jeweiligen Streamers, bevor du mit den Videos Geld
verdienst (TikTok Creator Rewards). TikTok drosselt reine Reuploads,
deshalb Titel, Untertitel und eigenes Layout.
