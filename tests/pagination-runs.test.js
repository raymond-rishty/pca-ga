const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const root = path.join(__dirname, '..');
const pagination = JSON.parse(fs.readFileSync(path.join(root, 'index', 'pagination_runs.json'), 'utf8'));

test('pagination runs are ordered and their visual samples agree with each offset', () => {
  assert.equal(pagination.schema_version, 1);
  assert.equal(pagination.volumes.length, 16);
  for (const volume of pagination.volumes) {
    let previousEnd = 0;
    for (const run of volume.runs) {
      assert.ok(run.pdf_start <= run.pdf_end, `GA${volume.ga} has a reversed run`);
      assert.ok(run.pdf_start > previousEnd, `GA${volume.ga} has overlapping runs`);
      previousEnd = run.pdf_end;
      for (const sample of run.samples) {
        assert.ok(sample.pdf_page >= run.pdf_start && sample.pdf_page <= run.pdf_end);
        assert.equal(sample.printed_page, sample.pdf_page - run.offset, `GA${volume.ga} PDF ${sample.pdf_page}`);
      }
    }
  }
});

test('approved early pagination runs are projected into the rendered minutes with provenance', () => {
  for (const volume of pagination.volumes) {
    const file = path.join(root, 'markdown', `ga${String(volume.ga).padStart(2, '0')}_${volume.year}.md`);
    const text = fs.readFileSync(file, 'utf8');
    for (const run of volume.runs) {
      for (const sample of run.samples) {
        const marker = `<!-- PAGE ga=${volume.ga} pdf_page=${sample.pdf_page} printed_page=${sample.printed_page} printed_page_source=inferred -->`;
        assert.ok(text.includes(marker), `missing ${marker}`);
        const anchor = `<a id="ga${String(volume.ga).padStart(2, '0')}-p${sample.printed_page}"></a>\n${marker}`;
        assert.ok(text.includes(anchor), `missing ${anchor}`);
      }
    }
  }
});

test('the same approved pagination is projected into extracted records', () => {
  const caseText = fs.readFileSync(path.join(root, 'cases-rebuilt', 'ga10_1982__case2.md'), 'utf8');
  const studyText = fs.readFileSync(path.join(root, 'studies', 'joining-and-receiving__ga10_1982_p322.md'), 'utf8');
  assert.match(caseText, /PAGE ga=10 pdf_page=58 printed_page=56 printed_page_source=inferred/);
  assert.match(studyText, /PAGE ga=10 pdf_page=323 printed_page=321 printed_page_source=inferred/);
});
