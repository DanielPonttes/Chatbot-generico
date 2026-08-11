(() => {
  "use strict";

  const REFRESH_MS = 30_000;
  const refreshButton = document.getElementById("refresh-button");
  const connectionSummary = document.getElementById("connection-summary");
  const connectionDot = document.getElementById("connection-dot");
  const connectionMessage = document.getElementById("connection-message");
  let nextRefreshAt = Date.now() + REFRESH_MS;

  const setText = (id, value) => {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  };

  const numeric = (value) => {
    const result = Number(value);
    return Number.isFinite(result) ? result : null;
  };

  const number = (value, suffix = "") => {
    const result = numeric(value);
    return result === null ? "—" : `${result.toFixed(1)}${suffix}`;
  };

  const percent = (value) => {
    const result = numeric(value);
    return result === null ? null : Math.max(0, Math.min(100, result));
  };

  const bytes = (value) => {
    const result = numeric(value);
    if (result === null) return "—";
    const units = ["B", "KiB", "MiB", "GiB", "TiB"];
    let amount = result;
    let index = 0;
    while (amount >= 1024 && index < units.length - 1) {
      amount /= 1024;
      index += 1;
    }
    return `${amount.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
  };

  const duration = (value) => {
    const result = numeric(value);
    if (result === null) return "—";
    const total = Math.max(0, Math.floor(result));
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    if (days) return `${days}d ${hours}h`;
    if (hours) return `${hours}h ${minutes}m`;
    return `${minutes}m ${total % 60}s`;
  };

  const time = (value) => {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "—" : date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
  };

  const titleCase = (value) => String(value || "unknown").replace(/_/g, " ");

  const setConnection = (kind, message) => {
    connectionSummary.className = `connection-summary connection-${kind}`;
    connectionDot.className = "connection-dot";
    connectionMessage.textContent = message;
    document.body.classList.toggle("is-offline", kind === "bad");
  };

  const setStatusPill = (status) => {
    const normalized = String(status || "pending").toLowerCase();
    const good = ["healthy", "ok", "operational", "degraded"].includes(normalized);
    const bad = ["unhealthy", "failed", "error", "offline"].includes(normalized);
    const pill = document.getElementById("service-status-pill");
    pill.className = `status-pill status-${bad ? "bad" : good ? "good" : "pending"}`;
    pill.textContent = good ? "Operacional" : bad ? "Atenção" : titleCase(normalized);
  };

  const setMeter = (id, value, limit = 100) => {
    const element = document.getElementById(id);
    const result = numeric(value);
    if (!element || result === null) {
      if (element) element.style.width = "0%";
      return;
    }
    const safeLimit = Math.max(1, numeric(limit) || 100);
    const ratio = Math.max(0, Math.min(100, (result / safeLimit) * 100));
    element.style.width = `${ratio}%`;
    element.setAttribute("aria-valuenow", String(Math.round(Math.max(0, Math.min(safeLimit, result)))));
    element.classList.toggle("meter-red", ratio >= 85);
  };

  const setSignal = (node, body) => {
    const available = Boolean(node && node.gpu_available);
    const icon = document.getElementById("gpu-availability");
    icon.className = `signal-icon signal-${available ? "good" : "pending"}`;
    icon.textContent = available ? `${(node.gpus || []).length}×` : "—";
    setText("signal-value", available ? "Online" : "Standby");
    setText("signal-status", available ? "Telemetria da GPU recebida com sucesso." : "GPU sem telemetria disponível neste snapshot.");
    setText("hero-runtime-state", body.provider_available ? "Local inference online" : "Provider aguardando disponibilidade");
  };

  const renderServices = (services) => {
    const container = document.getElementById("services");
    container.replaceChildren();
    const entries = Object.entries(services || {});
    setText("service-count", entries.length ? `${entries.length} itens` : "—");
    if (!entries.length) {
      const empty = document.createElement("span");
      empty.className = "empty-state";
      empty.textContent = "Sem snapshot disponível.";
      container.appendChild(empty);
      return;
    }
    entries.forEach(([name, state]) => {
      const normalized = String(state || "unknown").toLowerCase();
      const active = normalized === "active" || normalized === "healthy" || normalized === "ok";
      const row = document.createElement("div");
      row.className = "service-row";
      const label = document.createElement("span");
      label.className = "service-name";
      const dot = document.createElement("span");
      dot.className = `service-dot service-dot-${active ? "active" : "failed"}`;
      dot.setAttribute("aria-hidden", "true");
      label.append(dot);
      label.appendChild(document.createTextNode(titleCase(name)));
      const value = document.createElement("strong");
      value.className = `service-state service-state-${active ? "active" : "failed"}`;
      value.textContent = titleCase(normalized);
      row.append(label, value);
      container.appendChild(row);
    });
  };

  const appendGpuDetail = (parent, labelText, valueText, meterValue = null, meterClass = "") => {
    const item = document.createElement("div");
    item.className = "gpu-detail";
    const label = document.createElement("span");
    label.textContent = labelText;
    const value = document.createElement("strong");
    value.textContent = valueText;
    item.append(label, value);
    if (meterValue !== null) {
      const meter = document.createElement("div");
      meter.className = "gpu-mini-meter";
      const fill = document.createElement("span");
      fill.className = meterClass;
      fill.style.width = `${Math.max(0, Math.min(100, meterValue))}%`;
      meter.appendChild(fill);
      item.appendChild(meter);
    }
    parent.appendChild(item);
  };

  const renderGpus = (gpus) => {
    const container = document.getElementById("gpus");
    container.replaceChildren();
    if (!gpus || !gpus.length) {
      const empty = document.createElement("span");
      empty.className = "empty-state";
      empty.textContent = "Nenhuma GPU disponível para telemetria.";
      container.appendChild(empty);
      return;
    }
    gpus.forEach((gpu) => {
      const card = document.createElement("article");
      card.className = "gpu-card";
      const top = document.createElement("div");
      top.className = "gpu-card-top";
      const name = document.createElement("p");
      name.className = "gpu-name";
      name.textContent = gpu.name || `GPU ${gpu.index}`;
      const index = document.createElement("span");
      index.className = "gpu-index";
      index.textContent = `GPU ${gpu.index}`;
      top.append(name, index);
      const details = document.createElement("div");
      details.className = "gpu-detail-grid";
      const utilization = percent(gpu.utilization_percent);
      const memoryTotal = numeric(gpu.memory_total_bytes);
      const memoryUsed = numeric(gpu.memory_used_bytes);
      const memoryPercent = memoryTotal && memoryUsed !== null ? Math.max(0, Math.min(100, (memoryUsed / memoryTotal) * 100)) : null;
      appendGpuDetail(details, "Uso", number(gpu.utilization_percent, "%"), utilization, "meter-blue");
      appendGpuDetail(details, "Memória", `${bytes(gpu.memory_used_bytes)} / ${bytes(gpu.memory_total_bytes)}`, memoryPercent, "meter-purple");
      appendGpuDetail(details, "Temperatura", number(gpu.temperature_c, " °C"));
      appendGpuDetail(details, "Potência", number(gpu.power_w, " W"));
      card.append(top, details);
      container.appendChild(card);
    });
  };

  const renderGpuHero = (gpus) => {
    const gpu = gpus && gpus[0];
    if (!gpu) {
      setText("hero-gpu-name", "GPU indisponível");
      setText("hero-temp", "—");
      setText("hero-util", "—");
      setText("hero-memory", "—");
      setText("hero-power", "—");
      setText("hero-temp-state", "aguardando telemetria");
      setText("hero-memory-state", "aguardando telemetria");
      return;
    }
    const memoryTotal = numeric(gpu.memory_total_bytes);
    const memoryUsed = numeric(gpu.memory_used_bytes);
    const memoryPercent = memoryTotal && memoryUsed !== null ? (memoryUsed / memoryTotal) * 100 : null;
    const temperature = numeric(gpu.temperature_c);
    setText("hero-gpu-name", gpu.name || `GPU ${gpu.index}`);
    setText("hero-temp", number(temperature, " °C"));
    setText("hero-util", number(gpu.utilization_percent, "%"));
    setText("hero-memory", memoryPercent === null ? "—" : `${memoryPercent.toFixed(1)}%`);
    setText("hero-power", number(gpu.power_w, " W"));
    setText("hero-temp-state", temperature === null ? "sem leitura" : temperature >= 83 ? "faixa de atenção" : "faixa normal");
    setText("hero-memory-state", memoryTotal ? `${bytes(memoryUsed)} de ${bytes(memoryTotal)}` : "sem leitura");
  };

  const render = (body) => {
    const node = body.node_metrics;
    const status = body.status || "unknown";
    const gpus = node && Array.isArray(node.gpus) ? node.gpus : [];
    const fresh = Boolean(node && node.fresh);
    document.body.classList.toggle("is-stale", Boolean(node && !fresh));
    setStatusPill(status);
    setText("service-status", titleCase(status));
    setText("service-status-detail", body.provider_available ? "backend respondendo" : "provider indisponível");
    setText("service-name", body.service || "—");
    setText("provider-name", body.provider || "—");
    setText("provider-summary", body.provider || "—");
    setText("model-name", body.model || "—");
    setText("model-summary", body.model || "modelo não informado");
    setText("process-uptime", duration(body.uptime_seconds));
    setText("uptime-summary", duration(body.uptime_seconds));
    setText("last-refresh", body.checked_at ? `Hoje, ${time(body.checked_at)}` : "agora");
    setText("metrics-fresh", node ? (fresh ? "Fresco" : "Stale") : "Indisponível");
    setText("metrics-age", node ? `${number(node.age_seconds)} s atrás` : "agente sem snapshot válido");
    setSignal(node, body);
    renderGpuHero(gpus);
    renderGpus(gpus);
    renderServices(node ? node.services : {});
    setText("hostname", node ? (node.hostname || "—") : "—");
    setText("cpu-value", node ? number(node.cpu_percent, "%") : "—");
    setText("memory-value", node ? number(node.memory_used_percent, "%") : "—");
    setText("disk-value", node ? number(node.disk_used_percent, "%") : "—");
    setText("host-uptime", node ? duration(node.host_uptime_seconds) : "—");
    setMeter("cpu-meter", node && node.cpu_percent);
    setMeter("memory-meter", node && node.memory_used_percent);
    setMeter("disk-meter", node && node.disk_used_percent);
  };

  const updateCountdown = () => {
    const remaining = Math.max(0, Math.ceil((nextRefreshAt - Date.now()) / 1000));
    setText("refresh-countdown", remaining ? `${remaining}s` : "agora");
  };

  const refresh = async () => {
    refreshButton.disabled = true;
    setConnection("pending", "Consultando o backend…");
    try {
      const response = await fetch("/api/status", { headers: { Accept: "application/json" }, cache: "no-store" });
      if (!response.ok) throw new Error(`status_${response.status}`);
      render(await response.json());
      setConnection("good", "Backend administrativo conectado");
      nextRefreshAt = Date.now() + REFRESH_MS;
    } catch (error) {
      setConnection("bad", error.message === "status_401" || error.message === "status_403" ? "Sessão do Cloudflare Access não autorizada" : "Não foi possível consultar o backend");
      setText("last-refresh", "Falha na leitura");
    } finally {
      refreshButton.disabled = false;
      updateCountdown();
    }
  };

  refreshButton.addEventListener("click", refresh);
  refresh();
  window.setInterval(refresh, REFRESH_MS);
  window.setInterval(updateCountdown, 1000);
  updateCountdown();
})();
