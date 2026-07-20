(function attachSearchRecord(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.PcaSearchRecord = api;
}(typeof globalThis === 'undefined' ? this : globalThis, () => {
  const CATEGORIES = {
    'General Assembly minutes': { className: 'minutes', label: 'General Assembly minutes' },
    'Judicial case': { className: 'case', label: 'Judicial case' },
    'Constitutional inquiry': { className: 'inquiry', label: 'Constitutional inquiry' },
    'RPR exception': { className: 'rpr', label: 'RPR exception' },
    'Overture': { className: 'overture', label: 'Overture' },
    'Position paper': { className: 'study', label: 'Study / position paper' },
  };

  const GA_IN_URL = /ga(\d{2})_(\d{4})/i;
  const PAGE_IN_URL = /#ga\d+-p(\d+)/i;
  const CASE_IN_SUB = /(?:SJC\/CJB\s+)?case\s+([\d-]+)/i;
  const INQUIRY_IN_URL = /__ci(\d+)/i;
  const OVERTURE_IN_SUB = /\boverture\s+(\d+)/i;
  const OVERTURE_IN_URL = /__o(\d+)/i;
  const RPR_IN_URL = /\/([^/]+)__([0-9]+)\.md(?:$|[?#])/i;

  function ordinal(value) {
    const number = Number(value);
    const mod100 = number % 100;
    if (mod100 >= 11 && mod100 <= 13) return `${number}th`;
    return `${number}${({ 1: 'st', 2: 'nd', 3: 'rd' })[number % 10] || 'th'}`;
  }

  function clean(value) {
    return String(value || '').replace(/\s+/g, ' ').trim();
  }

  function gaFromYear(year) {
    const number = Number(year);
    if (!Number.isInteger(number) || number < 1973 || number === 2020) return null;
    return number < 2020 ? number - 1972 : number - 1973;
  }

  function assembly(record) {
    const urlMatch = String(record.url || '').match(GA_IN_URL);
    if (urlMatch) return `${ordinal(urlMatch[1])} GA (${urlMatch[2]})`;
    const ga = gaFromYear(record.year);
    return ga ? `${ordinal(ga)} GA (${record.year})` : record.year ? String(record.year) : '';
  }

  function sourcePage(record) {
    const match = String(record.url || '').match(PAGE_IN_URL);
    return match ? `p. ${Number(match[1])}` : '';
  }

  function href(record) {
    return String(record.url || '').replace(/\.md(?=($|[?#]))/i, '.html');
  }

  function rprDetails(record) {
    const match = String(record.url || '').match(RPR_IN_URL);
    const exception = match ? String(Number(match[2])) : '';
    const presbytery = clean(record.sub).replace(/\s+Presbytery(?:\s+.*)?$/i, ' Presbytery') || 'Presbytery';
    const prefix = new RegExp(`^${presbytery.replace(/\s+Presbytery$/i, '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}:\\s*`, 'i');
    return {
      identifier: exception ? `Exception ${exception}` : 'Exception of substance',
      title: `${presbytery} — ${exception ? `exception ${exception}` : 'exception of substance'}`,
      excerpt: clean(record.title).replace(prefix, ''),
    };
  }

  function identifier(record) {
    if (record.type === 'Judicial case') {
      const match = clean(record.sub).match(CASE_IN_SUB);
      return match ? `Case ${match[1]}` : 'Judicial case';
    }
    if (record.type === 'Constitutional inquiry') {
      const match = String(record.url || '').match(INQUIRY_IN_URL);
      return match ? `CCB inquiry ${Number(match[1])}` : 'CCB inquiry';
    }
    if (record.type === 'Overture') {
      const match = clean(record.sub).match(OVERTURE_IN_SUB) || String(record.url || '').match(OVERTURE_IN_URL);
      return match ? `Overture ${Number(match[1])}` : 'Overture';
    }
    if (record.type === 'Position paper') return clean(record.sub) || 'Study paper';
    return '';
  }

  function excerpt(record) {
    if (record.type === 'Judicial case') return clean(record.summary);
    if (record.type === 'Constitutional inquiry') return clean(record.sub);
    return '';
  }

  function statusLabel(type) {
    if (type === 'Judicial case') return 'Disposition';
    if (type === 'Constitutional inquiry') return 'CCB advice';
    if (type === 'Overture') return 'Outcome';
    return 'Status';
  }

  function formatRecord(record) {
    const category = CATEGORIES[record.type] || { className: 'minutes', label: clean(record.type) || 'General Assembly minutes' };
    const rpr = record.type === 'RPR exception' ? rprDetails(record) : null;
    return {
      category,
      identifier: rpr?.identifier || identifier(record),
      title: rpr?.title || clean(record.title),
      excerpt: rpr?.excerpt || excerpt(record),
      assembly: assembly(record),
      sourcePage: sourcePage(record),
      status: clean(record.disposition),
      statusLabel: statusLabel(record.type),
      provisions: Array.isArray(record.provisions) ? record.provisions.filter(Boolean) : [],
      href: href(record),
    };
  }

  return { CATEGORIES, formatRecord, href, ordinal };
}));
