'use strict';

(() => {
  const header = document.getElementById('recordHeader');
  const topbar = document.querySelector('.topbar');
  const title = header?.querySelector('h1');
  if (!header || !title) return;

  const label = title.textContent.replace(/\s+/g, ' ').trim();
  if (!label) return;

  const rail = document.createElement('div');
  rail.className = 'record-context-rail';
  rail.id = 'recordContextRail';
  rail.setAttribute('aria-hidden', 'true');
  rail.innerHTML = `<button class="record-context-rail__button" type="button" aria-label="Return to case heading">
    <span class="record-context-rail__title"></span>
    <span class="record-context-rail__return" aria-hidden="true">↑</span>
  </button>`;
  rail.querySelector('.record-context-rail__title').textContent = label;
  document.body.appendChild(rail);

  const button = rail.querySelector('button');
  button.tabIndex = -1;

  let frame = 0;
  let visible = false;

  function topbarHeight() {
    return topbar?.getBoundingClientRect().height || 56;
  }

  function setVisible(nextVisible) {
    if (visible === nextVisible) return;
    visible = nextVisible;
    rail.classList.toggle('is-visible', visible);
    rail.setAttribute('aria-hidden', String(!visible));
    button.tabIndex = visible ? 0 : -1;
    document.body.classList.toggle('has-sticky-record-context', visible);
  }

  function update() {
    frame = 0;
    setVisible(header.getBoundingClientRect().bottom <= topbarHeight());
  }

  function scheduleUpdate() {
    if (!frame) frame = window.requestAnimationFrame(update);
  }

  button.addEventListener('click', () => {
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const target = window.scrollY + header.getBoundingClientRect().top - topbarHeight() - 12;
    window.scrollTo({ top: Math.max(0, target), behavior: reducedMotion ? 'auto' : 'smooth' });
  });

  window.addEventListener('scroll', scheduleUpdate, { passive: true });
  window.addEventListener('resize', scheduleUpdate);
  window.addEventListener('pageshow', scheduleUpdate);
  document.fonts?.ready.then(scheduleUpdate);
  scheduleUpdate();
})();
