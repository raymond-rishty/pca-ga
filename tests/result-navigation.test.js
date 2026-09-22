const assert = require('node:assert/strict');
const fs = require('node:fs');
const { test } = require('node:test');

const read = (path) => fs.readFileSync(path, 'utf8');

test('record layouts expose one shared return affordance', () => {
  const layout = read('_layouts/default.html');
  assert.equal((layout.match(/id="recordReturn"/g) || []).length, 1);
  assert.match(layout, /record-return.*hidden/);
  assert.match(layout, /id="recordReturnLink"/);
});

test('record navigation captures every supported canonical record family', () => {
  const nav = read('assets/pca-nav.js');
  assert.match(nav, /function isRecordPath/);
  assert.match(nav, /cases\|inquiries\|overtures\|rpr\\\/exc\|studies\|markdown/);
  assert.match(nav, /pca-ga-return-context/);
  assert.match(nav, /destination === location\.pathname/);
  assert.match(nav, /\.home-result\[href\], \[data-judicial-record\] h3 a\[href\], \.reading-col table a\[href\]/);
});

test('search state keeps loaded result depth deep-linkable', () => {
  const search = read('assets/home-search.js');
  assert.match(search, /searchParams\.set\('shown'/);
  assert.match(search, /initialShown/);
  assert.match(search, /data-result-primary/);
});
