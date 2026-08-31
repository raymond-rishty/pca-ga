'use strict';

(() => {
  if (document.body?.dataset.pageType !== 'volume') return;

  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'minutes-back-to-top';
  button.setAttribute('aria-label', 'Back to top');
  button.hidden = true;
  button.innerHTML = '<span aria-hidden="true">↑</span><span>Top</span>';
  document.body.appendChild(button);

  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const revealThreshold = () => Math.max(600, window.innerHeight * 0.75);

  function updateVisibility() {
    button.hidden = window.scrollY < revealThreshold();
  }

  button.addEventListener('click', () => {
    window.scrollTo({
      top: 0,
      left: 0,
      behavior: reducedMotion.matches ? 'auto' : 'smooth',
    });
  });

  window.addEventListener('scroll', updateVisibility, { passive: true });
  window.addEventListener('resize', updateVisibility, { passive: true });
  updateVisibility();

  const sourceLink = document.querySelector('.source-pdf-link[href]');
  let pdfPageMapPromise;

  function loadPdfPageMap() {
    if (!sourceLink) return Promise.resolve(new Map());
    if (pdfPageMapPromise) return pdfPageMapPromise;

    const sourceUrl = `${location.origin}${location.pathname}`;
    pdfPageMapPromise = fetch(sourceUrl, { credentials: 'same-origin', cache: 'force-cache' })
      .then((response) => {
        if (!response.ok) throw new Error(`Could not load minutes HTML (${response.status})`);
        return response.text();
      })
      .then((html) => {
        const pages = new Map();
        const markerRe = /<!--\s*PAGE\s+ga=(\d+)\s+pdf_page=(\d+)\s+printed_page=([^\s]+)(?:\s+printed_page_source=([^\s]+))?\s*-->/gi;
        let match;
        while ((match = markerRe.exec(html))) {
          const [, ga, pdfPage, printedPage] = match;
          const printed = printedPage.toLowerCase() !== 'null';
          const anchor = printed ? `ga${ga}-p${printedPage}` : `ga${ga}-pdf-p${pdfPage}`;
          pages.set(anchor, pdfPage);
        }
        return pages;
      })
      .catch(() => new Map());

    return pdfPageMapPromise;
  }

  function sourcePdfUrl(pdfPage) {
    if (!sourceLink || !pdfPage) return null;
    const url = new URL(sourceLink.href, location.href);
    url.hash = `page=${pdfPage}`;
    return url.href;
  }

  async function showSourcePdfAction(marker) {
    const sheet = document.getElementById('pageActionSheet');
    const list = sheet?.querySelector('.page-action-list');
    if (!sheet || !list || !marker?.id) return;

    let sourceButton = list.querySelector('[data-source-pdf-action]');
    if (!sourceButton) {
      sourceButton = document.createElement('button');
      sourceButton.type = 'button';
      sourceButton.dataset.sourcePdfAction = '';
      sourceButton.innerHTML = '<span aria-hidden="true">↗</span><span>Open source PDF</span>';
      list.appendChild(sourceButton);
    }

    sourceButton.disabled = true;
    sourceButton.dataset.markerId = marker.id;
    sourceButton.removeAttribute('data-source-pdf-url');
    sourceButton.querySelector('span:last-child').textContent = 'Open source PDF';

    const pages = await loadPdfPageMap();
    if (sourceButton.dataset.markerId !== marker.id) return;
    const pdfPage = pages.get(marker.id);
    const url = sourcePdfUrl(pdfPage);
    if (!url) {
      sourceButton.hidden = true;
      return;
    }

    sourceButton.hidden = false;
    sourceButton.disabled = false;
    sourceButton.dataset.sourcePdfUrl = url;
    sourceButton.title = `Open the original minutes at PDF page ${pdfPage}`;
  }

  document.addEventListener('click', (event) => {
    const pageActions = event.target.closest('.page-marker__actions');
    if (pageActions) {
      const marker = pageActions.closest('.page-marker');
      void showSourcePdfAction(marker);
      return;
    }

    const sourceButton = event.target.closest('[data-source-pdf-action]');
    const url = sourceButton?.dataset.sourcePdfUrl;
    if (!sourceButton || sourceButton.disabled || !url) return;
    const opened = window.open(url, '_blank', 'noopener,noreferrer');
    if (opened) opened.opener = null;
  });
})();
