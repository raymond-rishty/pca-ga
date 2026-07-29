const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

test('every full minutes volume exposes its PCA Historical Center source PDF', () => {
  const root = path.resolve(__dirname, '..');
  const volumes = fs.readdirSync(path.join(root, 'markdown'))
    .filter((name) => /^ga\d+_\d+\.md$/.test(name));
  const layout = fs.readFileSync(path.join(root, '_layouts/default.html'), 'utf8');

  assert.equal(volumes.length, 52);
  assert.match(layout, /page_type == 'volume' and page\.source_pdf\.file/);
  assert.match(layout, /https:\/\/www\.pcahistory\.org\/pca\/ga\/\{\{ page\.source_pdf\.file \}\}/);
  assert.match(layout, /target="_blank" rel="noopener noreferrer"/);

  for (const volume of volumes) {
    const text = fs.readFileSync(path.join(root, 'markdown', volume), 'utf8');
    assert.match(text, /^source_pdf:\n  file: \d+(?:st|nd|rd|th)_pcaga_\d{4}\.pdf$/m, volume);
  }
});
