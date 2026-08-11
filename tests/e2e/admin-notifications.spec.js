const fs = require('fs');
const path = require('path');
const { test, expect } = require('@playwright/test');

const ADMIN_DIR = path.join(__dirname, '..', '..', 'deploy', 'procelbot', 'admin');

const fixtures = {
  personas: [
    { id: 'motivador', name: 'Motivador', description: 'Encoraja com clareza.' },
    { id: 'provocador', name: 'Provocador', description: 'Questiona o desperdício.' },
  ],
  profiles: [
    { id: 'engajado', name: 'Engajado', description: 'Já participa das ações.' },
    { id: 'gastao', name: 'Gastão', description: 'Precisa de estímulos objetivos.' },
  ],
  missions: {
    mission_count: 2,
    missions: [
      {
        mission_id: 'sala_vazia_luz_off',
        name: 'Sala Vazia, Luz Off',
        category: 'Feedback em Tempo Real',
        subtype: 'Alerta de Consumo Anômalo',
        template_id: 'feedback_alerta_consumo',
        execution_status: 'mapped_template',
        example: 'A sala está vazia e a iluminação continua ligada.',
        context_variables: ['room_id', 'potential_wasted_kwh', 'presence_status'],
        template_required_context_vars: ['room_id', 'potential_wasted_kwh'],
      },
      {
        mission_id: 'catalog_only',
        name: 'Em planejamento',
        category: 'Futuro',
        subtype: 'Catálogo',
        template_id: null,
        execution_status: 'catalog_only',
        context_variables: [],
        template_required_context_vars: [],
      },
    ],
  },
  types: [
    {
      id: 'feedback_alerta_consumo',
      name: 'Alerta de consumo',
      description: 'Aponta desperdício observado.',
      category: 'Feedback em Tempo Real',
      subtype: 'Alerta de Consumo Anômalo',
      default_use_rag: false,
      required_context_vars: ['room_id', 'potential_wasted_kwh'],
      context_variables: ['room_id', 'potential_wasted_kwh', 'presence_status'],
    },
  ],
};

async function serveAssets(page) {
  const assets = {
    '/notifications.html': ['notifications.html', 'text/html'],
    '/admin.css': ['admin.css', 'text/css'],
    '/notifications.css': ['notifications.css', 'text/css'],
    '/notifications.js': ['notifications.js', 'application/javascript'],
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

async function mockApi(page, options = {}) {
  const saved = [];
  const generated = [];
  const reviews = [];

  const json = (route, body, status = 200) => route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });

  await page.route('**/api/status', (route) => json(route, {
    status: 'healthy',
    provider: 'ollama',
    model: 'gemma4:26b',
    provider_available: true,
  }));
  await page.route('**/v1/personas', (route) => json(route, fixtures.personas));
  await page.route('**/v1/target-profiles', (route) => json(route, fixtures.profiles));
  await page.route('**/v1/notifications/missions', (route) => json(route, fixtures.missions));
  await page.route('**/v1/notifications/types', (route) => json(route, fixtures.types));
  await page.route('**/v1/notifications/generate', async (route) => {
    const payload = JSON.parse(route.request().postData() || '{}');
    generated.push(payload);
    const item = {
      id: 'candidate-1',
      type: 'Pendente',
      content: 'Sala demo 204 vazia: apague a luz e evite 3,2 kWh de desperdício. ⚡',
      persona: payload.persona_id,
      target_profile: payload.target_profile_id,
      model: 'gemma4:26b',
      date: '2026-08-11T12:00:00Z',
    };
    saved.unshift(item);
    return json(route, {
      session_id: item.id,
      reply: item.content,
      provider: 'ollama',
      model: item.model,
    });
  });
  await page.route(/.*\/v1\/notifications\/saved\/[^/?]+$/, async (route) => {
    if (route.request().method() !== 'PATCH') return route.fallback();
    const id = new URL(route.request().url()).pathname.split('/').pop();
    const payload = JSON.parse(route.request().postData() || '{}');
    reviews.push({ id, ...payload });
    if (options.reviewStatus && options.reviewStatus !== 200) {
      return json(route, { detail: { error: 'review_failed', message: 'Falha simulada na revisão' } }, options.reviewStatus);
    }
    const item = saved.find((entry) => entry.id === id);
    if (item) item.type = payload.type;
    return json(route, { status: 'success', id, type: payload.type });
  });
  await page.route('**/v1/notifications/saved', (route) => json(route, saved));
  return { generated, reviews, saved };
}

test.describe('Admin Notification Studio', () => {
  test('emula contexto manual, gera candidata e registra aprovação', async ({ page }) => {
    await serveAssets(page);
    const captures = await mockApi(page);

    await page.goto('/notifications.html');

    await expect(page.locator('h1')).toHaveText('Notification Studio');
    await expect(page.locator('#mission-count')).toHaveText('1');
    await expect(page.locator('#active-model')).toHaveText('gemma4:26b');
    await expect(page.locator('#mission-select option')).toHaveCount(1);
    await expect(page.locator('[data-context-value="room_id"]')).toBeVisible();

    await page.click('#fill-demo-button');
    await page.click('#generate-button');

    await expect.poll(() => captures.generated.length).toBe(1);
    expect(captures.generated[0]).toMatchObject({
      mission_id: 'sala_vazia_luz_off',
      persona_id: 'motivador',
      target_profile_id: 'engajado',
      use_canonical_context: false,
      notification_context: {
        room_id: 'sala-demo-204',
        potential_wasted_kwh: 3.2,
        presence_status: 'sala vazia',
      },
    });
    await expect(page.locator('#preview-content')).toContainText('Sala demo 204 vazia');
    await expect(page.locator('#history-list')).toContainText('Sala demo 204 vazia');

    await page.click('[data-preview-review="Aprovada"]');
    await expect.poll(() => captures.reviews.length).toBe(1);
    expect(captures.reviews[0]).toEqual({ id: 'candidate-1', type: 'Aprovada' });
    await expect(page.locator('#history-list')).toContainText('Aprovada');
  });

  test('permanece utilizável em viewport móvel e filtra missões', async ({ page }) => {
    await serveAssets(page);
    await mockApi(page);
    await page.setViewportSize({ width: 390, height: 844 });

    await page.goto('/notifications.html');
    await page.fill('#mission-search', 'inexistente');
    await expect(page.locator('#mission-select')).toBeDisabled();
    await expect(page.locator('#generate-button')).toBeDisabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  });

  test('impede geração quando o contexto obrigatório está vazio', async ({ page }) => {
    await serveAssets(page);
    const captures = await mockApi(page);

    await page.goto('/notifications.html');
    await page.click('#generate-button');

    await expect(page.locator('#toast-region')).toContainText('Contexto incompleto');
    await expect(page.locator('[data-context-value="room_id"]')).toHaveAttribute('aria-invalid', 'true');
    expect(captures.generated).toHaveLength(0);
  });

  test('registra reprovação e filtra a fila por parecer', async ({ page }) => {
    await serveAssets(page);
    const captures = await mockApi(page);

    await page.goto('/notifications.html');
    await page.click('#fill-demo-button');
    await page.click('#generate-button');
    await expect(page.locator('[data-preview-review="Reprovada"]')).toBeEnabled();
    await page.click('[data-preview-review="Reprovada"]');

    await expect.poll(() => captures.reviews.length).toBe(1);
    expect(captures.reviews[0]).toEqual({ id: 'candidate-1', type: 'Reprovada' });
    await page.selectOption('#history-filter', 'Aprovada');
    await expect(page.locator('#history-list')).toContainText('Nenhuma candidata aprovada');
    await page.selectOption('#history-filter', 'Reprovada');
    await expect(page.locator('#history-list')).toContainText('Sala demo 204 vazia');
  });

  test('mantém a candidata pendente quando a revisão falha', async ({ page }) => {
    await serveAssets(page);
    const captures = await mockApi(page, { reviewStatus: 500 });

    await page.goto('/notifications.html');
    await page.click('#fill-demo-button');
    await page.click('#generate-button');
    await expect(page.locator('[data-preview-review="Aprovada"]')).toBeEnabled();
    await page.click('[data-preview-review="Aprovada"]');

    await expect.poll(() => captures.reviews.length).toBe(1);
    await expect(page.locator('#toast-region')).toContainText('Falha na revisão');
    await expect(page.locator('#history-list')).toContainText('Pendente');
  });
});
