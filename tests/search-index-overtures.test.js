const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');

test('search-index build retains linked overtures', () => {
  const root = path.resolve(__dirname, '..');
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'pca-ga-search-index-'));
  fs.mkdirSync(path.join(temp, 'index'));
  fs.copyFileSync(path.join(root, 'index/OVERTURES.md'), path.join(temp, 'index/OVERTURES.md'));
  fs.mkdirSync(path.join(temp, 'app'));

  try {
    const result = spawnSync('python3', ['scripts/35_search_index.py', temp], {
      cwd: root,
      encoding: 'utf8',
    });
    assert.equal(result.status, 0, result.stderr || result.stdout);
    const records = JSON.parse(fs.readFileSync(path.join(temp, 'app/search_index.json'), 'utf8'));
    const overtures = records.filter((record) => record.type === 'Overture');
    assert.ok(overtures.length > 1200, `expected overtures in the search index, found ${overtures.length}`);
    assert.deepEqual(overtures[0], {
      type: 'Overture',
      title: 'Appoint Committee to Add Scripture Proof Texts to the BCO',
      sub: 'Overture 6 · Covenant Presbytery',
      identifier: 'Overture 6',
      identifiers: ['Overture 6'],
      topics: ['Appoint Committee to Add Scripture Proof Texts to the BCO'],
      provisions: [],
      year: 1973,
      disposition: '',
      url: 'markdown/ga01_1973.md#ga01-p21',
    });
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});
