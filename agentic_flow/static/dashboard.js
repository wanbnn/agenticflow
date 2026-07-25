(() => {
  const escapeHtml = (value) => {
    const element = document.createElement("div");
    element.textContent = value == null ? "" : String(value);
    return element.innerHTML;
  };
  const modal = document.querySelector("#workflow-modal");
  const form = document.querySelector("#workflow-form");
  const openModal = () => {
    modal.classList.remove("hidden");
    setTimeout(() => document.querySelector("#new-workflow-name").focus(), 50);
  };
  const closeModal = () => modal.classList.add("hidden");

  document.querySelector("#new-workflow-button")?.addEventListener("click", openModal);
  document.querySelector("#new-workflow-card")?.addEventListener("click", openModal);
  document.querySelector("#modal-close")?.addEventListener("click", closeModal);
  modal?.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = document.querySelector("#workflow-error");
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    errorBox.classList.add("hidden");
    try {
      const response = await fetch("/api/workflows", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: document.querySelector("#new-workflow-name").value,
          description: document.querySelector("#new-workflow-description").value,
          nodes: [],
          edges: [],
        }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Não foi possível criar o workflow.");
      window.location.assign(`/workflows/${data.id}`);
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("hidden");
    } finally {
      button.disabled = false;
    }
  });

  const templateModal = document.querySelector("#template-modal");
  const templateGrid = document.querySelector("#template-grid");
  let templates = [];
  let templateCategory = "Todos";

  function renderTemplates() {
    if (!templateGrid) return;
    const query = (document.querySelector("#template-search")?.value || "")
      .trim()
      .toLowerCase();
    const visible = templates.filter(
      (template) =>
        (templateCategory === "Todos" || template.category === templateCategory) &&
        `${template.name} ${template.description} ${template.tags.join(" ")}`
          .toLowerCase()
          .includes(query)
    );
    templateGrid.innerHTML = visible.length
      ? visible
          .map(
            (template) => `
              <article class="template-card ${template.compatible ? "" : "locked"}"
                style="--template-color:${template.color}">
                <div class="template-card-head">
                  <span class="template-icon">${escapeHtml(template.icon)}</span>
                  <span class="template-category">${escapeHtml(template.category)}</span>
                </div>
                <h3>${escapeHtml(template.name)}</h3>
                <p>${escapeHtml(template.description)}</p>
                <div class="template-tags">
                  ${template.tags.map((tag) => `<span>${escapeHtml(tag)}</span>`).join("")}
                </div>
                <div class="template-card-footer">
                  <span>${template.nodes_count} nós</span>
                  <button class="button ${template.compatible ? "primary" : "secondary"} compact"
                    type="button" data-use-template="${template.id}"
                    ${template.compatible ? "" : "disabled"}>
                    ${template.compatible ? "Usar template" : "Sem permissão"}
                  </button>
                </div>
                ${
                  template.blocked_node_types.length
                    ? `<small class="template-blocked">Nós bloqueados: ${template.blocked_node_types.join(", ")}</small>`
                    : ""
                }
              </article>`
          )
          .join("")
      : '<div class="template-empty">Nenhum template encontrado.</div>';
  }

  async function openTemplateLibrary() {
    templateModal.classList.remove("hidden");
    if (templates.length) return;
    try {
      const response = await fetch("/api/templates");
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || "Não foi possível carregar os templates.");
      templates = payload;
      const categories = ["Todos", ...new Set(templates.map((item) => item.category))];
      document.querySelector("#template-filters").innerHTML = categories
        .map(
          (category) =>
            `<button type="button" class="template-filter ${category === "Todos" ? "active" : ""}"
              data-template-category="${escapeHtml(category)}">${escapeHtml(category)}</button>`
        )
        .join("");
      renderTemplates();
    } catch (error) {
      templateGrid.innerHTML = `<div class="template-empty">${escapeHtml(error.message)}</div>`;
    }
  }

  document
    .querySelector("#template-library-button")
    ?.addEventListener("click", openTemplateLibrary);
  document.querySelector("#template-modal-close")?.addEventListener("click", () => {
    templateModal.classList.add("hidden");
  });
  templateModal?.addEventListener("click", (event) => {
    if (event.target === templateModal) templateModal.classList.add("hidden");
  });
  document.querySelector("#template-search")?.addEventListener("input", renderTemplates);
  document.querySelector("#template-filters")?.addEventListener("click", (event) => {
    const filter = event.target.closest("[data-template-category]");
    if (!filter) return;
    templateCategory = filter.dataset.templateCategory;
    document.querySelectorAll("[data-template-category]").forEach((item) =>
      item.classList.toggle("active", item === filter)
    );
    renderTemplates();
  });
  templateGrid?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-use-template]");
    if (!button || button.disabled) return;
    button.disabled = true;
    button.textContent = "Criando...";
    try {
      const response = await fetch(
        `/api/templates/${button.dataset.useTemplate}/instantiate`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        }
      );
      const workflow = await response.json();
      if (!response.ok) throw new Error(workflow.detail || "Não foi possível usar o template.");
      window.location.assign(`/workflows/${workflow.id}`);
    } catch (error) {
      button.disabled = false;
      button.textContent = "Usar template";
      window.alert(error.message);
    }
  });

  document.querySelector("#logout-button")?.addEventListener("click", async () => {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.assign("/login");
  });
})();
