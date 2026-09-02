const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');

function read(file) {
  return fs.readFileSync(path.join(root, file), 'utf8');
}

test('source-PDF page action is part of the shared page-action implementation', () => {
  const layout = read('_layouts/default.html');
  const nav = read('assets/pca-nav.js');
  assert.doesNotMatch(layout, /minutes-page-source-pdf\.js/);
  assert.match(nav, /data-page-action="source-pdf"/);
  assert.match(nav, /sourcePdfUrlForMeta/);
  assert.match(nav, /meta\.pdfPage/);
  assert.doesNotMatch(nav, /dataset\.pageType !== ['"]volume['"]/);
  assert.doesNotMatch(read('assets/minutes-back-to-top.js'), /source PDF|pdf_page|page-source-pdf/i);
});

test('source-PDF action uses the marker coordinate and matching minutes source', () => {
  const script = read('assets/pca-nav.js');
  assert.match(script, /meta\.pdfPage = Number\(pdfPage\)/);
  assert.match(script, /sourceId\.match/);
  assert.match(script, /\^minutes:ga0\*/);
  assert.match(script, /url\.hash = `page=\$\{meta\.pdfPage\}`/);
  assert.match(script, /Open source PDF/);
  assert.match(script, /window\.open\(sourceUrl, '_blank', 'noopener,noreferrer'\)/);
  assert.match(script, /data-source-pdf-actions/);
});

test('GA33 demonstrates why printed folio cannot be the lookup key', () => {
  const minutes = read('markdown/ga33_2005.md');
  assert.match(minutes, /PAGE ga=33 pdf_page=302 printed_page=300/);
  assert.match(minutes, /PAGE ga=33 pdf_page=590 printed_page=300/);
});
