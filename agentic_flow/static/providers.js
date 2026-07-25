(() => {
  document.querySelector("#workspace-select")?.addEventListener("change", async (event) => {
    const response = await fetch(`/api/auth/workspace/${event.target.value}`, {
      method: "POST",
    });
    if (response.ok) window.location.reload();
  });

  const $ = (selector) => document.querySelector(selector);
  let providers = [];
  let types = [];
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
  }

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

  Promise.all([api("/api/provider-types"), api("/api/providers")])
    .then(([knownTypes, savedProviders]) => {
      types = knownTypes;
      providers = savedProviders;
      renderCards();
    })
    .catch((error) => {
      $("#provider-grid").innerHTML = `<div class="auth-error">${escapeHtml(error.message)}</div>`;
    });
})();
