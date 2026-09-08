(function attachPagefindSearch(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.PcaPagefindSearch = api;
}(typeof globalThis === 'undefined' ? this : globalThis, () => {
  const TYPE_CLASSES = {
    'General Assembly minutes': 'minutes',
    'Judicial case': 'case',
    'Constitutional inquiry': 'inquiry',
    'RPR exception': 'rpr',
    Overture: 'overture',
    'Position paper': 'study',
  };

  function filtersForTypes(types) {
    const values = [...(types || [])].filter(Boolean).sort();
    return values.length ? { type: { any: values } } : undefined;
  }

  function safeExcerpt(value) {
    const open = '\u0000PAGEFIND_MARK_OPEN\u0000';
    const close = '\u0000PAGEFIND_MARK_CLOSE\u0000';
    return String(value || '')
      .replace(/<mark>/gi, open)
      .replace(/<\/mark>/gi, close)
      .replace(/<[^>]*>/g, '')
      .replaceAll(open, '<mark>')
      .replaceAll(close, '</mark>');
  }

  function safeHref(value) {
    const href = String(value || '').trim();
    return href && !/^(?:javascript|data):/i.test(href) ? href : '#';
  }

  function bestPassage(data) {
    const meta = data?.meta || {};
    const subResults = Array.isArray(data?.sub_results) ? data.sub_results : [];
    const passage = subResults.find((result) => result?.anchor) || subResults[0] || data || {};
    const pageTitle = String(meta.title || '').trim();
    const title = String(passage.title || pageTitle || 'Matching passage').trim();
    return {
      href: safeHref(passage.url || data?.url),
      title,
      pageTitle: pageTitle && pageTitle !== title ? pageTitle : '',
      excerpt: safeExcerpt(passage.excerpt || data?.excerpt),
      type: String(meta.type || 'Full text'),
      year: String(meta.year || ''),
      className: TYPE_CLASSES[meta.type] || 'minutes',
    };
  }

  return { TYPE_CLASSES, bestPassage, filtersForTypes, safeExcerpt, safeHref };
}));
