/* Nimmt welt.html Bild fuer Bild auf (1080x1920, 60 fps) und legt den Ton dazu.

     node tools/videos/welt-rendern.js [ziel.mp4]

   Ablauf: Die Bilder sind allein von der Bildnummer abhaengig, darum nehmen
   mehrere Browser parallel je ein Stueck auf (TEILE, Vorgabe 4). Die Stuecke
   werden ohne neues Kodieren aneinandergehaengt, ton.py baut aus der
   Ereignisliste der Szene Musik und Effekte, ffmpeg legt beides zusammen. */
const { chromium } = require('playwright');
const { spawn, execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const hier = __dirname;
const AUFNAHME_FPS = 60;
const TEILE = Number(process.env.TEILE || 4);

async function oeffnen() {
  const browser = await chromium.launch({ args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  const seite = await browser.newPage({ viewport: { width: 540, height: 960 }, deviceScaleFactor: 2 });
  const fehler = [];
  seite.on('pageerror', e => fehler.push(e.message));
  await seite.addInitScript(() => { window.__aufnahme = true; });
  await seite.goto('file://' + path.join(hier, 'welt.html'));
  await seite.waitForTimeout(1500);
  if (fehler.length) throw new Error('Seitenfehler: ' + fehler.join(' | '));
  return { browser, seite, fehler };
}

/* Ein Stueck: Bilder von..bis (Aufnahmebilder, 60 fps) in eine Datei. */
async function stueck(von, bis, datei) {
  const { browser, seite, fehler } = await oeffnen();
  const { fps } = await seite.evaluate(() => ({ fps: window.__fps }));
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(AUFNAHME_FPS), '-i', 'pipe:0',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '15', '-preset', 'slow', '-profile:v', 'high', datei]);
  let ffFehler = '';
  ff.stderr.on('data', d => { ffFehler += d; });
  const fertig = new Promise((ok, nein) => ff.on('close', c => c === 0 ? ok() : nein(new Error(ffFehler))));
  const t0 = Date.now();
  for (let i = von; i < bis; i++) {
    await seite.evaluate(n => window.zeichne(n), i * fps / AUFNAHME_FPS);
    const bild = await seite.screenshot({ type: 'png' });
    if (!ff.stdin.write(bild)) await new Promise(r => ff.stdin.once('drain', r));
    if ((i - von) % 120 === 0) console.log(`  Stück ${von}-${bis}: ${i - von}/${bis - von}  (${Math.round((Date.now() - t0) / 1000)} s)`);
  }
  ff.stdin.end();
  await fertig;
  await browser.close();
  if (fehler.length) throw new Error('Fehler waehrend der Aufnahme: ' + fehler.join(' | '));
}

async function ganz(ziel) {
  fs.mkdirSync(path.dirname(ziel), { recursive: true });
  const arbeit = ziel.replace(/\.mp4$/, '.teile');
  fs.mkdirSync(arbeit, { recursive: true });

  const { browser, seite } = await oeffnen();
  const { laenge, fps, liste } = await seite.evaluate(() => ({ laenge: window.__laenge, fps: window.__fps, liste: window.__ereignisse }));
  await browser.close();
  const ereignisse = path.join(arbeit, 'ereignisse.json'), wav = path.join(arbeit, 'ton.wav');
  fs.writeFileSync(ereignisse, JSON.stringify({ fps, laenge, ereignisse: liste }, null, 1));

  const bilder = Math.round(laenge * AUFNAHME_FPS / fps);
  const groesse = Math.ceil(bilder / TEILE);
  const dateien = [];
  const laeufe = [];
  for (let t = 0; t < TEILE; t++) {
    const von = t * groesse, bis = Math.min(bilder, von + groesse);
    if (von >= bis) break;
    const datei = path.join(arbeit, `teil${t}.mp4`);
    dateien.push(datei);
    laeufe.push(new Promise((ok, nein) => {
      const p = spawn(process.execPath, [__filename, '--stueck', String(von), String(bis), datei], { stdio: 'inherit' });
      p.on('close', c => c === 0 ? ok() : nein(new Error('Stück ' + von + ' fehlgeschlagen')));
    }));
  }
  const t0 = Date.now();
  await Promise.all(laeufe);
  console.log(`Bilder fertig in ${Math.round((Date.now() - t0) / 1000)} s`);

  const liste_ = path.join(arbeit, 'liste.txt');
  fs.writeFileSync(liste_, dateien.map(d => `file '${d}'`).join('\n'));
  const stumm = path.join(arbeit, 'stumm.mp4');
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', liste_, '-c', 'copy', stumm], { stdio: 'inherit' });
  execFileSync('python3', [path.join(hier, 'ton.py'), ereignisse, wav], { stdio: 'inherit' });
  execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', stumm, '-i', wav, '-c:v', 'copy', '-c:a', 'aac', '-b:a', '256k',
    '-shortest', '-movflags', '+faststart', ziel], { stdio: 'inherit' });
  fs.rmSync(arbeit, { recursive: true, force: true });
  console.log('fertig:', ziel);
}

const a = process.argv.slice(2);
(a[0] === '--stueck'
  ? stueck(Number(a[1]), Number(a[2]), a[3])
  : ganz(a[0] || path.join(hier, '..', '..', 'media', 'tiktok', '01-trading-erklaert.mp4'))
).catch(e => { console.error(e); process.exit(1); });
