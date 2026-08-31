const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');

function read(file) {
  return fs.readFileSync(path.join(root, file), 'utf8');
}

test('source-PDF page action is a separate minutes enhancement', () => {
  const layout = read('_layouts/default.html');
  assert.match(layout, /page_type == 'volume'[\s\S]*minutes-page-source-pdf\.js/);
  assert.doesNotMatch(read('assets/minutes-back-to-top.js'), /source PDF|pdf_page|page-source-pdf/i);
});

test('source-PDF action maps each rendered marker to the PDF page at the same document position', () => {
  const script = read('assets/minutes-page-source-pdf.js');
  assert.match(script, /const pdfPages = \[\]/);
  assert.match(script, /pdfPages\.push\(match\[2\]\)/);
  assert.match(script, /const markers = \[\.\.\.column\.querySelectorAll\('\.page-marker'\)\]/);
  assert.match(script, /const markerIndex = markers\.indexOf\(marker\)/);
  assert.match(script, /pdfPages\[markerIndex\]/);
  assert.doesNotMatch(script, /pdfByAnchor|\.set\(anchor, pdfPage\)/);
  assert.match(script, /url\.hash = `page=\$\{pdfPage\}`/);
  assert.match(script, /Open source PDF/);
  assert.match(script, /window\.open\(sourceUrl, '_blank', 'noopener,noreferrer'\)/);
});

test('GA33 demonstrates why printed folio cannot be the lookup key', () => {
  const minutes = read('markdown/ga33_2005.md');
  assert.match(minutes, /PAGE ga=33 pdf_page=302 printed_page=300/);
  assert.match(minutes, /PAGE ga=33 pdf_page=590 printed_page=300/);
});
