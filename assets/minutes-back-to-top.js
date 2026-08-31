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
})();
