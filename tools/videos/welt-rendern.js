/* Nimmt welt.html Bild fuer Bild auf (1080x1920, 30 fps) und legt den Ton dazu.

     node tools/videos/welt-rendern.js [ziel.mp4]

   Ablauf: Bilder ueber die Pipe in ffmpeg (stumm), Ereignisliste der Szene
   als JSON ablegen, ton.py baut daraus Musik und Effekte, ffmpeg legt beides
   zusammen. */
const { chromium } = require('playwright');
const { spawn, execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const hier = __dirname;
const ziel = process.argv[2] || path.join(hier, '..', '..', 'media', 'tiktok', '01-trading-erklaert.mp4');
const stumm = ziel.replace(/\.mp4$/, '.stumm.mp4');
const ereignisse = ziel.replace(/\.mp4$/, '.ereignisse.json');
const wav = ziel.replace(/\.mp4$/, '.wav');

(async () => {
  fs.mkdirSync(path.dirname(ziel), { recursive: true });
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const seite = await browser.newPage({ viewport: { width: 540, height: 960 }, deviceScaleFactor: 2 });
  const fehler = [];
  seite.on('pageerror', e => fehler.push(e.message));
  await seite.addInitScript(() => { window.__aufnahme = true; });
  await seite.goto('file://' + path.join(hier, 'welt.html'));
  await seite.waitForTimeout(1200);
  if (fehler.length) throw new Error('Seitenfehler: ' + fehler.join(' | '));

  const { laenge, fps, liste } = await seite.evaluate(() => ({ laenge: window.__laenge, fps: window.__fps, liste: window.__ereignisse }));
  fs.writeFileSync(ereignisse, JSON.stringify({ fps, laenge, ereignisse: liste }, null, 1));

  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-i', 'pipe:0',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '17', '-preset', 'slow', '-movflags', '+faststart', stumm]);
  let ffFehler = '';
  ff.stderr.on('data', d => { ffFehler += d; });
  const fertig = new Promise((ok, nein) => ff.on('close', c => c === 0 ? ok() : nein(new Error(ffFehler))));
  const t0 = Date.now();
  for (let b = 0; b < laenge; b++) {
    await seite.evaluate(n => window.zeichne(n), b);
    const bild = await seite.screenshot({ type: 'png' });
    if (!ff.stdin.write(bild)) await new Promise(r => ff.stdin.once('drain', r));
    if (b % 120 === 0) console.log(`  Bild ${b}/${laenge}  (${Math.round((Date.now() - t0) / 1000)} s)`);
  }
  ff.stdin.end();
  await fertig;
  await browser.close();
  if (fehler.length) console.log('Fehler waehrend der Aufnahme:', fehler);

  execFileSync('python3', [path.join(hier, 'ton.py'), ereignisse, wav], { stdio: 'inherit' });
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', stumm, '-i', wav, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k',
    '-shortest', '-movflags', '+faststart', ziel], { stdio: 'inherit' });
  [stumm, wav, ereignisse].forEach(f => fs.unlinkSync(f));
  console.log('fertig:', ziel);
})();
