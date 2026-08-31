const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');

function read(file) {
  return fs.readFileSync(path.join(root, file), 'utf8');
}

test('back-to-top enhancement is scoped to full minutes volumes', () => {
  const layout = read('_layouts/default.html');
  assert.match(layout, /page_type == 'volume'[\s\S]*minutes-back-to-top\.css/);
  assert.match(layout, /page_type == 'volume'[\s\S]*minutes-back-to-top\.js/);
});

test('back-to-top appears after scrolling and respects reduced motion', () => {
  const script = read('assets/minutes-back-to-top.js');
  assert.match(script, /dataset\.pageType !== 'volume'/);
  assert.match(script, /Math\.max\(600, window\.innerHeight \* 0\.75\)/);
  assert.match(script, /window\.scrollY < revealThreshold\(\)/);
  assert.match(script, /prefers-reduced-motion: reduce/);
  assert.match(script, /behavior: reducedMotion\.matches \? 'auto' : 'smooth'/);
  assert.match(script, /window\.scrollTo\(\{/);
});

test('mobile back-to-top clears the fixed bottom navigation', () => {
  const css = read('assets/minutes-back-to-top.css');
  assert.match(css, /@media \(max-width: 640px\)/);
  assert.match(css, /bottom: calc\(64px \+ \.75rem \+ env\(safe-area-inset-bottom\)\)/);
  assert.match(css, /\.minutes-back-to-top\[hidden\] \{ display: none; \}/);
});
