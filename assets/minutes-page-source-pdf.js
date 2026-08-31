'use strict';

(() => {
  if (document.body?.dataset.pageType !== 'volume') return;

  const sourceLink = document.querySelector('.source-pdf-link[href]');
  const column = document.querySelector('.reading-col');
  if (!sourceLink || !column) return;

  const pdfByAnchor = new Map();
  const walker = document.createTreeWalker(column, NodeFilter.SHOW_COMMENT);
  while (walker.nextNode()) {
    const match = walker.currentNode.nodeValue.match(/\bPAGE\s+ga=(\d+)\s+pdf_page=(\d+)\s+printed_page=([^\s]+)/i);
    if (!match) continue;
    const [, ga, pdfPage, printedPage] = match;
    const printed = printedPage.toLowerCase() !== 'null';
    const anchor = printed ? `ga${ga}-p${printedPage}` : `ga${ga}-pdf-p${pdfPage}`;
    pdfByAnchor.set(anchor, pdfPage);
  }

  function sourceUrlFor(marker) {
    if (!marker?.id) return null;
    const pdfPage = pdfByAnchor.get(marker.id);
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
