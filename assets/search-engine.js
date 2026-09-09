(function attachSearchEngine(root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.PcaSearchEngine = api;
}(typeof globalThis === 'undefined' ? this : globalThis, () => {
  const FIELD_LABELS = {
    title: 'title',
    identifier: 'identifier',
    assembly: 'Assembly/year',
    parties: 'parties',
    bco: 'BCO reference',
    topics: 'topic',
    proceeding: 'proceeding type',
    review: 'review standard',
    summary: 'summary',
    status: 'status',
    context: 'record context',
  };

  const FIELD_WEIGHTS = {
    identifier: 120,
    title: 100,
    bco: 85,
    parties: 70,
    topics: 55,
    proceeding: 50,
    review: 50,
    assembly: 35,
    summary: 30,
    context: 20,
    status: 15,
  };

  const FIELD_ORDER = Object.keys(FIELD_LABELS);
  const TYPE_LABELS = {
    'Judicial case': 'judicial cases',
    'Constitutional inquiry': 'constitutional inquiries',
    'RPR exception': 'RPR exceptions',
    Overture: 'overtures',
    'Position paper': 'studies and position papers',
    'General Assembly minutes': 'General Assembly minutes',
  };

  function asArray(value) {
    if (Array.isArray(value)) return value.filter(Boolean).map(String);
    return value ? [String(value)] : [];
  }

  function normalize(value) {
    return String(value || '')
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/&/g, ' and ')
      .replace(/['’]/g, '')
      .replace(/[^a-z0-9]+/g, ' ')
      .trim()
      .replace(/\s+/g, ' ');
  }

  function ordinal(number) {
    const n = Number(number);
    const mod100 = n % 100;
    if (mod100 >= 11 && mod100 <= 13) return `${n}th`;
    return `${n}${({ 1: 'st', 2: 'nd', 3: 'rd' })[n % 10] || 'th'}`;
  }

  function gaFromYear(year) {
    const number = Number(year);
    if (!Number.isInteger(number) || number < 1973 || number === 2020) return null;
    return number < 2020 ? number - 1972 : number - 1973;
  }

  function assemblyValues(record) {
    const values = asArray(record.assembly);
    const gaMatch = String(record.url || '').match(/ga(\d{1,2})_(\d{4})/i);
    if (gaMatch) values.push(`${gaMatch[1]} GA`, `${ordinal(gaMatch[1])} GA`, gaMatch[2]);
    const ga = gaFromYear(record.year);
    if (ga) values.push(`${ga} GA`, `${ordinal(ga)} GA`, String(record.year));
    return values;
  }

  function parseQuery(query) {
    const phrases = [];
    const terms = [];
    const source = String(query || '').trim();
    const tokenPattern = /"([^"\n]+)"|([^\s]+)/g;
    let match;
    while ((match = tokenPattern.exec(source))) {
      const value = normalize(match[1] || match[2]);
      if (!value) continue;
      if (match[1]) phrases.push(value);
      else terms.push(value);
    }

    const unquoted = normalize(source.replace(/"[^"\n]+"/g, ' '));
    const identifier = detectIdentifier(unquoted);
    return { source, phrases, terms, identifier };
  }

  function detectIdentifier(query) {
    const value = normalize(query);
    let match = value.match(/^bco\s+(\d+)\s+(\d+(?:\s+[a-z])?(?:\s+[a-z0-9]+)*)$/i);
    if (match) return { kind: 'bco', value: `bco ${match[1]} ${match[2]}` };

    match = value.match(/^(\d{1,2})\s+(\d+(?:\s+[a-z])?(?:\s+[a-z0-9]+)*)$/i);
    if (match) return { kind: 'bco', value: `bco ${match[1]} ${match[2]}` };

    match = value.match(/^(?:case\s+)?(\d{4})\s+(\d+[a-z]?)$/i);
    if (match) return { kind: 'case', value: `${match[1]} ${match[2]}` };

    match = value.match(/^(?:overture|o)\s+(?:number\s+)?(\d+)$/i);
    if (match) return { kind: 'overture', value: `overture ${Number(match[1])}` };

    match = value.match(/^(?:ccb\s+)?(?:inquiry|ci)\s+(\d+)$/i);
    if (match) return { kind: 'inquiry', value: `ccb inquiry ${Number(match[1])}` };

    return null;
  }

  function recordFields(record) {
    const identifier = asArray(record.identifier).concat(asArray(record.identifiers));
    if (record.type === 'Judicial case') {
      const subCase = String(record.sub || '').match(/(?:case\s+)([\d-]+[a-z]?)/i);
      if (subCase) identifier.push(`Case ${subCase[1]}`);
    }
    if (record.type === 'Overture') {
      const subOverture = String(record.sub || '').match(/\boverture\s+(\d+)/i);
      if (subOverture) identifier.push(`Overture ${Number(subOverture[1])}`);
    }
    if (record.type === 'Constitutional inquiry') {
      const inquiry = String(record.url || '').match(/__ci(\d+)/i);
      if (inquiry) identifier.push(`CCB inquiry ${Number(inquiry[1])}`);
    }

    return {
      title: asArray(record.title),
      identifier,
      assembly: assemblyValues(record),
      parties: asArray(record.parties),
      bco: asArray(record.provisions),
      topics: asArray(record.topics).concat(asArray(record.topic)),
      proceeding: asArray(record.proceeding_type),
      review: asArray(record.standard_of_review)
        .concat(asArray(record.review_standards))
        .concat(asArray(record.standard_of_review_detail)),
      summary: asArray(record.summary),
      status: asArray(record.disposition),
      context: asArray(record.sub),
    };
  }

  function normalizedFields(record) {
    const fields = recordFields(record);
    return Object.fromEntries(FIELD_ORDER.map((field) => [
      field,
      fields[field].map(normalize).filter(Boolean),
    ]));
  }

  function hasExactIdentifier(fields, identifier) {
    if (!identifier) return false;
    if (identifier.kind === 'bco') {
      const needle = identifier.value;
      return fields.bco.some((value) => {
        const normalized = normalize(value);
        return normalized === needle || normalized.replace(/^bco\s+/, '') === needle.replace(/^bco\s+/, '');
      });
    }
    const values = fields.identifier;
    if (identifier.kind === 'case') {
      return values.some((value) => normalize(value).replace(/^case\s+/, '') === identifier.value);
    }
    if (identifier.kind === 'overture') {
      return values.some((value) => normalize(value) === identifier.value);
    }
    if (identifier.kind === 'inquiry') {
      return values.some((value) => normalize(value) === identifier.value);
    }
    return false;
  }

  function phraseMatches(fieldValues, phrase) {
    return fieldValues.some((value) => value.includes(phrase));
  }

  function termMatches(fieldValues, term) {
    return fieldValues.some((value) => value.includes(term));
  }

  function search(records, query, options = {}) {
    const parsed = parseQuery(query);
    const scope = options.types?.size ? records.filter((record) => options.types.has(record.type)) : records;
    const resultRows = [];

    for (const record of scope) {
      const fields = normalizedFields(record);
      const exactIdentifier = hasExactIdentifier(fields, parsed.identifier);
      if (parsed.identifier && !exactIdentifier) continue;

      const matchedFields = new Set();
      const matchedTerms = [];
      const matchedPhrases = [];
      let score = parsed.identifier ? 10000 : 0;

      for (const phrase of parsed.phrases) {
        const phraseFields = FIELD_ORDER.filter((field) => phraseMatches(fields[field], phrase));
        if (!phraseFields.length) {
          matchedFields.clear();
          score = -1;
          break;
        }
        phraseFields.forEach((field) => matchedFields.add(field));
        matchedPhrases.push(phrase);
        score += 500 + Math.max(...phraseFields.map((field) => FIELD_WEIGHTS[field]));
      }
      if (score < 0) continue;

      for (const term of parsed.terms) {
        const termFields = FIELD_ORDER.filter((field) => termMatches(fields[field], term));
        if (!termFields.length) continue;
        termFields.forEach((field) => matchedFields.add(field));
        matchedTerms.push(term);
        score += Math.max(...termFields.map((field) => FIELD_WEIGHTS[field]));
        if (termFields.includes('title')) score += 25;
      }

      if (!parsed.identifier && !parsed.phrases.length && !matchedTerms.length) continue;
      if (!parsed.identifier && parsed.terms.length && !matchedTerms.length) continue;
      if (!parsed.source) score = 0;
      resultRows.push({
        record,
        score,
        matchedFields: FIELD_ORDER.filter((field) => matchedFields.has(field)),
        matchedTerms,
        matchedPhrases,
        exactIdentifier,
      });
    }

    resultRows.sort((a, b) => b.score - a.score
      || (Number(b.record.year) || 0) - (Number(a.record.year) || 0)
      || String(a.record.title || '').localeCompare(String(b.record.title || '')));

    const typeCount = new Set(scope.map((record) => record.type)).size;
    const scopeLabel = options.types?.size
      ? [...options.types].map((type) => TYPE_LABELS[type] || type).sort().join(', ')
      : `all ${typeCount} record types`;
    const suggestions = buildSuggestions(parsed, resultRows.length === 0, options.types);

    return {
      query: parsed.source,
      terms: parsed.terms,
      phrases: parsed.phrases,
      identifier: parsed.identifier,
      scope: scopeLabel,
      total: resultRows.length,
      results: resultRows,
      suggestions,
      emptyReason: emptyReason(parsed, resultRows.length, scope.length),
    };
  }

  function buildSuggestions(parsed, empty, types) {
    if (!empty) return [];
    const suggestions = [];
    if (parsed.identifier) suggestions.push('Check the identifier format or browse that record type.');
    if (parsed.terms.length > 1) suggestions.push('Remove one keyword and search the remaining terms separately.');
    if (parsed.phrases.length) suggestions.push('Remove the quotation marks to try a broader keyword search.');
    if (types?.size) suggestions.push('Clear the record-type filter and search the full catalogue.');
    suggestions.push('Try a distinctive word, a presbytery, a BCO reference, or a case number.');
    return [...new Set(suggestions)];
  }

  function emptyReason(parsed, count, scopeCount) {
    if (!parsed.source) return '';
    if (count) return '';
    if (!scopeCount) return 'The selected record-type filters contain no records.';
    if (parsed.identifier) return 'No record has that exact identifier in the selected scope.';
    if (parsed.phrases.length) return 'No record contains the exact quoted phrase in the selected scope.';
    return 'No record contains any of those keywords in the selected scope.';
  }

  return {
    FIELD_LABELS,
    normalize,
    parseQuery,
    recordFields,
    search,
  };
}));
