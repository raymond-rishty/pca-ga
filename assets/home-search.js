(() => {
  const RECORD_PAGE_SIZE = 30;
  const PASSAGE_PAGE_SIZE = 10;
  const VISIBLE_PROVISIONS = 4;
  const presenter = window.PcaSearchRecord;
  const engine = window.PcaSearchEngine;
  const pageSearch = window.PcaPagefindSearch;
  const TAGS = presenter?.CATEGORIES || {};
  const siteRoot = new URL('../', document.currentScript?.src || window.location.href);

  const form = document.querySelector('.home-search');
  const input = document.querySelector('#home-search-input');
  const section = document.querySelector('#search-results');
  const meta = document.querySelector('#search-meta');
  const scope = document.querySelector('#search-scope');
  const modes = document.querySelector('#search-modes');
  const filters = document.querySelector('#search-filters');
  const catalogueGroup = document.querySelector('#catalogue-results-group');
  const catalogueMeta = document.querySelector('#catalogue-results-meta');
  const list = document.querySelector('#search-result-list');
  const empty = document.querySelector('#search-empty');
  const more = document.querySelector('#search-more');
  const moreButton = document.querySelector('#show-more-results');
  const passageGroup = document.querySelector('#passage-results-group');
  const passageMeta = document.querySelector('#passage-results-meta');
  const passageList = document.querySelector('#passage-result-list');
  const passageEmpty = document.querySelector('#passage-results-empty');
  const passageMore = document.querySelector('#passage-results-more');
  const passageMoreButton = document.querySelector('#show-more-passages');
  const clearButton = document.querySelector('#clear-search');
  if (!form || !input || !section || !presenter || !engine || !pageSearch) return;

  let data;
  let recordShown = 0;
  let activeTypes = new Set();
  let recordResults = [];
  let terms = [];
  let currentSearch;
  let searchMode = 'all';
  let pagefindPromise;
  let pagefindRefs = [];
  let passageResults = [];
  let passageLoaded = 0;
  let searchSequence = 0;

  const esc = (value) => String(value || '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
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

  function updateUrl(query) {
    const url = new URL(window.location.href);
    if (query) url.searchParams.set('q', query);
    else url.searchParams.delete('q');
    if (activeTypes.size) url.searchParams.set('type', [...activeTypes].sort().join('|'));
    else url.searchParams.delete('type');
    if (searchMode !== 'all') url.searchParams.set('scope', searchMode);
    else url.searchParams.delete('scope');
    history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
  }

  function renderMode() {
    catalogueGroup.hidden = searchMode === 'fulltext';
    passageGroup.hidden = searchMode === 'catalogue';
    modes.querySelectorAll('[data-search-mode]').forEach((button) => {
      button.setAttribute('aria-pressed', String(button.dataset.searchMode === searchMode));
    });
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

  function renderRecordEmptyState() {
    if (!currentSearch || currentSearch.total) {
      empty.hidden = true;
      return;
    }
    empty.innerHTML = `<p>${esc(currentSearch.emptyReason)}</p>${currentSearch.suggestions.length
      ? `<ul>${currentSearch.suggestions.map((suggestion) => `<li>${esc(suggestion)}</li>`).join('')}</ul>` : ''}`;
    empty.hidden = false;
  }

  function renderRecordResults() {
    const slice = recordResults.slice(0, recordShown);
    list.innerHTML = slice.map(({ record, matchedFields }) => {
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
        view.category.label === 'Judicial case' && (view.proceedingType || view.reviewStandard)
          ? `<span class="home-result__fact home-result__fact--judicial"><b>Case:</b> ${view.proceedingType ? esc(view.proceedingType) : ''}${view.proceedingType && view.reviewStandard ? ' · ' : ''}${view.reviewStandard ? `<b>Review:</b> ${esc(view.reviewStandard)}` : ''}</span>` : '',
        view.status ? `<span class="home-result__fact"><b>${esc(view.statusLabel)}:</b> ${highlight(view.status)}</span>` : '',
        provisions ? `<span class="home-result__fact home-result__fact--provisions"><b>Cites:</b> ${provisions}${moreProvisions}</span>` : '',
        matchedFields?.length ? `<span class="home-result__fact home-result__fact--matched"><b>Matched:</b> ${esc(matchedFields.map((field) => engine.FIELD_LABELS[field] || field).join(', '))}</span>` : '',
      ].filter(Boolean).join('');
      return `<a class="home-result home-result--${esc(view.category.className)}" href="${esc(view.href)}">
        <span class="home-result__metadata">${metadata}</span>
        <span class="home-result__title">${highlight(view.title)}</span>
        ${view.excerpt ? `<span class="home-result__summary">${highlight(view.excerpt)}</span>` : ''}
        ${facts ? `<span class="home-result__facts">${facts}</span>` : ''}
      </a>`;
    }).join('');
    more.hidden = recordShown >= recordResults.length;
  }

  function renderPassageResults() {
    passageList.innerHTML = passageResults.map((result) => {
      const metadata = [
        '<span class="home-result__category">Full-text passage</span>',
        result.type ? `<span>${esc(result.type)}</span>` : '',
        result.year ? `<span>${esc(result.year)}</span>` : '',
        result.pageTitle ? `<span>${esc(result.pageTitle)}</span>` : '',
      ].filter(Boolean).join('<span class="home-result__separator" aria-hidden="true">•</span>');
      return `<a class="home-result home-result--${esc(result.className)} home-result--passage" href="${esc(result.href)}">
        <span class="home-result__metadata">${metadata}</span>
        <span class="home-result__title">${esc(result.title)}</span>
        ${result.excerpt ? `<span class="home-result__summary">${result.excerpt}</span>` : ''}
      </a>`;
    }).join('');
    passageMore.hidden = passageLoaded >= pagefindRefs.length;
  }

  async function ensurePagefind() {
    if (!pagefindPromise) {
      const moduleUrl = new URL('pagefind/pagefind.js', siteRoot).href;
      pagefindPromise = import(moduleUrl).then(async (pagefind) => {
        await pagefind.options({
          baseUrl: siteRoot.pathname,
          excerptLength: 45,
          metaCacheTag: 'pca-ga-v17',
          ranking: { metaWeights: { title: 6, type: 1 } },
        });
        return pagefind;
      });
    }
    return pagefindPromise;
  }

  async function loadMorePassages(target, sequence) {
    const end = Math.min(target, pagefindRefs.length);
    const refs = pagefindRefs.slice(passageLoaded, end);
    const loaded = await Promise.all(refs.map(async (result) => {
      try { return pageSearch.bestPassage(await result.data()); }
      catch { return null; }
    }));
    if (sequence !== searchSequence) return;
    passageResults.push(...loaded.filter(Boolean));
    passageLoaded = end;
    renderPassageResults();
  }

  async function searchPassages(query, sequence) {
    pagefindRefs = [];
    passageResults = [];
    passageLoaded = 0;
    passageList.innerHTML = '';
    passageEmpty.hidden = true;
    passageMore.hidden = true;
    passageMeta.textContent = 'Searching the full text…';
    try {
      const pagefind = await ensurePagefind();
      const options = {};
      const typeFilters = pageSearch.filtersForTypes(activeTypes);
      if (typeFilters) options.filters = typeFilters;
      const response = await pagefind.search(query, options);
      if (sequence !== searchSequence) return;
      pagefindRefs = response.results || [];
      passageMeta.textContent = `${pagefindRefs.length.toLocaleString()} document${pagefindRefs.length === 1 ? '' : 's'} with matching passages`;
      if (!pagefindRefs.length) {
        passageEmpty.innerHTML = '<p>No indexed passage contains this search in the selected record types. Try fewer terms or switch to All record types.</p>';
        passageEmpty.hidden = false;
        return;
      }
      await loadMorePassages(PASSAGE_PAGE_SIZE, sequence);
    } catch {
      if (sequence !== searchSequence) return;
      passageMeta.textContent = 'Full-text passage search is unavailable.';
      passageEmpty.innerHTML = '<p>Pagefind is generated by the deployed site build. Catalogue search remains available.</p>';
      passageEmpty.hidden = false;
    }
  }

  function search(scroll) {
    const query = input.value.trim();
    const sequence = ++searchSequence;
    currentSearch = engine.search(data, query, { types: activeTypes });
    recordResults = currentSearch.results;
    terms = query.replace(/"/g, '').split(/\s+/).filter(Boolean);
    recordShown = RECORD_PAGE_SIZE;
    meta.textContent = `Search for “${query}” across catalogue records and full-text passages.`;
    catalogueMeta.textContent = `${currentSearch.total.toLocaleString()} catalogue record${currentSearch.total === 1 ? '' : 's'}`;
    const modeLabel = searchMode === 'all' ? 'catalogue and full text' : searchMode === 'catalogue' ? 'catalogue only' : 'full text only';
    scope.textContent = `Scope: ${modeLabel} · ${currentSearch.scope}`;
    renderMode();
    renderRecordResults();
    renderRecordEmptyState();
    section.hidden = false;
    updateUrl(query);
    if (searchMode === 'catalogue') {
      passageMeta.textContent = '';
      passageList.innerHTML = '';
      passageEmpty.hidden = true;
      passageMore.hidden = true;
    } else {
      searchPassages(query, sequence);
    }
    if (scroll) {
      const behavior = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
      section.scrollIntoView({ behavior, block: 'start' });
    }
  }

  async function ensureData() {
    if (data) return;
    section.hidden = false;
    meta.textContent = 'Loading the search catalogue…';
    list.innerHTML = '';
    try {
      const response = await fetch('app/search_index.json');
      if (!response.ok) throw new Error('Search index unavailable');
      data = await response.json();
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

  modes.addEventListener('click', (event) => {
    const button = event.target.closest('[data-search-mode]');
    if (!button) return;
    searchMode = button.dataset.searchMode;
    renderMode();
    if (data && input.value.trim()) search(false);
    else updateUrl(input.value.trim());
  });

  moreButton.addEventListener('click', () => {
    recordShown += RECORD_PAGE_SIZE;
    renderRecordResults();
  });

  passageMoreButton.addEventListener('click', () => {
    loadMorePassages(passageLoaded + PASSAGE_PAGE_SIZE, searchSequence);
  });

  clearButton.addEventListener('click', () => {
    searchSequence += 1;
    input.value = '';
    activeTypes = new Set();
    currentSearch = null;
    pagefindRefs = [];
    passageResults = [];
    section.hidden = true;
    if (data) renderFilters();
    updateUrl('');
    input.focus();
  });

  const initialParams = new URLSearchParams(window.location.search);
  const initialQuery = initialParams.get('q');
  const initialTypes = initialParams.get('type');
  const initialScope = initialParams.get('scope');
  if (initialTypes) activeTypes = new Set(initialTypes.split('|').filter(Boolean));
  if (['all', 'catalogue', 'fulltext'].includes(initialScope)) searchMode = initialScope;
  renderMode();
  if (initialQuery) {
    input.value = initialQuery;
    ensureData().then(() => search(false)).catch(() => {});
  }
})();
