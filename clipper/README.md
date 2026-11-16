# Clip-Fabrik

Macht 4x am Tag von allein TikTok-Clips von **Rohat, Trymacs, Zarbex,
Eligella und Papaplatte**. Läuft auf den Servern von GitHub, dein iPad
muss dafür nicht an sein.

## Was passiert bei jedem Lauf

1. Für jeden Streamer werden die **meistgesehenen Twitch-Clips der letzten
   24 Stunden** geholt. Die Zuschauer haben die besten Momente damit
   schon ausgesucht.
2. Clips, die schon gemacht wurden, werden übersprungen.
3. Pro Streamer werden die **2 besten** Clips geschnitten:
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

### Optional: Clips direkt aufs iPad per Telegram

Repo → Settings → Secrets and variables → Actions → *New repository secret*:

| Name | Wert |
|---|---|
| `CLIPS_TELEGRAM_BOT_TOKEN` | Token eines Telegram-Bots (von @BotFather) |
| `CLIPS_TELEGRAM_CHAT_ID` | deine Chat-ID (z. B. von @userinfobot) |

Dann kommt jeder Clip mit Beschreibung als Nachricht. Gedrückt halten →
*Speichern* → posten.

### Optional: offizielle Twitch-API

Funktioniert auch ohne. Wenn die Clip-Liste mal leer bleibt: auf
dev.twitch.tv eine App anlegen und `TWITCH_CLIENT_ID` und
`TWITCH_CLIENT_SECRET` als Secrets eintragen.

## Anpassen (`clipper/config.json`)

| Feld | Bedeutung |
|---|---|
| `streamer` | Name + Twitch-Kanal. Weitere einfach dazuschreiben. |
| `clips_pro_streamer` | wie viele Clips pro Streamer und Lauf |
| `mindest_aufrufe` | schwächere Clips werden ignoriert |
| `hashtags`, `hashtags_pro_streamer` | landen in der Beschreibung |
| `untertitel` | `false` = ohne Untertitel (schneller) |

Die Uhrzeiten stehen in `.github/workflows/clips.yml` (`cron`).

## Wichtig

Die Clips gehören den Streamern. Credit steht immer drin. Prüfe die
Clip-Regeln des jeweiligen Streamers, bevor du mit den Videos Geld
verdienst (TikTok Creator Rewards). TikTok drosselt reine Reuploads,
deshalb Titel, Untertitel und eigenes Layout.
