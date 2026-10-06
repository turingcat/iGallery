import { defineConfig } from '@playwright/test';
export default defineConfig({
  testDir: '.', testMatch: 'slideshow.spec.mjs',
  use: { headless: true },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1920, height: 1080 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 } } }
  ]
});
