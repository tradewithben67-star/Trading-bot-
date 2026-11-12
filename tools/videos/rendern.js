/* Nimmt die Szenen Bild fuer Bild auf und schiebt sie direkt in ffmpeg.
   Ueber die Pipe, damit keine 2400 Einzelbilder auf der Platte landen. */
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');

const FPS = 30, BILDER = 800;
const SZENEN = [
  ['grundlagen', '01-grundlagen.mp4'],
  ['risiko',     '02-risiko.mp4'],
  ['praxis',     '03-praxis.mp4'],
];

async function einen(seite, name, ziel){
  await seite.evaluate(n => { window.__aktuelle = n; }, name);
  const ff = spawn('ffmpeg', [
    '-y', '-loglevel', 'error',
    '-f', 'image2pipe', '-framerate', String(FPS), '-i', 'pipe:0',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20',
    '-preset', 'medium', '-movflags', '+faststart', ziel,
  ]);
  let fehler = '';
  ff.stderr.on('data', d => { fehler += d.toString(); });
  const fertig = new Promise((ok, nein) => {
    ff.on('close', code => code === 0 ? ok() : nein(new Error(fehler || ('ffmpeg ' + code))));
  });

  for (let b = 0; b < BILDER; b++){
    await seite.evaluate(n => window.zeichne(n), b);
    const bild = await seite.screenshot({ type: 'jpeg', quality: 94 });
    if (!ff.stdin.write(bild)) await new Promise(r => ff.stdin.once('drain', r));
    if (b % 200 === 0) process.stdout.write(`  ${name}: ${b}/${BILDER}\n`);
  }
  ff.stdin.end();
  await fertig;
}

(async () => {
  const hier = __dirname;
  const ziel = process.argv[2] || path.join(hier, '..', '..', 'media');
  const browser = await chromium.launch();
  const seite = await browser.newPage({ viewport: { width: 1280, height: 720 }, deviceScaleFactor: 1 });
  const fehler = [];
  seite.on('pageerror', e => fehler.push(e.message));
  await seite.goto('file://' + path.join(hier, 'studio.html'));
  await seite.waitForTimeout(1500);           // Schriften laden lassen
  if (fehler.length) throw new Error('Seitenfehler: ' + fehler.join(' | '));

  for (const [name, datei] of SZENEN){
    const t0 = Date.now();
    await einen(seite, name, path.join(ziel, datei));
    console.log(`${datei} fertig in ${Math.round((Date.now() - t0) / 1000)} s`);
  }
  if (fehler.length) console.log('Fehler waehrend der Aufnahme:', fehler);
  await browser.close();
})();
