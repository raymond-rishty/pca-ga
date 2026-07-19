'use strict';

(() => {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const menuBtn = document.getElementById('menuBtn');
  const sbClose = document.getElementById('sidebarClose');
  const store = window.PCAResearch;
  const ICONS = {
    page: (filled = false) => `<svg class="action-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 3h10l4 4v14H5zM15 3v5h4M8 12h8M8 16h5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/>${filled ? '<path d="M3 2h5v5l-2.5-1.8L3 7z" fill="currentColor"/>' : '<path d="M3 2h5v5l-2.5-1.8L3 7z" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/>'}</svg>`,
    cite: `<svg class="action-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M5 3h10l4 4v14H5zM15 3v5h4M8 12h8M8 16h5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M7 7v3M5.5 8.5h3M12 11v3M10.5 12.5h3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>`,
    link: `<svg class="action-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M10 14 14 10M8 17l-1.5 1.5a3 3 0 0 1-4.25-4.25L6 10.5M16 7l1.5-1.5a3 3 0 0 1 4.25 4.25L18 13.5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>`,
    share: `<svg class="action-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M13 4h7v7M20 4 10 14M5 7v12h12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  };

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

  function openSidebar() {
    sidebar?.classList.add('open');
    overlay?.classList.add('active');
    menuBtn?.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
  }

  function closeSidebar() {
    sidebar?.classList.remove('open');
    overlay?.classList.remove('active');
    menuBtn?.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
  }

  menuBtn?.addEventListener('click', () => sidebar?.classList.contains('open') ? closeSidebar() : openSidebar());
  sbClose?.addEventListener('click', closeSidebar);
  overlay?.addEventListener('click', closeSidebar);
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (!document.getElementById('pageFind')?.hidden) { closePageFind(); return; }
    if ([...document.querySelectorAll('.research-sheet')].some((sheet) => !sheet.hidden)) closeResearchSheets();
    else closeSidebar();
  });

  function pageUrl() {
    return `${location.origin}${location.pathname}`;
  }

  function sourceCitation(header) {
    const title = header.querySelector('h1')?.textContent.trim() || `Judicial Case ${header.dataset.case}`;
    const source = header.querySelector('.record-header__content p:last-child')?.textContent || '';
    const pages = source.match(/pp?\.\s*(\d+)(?:\s*[–-]\s*(\d+))?/i);
    const ga = header.dataset.ga;
    const range = pages ? `M${ga}GA ${pages[2] ? `pp.${pages[1]}–${pages[2]}` : `p.${pages[1]}`}` : `${ga}th General Assembly`;
    const url = pageUrl();
    return {
      id: url,
      url,
      title,
      type: 'Judicial case',
      short: range,
      full: `${title} — ${range}. ${url}`,
      markdown: `[${title}](${url}) — ${range}.`,
    };
  }

  function createSheet() {
    const sheet = document.createElement('div');
    sheet.className = 'research-sheet';
    sheet.id = 'citationSheet';
    sheet.hidden = true;
    sheet.innerHTML = `<div class="research-sheet__backdrop" data-sheet-close></div>
      <section class="research-sheet__panel" role="dialog" aria-modal="true" aria-labelledby="citationSheetTitle">
        <div class="research-sheet__handle" aria-hidden="true"></div>
        <header><h2 id="citationSheetTitle">Cite record</h2><button type="button" data-sheet-close aria-label="Close citation sheet">×</button></header>
        <p class="research-sheet__label">Citation format</p>
        <div class="citation-formats" role="group" aria-label="Citation format">
          <button type="button" data-citation-format="full" aria-pressed="true">Full</button>
          <button type="button" data-citation-format="short" aria-pressed="false">Short</button>
          <button type="button" data-citation-format="markdown" aria-pressed="false">Markdown</button>
        </div>
        <div class="citation-preview" id="citationPreview"></div>
        <button class="sheet-primary" type="button" id="copyCitation">Copy citation</button>
        <button class="sheet-secondary" type="button" id="saveCitation">Add to My Research</button>
      </section>`;
    document.body.appendChild(sheet);
    return sheet;
  }

  let activeCitation;
  let activePage;
  let citationFormat = 'full';

  function openCitation(meta) {
    activeCitation = meta;
    citationFormat = 'full';
    const sheet = document.getElementById('citationSheet') || createSheet();
    closeResearchSheets();
    sheet.hidden = false;
    document.body.classList.add('sheet-open');
    updateCitationSheet();
    sheet.querySelector('[data-citation-format="full"]')?.focus();
  }

  function closeCitation() {
    closeResearchSheets();
  }

  function closeResearchSheets() {
    document.querySelectorAll('.research-sheet').forEach((sheet) => sheet.setAttribute('hidden', ''));
    document.body.classList.remove('sheet-open');
  }

  function updateCitationSheet() {
    const sheet = document.getElementById('citationSheet');
    if (!sheet || !activeCitation) return;
    sheet.querySelector('#citationPreview').textContent = activeCitation[citationFormat];
    sheet.querySelectorAll('[data-citation-format]').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.citationFormat === citationFormat)));
  }

  document.addEventListener('click', async (event) => {
    const close = event.target.closest('[data-sheet-close]');
    if (close) { closeResearchSheets(); return; }
    const format = event.target.closest('[data-citation-format]');
    if (format) { citationFormat = format.dataset.citationFormat; updateCitationSheet(); return; }
    if (event.target.closest('#copyCitation') && activeCitation) {
      await copyText(activeCitation[citationFormat]);
      showToast('Citation copied');
      return;
    }
    if (event.target.closest('#saveCitation') && activeCitation && store) {
      store.addCitation({ ...activeCitation, citation: activeCitation[citationFormat] });
      showToast('Citation added to My Research');
      closeCitation();
    }
  });

  function setupRecordActions(header, meta) {
    store?.addRecent({ ...meta, citation: meta.short });
    const saveButton = header.querySelector('[data-record-save]');
    if (!saveButton) return;
    const setSave = (saved) => {
      saveButton.classList.toggle('is-saved', saved);
      saveButton.setAttribute('aria-pressed', String(saved));
      saveButton.innerHTML = `${ICONS.page(saved)} ${saved ? 'Saved' : 'Save'}`;
    };
    setSave(Boolean(store?.isSaved(meta)));
    saveButton.addEventListener('click', () => {
      const saved = store?.toggleSaved({ ...meta, citation: meta.short });
      setSave(saved);
      showToast(saved ? 'Added to your bookshelf' : 'Removed from your bookshelf');
    });
    header.querySelector('[data-record-cite]')?.addEventListener('click', () => openCitation(meta));
    header.querySelector('[data-record-share]')?.addEventListener('click', async () => {
      try {
        if (navigator.share) await navigator.share({ title: meta.title, text: meta.short, url: meta.url });
        else { await copyText(meta.url); showToast('Link copied'); }
      } catch (_) { /* A dismissed share sheet is not an error state. */ }
    });
  }

  function enhanceCaseHeader() {
    const header = document.getElementById('recordHeader');
    const content = document.getElementById('recordHeaderContent');
    const column = document.querySelector('.reading-col');
    if (!header || !content || !column) return;
    const title = [...column.children].find((child) => child.tagName === 'H1');
    if (!title) return;
    let next = title.nextElementSibling;
    content.appendChild(title);
    let moved = 0;
    while (next && next.tagName === 'P' && moved < 2) {
      const current = next;
      next = next.nextElementSibling;
      content.appendChild(current);
      moved += 1;
    }
    const sourceLine = [...content.querySelectorAll('p')].find((paragraph) => /^\s*Source:/i.test(paragraph.textContent));
    const sourceLink = sourceLine?.querySelector('a[href*="/markdown/"]');
    const sourcePages = sourceLine?.textContent.match(/pp?\.\s*(\d+)(?:\s*[–-]\s*(\d+))?/i);
    if (sourceLink && sourcePages) {
      sourceLink.textContent = `M${header.dataset.ga}GA ${sourcePages[2] ? `pp.${sourcePages[1]}–${sourcePages[2]}` : `p.${sourcePages[1]}`}`;
    }
    const disposition = content.querySelector('p')?.textContent.match(/Disposition:\s*([^·]+)/i)?.[1]?.trim();
    const dispositionKind = disposition && DISPS[disposition.toLowerCase()];
    if (dispositionKind) {
      const status = document.createElement('span');
      status.className = `record-header__disposition badge badge--${dispositionKind}`;
      status.textContent = disposition;
      content.before(status);
    }
    header.classList.add('is-ready');

    setupRecordActions(header, sourceCitation(header));
  }

  function collectionCitation(header) {
    const title = header.querySelector('h1')?.textContent.trim() || header.dataset.recordKind || 'PCA record';
    const source = header.querySelector('a[href*="/markdown/"]') || document.querySelector('.reading-col a[href*="/markdown/"]');
    const href = source?.getAttribute('href') || '';
    const sourceText = source?.textContent || '';
    const ga = (href.match(/ga0?(\d+)_/i) || href.match(/#ga0?(\d+)-p/i) || sourceText.match(/ga0?(\d+)/i))?.[1];
    const page = (sourceText.match(/p\.(\d+)/i) || href.match(/-p(\d+)/i))?.[1];
    const short = ga && page ? `M${Number(ga)}GA p.${page}` : 'PCA General Assembly Minutes';
    const url = pageUrl();
    return {
      id: url,
      url,
      title,
      type: header.dataset.recordKind || 'PCA record',
      short,
      full: `${title} — ${short}. ${url}`,
      markdown: `[${title}](${url}) — ${short}.`,
    };
  }

  function enhanceCollectionHeader() {
    const header = document.getElementById('collectionRecordHeader');
    const content = document.getElementById('collectionRecordHeaderContent');
    const column = document.querySelector('.reading-col');
    if (!header || !content || !column) return;
    const title = [...column.children].find((child) => child.tagName === 'H1');
    if (!title) return;
    let next = title.nextElementSibling;
    content.appendChild(title);
    let moved = 0;
    while (next && next.tagName !== 'HR' && moved < 3) {
      const current = next;
      next = next.nextElementSibling;
      content.appendChild(current);
      moved += 1;
    }
    header.classList.add('is-ready');
    setupRecordActions(header, collectionCitation(header));
  }

  function pageMeta(ga, page) {
    const short = `M${ga}GA p.${page}`;
    const url = `${pageUrl()}#ga${ga}-p${page}`;
    const recordTitle = document.querySelector('.record-header h1, .reading-col > h1')?.textContent.trim() || 'PCA General Assembly Minutes';
    return {
      id: url,
      url,
      title: `${recordTitle} — ${short}`,
      type: 'Printed minutes page',
      short,
      full: `${recordTitle} — ${short}. ${url}`,
      markdown: `[${short}](${url}) — ${recordTitle}.`,
      citation: short,
    };
  }

  function createPageActionSheet() {
    const sheet = document.createElement('div');
    sheet.className = 'research-sheet';
    sheet.id = 'pageActionSheet';
    sheet.hidden = true;
    sheet.innerHTML = `<div class="research-sheet__backdrop" data-sheet-close></div>
      <section class="research-sheet__panel page-action-sheet" role="dialog" aria-modal="true" aria-labelledby="pageActionTitle">
        <div class="research-sheet__handle" aria-hidden="true"></div>
        <header><h2 id="pageActionTitle">Printed page</h2><button type="button" data-sheet-close aria-label="Close page actions">×</button></header>
        <p class="page-action-sheet__context" id="pageActionContext"></p>
        <div class="page-action-list" aria-label="Printed page actions">
          <button type="button" data-page-action="save"></button>
          <button type="button" data-page-action="cite">${ICONS.cite}<span>Copy citation</span></button>
          <button type="button" data-page-action="link">${ICONS.link}<span>Copy page link</span></button>
          <button type="button" data-page-action="share">${ICONS.share}<span>Share page</span></button>
        </div>
      </section>`;
    document.body.appendChild(sheet);
    return sheet;
  }

  function setPageSaveButton(button, saved) {
    if (!button) return;
    button.classList.toggle('is-saved', saved);
    button.setAttribute('aria-pressed', String(saved));
    button.innerHTML = `${ICONS.page(saved)}<span>${saved ? 'Saved to bookshelf' : 'Save to bookshelf'}</span>`;
  }

  function openPageActions(meta) {
    activePage = meta;
    const sheet = document.getElementById('pageActionSheet') || createPageActionSheet();
    closeResearchSheets();
    sheet.querySelector('#pageActionTitle').textContent = meta.short;
    sheet.querySelector('#pageActionContext').textContent = 'Save, cite, or share a link that opens at this exact printed page.';
    setPageSaveButton(sheet.querySelector('[data-page-action="save"]'), Boolean(store?.isSaved(meta)));
    sheet.hidden = false;
    document.body.classList.add('sheet-open');
    sheet.querySelector('[data-page-action="save"]')?.focus();
  }

  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-page-action]');
    if (!button || !activePage) return;
    const action = button.dataset.pageAction;
    if (action === 'save') {
      const saved = store?.toggleSaved(activePage);
      setPageSaveButton(button, saved);
      showToast(saved ? 'Added to your bookshelf' : 'Removed from your bookshelf');
      return;
    }
    if (action === 'cite') {
      await copyText(activePage.short);
      showToast(`Citation ${activePage.short} copied`);
      return;
    }
    if (action === 'link') {
      await copyText(activePage.url);
      showToast('Page link copied');
      return;
    }
    if (action === 'share') {
      try {
        if (navigator.share) await navigator.share({ title: activePage.title, text: activePage.short, url: activePage.url });
        else { await copyText(activePage.url); showToast('Page link copied'); }
      } catch (_) { /* A dismissed share sheet is not an error state. */ }
    }
  });

  function decoratePageMarkers() {
    const column = document.querySelector('.reading-col');
    if (!column) return;
    const walker = document.createTreeWalker(column, NodeFilter.SHOW_COMMENT);
    const comments = [];
    while (walker.nextNode()) comments.push(walker.currentNode);
    comments.forEach((comment) => {
      const match = comment.nodeValue.match(/PAGE\s+ga=(\d+)[^\n]*printed_page=(\d+)/i);
      if (!match) return;
      const [, ga, page] = match;
      const meta = pageMeta(ga, page);
      const marker = document.createElement('div');
      marker.className = 'page-marker';
      marker.id = `ga${ga}-p${page}`;
      marker.innerHTML = `<a href="#ga${ga}-p${page}">${meta.short}</a><button type="button" class="page-marker__actions" aria-label="Actions for ${meta.short}">${ICONS.page()}<span>Page actions</span></button>`;
      marker.querySelector('button').addEventListener('click', () => openPageActions(meta));
      comment.replaceWith(marker);
    });
  }

  const DISPS = {
    sustained: 'sustained', 'not sustained': 'not-sustained', denied: 'denied', dismissed: 'dismissed',
    withdrawn: 'withdrawn', moot: 'moot', administrative: 'administrative', remanded: 'remanded', remitted: 'remanded',
  };

  function makeTablesResponsive() {
    document.querySelectorAll('.reading-col table').forEach((table) => {
      const header = table.tHead?.rows[0] || table.rows[0];
      const labels = header ? [...header.cells].map((cell) => cell.textContent.replace(/\s+/g, ' ').trim()) : [];
      if (labels.length < 4) return;
      table.classList.add('responsive-table');
      [...table.tBodies].forEach((body) => {
        [...body.rows].forEach((row) => {
          [...row.cells].forEach((cell, index) => {
            cell.dataset.label = labels[index] || 'Detail';
          });
        });
      });
    });
  }

  function injectBadges() {
    document.querySelectorAll('.reading-col strong').forEach((element) => {
      const value = element.textContent.trim().toLowerCase();
      if (!DISPS[value]) return;
      const badge = document.createElement('span');
      badge.className = `badge badge--${DISPS[value]}`;
      badge.textContent = element.textContent.trim();
      element.replaceWith(badge);
    });
  }

  function contextLabel() {
    const query = document.querySelector('#home-search-input')?.value.trim();
    if (query) return `Back to “${query}” results`;
    const heading = document.querySelector('.workspace-hero h1, .reading-col > h1');
    return heading ? `Back to ${heading.textContent.trim()}` : 'Back to results';
  }

  function recordContext(event) {
    const link = event.target.closest('a[href]');
    if (!link || link.closest('#recordSequence') || event.defaultPrevented || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const target = new URL(link.href, location.href);
    if (target.origin !== location.origin || !target.pathname.includes('/cases/')) return;
    const resultLinks = [...document.querySelectorAll('.home-result[href]')].map((item) => ({ href: item.href, title: item.querySelector('.home-result__title')?.textContent.trim() || '' }));
    const position = resultLinks.findIndex((item) => item.href === target.href);
    const context = {
      href: location.href,
      label: contextLabel(),
      y: window.scrollY,
      items: resultLinks,
      position,
    };
    try { sessionStorage.setItem('pca-ga-return-context', JSON.stringify(context)); } catch (_) { /* Context is a convenience. */ }
  }

  function restoreContext() {
    const container = document.getElementById('recordReturn');
    const link = document.getElementById('recordReturnLink');
    const sequence = document.getElementById('recordSequence');
    if (!container || !link) return;
    let context;
    try { context = JSON.parse(sessionStorage.getItem('pca-ga-return-context')); } catch (_) { context = null; }
    if (!context?.href) return;
    link.textContent = `← ${context.label || 'Back to results'}`;
    link.href = context.href;
    link.addEventListener('click', () => {
      try { sessionStorage.setItem('pca-ga-restore-scroll', JSON.stringify({ href: context.href, y: context.y || 0 })); } catch (_) { /* No persistence needed. */ }
    });
    if (context.items?.length && context.position >= 0 && sequence) {
      const previous = context.items[context.position - 1];
      const next = context.items[context.position + 1];
      sequence.hidden = false;
      sequence.innerHTML = `${context.position + 1} of ${context.items.length}${previous ? ` <a href="${previous.href}" aria-label="Previous result">‹</a>` : ''}${next ? ` <a href="${next.href}" aria-label="Next result">›</a>` : ''}`;
    }
    container.hidden = false;
  }

  function restoreScroll() {
    let restore;
    try { restore = JSON.parse(sessionStorage.getItem('pca-ga-restore-scroll')); } catch (_) { restore = null; }
    if (!restore || new URL(restore.href, location.href).pathname !== location.pathname) return;
    sessionStorage.removeItem('pca-ga-restore-scroll');
    window.setTimeout(() => window.scrollTo({ top: restore.y || 0, behavior: 'auto' }), 650);
  }

  function renderBrowseRecent() {
    const section = document.getElementById('recentBrowse');
    const list = document.getElementById('recentBrowseList');
    if (!section || !list || !store) return;
    const records = store.listRecent().slice(0, 3);
    if (!records.length) return;
    list.innerHTML = records.map((record) => `<a href="${record.url}"><span>${record.type}</span><strong>${record.title}</strong></a>`).join('');
    section.hidden = false;
  }

  document.addEventListener('click', recordContext);
  document.querySelectorAll('[data-share-app]').forEach((button) => button.addEventListener('click', async () => {
    const url = document.querySelector('.topbar-brand')?.href || `${location.origin}/`;
    try {
      if (navigator.share) await navigator.share({ title: 'PCA General Assembly Minutes', url });
      else { await copyText(url); showToast('App link copied'); }
    } catch (_) { /* A dismissed share sheet is not an error state. */ }
  }));

  decoratePageMarkers();
  enhanceCaseHeader();
  enhanceCollectionHeader();
  makeTablesResponsive();
  injectBadges();
  restoreContext();
  restoreScroll();
  renderBrowseRecent();

  const pageFindState = { matches: [], index: -1, query: '' };

  function pageFindRoots() {
    return [...document.querySelectorAll('.reading-col')];
  }

  function createPageFind() {
    const finder = document.createElement('section');
    finder.className = 'page-find';
    finder.id = 'pageFind';
    finder.hidden = true;
    finder.setAttribute('role', 'dialog');
    finder.setAttribute('aria-label', 'Find in page');
    finder.innerHTML = `<label class="visually-hidden" for="pageFindInput">Find in page</label>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="11" cy="11" r="6.5" stroke="currentColor" stroke-width="1.8"/><path d="m16 16 4 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
      <input id="pageFindInput" type="search" autocomplete="off" enterkeyhint="search" placeholder="Find in this page">
      <output id="pageFindCount" aria-live="polite"></output>
      <button type="button" class="page-find__step" data-page-find-previous aria-label="Previous match">‹</button>
      <button type="button" class="page-find__step" data-page-find-next aria-label="Next match">›</button>
      <button type="button" class="page-find__close" data-page-find-close aria-label="Close find">×</button>`;
    document.body.appendChild(finder);
    return finder;
  }

  function clearPageFindHighlights() {
    pageFindState.matches = [];
    pageFindState.index = -1;
    if ('highlights' in CSS) {
      CSS.highlights.delete('pca-page-find');
      CSS.highlights.delete('pca-page-find-active');
    }
  }

  function collectPageFindMatches(query) {
    const matches = [];
    const needle = query.toLocaleLowerCase();
    pageFindRoots().forEach((root) => {
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
        acceptNode(node) {
          if (!node.nodeValue.trim() || node.parentElement?.closest('script, style, [data-page-find-ignore]')) return NodeFilter.FILTER_REJECT;
          return NodeFilter.FILTER_ACCEPT;
        },
      });
      while (walker.nextNode()) {
        const text = walker.currentNode.nodeValue;
        let start = text.toLocaleLowerCase().indexOf(needle);
        while (start !== -1) {
          const range = document.createRange();
          range.setStart(walker.currentNode, start);
          range.setEnd(walker.currentNode, start + query.length);
          matches.push(range);
          start = text.toLocaleLowerCase().indexOf(needle, start + query.length);
        }
      }
    });
    return matches;
  }

  function showPageFindMatch(index, { scroll = true } = {}) {
    const finder = document.getElementById('pageFind');
    const count = document.getElementById('pageFindCount');
    const total = pageFindState.matches.length;
    if (!total) {
      pageFindState.index = -1;
      if ('highlights' in CSS) CSS.highlights.delete('pca-page-find-active');
      count.textContent = pageFindState.query ? 'No matches' : '';
      finder?.classList.toggle('page-find--empty', Boolean(pageFindState.query));
      return;
    }
    pageFindState.index = (index + total) % total;
    const active = pageFindState.matches[pageFindState.index];
    if ('highlights' in CSS) CSS.highlights.set('pca-page-find-active', new Highlight(active));
    else {
      const selection = getSelection();
      selection.removeAllRanges();
      selection.addRange(active);
    }
    finder?.classList.remove('page-find--empty');
    count.textContent = `${pageFindState.index + 1} of ${total}`;
    if (scroll) active.startContainer.parentElement?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  function updatePageFind(query) {
    clearPageFindHighlights();
    pageFindState.query = query.trim();
    if (!pageFindState.query) {
      showPageFindMatch(-1);
      return;
    }
    pageFindState.matches = collectPageFindMatches(pageFindState.query);
    if ('highlights' in CSS && pageFindState.matches.length) CSS.highlights.set('pca-page-find', new Highlight(...pageFindState.matches));
    showPageFindMatch(0);
  }

  function openPageFind() {
    const finder = document.getElementById('pageFind') || createPageFind();
    finder.hidden = false;
    const input = finder.querySelector('input');
    input.focus();
    input.select();
  }

  function closePageFind() {
    const finder = document.getElementById('pageFind');
    if (!finder) return;
    finder.hidden = true;
    clearPageFindHighlights();
    pageFindState.query = '';
    const selection = getSelection();
    selection.removeAllRanges();
  }

  document.addEventListener('click', (event) => {
    if (event.target.closest('[data-page-find-open]')) { openPageFind(); return; }
    if (event.target.closest('[data-page-find-close]')) { closePageFind(); return; }
    if (event.target.closest('[data-page-find-previous]')) { showPageFindMatch(pageFindState.index - 1); return; }
    if (event.target.closest('[data-page-find-next]')) { showPageFindMatch(pageFindState.index + 1); }
  });

  document.addEventListener('input', (event) => {
    if (event.target.id === 'pageFindInput') updatePageFind(event.target.value);
  });

  document.addEventListener('keydown', (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'f') {
      event.preventDefault();
      openPageFind();
      return;
    }
    if (event.target.id !== 'pageFindInput') return;
    if (event.key === 'Enter') {
      event.preventDefault();
      showPageFindMatch(pageFindState.index + (event.shiftKey ? -1 : 1));
    }
  });

})();
