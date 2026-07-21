const { test, expect } = require('@playwright/test');
const {
  defaultMocks,
  mockNotificationsApi,
  configureOperationalContext,
} = require('./helpers/notifications-mocks');

test.describe('Notifications UI', () => {
  test('carrega bootstrap inicial com status, personas e lookups', async ({ page }) => {
    await mockNotificationsApi(page);

    await page.goto('/notifications');

    await expect(page.locator('h1')).toContainText('Notificações');
    await expect(page.locator('#personaSelect option')).toHaveCount(defaultMocks.personas.length);
    await expect(page.locator('#targetProfileSelect option')).toHaveCount(defaultMocks.targetProfiles.length);
    await expect(page.locator('.api-status-text').first()).toContainText(defaultMocks.health.model);
    await expect
      .poll(async () => await page.locator('#roomLookupList option').count())
      .toBe(defaultMocks.rooms.length);
    await expect
      .poll(async () => await page.locator('#sensorLookupList option').count())
      .toBe(defaultMocks.sensors.length);
    await expect
      .poll(async () => await page.locator('#personLookupList option').count())
      .toBe(defaultMocks.people.length);
  });

  test('gera notificacao contextual em viewport menor e envia ids normalizados', async ({ page }) => {
    const { captures } = await mockNotificationsApi(page);

    await page.setViewportSize({ width: 820, height: 620 });
    await page.goto('/notifications');
    await expect(page.locator('#personaSelect option')).toHaveCount(defaultMocks.personas.length);

    await page.selectOption('#personaSelect', 'provocador');
    await page.selectOption('#targetProfileSelect', 'gastao');

    await configureOperationalContext(page);
    await expect
      .poll(() => captures.sensorQueries.some((entry) => entry.room_id === '2'))
      .toBeTruthy();

    await page.click('#saveConfigBtn');
    await expect(page.locator('#configModal')).toBeHidden();
    await expect(page.locator('#configBtn')).toHaveClass(/text-primary-light/);

    await page.click('#generateBtn');

    await expect.poll(() => captures.chatRequests.length).toBe(1);
    expect(captures.chatRequests[0]).toMatchObject({
      persona_id: 'provocador',
      target_profile_id: 'gastao',
      room_id: '2',
      sensor_external_id: 'SII-001',
      pessoa_id: 'ravilon',
      use_rag: true,
    });

    await expect(page.locator('#notifContent')).toContainText('Ar-condicionado ligado');
    await expect(page.locator('#notifContextSummary')).toContainText('Contexto aplicado');
    await expect(page.locator('#notifContextSummary')).toContainText('SII-001');
    await expect(page.locator('#modelUsedTag')).toContainText('gemini-3-flash-preview');
  });

  test('aplica overrides na requisicao e salva feedback aprovado', async ({ page }) => {
    const { captures } = await mockNotificationsApi(page, {
      chatResponse: (payload) => ({
        session_id: 'new-session',
        reply: `Mensagem ajustada para ${payload.target_profile_id || 'sem alvo'}.`,
        provider: 'google',
        model: payload.model_override || 'gemini-3-flash-preview',
        context_summary: null,
      }),
    });

    await page.goto('/notifications');
    await page.selectOption('#personaSelect', 'mentor');
    await page.selectOption('#targetProfileSelect', 'gastao');

    await page.click('#configBtn');
    await expect(page.locator('#configModal')).toBeVisible();
    await page.selectOption('#modelOverrideSelect', 'gemini-3-pro-preview');
    await page.uncheck('#useRagToggle');
    await page.fill('#systemPromptOverride', 'Voce responde como auditor ambiental.');
    await page.click('#saveConfigBtn');

    await page.click('#generateBtn');

    await expect.poll(() => captures.chatRequests.length).toBe(1);
    expect(captures.chatRequests[0]).toMatchObject({
      persona_id: 'mentor',
      target_profile_id: 'gastao',
      model_override: 'gemini-3-pro-preview',
      use_rag: false,
      persona_override: {
        system_prompt: 'Voce responde como auditor ambiental.',
      },
    });

    await expect(page.locator('#notifPersonaName')).toContainText('Persona Customizada');
    await expect(page.locator('#notifContent')).toContainText('Mensagem ajustada para gastao.');

    await page.click('button[title="Boa notificação"]');

    await expect.poll(() => captures.savedPosts.length).toBe(1);
    expect(captures.savedPosts[0]).toMatchObject({
      type: 'Aprovada',
      content: 'Mensagem ajustada para gastao.',
      persona: 'Persona Customizada',
      model: 'gemini-3-pro-preview',
    });

    await expect(page.locator('#evalButtons')).toContainText('Obrigado pelo feedback');

    await page.getByRole('button', { name: /salvas/i }).click();
    await expect(page.locator('#savedModal')).toBeVisible();
    await expect(page.locator('#count-like')).toContainText('1');
    await expect(page.locator('#savedListContainer')).toContainText('Mensagem ajustada para gastao.');

    await page.click('#tab-dislike');
    await expect(page.locator('#savedListContainer')).toContainText('Nenhuma notificação salva');
  });

  test('reexibe a interface pronta para nova tentativa quando a geracao falha', async ({ page }) => {
    let dialogMessage = '';
    await mockNotificationsApi(page, { chatStatus: 500 });

    page.on('dialog', async (dialog) => {
      dialogMessage = dialog.message();
      await dialog.accept();
    });

    await page.goto('/notifications');
    await page.selectOption('#personaSelect', 'provocador');
    await page.selectOption('#targetProfileSelect', 'gastao');
    await page.click('#generateBtn');

    await expect.poll(() => dialogMessage).toContain('Erro ao gerar notificação: Falha na requisição');
    await expect(page.locator('#loadingState')).toBeHidden();
    await expect(page.locator('#generateBtn')).toBeEnabled();
    await expect(page.locator('#notificationArea')).toBeHidden();
  });
});
