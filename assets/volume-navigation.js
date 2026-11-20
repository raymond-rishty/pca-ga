'use strict';

(() => {
  const byId = id => document.getElementById(id);
  const nav = byId('volumeNav');
  const panel = byId('volumePanel');
  if (!nav || !panel?.showModal) return;

  const tree = byId('volumeTree');
  const contents = byId('volumeContents');
  const lookup = byId('volumeLookup');
  const form = byId('volumeForm');
  const mode = byId('volumeMode');
  const input = byId('volumeNumber');
  const choices = byId('volumeChoices');
  const message = byId('volumeMessage');
  const mobile = window.matchMedia('(max-width:640px)');
  const pages = [];
  const byPdf = new Map();
  const byFolio = new Map();
  const byTarget = new Map();
  for (const marker of document.querySelectorAll('.page-marker[data-pdf-anchor]')) {
    const anchor = byId(marker.dataset.pdfAnchor);
    if (!anchor) continue;
    const pdf = Number(marker.dataset.pdfPage);
    const folio = marker.dataset.printedPage === 'null' ? '' : marker.dataset.printedPage;
    const target = marker.querySelector('a').hash.slice(1);
    const page = { pdf, folio, target, anchor };
    pages.push(page);
    byPdf.set(pdf, page);
    byTarget.set(target, page);
    byTarget.set(anchor.id, page);
    if (folio) {
      if (!byFolio.has(folio)) byFolio.set(folio, []);
      byFolio.get(folio).push(page);
    }
  }
  if (!pages.length) return;

  const folioLabel = page => page.folio ? 'p. ' + page.folio : 'PDF p. ' + page.pdf;
  const element = (tag, text) => {
    const node = document.createElement(tag);
    if (text) node.textContent = text;
    return node;
  };
  function link(text, href) {
    const a = element('a', text);
    a.href = href;
    return a;
  }
  function visiblePage() {
    // Stationary anchors stay in document order even where page markers stick.
    const line = nav.getBoundingClientRect().bottom + 2;
    let left = 0;
    let right = pages.length;
    while (left < right) {
      const mid = Math.floor((left + right) / 2);
      if (pages[mid].anchor.getBoundingClientRect().top <= line) left = mid + 1;
      else right = mid;
    }
    return pages[left - 1];
  }
  let scheduled = false;
  function update() {
    scheduled = false;
    const page = visiblePage();
    const text = page ? ' · ' + folioLabel(page) : '';
    if (byId('volumeFolio').textContent !== text) byId('volumeFolio').textContent = text;
  }
  function schedule() {
    if (!scheduled) requestAnimationFrame(update);
    scheduled = true;
  }
  new ResizeObserver(() => {
    document.documentElement.style.setProperty('--volume-nav-height', nav.offsetHeight + 'px');
    schedule();
  }).observe(nav);
  for (const event of ['scroll', 'resize', 'pageshow', 'hashchange']) window.addEventListener(event, schedule, {passive:true});
  document.fonts?.ready.then(schedule);
  // Font substitution during reload can leave the cited boundary just below
  // the sticky row, showing the preceding folio even though the citation is visible.
  window.addEventListener('pageshow', event => {
    if (event.persisted) return;
    const target = byId(location.hash.slice(1));
    if (!target?.classList.contains('minutes-page__anchor')) return;
    requestAnimationFrame(() => {
      if (Math.abs(target.getBoundingClientRect().top - nav.getBoundingClientRect().bottom) < 16) {
        target.scrollIntoView({block:'start', behavior:'instant'});
        schedule();
      }
    });
  });

  let opener;
  let openingPage;
  let openingY;
  function show(button, title) {
    if (panel.open) panel.close();
    openingPage = visiblePage();
    openingY = window.scrollY;
    opener = button;
    byId('volumePanelTitle').textContent = title;
    tree.hidden = button !== contents;
    form.hidden = button !== lookup;
    if (mobile.matches) panel.showModal();
    else panel.show();
  }
  function dismiss() {
    panel.close();
    opener.focus({preventScroll:true});
  }
  panel.querySelector('[data-close]').addEventListener('click', dismiss);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && panel.open) {
      event.preventDefault();
      dismiss();
    }
  });
  mobile.addEventListener('change', () => { if (panel.open) dismiss(); });

  function jump(fragment) {
    const anchor = byId(fragment);
    if (!anchor) return;
    const page = byTarget.get(fragment);
    dismiss();
    const samePlace = Math.abs(anchor.getBoundingClientRect().top - nav.getBoundingClientRect().bottom) <= 3;
    // Carry the record's result context into the new entry, including after reload.
    if (!samePlace) {
      const state = {...history.state};
      history.replaceState({...state, volumeY:openingY}, '');
      delete state.volumeY;
      history.pushState({...state, volumeJump:true}, '', '#' + fragment);
    }
    else if (location.hash !== '#' + fragment) history.replaceState(history.state, '', '#' + fragment);
    anchor.scrollIntoView({block:'start', behavior:'instant'});
    anchor.tabIndex = -1;
    anchor.setAttribute('role', 'group');
    anchor.setAttribute('aria-label', page ? folioLabel(page) : fragment);
    anchor.focus({preventScroll:true});
    schedule();
  }
  window.addEventListener('popstate', event => {
    // A browser may reapply the incoming fragment after traversing. Restore
    // the actual position recorded when the reader deliberately left it.
    const y = event.state?.volumeY;
    if (Number.isFinite(y)) requestAnimationFrame(() => window.scrollTo({top:y, behavior:'instant'}));
  });
  panel.addEventListener('click', event => {
    const a = event.target.closest('a[href^="#"]');
    if (!a || event.button || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    jump(a.hash.slice(1));
  });

  let outlineReady = false;
  let loading;
  const sections = [];
  function buildTree(nodes, parents = []) {
    const list = element('ul');
    for (const row of nodes) {
      const li = element('li');
      const page = byPdf.get(row.pdf);
      const hasChildren = row.children.length > 0;
      const item = page ? link(row.label + ' · ' + folioLabel(page), '#' + row.target) : element('span', row.label);
      const path = [...parents, {row, item}];
      if (page) sections.push({pdf:page.pdf, path});
      if (hasChildren) {
        const details = element('details');
        const summary = element('summary', row.label);
        summary.dataset.sectionKey = row.key;
        details.append(summary);
        if (page) details.append(item);
        details.append(buildTree(row.children, path));
        li.append(details);
      } else li.append(item);
      list.append(li);
    }
    return list;
  }
  function currentSection(pdf) {
    let start = -1;
    let paths = [];
    for (const section of sections) {
      if (section.pdf > pdf || section.pdf < start) continue;
      if (section.pdf > start) paths = [];
      start = section.pdf;
      paths.push(section.path);
    }
    // Remove ancestor-only paths, then find the common ancestor of tied starts.
    const leaves = paths.filter(path => !paths.some(other => other.length > path.length && other[path.length-1] === path.at(-1)));
    return leaves[0]?.filter((entry,i) => leaves.every(path => path[i] === entry)).at(-1);
  }
  function revealSection() {
    tree.querySelector('[aria-current]')?.removeAttribute('aria-current');
    tree.querySelectorAll('details[open]').forEach(node => { node.open = false; });
    const section = currentSection(openingPage?.pdf ?? 0);
    if (!section) return;
    const item = section.item.isConnected ? section.item : tree.querySelector('[data-section-key="' + section.row.key + '"]');
    if (!item) return;
    for (let parent = item.parentElement; parent && parent !== tree; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
    }
    item.setAttribute('aria-current', 'location');
    // Scroll only the panel. scrollIntoView would also move the volume behind it.
    panel.scrollTop += item.getBoundingClientRect().top - panel.getBoundingClientRect().top - panel.querySelector('header').offsetHeight;
  }
  async function loadOutline() {
    tree.textContent = 'Loading contents…';
    try {
      const response = await fetch(nav.dataset.outline);
      if (!response.ok) throw new Error('outline unavailable');
      const data = await response.json();
      if (data.version !== 1 || data.volume !== nav.dataset.volume || !data.nodes.length) throw new Error('outline unavailable');
      sections.length = 0;
      tree.replaceChildren(buildTree(data.nodes));
      outlineReady = true;
    } catch {
      const retry = element('button', 'Retry');
      retry.type = 'button';
      retry.onclick = openContents;
      tree.replaceChildren(element('p', 'Contents could not be loaded.'), link('Open full outline', contents.href), retry);
    }
  }
  async function openContents() {
    show(contents, 'Contents');
    if (!outlineReady) {
      loading ??= loadOutline().finally(() => { loading = null; });
      await loading;
    }
    if (outlineReady && panel.open && !tree.hidden) revealSection();
  }
  contents.addEventListener('click', event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    openContents();
  });

  function clearLookup() {
    choices.replaceChildren();
    message.textContent = '';
    input.inputMode = mode.value === 'pdf' ? 'numeric' : 'text';
  }
  lookup.hidden = false;
  lookup.addEventListener('click', () => {
    mode.value = byFolio.size ? 'printed' : 'pdf';
    input.value = '';
    clearLookup();
    show(lookup, 'Go to page');
    input.focus({preventScroll:true});
  });
  input.addEventListener('input', clearLookup);
  mode.addEventListener('change', clearLookup);
  form.addEventListener('submit', event => {
    event.preventDefault();
    clearLookup();
    const value = input.value.trim();
    if (mode.value === 'pdf') {
      const page = /^\d+$/.test(value) && byPdf.get(Number(value));
      if (page) jump(page.anchor.id);
      else message.textContent = 'Enter a PDF page number present in this volume.';
      return;
    }
    const matches = byFolio.get(value) || [];
    if (matches.length === 1) return jump(matches[0].target);
    if (!matches.length) {
      message.textContent = 'No matching printed page. Check the folio or choose PDF page.';
      return;
    }
    message.textContent = 'This folio appears more than once. Choose an occurrence.';
    for (const page of matches) {
      const section = currentSection(page.pdf);
      choices.append(link('PDF p. ' + page.pdf + (section ? ' · ' + section.row.label : ''), '#' + page.target), element('br'));
    }
  });
  if (!window.navigation) {
    const back = byId('readingBack');
    const syncBack = () => { back.hidden = !history.state?.volumeJump; };
    back.addEventListener('click', () => history.back());
    window.addEventListener('popstate', syncBack);
    panel.addEventListener('close', syncBack);
    syncBack();
  }
  update();
})();
