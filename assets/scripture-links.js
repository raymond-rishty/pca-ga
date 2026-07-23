'use strict';
(() => {
  const base = new URL('scripture/bsb/', document.currentScript?.src || location.href);
  const cache = new Map();
  let sheet, trigger;

  const esc = (v) => String(v).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const ranges = (item) => item.ranges || [];
  const hasExplicitVerses = (item) => ranges(item).length > 0;
  const includesVerse = (verse, item) => ranges(item).some(([first, last]) => verse >= first && verse <= last);
  const rangeLabel = ([first, last]) => first === last ? String(first) : `${first}–${last}`;
  const referenceLabel = (payload, item) => hasExplicitVerses(item)
    ? `${payload.bookName} ${item.chapter}:${ranges(item).map(rangeLabel).join(', ')}`
    : `${payload.bookName} ${item.chapter}`;
  const openBibleUrl = (payload, item) => {
    const [firstVerse] = ranges(item)[0] || [];
    if (!firstVerse) return null;
    const url = new URL('https://www.openbible.info/labs/cross-references/search');
    url.searchParams.set('q', `${payload.bookName} ${item.chapter}:${firstVerse}`);
    return url.href;
  };

  function make() {
    const e = document.createElement('div');
    e.className = 'scripture-sheet';
    e.hidden = true;
    e.innerHTML = '<div class="scripture-sheet__backdrop" data-scripture-close></div><section class="scripture-sheet__panel" role="dialog" aria-modal="true" aria-labelledby="scriptureSheetTitle"><header class="scripture-sheet__header"><div><p class="scripture-sheet__eyebrow">Berean Standard Bible (BSB)</p><h2 id="scriptureSheetTitle"></h2></div><button type="button" class="scripture-sheet__close" data-scripture-close aria-label="Close Scripture reader">×</button></header><div id="scriptureSheetBody" class="scripture-sheet__body" aria-live="polite"></div></section>';
    document.body.append(e);
    return e;
  }

  function ensure() { return sheet ||= document.getElementById('scriptureSheet') || make(); }
  function close() { ensure().hidden = true; document.body.classList.remove('scripture-sheet-open'); trigger?.focus(); }
  function load(book, chapter) {
    const key = `${book}/${chapter}`;
    if (!cache.has(key)) cache.set(key, fetch(new URL(`${encodeURIComponent(book)}/${chapter}.json`, base)).then(r => {
      if (!r.ok) throw Error('load');
      return r.json();
    }));
    return cache.get(key);
  }
  function renderSection(payload, item) {
    const label = referenceLabel(payload, item);
    const verses = hasExplicitVerses(item) ? payload.verses.filter(verse => includesVerse(verse.verse, item)) : payload.verses;
    const contextUrl = openBibleUrl(payload, item);
    const action = contextUrl
      ? `<a class="scripture-sheet__action" href="${esc(contextUrl)}" target="_blank" rel="noopener noreferrer" aria-label="Open ${esc(label)} in OpenBible">Open in OpenBible ↗</a>`
      : '';
    return `<section class="scripture-sheet__chapter"><h3>${esc(label)}</h3>${verses.map(verse => `<span class="scripture-sheet__verse${includesVerse(verse.verse, item) ? ' is-cited' : ''}"><sup class="scripture-sheet__number">${verse.verse}</sup>${esc(verse.text)}</span>`).join('')}${action}</section>`;
  }
  async function open(button) {
    trigger = button;
    const current = ensure();
    const body = current.querySelector('#scriptureSheetBody');
    const title = current.querySelector('#scriptureSheetTitle');
    let refs;
    try { refs = JSON.parse(button.dataset.scriptureRefs); } catch { return; }
    title.textContent = button.dataset.scriptureTitle || button.dataset.scriptureRef || button.textContent;
    body.innerHTML = '<p class="scripture-sheet__loading">Loading Scripture…</p>';
    current.hidden = false;
    document.body.classList.add('scripture-sheet-open');
    current.querySelector('[data-scripture-close]').focus();
    try {
      const chapters = await Promise.all(refs.map(item => load(item.book, item.chapter).then(payload => ({item, payload}))));
      body.innerHTML = chapters.map(({item, payload}) => renderSection(payload, item)).join('');
    } catch (_) {
      body.innerHTML = '<p class="scripture-sheet__error">The BSB chapter could not be loaded. The minutes page remains available.</p>';
    }
  }

  document.addEventListener('click', event => {
    const closeButton = event.target.closest('[data-scripture-close]');
    if (closeButton) { close(); return; }
    const button = event.target.closest('.scripture-ref[data-scripture-refs]');
    if (button) open(button);
  });
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && sheet && !sheet.hidden) close(); });
})();
