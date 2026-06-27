'use strict';

/* ── Sidebar ── */
const sidebar  = document.getElementById('sidebar');
const overlay  = document.getElementById('sidebarOverlay');
const menuBtn  = document.getElementById('menuBtn');
const sbClose  = document.getElementById('sidebarClose');

function openSidebar() {
  sidebar.classList.add('open');
  overlay.classList.add('active');
  menuBtn.setAttribute('aria-expanded', 'true');
  document.body.style.overflow = 'hidden';
}
function closeSidebar() {
  sidebar.classList.remove('open');
  overlay.classList.remove('active');
  menuBtn.setAttribute('aria-expanded', 'false');
  document.body.style.overflow = '';
}

menuBtn.addEventListener('click', () =>
  sidebar.classList.contains('open') ? closeSidebar() : openSidebar()
);
sbClose.addEventListener('click', closeSidebar);
overlay.addEventListener('click', closeSidebar);
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeSidebar(); });

/* ── Disposition badge injection ── */
// Runs only on case pages. Finds the disposition value in the structured
// metadata paragraph (e.g. "Disposition:** sustained") and wraps it.
(function injectBadge() {
  const col = document.querySelector('.reading-col');
  if (!col) return;

  const DISPS = {
    'sustained':       'sustained',
    'not sustained':   'not-sustained',
    'denied':          'denied',
    'dismissed':       'dismissed',
    'withdrawn':       'withdrawn',
    'moot':            'moot',
    'administrative':  'administrative',
    'remanded':        'remanded',
  };

  // Walk text nodes inside <strong> elements (that's where Jekyll renders **bold**)
  col.querySelectorAll('strong').forEach(el => {
    const text = el.textContent.trim().toLowerCase();
    // Only match stand-alone disposition values, not labels like "Disposition:"
    if (DISPS[text]) {
      const span = document.createElement('span');
      span.className = `badge badge--${DISPS[text]}`;
      span.textContent = el.textContent.trim();
      el.replaceWith(span);
    }
  });
})();
