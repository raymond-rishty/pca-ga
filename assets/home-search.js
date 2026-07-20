(() => {
  const PAGE_SIZE = 30;
  const VISIBLE_PROVISIONS = 4;
  const CASE_SUMMARY_FILES = ['app/case_summaries_1.json', 'app/case_summaries_2.json'];
  const presenter = window.PcaSearchRecord;
  const TAGS = presenter?.CATEGORIES || {};

  const form = document.querySelector('.home-search');
  const input = document.querySelector('#home-search-input');
  const section = document.querySelector('#search-results');
  const meta = document.querySelector('#search-meta');
  const filters = document.querySelector('#search-filters');
  const list = document.querySelector('#search-result-list');
  const more = document.querySelector('#search-more');
  const moreButton = document.querySelector('#show-more-results');
  const clearButton = document.querySelector('#clear-search');
  if (!form || !input || !section || !presenter) return;

  let data;
  let shown = 0;
  let activeTypes = new Set();
  let results = [];
  let terms = [];

  const esc = (value) => String(value || '').replace(/[&<>]/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;'
  }[character]));

  function highlight(value) {
    let text = esc(value);
    for (const term of terms) {
      if (term.length < 2) continue;
      const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      text = text.replace(new RegExp(`(${escaped})`, 'ig'), '<mark>$1</mark>');
    }
    return text;
  }

  function score(record) {
    let score = 0;
    for (const term of terms) {
      const position = record._searchText.indexOf(term);
      if (position < 0) return -1;
      score += position < (record.title || '').length ? 3 : 1;
    }
    return score;
  }

  function updateUrl(query) {
    const url = new URL(window.location.href);
    if (query) url.searchParams.set('q', query);
    else url.searchParams.delete('q');
    if (activeTypes.size) url.searchParams.set('type', [...activeTypes].sort().join('|'));
    else url.searchParams.delete('type');
    history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  }

  function renderFilters() {
    const present = new Set(data.map((record) => record.type));
    filters.innerHTML = '';
    Object.keys(TAGS).forEach((type) => {
      if (!present.has(type)) return;
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = type;
      button.setAttribute('aria-pressed', String(activeTypes.has(type)));
      button.addEventListener('click', () => {
        if (activeTypes.has(type)) activeTypes.delete(type);
        else activeTypes.add(type);
        renderFilters();
        search(false);
      });
      filters.append(button);
    });
  }

  function renderResults() {
    const slice = results.slice(0, shown);
    list.innerHTML = slice.map((record) => {
      const view = presenter.formatRecord(record);
      const allProvisions = view.provisions;
      const provisions = allProvisions.slice(0, VISIBLE_PROVISIONS).map((provision) =>
        `<span class="home-result__provision">${esc(provision)}</span>`
      ).join('');
      const moreProvisions = allProvisions.length > VISIBLE_PROVISIONS
        ? `<span class="home-result__provision-count">+${allProvisions.length - VISIBLE_PROVISIONS} more</span>`
        : '';
      const metadata = [
        `<span class="home-result__category">${esc(view.category.label)}</span>`,
        view.identifier ? `<span>${highlight(view.identifier)}</span>` : '',
        view.assembly ? `<span>${esc(view.assembly)}</span>` : '',
        view.sourcePage ? `<span>${esc(view.sourcePage)}</span>` : '',
      ].filter(Boolean).join('<span class="home-result__separator" aria-hidden="true">•</span>');
      const facts = [
        view.status ? `<span class="home-result__fact"><b>${esc(view.statusLabel)}:</b> ${highlight(view.status)}</span>` : '',
        provisions ? `<span class="home-result__fact home-result__fact--provisions"><b>Cites:</b> ${provisions}${moreProvisions}</span>` : '',
      ].filter(Boolean).join('');
      return `<a class="home-result home-result--${esc(view.category.className)}" href="${esc(view.href)}">
        <span class="home-result__metadata">${metadata}</span>
        <span class="home-result__title">${highlight(view.title)}</span>
        ${view.excerpt ? `<span class="home-result__summary">${highlight(view.excerpt)}</span>` : ''}
        ${facts ? `<span class="home-result__facts">${facts}</span>` : ''}
      </a>`;
    }).join('');
    more.hidden = shown >= results.length;
  }

  function search(scroll) {
    const query = input.value.trim();
    terms = query.toLowerCase().split(/\s+/).filter(Boolean);
    let pool = data;
    if (activeTypes.size) pool = pool.filter((record) => activeTypes.has(record.type));
    if (terms.length) {
      results = pool.map((record) => [score(record), record])
        .filter(([recordScore]) => recordScore >= 0)
        .sort((a, b) => b[0] - a[0] || (b[1].year || 0) - (a[1].year || 0))
        .map(([, record]) => record);
    } else {
      results = pool.slice().sort((a, b) => (b.year || 0) - (a.year || 0));
    }
    shown = PAGE_SIZE;
    meta.textContent = results.length
      ? `${results.length.toLocaleString()} result${results.length === 1 ? '' : 's'}${terms.length ? '' : ' (most recent first)'}`
      : 'No matches. Try a presbytery, BCO provision, case party, or topic.';
    renderResults();
    section.hidden = false;
    updateUrl(query);
    if (scroll) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  async function ensureData() {
    if (data) return;
    section.hidden = false;
    meta.textContent = 'Loading the catalogue…';
    list.innerHTML = '';
    try {
      const responses = await Promise.all([
        fetch('app/search_index.json'),
        ...CASE_SUMMARY_FILES.map((path) => fetch(path))
      ]);
      if (responses.some((response) => !response.ok)) throw new Error('Search index unavailable');
      data = await responses[0].json();
      const summaries = Object.assign({}, ...(await Promise.all(responses.slice(1).map((response) => response.json()))));
      data = data.filter((record) => {
        if (record.type === 'Judicial case') {
          const number = (record.sub || '').replace(/^SJC\/CJB case\s+/, '');
          record.summary = summaries[number] || '';
          return Boolean(record.summary);
        }
        return true;
      });
      data.forEach((record) => {
        record._searchText = `${record.title || ''} ${record.summary || ''} ${record.sub || ''} ${record.disposition || ''} ${(record.provisions || []).join(' ')}`.toLowerCase();
      });
      renderFilters();
    } catch {
      meta.textContent = 'The search catalogue could not be loaded. Please check your connection and try again.';
      throw new Error('Search index unavailable');
    }
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!input.value.trim()) {
      input.focus();
      return;
    }
    try {
      await ensureData();
      search(true);
    } catch { /* The message is already shown beside the search results. */ }
  });

  moreButton.addEventListener('click', () => {
    shown += PAGE_SIZE;
    renderResults();
  });

  clearButton.addEventListener('click', () => {
    input.value = '';
    activeTypes = new Set();
    section.hidden = true;
    if (data) renderFilters();
    updateUrl('');
    input.focus();
  });

  const initialParams = new URLSearchParams(window.location.search);
  const initialQuery = initialParams.get('q');
  const initialTypes = initialParams.get('type');
  if (initialTypes) activeTypes = new Set(initialTypes.split('|').filter(Boolean));
  if (initialQuery) {
    input.value = initialQuery;
    ensureData().then(() => search(false)).catch(() => {});
  }
})();
