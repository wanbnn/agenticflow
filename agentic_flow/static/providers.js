(() => {
  const $ = (selector) => document.querySelector(selector);
  let providers = [];
  let types = [];
  let localModels = [];
  let localTasks = [];
  let discoveredModels = [];
  let hardware = {};
  let selectedTask = "text-generation";
  let selectedSort = "trending";
  let currentPage = 1;
  let discoveryPagination = {};
  let discoveryRequest = 0;
  let discoveryTimer;
  let installPollTimer;
  let selectedGgufModel = null;
  let ggufCatalog = null;
  const modal = $("#provider-modal");
  const form = $("#provider-form");

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (response.status === 401) {
      window.location.assign("/login");
      throw new Error("Sessão expirada.");
    }
    const data = response.status === 204 ? null : await response.json();
    if (!response.ok) throw new Error(data.detail || "Não foi possível continuar.");
    return data;
  }

  const typeFor = (value) => types.find((item) => item.type === value);

  function escapeHtml(value) {
    const element = document.createElement("div");
    element.textContent = value == null ? "" : String(value);
    return element.innerHTML;
  }

  function renderCards() {
    const cards = providers
      .map(
        (provider) => `
          <article class="provider-card" data-provider-id="${provider.id}">
            <div class="provider-card-head">
              <span class="provider-logo">${escapeHtml(provider.name.slice(0, 2).toUpperCase())}</span>
              <span class="provider-status ${provider.enabled ? "active" : ""}">${provider.enabled ? "Ativo" : "Inativo"}</span>
            </div>
            <h2>${escapeHtml(provider.name)}</h2>
            <p>${escapeHtml((typeFor(provider.type)?.name || provider.type))}</p>
            <code>${escapeHtml(provider.base_url)}</code>
            <div class="provider-card-actions">
              <span>${provider.has_api_key ? "● Chave salva" : "○ Sem chave"}</span>
              <button class="provider-edit" data-edit-provider="${provider.id}">Editar</button>
            </div>
          </article>`
      )
      .join("");
    $("#provider-grid").innerHTML =
      cards +
      `<button class="provider-card provider-new-card" id="new-provider-card">
        <span class="new-card-plus">+</span>
        <strong>Conectar provedor</strong>
        <small>OpenAI, Anthropic, Ollama e compatíveis</small>
      </button>`;
    document.querySelectorAll("[data-edit-provider]").forEach((button) =>
      button.addEventListener("click", () => openModal(button.dataset.editProvider))
    );
    $("#new-provider-card").addEventListener("click", () => openModal());
  }

  function applyTypeDefaults(force = false) {
    const definition = typeFor($("#provider-type").value);
    if (!definition) return;
    $("#provider-type-help").textContent = definition.description;
    if (force || !$("#provider-name").value) $("#provider-name").value = definition.name;
    if (force || !$("#provider-base-url").value) $("#provider-base-url").value = definition.base_url;
    if (force || !$("#provider-model").value) $("#provider-model").value = definition.default_model;
    $("#provider-api-key").closest(".field").classList.toggle("optional-key", !definition.requires_key);
    $("#provider-api-key").placeholder = definition.requires_key
      ? "Cole a chave aqui"
      : "Opcional para este provedor";
    if (definition.protocol === "local") {
      const ready = localModels.filter((model) => model.status === "ready");
      if ((force || !$("#provider-model").value) && ready.length) {
        $("#provider-model").value = ready[0].id;
      }
      $("#provider-model").placeholder = "ID mdl-... exibido abaixo";
    } else {
      $("#provider-model").placeholder = "";
    }
  }

  const TASK_LABELS = {
    "text-generation": "LLMs",
    "image-text-to-text": "LLMs multimodais",
    "image-to-text": "Visão",
    "automatic-speech-recognition": "Transcrição",
    "text-to-audio": "Voz",
    "text-to-image": "Imagens",
    "text-to-video": "Texto → vídeo",
    "image-to-video": "Imagem → vídeo",
    "image-to-3d": "Imagem → 3D",
    "text-to-3d": "Texto → 3D",
    "feature-extraction": "Embeddings",
  };

  const SORT_LABELS = {
    trending: "em alta",
    downloads: "mais baixados",
    likes: "mais curtidos",
    updated: "atualizados recentemente",
  };

  function formatCompact(value) {
    return new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(Number(value || 0));
  }

  function formatBytes(value) {
    const bytes = Number(value || 0);
    if (!bytes) return "Tamanho não informado";
    const units = ["B", "KB", "MB", "GB", "TB"];
    const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    return `${(bytes / 1024 ** index).toFixed(index > 2 ? 1 : 0)} ${units[index]}`;
  }

  function taskName(task) {
    return TASK_LABELS[task] || localTasks.find((item) => item.task === task)?.name || task;
  }

  function capabilityBadges(model) {
    const inputs = model.capabilities?.input_modalities || [];
    const outputs = model.capabilities?.output_modalities || [];
    const badges = [];
    if (inputs.includes("image")) badges.push("Aceita imagem");
    if (inputs.includes("text")) badges.push("Aceita texto");
    if (inputs.includes("audio")) badges.push("Aceita áudio");
    if (outputs.includes("image")) badges.push("Gera imagem");
    if (outputs.includes("text")) badges.push("Retorna texto");
    if (outputs.includes("audio")) badges.push("Gera áudio");
    if (outputs.includes("3d")) badges.push("Gera 3D");
    return badges.map((badge) => `<span>${escapeHtml(badge)}</span>`).join("");
  }

  function installedFor(model) {
    return localModels.find(
      (item) => item.repository_id === model.id && item.task === model.task && item.revision === "main"
    );
  }

  function showLibraryFeedback(message, tone = "info") {
    const feedback = $("#model-library-feedback");
    feedback.textContent = message;
    feedback.className = `model-library-feedback ${tone}`;
  }

  function clearLibraryFeedback() {
    $("#model-library-feedback").className = "model-library-feedback hidden";
  }

  function renderTaskTabs() {
    $("#model-task-tabs").innerHTML = localTasks.map((item) => `
      <button type="button" class="model-task-tab ${item.task === selectedTask ? "active" : ""}" data-model-task="${escapeHtml(item.task)}">
        ${escapeHtml(taskName(item.task))}
      </button>`).join("");
    document.querySelectorAll("[data-model-task]").forEach((button) =>
      button.addEventListener("click", () => {
        selectedTask = button.dataset.modelTask;
        currentPage = 1;
        renderTaskTabs();
        loadDiscovery();
      })
    );
  }

  function modelCompatibility(model) {
    if (model.gated) return { label: "Requer acesso", tone: "warning", detail: "Token do Hugging Face necessário" };
    if (model.runtime_format === "auto-resolve") {
      return { label: "Formato adaptado", tone: "neutral", detail: "O AgenticFlow localizará uma variante Diffusers executável" };
    }
    const memory = Number(hardware.devices?.[0]?.total_memory_bytes || 0);
    const estimated = Number(model.estimated_memory_bytes || 0);
    if (memory && estimated && estimated > memory * 0.9) {
      return { label: "Modelo grande", tone: "warning", detail: `Estimativa ${formatBytes(estimated)} para ${formatBytes(memory)} de VRAM` };
    }
    if (hardware.backend === "cpu") return { label: "Compatível com CPU", tone: "neutral", detail: "A execução pode ser mais lenta" };
    return { label: "Compatível", tone: "success", detail: hardware.devices?.[0]?.name || "Hardware disponível" };
  }

  function renderDiscovery() {
    const grid = $("#model-discovery-grid");
    const range = discoveryPagination.start && discoveryPagination.end
      ? `${discoveryPagination.start}–${discoveryPagination.end}`
      : "";
    $("#model-result-count").textContent = range ? `Exibindo ${range}` : "";
    $("#model-discovery-caption").textContent = `${taskName(selectedTask)} · ${SORT_LABELS[selectedSort]} no Hugging Face`;
    if (!discoveredModels.length) {
      grid.innerHTML = '<div class="model-empty-state"><strong>Nenhum modelo encontrado</strong><span>Tente outro termo ou categoria.</span></div>';
      renderPagination();
      return;
    }
    grid.innerHTML = discoveredModels.map((model) => {
      const installed = installedFor(model);
      const compatibility = modelCompatibility(model);
      const status = installed?.status;
      const buttonLabel = status === "ready" ? "Instalado" : status === "installing" ? "Instalando…" : status === "error" ? "Tentar novamente" : "Instalar";
      const disabled = ["ready", "installing"].includes(status);
      const parameterLabel = model.parameters ? `${formatCompact(model.parameters)} parâmetros` : formatBytes(model.estimated_memory_bytes);
      return `<article class="model-catalog-card ${status || ""}" data-discovery-model="${escapeHtml(model.id)}">
        <div class="model-card-top">
          <span class="model-org-mark">${escapeHtml(model.id.split("/")[0].slice(0, 2).toUpperCase())}</span>
          <span class="model-compatibility ${compatibility.tone}">${escapeHtml(compatibility.label)}</span>
        </div>
        <div class="model-card-title">
          <h3>${escapeHtml(model.id.split("/").slice(1).join("/") || model.id)}</h3>
          <span>${escapeHtml(model.id.split("/")[0])}</span>
        </div>
        <p class="model-card-description">${escapeHtml(compatibility.detail)}</p>
        <div class="model-card-metrics">
          ${model.trending_score ? `<span title="Pontuação de tendência">🔥 ${formatCompact(model.trending_score)}</span>` : ""}
          <span title="Downloads">↓ ${formatCompact(model.downloads)}</span>
          <span title="Curtidas">♡ ${formatCompact(model.likes)}</span>
          <span>${escapeHtml(parameterLabel)}</span>
        </div>
        <div class="model-card-tags">
          <span>${escapeHtml(model.library || "Hugging Face")}</span>
          ${model.gguf ? '<span>GGUF · llama.cpp</span>' : ""}
          ${model.license ? `<span>${escapeHtml(model.license)}</span>` : ""}
        </div>
        <div class="model-capability-badges">${capabilityBadges(model)}</div>
        ${status === "error" ? `<div class="model-install-error">${escapeHtml(installed.error || "A instalação falhou.")}</div>` : ""}
        ${status === "installing" ? '<div class="model-install-progress"><span></span></div>' : ""}
        <button type="button" class="button ${disabled ? "secondary" : "primary"} model-install-button" data-install-model="${escapeHtml(model.id)}" ${disabled ? "disabled" : ""}>
          ${status === "installing" ? '<span class="model-spinner"></span>' : ""}${!status && model.gguf ? "Escolher quantização" : buttonLabel}
        </button>
      </article>`;
    }).join("");
    document.querySelectorAll("[data-install-model]").forEach((button) =>
      button.addEventListener("click", () => installDiscoveredModel(button.dataset.installModel))
    );
    renderPagination();
  }

  function renderPagination() {
    const pagination = $("#model-pagination");
    const page = Number(discoveryPagination.page || currentPage);
    const hasPrevious = Boolean(discoveryPagination.has_previous);
    const hasNext = Boolean(discoveryPagination.has_next);
    if (!discoveredModels.length && !hasPrevious) {
      pagination.classList.add("hidden");
      pagination.innerHTML = "";
      return;
    }
    const firstVisible = Math.max(1, page - 2);
    const lastVisible = hasNext ? page + 1 : page;
    const pages = [];
    for (let number = firstVisible; number <= lastVisible; number += 1) pages.push(number);
    pagination.classList.remove("hidden");
    pagination.innerHTML = `
      <button type="button" class="model-page-direction" data-model-page="${page - 1}" ${hasPrevious ? "" : "disabled"} aria-label="Página anterior">← <span>Anterior</span></button>
      <div class="model-page-numbers">
        ${firstVisible > 1 ? '<button type="button" data-model-page="1">1</button><span>…</span>' : ""}
        ${pages.map((number) => `<button type="button" class="${number === page ? "active" : ""}" data-model-page="${number}" ${number === page ? 'aria-current="page"' : ""}>${number}</button>`).join("")}
      </div>
      <button type="button" class="model-page-direction" data-model-page="${page + 1}" ${hasNext ? "" : "disabled"}><span>Próxima</span> →</button>`;
    pagination.querySelectorAll("[data-model-page]:not([disabled])").forEach((button) =>
      button.addEventListener("click", () => {
        const requestedPage = Number(button.dataset.modelPage);
        if (requestedPage === currentPage) return;
        currentPage = requestedPage;
        loadDiscovery({ scroll: true });
      })
    );
  }

  async function loadDiscovery({ scroll = false } = {}) {
    const requestId = ++discoveryRequest;
    const query = $("#model-library-search").value.trim();
    $("#model-discovery-grid").innerHTML = '<div class="model-library-loading"><span class="model-spinner"></span>Buscando modelos no Hugging Face…</div>';
    $("#model-pagination").classList.add("hidden");
    clearLibraryFeedback();
    try {
      const result = await api(`/api/huggingface/models?q=${encodeURIComponent(query)}&task=${encodeURIComponent(selectedTask)}&page=${currentPage}&per_page=18&sort=${encodeURIComponent(selectedSort)}`);
      if (requestId !== discoveryRequest) return;
      discoveredModels = result.items;
      discoveryPagination = result.pagination;
      renderDiscovery();
      if (scroll) $("#model-discovery-caption").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      if (requestId !== discoveryRequest) return;
      discoveredModels = [];
      discoveryPagination = {};
      $("#model-discovery-grid").innerHTML = `<div class="model-empty-state error"><strong>Não foi possível consultar o Hugging Face</strong><span>${escapeHtml(error.message)}</span></div>`;
    }
  }

  async function installDiscoveredModel(repositoryId) {
    const model = discoveredModels.find((item) => item.id === repositoryId);
    if (!model) return;
    const token = $("#model-library-token").value.trim();
    if (model.gated && !token) {
      $(".model-library-access").open = true;
      $("#model-library-token").focus();
      showLibraryFeedback("Este modelo exige aceite no Hugging Face e um token de acesso.", "warning");
      return;
    }
    if (model.gguf) {
      await openGgufModal(model);
      return;
    }
    await performModelInstall(model, {});
  }

  async function openGgufModal(model) {
    selectedGgufModel = model;
    ggufCatalog = null;
    const modal = $("#gguf-variant-modal");
    const errorBox = $("#gguf-variant-error");
    $("#gguf-repository-label").textContent = model.id;
    $("#gguf-loading").classList.remove("hidden");
    $("#gguf-variant-field").classList.add("hidden");
    $("#gguf-mmproj-field").classList.add("hidden");
    errorBox.classList.add("hidden");
    $("#gguf-install-button").disabled = true;
    modal.classList.remove("hidden");
    try {
      ggufCatalog = await api("/api/huggingface/gguf-variants", {
        method: "POST",
        body: JSON.stringify({
          repository_id: model.id,
          revision: "main",
          token: $("#model-library-token").value.trim(),
        }),
      });
      if (!ggufCatalog.variants.length) throw new Error("Este repositório não contém arquivos GGUF instaláveis.");
      const select = $("#gguf-variant-select");
      select.innerHTML = ggufCatalog.variants.map((variant, index) => `
        <option value="${index}" ${variant.recommended ? "selected" : ""}>
          ${escapeHtml(variant.quantization)} · ${escapeHtml(formatBytes(variant.size_bytes))}${variant.recommended ? " · recomendado" : ""}
        </option>`).join("");
      const mmproj = $("#gguf-mmproj-select");
      mmproj.innerHTML = '<option value="">Sem entrada de imagem</option>' + ggufCatalog.mmproj_files.map((file) =>
        `<option value="${escapeHtml(file.name)}">${escapeHtml(file.name)} · ${escapeHtml(formatBytes(file.size_bytes))}</option>`
      ).join("");
      $("#gguf-mmproj-field").classList.toggle("hidden", !ggufCatalog.mmproj_files.length);
      $("#gguf-variant-field").classList.remove("hidden");
      updateGgufVariantHelp();
      $("#gguf-install-button").disabled = false;
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("hidden");
    } finally {
      $("#gguf-loading").classList.add("hidden");
    }
  }

  function updateGgufVariantHelp() {
    if (!ggufCatalog) return;
    const variant = ggufCatalog.variants[Number($("#gguf-variant-select").value || 0)];
    $("#gguf-variant-help").textContent = variant
      ? `${variant.description} Download: ${formatBytes(variant.size_bytes)}.`
      : "";
  }

  async function performModelInstall(model, options) {
    clearLibraryFeedback();
    const token = $("#model-library-token").value.trim();
    const optimistic = { id: `pending-${Date.now()}`, repository_id: model.id, revision: "main", task: model.task, status: "installing", error: "", options };
    localModels = [...localModels.filter((item) => !(item.repository_id === model.id && item.task === model.task)), optimistic];
    renderDiscovery();
    renderLocalModels();
    try {
      const installed = await api("/api/local-models", {
        method: "POST",
        body: JSON.stringify({ repository_id: model.id, revision: "main", task: model.task, token, download: true, options }),
      });
      localModels = [...localModels.filter((item) => item.id !== optimistic.id), installed];
      showLibraryFeedback(`${model.id} entrou na fila de instalação. Você pode continuar navegando.`, "success");
      renderDiscovery();
      renderLocalModels();
      scheduleInstallPolling();
    } catch (error) {
      localModels = localModels.filter((item) => item.id !== optimistic.id);
      showLibraryFeedback(error.message, "error");
      renderDiscovery();
      renderLocalModels();
    }
  }

  function scheduleInstallPolling() {
    clearTimeout(installPollTimer);
    if (!localModels.some((model) => model.status === "installing")) return;
    installPollTimer = setTimeout(async () => {
      try {
        localModels = await api("/api/local-models");
        renderLocalModels();
        renderDiscovery();
      } finally {
        scheduleInstallPolling();
      }
    }, 2000);
  }

  function renderLocalModels() {
    const grid = $("#local-model-grid");
    if (!grid) return;
    grid.innerHTML = localModels.length
      ? localModels.map((model) => `
          <article class="installed-model-card ${escapeHtml(model.status)}" data-local-model-id="${escapeHtml(model.id)}">
            <div class="installed-model-icon">HF</div>
            <div class="installed-model-body">
              <div class="installed-model-title"><strong>${escapeHtml(model.repository_id)}</strong><span class="installed-status ${escapeHtml(model.status)}">${model.status === "ready" ? "Pronto" : model.status === "installing" ? "Instalando" : "Erro"}</span></div>
              <p>${escapeHtml(taskName(model.task))} · ${escapeHtml(model.revision)}</p>
              ${model.options?.runtime === "llama_cpp" ? `<p><strong>GGUF ${escapeHtml(model.options.quantization || "")}</strong> · llama.cpp</p>` : ""}
              <div class="model-capability-badges">${capabilityBadges(model)}</div>
              ${model.error ? `<small>${escapeHtml(model.error)}</small>` : ""}
              ${model.status === "error" ? `<button type="button" class="installed-model-retry" data-retry-local-model="${escapeHtml(model.id)}">Resolver e reinstalar</button>` : ""}
              ${model.status === "installing" ? '<div class="model-install-progress"><span></span></div>' : ""}
            </div>
            <button class="installed-model-remove" title="Remover modelo" aria-label="Remover ${escapeHtml(model.repository_id)}" data-delete-local-model="${escapeHtml(model.id)}">×</button>
          </article>`).join("")
      : '<div class="model-empty-state compact"><strong>Nenhum modelo instalado</strong><span>Escolha um modelo acima e clique em Instalar.</span></div>';
    document.querySelectorAll("[data-delete-local-model]").forEach((button) =>
      button.addEventListener("click", async () => {
        if (!window.confirm("Remover o modelo e seus arquivos locais?")) return;
        await api(`/api/local-models/${button.dataset.deleteLocalModel}`, { method: "DELETE" });
        localModels = await api("/api/local-models");
        renderLocalModels();
        renderDiscovery();
      })
    );
    document.querySelectorAll("[data-retry-local-model]").forEach((button) =>
      button.addEventListener("click", () => retryLocalModel(button.dataset.retryLocalModel))
    );
  }

  async function retryLocalModel(modelId) {
    const model = localModels.find((item) => item.id === modelId);
    if (!model) return;
    const token = $("#model-library-token").value.trim();
    try {
      const installing = await api("/api/local-models", {
        method: "POST",
        body: JSON.stringify({
          repository_id: model.repository_id,
          revision: model.revision,
          task: model.task,
          token,
          download: true,
          options: model.options || {},
        }),
      });
      localModels = localModels.map((item) => item.id === modelId ? installing : item);
      showLibraryFeedback("O AgenticFlow está resolvendo um formato compatível e reinstalando o modelo.", "success");
      renderLocalModels();
      renderDiscovery();
      scheduleInstallPolling();
    } catch (error) {
      showLibraryFeedback(error.message, "error");
    }
  }

  function openLocalModelModal() {
    $("#local-model-form").reset();
    $("#local-revision").value = "main";
    $("#local-task").innerHTML = localTasks.map((item) =>
      `<option value="${escapeHtml(item.task)}">${escapeHtml(item.name)}</option>`
    ).join("");
    $("#local-model-error").classList.add("hidden");
    $("#local-model-modal").classList.remove("hidden");
  }

  $("#model-library-search")?.addEventListener("input", () => {
    clearTimeout(discoveryTimer);
    currentPage = 1;
    discoveryTimer = setTimeout(() => loadDiscovery(), 400);
  });

  $("#model-sort")?.addEventListener("change", (event) => {
    selectedSort = event.target.value;
    currentPage = 1;
    loadDiscovery();
  });

  function openModal(providerId = null) {
    form.reset();
    $("#provider-id").value = providerId || "";
    $("#provider-error").classList.add("hidden");
    $("#delete-provider").classList.toggle("hidden", !providerId);
    $("#test-provider").classList.toggle("hidden", !providerId);
    $("#provider-modal-title").textContent = providerId ? "Editar provedor" : "Adicionar provedor";
    if (providerId) {
      const provider = providers.find((item) => item.id === providerId);
      $("#provider-type").value = provider.type;
      $("#provider-name").value = provider.name;
      $("#provider-base-url").value = provider.base_url;
      $("#provider-model").value = provider.default_model;
      $("#provider-enabled").checked = provider.enabled;
      $("#provider-api-key").placeholder = provider.has_api_key
        ? "Chave já armazenada ••••••••"
        : "Cole a chave aqui";
      applyTypeDefaults(false);
    } else {
      $("#provider-enabled").checked = true;
      applyTypeDefaults(true);
    }
    modal.classList.remove("hidden");
  }

  function closeModal() {
    modal.classList.add("hidden");
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const providerId = $("#provider-id").value;
    const button = form.querySelector("button[type=submit]");
    const errorBox = $("#provider-error");
    button.disabled = true;
    errorBox.classList.add("hidden");
    const payload = {
      type: $("#provider-type").value,
      name: $("#provider-name").value,
      base_url: $("#provider-base-url").value,
      default_model: $("#provider-model").value,
      api_key: $("#provider-api-key").value,
      enabled: $("#provider-enabled").checked,
    };
    try {
      await api(providerId ? `/api/providers/${providerId}` : "/api/providers", {
        method: providerId ? "PUT" : "POST",
        body: JSON.stringify(payload),
      });
      providers = await api("/api/providers");
      renderCards();
      closeModal();
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("hidden");
    } finally {
      button.disabled = false;
    }
  });

  $("#test-provider").addEventListener("click", async () => {
    const button = $("#test-provider");
    const errorBox = $("#provider-error");
    button.disabled = true;
    button.textContent = "Testando...";
    errorBox.classList.add("hidden");
    try {
      const result = await api(`/api/providers/${$("#provider-id").value}/test`, {
        method: "POST",
      });
      errorBox.textContent = `Conexão funcionando: ${result.preview}`;
      errorBox.className = "auth-error provider-success";
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.className = "auth-error";
    } finally {
      button.disabled = false;
      button.textContent = "Testar conexão";
    }
  });

  $("#delete-provider").addEventListener("click", async () => {
    if (!window.confirm("Excluir este provedor? Nós que o utilizam precisarão ser reconfigurados.")) return;
    await api(`/api/providers/${$("#provider-id").value}`, { method: "DELETE" });
    providers = await api("/api/providers");
    renderCards();
    closeModal();
  });

  $("#provider-type").addEventListener("change", () => applyTypeDefaults(true));
  $("#provider-modal-close").addEventListener("click", closeModal);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });
  $("#new-provider-button").addEventListener("click", () => openModal());

  $("#new-local-model-button")?.addEventListener("click", openLocalModelModal);
  $("#local-model-modal-close")?.addEventListener("click", () => $("#local-model-modal").classList.add("hidden"));
  $("#gguf-variant-close")?.addEventListener("click", () => $("#gguf-variant-modal").classList.add("hidden"));
  $("#gguf-variant-select")?.addEventListener("change", updateGgufVariantHelp);
  $("#gguf-variant-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!selectedGgufModel || !ggufCatalog) return;
    const variant = ggufCatalog.variants[Number($("#gguf-variant-select").value || 0)];
    const mmprojFile = $("#gguf-mmproj-select").value;
    $("#gguf-variant-modal").classList.add("hidden");
    await performModelInstall(selectedGgufModel, {
      runtime: "llama_cpp",
      quantization: variant.quantization,
      gguf_file: variant.main_file,
      gguf_files: variant.files,
      mmproj_file: mmprojFile,
      capabilities: {
        input_modalities: mmprojFile ? ["text", "image"] : ["text"],
        output_modalities: ["text"],
      },
    });
  });
  $("#local-model-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.currentTarget.querySelector("button[type=submit]");
    const errorBox = $("#local-model-error");
    button.disabled = true;
    errorBox.classList.add("hidden");
    try {
      await api("/api/local-models", {
        method: "POST",
        body: JSON.stringify({
          repository_id: $("#local-repository").value,
          task: $("#local-task").value,
          revision: $("#local-revision").value,
          token: $("#local-token").value || $("#model-library-token").value,
          download: true,
          options: {},
        }),
      });
      localModels = await api("/api/local-models");
      renderLocalModels();
      $("#local-model-modal").classList.add("hidden");
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("hidden");
    } finally {
      button.disabled = false;
    }
  });

  Promise.all([
    api("/api/provider-types"),
    api("/api/providers"),
    api("/api/local-models"),
    api("/api/local-model-tasks"),
    api("/api/local-models/hardware"),
  ])
    .then(([knownTypes, savedProviders, savedModels, knownTasks, detectedHardware]) => {
      types = knownTypes;
      providers = savedProviders;
      localModels = savedModels;
      localTasks = knownTasks;
      hardware = detectedHardware;
      renderCards();
      renderTaskTabs();
      renderLocalModels();
      const device = hardware.devices?.[0];
      $("#local-hardware").innerHTML = hardware.available
        ? `<span class="model-hardware-icon">◇</span><div><strong>${device ? escapeHtml(device.name) : "Execução em CPU"}</strong><p>${hardware.backend === "rocm" ? `AMD ROCm ${escapeHtml(hardware.rocm_version || "")}` : hardware.backend.toUpperCase()}${device?.total_memory_bytes ? ` · ${formatBytes(device.total_memory_bytes)} de VRAM` : ""}</p></div><span class="model-hardware-ready">Pronto para instalar</span>`
        : `<span class="model-hardware-icon warning">!</span><div><strong>Runtime local indisponível</strong><p>${escapeHtml(hardware.error)}</p></div>`;
      loadDiscovery();
      scheduleInstallPolling();
    })
    .catch((error) => {
      $("#provider-grid").innerHTML = `<div class="auth-error">${escapeHtml(error.message)}</div>`;
    });
})();
