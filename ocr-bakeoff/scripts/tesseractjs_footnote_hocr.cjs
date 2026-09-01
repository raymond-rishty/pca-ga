const fs = require('fs');
const path = require('path');
const { createWorker } = require('../tools/tesseractjs/node_modules/tesseract.js');

const root = path.resolve(__dirname, '..', '..');
const goldPath = path.join(root, 'ocr-bakeoff', 'benchmark', 'footnote_gold_marker_sample.json');
const outputDir = path.join(root, 'tmp', 'footnote_hocr_marker_sample');
const imageDirs = [
  path.join(root, 'tmp', 'footnote_review_note_only'),
  path.join(root, 'tmp', 'footnote_adjudication_sample'),
];

function imageFor(volume, page) {
  const name = `${volume}_p${String(page).padStart(4, '0')}.png`;
  for (const dir of imageDirs) {
    const candidate = path.join(dir, name);
    if (fs.existsSync(candidate)) return candidate;
  }
  throw new Error(`rendered image not found for ${volume} page ${page}`);
}

async function main() {
  const gold = JSON.parse(fs.readFileSync(goldPath, 'utf8'));
  fs.mkdirSync(outputDir, { recursive: true });
  const worker = await createWorker('eng', 1, {
    logger: message => {
      if (message.status === 'recognizing text' && Math.round(message.progress * 100) % 20 === 0) {
        console.error(`${message.status} ${Math.round(message.progress * 100)}%`);
      }
    },
  });
  await worker.setParameters({ tessedit_pageseg_mode: '6' });
  for (const item of gold.pages) {
    const stem = `${item.volume}_p${String(item.page).padStart(4, '0')}`;
    const hocrPath = path.join(outputDir, `${stem}.hocr`);
    const boxPath = path.join(outputDir, `${stem}.box`);
    const metaPath = path.join(outputDir, `${stem}.json`);
    if (fs.existsSync(hocrPath) && fs.existsSync(boxPath) && fs.existsSync(metaPath)) continue;
    const image = imageFor(item.volume, item.page);
    const started = Date.now();
    try {
      const result = await worker.recognize(image, {}, { text: true, hocr: true, box: true });
      fs.writeFileSync(hocrPath, result.data.hocr || '', 'utf8');
      fs.writeFileSync(boxPath, result.data.box || '', 'utf8');
      fs.writeFileSync(metaPath, JSON.stringify({
        volume: item.volume,
        page: item.page,
        image,
        dpi: 150,
        config: '--psm 6 -l eng; output text+hocr+box',
        runtime: 'Tesseract.js 6.0.1 (WASM Tesseract 5 engine)',
        status: 'success',
        seconds: (Date.now() - started) / 1000,
      }, null, 2));
      console.error(`${stem} ok ${(Date.now() - started) / 1000}s`);
    } catch (error) {
      fs.writeFileSync(metaPath, JSON.stringify({
        volume: item.volume,
        page: item.page,
        image,
        dpi: 150,
        status: 'failure',
        error: String(error),
      }, null, 2));
      console.error(`${stem} failed`, error);
    }
  }
  await worker.terminate();
}

main().catch(error => {
  console.error(error);
  process.exit(1);
});
