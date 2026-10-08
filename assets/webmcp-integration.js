/* Expose public research records only, never the personal research workspace. */
(() => {
  const context = document.modelContext;
  if (typeof context?.registerTool !== 'function') return;
  const siteRoot = new URL('../', document.currentScript.src);
  // Registration can reject when browser permissions or duplicate names prevent it.
  function registerTool(name, description, inputSchema, execute) {
    Promise.resolve().then(() => context.registerTool({
      name, description, inputSchema, annotations: { readOnlyHint: true },
      execute: async (args) => execute(args)
    })).catch(error => console.warn(`WebMCP tool ${name} could not be registered`, error));
  }
  const result = value => ({ content: [{ type: 'text', text: JSON.stringify(value) }] });
  // The Ask page and both sites share the Assembly site's published prompt.
  const promptURL = new URL('assets/pca-research-prompt.txt', siteRoot);
  let researchPrompt;
  async function loadResearchPrompt() {
    if (!researchPrompt) researchPrompt = fetch(promptURL).then(async response => {
      if (!response.ok) throw new Error('Research prompt unavailable; open https://raymond-rishty.github.io/pca-ga/ask.html or retry');
      const template = await response.text();
      if (!template.trimEnd().endsWith('[INSERT YOUR QUESTION HERE]')) throw new Error('Research prompt format is invalid');
      return template;
    }).catch(error => { researchPrompt = null; throw error; });
    return researchPrompt;
  }
  registerTool('prepare_pca_research', 'Primary entry point for a PCA Constitution or General Assembly research question. Call this first with the user question to receive the Ask page research prompt, source routes, authority distinctions, and citation requirements. Then retrieve and verify the evidence using the search and reading tools or the linked sources; this tool does not answer the question.', {
    type: 'object', properties: {
      question: { type: 'string', minLength: 1, description: 'The full user question, including any provision, case, date, or scope requested' }
    }, required: ['question'], additionalProperties: false
  }, async (args = {}) => {
    if (typeof args.question !== 'string' || !args.question.trim()) throw new Error('A nonempty question is required');
    const template = await loadResearchPrompt();
    const marker = template.lastIndexOf('[INSERT YOUR QUESTION HERE]');
    return result({
      question: args.question.trim(),
      prompt: template.slice(0, marker) + args.question.trim() + '\n'
    });
  });
  let catalogue;
  async function records() {
    if (!catalogue) catalogue = Promise.all(['app/search_index.json', 'app/provision_search.json'].map(async path => {
      const response = await fetch(new URL(path, siteRoot));
      if (!response.ok) throw new Error('Search catalogue unavailable; check your connection');
      return response.json();
    })).then(parts => parts.flat()).catch(error => { catalogue = null; throw error; });
    return catalogue;
  }
  registerTool('search_assembly_records', 'Search PCA General Assembly catalogues and constitutional provisions. Returns public source links. Minutes, judicial holdings, CCB advice, RPR exceptions, and overtures have distinct authority.', {
    type: 'object', properties: {
      query: { type: 'string', description: 'Reference, case identifier, topic, keywords, or quoted phrase' },
      limit: { type: 'integer', minimum: 1, maximum: 50, default: 10 }
    }, required: ['query'], additionalProperties: false
  }, async (args = {}) => {
    if (typeof args.query !== 'string' || !args.query.trim()) throw new Error('A nonempty query is required');
    if (args.limit !== undefined && (!Number.isInteger(args.limit) || args.limit < 1 || args.limit > 50)) throw new Error('limit must be an integer from 1 to 50');
    const found = window.PcaSearchEngine.search(await records(), args.query);
    return result({ total: found.total, results: found.results.slice(0, args.limit ?? 10).map(({ record }) => ({
      ...record, url: new URL(String(record.url || '').replace(/\.md(?=($|[?#]))/i, '.html'), siteRoot).href
    })) });
  });
  registerTool('read_current_record', 'Read the current public record or catalogue. Personal research workspace and home search are excluded.', { type: 'object', properties: {}, additionalProperties: false }, () => {
    const article = document.querySelector('article.reading-col, article.ask-content');
    if (!article || document.querySelector('.page-main--workspace, .page-main--home')) throw new Error('Open a public record or catalogue to read its text');
    return result({ url: location.href, title: document.title, text: article.innerText });
  });
})();
