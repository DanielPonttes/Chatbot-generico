const { expect } = require('@playwright/test');

const defaultMocks = {
  personas: [
    {
      id: 'provocador',
      name: 'Provocador',
      description: 'Cutuca desperdicios de forma direta.',
    },
    {
      id: 'mentor',
      name: 'Mentor',
      description: 'Orienta com foco em economia.',
    },
  ],
  targetProfiles: [
    {
      id: 'gastao',
      name: 'Gastao',
      description: 'Ignora desperdicios no dia a dia.',
    },
    {
      id: 'consciente',
      name: 'Consciente',
      description: 'Ja tenta economizar energia.',
    },
  ],
  health: {
    status: 'healthy',
    provider: 'google',
    model: 'gemini-3-flash-preview',
    provider_available: true,
    message: null,
  },
  rooms: [
    {
      id: '2',
      label: 'Elevador',
      description: 'Bloco A - 4o andar',
    },
    {
      id: '8',
      label: 'Laboratorio',
      description: 'Bloco B - terreo',
    },
  ],
  sensors: [
    {
      id: 'SII-001',
      label: 'SII Smart - Sala 400D',
      description: 'Sensor principal',
      roomId: '2',
    },
    {
      id: 'SII-777',
      label: 'SII Smart - Lab B',
      description: 'Sensor secundario',
      roomId: '8',
    },
  ],
  people: [
    {
      id: 'ravilon',
      label: 'Ravilon A. Santos',
      description: 'MAT-001 | ravilon@exemplo.com',
    },
    {
      id: 'bia',
      label: 'Bianca Lima',
      description: 'MAT-002 | bia@exemplo.com',
    },
  ],
  proactiveResponse: {
    session_id: 'new-session',
    reply: 'Ar-condicionado ligado sem necessidade detectada na sala monitorada.',
    provider: 'google',
    model: 'gemini-3-flash-preview',
    context_summary: 'Sala Elevador (id=2) | Sensor SII-001 | Pessoa Ravilon A. Santos',
  },
  selections: {
    roomSearch: '2',
    roomDisplay: '2 | Elevador | Bloco A - 4o andar',
    sensorSearch: 'SII',
    sensorDisplay: 'SII-001 | SII Smart - Sala 400D | Sensor principal',
    personSearch: 'ravilon',
    personDisplay: 'ravilon | Ravilon A. Santos | MAT-001 | ravilon@exemplo.com',
  },
};

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function fulfillJson(route, data, status = 200) {
  return route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(data),
  });
}

function matchesQuery(option, query) {
  if (!query) return true;
  const haystack = [option.id, option.label, option.description]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  return haystack.includes(query.toLowerCase());
}

function applyLimit(options, rawLimit) {
  const limit = Number.parseInt(rawLimit || '', 10);
  if (!Number.isFinite(limit) || limit <= 0) return options;
  return options.slice(0, limit);
}

async function mockNotificationsApi(page, overrides = {}) {
  const personas = clone(overrides.personas || defaultMocks.personas);
  const targetProfiles = clone(overrides.targetProfiles || defaultMocks.targetProfiles);
  const health = clone(overrides.health || defaultMocks.health);
  const rooms = clone(overrides.rooms || defaultMocks.rooms);
  const sensors = clone(overrides.sensors || defaultMocks.sensors);
  const people = clone(overrides.people || defaultMocks.people);
  const proactiveResponse = clone(overrides.proactiveResponse || defaultMocks.proactiveResponse);
  const savedNotifications = clone(overrides.savedNotifications || []);

  const captures = {
    roomQueries: [],
    sensorQueries: [],
    personQueries: [],
    chatRequests: [],
    savedPosts: [],
    deletedIds: [],
    clearSavedCalls: 0,
  };

  await page.route('**/notifications/saved/all', async (route) => {
    if (route.request().method() !== 'DELETE') {
      return route.fallback();
    }
    captures.clearSavedCalls += 1;
    const deleted = savedNotifications.length;
    savedNotifications.length = 0;
    return fulfillJson(route, { status: 'success', deleted });
  });

  await page.route(/.*\/notifications\/saved\/[^/?]+$/, async (route) => {
    if (route.request().method() !== 'DELETE') {
      return route.fallback();
    }
    const url = new URL(route.request().url());
    const notifId = url.pathname.split('/').pop();
    captures.deletedIds.push(notifId);
    const index = savedNotifications.findIndex((item) => item.id === notifId);
    if (index === -1) {
      return fulfillJson(route, { detail: 'Notificacao nao encontrada' }, 404);
    }
    savedNotifications.splice(index, 1);
    return fulfillJson(route, { status: 'success' });
  });

  await page.route('**/notifications/saved', async (route) => {
    if (route.request().method() === 'GET') {
      return fulfillJson(route, savedNotifications);
    }

    if (route.request().method() === 'POST') {
      const payload = JSON.parse(route.request().postData() || '{}');
      captures.savedPosts.push(payload);
      savedNotifications.push(payload);
      return fulfillJson(route, { status: 'success' });
    }

    return route.fallback();
  });

  await page.route('**/personas', (route) => fulfillJson(route, personas));
  await page.route('**/target-profiles', (route) => fulfillJson(route, targetProfiles));
  await page.route('**/health', (route) => fulfillJson(route, health));

  await page.route('**/integrations/context/rooms**', (route) => {
    const url = new URL(route.request().url());
    const query = url.searchParams.get('query') || '';
    const limit = url.searchParams.get('limit');
    captures.roomQueries.push(Object.fromEntries(url.searchParams.entries()));

    const items = applyLimit(
      rooms.filter((option) => matchesQuery(option, query)),
      limit,
    );

    return fulfillJson(route, items);
  });

  await page.route('**/integrations/context/sensors**', (route) => {
    const url = new URL(route.request().url());
    const query = url.searchParams.get('query') || '';
    const roomId = url.searchParams.get('room_id') || '';
    const limit = url.searchParams.get('limit');
    captures.sensorQueries.push(Object.fromEntries(url.searchParams.entries()));

    const items = applyLimit(
      sensors.filter((option) => {
        if (roomId && option.roomId !== roomId) return false;
        return matchesQuery(option, query);
      }),
      limit,
    );

    return fulfillJson(route, items);
  });

  await page.route('**/integrations/context/people**', (route) => {
    const url = new URL(route.request().url());
    const query = url.searchParams.get('query') || '';
    const limit = url.searchParams.get('limit');
    captures.personQueries.push(Object.fromEntries(url.searchParams.entries()));

    const items = applyLimit(
      people.filter((option) => matchesQuery(option, query)),
      limit,
    );

    return fulfillJson(route, items);
  });

  await page.route('**/chat/proactive', async (route) => {
    const payload = JSON.parse(route.request().postData() || '{}');
    captures.chatRequests.push(payload);

    if (overrides.chatStatus && overrides.chatStatus !== 200) {
      return fulfillJson(
        route,
        overrides.chatError || { detail: { error: 'mock_error', message: 'Falha simulada' } },
        overrides.chatStatus,
      );
    }

    const body = typeof overrides.chatResponse === 'function'
      ? overrides.chatResponse(payload)
      : (overrides.chatResponse || proactiveResponse);

    return fulfillJson(route, body);
  });

  return {
    captures,
    savedNotifications,
  };
}

async function fillLookup(page, inputSelector, listSelector, searchValue, displayValue) {
  await page.fill(inputSelector, searchValue);
  await expect
    .poll(async () => (await page.locator(`${listSelector} option`).count()) > 0)
    .toBeTruthy();
  await page.fill(inputSelector, displayValue);
}

async function configureOperationalContext(page, selections = defaultMocks.selections) {
  await page.click('#configBtn');
  await expect(page.locator('#configModal')).toBeVisible();

  await fillLookup(
    page,
    '#roomLookupInput',
    '#roomLookupList',
    selections.roomSearch,
    selections.roomDisplay,
  );
  await page.dispatchEvent('#roomLookupInput', 'change');

  await fillLookup(
    page,
    '#sensorLookupInput',
    '#sensorLookupList',
    selections.sensorSearch,
    selections.sensorDisplay,
  );

  await fillLookup(
    page,
    '#personLookupInput',
    '#personLookupList',
    selections.personSearch,
    selections.personDisplay,
  );
}

module.exports = {
  defaultMocks,
  mockNotificationsApi,
  configureOperationalContext,
};
