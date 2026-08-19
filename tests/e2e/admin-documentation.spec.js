const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');

const ADMIN_DIR = path.join(__dirname, '..', '..', 'deploy', 'procelbot', 'admin');

async function serveDocumentation(page) {
  const assets = {
    '/notifications/docs': ['notifications-docs.html', 'text/html'],
    '/notifications-docs.html': ['notifications-docs.html', 'text/html'],
    '/admin.css': ['admin.css', 'text/css'],
    '/notifications.css': ['notifications.css', 'text/css'],
    '/documentation.css': ['documentation.css', 'text/css'],
  };

  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const asset = assets[url.pathname];
    if (!asset) return route.fallback();
    return route.fulfill({
      status: 200,
      contentType: asset[1],
      body: fs.readFileSync(path.join(ADMIN_DIR, asset[0]), 'utf8'),
    });
  });
}

test.describe('Admin documentation', () => {
  test('explica o laboratório e mantém a navegação acessível', async ({ page }) => {
    await serveDocumentation(page);
    await page.goto('/notifications/docs');

    await expect(page.locator('h1')).toHaveText('Documentação do laboratório');
    await expect(page.locator('#visao-geral')).toContainText('Notification Studio');
    await expect(page.locator('#campos')).toContainText('Missão executável');
    await expect(page.locator('.docs-toc a')).toHaveCount(6);
    await expect(page.locator('.nav-item[aria-current="page"]')).toHaveText('Documentação');
    await expect(page.locator('a[href="/notifications"]')).toHaveCount(5);
  });

  test('não cria rolagem horizontal em viewport móvel', async ({ page }) => {
    await serveDocumentation(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/notifications/docs');

    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
    await expect(page.locator('.docs-endpoints article')).toHaveCount(4);
  });
});
