'use strict';

(() => {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const menuBtn = document.getElementById('menuBtn');
  const sbClose = document.getElementById('sidebarClose');
  const store = window.PCAResearch;

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
    if (!document.getElementById('citationSheet')?.hidden) closeCitation();
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
  let citationFormat = 'full';

  function openCitation(meta) {
    activeCitation = meta;
    citationFormat = 'full';
    const sheet = document.getElementById('citationSheet') || createSheet();
    sheet.hidden = false;
    document.body.classList.add('sheet-open');
    updateCitationSheet();
    sheet.querySelector('[data-citation-format="full"]')?.focus();
  }

  function closeCitation() {
    document.getElementById('citationSheet')?.setAttribute('hidden', '');
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
    if (close) { closeCitation(); return; }
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
    if (disposition) {
      const status = document.createElement('span');
      status.className = `record-header__disposition badge badge--${DISPS[disposition.toLowerCase()] || 'administrative'}`;
      status.textContent = disposition;
      content.before(status);
    }
    header.classList.add('is-ready');

    const meta = sourceCitation(header);
    store?.addRecent({ ...meta, citation: meta.short });
    const saveButton = header.querySelector('[data-record-save]');
    const setSave = (saved) => {
      saveButton.classList.toggle('is-saved', saved);
      saveButton.setAttribute('aria-pressed', String(saved));
      saveButton.innerHTML = saved ? '<span aria-hidden="true">▰</span> Saved' : '<span aria-hidden="true">▱</span> Save';
    };
    setSave(Boolean(store?.isSaved(meta)));
    saveButton.addEventListener('click', () => {
      const saved = store?.toggleSaved({ ...meta, citation: meta.short });
      setSave(saved);
      showToast(saved ? 'Saved to My Research' : 'Removed from My Research');
    });
    header.querySelector('[data-record-cite]')?.addEventListener('click', () => openCitation(meta));
    header.querySelector('[data-record-share]')?.addEventListener('click', async () => {
      try {
        if (navigator.share) await navigator.share({ title: meta.title, text: meta.short, url: meta.url });
        else { await copyText(meta.url); showToast('Link copied'); }
      } catch (_) { /* A dismissed share sheet is not an error state. */ }
    });
  }

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
      const marker = document.createElement('div');
      marker.className = 'page-marker';
      marker.id = `ga${ga}-p${page}`;
      marker.innerHTML = `<a href="#ga${ga}-p${page}">M${ga}GA p.${page}</a><button type="button" aria-label="Copy link to M${ga}GA p.${page}">↗</button>`;
      marker.querySelector('button').addEventListener('click', () => copyText(`${pageUrl()}#ga${ga}-p${page}`).then(() => showToast(`Link to M${ga}GA p.${page} copied`)));
      comment.replaceWith(marker);
    });
  }

  const DISPS = {
    sustained: 'sustained', 'not sustained': 'not-sustained', denied: 'denied', dismissed: 'dismissed',
    withdrawn: 'withdrawn', moot: 'moot', administrative: 'administrative', remanded: 'remanded', remitted: 'remanded',
  };

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
  injectBadges();
  restoreContext();
  restoreScroll();
  renderBrowseRecent();
})();
