'use strict';

(() => {
  const PREFIX = 'pca-ga-research-v1';
  const KEYS = {
    saved: `${PREFIX}:saved`,
    citations: `${PREFIX}:citations`,
    recent: `${PREFIX}:recent`,
  };

  function read(key) {
    try {
      const value = JSON.parse(localStorage.getItem(key));
      return Array.isArray(value) ? value : [];
    } catch (_) {
      return [];
    }
  }

  function write(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (_) { /* Local saving is an enhancement, never a reading blocker. */ }
  }

  function normalise(record) {
    const title = record.title || 'Untitled record';
    const url = record.url || record.id || '';
    const short = record.short || record.citation || '';
    return {
      id: record.id || url,
      url,
      title,
      type: record.type || 'Record',
      citation: record.citation || short,
      short,
      full: record.full || (short ? `${title} — ${short}. ${url}` : url),
      markdown: record.markdown || (short ? `[${title}](${url}) — ${short}.` : `[${title}](${url})`),
      savedAt: record.savedAt || new Date().toISOString(),
    };
  }

  function mergeRecord(current, incoming) {
    const next = normalise(incoming);
    return {
      ...next,
      ...current,
      url: current.url || next.url,
      title: current.title || next.title,
      type: current.type || next.type,
      citation: current.citation || next.citation,
      short: current.short || next.short,
      full: current.full || next.full,
      markdown: current.markdown || next.markdown,
      savedAt: current.savedAt || next.savedAt,
    };
  }

  function addSaved(record) {
    const item = normalise(record);
    const saved = read(KEYS.saved);
    const found = saved.findIndex((entry) => entry.id === item.id);
    if (found >= 0) {
      const current = saved.splice(found, 1)[0];
      saved.unshift(mergeRecord(current, item));
      write(KEYS.saved, saved.slice(0, 100));
      return false;
    }
    saved.unshift(item);
    write(KEYS.saved, saved.slice(0, 100));
    return true;
  }

  function toggleSaved(record) {
    const item = normalise(record);
    const saved = read(KEYS.saved);
    const found = saved.findIndex((entry) => entry.id === item.id);
    if (found >= 0) {
      saved.splice(found, 1);
      write(KEYS.saved, saved);
      return false;
    }
    saved.unshift(item);
    write(KEYS.saved, saved.slice(0, 100));
    return true;
  }

  function isSaved(record) {
    return read(KEYS.saved).some((entry) => entry.id === (record.id || record.url));
  }

  function addCitation(record) {
    addSaved(record);
    window.setTimeout(() => {
      const toast = document.getElementById('researchToast');
      if (toast?.textContent === 'Citation added to My Research') toast.textContent = 'Saved to your bookshelf';
    }, 0);
  }

  function addRecent(record) {
    const item = normalise(record);
    const recent = read(KEYS.recent).filter((entry) => entry.id !== item.id);
    recent.unshift(item);
    write(KEYS.recent, recent.slice(0, 50));
  }

  function remove(kind, id, citation) {
    const key = KEYS[kind];
    if (!key) return;
    write(key, read(key).filter((entry) => entry.id !== id || (citation && entry.citation !== citation)));
  }

  function migrateLegacyCitations() {
    const citations = read(KEYS.citations);
    if (!citations.length) return;
    const saved = read(KEYS.saved).map(normalise);
    citations.forEach((citation) => {
      const item = normalise(citation);
      const found = saved.findIndex((entry) => entry.id === item.id);
      if (found >= 0) saved[found] = mergeRecord(saved[found], item);
      else saved.push(item);
    });
    write(KEYS.saved, saved.slice(0, 100));
    write(KEYS.citations, []);
  }

  migrateLegacyCitations();

  document.addEventListener('click', (event) => {
    if (!event.target.closest('[data-record-cite]')) return;
    window.setTimeout(() => {
      const button = document.getElementById('saveCitation');
      if (button) button.textContent = 'Save to bookshelf';
    }, 0);
  });

  window.PCAResearch = {
    listSaved: () => read(KEYS.saved).map(normalise),
    listRecent: () => read(KEYS.recent).map(normalise),
    addSaved,
    toggleSaved,
    isSaved,
    addCitation,
    addRecent,
    remove,
  };
})();
