import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
const photo = n => `/api/photo/00000000-0000-0000-0000-${String(n).padStart(12, '0')}`;
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64');

async function setup(page, playlist) {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.clock.install();
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    expect(url.origin).toBe('http://frame.test');
    if (url.pathname === '/api/photos') {
      const data = playlist();
      if (data === null) return route.fulfill({status: 500});
      return route.fulfill({json: {photos: data.map(url => ({url})), interval_seconds: 1}});
    }
    if (url.pathname.startsWith('/api/photo/')) {
      if (url.pathname === photo(9)) return route.fulfill({status: 404});
      return route.fulfill({body: png, contentType: 'image/png'});
    }
    const name = url.pathname === '/' ? 'index.html' : url.pathname.split('/').pop();
    return route.fulfill({body: await readFile(`igallery/web/${name}`),
      contentType: name.endsWith('.js') ? 'text/javascript' : name.endsWith('.css') ? 'text/css' : 'text/html'});
  });
  await page.goto('http://frame.test/');
  return errors;
}

test('switches preloaded photos without overflow', async ({page}) => {
  const errors = await setup(page, () => [photo(1), photo(2)]);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(1));
  await page.clock.runFor(2000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(2));
  expect(await page.evaluate(() => document.body.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('empty, bad image, service failure and new batch recover', async ({page}) => {
  let list = [];
  const errors = await setup(page, () => list);
  await expect(page.locator('#waiting')).toBeVisible();
  list = [photo(9), photo(1)];
  await page.clock.runFor(6000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(1));
  list = null;
  await page.clock.runFor(3000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(1));
  list = [photo(2)];
  await page.clock.runFor(3000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(2));
  expect(errors).toEqual([]);
});

test('keeps actual loaded image when next request becomes unavailable', async ({page}) => {
  await setup(page, () => [photo(1), photo(2)]);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(1));
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.clearBrowserCache');
  await page.route('**' + photo(2), route => route.fulfill({status: 404}));
  await cdp.send('HeapProfiler.collectGarbage');
  await page.clock.runFor(2000);
  await expect.poll(() => page.locator('.active').evaluate(image => image.naturalWidth)).toBeGreaterThan(0);
});

test('hung playlist request times out and recovers', async ({page}) => {
  await setup(page, () => [photo(1)]);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(1));
  let recover = false;
  await page.route('**/api/photos', route => {
    if (recover) return route.fulfill({json: {photos: [{url: photo(2)}], interval_seconds: 1}});
    return new Promise(() => {});
  });
  await page.clock.runFor(12000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(1));
  recover = true;
  await page.clock.runFor(15000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(2));
});

test('hung image and all bad images preserve display and recover', async ({page}) => {
  let list = [photo(1)];
  await setup(page, () => list);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(1));
  await page.route('**' + photo(3), () => new Promise(() => {}));
  list = [photo(3)];
  await page.clock.runFor(17000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(1));
  list = [photo(9)];
  await page.clock.runFor(17000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(1));
  list = [photo(2)];
  await page.clock.runFor(17000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(2));
});
