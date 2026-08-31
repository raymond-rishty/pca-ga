'use strict';

(() => {
  if (document.body?.dataset.pageType !== 'volume') return;

  const sourceLink = document.querySelector('.source-pdf-link[href]');
  const column = document.querySelector('.reading-col');
  if (!sourceLink || !column) return;

  // Capture PDF coordinates in source-document order before pca-nav.js turns
  // PAGE comments into rendered page markers. Printed folio numbers can repeat
  // later in a volume (for example GA33 has two different printed page 300s),
  // so the printed-page label is not a safe lookup key.
  const pdfPages = [];
  const walker = document.createTreeWalker(column, NodeFilter.SHOW_COMMENT);
  while (walker.nextNode()) {
    const match = walker.currentNode.nodeValue.match(/\bPAGE\s+ga=(\d+)\s+pdf_page=(\d+)\s+printed_page=([^\s]+)/i);
    if (!match) continue;
    pdfPages.push(match[2]);
  }

  function sourceUrlFor(marker) {
    if (!marker) return null;
    const markers = [...column.querySelectorAll('.page-marker')];
    const markerIndex = markers.indexOf(marker);
    const pdfPage = markerIndex >= 0 ? pdfPages[markerIndex] : null;
    if (!pdfPage) return null;
    const url = new URL(sourceLink.href, location.href);
    url.hash = `page=${pdfPage}`;
    return url.href;
  }

  function addSourceAction(marker) {
    const sheet = document.getElementById('pageActionSheet');
    const list = sheet?.querySelector('.page-action-list');
    if (!list) return;

    let action = list.querySelector('[data-page-source-pdf]');
    if (!action) {
      action = document.createElement('button');
      action.type = 'button';
      action.dataset.pageSourcePdf = '';
      action.innerHTML = '<span aria-hidden="true">↗</span><span>Open source PDF</span>';
      list.appendChild(action);
    }

    const sourceUrl = sourceUrlFor(marker);
    action.hidden = !sourceUrl;
    action.onclick = sourceUrl
      ? () => window.open(sourceUrl, '_blank', 'noopener,noreferrer')
      : null;
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('.page-marker__actions');
    if (!button) return;
    const marker = button.closest('.page-marker');
    queueMicrotask(() => addSourceAction(marker));
  });
})();
