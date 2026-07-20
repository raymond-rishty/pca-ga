const assert = require('node:assert/strict');
const { test } = require('node:test');
const presenter = require('../assets/search-record.js');

test('formats case metadata from the record link instead of the case-year field', () => {
  const view = presenter.formatRecord({
    type: 'Judicial case',
    title: 'Woodham v. South Florida Presbytery',
    sub: 'SJC/CJB case 2022-23',
    summary: 'The SJC denied the complaint after considering BCO 38-4.',
    provisions: ['BCO 38-4'],
    year: 2022,
    disposition: 'denied',
    url: 'cases/ga51_2024__2022-23.md',
  });

  assert.equal(view.identifier, 'Case 2022-23');
  assert.equal(view.assembly, '51st GA (2024)');
  assert.equal(view.statusLabel, 'Disposition');
  assert.equal(view.href, 'cases/ga51_2024__2022-23.html');
  assert.match(view.excerpt, /BCO 38-4/);
});

test('turns an RPR exception into a readable document title while retaining its source text as context', () => {
  const view = presenter.formatRecord({
    type: 'RPR exception',
    title: 'Calvary: Page 4: The resulting prohibition is contrary to good faith subscription.',
    sub: 'Calvary Presbytery',
    year: 2018,
    disposition: 'raised',
    url: 'rpr/exc/calvary__100.md',
  });

  assert.equal(view.title, 'Calvary Presbytery — exception 100');
  assert.equal(view.identifier, 'Exception 100');
  assert.equal(view.excerpt, 'Page 4: The resulting prohibition is contrary to good faith subscription.');
  assert.equal(view.assembly, '46th GA (2018)');
  assert.equal(view.statusLabel, 'Status');
});

test('preserves source anchors for overtures and exposes their source locator', () => {
  const view = presenter.formatRecord({
    type: 'Overture',
    title: 'Amend BCO 7-2 to Specify Ordination for Biological Males Only',
    sub: 'Overture 15 · West End Presbyterian Church',
    year: 2024,
    disposition: 'Answered in the negative',
    url: 'markdown/ga51_2024.md#ga51-p1277',
  });

  assert.equal(view.identifier, 'Overture 15');
  assert.equal(view.assembly, '51st GA (2024)');
  assert.equal(view.sourcePage, 'p. 1277');
  assert.equal(view.href, 'markdown/ga51_2024.html#ga51-p1277');
  assert.equal(view.statusLabel, 'Outcome');
});
