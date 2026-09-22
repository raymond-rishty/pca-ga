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

  const FOCUSABLE = 'a[href], area[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  let activeModal = null;
  let modalBackground = new Map();

  function focusableIn(container) {
    return [...container.querySelectorAll(FOCUSABLE)].filter((element) => !element.closest('[hidden]') && !element.closest('[inert]'));
  }

  function openModal(element) {
    if (activeModal && activeModal !== element) closeModal(activeModal);
    activeModal = element;
    modalBackground = new Map();
    document.querySelectorAll('body > *').forEach((sibling) => {
      if (sibling === element) return;
      modalBackground.set(sibling, sibling.inert);
      sibling.inert = true;
    });
  }

  function closeModal(element) {
    if (element && activeModal !== element) return;
    modalBackground.forEach((wasInert, sibling) => { sibling.inert = wasInert; });
    modalBackground.clear();
    activeModal = null;
  }

  function trapFocus(element, event) {
    if (event.key !== 'Tab') return false;
    const items = focusableIn(element);
    if (!items.length) {
      event.preventDefault();
      return true;
    }
    const first = items[0];
    const last = items[items.length - 1];
    if (!element.contains(document.activeElement)) {
      event.preventDefault();
      first.focus();
    } else if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
    return true;
  }

  window.PCAFocus = { openModal, closeModal, trapFocus };

  function openSidebar() {
    sidebar?.removeAttribute('inert');
    sidebar?.classList.add('open');
    overlay?.classList.add('active');
    menuBtn?.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
    sbClose?.focus();
  }

  function closeSidebar() {
    const wasOpen = sidebar?.classList.contains('open');
    sidebar?.classList.remove('open');
    sidebar?.setAttribute('inert', '');
    overlay?.classList.remove('active');
    menuBtn?.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
    if (wasOpen) menuBtn?.focus();
  }

  menuBtn?.addEventListener('click', () => sidebar?.classList.contains('open') ? closeSidebar() : openSidebar());
  sbClose?.addEventListener('click', closeSidebar);
  overlay?.addEventListener('click', closeSidebar);
  document.addEventListener('keydown', (event) => {
    const pageFind = document.getElementById('pageFind');
    if (event.key === 'Escape') {
      if (pageFind && !pageFind.hidden) { closePageFind(); return; }
      const openSheet = [...document.querySelectorAll('.research-sheet, .constitution-sheet, .scripture-sheet')].find((sheet) => !sheet.hidden);
      if (openSheet) {
        openSheet.querySelector('button[data-sheet-close], button[data-constitution-close], button[data-scripture-close]')?.click();
        return;
      }
      if (sidebar?.classList.contains('open')) { closeSidebar(); return; }
    }
    if (event.key === 'Tab') {
      const openSheet = [...document.querySelectorAll('.research-sheet, .constitution-sheet, .scripture-sheet')].find((sheet) => !sheet.hidden);
      if (openSheet && trapFocus(openSheet.querySelector('[role="dialog"]') || openSheet, event)) return;
      if (sidebar?.classList.contains('open')) trapFocus(sidebar, event);
    }
  });

  function pageUrl() {
    return `${location.origin}${location.pathname}`;
  }

  function scrollBehavior() {
    return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth';
  }

  function compactCaseTitle(value) {
    let text = String(value || '').replace(/^\s*(?:Case\s+)?\d{4}-\d+[a-z]?\s*[—-]\s*/i, '').replace(/\s+Presbytery\b/gi, '').trim();
    const parts = text.split(/\s+v(?:s?\.)?\s+/i);
    if (parts.length !== 2) return text;
    const party = (value) => {
      let item = value.trim().replace(/^\s*(?:TE|RE|Rev\.?|Elder)\s+/i, '');
      if (/\b(?:Session|Church|PCA|Presbytery)\b/i.test(item)) return item;
      return item.split(/\s+(?:and|&)\s+/i).map((piece) => {
        const suffix = /\bet\.?\s+al\.?\s*$/i.test(piece) ? ' et al.' : '';
        const clean = piece.replace(/\s+et\.?\s+al\.?\s*$/i, '').trim();
        const words = clean.split(/\s+/);
        return `${words.length > 1 ? words[words.length - 1] : clean}${suffix}`;
      }).join(' and ');
    };
    const respondent = parts[1].replace(/\bMetropolitan New York\b/ig, 'Metro NY').replace(/\bPresbytery\b/ig, '').trim();
    return `${party(parts[0])} v. ${respondent}`;
  }

  function sourceCitation(header) {
    const rawTitle = header.querySelector('h1')?.textContent.trim() || `Judicial Case ${header.dataset.case}`;
    const title = compactCaseTitle(rawTitle);
    const source = header.querySelector('.record-header__content p:last-child')?.textContent || '';
    const pages = source.match(/pp?\.\s*(\d+)(?:\s*[–-]\s*(\d+))?/i);
    const ga = header.dataset.ga;
    const range = pages ? `M${ga}GA ${pages[2] ? `pp. ${pages[1]}–${pages[2]}` : `p. ${pages[1]}`}` : `${ga}th General Assembly`;
    const url = pageUrl();
    const docket = header.dataset.case;
    const short = docket ? `${docket} ${title}` : range;
    const full = docket ? `Case ${docket}: ${title}, ${range.replace(/^M(\d+GA)\s*/, 'M$1, ')}` : `${title} — ${range}`;
    return {
      id: url,
      url,
      title,
      type: 'Judicial case',
      short,
      full,
      markdown: `[${full}](${url})`,
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
  let activeSheetOpener;
  let activePage;
  let citationFormat = 'full';

  function openCitation(meta, opener) {
    activeCitation = meta;
    citationFormat = 'full';
    const sheet = document.getElementById('citationSheet') || createSheet();
    closeResearchSheets();
    activeSheetOpener = opener;
    sheet.hidden = false;
    document.body.classList.add('sheet-open');
    updateCitationSheet();
    sheet.querySelector('[data-citation-format="full"]')?.focus();
  }

  function closeCitation() {
    closeResearchSheets();
  }

  function closeResearchSheets() {
    const opener = activeSheetOpener;
    activeSheetOpener = null;
    document.querySelectorAll('.research-sheet').forEach((sheet) => sheet.setAttribute('hidden', ''));
    closeModal();
    document.body.classList.remove('sheet-open');
    if (opener?.isConnected) opener.focus();
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
    header.querySelector('[data-record-cite]')?.addEventListener('click', (event) => openCitation(meta, event.currentTarget));
    header.querySelector('[data-record-share]')?.addEventListener('click', async () => {
      const shareButton = header.querySelector('[data-record-share]');
      if (shareButton.hasAttribute('data-record-copy-link')) {
        await copyText(meta.url);
        showToast('Link copied');
        return;
      }
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

  function pageMeta(ga, page, { printed = true, printedSource = null } = {}) {
    const short = `M${ga}GA ${printed ? 'p.' : 'PDF p.'}${page}`;
    const anchor = printed ? `ga${ga}-p${page}` : `ga${ga}-pdf-p${page}`;
    const url = `${pageUrl()}#${anchor}`;
    const recordTitle = document.querySelector('.record-header h1, .reading-col > h1')?.textContent.trim() || 'PCA General Assembly Minutes';
    return {
      id: url,
      url,
      title: `${recordTitle} — ${short}`,
      type: printed ? 'Printed minutes page' : 'PDF page',
      short,
      full: `${recordTitle} — ${short}. ${url}`,
      markdown: `[${short}](${url}) — ${recordTitle}.`,
      citation: short,
      ga: Number(ga),
      pdfPage: null,
      printed,
      printedSource,
    };
  }

  function sourcePdfUrlForMeta(meta) {
    if (meta?.sourcePdfUrl) return meta.sourcePdfUrl;
    if (!Number.isInteger(meta?.pdfPage) || meta.pdfPage < 1) return null;

    const links = [...document.querySelectorAll('.source-pdf-link[href]')];
    const link = links.find((candidate) => {
      const sourceId = candidate.dataset.sourceId || '';
      const sourceVolume = sourceId.match(/^minutes:ga0*(\d+)_\d{4}$/i)?.[1];
      if (sourceVolume) return Number(sourceVolume) === meta.ga;

      const filename = candidate.href.match(/\/(\d+)(?:st|nd|rd|th)_pcaga_\d{4}\.pdf(?:[#?]|$)/i)?.[1];
      return filename ? Number(filename) === meta.ga : false;
    });
    if (!link) return null;

    const url = new URL(link.href, location.href);
    url.hash = `page=${meta.pdfPage}`;
    return url.href;
  }

  function setSourcePdfAction(button, meta) {
    if (!button) return;
    const sourceUrl = sourcePdfUrlForMeta(meta);
    button.hidden = !sourceUrl;
    button.dataset.sourceUrl = sourceUrl || '';
    if (sourceUrl) button.setAttribute('href', sourceUrl);
    else button.removeAttribute('href');
    button.innerHTML = '<span aria-hidden="true">↗</span><span>Open source PDF</span>';
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
          <a href="#" data-page-action="source-pdf" target="_blank" rel="noopener noreferrer" hidden></a>
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

  function openPageActions(meta, opener) {
    activePage = meta;
    const sheet = document.getElementById('pageActionSheet') || createPageActionSheet();
    closeResearchSheets();
    activeSheetOpener = opener;
    sheet.querySelector('#pageActionTitle').textContent = meta.short;
    sheet.querySelector('#pageActionContext').textContent = meta.printed
      ? meta.printedSource === 'inferred'
        ? 'Save, cite, or share a link that opens at this printed page, inferred from a verified pagination run.'
        : 'Save, cite, or share a link that opens at this exact printed page.'
      : 'Save, cite, or share a link to this source PDF page; no printed folio was detected.';
    setPageSaveButton(sheet.querySelector('[data-page-action="save"]'), Boolean(store?.isSaved(meta)));
    setSourcePdfAction(sheet.querySelector('[data-page-action="source-pdf"]'), meta);
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
      return;
    }
    if (action === 'source-pdf') {
      // Keep a fallback for an older cached sheet; the current path is the anchor href.
      const sourceUrl = button.dataset.sourceUrl;
      if (sourceUrl && !button.getAttribute('href')) window.open(sourceUrl, '_blank', 'noopener,noreferrer');
      return;
    }
  });

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-source-pdf-actions]');
    if (!button) return;
    const sourceUrl = button.dataset.sourceUrl;
    const label = button.dataset.sourceLabel || 'Source PDF page';
    if (!sourceUrl) return;
    const page = pageUrl();
    const title = document.querySelector('.record-header h1, .reading-col > h1')?.textContent.trim() || 'PCA record';
    openPageActions({
      id: `${page}#source-pdf-${encodeURIComponent(label)}`,
      url: page,
      title: `${title} — ${label}`,
      type: 'Source PDF page',
      short: label,
      full: `${title} — ${label}. ${page}`,
      markdown: `[${label}](${page}) — ${title}.`,
      sourcePdfUrl: new URL(sourceUrl, location.href).href,
      printed: true,
    }, button);
  });

  function decoratePageMarkers() {
    const column = document.querySelector('.reading-col');
    if (!column) return;
    const walker = document.createTreeWalker(column, NodeFilter.SHOW_COMMENT);
    const comments = [];
    while (walker.nextNode()) comments.push(walker.currentNode);
    comments.forEach((comment) => {
      const match = comment.nodeValue.match(/\bPAGE\s+ga=(\d+)\s+pdf_page=(\d+)\s+printed_page=([^\s]+)(?:\s+printed_page_source=([^\s]+))?/i);
      if (!match) return;
      const [, ga, pdfPage, printedPage, printedSource] = match;
      // Markdown renderers can put a standalone page comment and its empty
      // deep-link anchor in a paragraph. Promote both as one page-break unit so
      // the marker becomes a direct child of the reading column and can
      // establish a sticky page boundary.
      const parent = comment.parentElement;
      const isEmptyPageAnchor = (node) => node.nodeType === Node.ELEMENT_NODE
        && node.tagName === 'A'
        && node.hasAttribute('id')
        && !node.hasAttribute('href')
        && !node.textContent.trim();
      const isPageBreakParagraph = parent?.tagName === 'P'
        && [...parent.childNodes].every((node) => node === comment
          || (node.nodeType === Node.TEXT_NODE && !node.nodeValue.trim())
          || isEmptyPageAnchor(node));
      if (isPageBreakParagraph) {
        const breakNodes = [...parent.childNodes]
          .filter((node) => node === comment || isEmptyPageAnchor(node));
        parent.before(...breakNodes);
        parent.remove();
      }
      const printed = printedPage.toLowerCase() !== 'null';
      const page = printed ? printedPage : pdfPage;
      const meta = pageMeta(ga, page, { printed, printedSource });
      meta.pdfPage = Number(pdfPage);
      meta.printedPage = printed ? printedPage : null;
      const marker = document.createElement('div');
      marker.className = 'page-marker';
      const anchor = printed ? `ga${ga}-p${page}` : `ga${ga}-pdf-p${page}`;
      marker.id = anchor;
      marker.innerHTML = `<a href="#${anchor}">${meta.short}</a><button type="button" class="page-marker__actions" aria-label="Actions for ${meta.short}">${ICONS.page()}<span>Page actions</span></button>`;
      marker.querySelector('button').addEventListener('click', (event) => openPageActions(meta, event.currentTarget));
      comment.replaceWith(marker);
    });

    // A page marker needs its own containing block for sticky positioning.  That
    // lets the following marker naturally push it away at the next page break,
    // rather than leaving every earlier page number pinned at the top of the
    // entire minutes record.
    const markers = [...column.children].filter((child) => child.classList.contains('page-marker'));
    markers.forEach((marker) => {
      const anchor = marker.previousElementSibling?.matches('a[id]')
        ? marker.previousElementSibling
        : null;
      const page = document.createElement('div');
      page.className = 'minutes-page';
      (anchor || marker).before(page);
      if (anchor) page.append(anchor);
      page.append(marker);

      let sibling = page.nextElementSibling;
      while (sibling
        && !sibling.classList.contains('page-marker')
        && !(sibling.matches('a[id]') && sibling.nextElementSibling?.classList.contains('page-marker'))) {
        const next = sibling.nextElementSibling;
        page.append(sibling);
        sibling = next;
      }
    });
  }

  const DISPS = {
    sustained: 'sustained', 'not sustained': 'not-sustained', denied: 'denied', dismissed: 'dismissed',
    withdrawn: 'withdrawn', moot: 'moot', administrative: 'administrative', remanded: 'remanded', remitted: 'remanded',
  };

  function makeTablesResponsive() {
    const indexVariant = document.body.dataset.indexVariant || '';
    const isCatalogueIndex = Boolean(indexVariant);
    const isCaseIndex = /\/index\/CASES\.html$/i.test(location.pathname);
    const isProvisionIndex = /\/index\/(?:CASES-BY-PROVISION|RPR-BY-PROVISION)\.html$/i.test(location.pathname);
    const isCaseProvisionIndex = /\/index\/CASES-BY-PROVISION\.html$/i.test(location.pathname);
    const isInquiryIndex = /\/index\/(?:INQUIRIES|CCB-OVERTURE-ADVICE)\.html$/i.test(location.pathname);
    document.querySelectorAll('.reading-col table').forEach((table) => {
      const header = table.tHead?.rows[0] || table.rows[0];
      const labels = header ? [...header.cells].map((cell) => cell.textContent.replace(/\s+/g, ' ').trim()) : [];
      if (labels.length < 2 && !isCatalogueIndex && !isProvisionIndex) return;

      // This index is generated entirely as provision-audit tables.  Do not
      // depend on header text here: Markdown table parsing can normalize a
      // header differently across renderers, leaving the table unwrapped on
      // narrow screens.
      const isProvisionAudit = isCaseProvisionIndex;
      const isCaseTable = isCaseIndex
        && ['Case', 'Parties / Title', 'Disposition', 'Summary', 'Page']
          .every((label) => labels.includes(label));
      const isInquiryTable = isInquiryIndex
        && ['Inquiry', 'Subject', 'Synopsis', 'Provisions', 'Outcome', 'From', 'Minutes']
          .every((label) => labels.includes(label));
      if (isCaseTable) table.classList.add('case-index-table');
      if (isProvisionAudit) table.classList.add('case-provision-table');
      if (isInquiryTable) table.classList.add('inquiry-table');
      if (['Overture', 'Subject', 'Outcome', 'Source', 'Pages'].every((label) => labels.includes(label))) table.classList.add('overture-table');
      if (['Document', 'Type', 'Assembly', 'Outcome', 'Provenance', 'Source'].every((label) => labels.includes(label))) table.classList.add('study-table');

      let scroller = table.parentElement?.classList.contains('table-scroll')
        ? table.parentElement
        : null;
      if (!scroller) {
        scroller = document.createElement('div');
        scroller.className = 'table-scroll';
        table.before(scroller);
        scroller.append(table);
      }
      if (isCaseTable || isProvisionAudit) scroller.classList.add('table-scroll--case-index');
      table.querySelectorAll('a[href]').forEach((link) => {
        const href = new URL(link.href, location.href);
        if (!isRecordPath(href.pathname)) return;
        link.dataset.resultPrimary = '';
        link.dataset.resultType ||= labels[0] || 'Catalogue record';
        link.dataset.resultTitle ||= link.textContent.trim().replace(/\s+/g, ' ');
        const row = link.closest('tr');
        const cell = link.closest('td');
        if (!row || !cell || row.dataset.resultItem) return;
        row.dataset.resultItem = '';
        const actions = document.createElement('details');
        actions.className = 'result-actions';
        actions.innerHTML = `<summary>Actions</summary>
          <div class="result-actions__panel" aria-label="Actions for ${link.dataset.resultTitle}">
            <button type="button" data-result-action="save">Save</button>
            <button type="button" data-result-action="cite">Cite</button>
            <button type="button" data-result-action="link">Copy link</button>
          </div>`;
        cell.append(actions);
      });
      if (isCatalogueIndex) {
        scroller.classList.add('table-scroll--catalogue');
        scroller.tabIndex = 0;
        scroller.setAttribute('role', 'region');
        scroller.setAttribute('aria-label', 'Scrollable catalogue table: ' + labels.join(', '));
      }
    });
  }

  function catalogueCellText(cell) {
    return cell ? cell.textContent.replace(/\s+/g, ' ').trim() : '';
  }

  function catalogueDigestCitation(numberText, sourceCell) {
    const sourceAnchor = sourceCell?.querySelector('a[href]');
    const sourceText = sourceAnchor?.textContent.replace(/\s+/g, ' ').trim() || '';
    const sourceHref = sourceAnchor?.getAttribute('href') || '';
    const year = sourceText.match(/_(\d{4})\b/)?.[1] || sourceHref.match(/_(\d{4})\b/)?.[1] || '';
    const page = sourceText.match(/\bp\.\s*(\d+[a-z]?)\b/i)?.[1] || '';
    if (!year || !page || !numberText) return '';
    let locator = numberText.replace(/\s+/g, ' ').trim();
    if (/^App\. O\b/i.test(locator)) locator = locator.replace(/^App\. O\s*/i, 'App. O, ');
    return `${year}, p. ${page}, ${locator}.`;
  }

  function catalogueCopyCell(cell, target) {
    if (!cell) return;
    [...cell.childNodes].forEach((node) => {
      if (node.nodeType === Node.ELEMENT_NODE && node.matches('.result-actions')) return;
      target.append(node.cloneNode(true));
    });
  }

  function catalogueCell(cells, labels, pattern) {
    const index = labels.findIndex((label) => pattern.test(label));
    return index >= 0 ? cells[index] : null;
  }

  function catalogueDispositionClass(value) {
    if (/conflict|denied|declined|negative|rejected|not sustained/.test(value)) return 'catalogue-record__badge--negative';
    if (/adopted|approved|answered|sustained|affirmed|in accord/.test(value)) return 'catalogue-record__badge--positive';
    if (/referred|received|continued|pending|moot/.test(value)) return 'catalogue-record__badge--neutral';
    return '';
  }

  function catalogueMeta(parent, label, value) {
    if (!value) return;
    const item = document.createElement('span');
    item.className = 'catalogue-record__meta-item';
    const labelElement = document.createElement('span');
    labelElement.className = 'catalogue-record__meta-label';
    labelElement.textContent = label;
    item.append(labelElement, document.createTextNode(value));
    parent.append(item);
  }

  function catalogueAction(anchor, label, primary = false) {
    if (!anchor) return null;
    const link = anchor.cloneNode(true);
    link.className = primary ? 'catalogue-record__action catalogue-record__action--primary' : 'catalogue-record__action';
    link.textContent = label;
    return link;
  }

  function catalogueActions() {
    const actions = document.createElement('details');
    actions.className = 'result-actions catalogue-record__actions';
    actions.innerHTML = '<summary>Actions</summary><div class="result-actions__panel" aria-label="Record actions"><button type="button" data-result-action="save">Save</button><button type="button" data-result-action="cite">Cite</button><button type="button" data-result-action="link">Copy link</button></div>';
    return actions;
  }

  function buildCatalogueRecord(row, labels, groupLabel, variant) {
    const cells = [...row.cells];
    const numberCell = catalogueCell(cells, labels, /^(inquiry|overture)$/);
    const titleCell = variant === 'study'
      ? catalogueCell(cells, labels, /^document$/)
      : catalogueCell(cells, labels, /^subject$/);
    const synopsisCell = catalogueCell(cells, labels, /^synopsis$/);
    const provisionsCell = catalogueCell(cells, labels, /^provisions?$/);
    const outcomeCell = catalogueCell(cells, labels, /^(outcome|disposition)$/);
    const fromCell = catalogueCell(cells, labels, /^(from|originating|source body)$/);
    const assemblyCell = catalogueCell(cells, labels, /^assembly$/);
    const typeCell = catalogueCell(cells, labels, /^type$/);
    const provenanceCell = catalogueCell(cells, labels, /^provenance$/);
    const sourceCell = catalogueCell(cells, labels, /^(minutes|source)$/);
    const numberText = catalogueCellText(numberCell);
    const titleText = catalogueCellText(titleCell);
    const synopsisText = catalogueCellText(synopsisCell);
    const outcomeText = catalogueCellText(outcomeCell);
    const provenanceText = catalogueCellText(provenanceCell);
    const statusText = variant === 'study'
      ? outcomeText.replace(/\s*\([^)]*\)\s*$/, '')
      : outcomeText;
    const primaryAnchor = titleCell?.querySelector('a[href]');
    const sourceAnchor = sourceCell?.querySelector('a[href]');
    const record = document.createElement('article');
    record.className = 'catalogue-record catalogue-record--' + variant;
    record.dataset.catalogueRecord = '';
    record.dataset.catalogueStatus = statusText.toLocaleLowerCase();
    record.dataset.searchText = [
      groupLabel, numberText, titleText, synopsisText, catalogueCellText(provisionsCell),
      outcomeText, catalogueCellText(fromCell), catalogueCellText(assemblyCell),
      catalogueCellText(typeCell), provenanceText, catalogueCellText(sourceCell),
    ].join(' ').toLocaleLowerCase();

    const layout = document.createElement('div');
    layout.className = 'catalogue-record__layout';
    const main = document.createElement('div');
    main.className = 'catalogue-record__main';
    const eyebrow = document.createElement('p');
    eyebrow.className = 'catalogue-record__eyebrow';
    if (variant === 'ccb') {
      const kind = document.createElement('span');
      kind.className = 'catalogue-record__eyebrow-kind';
      kind.textContent = 'CCB advice';
      eyebrow.append(kind);
    }
    if (variant === 'study') {
      const typeText = catalogueCellText(typeCell);
      const assemblyText = catalogueCellText(assemblyCell);
      const assemblyLabel = assemblyText.replace(/^(\d+(?:st|nd|rd|th))\s+\((\d{4})\)$/, '$1 GA ($2)');
      const assembly = document.createElement('span');
      assembly.className = 'catalogue-record__eyebrow-context';
      assembly.textContent = [typeText, assemblyLabel].filter(Boolean).join(' · ');
      eyebrow.append(assembly);
    } else if (groupLabel) {
      const group = document.createElement('span');
      group.className = 'catalogue-record__eyebrow-context';
      group.textContent = groupLabel;
      eyebrow.append(group);
    }
    if (numberText) {
      const number = document.createElement('span');
      number.className = 'catalogue-record__eyebrow-id';
      number.textContent = numberText;
      eyebrow.append(number);
    }
    main.append(eyebrow);

    const title = document.createElement('h3');
    title.className = 'catalogue-record__title';
    catalogueCopyCell(titleCell, title);
    if (!title.textContent.trim()) title.textContent = titleText || 'Untitled record';
    const resultTitle = titleText || title.textContent.trim() || 'PCA record';
    const resultCitation = variant === 'study' ? '' : catalogueDigestCitation(numberText, sourceCell);
    record.dataset.resultItem = '';
    record.dataset.resultTitle = resultTitle;
    record.dataset.resultType = variant === 'study' ? 'Study report' : variant === 'ccb' ? 'CCB advice' : 'Constitutional inquiry';
    if (resultCitation) record.dataset.resultCitation = resultCitation;
    const resultPrimary = title.querySelector('a[href]');
    if (resultPrimary) {
      resultPrimary.dataset.resultPrimary = '';
      resultPrimary.dataset.resultTitle = resultTitle;
      resultPrimary.dataset.resultType = record.dataset.resultType;
      if (resultCitation) resultPrimary.dataset.resultCitation = resultCitation;
    }
    main.append(title);

    if (synopsisText) {
      const synopsis = document.createElement('p');
      synopsis.className = 'catalogue-record__summary';
      catalogueCopyCell(synopsisCell, synopsis);
      main.append(synopsis);
    }

    const status = document.createElement('div');
    status.className = 'catalogue-record__status';
    if (variant === 'ccb') {
      const statusLabel = document.createElement('span');
      statusLabel.className = 'catalogue-record__status-label';
      statusLabel.textContent = 'CCB finding';
      status.append(statusLabel);
    } else if (variant === 'study') {
      const typeText = catalogueCellText(typeCell);
      if (typeText) {
        const typeBadge = document.createElement('span');
        typeBadge.className = 'catalogue-record__badge catalogue-record__badge--type';
        typeBadge.textContent = typeText;
        status.append(typeBadge);
      }
    } else {
      const statusLabel = document.createElement('span');
      statusLabel.className = 'catalogue-record__status-label';
      statusLabel.textContent = 'Disposition';
      status.append(statusLabel);
    }
    if (statusText) {
      const badge = document.createElement('span');
      badge.className = ('catalogue-record__badge ' + catalogueDispositionClass(statusText)).trim();
      badge.textContent = statusText;
      status.append(badge);
    }
    if (status.children.length) main.append(status);

    const meta = document.createElement('div');
    meta.className = 'catalogue-record__meta';
    if (variant !== 'study') {
      catalogueMeta(meta, 'Provisions', catalogueCellText(provisionsCell));
      catalogueMeta(meta, 'From', catalogueCellText(fromCell));
    }
    if (meta.children.length) main.append(meta);

    const rail = document.createElement('aside');
    rail.className = 'catalogue-record__rail';
    const primaryLabel = variant === 'ccb' ? 'Read advice' : variant === 'study' ? 'Read report' : 'Read inquiry';
    const primary = catalogueAction(primaryAnchor, primaryLabel, true);
    if (primary) rail.append(primary);
    if (sourceAnchor) {
      const sourceLabel = variant === 'study'
        ? (/pcahistory|pdf/i.test(sourceAnchor.href + ' ' + sourceCell.textContent) ? 'Source PDF' : 'Minutes')
        : 'Minutes';
      rail.append(catalogueAction(sourceAnchor, sourceLabel));
    }
    rail.append(catalogueActions());
    if (rail.children.length) layout.append(main, rail);
    else layout.append(main);
    record.append(layout);
    return record;
  }

  function enhanceCatalogueCards() {
    const root = document.querySelector('.reading-col--catalogue-index:not(.reading-col--case-index)');
    if (!root) return;
    const path = location.pathname;
    const variant = /\/index\/CCB-OVERTURE-ADVICE\.html$/i.test(path)
      ? 'ccb'
      : /\/index\/INQUIRIES\.html$/i.test(path)
        ? 'inquiry'
        : /\/index\/STUDIES\.html$/i.test(path)
          ? 'study'
          : '';
    if (!variant) return;
    const tables = [...root.querySelectorAll('table')];
    if (variant === 'study') {
      const records = document.createElement('div');
      records.className = 'catalogue-records catalogue-records--study';
      records.setAttribute('role', 'list');
      const topicHeading = [...root.querySelectorAll('h2')].find((heading) => /^By topic$/i.test(heading.textContent.trim()));
      if (topicHeading) topicHeading.textContent = 'Study reports';
      const provenanceHeading = [...root.querySelectorAll('h2')].find((heading) => /^Provenance counts$/i.test(heading.textContent.trim()));
      if (provenanceHeading) {
        let next = provenanceHeading.nextElementSibling;
        provenanceHeading.remove();
        while (next && next.tagName !== 'H2') {
          const current = next;
          next = next.nextElementSibling;
          current.remove();
        }
      }
      const firstContainer = tables[0]?.closest('.table-scroll') || tables[0];
      tables.forEach((table) => {
        const header = table.tHead?.rows[0] || table.rows[0];
        const labels = header
          ? [...header.cells].map((cell) => cell.textContent.replace(/\s+/g, ' ').trim().toLocaleLowerCase())
          : [];
        const rows = [...table.querySelectorAll('tbody tr')];
        const tableContainer = table.closest('.table-scroll') || table;
        let heading = tableContainer.previousElementSibling;
        while (heading && !/^H3$/.test(heading.tagName)) heading = heading.previousElementSibling;
        if (heading) heading.remove();
        rows.forEach((row) => {
          const record = buildCatalogueRecord(row, labels, '', 'study');
          record.setAttribute('role', 'listitem');
          records.append(record);
        });
        tableContainer.remove();
      });
      firstContainer?.before(records);
      root.classList.add('catalogue-cards-ready');
      return;
    }
    tables.forEach((table) => {
      const header = table.tHead?.rows[0] || table.rows[0];
      const labels = header
        ? [...header.cells].map((cell) => cell.textContent.replace(/\s+/g, ' ').trim().toLocaleLowerCase())
        : [];
      const rows = [...table.querySelectorAll('tbody tr')];
      if (!rows.length) return;
      const tableContainer = table.closest('.table-scroll') || table;
      let heading = tableContainer.previousElementSibling;
      while (heading && !/^H[23]$/.test(heading.tagName)) heading = heading.previousElementSibling;
      const groupLabel = heading
        ? heading.textContent.replace(/\s+/g, ' ').trim().split('·')[0].trim()
        : '';
      const records = document.createElement('div');
      records.className = 'catalogue-records catalogue-records--' + variant;
      records.setAttribute('role', 'list');
      rows.forEach((row) => {
        const record = buildCatalogueRecord(row, labels, groupLabel, variant);
        record.setAttribute('role', 'listitem');
        records.append(record);
      });
      tableContainer.replaceWith(records);
    });
    root.classList.add('catalogue-cards-ready');
  }

  function enhanceCatalogueIndex() {
    const root = document.querySelector('.reading-col--catalogue-index:not(.reading-col--case-index)');
    if (!root) return;
    const variant = document.body.dataset.indexVariant || '';
    if (/\/index\/RPR(?:-BY-PROVISION)?\.html$/i.test(location.pathname)
        || /\/rpr\/[^/]+\.html$/i.test(location.pathname)) return;
    if (variant === 'provision' || variant === 'legacy-case') return;
    const cardRecords = [...root.querySelectorAll('[data-catalogue-record]')];
    const usesCards = cardRecords.length > 0;
    const tables = [...root.querySelectorAll('table')];
    const rows = tables.flatMap((table) => [...table.tBodies].flatMap((body) => [...body.rows]));
    if (!rows.length && !cardRecords.length) return;

    const toolbar = document.createElement('div');
    toolbar.className = 'catalogue-tools';
    toolbar.setAttribute('role', 'search');
    const placeholder = usesCards
      ? (cardRecords.some((record) => record.classList.contains('catalogue-record--study'))
        ? 'Search title, topic, type, or source'
        : 'Search subject, synopsis, provision, or source')
      : 'Search title, subject, provision, or source';
    toolbar.innerHTML = '<div class="catalogue-tools__field"><label for="catalogueSearch">Search this catalogue</label><input id="catalogueSearch" type="search" placeholder="' + placeholder + '" autocomplete="off"></div><div class="catalogue-tools__field"><label for="catalogueStatus">Filter by status</label><select id="catalogueStatus"><option value="">All statuses</option></select></div><output id="catalogueResultCount" aria-live="polite"></output>';
    const insertionPoint = root.querySelector('h2, h3, table, .catalogue-records');
    insertionPoint?.before(toolbar);
    if (!insertionPoint) return;

    const search = toolbar.querySelector('#catalogueSearch');
    const status = toolbar.querySelector('#catalogueStatus');
    const count = toolbar.querySelector('#catalogueResultCount');
    const statusIndex = tables.map((table) => {
      const header = table.tHead?.rows[0] || table.rows[0];
      const labels = header ? [...header.cells].map((cell) => cell.textContent.trim().toLowerCase()) : [];
      return labels.findIndex((label) => /outcome|disposition|final|provenance/.test(label));
    });
    const rowRecords = usesCards
      ? cardRecords.map((record) => ({
        row: record,
        text: (record.dataset.searchText || record.textContent).toLocaleLowerCase(),
        rowStatus: record.dataset.catalogueStatus || '',
      }))
      : rows.map((row) => {
        const tableIndex = tables.findIndex((table) => table.contains(row));
        const cellIndex = statusIndex[tableIndex];
        const text = row.textContent.replace(/\s+/g, ' ').toLocaleLowerCase();
        const rowStatus = cellIndex >= 0 ? row.cells[cellIndex]?.textContent.trim().toLocaleLowerCase() : '';
        return { row, text, rowStatus };
      });
    const statuses = new Set(rowRecords.map(({ rowStatus }) => rowStatus).filter(Boolean));
    [...statuses].sort((a, b) => a.localeCompare(b)).forEach((value) => {
      const option = document.createElement('option');
      option.value = value.toLocaleLowerCase();
      option.textContent = value;
      status.append(option);
    });
    status.hidden = statuses.size < 2;
    status.parentElement.hidden = statuses.size < 2;

    const groups = usesCards
      ? [...root.querySelectorAll('.catalogue-records')].map((scroller) => {
        let heading = scroller.previousElementSibling;
        while (heading && !/^H[23]$/.test(heading.tagName)) heading = heading.previousElementSibling;
        return { scroller, heading };
      })
      : tables.map((table) => {
        const scroller = table.closest('.table-scroll') || table;
        let heading = scroller.previousElementSibling;
        while (heading && !/^H[23]$/.test(heading.tagName)) heading = heading.previousElementSibling;
        return { scroller, heading };
      });
    const update = () => {
      const query = search.value.toLocaleLowerCase().trim();
      const selectedStatus = status.value;
      let visible = 0;
      rowRecords.forEach(({ row, text, rowStatus }) => {
        const match = (!query || text.includes(query)) && (!selectedStatus || rowStatus === selectedStatus);
        row.hidden = !match;
        if (match) visible += 1;
      });
      groups.forEach(({ scroller, heading }) => {
        const hasVisible = usesCards
          ? scroller.querySelector('[data-catalogue-record]:not([hidden])')
          : scroller.querySelector('tbody tr:not([hidden])');
        scroller.hidden = !hasVisible;
        if (heading) heading.hidden = !hasVisible;
      });
      count.textContent = `${visible} ${visible === 1 ? 'record' : 'records'}`;
    };
    search.addEventListener('input', update);
    status.addEventListener('change', update);
    update();
  }
  function enhanceJudicialCatalogue() {
    const catalogue = document.getElementById('judicialCatalogue');
    if (!catalogue) return;
    const records = [...catalogue.querySelectorAll('[data-judicial-record]')];
    const search = document.getElementById('judicialCaseSearch');
    const jump = document.getElementById('judicialYearJump');
    const count = document.getElementById('judicialResultCount');
    const years = [...catalogue.querySelectorAll('[data-judicial-year]')];
    const synopsisRecords = records.filter((record) => record.querySelector('.judicial-case__summary'));
    const measureSynopsis = (record) => {
      const summary = record.querySelector('.judicial-case__summary');
      const toggle = record.querySelector('.judicial-case__summary-toggle');
      if (!summary || !toggle || !window.matchMedia('(max-width: 700px)').matches) {
        summary?.classList.remove('is-collapsed');
        if (toggle) toggle.hidden = true;
        return;
      }
      const expanded = toggle.getAttribute('aria-expanded') === 'true';
      summary.classList.toggle('is-collapsed', !expanded);
      const clipped = !expanded && summary.scrollHeight > summary.clientHeight + 1;
      if (!clipped) summary.classList.remove('is-collapsed');
      toggle.hidden = !clipped && !expanded;
      if (!toggle.hidden) toggle.textContent = expanded ? 'Show less' : 'Show full synopsis';
    };
    const measureAllSynopses = () => synopsisRecords.forEach(measureSynopsis);
    years.forEach((section) => {
      if (jump && section.dataset.judicialYear !== 'other' && !jump.querySelector(`option[value="${section.dataset.judicialYear}"]`)) {
        const option = document.createElement('option'); option.value = section.dataset.judicialYear; option.textContent = section.dataset.judicialYear; jump.append(option);
      }
    });
    const update = () => {
      const terms = (search?.value || '').toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
      let visible = 0;
      records.forEach((record) => {
        const match = terms.every((term) => (record.dataset.searchText || '').toLocaleLowerCase().includes(term));
        record.hidden = !match; if (match) visible += 1;
      });
      years.forEach((section) => { section.hidden = !section.querySelector('[data-judicial-record]:not([hidden])'); });
      if (count) count.textContent = `${visible} ${visible === 1 ? 'case' : 'cases'}`;
    };
    const syncUrl = () => {
      const url = new URL(location.href);
      if (search?.value.trim()) url.searchParams.set('q', search.value.trim());
      else url.searchParams.delete('q');
      if (jump?.value) url.searchParams.set('year', jump.value);
      else url.searchParams.delete('year');
      history.replaceState({}, '', `${url.pathname}${url.search}${url.hash}`);
    };
    const initialUrl = new URL(location.href);
    if (search && initialUrl.searchParams.has('q')) search.value = initialUrl.searchParams.get('q');
    if (jump && initialUrl.searchParams.has('year')) jump.value = initialUrl.searchParams.get('year');
    search?.addEventListener('input', () => { update(); syncUrl(); });
    jump?.addEventListener('change', () => {
      syncUrl();
      if (jump.value) document.querySelector(`[data-judicial-year="${CSS.escape(jump.value)}"]`)?.scrollIntoView({ behavior: scrollBehavior(), block: 'start' });
    });
    catalogue.addEventListener('click', async (event) => {
      const actionButton = event.target.closest('.judicial-actions__button');
      const action = event.target.closest('[data-judicial-action]');
      const record = event.target.closest('[data-judicial-record]');
      if (actionButton) {
        const menu = actionButton.nextElementSibling; const open = menu.hidden;
        document.querySelectorAll('.judicial-actions__menu').forEach((item) => { item.hidden = true; item.previousElementSibling?.setAttribute('aria-expanded', 'false'); });
        menu.hidden = !open; actionButton.setAttribute('aria-expanded', String(open)); if (open) menu.querySelector('button')?.focus(); return;
      }
      const summaryToggle = event.target.closest('.judicial-case__summary-toggle');
      if (summaryToggle) {
        const expanded = summaryToggle.getAttribute('aria-expanded') === 'true';
        summaryToggle.setAttribute('aria-expanded', String(!expanded));
        summaryToggle.textContent = expanded ? 'Show full synopsis' : 'Show less';
        const record = summaryToggle.closest('[data-judicial-record]');
        record?.querySelector('.judicial-case__summary')?.classList.toggle('is-collapsed', expanded);
        return;
      }
      const topicsToggle = event.target.closest('.judicial-topics__toggle');
      if (topicsToggle) {
        const expanded = topicsToggle.getAttribute('aria-expanded') === 'true';
        const extraTopics = document.getElementById(topicsToggle.getAttribute('aria-controls'));
        const topicCount = topicsToggle.dataset.topicCount;
        const topicNoun = Number(topicCount) === 1 ? 'topic' : 'topics';
        topicsToggle.setAttribute('aria-expanded', String(!expanded));
        topicsToggle.setAttribute('aria-label', expanded ? `Show ${topicCount} more ${topicNoun}` : 'Hide additional topics');
        topicsToggle.textContent = expanded ? `+${topicCount} ${topicNoun}` : 'Fewer topics';
        if (extraTopics) extraTopics.hidden = expanded;
        return;
      }
      const detailsToggle = event.target.closest('.judicial-details__toggle');
      if (detailsToggle) {
        const expanded = detailsToggle.getAttribute('aria-expanded') === 'true';
        const details = document.getElementById(detailsToggle.getAttribute('aria-controls'));
        const caseTitle = detailsToggle.closest('[data-judicial-record]')?.querySelector('h3')?.textContent.trim() || 'this case';
        detailsToggle.setAttribute('aria-expanded', String(!expanded));
        detailsToggle.setAttribute('aria-label', (expanded ? 'Show' : 'Hide') + ' details for ' + caseTitle);
        detailsToggle.textContent = expanded ? 'Show details' : 'Hide details';
        if (details) details.hidden = expanded;
        return;
      }
      if (!action || !record) return;
      const title = record.querySelector('h3')?.textContent.trim() || 'Judicial case';
      const url = new URL(record.querySelector('h3 a, .judicial-case__rail a')?.href || `#${record.id}`, location.href).href;
      const id = url;
      const short = record.dataset.judicialShortCitation || `${record.querySelector('.judicial-case__docket code')?.textContent || ''} ${compactCaseTitle(title)}`.trim();
      const full = record.dataset.judicialFullCitation || `Case ${short}`;
      const actionMenu = action.closest('.judicial-actions__menu');
      const actionTrigger = actionMenu?.previousElementSibling;
      let restoreMenuFocus = true;
      if (action.dataset.judicialAction === 'save') {
        const saved = store?.toggleSaved({ id, url, title, type: 'Judicial case', short, citation: short });
        const state = record.querySelector('[data-judicial-saved]'); if (state) state.hidden = !saved;
        action.textContent = saved ? 'Remove from bookshelf' : 'Save to bookshelf'; showToast(saved ? 'Added to your bookshelf' : 'Removed from your bookshelf');
      } else if (action.dataset.judicialAction === 'link') { await copyText(url); showToast('Link copied'); }
      else if (action.dataset.judicialAction === 'cite') { restoreMenuFocus = false; openCitation({ id, url, title, type: 'Judicial case', short, full, markdown: `[${full}](${url})` }, actionTrigger); }
      actionMenu.hidden = true; actionTrigger?.setAttribute('aria-expanded', 'false');
      if (restoreMenuFocus) actionTrigger?.focus();
    });
    catalogue.addEventListener('keydown', (event) => {
      const button = event.target.closest('.judicial-actions__button');
      const menuItem = event.target.closest('.judicial-actions__menu [role="menuitem"]');
      if (button && (event.key === 'ArrowDown' || event.key === 'ArrowUp')) {
        event.preventDefault();
        const menu = button.nextElementSibling;
        document.querySelectorAll('.judicial-actions__menu').forEach((item) => { item.hidden = true; item.previousElementSibling?.setAttribute('aria-expanded', 'false'); });
        menu.hidden = false; button.setAttribute('aria-expanded', 'true');
        const items = [...menu.querySelectorAll('[role="menuitem"]')];
        items[event.key === 'ArrowUp' ? items.length - 1 : 0]?.focus();
      } else if (menuItem && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        const items = [...menuItem.parentElement.querySelectorAll('[role="menuitem"]')];
        const index = items.indexOf(menuItem);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        items[next]?.focus();
      }
    });
    document.addEventListener('click', (event) => { if (!event.target.closest('.judicial-actions')) document.querySelectorAll('.judicial-actions__menu').forEach((menu) => { menu.hidden = true; menu.previousElementSibling?.setAttribute('aria-expanded', 'false'); }); });
    document.addEventListener('keydown', (event) => { if (event.key === 'Escape') document.querySelectorAll('.judicial-actions__menu').forEach((menu) => { if (!menu.hidden) { menu.hidden = true; menu.previousElementSibling?.setAttribute('aria-expanded', 'false'); menu.previousElementSibling?.focus(); } }); });
    records.forEach((record) => {
      const link = record.querySelector('h3 a, .judicial-case__rail a');
      const saved = store?.isSaved({ id: new URL(link?.href || `#${record.id}`, location.href).href });
      const state = record.querySelector('[data-judicial-saved]'); if (state) state.hidden = !saved;
    });
    measureAllSynopses();
    if (document.fonts?.ready) document.fonts.ready.then(measureAllSynopses);
    let synopsisResizeTimer;
    window.addEventListener('resize', () => {
      window.clearTimeout(synopsisResizeTimer);
      synopsisResizeTimer = window.setTimeout(measureAllSynopses, 120);
    }, { passive: true });
    update();
  }

  function enhanceProvisionIndex() {
    if (!/\/index\/(?:CASES-BY-PROVISION|RPR-BY-PROVISION)\.html$/i.test(location.pathname)) return;
    const provisions = [...document.querySelectorAll('.reading-col h2')];
    if (provisions.length < 2) return;
    const jump = document.createElement('nav');
    jump.className = 'provision-jump';
    jump.setAttribute('aria-label', 'Jump to constitutional provision');
    const options = provisions.map((heading, index) => {
      if (!heading.id) heading.id = `provision-${index + 1}`;
      return `<option value="#${heading.id}">${heading.textContent.trim()}</option>`;
    }).join('');
    jump.innerHTML = `<label for="provisionJump">Jump to</label><select id="provisionJump"><option value="">Choose a provision…</option>${options}</select>`;
    provisions[0].before(jump);
    jump.querySelector('select').addEventListener('change', (event) => {
      if (!event.target.value) return;
      const target = document.querySelector(event.target.value);
      if (target) {
        history.pushState({}, '', `#${target.id}`);
        target.scrollIntoView({ behavior: scrollBehavior(), block: 'start' });
      }
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

  function isRecordPath(pathname) {
    return /\/(?:cases|inquiries|overtures|rpr\/exc|studies|markdown)\//i.test(pathname);
  }

  function resultLinksForContext() {
    const seen = new Set();
    return [...document.querySelectorAll('[data-result-primary][href], .home-result[href], .rpr-card .home-result__title[href], [data-judicial-record] h3 a[href], .reading-col table a[href]')]
      .map((item) => {
        const href = new URL(item.href, location.href);
        return { href: href.href, title: item.textContent.trim().replace(/\s+/g, ' ') };
      })
      .filter((item) => isRecordPath(new URL(item.href).pathname) && !seen.has(item.href) && seen.add(item.href));
  }

  function resultActionMeta(action) {
    const item = action.closest('[data-result-item]') || action.closest('tr');
    const link = item?.querySelector('[data-result-primary][href]') || action.closest('td')?.querySelector('[data-result-primary][href]');
    if (!link) return null;
    const url = new URL(link.href, location.href).href;
    const title = item?.dataset.resultTitle || link.dataset.resultTitle || link.textContent.trim().replace(/\s+/g, ' ') || 'PCA record';
    const type = item?.dataset.resultType || link.dataset.resultType || 'PCA record';
    const citation = item?.dataset.resultCitation || link.dataset.resultCitation || '';
    const short = citation || title;
    const full = citation ? `${title}, ${citation}` : title;
    const markdown = citation ? `[${title}](${url}) — ${citation}` : `[${title}](${url})`;
    return { id: url, url, title, type, short, full, markdown };
  }

  document.addEventListener('click', async (event) => {
    const action = event.target.closest('[data-result-action]');
    if (!action) return;
    const meta = resultActionMeta(action);
    if (!meta) return;
    const actionName = action.dataset.resultAction;
    if (actionName === 'save') {
      const saved = store?.toggleSaved({ ...meta, citation: meta.short });
      action.textContent = saved ? 'Saved' : 'Save';
      action.setAttribute('aria-pressed', String(Boolean(saved)));
      showToast(saved ? 'Added to your bookshelf' : 'Removed from your bookshelf');
    } else if (actionName === 'cite') {
      openCitation(meta, action);
    } else if (actionName === 'link') {
      await copyText(meta.url);
      showToast('Link copied');
    }
  });

  function recordContext(event) {
    const link = event.target.closest('a[href]');
    if (!link || link.closest('#recordSequence') || event.defaultPrevented || event.button || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const target = new URL(link.href, location.href);
    if (target.origin !== location.origin || !isRecordPath(target.pathname)) return;
    const resultLinks = resultLinksForContext();
    const position = resultLinks.findIndex((item) => item.href === target.href);
    const context = {
      version: 2,
      href: location.href,
      destination: target.pathname,
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
    // The shared layout includes this element on every page, but the affordance
    // is meaningful only on canonical record pages.  A stale session context
    // must never make “Back to results” appear on the home or catalogue pages.
    if (!isRecordPath(location.pathname)) {
      container.hidden = true;
      return;
    }
    let context;
    try { context = JSON.parse(sessionStorage.getItem('pca-ga-return-context')); } catch (_) { context = null; }
    const currentIndex = context?.items?.findIndex((item) => new URL(item.href, location.href).pathname === location.pathname) ?? -1;
    if (!context?.href || (context.destination && context.destination !== location.pathname && currentIndex < 0)) return;
    const activePosition = currentIndex >= 0 ? currentIndex : (context.position || 0);
    link.textContent = `← ${context.label || 'Back to results'}`;
    link.href = context.href;
    link.addEventListener('click', () => {
      try { sessionStorage.setItem('pca-ga-restore-scroll', JSON.stringify({ href: context.href, y: context.y || 0 })); } catch (_) { /* No persistence needed. */ }
    });
    if (context.items?.length && context.position >= 0 && sequence) {
      const previous = context.items[activePosition - 1];
      const next = context.items[activePosition + 1];
      sequence.hidden = false;
      sequence.innerHTML = `${activePosition + 1} of ${context.items.length}${previous ? ` <a href="${previous.href}" aria-label="Previous result">‹</a>` : ''}${next ? ` <a href="${next.href}" aria-label="Next result">›</a>` : ''}`;
      sequence.querySelectorAll('a[href]').forEach((resultLink) => resultLink.addEventListener('click', () => {
        const target = new URL(resultLink.href, location.href);
        context.destination = target.pathname;
        context.position = context.items.findIndex((item) => item.href === target.href);
        try { sessionStorage.setItem('pca-ga-return-context', JSON.stringify(context)); } catch (_) { /* Context is a convenience. */ }
      }));
    }
    container.hidden = false;
  }

  function restoreScroll() {
    let restore;
    try { restore = JSON.parse(sessionStorage.getItem('pca-ga-restore-scroll')); } catch (_) { restore = null; }
    if (!restore || new URL(restore.href, location.href).pathname !== location.pathname) return;
    sessionStorage.removeItem('pca-ga-restore-scroll');
    const apply = () => window.requestAnimationFrame(() => window.scrollTo({ top: restore.y || 0, behavior: 'auto' }));
    const isSearchHydration = document.body.dataset.pageType === 'home' && new URLSearchParams(location.search).has('q');
    if (isSearchHydration) window.addEventListener('pca-results-ready', apply, { once: true });
    else apply();
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
  enhanceCatalogueCards();
  enhanceCatalogueIndex();
  enhanceProvisionIndex();
  enhanceJudicialCatalogue();
  injectBadges();
  restoreContext();
  restoreScroll();
  renderBrowseRecent();

  const pageFindState = { matches: [], index: -1, query: '' };
  let pageFindOpener;

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
      <input id="pageFindInput" name="page-find" type="search" autocomplete="off" enterkeyhint="search" placeholder="Find in this page…">
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
    if (scroll) active.startContainer.parentElement?.scrollIntoView({ behavior: scrollBehavior(), block: 'center' });
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

  function openPageFind(opener) {
    const finder = document.getElementById('pageFind') || createPageFind();
    pageFindOpener = opener || document.querySelector('[data-page-find-open]');
    finder.hidden = false;
    const input = finder.querySelector('input');
    input.focus();
    input.select();
  }

  function closePageFind() {
    const finder = document.getElementById('pageFind');
    if (!finder) return;
    const opener = pageFindOpener;
    pageFindOpener = null;
    finder.hidden = true;
    clearPageFindHighlights();
    pageFindState.query = '';
    const selection = getSelection();
    selection.removeAllRanges();
    if (opener?.isConnected) opener.focus();
  }

  document.addEventListener('click', (event) => {
    if (event.target.closest('[data-page-find-open]')) { openPageFind(event.target.closest('[data-page-find-open]')); return; }
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
