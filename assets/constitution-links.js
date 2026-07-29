'use strict';

(() => {
  const loader = document.currentScript;
  const dataBase = new URL('constitution/', loader?.src || location.href);
  const readerBase = 'https://raymond-rishty.github.io/pca-constitution-reader/';
  const bcoChapterCache = new Map();
  const standardCache = new Map();
  const packCache = new Map();
  const books = {
    bco: { name: 'Book of Church Order', abbr: 'BCO' },
    wcf: { name: 'Westminster Confession of Faith', abbr: 'WCF' },
    wlc: { name: 'Westminster Larger Catechism', abbr: 'WLC' },
    wsc: { name: 'Westminster Shorter Catechism', abbr: 'WSC' },
    rao: { name: 'Rules of Assembly Operations', abbr: 'RAO', nonConstitutional: true },
  };
  let sheet;
  let lastTrigger;

  function createSheet() {
    const element = document.createElement('div');
    element.className = 'constitution-sheet';
    element.id = 'constitutionSheet';
    element.hidden = true;
    element.innerHTML = `
      <div class="constitution-sheet__backdrop" data-constitution-close></div>
      <section class="constitution-sheet__panel" role="dialog" aria-modal="true" aria-labelledby="constitutionSheetTitle">
        <div class="constitution-sheet__handle" aria-hidden="true"></div>
        <header class="constitution-sheet__header">
          <div>
            <p class="constitution-sheet__eyebrow" id="constitutionSheetEyebrow"></p>
            <h2 id="constitutionSheetTitle"></h2>
            <p class="constitution-sheet__chapter" id="constitutionSheetChapter"></p>
          </div>
          <button type="button" class="constitution-sheet__close" data-constitution-close aria-label="Close constitutional text">×</button>
        </header>
        <div class="constitution-sheet__body" id="constitutionSheetBody" aria-live="polite"></div>
        <footer class="constitution-sheet__actions">
          <a class="constitution-sheet__primary" id="constitutionOpenReader" target="_blank" rel="noopener">Open in Constitution</a>
          <button type="button" class="constitution-sheet__secondary" id="constitutionCopy">Copy citation</button>
        </footer>
      </section>`;
    document.body.appendChild(element);
    return element;
  }

  function ensureSheet() {
    sheet = sheet || document.getElementById('constitutionSheet') || createSheet();
    return sheet;
  }

  function closeSheet() {
    const current = ensureSheet();
    current.hidden = true;
    document.body.classList.remove('constitution-sheet-open');
    lastTrigger?.focus?.();
  }

  function loadBcoChapter(chapter) {
    if (!bcoChapterCache.has(chapter)) {
      const url = new URL(`chapters/${encodeURIComponent(chapter)}.json`, dataBase);
      bcoChapterCache.set(chapter, fetch(url).then((response) => {
        if (!response.ok) throw new Error(`BCO chapter ${chapter} could not be loaded`);
        return response.json();
      }));
    }
    return bcoChapterCache.get(chapter);
  }

  function loadStandard(book) {
    if (!standardCache.has(book)) {
      const url = new URL(`standards/${encodeURIComponent(book)}.json`, dataBase);
      standardCache.set(book, fetch(url).then((response) => {
        if (!response.ok) throw new Error(`${book.toUpperCase()} text could not be loaded`);
        return response.json();
      }));
    }
    return standardCache.get(book);
  }

  function loadPack(book) {
    if (!packCache.has(book)) {
      const url = new URL(`packs/${encodeURIComponent(book)}.json`, dataBase);
      packCache.set(book, fetch(url).then((response) => {
        if (!response.ok) throw new Error(`${book.toUpperCase()} pack could not be loaded`);
        return response.json();
      }));
    }
    return packCache.get(book);
  }

  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"]/g, (character) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;',
    }[character]));
  }

  function standardSectionHtml(book, ref, section) {
    if (book === 'wcf') return section.body || '<p>No text is available for this section.</p>';
    const question = escapeHtml(section.question);
    const answer = escapeHtml(section.answer);
    return `<p class="constitution-sheet__question"><strong>${escapeHtml(ref)}</strong> ${question}</p><p><strong>A.</strong> ${answer}</p>`;
  }

  async function copyCitation(label, button) {
    const original = button.textContent;
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(label);
      else {
        const textarea = document.createElement('textarea');
        textarea.value = label;
        textarea.setAttribute('readonly', '');
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        textarea.remove();
      }
      button.textContent = 'Copied ✓';
    } catch (_) {
      button.textContent = label;
    }
    window.setTimeout(() => {
      if (document.body.contains(button)) button.textContent = original;
    }, 1500);
  }

  function linkDetails(link) {
    const book = link.dataset.constitutionBook || 'bco';
    const ref = link.dataset.constitutionRef || link.dataset.bcoRef;
    const chapter = link.dataset.bcoChapter;
    const chapterOnly = link.dataset.bcoKind === 'chapter'
      || link.dataset.constitutionKind === 'chapter';
    return { book, ref, chapter, chapterOnly };
  }

  async function openSheet(link) {
    const { book, ref, chapter, chapterOnly } = linkDetails(link);
    if (!books[book] || !ref || (book === 'bco' && !chapter)) return;

    const current = ensureSheet();
    const eyebrow = current.querySelector('#constitutionSheetEyebrow');
    const title = current.querySelector('#constitutionSheetTitle');
    const chapterLine = current.querySelector('#constitutionSheetChapter');
    const body = current.querySelector('#constitutionSheetBody');
    const reader = current.querySelector('#constitutionOpenReader');
    const copy = current.querySelector('#constitutionCopy');
    const citationRef = book === 'wcf' ? ref : ref.replace(/^Q\./, '');
    const citationLabel = `${books[book].abbr} ${citationRef}`;

    lastTrigger = link;
    eyebrow.textContent = books[book].nonConstitutional
      ? `Current ${books[book].name} text · not part of the PCA Constitution`
      : `Current ${books[book].name} text`;
    title.textContent = citationLabel;
    chapterLine.textContent = book === 'bco'
      ? `Chapter ${chapter}`
      : (book === 'rao' ? `Article ${ref.split('-')[0]}` : (book === 'wcf' ? `Chapter ${ref.split('.')[0]}` : `Question ${citationRef}`));
    body.innerHTML = '<p class="constitution-sheet__loading">Loading current text…</p>';
    reader.href = `${readerBase}#${book}/${encodeURIComponent(ref)}`;
    reader.textContent = book === 'rao' ? 'Open in Reader' : 'Open in Constitution';
    copy.onclick = () => copyCitation(citationLabel, copy);

    current.hidden = false;
    document.body.classList.add('constitution-sheet-open');
    current.querySelector('[data-constitution-close]')?.focus();

    try {
      if (book === 'bco') {
        const payload = await loadBcoChapter(chapter);
        chapterLine.textContent = `Chapter ${chapter} · ${payload.title || ''}`.replace(/\s+·\s*$/, '');
        if (chapterOnly) {
          const sections = Object.entries(payload.sections || {});
          if (!sections.length) throw new Error(`BCO chapter ${chapter} was not found in the current chapter data`);
          body.innerHTML = sections.map(([sectionRef, section]) => (
            `<section class="constitution-sheet__section"><h3>BCO ${escapeHtml(sectionRef)}</h3>${section.body || '<p>No text is available for this section.</p>'}</section>`
          )).join('');
        } else {
          const section = payload.sections?.[ref];
          if (!section) throw new Error(`BCO ${ref} was not found in the current chapter data`);
          body.innerHTML = section.body || '<p>No text is available for this section.</p>';
        }
      } else if (book === 'rao') {
        const payload = await loadPack(book);
        const section = payload.sections?.[ref];
        if (!section) throw new Error(`${citationLabel} was not found in the current RAO pack`);
        chapterLine.textContent = `Article ${section.article} · ${section.articleTitle || ''} · ${payload.edition || 'current edition'}`.replace(/\s+·\s*$/, '');
        body.innerHTML = section.body || '<p>No text is available for this section.</p>';
      } else {
        const payload = await loadStandard(book);
        if (book === 'wcf' && chapterOnly) {
          const chapterPayload = payload.chapters?.[ref];
          if (!chapterPayload) throw new Error(`${citationLabel} was not found in the current chapter data`);
          chapterLine.textContent = `Chapter ${ref} · ${chapterPayload.title || ''}`.replace(/\s+·\s*$/, '');
          const sections = Object.entries(chapterPayload.sections || {});
          if (!sections.length) throw new Error(`${citationLabel} has no sections in the current chapter data`);
          body.innerHTML = sections.map(([sectionRef, section]) => (
            `<section class="constitution-sheet__section"><h3>WCF ${escapeHtml(sectionRef)}</h3>${standardSectionHtml(book, sectionRef, section)}</section>`
          )).join('');
          return;
        }
        const section = payload.sections?.[ref];
        if (!section) throw new Error(`${citationLabel} was not found in the current preview data`);
        if (book === 'wcf') chapterLine.textContent = `Chapter ${section.chapter} · ${section.chapterTitle || ''}`.replace(/\s+·\s*$/, '');
        body.innerHTML = standardSectionHtml(book, ref, section);
      }
    } catch (error) {
      body.innerHTML = '<p class="constitution-sheet__error">The current text could not be loaded here. Open the provision in the Constitution Reader instead.</p>';
      console.warn(error);
    }
  }

  document.addEventListener('click', (event) => {
    const close = event.target.closest('[data-constitution-close]');
    if (close) {
      closeSheet();
      return;
    }

    const link = event.target.closest('a.bco-ref[data-bco-ref], a.constitution-ref[data-constitution-book][data-constitution-ref]');
    if (!link || event.defaultPrevented) return;
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    event.preventDefault();
    openSheet(link);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !ensureSheet().hidden) closeSheet();
  });
})();
