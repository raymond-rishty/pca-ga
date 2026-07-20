const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const { test } = require('node:test');

test('search-index build retains linked overtures', () => {
  const root = path.resolve(__dirname, '..');
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'pca-ga-search-index-'));
  fs.symlinkSync(path.join(root, 'index'), path.join(temp, 'index'), 'dir');
  fs.mkdirSync(path.join(temp, 'app'));

  try {
    const result = spawnSync('python3', ['scripts/35_search_index.py', temp], {
      cwd: root,
      encoding: 'utf8',
    });
    assert.equal(result.status, 0, result.stderr || result.stdout);
    const records = JSON.parse(fs.readFileSync(path.join(temp, 'app/search_index.json'), 'utf8'));
    const overtures = records.filter((record) => record.type === 'Overture');
    assert.ok(overtures.length > 1900, `expected overtures in the search index, found ${overtures.length}`);
    assert.deepEqual(overtures[0], {
      type: 'Overture',
      title: 'Leave Presbytery Boundaries Fluid Through 1974 and Consult Before Changes',
      sub: 'Overture 1 · LF Coast Presbytery',
      provisions: [],
      year: 1973,
      disposition: 'Adopted (final)',
      url: 'markdown/ga01_1973.md#ga01-p19',
    });
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});
