'use strict';

(() => {
  const store = window.PCAResearch;
  if (!store) return;

  const ICONS = {
    open: '<svg class="action-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M13 4h7v7M20 4 10 14M5 7v12h12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    cite: '<svg class="action-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 3h10l4 4v14H5zM15 3v5h4M8 12h8M8 16h5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M7 7v3M5.5 8.5h3M12 11v3M10.5 12.5h3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>',
    link: '<svg class="action-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M10 14 14 10M8 17l-1.5 1.5a3 3 0 0 1-4.25-4.25L6 10.5M16 7l1.5-1.5a3 3 0 0 1 4.25 4.25L18 13.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
    share: '<svg class="action-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M13 4h7v7M20 4 10 14M5 7v12h12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    remove: '<svg class="action-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  };

  const esc = (value) => String(value || '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));
  const when = (value) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  };

  let activeRecord = null;
  let savedFilter = '';

  function copyText(value) {
    if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(value);
    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', '');
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand('copy');
    textarea.remove();
    return Promise.resolve();
  }

  function showToast(message) {
    let toast = document.getElementById('researchToast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'researchToast';
      toast.className = 'research-toast';
      toast.setAttribute('role', 'status');
      toast.setAttribute('aria-live', 'polite');
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add('visible');
    window.clearTimeout(showToast.timeout);
    showToast.timeout = window.setTimeout(() => toast.classList.remove('visible'), 2200);
  }

  function savedItem(record) {
    const detail = record.short || record.citation || 'Saved source';
    return `<article class="research-item research-item--saved">
      <button class="research-item__open" type="button" data-open-bookshelf="${esc(record.id)}" aria-label="Open actions for ${esc(record.title)}">
        <span class="research-item__content"><span class="research-item__type">${esc(record.type)}</span><strong>${esc(record.title)}</strong><small>${esc(detail)}</small></span>
        <span class="research-item__meta"><time datetime="${esc(record.savedAt)}">${when(record.savedAt)}</time><span class="research-item__chevron" aria-hidden="true">›</span></span>
      </button>
    </article>`;
  }

  function recentItem(record) {
    return `<article class="research-item research-item--recent">
      <a href="${esc(record.url)}"><span class="research-item__type">${esc(record.type)}</span><strong>${esc(record.title)}</strong>${record.short || record.citation ? `<small>${esc(record.short || record.citation)}</small>` : ''}</a>
      <div class="research-item__aside"><time datetime="${esc(record.savedAt)}">${when(record.savedAt)}</time></div>
    </article>`;
  }

  function render(kind, filter = '') {
    const records = kind === 'saved' ? store.listSaved() : store.listRecent();
    const visible = filter ? records.filter((record) => `${record.title} ${record.type} ${record.short} ${record.citation}`.toLowerCase().includes(filter.toLowerCase())) : records;
    const list = document.getElementById(`${kind}List`);
    const empty = document.getElementById(`${kind}Empty`);
    if (!list || !empty) return;
    list.innerHTML = visible.map((record) => kind === 'saved' ? savedItem(record) : recentItem(record)).join('');
    empty.hidden = Boolean(visible.length);
  }

  function select(tab) {
    document.querySelectorAll('[data-research-tab]').forEach((button) => button.setAttribute('aria-selected', String(button.dataset.researchTab === tab)));
    document.querySelectorAll('[data-research-panel]').forEach((panel) => { panel.hidden = panel.dataset.researchPanel !== tab; });
  }

  function createBookshelfSheet() {
    const sheet = document.createElement('div');
    sheet.className = 'research-sheet';
    sheet.id = 'bookshelfItemSheet';
    sheet.hidden = true;
    sheet.innerHTML = `<div class="research-sheet__backdrop" data-sheet-close></div>
      <section class="research-sheet__panel bookshelf-sheet" role="dialog" aria-modal="true" aria-labelledby="bookshelfSheetTitle">
        <div class="research-sheet__handle" aria-hidden="true"></div>
        <header><h2 id="bookshelfSheetTitle">Bookshelf item</h2><button type="button" data-sheet-close aria-label="Close bookshelf item">×</button></header>
        <div class="bookshelf-preview">
          <p class="research-sheet__label" id="bookshelfPreviewType"></p>
          <h3 id="bookshelfPreviewTitle"></h3>
          <p id="bookshelfPreviewCitation"></p>
          <small id="bookshelfPreviewSaved"></small>
        </div>
        <div class="page-action-list" aria-label="Bookshelf item actions">
          <button type="button" class="is-primary" data-bookshelf-action="open">${ICONS.open}<span>Open page</span></button>
          <button type="button" data-bookshelf-action="cite">${ICONS.cite}<span>Copy citation</span></button>
          <button type="button" data-bookshelf-action="link">${ICONS.link}<span>Copy link</span></button>
          <button type="button" data-bookshelf-action="share">${ICONS.share}<span>Share</span></button>
          <button type="button" class="is-destructive" data-bookshelf-action="remove">${ICONS.remove}<span>Remove from bookshelf</span></button>
        </div>
      </section>`;
    document.body.appendChild(sheet);
    return sheet;
  }

  function closeBookshelfSheet() {
    const sheet = document.getElementById('bookshelfItemSheet');
    if (sheet) sheet.hidden = true;
    document.body.classList.remove('sheet-open');
    activeRecord = null;
  }

  function openBookshelfSheet(record) {
    activeRecord = record;
    const sheet = document.getElementById('bookshelfItemSheet') || createBookshelfSheet();
    document.querySelectorAll('.research-sheet').forEach((candidate) => { candidate.hidden = true; });
    sheet.querySelector('#bookshelfPreviewType').textContent = record.type;
    sheet.querySelector('#bookshelfPreviewTitle').textContent = record.title;
    sheet.querySelector('#bookshelfPreviewCitation').textContent = record.short || record.citation || 'PCA General Assembly Minutes';
    sheet.querySelector('#bookshelfPreviewSaved').textContent = record.savedAt ? `Saved ${when(record.savedAt)}` : '';
    sheet.hidden = false;
    document.body.classList.add('sheet-open');
    sheet.querySelector('[data-bookshelf-action="open"]')?.focus();
  }

  document.querySelectorAll('[data-research-tab]').forEach((button) => button.addEventListener('click', () => select(button.dataset.researchTab)));
  document.getElementById('savedFilter')?.addEventListener('input', (event) => {
    savedFilter = event.target.value;
    render('saved', savedFilter);
  });

  document.addEventListener('click', async (event) => {
    const opener = event.target.closest('[data-open-bookshelf]');
    if (opener) {
      const record = store.listSaved().find((entry) => entry.id === opener.dataset.openBookshelf);
      if (record) openBookshelfSheet(record);
      return;
    }

    if (event.target.closest('[data-sheet-close]') && event.target.closest('#bookshelfItemSheet')) {
      closeBookshelfSheet();
      return;
    }

    const button = event.target.closest('[data-bookshelf-action]');
    if (!button || !activeRecord) return;
    const action = button.dataset.bookshelfAction;
    if (action === 'open') {
      location.assign(activeRecord.url);
      return;
    }
    if (action === 'cite') {
      await copyText(activeRecord.full || activeRecord.citation || activeRecord.short || activeRecord.url);
      showToast('Citation copied');
      return;
    }
    if (action === 'link') {
      await copyText(activeRecord.url);
      showToast('Link copied');
      return;
    }
    if (action === 'share') {
      try {
        if (navigator.share) await navigator.share({ title: activeRecord.title, text: activeRecord.short || activeRecord.citation, url: activeRecord.url });
        else { await copyText(activeRecord.url); showToast('Link copied'); }
      } catch (_) { /* A dismissed share sheet is not an error state. */ }
      return;
    }
    if (action === 'remove') {
      store.remove('saved', activeRecord.id);
      render('saved', savedFilter);
      closeBookshelfSheet();
      showToast('Removed from your bookshelf');
    }
  });

  render('saved');
  render('recent');
})();
