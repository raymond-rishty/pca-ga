'use strict';

(() => {
  const loader = document.currentScript;
  const dataBase = new URL('constitution/', loader?.src || location.href);
  const chapterCache = new Map();
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
            <p class="constitution-sheet__eyebrow">Current Book of Church Order text</p>
            <h2 id="constitutionSheetTitle">BCO</h2>
            <p class="constitution-sheet__chapter" id="constitutionSheetChapter"></p>
          </div>
          <button type="button" class="constitution-sheet__close" data-constitution-close aria-label="Close BCO text">×</button>
        </header>
        <div class="constitution-sheet__body" id="constitutionSheetBody" aria-live="polite"></div>
        <footer class="constitution-sheet__actions">
          <a class="constitution-sheet__primary" id="constitutionOpenReader" target="_blank" rel="noopener">Open chapter in Constitution</a>
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

  function loadChapter(chapter) {
    if (!chapterCache.has(chapter)) {
      const url = new URL(`chapters/${encodeURIComponent(chapter)}.json`, dataBase);
      chapterCache.set(chapter, fetch(url).then((response) => {
        if (!response.ok) throw new Error(`BCO chapter ${chapter} could not be loaded`);
        return response.json();
      }));
    }
    return chapterCache.get(chapter);
  }

  async function copyCitation(ref, button) {
    const text = `BCO ${ref}`;
    const original = button.textContent;
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
      else {
        const textarea = document.createElement('textarea');
        textarea.value = text;
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
      button.textContent = text;
    }
    window.setTimeout(() => {
      if (document.body.contains(button)) button.textContent = original;
    }, 1500);
  }

  async function openSheet(link) {
    const ref = link.dataset.bcoRef;
    const chapter = link.dataset.bcoChapter;
    if (!ref || !chapter) return;

    const current = ensureSheet();
    const title = current.querySelector('#constitutionSheetTitle');
    const chapterLine = current.querySelector('#constitutionSheetChapter');
    const body = current.querySelector('#constitutionSheetBody');
    const reader = current.querySelector('#constitutionOpenReader');
    const copy = current.querySelector('#constitutionCopy');

    lastTrigger = link;
    title.textContent = `BCO ${ref}`;
    chapterLine.textContent = `Chapter ${chapter}`;
    body.innerHTML = '<p class="constitution-sheet__loading">Loading current text…</p>';
    reader.href = `https://raymond-rishty.github.io/pca-constitution-reader/#bco/${encodeURIComponent(chapter)}`;
    copy.onclick = () => copyCitation(ref, copy);

    current.hidden = false;
    document.body.classList.add('constitution-sheet-open');
    current.querySelector('[data-constitution-close]')?.focus();

    try {
      const payload = await loadChapter(chapter);
      const section = payload.sections?.[ref];
      if (!section) throw new Error(`BCO ${ref} was not found in the current chapter data`);
      chapterLine.textContent = `Chapter ${chapter} · ${payload.title || ''}`.replace(/\s+·\s*$/, '');
      body.innerHTML = section.body || '<p>No text is available for this section.</p>';
    } catch (error) {
      body.innerHTML = '<p class="constitution-sheet__error">The current text could not be loaded here. Open the chapter in the Constitution Reader instead.</p>';
      console.warn(error);
    }
  }

  document.addEventListener('click', (event) => {
    const close = event.target.closest('[data-constitution-close]');
    if (close) {
      closeSheet();
      return;
    }

    const link = event.target.closest('a.bco-ref[data-bco-ref]');
    if (!link || event.defaultPrevented) return;
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    event.preventDefault();
    openSheet(link);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !ensureSheet().hidden) closeSheet();
  });
})();
