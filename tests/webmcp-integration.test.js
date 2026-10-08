const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const root = require('node:path').resolve(__dirname, '..');
async function check(site) {
  const tools = new Map();
  const isReader = site === 'pca-constitution-reader';
  const realEngine = require(root + (isReader ? '/search-engine.js' : '/assets/search-engine.js'));
  const records = isReader ? [{ book: 'bco', ref: '19-2', reference: 'BCO 19-2', title: 'Licensure', text: 'candidate for licensure', open: { ch: '19' } }] : JSON.parse(fs.readFileSync(root + '/app/search_index.json'));
  let fetches = 0;
  let promptFetches = 0;
  const template = isReader ? 'Research using llms.txt.\nQUESTION\n\n[INSERT YOUR QUESTION HERE]\n' : fs.readFileSync(root + '/_includes/pca-research-prompt.txt', 'utf8');
  const context = {
    URL, location: { href: 'https://example.com/' + site + '/#bco/19-2' },
    document: { modelContext: { registerTool: async tool => { assert.equal(tool.inputSchema.type, 'object'); assert.equal(tool.annotations.readOnlyHint, true); tools.set(tool.name, tool.execute); } }, currentScript: { src: 'https://example.com/pca-ga/assets/webmcp-integration.js' }, querySelector: () => null, getElementById: () => ({ innerText: 'Public provision' }) },
    window: { PcaSearchEngine: realEngine }, PcaConstitutionSearch: realEngine,
    buildSearch: () => records, appURL: () => 'https://example.com/pca-constitution-reader/',
    fetch: async url => { if (url.pathname.endsWith('/assets/pca-research-prompt.txt')) { promptFetches++; return { ok: true, text: async () => template }; } fetches++; assert.equal(url.origin, 'https://example.com'); return { ok: true, json: async () => url.pathname.endsWith('provision_search.json') ? [] : records }; }
  };
  vm.runInNewContext(fs.readFileSync(root + (isReader ? '/webmcp-integration.js' : '/assets/webmcp-integration.js'), 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(tools.size, 3);
  const prepare = tools.get('prepare_pca_research');
  await assert.rejects(() => prepare({question: '  '}), /nonempty/);
  assert.equal(promptFetches, 0);
  const question = 'What does BCO 38-4 require? Include "withdrawal" and historical changes. $literal';
  const brief = JSON.parse((await prepare({question})).content[0].text);
  assert.equal(brief.question, question);
  assert.equal(brief.prompt, template.slice(0, template.lastIndexOf('[INSERT YOUR QUESTION HERE]')) + question + '\n');
  assert.deepEqual(Object.keys(brief).sort(), ['prompt', 'question']);
  await prepare({question: 'A second question'});
  assert.equal(promptFetches, 1);
  const search = tools.get(isReader ? 'search_constitution' : 'search_assembly_records');
  await assert.rejects(async () => search({query: ''}), /nonempty/);
  await assert.rejects(async () => search({query: 'licensure', limit: 51}), /integer/);
  const data = JSON.parse((await search({query: isReader ? 'BCO 19-2' : 'Ascension', limit: 2})).content[0].text);
  assert.ok(data.total > 0); assert.ok(data.results.length <= 2);
  for (const row of data.results) assert.ok(row.url.startsWith('https://example.com/' + site + '/'));
  if (isReader) assert.equal(data.results[0].url, 'https://example.com/pca-constitution-reader/#bco/19-2');
  else { const studies = JSON.parse((await search({query:'Human Sexuality',limit:1})).content[0].text); assert.ok(studies.results[0].url.endsWith('.html')); await search({query: 'Ascension'}); assert.equal(fetches, 2); await assert.rejects(async () => tools.get('read_current_record')(), /public record/); }
  let unavailable = true;
  context.fetch = async () => unavailable ? {ok: false} : {ok: true, text: async () => template};
  vm.runInNewContext(fs.readFileSync(root + (isReader ? '/webmcp-integration.js' : '/assets/webmcp-integration.js'), 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  await assert.rejects(() => tools.get('prepare_pca_research')({question}), /Research prompt unavailable/);
  unavailable = false;
  const retried = JSON.parse((await tools.get('prepare_pca_research')({question})).content[0].text);
  assert.equal(retried.question, question);
  delete context.document.modelContext;
  context.fetch = () => { throw new Error('Unsupported browsers must not fetch'); };
  vm.runInNewContext(fs.readFileSync(root + (isReader ? '/webmcp-integration.js' : '/assets/webmcp-integration.js'), 'utf8'), context);
  const warnings = [];
  context.console = { warn: (...args) => warnings.push(args) };
  context.document.modelContext = { registerTool: () => Promise.reject(new Error('NotAllowedError')) };
  vm.runInNewContext(fs.readFileSync(root + (isReader ? '/webmcp-integration.js' : '/assets/webmcp-integration.js'), 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(warnings.length, 3);
  console.log(site + ': native registration, search, citations, validation, unsupported-browser and rejected-registration checks passed');
}
(async () => { await check('pca-ga'); })().catch(e => { console.error(e); process.exitCode = 1; });
