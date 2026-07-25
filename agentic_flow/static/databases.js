(() => {
  const $ = (selector) => document.querySelector(selector);
  let connections = [];
  let types = [];
  const modal = $("#database-modal");
  const form = $("#database-form");

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

  function escapeHtml(value) {
    const element = document.createElement("div");
    element.textContent = value == null ? "" : String(value);
    return element.innerHTML;
  }

  const typeFor = (value) => types.find((item) => item.type === value);

  function endpoint(connection) {
    if (connection.type === "sqlite" || connection.type === "bigquery") {
      return connection.database_name;
    }
    return `${connection.host}${connection.port ? `:${connection.port}` : ""}/${connection.database_name}`;
  }

  function renderCards() {
    const cards = connections
      .map((connection) => {
        const definition = typeFor(connection.type) || {};
        return `
          <article class="provider-card database-card" data-database-id="${connection.id}">
            <div class="provider-card-head">
              <span class="provider-logo database-logo" style="--database-color:${escapeHtml(definition.color || "#7657ff")}">${escapeHtml(definition.icon || connection.type.slice(0, 2).toUpperCase())}</span>
              <span class="provider-status ${connection.enabled ? "active" : ""}">${connection.enabled ? "Ativo" : "Inativo"}</span>
            </div>
            <h2>${escapeHtml(connection.name)}</h2>
            <p>${escapeHtml(definition.name || connection.type)}</p>
            <code>${escapeHtml(endpoint(connection))}</code>
            <div class="provider-card-actions">
              <span>${connection.has_secret ? "● Credencial protegida" : "○ Sem credencial"}</span>
              <button class="provider-edit" data-edit-database="${connection.id}">Editar</button>
            </div>
          </article>`;
      })
      .join("");
    $("#database-grid").innerHTML =
      cards +
      `<button class="provider-card provider-new-card" id="new-database-card">
        <span class="new-card-plus">+</span>
        <strong>Conectar banco</strong>
        <small>MySQL, PostgreSQL, SQL Server, SQLite, BigQuery e MariaDB</small>
      </button>`;
    document.querySelectorAll("[data-edit-database]").forEach((button) =>
      button.addEventListener("click", () => openModal(button.dataset.editDatabase))
    );
    $("#new-database-card").addEventListener("click", () => openModal());
  }

  function applyTypeDefaults(force = false) {
    const definition = typeFor($("#database-type").value);
    if (!definition) return;
    const local = definition.type === "sqlite";
    const bigQuery = definition.type === "bigquery";
    $("#database-type-help").textContent = definition.description;
    $("#database-host-field").classList.toggle("hidden", local || bigQuery);
    $("#database-port-field").classList.toggle("hidden", local || bigQuery);
    $("#database-username-field").classList.toggle("hidden", local || bigQuery);
    $("#database-dataset-field").classList.toggle("hidden", !bigQuery);
    $("#database-database-field label").textContent = local
      ? "Caminho do arquivo"
      : bigQuery
        ? "Projeto Google Cloud"
        : "Database";
    $("#database-database-help").textContent = local
      ? "Caminho acessível pelo servidor Agentic Flow."
      : bigQuery
        ? "O ID do projeto que contém os dados."
        : "";
    $("#database-secret-label").textContent = bigQuery
      ? "Service account JSON"
      : "Senha";
    $("#database-secret").placeholder = bigQuery
      ? '{ "type": "service_account", ... }'
      : "Senha da conexão";
    if (force) {
      $("#database-name").value = definition.name;
      $("#database-host").value = local || bigQuery ? "" : "localhost";
      $("#database-port").value = definition.default_port || "";
    }
  }

  function openModal(connectionId = null) {
    form.reset();
    $("#database-id").value = connectionId || "";
    $("#database-error").className = "auth-error hidden";
    $("#delete-database").classList.toggle("hidden", !connectionId);
    $("#test-database").classList.toggle("hidden", !connectionId);
    $("#database-modal-title").textContent = connectionId
      ? "Editar conexão"
      : "Adicionar banco";
    if (connectionId) {
      const connection = connections.find((item) => item.id === connectionId);
      $("#database-type").value = connection.type;
      $("#database-name").value = connection.name;
      $("#database-host").value = connection.host || "";
      $("#database-port").value = connection.port || "";
      $("#database-database").value = connection.database_name;
      $("#database-username").value = connection.username || "";
      $("#database-dataset").value = connection.options?.dataset || "";
      $("#database-enabled").checked = connection.enabled;
      $("#database-secret").placeholder = connection.has_secret
        ? "Credencial já armazenada ••••••••"
        : "Informe a credencial";
      applyTypeDefaults(false);
    } else {
      $("#database-enabled").checked = true;
      applyTypeDefaults(true);
    }
    modal.classList.remove("hidden");
  }

  function closeModal() {
    modal.classList.add("hidden");
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const connectionId = $("#database-id").value;
    const button = form.querySelector("button[type=submit]");
    const errorBox = $("#database-error");
    button.disabled = true;
    errorBox.classList.add("hidden");
    const payload = {
      type: $("#database-type").value,
      name: $("#database-name").value,
      host: $("#database-host").value,
      port: $("#database-port").value ? Number($("#database-port").value) : null,
      database_name: $("#database-database").value,
      username: $("#database-username").value,
      secret: $("#database-secret").value,
      options: {
        dataset: $("#database-dataset").value,
        trust_server_certificate: true,
      },
      enabled: $("#database-enabled").checked,
    };
    try {
      await api(
        connectionId
          ? `/api/database-connections/${connectionId}`
          : "/api/database-connections",
        {
          method: connectionId ? "PUT" : "POST",
          body: JSON.stringify(payload),
        }
      );
      connections = await api("/api/database-connections");
      renderCards();
      closeModal();
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("hidden");
    } finally {
      button.disabled = false;
    }
  });

  $("#test-database").addEventListener("click", async () => {
    const button = $("#test-database");
    const errorBox = $("#database-error");
    button.disabled = true;
    button.textContent = "Testando...";
    errorBox.classList.add("hidden");
    try {
      const result = await api(
        `/api/database-connections/${$("#database-id").value}/test`,
        { method: "POST" }
      );
      errorBox.textContent = result.message;
      errorBox.className = "auth-error provider-success";
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.className = "auth-error";
    } finally {
      button.disabled = false;
      button.textContent = "Testar conexão";
    }
  });

  $("#delete-database").addEventListener("click", async () => {
    if (!window.confirm("Excluir esta conexão? Nós que a utilizam precisarão ser reconfigurados.")) return;
    await api(`/api/database-connections/${$("#database-id").value}`, {
      method: "DELETE",
    });
    connections = await api("/api/database-connections");
    renderCards();
    closeModal();
  });

  $("#database-type").addEventListener("change", () => applyTypeDefaults(true));
  $("#database-modal-close").addEventListener("click", closeModal);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });
  $("#new-database-button").addEventListener("click", () => openModal());

  Promise.all([
    api("/api/database-types"),
    api("/api/database-connections"),
  ])
    .then(([knownTypes, savedConnections]) => {
      types = knownTypes;
      connections = savedConnections;
      renderCards();
    })
    .catch((error) => {
      $("#database-grid").innerHTML = `<div class="auth-error">${escapeHtml(error.message)}</div>`;
    });
})();
