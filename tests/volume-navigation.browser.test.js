const assert = require('node:assert/strict');
const { test } = require('node:test');
const { chromium } = require('playwright');

const base = process.env.PCA_TEST_BASE_URL || 'http://127.0.0.1:8000/pca-ga';

async function withPage(width, action) {
  const browser = await chromium.launch();
  try {
    const context = await browser.newContext({ viewport: {width, height: 800}, reducedMotion: 'reduce', serviceWorkers: 'block' });
    const page = await context.newPage();
    await action(page);
  } finally {
    await browser.close();
  }
}

for (const width of [320, 1280]) {
  test('a direct citation, Contents and page lookup at ' + width + 'px', () => withPage(width, async page => {
    const volume = base + '/markdown/ga51_2024.html';
    await page.goto(volume + '#ga51-p808');
    await page.waitForFunction(() => document.querySelector('#volumeFolio').textContent.includes('p. 808'));
    await page.evaluate(() => scrollBy({top:80,behavior:'instant'}));
    const position = await page.evaluate(() => scrollY);
    const length = await page.evaluate(() => history.length);
    await page.locator('#volumeContents').click();
    const current = page.locator('#volumeTree [aria-current="location"]');
    await current.waitFor();
    await page.locator('#volumeTree a[href="#ga51-p5"]').evaluate(a => {
      for (let el = a.parentElement; el; el = el.parentElement) if (el.tagName === 'DETAILS') el.open = true;
    });
    await page.locator('#volumeTree a[href="#ga51-p5"]').click();
    await page.waitForURL(volume + '#ga51-p5');
    await page.locator('#readingBack').click();
    await page.waitForURL(volume + '#ga51-p808');
    await page.waitForFunction(y => Math.abs(scrollY - y) < 4, position);
    await page.goForward();
    await page.waitForURL(volume + '#ga51-p5');
    await page.locator('#volumeLookup').click();
    await page.locator('#volumeMode').selectOption('pdf');
    await page.locator('#volumeNumber').fill('808');
    await page.locator('#volumeNumber').press('Enter');
    await page.waitForURL(volume + '#ga51-pdf-p808');
    await page.waitForFunction(() => document.querySelector('#volumeFolio').textContent.includes('p. 801'));
    await page.locator('#volumeLookup').click();
    await page.locator('#volumeNumber').fill('unknown');
    await page.locator('#volumeNumber').press('Enter');
    assert.match(await page.locator('#volumeMessage').innerText(), /No matching/);
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('#volumeLookup').evaluate(el => el === document.activeElement), true);
    assert.equal(await page.evaluate(() => history.length), length + 2);
  }));
}

test('ambiguous printed folios resolve to shareable occurrence links and lookup works offline from the outline', () => withPage(390, async page => {
  await page.route('**/volume-outlines/**', route => route.abort());
  await page.goto(base + '/markdown/ga33_2005.html');
  await page.locator('#volumeContents').click();
  await page.getByRole('link', {name:'Open full outline'}).waitFor();
  await page.keyboard.press('Escape');
  await page.locator('#volumeLookup').click();
  await page.locator('#volumeNumber').fill('300');
  await page.locator('#volumeNumber').press('Enter');
  const choices = page.locator('#volumeChoices');
  await choices.getByText('PDF p. 302').waitFor();
  await choices.getByText('PDF p. 590').click();
  await page.waitForURL(url => url.hash === '#ga33-p300-at-pdf590');
  const shared = page.url();
  const freshTab = await page.context().newPage();
  await freshTab.goto(shared);
  await freshTab.waitForFunction(() => document.querySelector('#volumeFolio').textContent.includes('p. 300'));
  assert.equal(await freshTab.locator('#readingBack').isVisible(), false);
  await freshTab.close();
  await page.reload();
  await page.waitForFunction(() => document.activeElement?.id === 'ga33-p300-at-pdf590' || Math.abs(document.getElementById('ga33-p300-at-pdf590').getBoundingClientRect().top - document.getElementById('volumeNav').getBoundingClientRect().bottom) < 5);
}));

test('record families expose their catalogue, Assembly and source', () => withPage(390, async page => {
  for (const [path, catalogue] of [
    ['cases/ga51_2024__2022-23','JUDICIAL-CASES'],
    ['inquiries/ga03_1975__ci01','INQUIRIES'],
    ['inquiries/ga17_1989__ci02','CCB-OVERTURE-ADVICE'],
    ['overtures/ga01_1973__o1','OVERTURES'],
    ['rpr/exc/arizona__001','RPR'],
    ['studies/a-declaration-of-conscience-addressed-to-the-president-of-th__ga21_1993_p129','STUDIES'],
  ]) {
    await page.goto(base + '/' + path + '.html');
    const location = page.locator('#recordLocation');
    await location.locator('a[href$="/index/' + catalogue + '.html"]').waitFor();
    assert.ok(await location.getByLabel(/Open Assembly volume/).count() > 0);
    const source = location.getByRole('link',{name:/Read in the Minutes/});
    await source.waitFor();
    if (catalogue === 'JUDICIAL-CASES') assert.match(await source.textContent(), /pp\. 742–766/);
    if (catalogue === 'RPR') assert.ok(await location.locator('details a').count() > 1);
  }
  await page.goto(base + '/cases/ga52_2025__2025-07.html');
  assert.equal(await page.locator('#recordLocation').getByRole('link',{name:/Read in the Minutes/}).count(),0);
}));
