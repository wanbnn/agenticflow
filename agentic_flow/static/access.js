(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const modal = $("#access-modal");
  const form = $("#access-form");
  const body = $("#access-modal-body");
  const errorBox = $("#access-error");
  const isAdmin = $(".access-shell").dataset.currentRole === "admin";
  let overview = null;
  let action = null;

  const escapeHtml = (value) => {
    const element = document.createElement("div");
    element.textContent = value == null ? "" : String(value);
    return element.innerHTML;
  };

  async function api(path, options = {}) {
    const response = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (response.status === 204) return null;
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `Erro HTTP ${response.status}`);
    return payload;
  }

  function toast(message, tone = "success") {
    const item = document.createElement("div");
    item.className = `toast ${tone}`;
    item.textContent = message;
    $("#toast-region").append(item);
    setTimeout(() => item.remove(), 3000);
  }

  function roleLabel(role) {
    return { admin: "Admin", manager: "Manager", user: "User", member: "User" }[role] || role;
  }

  function render() {
    const workspaceUsers = overview.workspace_users || [];
    const teams = overview.teams || [];
    $("#access-stats").innerHTML = `
      <article><strong>${workspaceUsers.length}</strong><span>Usuários</span></article>
      <article><strong>${teams.length}</strong><span>Times</span></article>
      <article><strong>${overview.workspaces.length}</strong><span>Workspaces</span></article>`;

    $("#access-users").innerHTML = workspaceUsers.length
      ? workspaceUsers
          .map(
            (user) => `
              <article class="access-user-row">
                <span class="user-avatar">${escapeHtml(user.name[0].toUpperCase())}</span>
                <span class="access-user-copy">
                  <strong>${escapeHtml(user.name)}</strong>
                  <small>${escapeHtml(user.email)}</small>
                </span>
                <span class="role-badge ${user.role}">${roleLabel(user.role)}</span>
                <span class="status-badge ${user.active ? "active" : ""}">${user.active ? "Ativo" : "Inativo"}</span>
                ${
                  isAdmin
                    ? `<button class="provider-edit" type="button" data-edit-user="${user.id}">Editar</button>`
                    : ""
                }
              </article>`
          )
          .join("")
      : '<div class="access-empty">Nenhum usuário liberado neste workspace.</div>';

    if (isAdmin) {
      $("#workspace-admin-grid").innerHTML = overview.workspaces
        .map((workspace) => {
          const count = overview.users.filter((user) =>
            user.workspace_ids.includes(workspace.id)
          ).length;
          return `
            <article class="access-card">
              <span class="workspace-avatar">${escapeHtml(workspace.name[0].toUpperCase())}</span>
              <div><h3>${escapeHtml(workspace.name)}</h3><p>${count} vínculo(s) explícito(s)</p></div>
              <button class="button secondary compact" type="button" data-members-workspace="${workspace.id}">Gerenciar acessos</button>
            </article>`;
        })
        .join("");
    }

    $("#team-grid").innerHTML = teams.length
      ? teams
          .map((team) => {
            const policy = team.policy || {};
            const permissions = [
              policy.create_workflows && "Criar workflows",
              policy.edit_workflows && "Editar workflows",
              policy.run_workflows && "Executar",
              policy.manage_providers && "Provedores",
            ].filter(Boolean);
            return `
              <article class="team-card">
                <div class="team-card-head">
                  <span class="team-icon">♙</span>
                  <span class="version-pill">${team.member_ids.length} membros</span>
                </div>
                <h3>${escapeHtml(team.name)}</h3>
                <p>${escapeHtml(team.description || "Sem descrição.")}</p>
                <div class="policy-tags">
                  ${(permissions.length ? permissions : ["Somente visualização"])
                    .map((item) => `<span>${escapeHtml(item)}</span>`)
                    .join("")}
                  ${
                    policy.allowed_node_types?.length
                      ? `<span>${policy.allowed_node_types.length} tipos de nó</span>`
                      : "<span>Todos os nós</span>"
                  }
                </div>
                <div class="team-actions">
                  <button class="provider-edit" type="button" data-edit-team="${team.id}">Editar política</button>
                  <button class="provider-edit danger-text" type="button" data-delete-team="${team.id}">Excluir</button>
                </div>
              </article>`;
          })
          .join("")
      : '<div class="access-empty">Nenhum time criado neste workspace.</div>';
  }

  async function load() {
    overview = await api("/api/access/overview");
    render();
  }

  function openModal(kind, item = null) {
    action = { kind, item };
    errorBox.classList.add("hidden");
    const title = $("#access-modal-title");
    if (kind === "user") {
      title.textContent = "Criar usuário";
      body.innerHTML = `
        <div class="field"><label>Nome</label><input name="name" required></div>
        <div class="field"><label>E-mail</label><input name="email" type="email" required></div>
        <div class="field"><label>Senha inicial</label><input name="password" type="password" minlength="8" required></div>
        <div class="field"><label>Papel global</label><select name="role">
          <option value="user">User</option><option value="manager">Manager</option><option value="admin">Admin</option>
        </select></div>`;
    } else if (kind === "edit-user") {
      title.textContent = "Editar usuário";
      body.innerHTML = `
        <div class="field"><label>Nome</label><input name="name" value="${escapeHtml(item.name)}" required></div>
        <div class="field"><label>Papel global</label><select name="role">
          ${["user", "manager", "admin"].map((role) => `<option value="${role}" ${item.role === role ? "selected" : ""}>${roleLabel(role)}</option>`).join("")}
        </select></div>
        <label class="toggle-field"><input name="active" type="checkbox" ${item.active ? "checked" : ""}><span></span>Usuário ativo</label>`;
    } else if (kind === "workspace") {
      title.textContent = "Criar workspace";
      body.innerHTML = '<div class="field"><label>Nome</label><input name="name" required placeholder="Ex.: Operação Brasil"></div>';
    } else if (kind === "members") {
      title.textContent = `Acessos · ${item.name}`;
      body.innerHTML = `<div class="member-check-list">
        ${overview.users
          .filter((user) => user.role !== "admin")
          .map(
            (user) => `<label class="member-check">
              <input type="checkbox" name="user_ids" value="${user.id}" ${user.workspace_ids.includes(item.id) ? "checked" : ""}>
              <span><strong>${escapeHtml(user.name)}</strong><small>${roleLabel(user.role)} · ${escapeHtml(user.email)}</small></span>
            </label>`
          )
          .join("")}
      </div><small class="field-help">Administradores acessam todos os workspaces automaticamente.</small>`;
    } else if (kind === "team") {
      const policy = item?.policy || {};
      const members = item?.member_ids || [];
      title.textContent = item ? "Editar time e políticas" : "Criar time";
      body.innerHTML = `
        <div class="field"><label>Nome</label><input name="name" value="${escapeHtml(item?.name || "")}" required></div>
        <div class="field"><label>Descrição</label><textarea name="description">${escapeHtml(item?.description || "")}</textarea></div>
        <div class="policy-editor">
          <strong>Permissões do time</strong>
          ${[
            ["create_workflows", "Criar workflows"],
            ["edit_workflows", "Editar workflows"],
            ["run_workflows", "Executar workflows"],
            ["manage_providers", "Gerenciar provedores"],
          ].map(([key, label]) => `<label class="toggle-field"><input type="checkbox" name="${key}" ${policy[key] ? "checked" : ""}><span></span>${label}</label>`).join("")}
        </div>
        <div class="field"><label>Tipos de nó permitidos <small>opcional</small></label>
          <label class="toggle-field"><input type="checkbox" name="restrict_nodes" ${policy.allowed_node_types != null ? "checked" : ""}><span></span>Restringir catálogo para este time</label>
          <div class="node-policy-grid">
            ${overview.node_types.map((node) => `<label><input type="checkbox" name="allowed_node_types" value="${node.type}" ${(policy.allowed_node_types || []).includes(node.type) ? "checked" : ""}><span>${escapeHtml(node.name)}</span><code>${node.type}</code></label>`).join("")}
          </div>
          <small class="field-help">Sem restrição, todos os tipos de nó ficam disponíveis.</small>
        </div>
        <div class="field"><label>Membros</label><div class="member-check-list compact-list">
          ${overview.workspace_users
            .filter((user) => user.role !== "admin")
            .map((user) => `<label class="member-check"><input type="checkbox" name="team_user_ids" value="${user.id}" ${members.includes(user.id) ? "checked" : ""}><span><strong>${escapeHtml(user.name)}</strong><small>${roleLabel(user.role)}</small></span></label>`)
            .join("")}
        </div></div>`;
    }
    modal.classList.remove("hidden");
    setTimeout(() => body.querySelector("input")?.focus(), 40);
  }

  function closeModal() {
    modal.classList.add("hidden");
    action = null;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("[type=submit]");
    submit.disabled = true;
    errorBox.classList.add("hidden");
    const data = new FormData(form);
    try {
      if (action.kind === "user") {
        await api("/api/admin/users", {
          method: "POST",
          body: JSON.stringify(Object.fromEntries(data.entries())),
        });
      } else if (action.kind === "edit-user") {
        await api(`/api/admin/users/${action.item.id}`, {
          method: "PUT",
          body: JSON.stringify({
            name: data.get("name"),
            role: data.get("role"),
            active: data.has("active"),
          }),
        });
      } else if (action.kind === "workspace") {
        await api("/api/admin/workspaces", {
          method: "POST",
          body: JSON.stringify({ name: data.get("name") }),
        });
      } else if (action.kind === "members") {
        const selected = new Set(data.getAll("user_ids"));
        await Promise.all(
          overview.users
            .filter((user) => user.role !== "admin")
            .map((user) =>
              api(`/api/admin/workspaces/${action.item.id}/members`, {
                method: "PUT",
                body: JSON.stringify({
                  user_id: user.id,
                  enabled: selected.has(user.id),
                }),
              })
            )
        );
      } else if (action.kind === "team") {
        const allowed = data.has("restrict_nodes")
          ? data.getAll("allowed_node_types")
          : null;
        const payload = {
          name: data.get("name"),
          description: data.get("description"),
          policy: {
            create_workflows: data.has("create_workflows"),
            edit_workflows: data.has("edit_workflows"),
            run_workflows: data.has("run_workflows"),
            manage_providers: data.has("manage_providers"),
            allowed_node_types: allowed,
          },
        };
        const team = await api(
          action.item ? `/api/teams/${action.item.id}` : "/api/teams",
          { method: action.item ? "PUT" : "POST", body: JSON.stringify(payload) }
        );
        await api(`/api/teams/${team.id}/members`, {
          method: "PUT",
          body: JSON.stringify({ user_ids: data.getAll("team_user_ids") }),
        });
      }
      closeModal();
      await load();
      toast("Configuração salva.");
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.classList.remove("hidden");
    } finally {
      submit.disabled = false;
    }
  });

  document.addEventListener("click", async (event) => {
    const editUser = event.target.closest("[data-edit-user]");
    const workspaceMembers = event.target.closest("[data-members-workspace]");
    const editTeam = event.target.closest("[data-edit-team]");
    const deleteTeam = event.target.closest("[data-delete-team]");
    if (editUser) {
      openModal("edit-user", overview.users.find((item) => item.id === editUser.dataset.editUser));
    } else if (workspaceMembers) {
      openModal("members", overview.workspaces.find((item) => item.id === workspaceMembers.dataset.membersWorkspace));
    } else if (editTeam) {
      openModal("team", overview.teams.find((item) => item.id === editTeam.dataset.editTeam));
    } else if (deleteTeam && window.confirm("Excluir este time e suas políticas?")) {
      try {
        await api(`/api/teams/${deleteTeam.dataset.deleteTeam}`, { method: "DELETE" });
        await load();
        toast("Time excluído.");
      } catch (error) {
        toast(error.message, "error");
      }
    }
  });

  $("#new-user-button")?.addEventListener("click", () => openModal("user"));
  $("#new-workspace-button")?.addEventListener("click", () => openModal("workspace"));
  $("#new-team-button").addEventListener("click", () => openModal("team"));
  $("#access-modal-close").addEventListener("click", closeModal);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });
  document.querySelectorAll("[data-access-tab]").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll("[data-access-tab]").forEach((item) =>
        item.classList.toggle("active", item === tab)
      );
      document.querySelectorAll("[data-access-panel]").forEach((panel) =>
        panel.classList.toggle(
          "active",
          panel.dataset.accessPanel === tab.dataset.accessTab
        )
      );
    });
  });
  load().catch((error) => toast(error.message, "error"));
})();
