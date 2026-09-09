const assert = require('node:assert/strict');
const { test } = require('node:test');
const engine = require('../assets/search-engine.js');

const records = [
  {
    type: 'Judicial case',
    title: 'Woodham v. South Florida Presbytery',
    sub: 'SJC/CJB case 2022-23',
    identifiers: ['Case 2022-23'],
    parties: ['Woodham', 'South Florida Presbytery'],
    topics: ['pastoral relationship'],
    summary: '',
    provisions: ['BCO 38-4'],
    year: 2024,
    disposition: 'denied',
    url: 'cases/ga51_2024__2022-23.md',
  },
  {
    type: 'Constitutional inquiry',
    title: 'Session responsibility for budgeting',
    sub: 'The CCB addressed session responsibility.',
    identifiers: ['CCB inquiry 1'],
    provisions: ['BCO 10-2'],
    year: 1975,
    disposition: 'advice given',
    url: 'inquiries/ga03_1975__ci01.md',
  },
  {
    type: 'Overture',
    title: 'Amend BCO 38-4 on judicial review',
    sub: 'Overture 15 · South Florida Presbytery',
    identifiers: ['Overture 15'],
    provisions: ['BCO 38-4'],
    year: 2024,
    disposition: 'Answered in the negative',
    url: 'markdown/ga51_2024.md#ga51-p1277',
  },
];

test('keeps a case with no summary searchable', () => {
  const result = engine.search(records, 'Woodham');
  assert.equal(result.total, 1);
  assert.equal(result.results[0].record.title, 'Woodham v. South Florida Presbytery');
  assert.ok(result.results[0].matchedFields.includes('title'));
});

test('ranks records matching more ordinary keywords above partial matches', () => {
  const result = engine.search(records, 'South judicial');
  assert.equal(result.total, 2);
  assert.equal(result.results[0].record.type, 'Overture');
  assert.ok(result.results[0].matchedFields.includes('title'));
});

test('normalizes BCO punctuation and performs exact provision lookup', () => {
  const result = engine.search(records, 'bco 38.4');
  assert.equal(result.total, 2);
  assert.ok(result.results.every(({ record }) => record.provisions.includes('BCO 38-4')));
  assert.equal(engine.search(records, '38-4').total, 2);
  assert.equal(engine.normalize('BCO 38–4'), 'bco 38 4');
});

test('recognizes exact case identifiers with common prefixes', () => {
  const result = engine.search(records, 'case 2022-23');
  assert.equal(result.total, 1);
  assert.equal(result.results[0].record.type, 'Judicial case');
  assert.equal(engine.search(records, '2022-24').total, 0);
});

test('requires quoted phrases and reports useful zero-result suggestions', () => {
  const result = engine.search(records, '"Woodham v. South Florida"');
  assert.equal(result.total, 1);
  assert.equal(engine.search(records, '"not in this corpus"').emptyReason,
    'No record contains the exact quoted phrase in the selected scope.');
  assert.ok(engine.search(records, '"not in this corpus"').suggestions.some((text) => text.includes('quotation')));
});

test('reports the selected scope and filter-specific empty state', () => {
  const result = engine.search(records, 'Woodham', { types: new Set(['Overture']) });
  assert.equal(result.total, 0);
  assert.equal(result.scope, 'overtures');
  assert.ok(result.suggestions.some((text) => text.includes('record-type filter')));
});

test('searches judicial cases by proceeding type and review basis', () => {
  const caseRecord = [{
    type: 'Judicial case',
    title: 'Evans v. Arizona Presbytery',
    identifier: 'Case 2023-07',
    proceeding_type: 'appeal',
    review_standards: ['discretion_and_judgment'],
  }];

  assert.equal(engine.search(caseRecord, 'appeal').total, 1);
  assert.equal(engine.search(caseRecord, 'discretion and judgment').total, 1);
});
