(() => {
  const $ = (selector) => document.querySelector(selector);
  let providers = [];
  let types = [];
  let localModels = [];
  let localTasks = [];
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

  function renderLocalModels() {
    const grid = $("#local-model-grid");
    if (!grid) return;
    grid.innerHTML = localModels.length
      ? localModels.map((model) => `
          <article class="provider-card" data-local-model-id="${escapeHtml(model.id)}">
            <div class="provider-card-head">
              <span class="provider-logo">HF</span>
              <span class="provider-status ${model.status === "ready" ? "active" : ""}">${escapeHtml(model.status)}</span>
            </div>
            <h2>${escapeHtml(model.repository_id)}</h2>
            <p>${escapeHtml(model.task)} · revisão ${escapeHtml(model.revision)}</p>
            <code>${escapeHtml(model.id)}</code>
            ${model.error ? `<small class="auth-error">${escapeHtml(model.error)}</small>` : ""}
            <div class="provider-card-actions">
              <span>${model.local_path ? "● Baixado no servidor" : "○ Cache gerenciado em execução"}</span>
              <button class="provider-edit" data-delete-local-model="${escapeHtml(model.id)}">Excluir</button>
            </div>
          </article>`).join("")
      : '<div class="workflow-empty-state">Nenhum modelo local instalado.</div>';
    document.querySelectorAll("[data-delete-local-model]").forEach((button) =>
      button.addEventListener("click", async () => {
        if (!window.confirm("Remover o modelo e seus arquivos locais?")) return;
        await api(`/api/local-models/${button.dataset.deleteLocalModel}`, { method: "DELETE" });
        localModels = await api("/api/local-models");
        renderLocalModels();
      })
    );
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

  let huggingFaceSearchTimer;
  $("#local-repository")?.addEventListener("input", (event) => {
    clearTimeout(huggingFaceSearchTimer);
    const query = event.target.value.trim();
    if (query.length < 2) return;
    huggingFaceSearchTimer = setTimeout(async () => {
      try {
        const task = $("#local-task").value;
        const models = await api(`/api/huggingface/models?q=${encodeURIComponent(query)}&task=${encodeURIComponent(task)}&limit=12`);
        $("#huggingface-model-options").innerHTML = models.map((model) =>
          `<option value="${escapeHtml(model.id)}">${escapeHtml(model.task || "modelo")} · ${Number(model.downloads || 0).toLocaleString()} downloads</option>`
        ).join("");
      } catch (_) {
        // O usuário ainda pode informar qualquer repository ID manualmente.
      }
    }, 350);
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
          token: $("#local-token").value,
          download: true,
          options: { trust_remote_code: $("#local-trust-code").checked },
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
    .then(([knownTypes, savedProviders, savedModels, knownTasks, hardware]) => {
      types = knownTypes;
      providers = savedProviders;
      localModels = savedModels;
      localTasks = knownTasks;
      renderCards();
      renderLocalModels();
      const deviceNames = (hardware.devices || []).map((item) => item.name).join(", ");
      $("#local-hardware").textContent = hardware.available
        ? `Backend: ${hardware.backend}${hardware.rocm_version ? ` · ROCm ${hardware.rocm_version}` : ""}${deviceNames ? ` · ${deviceNames}` : " · CPU"}`
        : hardware.error;
    })
    .catch((error) => {
      $("#provider-grid").innerHTML = `<div class="auth-error">${escapeHtml(error.message)}</div>`;
    });
})();
