/* Nimmt die Szenen Bild fuer Bild auf und schiebt sie direkt in ffmpeg.
   Ueber die Pipe, damit keine 2400 Einzelbilder auf der Platte landen. */
const { chromium } = require('playwright');
const { spawn } = require('child_process');
const path = require('path');

const FPS = 30;
/* Die drei Grundlagenfilme laufen laenger, die Marktbegriffe sind kurz
   und auf einen Gedanken gebaut. */
const LANG = 800, KURZ = 620;
const SZENEN = [
  ['grundlagen',  '01-grundlagen.mp4',  LANG],
  ['risiko',      '02-risiko.mp4',      LANG],
  ['praxis',      '03-praxis.mp4',      LANG],
  ['liquiditaet', '04-liquiditaet.mp4', KURZ],
  ['bos',         '05-bos.mp4',         KURZ],
  ['choch',       '06-choch.mp4',       KURZ],
  ['fvg',         '07-fvg.mp4',         KURZ],
  ['ifvg',        '08-ifvg.mp4',        KURZ],
  ['orderblock',  '09-orderblock.mp4',  KURZ],
  ['angebot',     '10-angebot.mp4',     KURZ],
];

async function einen(seite, name, ziel, bilder){
  await seite.evaluate(n => { window.__aktuelle = n; }, name);
  const ff = spawn('ffmpeg', [
    '-y', '-loglevel', 'error',
    '-f', 'image2pipe', '-framerate', String(FPS), '-i', 'pipe:0',
    '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '17',
    '-preset', 'slow', '-movflags', '+faststart', ziel,
  ]);
  let fehler = '';
  ff.stderr.on('data', d => { fehler += d.toString(); });
  const fertig = new Promise((ok, nein) => {
    ff.on('close', code => code === 0 ? ok() : nein(new Error(fehler || ('ffmpeg ' + code))));
  });

  for (let b = 0; b < bilder; b++){
    await seite.evaluate(n => window.zeichne(n), b);
    /* Verlustfrei aufnehmen: ffmpeg soll das einzige Mal sein, das
       Bildqualitaet kostet. */
    const bild = await seite.screenshot({ type: 'png' });
    if (!ff.stdin.write(bild)) await new Promise(r => ff.stdin.once('drain', r));
    if (b % 300 === 0) process.stdout.write(`  ${name}: ${b}/${bilder}\n`);
  }
  ff.stdin.end();
  await fertig;
}

(async () => {
  const hier = __dirname;
  const ziel = process.argv[2] || path.join(hier, '..', '..', 'media');
  const browser = await chromium.launch();
  const seite = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const fehler = [];
  seite.on('pageerror', e => fehler.push(e.message));
  await seite.goto('file://' + path.join(hier, 'studio.html'));
  await seite.waitForTimeout(1500);           // Schriften laden lassen
  if (fehler.length) throw new Error('Seitenfehler: ' + fehler.join(' | '));

  const nur = process.argv[3] ? process.argv[3].split(',') : null;
  for (const [name, datei, bilder] of SZENEN){
    if (nur && nur.indexOf(name) < 0) continue;
    const t0 = Date.now();
    await einen(seite, name, path.join(ziel, datei), bilder);
    console.log(`${datei} fertig in ${Math.round((Date.now() - t0) / 1000)} s`);
  }
  if (fehler.length) console.log('Fehler waehrend der Aufnahme:', fehler);
  await browser.close();
})();
