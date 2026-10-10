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
  for (const filename of [
    'OVERTURES.md',
    'overture_bodies.jsonl',
    'overture_dispositions.jsonl',
    'overture_titles.jsonl',
  ]) {
    fs.copyFileSync(path.join(root, 'index', filename), path.join(temp, 'index', filename));
  }
  fs.mkdirSync(path.join(temp, 'app'));

  try {
    const python = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
    const result = spawnSync(python, ['scripts/35_search_index.py', temp], {
      cwd: root,
      encoding: 'utf8',
    });
    assert.equal(result.status, 0, result.stderr || result.stdout);
    const records = JSON.parse(fs.readFileSync(path.join(temp, 'app/search_index.json'), 'utf8'));
    const overtures = records.filter((record) => record.type === 'Overture');
    const catalogue = fs.readFileSync(path.join(root, 'index/OVERTURES.md'), 'utf8');
    const catalogueRows = catalogue.split(/\r?\n/).filter((line) =>
      /^\|\s*(?:\[\d+\]\([^)]+\)|\d+)\s*\|/.test(line));
    assert.equal(overtures.length, catalogueRows.length,
      `expected one search entry per reconciled catalogue record (${catalogueRows.length}), found ${overtures.length}`);
    assert.deepEqual(overtures[0], {
      type: 'Overture',
      record_id: 'overture:ga01_1973:2:p23',
      title: 'Appoint Committee to Explore and Establish Reformed Ministerial Training',
      sub: 'Overture 2 · First Presbyterian Church, Belzoni, Mississippi',
      identifier: 'Overture 2',
      identifiers: ['Overture 2'],
      topics: ['Appoint Committee to Explore and Establish Reformed Ministerial Training'],
      provisions: [],
      year: 1973,
      disposition: '',
      url: 'markdown/ga01_1973.md#ga01-p23',
    });
  } finally {
    fs.rmSync(temp, { recursive: true, force: true });
  }
});
