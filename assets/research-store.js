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
    return {
      id: record.id || record.url,
      url: record.url,
      title: record.title || 'Untitled record',
      type: record.type || 'Record',
      citation: record.citation || '',
      savedAt: record.savedAt || new Date().toISOString(),
    };
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
    const item = normalise(record);
    const citations = read(KEYS.citations);
    const found = citations.findIndex((entry) => entry.id === item.id && entry.citation === item.citation);
    if (found >= 0) citations.splice(found, 1);
    citations.unshift(item);
    write(KEYS.citations, citations.slice(0, 100));
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

  window.PCAResearch = {
    listSaved: () => read(KEYS.saved),
    listCitations: () => read(KEYS.citations),
    listRecent: () => read(KEYS.recent),
    toggleSaved,
    isSaved,
    addCitation,
    addRecent,
    remove,
  };
})();
