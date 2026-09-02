const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { test } = require('node:test');

const root = path.resolve(__dirname, '..');

function read(file) {
  return fs.readFileSync(path.join(root, file), 'utf8');
}

test('every full minutes volume exposes its PCA Historical Center source PDF', () => {
  const volumes = fs.readdirSync(path.join(root, 'markdown'))
    .filter((name) => /^ga\d+_\d+\.md$/.test(name));
  const layout = read('_layouts/default.html');

  assert.equal(volumes.length, 52);
  assert.match(layout, /page_type == 'volume' and page\.source_pdf\.file/);
  assert.match(layout, /https:\/\/www\.pcahistory\.org\/pca\/ga\/\{\{ page\.source_pdf\.file \}\}/);
  assert.match(layout, /target="_blank" rel="noopener noreferrer"/);

  for (const volume of volumes) {
    const text = fs.readFileSync(path.join(root, 'markdown', volume), 'utf8');
    assert.match(text, /^source_pdf:\n  file: \d+(?:st|nd|rd|th)_pcaga_\d{4}\.pdf$/m, volume);
  }
});

test('extracted pages use the shared registry-backed resolver and renderer', () => {
  const resolver = read('scripts/source_links.py');
  const include = read('_includes/source-pdf-links.html');
  const layout = read('_layouts/default.html');
  const inquiryLayout = read('_layouts/inquiry.html');
  const workflow = read('.github/workflows/pages.yml');
  const registryBuilder = read('scripts/build_source_registry.py');

  assert.match(resolver, /def load_registry\(/);
  assert.match(resolver, /def source_id_for_url\(/);
  assert.match(resolver, /def source_entries_for_record\(/);
  assert.match(resolver, /source_id:/);
  assert.match(resolver, /pdf_page:/);
  assert.match(include, /data-source-id/);
  assert.match(include, /source\.pdf_page \| default: source\.page/);
  assert.match(include, /data-source-pdf-actions/);
  assert.match(include, /data-source-url/);
  assert.match(include, /source_page != nil and source_page != ''/);
  assert.match(include, /page\.layout == 'ga53-overture'/);
  assert.match(layout, /include source-pdf-links\.html/);
  assert.match(inquiryLayout, /include source-pdf-links\.html/);
  assert.match(workflow, /build_source_registry\.py/);
  assert.match(workflow, /minutes-page-source-pdf\.test\.js/);
  assert.match(registryBuilder, /validate_registry\(/);

  for (const generator of [
    '24_case_pages.py',
    '26_case_pages_structured.py',
    '27_cjb_pages.py',
    '28_sjc_located_pages.py',
    '29_stub_pages.py',
    '30_inquiry_pages.py',
    '33_rpr_build.py',
    '36_ga53_overtures.py',
    '37_overture_pages.py',
    '37_study_pages.py',
  ]) {
    const generatorText = read(`scripts/${generator}`);
    assert.match(generatorText, /source_front_matter|source_id_for_url/, generator);
  }
});
