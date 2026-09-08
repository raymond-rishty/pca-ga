const assert = require('node:assert/strict');
const { test } = require('node:test');
const pageSearch = require('../assets/pagefind-search.js');

test('builds an OR filter for the selected record types', () => {
  assert.deepEqual(pageSearch.filtersForTypes(new Set(['Overture', 'Judicial case'])), {
    type: { any: ['Judicial case', 'Overture'] },
  });
  assert.equal(pageSearch.filtersForTypes(new Set()), undefined);
});

test('uses the highest-ranked anchored Pagefind section as the passage result', () => {
  const result = pageSearch.bestPassage({
    url: '/markdown/ga01_1973.html',
    excerpt: 'Page excerpt',
    meta: { title: 'First General Assembly', type: 'General Assembly minutes', year: '1973' },
    sub_results: [
      { title: 'First General Assembly', url: '/markdown/ga01_1973.html', excerpt: 'Opening' },
      { title: 'Overture 3', url: '/markdown/ga01_1973.html#overture-3', excerpt: 'The <mark>Assembly</mark> answered.' , anchor: { id: 'overture-3' } },
    ],
  });

  assert.equal(result.href, '/markdown/ga01_1973.html#overture-3');
  assert.equal(result.title, 'Overture 3');
  assert.equal(result.pageTitle, 'First General Assembly');
  assert.equal(result.excerpt, 'The <mark>Assembly</mark> answered.');
  assert.equal(result.year, '1973');
});

test('removes unexpected markup while preserving Pagefind highlights', () => {
  assert.equal(
    pageSearch.safeExcerpt('A <mark>match</mark> <img src=x onerror=alert(1)> remains.'),
    'A <mark>match</mark>  remains.',
  );
  assert.equal(pageSearch.safeHref('javascript:alert(1)'), '#');
  assert.equal(pageSearch.safeHref('/markdown/ga01_1973.html#overture-3'), '/markdown/ga01_1973.html#overture-3');
});
