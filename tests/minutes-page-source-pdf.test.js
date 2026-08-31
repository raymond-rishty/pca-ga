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

test('source-PDF action maps printed anchors to PDF page coordinates', () => {
  const script = read('assets/minutes-page-source-pdf.js');
  assert.match(script, /pdf_page=\(\\d\+\)[\s\S]*printed_page=\(\[\^\\s\]\+\)/);
  assert.match(script, /printed \? `ga\$\{ga\}-p\$\{printedPage\}` : `ga\$\{ga\}-pdf-p\$\{pdfPage\}`/);
  assert.match(script, /url\.hash = `page=\$\{pdfPage\}`/);
  assert.match(script, /Open source PDF/);
  assert.match(script, /window\.open\(sourceUrl, '_blank', 'noopener,noreferrer'\)/);
});
