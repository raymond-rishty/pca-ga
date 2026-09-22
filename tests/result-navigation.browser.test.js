const assert = require('node:assert/strict');
const { test } = require('node:test');
const { chromium } = require('playwright');

const baseUrl = process.env.PCA_TEST_BASE_URL || 'http://127.0.0.1:4173';

async function waitForReturnLink(page) {
  await page.waitForFunction(() => {
    const link = document.querySelector('#recordReturnLink');
    return link && !link.hidden && link.getAttribute('href');
  }, null, { timeout: 15000 });
}

test('search and catalogue results preserve return state and expose keyboard actions', async () => {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    reducedMotion: 'reduce',
  });
  try {
    await context.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: baseUrl }).catch(() => {});
    const page = await context.newPage();

    await page.goto(`${baseUrl}/?q=Woodham&scope=catalogue`, { waitUntil: 'networkidle' });
    await page.waitForSelector('.home-result__link[data-result-primary][href]', { timeout: 30000 });
    await page.evaluate(() => {
      sessionStorage.setItem('pca-ga-return-context', JSON.stringify({
        href: location.href,
        destination: location.pathname,
        label: 'Stale context'
      }));
    });
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForSelector('.home-result__link[data-result-primary][href]', { timeout: 30000 });
    assert.equal(await page.locator('#recordReturn').count(), 0);
    const searchResult = page.locator('.home-result__link[data-result-primary][href]').first();
    const searchHref = await searchResult.getAttribute('href');
    assert.match(searchHref, /\/?(?:cases|inquiries|overtures|rpr\/exc|studies|markdown)\//i);

    await searchResult.click();
    await page.waitForLoadState('domcontentloaded');
    await waitForReturnLink(page);
    assert.match(await page.locator('#recordReturnLink').getAttribute('href'), /[?&]q=Woodham/);

    await page.locator('#recordReturnLink').click();
    await page.waitForLoadState('networkidle');
    assert.equal(new URL(page.url()).searchParams.get('q'), 'Woodham');
    await page.waitForSelector('.home-result__link[data-result-primary][href]');

    const actions = page.locator('details.result-actions').first();
    await actions.locator('summary').click();
    await assert.doesNotReject(() => actions.locator('[data-result-action="save"]').waitFor({ state: 'visible' }));
    await assert.doesNotReject(() => actions.locator('[data-result-action="cite"]').waitFor({ state: 'visible' }));
    await assert.doesNotReject(() => actions.locator('[data-result-action="link"]').waitFor({ state: 'visible' }));

    await page.goto(`${baseUrl}/index/CASES.html`, { waitUntil: 'networkidle' });
    assert.equal(await page.locator('#recordReturn').count(), 0);
    await page.waitForSelector('.reading-col table [data-result-primary][href]', { timeout: 30000 });
    const catalogueResult = page.locator('.reading-col table [data-result-primary][href]').first();
    await catalogueResult.click();
    await page.waitForLoadState('domcontentloaded');
    await waitForReturnLink(page);
    assert.match(await page.locator('#recordReturnLink').getAttribute('href'), /CASES\.html/);

    await page.goBack({ waitUntil: 'networkidle' });
    await page.waitForSelector('.reading-col table [data-result-primary][href]');
    assert.match(new URL(page.url()).pathname, /\/index\/CASES\.html$/i);
  } finally {
    await context.close();
    await browser.close();
  }
});
