import { test, expect } from '@playwright/test';
import { readFile } from 'node:fs/promises';
const photo = n => `/api/photo/00000000-0000-0000-0000-${String(n).padStart(12, '0')}`;
const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=', 'base64');

async function setup(page, playlist, interval = 1) {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.clock.install();
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    expect(url.origin).toBe('http://frame.test');
    if (url.pathname === '/api/photos') {
      const data = playlist();
      if (data === null) return route.fulfill({status: 500});
      return route.fulfill({json: {photos: data.map(p => typeof p === 'string' ? {url: p} : p), interval_seconds: interval}});
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

test('uses a three-second fade and fifteen-second switch interval', async ({page}) => {
  await setup(page, () => [photo(1), photo(2)], 15);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(1));
  expect(await page.locator('.active').evaluate(image => getComputedStyle(image).transitionDuration)).toBe('3s');
  await page.clock.runFor(14000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(1));
  await page.clock.runFor(2000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(2));
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

test('keeps actual loaded image when next request in the same playlist becomes unavailable', async ({page}) => {
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
  list = [photo(3), photo(1)];
  await page.clock.runFor(17000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(1));
  list = [photo(9), photo(1)];
  await page.clock.runFor(17000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(1));
  list = [photo(2)];
  await page.clock.runFor(17000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(2));
});

test('dates switch with photos, survive failures and hide when missing', async ({page}) => {
  let list = [{url: photo(1), taken_date: '2020-01-02'}];
  await setup(page, () => list);
  const date = page.locator('#taken-date');
  await expect(date).toHaveText('2020-01-02');
  list = [{url: photo(9), taken_date: '2021-03-04'}, {url: photo(1), taken_date: '2020-01-02'}];
  await page.clock.runFor(3000);
  await expect(date).toHaveText('2020-01-02');
  list = [{url: photo(2), taken_date: '2021-03-04'}];
  await expect.poll(async () => {
    await page.clock.runFor(2000);
    return date.textContent();
  }).toBe('2021-03-04');
  list = [{url: photo(1)}];
  await expect.poll(async () => {
    await page.clock.runFor(2000);
    return date.isHidden();
  }).toBe(true);
  await expect(date).toBeHidden();
});

for (const [background, expected] of [['white', 'rgb(0, 0, 0)'], ['black', 'rgb(255, 255, 255)']]) {
  test(`date text contrasts with ${background} photo background`, async ({page}) => {
    const errors = await setup(page, () => []);
    // Keep the sampled label area inside the image on both viewport shapes.
    const body = await page.evaluate(color => {
      const canvas = document.createElement('canvas');
      canvas.width = innerWidth; canvas.height = innerHeight;
      const ctx = canvas.getContext('2d'); ctx.fillStyle = color;
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      return canvas.toDataURL().split(',')[1];
    }, background);
    await page.route('**' + photo(1), route => route.fulfill({body: Buffer.from(body, 'base64'), contentType: 'image/png'}));
    await page.route('**/api/photos', route => route.fulfill({json: {photos: [{url: photo(1), taken_date: '2020-01-02', location: 'Paris'}], interval_seconds: 30}}));
    await page.clock.runFor(6000);
    const date = page.locator('#taken-date');
    await expect(date).toBeVisible();
    await page.clock.runFor(3500);
    expect(await date.evaluate(el => getComputedStyle(el).color)).toBe(expected);
    await expect(page.locator('#taken-location')).toHaveCSS('color', expected);
    const box = await date.boundingBox();
    expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize().width);
    expect(box.y + box.height).toBeLessThanOrEqual(page.viewportSize().height);
    expect(errors).toEqual([]);
  });
}

test('samples the label region rather than the whole photo and updates on resize', async ({page}) => {
  await setup(page, () => []);
  const body = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = innerWidth; canvas.height = innerHeight;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = 'black'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = 'white'; ctx.fillRect(canvas.width - 320, canvas.height - 100, 320, 100);
    return canvas.toDataURL().split(',')[1];
  });
  await page.route('**' + photo(1), route => route.fulfill({body: Buffer.from(body, 'base64'), contentType: 'image/png'}));
  await page.route('**/api/photos', route => route.fulfill({json: {photos: [{url: photo(1), taken_date: '2020-01-02'}], interval_seconds: 30}}));
  await page.clock.runFor(6000);
  const date = page.locator('#taken-date');
  await expect(date).toBeVisible();
  await page.clock.runFor(3500);
  await expect(date).toHaveCSS('color', 'rgb(0, 0, 0)');
  // A taller viewport creates a black bar under the unchanged photo.
  const size = page.viewportSize();
  await page.setViewportSize({width: size.width, height: size.height + 300});
  await page.clock.runFor(100);
  await expect(date).toHaveCSS('color', 'rgb(255, 255, 255)');
});

test('date color follows the visible background during the initial fade', async ({page}) => {
  await setup(page, () => []);
  const body = await page.evaluate(() => {
    const c = document.createElement('canvas'); c.width = innerWidth; c.height = innerHeight;
    const ctx = c.getContext('2d'); ctx.fillStyle = 'white'; ctx.fillRect(0, 0, c.width, c.height);
    return c.toDataURL().split(',')[1];
  });
  await page.route('**' + photo(1), route => route.fulfill({body: Buffer.from(body, 'base64'), contentType: 'image/png'}));
  await page.route('**/api/photos', route => route.fulfill({json: {photos: [{url: photo(1), taken_date: '2020-01-02'}], interval_seconds: 30}}));
  await page.clock.runFor(5000);
  const date = page.locator('#taken-date');
  await expect(date).toBeVisible();
  const opacity = await page.locator('.active').evaluate(el => Number(getComputedStyle(el).opacity));
  expect(opacity).toBeLessThan(.1);
  await expect(date).toHaveCSS('color', 'rgb(255, 255, 255)');
  await page.clock.runFor(3500);
  await expect(date).toHaveCSS('color', 'rgb(0, 0, 0)');
});

test('location is below date, survives failed loads, and works without date', async ({page}) => {
  let list = [{url: photo(1), taken_date: '2020-01-02', location: 'China / Guangxi / Nanning'}];
  const errors = await setup(page, () => list);
  const date = page.locator('#taken-date'), location = page.locator('#taken-location');
  await expect(location).toHaveText('China / Guangxi / Nanning');
  const dateBox = await date.boundingBox(), locationBox = await location.boundingBox();
  expect(locationBox.y).toBeGreaterThanOrEqual(dateBox.y + dateBox.height);
  list = [{url: photo(9), location: 'London'}, {url: photo(1), taken_date: '2020-01-02', location: 'China / Guangxi / Nanning'}];
  await page.clock.runFor(3000);
  await expect(location).toHaveText('China / Guangxi / Nanning');
  list = [{url: photo(2), location: '<img src=x onerror=alert(1)>'}];
  await expect.poll(async () => { await page.clock.runFor(2000); return location.textContent(); }).toBe('<img src=x onerror=alert(1)>');
  await expect(date).toBeHidden();
  expect(await location.locator('img').count()).toBe(0);
  list = [{url: photo(1)}];
  await expect.poll(async () => { await page.clock.runFor(2000); return location.isHidden(); }).toBe(true);
  expect(errors).toEqual([]);
});

test('successful empty playlist removes visible photos and metadata immediately', async ({page}) => {
  let list = [{url: photo(1), taken_date: '2020-01-02', location: 'Paris'}];
  await setup(page, () => list);
  await expect(page.locator('#taken-location')).toHaveText('Paris');
  list = [];
  await expect.poll(async () => { await page.clock.runFor(2000); return page.locator('.active').count(); }).toBe(0);
  await expect(page.locator('#taken-date')).toBeHidden();
  await expect(page.locator('#taken-location')).toBeHidden();
  await expect(page.locator('#waiting')).toBeVisible();
});

test('successful refresh drops an excluded outgoing slide during crossfade', async ({page}) => {
  let list = [photo(1), photo(2)];
  await setup(page, () => list, 15);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(1));
  list = [photo(2)];
  await page.clock.runFor(16000);
  await expect(page.locator('.active')).toHaveAttribute('src', photo(2));
  await expect(page.locator(`.slide[src="${photo(1)}"]`)).toHaveCount(0);
});
