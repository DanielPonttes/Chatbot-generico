(() => {
  "use strict";

  const API = Object.freeze({
    status: "/api/status",
    personas: "/v1/personas",
    profiles: "/v1/target-profiles",
    missions: "/v1/notifications/missions",
    types: "/v1/notifications/types",
    generate: "/v1/notifications/generate",
    saved: "/v1/notifications/saved",
  });

  const state = {
    personas: [],
    profiles: [],
    missions: [],
    visibleMissions: [],
    types: [],
    saved: [],
    currentNotification: null,
    customFieldCounter: 0,
  };

  const element = (id) => document.getElementById(id);
  const form = element("notification-form");
  const personaSelect = element("persona-select");
  const profileSelect = element("profile-select");
  const missionSelect = element("mission-select");
  const contextFields = element("context-fields");
  const generateButton = element("generate-button");
  const generateButtonText = element("generate-button-text");
  const pushPreview = element("push-preview");
  const previewContent = element("preview-content");
  const historyList = element("history-list");
  const workflowSteps = Array.from(document.querySelectorAll("[data-workflow-step]"));
  const workflowLines = Array.from(document.querySelectorAll(".workflow-line"));

  const setText = (id, value) => {
    const node = element(id);
    if (node) node.textContent = value == null || value === "" ? "—" : String(value);
  };

  const setWorkflowStep = (currentStep) => {
    workflowSteps.forEach((step) => {
      const stepNumber = Number(step.dataset.workflowStep);
      const isCurrent = stepNumber === currentStep;
      step.classList.toggle("is-current", isCurrent);
      step.classList.toggle("is-complete", stepNumber < currentStep);
      if (isCurrent) step.setAttribute("aria-current", "step");
      else step.removeAttribute("aria-current");
    });
    workflowLines.forEach((line, index) => {
      line.classList.toggle("is-complete", index < currentStep - 1);
    });
  };

  const normalize = (value) => String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();

  const humanize = (value) => {
    const text = String(value || "").replace(/[_-]+/g, " ").trim();
    return text ? text.charAt(0).toUpperCase() + text.slice(1) : "Campo";
  };

  const CONTEXT_DESCRIPTIONS = Object.freeze({
    user_first_name: "Nome fictício usado para personalizar a saudação.",
    room_id: "Identifica a sala ou ambiente associado ao alerta.",
    presence_status: "Indica se o ambiente está ocupado, vazio ou em transição.",
    luminosity_level: "Informa o nível de luminosidade observado no ambiente.",
    time_window_elapsed: "Mostra há quanto tempo a condição foi observada.",
    potential_wasted_kwh: "Estima a energia que pode ser desperdiçada, em kWh.",
    lighting_power_delta: "Indica a variação de potência da iluminação, em W.",
    current_lux_reading: "Mede a luminosidade atual do ambiente, em lux.",
    target_lux_range: "Faixa de luminosidade considerada adequada para a atividade.",
    current_progress_percent: "Percentual de progresso já alcançado na missão.",
    recommended_temperature_range: "Faixa de temperatura sugerida para o ambiente.",
    user_setpoint_input: "Temperatura configurada pelo usuário no equipamento.",
    external_temperature: "Temperatura medida do lado de fora do ambiente.",
    internal_temperature: "Temperatura medida dentro do ambiente.",
    humidity_external: "Umidade relativa medida no lado de fora.",
    external_humidity: "Umidade relativa medida no lado de fora.",
    consumption_average_kwh: "Consumo médio do período, em kWh.",
    measured_consumption_kwh: "Consumo medido no cenário, em kWh.",
    expected_consumption_kwh: "Consumo esperado para comparar com o valor medido.",
    historical_baseline_kwh: "Referência histórica de consumo, em kWh.",
    room_baseline_consumption: "Consumo de referência daquele ambiente.",
    xp_reward: "Quantidade fictícia de pontos de experiência oferecida.",
    coins_reward: "Quantidade fictícia de EcoCoins oferecida.",
    coins_amount: "Quantidade de EcoCoins disponível para o usuário.",
    streak_days: "Número de dias consecutivos na sequência atual.",
    hours_remaining: "Horas restantes até o prazo do gatilho.",
    expiry_deadline: "Data ou horário fictício de expiração.",
    redemption_example: "Exemplo do benefício que pode ser resgatado.",
    new_feature_name: "Nome da funcionalidade fictícia apresentada.",
    new_feature_description: "Resumo curto da nova funcionalidade.",
    welcome_back_reward: "Recompensa fictícia para o retorno do usuário.",
    days_inactive: "Quantidade de dias desde o último acesso simulado.",
    saving_goal_percent: "Meta de economia definida para o desafio, em percentual.",
    reward_description: "Descrição da recompensa vinculada à missão.",
    community_name: "Nome fictício da comunidade ou grupo de comparação.",
    comparison_group: "Grupo usado como referência para a comparação.",
    current_rank_percentile: "Percentil atual do usuário dentro do grupo.",
    positions_gained: "Quantidade de posições avançadas no ranking.",
    recommended_action: "Ação simples sugerida para o usuário realizar.",
    target_action: "Ação que o gatilho espera que o usuário execute.",
    target_device: "Equipamento envolvido na ação da notificação.",
    target_time_window: "Janela de horário em que a ação deve acontecer.",
    remaining_action: "Ação que ainda falta para concluir a missão.",
    mission_name: "Nome da missão que será destacada na mensagem.",
    badge_name: "Nome fictício da conquista desbloqueada.",
    badge_description: "Descrição curta da conquista desbloqueada.",
  });

  const contextDescription = (key) => (
    CONTEXT_DESCRIPTIONS[key]
    || `Valor de ${humanize(key).toLowerCase()} usado para compor a mensagem.`
  );

  const createSvg = (pathData) => {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", pathData);
    svg.appendChild(path);
    return svg;
  };

  const errorMessage = (body, fallback) => {
    if (!body) return fallback;
    if (typeof body.detail === "string") return body.detail;
    if (body.detail && typeof body.detail.message === "string") return body.detail.message;
    if (typeof body.message === "string") return body.message;
    return fallback;
  };

  const request = async (path, options = {}) => {
    const controller = new AbortController();
    const timeoutMs = options.timeoutMs || 15_000;
    const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (options.body) headers.set("Content-Type", "application/json");

    try {
      const response = await fetch(path, {
        method: options.method || "GET",
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined,
        credentials: "same-origin",
        cache: "no-store",
        signal: controller.signal,
      });
      let body = null;
      try {
        body = await response.json();
      } catch (_error) {
        body = null;
      }
      if (!response.ok) {
        const failure = new Error(errorMessage(body, `Falha na requisição (${response.status}).`));
        failure.status = response.status;
        throw failure;
      }
      return body;
    } catch (error) {
      if (error && error.name === "AbortError") {
        throw new Error("O backend demorou além do limite. Tente novamente.");
      }
      throw error;
    } finally {
      window.clearTimeout(timeoutId);
    }
  };

  const toast = (title, message, kind = "info") => {
    const region = element("toast-region");
    const item = document.createElement("div");
    item.className = `toast${kind === "info" ? "" : ` is-${kind}`}`;
    const copy = document.createElement("div");
    const heading = document.createElement("strong");
    const detail = document.createElement("span");
    heading.textContent = title;
    detail.textContent = message;
    copy.append(heading, detail);
    item.appendChild(copy);
    region.appendChild(item);
    window.setTimeout(() => item.remove(), 4_500);
  };

  const setStudioStatus = (kind, message) => {
    const status = element("studio-status");
    status.className = `studio-status${kind === "ready" ? " is-ready" : kind === "error" ? " is-error" : ""}`;
    setText("studio-status-text", message);
  };

  const appendOption = (parent, value, label, selected = false) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    option.selected = selected;
    parent.appendChild(option);
    return option;
  };

  const populateSimpleSelect = (select, items, placeholder) => {
    select.replaceChildren();
    if (!items.length) {
      appendOption(select, "", placeholder);
      select.disabled = true;
      return;
    }
    items.forEach((item, index) => appendOption(select, item.id, item.name, index === 0));
    select.disabled = false;
  };

  const selectedById = (items, id, key = "id") => items.find((item) => String(item[key]) === String(id));

  const updatePersonaDescription = () => {
    const persona = selectedById(state.personas, personaSelect.value);
    setText("persona-description", persona ? persona.description : "Define o tom editorial da mensagem.");
    setText("preview-persona", persona ? persona.name : "—");
  };

  const updateProfileDescription = () => {
    const profile = selectedById(state.profiles, profileSelect.value);
    setText("profile-description", profile ? profile.description : "Ajusta a abordagem ao comportamento simulado.");
  };

  const currentMission = () => selectedById(state.missions, missionSelect.value, "mission_id");
  const currentType = () => {
    const mission = currentMission();
    return mission ? selectedById(state.types, mission.template_id) : null;
  };

  const renderMissionOptions = () => {
    const previous = missionSelect.value;
    state.visibleMissions = state.missions.filter((mission) => {
      if (mission.execution_status !== "mapped_template" || !mission.template_id) return false;
      return true;
    });

    missionSelect.replaceChildren();
    if (!state.visibleMissions.length) {
      appendOption(missionSelect, "", "Nenhuma missão encontrada");
      missionSelect.disabled = true;
      renderMission();
      return;
    }

    const groups = new Map();
    state.visibleMissions.forEach((mission) => {
      const category = mission.category || "Outras missões";
      if (!groups.has(category)) groups.set(category, []);
      groups.get(category).push(mission);
    });

    groups.forEach((missions, category) => {
      const group = document.createElement("optgroup");
      group.label = category;
      missions.forEach((mission) => {
        appendOption(group, mission.mission_id, `${mission.name} · ${mission.subtype || "template"}`, mission.mission_id === previous);
      });
      missionSelect.appendChild(group);
    });
    missionSelect.disabled = false;
    if (!missionSelect.value) missionSelect.value = state.visibleMissions[0].mission_id;
    const selectionChanged = missionSelect.value !== previous;
    if (selectionChanged) renderMission();
  };

  const requiredVariables = (mission, type) => {
    const values = type && Array.isArray(type.required_context_vars)
      ? type.required_context_vars
      : (mission && Array.isArray(mission.template_required_context_vars) ? mission.template_required_context_vars : []);
    return Array.from(new Set(values));
  };

  const allVariables = (mission, type) => {
    const values = [
      ...(mission && Array.isArray(mission.context_variables) ? mission.context_variables : []),
      ...(type && Array.isArray(type.context_variables) ? type.context_variables : []),
      ...requiredVariables(mission, type),
    ];
    return Array.from(new Set(values)).slice(0, 32);
  };

  const looksNumeric = (key) => /(^|_)(amount|count|days|hours|minutes|percent|percentage|kwh|kw|w|lux|temperature|level|score|xp|coins|reward|consumption|delta|progress|rank|position|value)($|_)/.test(key)
    && !/(description|name|status|range|window|deadline|unit|action)/.test(key);

  const sampleValue = (key) => {
    const samples = {
      user_first_name: "Ana",
      room_id: "sala-demo-204",
      sensor_external_id: "sensor-demo-01",
      presence_status: "sala vazia",
      target_action: "desligar a iluminação ao sair",
      recommended_action: "verificar luzes e ar-condicionado",
      target_time_window: "hoje, das 18h às 21h",
      time_window_elapsed: "últimos 30 minutos",
      expiry_deadline: "sexta-feira às 18h",
      target_lux_range: "300–500 lux",
      reward_description: "100 EcoCoins",
      redemption_example: "um kit de lâmpadas LED",
      new_feature_name: "Mapa de Economia",
      new_feature_description: "comparativo semanal por ambiente",
      welcome_back_reward: "50 EcoCoins",
      streak_days: 14,
      hours_remaining: 4,
      xp_reward: 50,
      coins_reward: 100,
      coins_amount: 500,
      potential_wasted_kwh: 3.2,
      measured_consumption_kwh: 8.4,
      expected_consumption_kwh: 5.2,
      anomaly_percent: 61.5,
      current_progress_percent: 72,
      current_lux_reading: 420,
      lighting_power_delta: 180,
      days_inactive: 21,
    };
    if (Object.prototype.hasOwnProperty.call(samples, key)) return samples[key];
    if (key.includes("percent")) return 65;
    if (key.includes("kwh")) return 2.4;
    if (key.includes("temperature")) return 24;
    if (key.includes("time") || key.includes("window")) return "última hora";
    if (key.includes("status")) return "ativo";
    if (key.includes("reward")) return 50;
    if (looksNumeric(key)) return 10;
    return "valor de demonstração";
  };

  const randomUnit = () => {
    if (window.crypto && typeof window.crypto.getRandomValues === "function") {
      const values = new Uint32Array(1);
      window.crypto.getRandomValues(values);
      return values[0] / 0x100000000;
    }
    return Math.random();
  };

  const randomInt = (minimum, maximum) => Math.floor(randomUnit() * (maximum - minimum + 1)) + minimum;
  const randomDecimal = (minimum, maximum, places = 1) => Number((minimum + randomUnit() * (maximum - minimum)).toFixed(places));
  const randomChoice = (values) => values[Math.floor(randomUnit() * values.length)];

  const randomContextValue = (key) => {
    const textSamples = {
      user_first_name: ["Ana", "Bruno", "Carla", "Diego", "Luiza", "Rafa"],
      presence_status: ["sala vazia", "ambiente ocupado", "transição de saída", "atividade reduzida"],
      target_action: ["desligar a iluminação ao sair", "ajustar o ar-condicionado", "confirmar o encerramento da sala"],
      recommended_action: ["verificar luzes e ar-condicionado", "reduzir o setpoint em 1 °C", "encerrar os equipamentos ao sair"],
      target_time_window: ["agora", "hoje, das 18h às 21h", "nos próximos 15 minutos", "antes do fim da aula"],
      time_window_elapsed: ["últimos 15 minutos", "última hora", "últimos 30 minutos", "desde o início da aula"],
      expiry_deadline: ["hoje às 18h", "sexta-feira às 18h", "amanhã às 12h", "domingo à meia-noite"],
      target_lux_range: ["300–500 lux", "250–450 lux", "350–550 lux"],
      recommended_temperature_range: ["23 °C–25 °C", "22 °C–24 °C", "24 °C–26 °C"],
      reward_description: ["100 EcoCoins", "um selo de eficiência", "bônus de 50 pontos"],
      redemption_example: ["um kit de lâmpadas LED", "um cupom de economia", "uma nova badge"],
      new_feature_name: ["Mapa de Economia", "Painel de Ambientes", "Desafio Relâmpago"],
      new_feature_description: ["comparativo semanal por ambiente", "visão rápida do consumo", "missão de cinco minutos"],
      welcome_back_reward: ["50 EcoCoins", "uma badge de retorno", "100 pontos de experiência"],
      community_name: ["usuários do campus", "sua turma", "moradores do prédio"],
      comparison_group: ["seu andar", "turmas semelhantes", "usuários do campus"],
      status_iluminacao: ["ligada", "desligada", "em modo econômico"],
      door_window_sensor_status: ["fechado", "aberto", "sem alteração"],
      shift_label: ["manhã", "tarde", "noite"],
      period_label: ["esta semana", "últimas 24 horas", "este mês"],
      interval_time_window: ["10 minutos", "15 minutos", "30 minutos"],
      target_device: ["iluminação", "ar-condicionado", "equipamento da sala"],
    };

    if (Object.prototype.hasOwnProperty.call(textSamples, key)) return randomChoice(textSamples[key]);
    if (key === "room_id") return `sala-demo-${randomInt(101, 799)}`;
    if (key === "sensor_external_id") return `sensor-demo-${String(randomInt(1, 99)).padStart(2, "0")}`;
    if (key.includes("lux")) return randomInt(220, 560);
    if (key.includes("temperature")) return randomDecimal(19, 29, 1);
    if (key.includes("humidity")) return randomInt(40, 78);
    if (key.includes("kwh") || key.includes("consumption")) return randomDecimal(1.2, 12.8, 1);
    if (key.includes("kw") || key.includes("power")) return randomDecimal(0.4, 4.8, 1);
    if (key.includes("percent") || key.includes("percentage")) return randomInt(8, 94);
    if (key.includes("minutes")) return randomInt(5, 90);
    if (key.includes("hours")) return randomInt(1, 12);
    if (key.includes("days") || key.includes("weeks") || key.includes("count")) return randomInt(2, 28);
    if (key.includes("rank") || key.includes("position")) return randomInt(2, 48);
    if (looksNumeric(key)) return randomInt(5, 100);
    return `${humanize(key)} fictício ${randomInt(100, 999)}`;
  };

  const createContextField = (key, required) => {
    const wrapper = document.createElement("label");
    wrapper.className = "context-field";
    wrapper.dataset.contextKey = key;

    const heading = document.createElement("span");
    heading.className = "context-field-heading";
    const label = document.createElement("span");
    label.className = "context-field-label";
    label.textContent = humanize(key);
    const mark = document.createElement("span");
    mark.className = required ? "required-mark" : "optional-mark";
    mark.textContent = required ? "obrigatório" : "opcional";
    heading.append(label, mark);

    const input = document.createElement("input");
    input.type = looksNumeric(key) ? "number" : "text";
    input.step = "any";
    input.dataset.contextValue = key;
    input.placeholder = `Ex.: ${sampleValue(key)}`;
    input.required = required;
    input.autocomplete = "off";

    const hint = document.createElement("small");
    hint.className = "field-hint";
    hint.id = `hint-${key.replace(/[^a-z0-9_-]/gi, "-")}`;
    hint.textContent = contextDescription(key);
    input.setAttribute("aria-describedby", hint.id);
    const technicalKey = document.createElement("small");
    technicalKey.className = "field-key";
    technicalKey.textContent = `Chave técnica: ${key}`;
    wrapper.append(heading, input, hint, technicalKey);
    return wrapper;
  };

  const renderContextFields = () => {
    const mission = currentMission();
    const type = currentType();
    contextFields.replaceChildren();
    if (!mission) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "Selecione uma missão para montar o contexto.";
      contextFields.appendChild(empty);
      return;
    }

    const required = new Set(requiredVariables(mission, type));
    const variables = allVariables(mission, type);
    if (!variables.length) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "Esta missão não exige variáveis adicionais.";
      contextFields.appendChild(empty);
      return;
    }
    variables.forEach((key) => contextFields.appendChild(createContextField(key, required.has(key))));
  };

  const renderMission = () => {
    const mission = currentMission();
    const type = currentType();
    setText("mission-category", mission ? mission.category : "Catálogo");
    setText("mission-template", mission ? mission.template_id : "—");
    setText("mission-example", mission ? (mission.example || type && type.description || "Sem exemplo editorial.") : "Selecione uma missão para visualizar o exemplo editorial.");
    element("rag-toggle").checked = Boolean(type && type.default_use_rag);
    generateButton.disabled = !mission || !personaSelect.value;
    renderContextFields();
    if (mission && personaSelect.value) setWorkflowStep(2);
    else setWorkflowStep(1);
  };

  const addCustomField = () => {
    if (contextFields.querySelectorAll("[data-context-value], .custom-field").length >= 32) {
      toast("Limite alcançado", "O contrato aceita no máximo 32 campos de contexto.", "error");
      return;
    }
    state.customFieldCounter += 1;
    const row = document.createElement("div");
    row.className = "custom-field";
    row.dataset.customField = String(state.customFieldCounter);

    const keyLabel = document.createElement("label");
    keyLabel.className = "field-control";
    const keyTitle = document.createElement("span");
    keyTitle.textContent = "Nome técnico";
    const keyInput = document.createElement("input");
    keyInput.type = "text";
    keyInput.dataset.customKey = "true";
    keyInput.placeholder = "ex.: campaign_label";
    keyInput.pattern = "[a-z][a-z0-9_]*";
    keyInput.autocomplete = "off";
    const keyHint = document.createElement("small");
    keyHint.textContent = "Nome curto usado pelo template.";
    keyLabel.append(keyTitle, keyInput, keyHint);

    const valueLabel = document.createElement("label");
    valueLabel.className = "field-control";
    const valueTitle = document.createElement("span");
    valueTitle.textContent = "Valor fictício";
    const valueInput = document.createElement("input");
    valueInput.type = "text";
    valueInput.dataset.customValue = "true";
    valueInput.placeholder = "valor de demonstração";
    valueInput.autocomplete = "off";
    const valueHint = document.createElement("small");
    valueHint.textContent = "Dado inventado para esta simulação.";
    valueLabel.append(valueTitle, valueInput, valueHint);

    const removeButton = document.createElement("button");
    removeButton.className = "remove-field";
    removeButton.type = "button";
    removeButton.title = "Remover campo opcional";
    removeButton.setAttribute("aria-label", removeButton.title);
    removeButton.appendChild(createSvg("M6 6l12 12M18 6 6 18"));
    removeButton.addEventListener("click", () => row.remove());
    row.append(keyLabel, valueLabel, removeButton);
    contextFields.appendChild(row);
    keyInput.focus();
  };

  const randomizeScenario = () => {
    if (!state.personas.length || !state.visibleMissions.length) {
      toast("Catálogo indisponível", "Aguarde o carregamento das opções para gerar um cenário.", "error");
      return;
    }

    personaSelect.value = randomChoice(state.personas).id;
    if (state.profiles.length) profileSelect.value = randomChoice(state.profiles).id;
    missionSelect.value = randomChoice(state.visibleMissions).mission_id;
    updatePersonaDescription();
    updateProfileDescription();
    renderMission();

    contextFields.querySelectorAll("[data-context-value]").forEach((input) => {
      input.value = String(randomContextValue(input.dataset.contextValue));
    });
    contextFields.querySelectorAll("[data-custom-value]").forEach((input) => {
      input.value = `valor fictício ${randomInt(100, 999)}`;
    });
    element("rag-toggle").checked = randomUnit() >= 0.5;
    toast("Cenário aleatório pronto", "Persona, missão e contexto foram sorteados. Revise antes de gerar.", "success");
  };

  const clearContext = () => {
    contextFields.querySelectorAll("input").forEach((input) => { input.value = ""; });
  };

  const coerceValue = (value, input) => {
    const trimmed = String(value).trim();
    if (input.type === "number" && trimmed !== "" && Number.isFinite(Number(trimmed))) return Number(trimmed);
    return trimmed;
  };

  const collectContext = () => {
    const context = {};
    const missing = [];
    contextFields.querySelectorAll("[data-context-value]").forEach((input) => {
      const key = input.dataset.contextValue;
      const value = input.value.trim();
      input.removeAttribute("aria-invalid");
      if (!value && input.required) {
        missing.push(humanize(key));
        input.setAttribute("aria-invalid", "true");
      }
      if (value) context[key] = coerceValue(value, input);
    });

    contextFields.querySelectorAll("[data-custom-field]").forEach((row) => {
      const keyInput = row.querySelector("[data-custom-key]");
      const valueInput = row.querySelector("[data-custom-value]");
      const key = keyInput.value.trim();
      const value = valueInput.value.trim();
      keyInput.removeAttribute("aria-invalid");
      if (!key && !value) return;
      if (!/^[a-z][a-z0-9_]*$/.test(key)) {
        keyInput.setAttribute("aria-invalid", "true");
        missing.push("nome técnico válido no campo opcional");
        return;
      }
      if (Object.prototype.hasOwnProperty.call(context, key)) {
        keyInput.setAttribute("aria-invalid", "true");
        missing.push(`campo sem duplicidade: ${key}`);
        return;
      }
      if (value) context[key] = coerceValue(value, valueInput);
    });

    if (missing.length) throw new Error(`Preencha: ${missing.join(", ")}.`);
    return context;
  };

  const setGenerating = (loading) => {
    generateButton.disabled = loading || !currentMission() || !personaSelect.value;
    generateButton.classList.toggle("is-loading", loading);
    generateButtonText.textContent = loading ? "Gerando no modelo local…" : "Gerar candidata";
    form.setAttribute("aria-busy", String(loading));
    if (loading) setWorkflowStep(2);
    else if (state.currentNotification) setWorkflowStep(3);
  };

  const updatePreview = (notification) => {
    const persona = selectedById(state.personas, notification.persona || personaSelect.value);
    const content = notification.content || notification.reply || "";
    state.currentNotification = {
      id: notification.id || notification.session_id,
      type: notification.type || "Pendente",
      content,
      persona: notification.persona || personaSelect.value,
      model: notification.model || "—",
    };
    previewContent.textContent = content;
    setText("preview-persona", persona ? persona.name : state.currentNotification.persona);
    setText("preview-model", state.currentNotification.model);
    setText("preview-length", content.length);
    setText("preview-state", state.currentNotification.type);
    element("preview-state").className = `preview-state ${statusClass(state.currentNotification.type)}`;
    setWorkflowStep(3);
    pushPreview.classList.remove("has-message");
    window.requestAnimationFrame(() => pushPreview.classList.add("has-message"));
    updatePreviewActions();
  };

  const updatePreviewActions = () => {
    const persisted = state.currentNotification
      ? state.saved.find((item) => item.id === state.currentNotification.id)
      : null;
    const enabled = Boolean(persisted && persisted.type === "Pendente");
    document.querySelectorAll("[data-preview-review]").forEach((button) => {
      button.disabled = !enabled;
      button.title = enabled ? `Marcar como ${button.dataset.previewReview.toLowerCase()}` : "Gere uma candidata para registrar o parecer";
    });
  };

  const generateNotification = async (event) => {
    event.preventDefault();
    const mission = currentMission();
    if (!mission || !personaSelect.value) {
      toast("Configuração incompleta", "Escolha uma persona e uma missão executável.", "error");
      return;
    }

    let context;
    try {
      context = collectContext();
    } catch (error) {
      toast("Contexto incompleto", error.message, "error");
      const invalid = contextFields.querySelector('[aria-invalid="true"]');
      if (invalid) invalid.focus();
      return;
    }

    setGenerating(true);
    setStudioStatus("loading", "Modelo local elaborando a candidata…");
    try {
      const response = await request(API.generate, {
        method: "POST",
        timeoutMs: 90_000,
        body: {
          mission_id: mission.mission_id,
          persona_id: personaSelect.value,
          target_profile_id: profileSelect.value || null,
          notification_context: context,
          use_rag: element("rag-toggle").checked,
          use_canonical_context: false,
        },
      });
      updatePreview(response);
      setStudioStatus("ready", "Candidata gerada e salva como pendente");
      toast("Candidata pronta", "Revise a experiência no celular e registre seu parecer.", "success");
      await loadHistory(false);
      if (window.matchMedia("(max-width: 900px)").matches) {
        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        window.setTimeout(() => element("preview-panel")?.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" }), 0);
      }
    } catch (error) {
      setStudioStatus("error", "Falha na geração da candidata");
      toast("Não foi possível gerar", error.message, "error");
    } finally {
      setGenerating(false);
    }
  };

  const formatDate = (value) => {
    const date = new Date(value || "");
    if (Number.isNaN(date.getTime())) return "data não informada";
    return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(date);
  };

  const statusClass = (status) => `status-${normalize(status).replace(/\s+/g, "-")}`;

  const reviewNotification = async (id, type) => {
    if (!id || !["Aprovada", "Reprovada", "Pendente"].includes(type)) return;
    setStudioStatus("loading", `Registrando parecer: ${type.toLowerCase()}…`);
    try {
      await request(`${API.saved}/${encodeURIComponent(id)}`, { method: "PATCH", body: { type } });
      if (state.currentNotification && state.currentNotification.id === id) {
        state.currentNotification.type = type;
        setText("preview-state", type);
        element("preview-state").className = `preview-state ${statusClass(type)}`;
        updatePreviewActions();
      }
      await loadHistory(false);
      setStudioStatus("ready", `Parecer registrado: ${type.toLowerCase()}`);
      toast("Revisão salva", `A candidata foi marcada como ${type.toLowerCase()}.`, "success");
    } catch (error) {
      setStudioStatus("error", "Não foi possível registrar o parecer");
      toast("Falha na revisão", error.message, "error");
    }
  };

  const historyAction = (notification, type, title, pathData, className) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `history-action ${className}`;
    button.title = title;
    button.setAttribute("aria-label", title);
    button.appendChild(createSvg(pathData));
    button.addEventListener("click", () => reviewNotification(notification.id, type));
    return button;
  };

  const renderHistory = () => {
    const filter = element("history-filter").value;
    const notifications = filter === "all" ? state.saved : state.saved.filter((item) => item.type === filter);
    historyList.replaceChildren();
    historyList.setAttribute("aria-busy", "false");
    setText("pending-count", state.saved.filter((item) => item.type === "Pendente").length);

    if (!notifications.length) {
      const empty = document.createElement("div");
      empty.className = "history-empty";
      const title = document.createElement("strong");
      const copy = document.createElement("span");
      title.textContent = filter === "all" ? "A fila está vazia" : `Nenhuma candidata ${filter.toLowerCase()}`;
      copy.textContent = "Gere uma nova candidata ou altere o filtro.";
      empty.append(title, copy);
      historyList.appendChild(empty);
      return;
    }

    notifications.forEach((notification) => {
      const row = document.createElement("article");
      row.className = "history-row";
      row.dataset.notificationId = notification.id || "";
      const openPreview = () => updatePreview(notification);
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "history-copy";
      copy.addEventListener("click", openPreview);
      const content = document.createElement("p");
      const date = document.createElement("small");
      content.textContent = notification.content;
      date.textContent = formatDate(notification.date);
      copy.append(content, date);

      const persona = document.createElement("div");
      persona.className = "history-meta";
      const personaLabel = document.createElement("span");
      const personaValue = document.createElement("strong");
      personaLabel.textContent = "Persona";
      personaValue.textContent = notification.persona || "—";
      persona.append(personaLabel, personaValue);

      const model = document.createElement("div");
      model.className = "history-meta history-model";
      const modelLabel = document.createElement("span");
      const modelValue = document.createElement("strong");
      modelLabel.textContent = "Modelo";
      modelValue.textContent = notification.model || "—";
      model.append(modelLabel, modelValue);

      const status = document.createElement("span");
      status.className = `history-status ${statusClass(notification.type)}`;
      status.textContent = notification.type;

      const actions = document.createElement("div");
      actions.className = "history-actions";
      if (notification.type === "Pendente") {
        actions.append(
          historyAction(notification, "Reprovada", "Reprovar candidata", "M6 6l12 12M18 6 6 18", "reject"),
          historyAction(notification, "Aprovada", "Aprovar candidata", "M5 12l4 4L19 6", "approve"),
        );
      }
      row.append(copy, persona, model, status, actions);
      historyList.appendChild(row);
    });
  };

  const loadHistory = async (announce = true) => {
    if (announce) historyList.setAttribute("aria-busy", "true");
    try {
      const saved = await request(API.saved);
      state.saved = Array.isArray(saved) ? saved : [];
      if (state.currentNotification) {
        const persisted = state.saved.find((item) => item.id === state.currentNotification.id);
        if (persisted) state.currentNotification.type = persisted.type;
      }
      renderHistory();
      updatePreviewActions();
    } catch (error) {
      historyList.replaceChildren();
      historyList.setAttribute("aria-busy", "false");
      const empty = document.createElement("div");
      empty.className = "history-empty";
      const title = document.createElement("strong");
      const copy = document.createElement("span");
      title.textContent = "Histórico indisponível";
      copy.textContent = error.message;
      empty.append(title, copy);
      historyList.appendChild(empty);
      if (announce) toast("Falha no histórico", error.message, "error");
    }
  };

  const bootstrap = async () => {
    setStudioStatus("loading", "Carregando catálogos do laboratório…");
    const results = await Promise.allSettled([
      request(API.personas),
      request(API.profiles),
      request(API.missions),
      request(API.types),
      request(API.status),
      request(API.saved),
    ]);

    const [personas, profiles, missions, types, status, saved] = results;
    state.personas = personas.status === "fulfilled" && Array.isArray(personas.value) ? personas.value : [];
    state.profiles = profiles.status === "fulfilled" && Array.isArray(profiles.value) ? profiles.value : [];
    state.missions = missions.status === "fulfilled" && missions.value && Array.isArray(missions.value.missions) ? missions.value.missions : [];
    state.types = types.status === "fulfilled" && Array.isArray(types.value) ? types.value : [];
    state.saved = saved.status === "fulfilled" && Array.isArray(saved.value) ? saved.value : [];

    populateSimpleSelect(personaSelect, state.personas, "Personas indisponíveis");
    populateSimpleSelect(profileSelect, state.profiles, "Perfis indisponíveis");
    renderMissionOptions();
    updatePersonaDescription();
    updateProfileDescription();
    renderHistory();

    const executableCount = state.missions.filter((mission) => mission.execution_status === "mapped_template" && mission.template_id).length;
    setText("mission-count", executableCount);
    if (status.status === "fulfilled" && status.value) {
      setText("active-model", status.value.model || "—");
      setText("preview-model", status.value.model || "—");
    }

    const catalogReady = state.personas.length && state.missions.length && state.types.length;
    if (catalogReady) {
      setStudioStatus("ready", "Laboratório conectado · dados fictícios");
    } else {
      const failed = results.filter((result) => result.status === "rejected").length;
      setStudioStatus("error", `${failed || 1} fonte(s) do laboratório indisponível(is)`);
      toast("Carga parcial", "Alguns catálogos não responderam. Atualize a página para tentar novamente.", "error");
    }
  };

  personaSelect.addEventListener("change", updatePersonaDescription);
  profileSelect.addEventListener("change", updateProfileDescription);
  missionSelect.addEventListener("change", renderMission);
  element("randomize-button").addEventListener("click", randomizeScenario);
  element("clear-context-button").addEventListener("click", clearContext);
  element("add-context-button").addEventListener("click", addCustomField);
  element("history-filter").addEventListener("change", renderHistory);
  element("refresh-history-button").addEventListener("click", () => loadHistory(true));
  document.querySelectorAll("[data-preview-review]").forEach((button) => {
    button.addEventListener("click", () => {
      if (state.currentNotification) reviewNotification(state.currentNotification.id, button.dataset.previewReview);
    });
  });
  form.addEventListener("submit", generateNotification);
  bootstrap();
})();
