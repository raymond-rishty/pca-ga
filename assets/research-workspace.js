'use strict';

(() => {
  const store = window.PCAResearch;
  if (!store) return;

  const esc = (value) => String(value || '').replace(/[&<>]/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;'
  }[character]));
  const when = (value) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return '';
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
  };
  const item = (record, kind) => `<article class="research-item">
    <a href="${esc(record.url)}"><span class="research-item__type">${esc(record.type)}</span><strong>${esc(record.title)}</strong>${record.citation ? `<small>${esc(record.citation)}</small>` : ''}</a>
    <div class="research-item__aside"><time datetime="${esc(record.savedAt)}">${when(record.savedAt)}</time>${kind !== 'recent' ? `<button type="button" data-remove-research="${kind}" data-remove-id="${esc(record.id)}"${record.citation ? ` data-remove-citation="${esc(record.citation)}"` : ''} aria-label="Remove ${esc(record.title)}">×</button>` : ''}</div>
  </article>`;

  function render(kind, filter = '') {
    const records = kind === 'saved' ? store.listSaved() : kind === 'citations' ? store.listCitations() : store.listRecent();
    const visible = filter ? records.filter((record) => `${record.title} ${record.type} ${record.citation}`.toLowerCase().includes(filter.toLowerCase())) : records;
    document.getElementById(`${kind}List`).innerHTML = visible.map((record) => item(record, kind)).join('');
    document.getElementById(`${kind}Empty`).hidden = Boolean(visible.length);
  }

  function select(tab) {
    document.querySelectorAll('[data-research-tab]').forEach((button) => button.setAttribute('aria-selected', String(button.dataset.researchTab === tab)));
    document.querySelectorAll('[data-research-panel]').forEach((panel) => { panel.hidden = panel.dataset.researchPanel !== tab; });
  }

  document.querySelectorAll('[data-research-tab]').forEach((button) => button.addEventListener('click', () => select(button.dataset.researchTab)));
  document.getElementById('savedFilter')?.addEventListener('input', (event) => render('saved', event.target.value));
  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-remove-research]');
    if (!button) return;
    store.remove(button.dataset.removeResearch, button.dataset.removeId, button.dataset.removeCitation || '');
    render(button.dataset.removeResearch);
  });
  document.getElementById('copyAllCitations')?.addEventListener('click', async () => {
    const citations = store.listCitations().map((record) => record.citation).filter(Boolean).join('\n\n');
    if (!citations) return;
    try { await navigator.clipboard.writeText(citations); } catch (_) { /* The copy button remains harmless if denied. */ }
  });

  render('saved');
  render('citations');
  render('recent');
})();
