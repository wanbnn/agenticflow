(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const state = {
    catalog: [],
    providers: [],
    workflow: null,
    selectedId: null,
    connectFrom: null,
    zoom: 1,
    pan: { x: 12, y: 36 },
    history: [],
    future: [],
    dirty: false,
    dragging: null,
  };

  const dom = {
    canvas: $("#canvas"),
    stage: $("#canvas-stage"),
    nodes: $("#nodes-layer"),
    edges: $("#edges-layer"),
    catalog: $("#node-catalog"),
    inspector: $("#inspector"),
    inspectorEmpty: $("#inspector-empty"),
    inspectorContent: $("#inspector-content"),
    inspectorForm: $("#inspector-form"),
    emptyCanvas: $("#empty-canvas"),
    workflowName: $("#workflow-name"),
    saveLabel: $("#save-label"),
    saveDot: $(".save-dot"),
    version: $("#version-label"),
    drawer: $("#run-drawer"),
    runInput: $("#run-input"),
    runStatus: $("#run-status"),
    runTrace: $("#run-trace"),
    resultPlaceholder: $("#result-placeholder"),
  };

  function api(path, options = {}) {
    return fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    }).then(async (response) => {
      if (!response.ok) {
        if (response.status === 401) {
          window.location.assign("/login");
          throw new Error("Sessão expirada.");
        }
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.detail || `Erro HTTP ${response.status}`);
      }
      if (response.status === 204) return null;
      return response.json();
    });
  }

  function uid(prefix) {
    return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
  }

  function cloneWorkflow() {
    return JSON.parse(JSON.stringify(state.workflow));
  }

  function snapshot() {
    if (!state.workflow) return;
    state.history.push(cloneWorkflow());
    if (state.history.length > 40) state.history.shift();
    state.future = [];
  }

  function markDirty() {
    state.dirty = true;
    dom.saveLabel.textContent = "Alterações não salvas";
    dom.saveDot.classList.add("dirty");
  }

  function catalogItem(type) {
    return state.catalog.find((item) => item.type === type);
  }

  function providerName(providerId) {
    if (!providerId || providerId === "mock") return "Simulado";
    return state.providers.find((item) => item.id === providerId)?.name || "Provedor indisponível";
  }

  function toast(message, tone = "success") {
    const item = document.createElement("div");
    item.className = `toast ${tone}`;
    item.textContent = message;
    $("#toast-region").append(item);
    setTimeout(() => item.remove(), 3200);
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  function renderCatalog(query = "") {
    const normalized = query.trim().toLowerCase();
    const groups = {};
    state.catalog
      .filter((item) =>
        `${item.name} ${item.description} ${item.category}`.toLowerCase().includes(normalized)
      )
      .forEach((item) => {
        (groups[item.category] ||= []).push(item);
      });

    dom.catalog.innerHTML = Object.entries(groups)
      .map(
        ([category, items]) => `
          <section class="catalog-group">
            <h3 class="catalog-group-title">${escapeHtml(category.toUpperCase())}</h3>
            ${items
              .map(
                (item) => `
                  <div class="catalog-node" draggable="true" data-node-type="${item.type}">
                    <span class="catalog-icon" style="--node-color:${item.color}">${item.icon}</span>
                    <span>
                      <strong>${escapeHtml(item.name)}</strong>
                      <small>${escapeHtml(item.description)}</small>
                    </span>
                    <span class="drag-dots">⠿</span>
                  </div>`
              )
              .join("")}
          </section>`
      )
      .join("");

    $$(".catalog-node", dom.catalog).forEach((item) => {
      item.addEventListener("dragstart", (event) => {
        event.dataTransfer.setData("application/agentic-node", item.dataset.nodeType);
        event.dataTransfer.effectAllowed = "copy";
      });
      item.addEventListener("dblclick", () => addNode(item.dataset.nodeType));
    });
  }

  function nodeSummary(node) {
    if (node.type === "llm") return `${providerName(node.config.provider_id || node.config.provider)} · ${node.config.model || "modelo padrão"}`;
    if (node.type === "agent") return `${node.config.role || "Especialista"} · ${providerName(node.config.provider_id || node.config.provider)}`;
    if (node.type === "webhook") return node.config.webhook_id ? "Endpoint ativo" : "Salve para ativar";
    if (node.type === "prompt") return "Template dinâmico";
    if (node.type === "input") return `campo: ${node.config.field || "message"}`;
    if (node.type === "output") return `retorna: ${node.config.field || "response"}`;
    if (node.type === "http") return `${node.config.method || "GET"} · API`;
    if (node.type === "condition") return `${node.config.field || "campo"} · ${node.config.operator || "equals"}`;
    if (node.type === "memory") return node.config.key || "conversation";
    return node.config.target || "Configurar";
  }

  function renderNodes() {
    if (!state.workflow) return;
    dom.nodes.innerHTML = state.workflow.nodes
      .map((node) => {
        const meta = catalogItem(node.type) || { color: "#7657ff", icon: "?", description: "" };
        const conditionHandles =
          node.type === "condition"
            ? `
              <span class="handle output true" data-handle="true" title="Saída verdadeira"></span>
              <span class="handle-label true">sim</span>
              <span class="handle output false" data-handle="false" title="Saída falsa"></span>
              <span class="handle-label false">não</span>`
            : `<span class="handle output" data-handle="default" title="Criar conexão"></span>`;
        return `
          <article class="flow-node ${node.id === state.selectedId ? "selected" : ""}"
            data-node-id="${node.id}"
            style="left:${node.position.x}px;top:${node.position.y}px;--node-color:${meta.color}">
            <span class="handle input" data-handle="input" title="Entrada"></span>
            ${conditionHandles}
            <div class="node-head">
              <span class="node-icon">${meta.icon}</span>
              <span class="node-copy">
                <strong>${escapeHtml(node.name)}</strong>
                <span>${escapeHtml(nodeSummary(node))}</span>
              </span>
              <button class="node-menu" tabindex="-1">•••</button>
            </div>
            <div class="node-status"><span class="status-dot"></span>${escapeHtml(meta.category || "Nó")}</div>
          </article>`;
      })
      .join("");

    dom.emptyCanvas.classList.toggle("hidden", state.workflow.nodes.length > 0);
    bindNodeEvents();
    requestAnimationFrame(() => {
      renderEdges();
      renderMinimap();
    });
  }

  function bindNodeEvents() {
    $$(".flow-node", dom.nodes).forEach((element) => {
      element.addEventListener("mousedown", startNodeDrag);
      element.addEventListener("click", (event) => {
        if (event.target.closest(".handle")) return;
        selectNode(element.dataset.nodeId);
      });
      $(".node-menu", element).addEventListener("click", (event) => {
        event.stopPropagation();
        selectNode(element.dataset.nodeId);
      });
      $$(".handle", element).forEach((handle) => {
        handle.addEventListener("mousedown", (event) => event.stopPropagation());
        handle.addEventListener("click", (event) => handleConnection(event, element.dataset.nodeId, handle));
      });
    });
  }

  function edgePath(source, target) {
    const sx = source.position.x + 218;
    const sy = source.position.y + 45;
    const tx = target.position.x;
    const ty = target.position.y + 45;
    const curve = Math.max(70, Math.abs(tx - sx) * 0.45);
    return `M ${sx} ${sy} C ${sx + curve} ${sy}, ${tx - curve} ${ty}, ${tx} ${ty}`;
  }

  function renderEdges() {
    if (!state.workflow) return;
    const nodes = Object.fromEntries(state.workflow.nodes.map((node) => [node.id, node]));
    dom.edges.innerHTML = state.workflow.edges
      .filter((edge) => nodes[edge.source] && nodes[edge.target])
      .map((edge) => {
        const source = nodes[edge.source];
        const target = nodes[edge.target];
        const label =
          source.type === "condition" && edge.source_handle !== "default"
            ? `<text class="edge-label" x="${(source.position.x + target.position.x + 218) / 2}" y="${(source.position.y + target.position.y) / 2 + 35}">${edge.source_handle === "true" ? "SIM" : "NÃO"}</text>`
            : "";
        return `<g data-edge-id="${edge.id}"><path class="edge-path" d="${edgePath(source, target)}"></path>${label}</g>`;
      })
      .join("");
  }

  function renderMinimap() {
    if (!state.workflow) return;
    $("#minimap-content").innerHTML = state.workflow.nodes
      .map((node) => {
        const meta = catalogItem(node.type) || { color: "#7657ff" };
        return `<span class="mini-node" style="left:${node.position.x / 13}px;top:${node.position.y / 13}px;--node-color:${meta.color}"></span>`;
      })
      .join("");
  }

  function applyTransform() {
    dom.stage.style.transform = `translate(${state.pan.x}px, ${state.pan.y}px) scale(${state.zoom})`;
    $("#zoom-value").textContent = `${Math.round(state.zoom * 100)}%`;
  }

  function startNodeDrag(event) {
    if (event.button !== 0 || event.target.closest(".handle,button")) return;
    const id = event.currentTarget.dataset.nodeId;
    const node = state.workflow.nodes.find((item) => item.id === id);
    if (!node) return;
    snapshot();
    selectNode(id);
    state.dragging = {
      node,
      startX: event.clientX,
      startY: event.clientY,
      originX: node.position.x,
      originY: node.position.y,
    };
    event.currentTarget.style.cursor = "grabbing";
    event.preventDefault();
  }

  window.addEventListener("mousemove", (event) => {
    if (!state.dragging) return;
    const drag = state.dragging;
    drag.node.position.x = Math.max(0, drag.originX + (event.clientX - drag.startX) / state.zoom);
    drag.node.position.y = Math.max(0, drag.originY + (event.clientY - drag.startY) / state.zoom);
    const element = $(`[data-node-id="${drag.node.id}"]`, dom.nodes);
    element.style.left = `${drag.node.position.x}px`;
    element.style.top = `${drag.node.position.y}px`;
    renderEdges();
    renderMinimap();
  });

  window.addEventListener("mouseup", () => {
    if (!state.dragging) return;
    state.dragging = null;
    markDirty();
  });

  function handleConnection(event, nodeId, handle) {
    event.stopPropagation();
    const kind = handle.dataset.handle;
    if (kind !== "input") {
      state.connectFrom = { nodeId, handle: kind };
      toast("Agora clique na entrada do próximo nó.");
      $(`[data-node-id="${nodeId}"]`, dom.nodes).classList.add("selected");
      return;
    }
    if (!state.connectFrom || state.connectFrom.nodeId === nodeId) return;
    const duplicate = state.workflow.edges.some(
      (edge) => edge.source === state.connectFrom.nodeId && edge.target === nodeId
    );
    if (!duplicate) {
      snapshot();
      state.workflow.edges.push({
        id: uid("edge"),
        source: state.connectFrom.nodeId,
        target: nodeId,
        source_handle: state.connectFrom.handle,
      });
      markDirty();
      renderEdges();
    }
    state.connectFrom = null;
  }

  function addNode(type, point = null) {
    const meta = catalogItem(type);
    if (!meta) return;
    snapshot();
    const count = state.workflow.nodes.length;
    const node = {
      id: uid(type),
      type,
      name: meta.name,
      position: point || { x: 120 + (count % 3) * 250, y: 120 + Math.floor(count / 3) * 150 },
      config: JSON.parse(JSON.stringify(meta.defaults || {})),
    };
    state.workflow.nodes.push(node);
    markDirty();
    selectNode(node.id);
    renderNodes();
  }

  function selectNode(id) {
    state.selectedId = id;
    $$(".flow-node", dom.nodes).forEach((node) =>
      node.classList.toggle("selected", node.dataset.nodeId === id)
    );
    renderInspector();
    if (window.innerWidth <= 800) dom.inspector.classList.add("mobile-open");
  }

  function renderInspector() {
    const node = state.workflow?.nodes.find((item) => item.id === state.selectedId);
    dom.inspectorEmpty.classList.toggle("hidden", Boolean(node));
    dom.inspectorContent.classList.toggle("hidden", !node);
    if (!node) return;
    const meta = catalogItem(node.type);
    $("#inspector-title").textContent = node.name;
    const avatar = $("#inspector-avatar");
    avatar.textContent = meta.icon;
    avatar.style.setProperty("--node-color", meta.color);

    const nameField = `
      <div class="field">
        <label for="field-node-name">Nome do nó</label>
        <input id="field-node-name" data-node-name value="${escapeHtml(node.name)}">
      </div>`;
    const configFields = (meta.fields || [])
      .map((field) => {
        const value = node.config[field.key] ?? "";
        let control;
        if (field.type === "provider_select") {
          const selected = node.config[field.key] || node.config.provider || "mock";
          const options = [
            { id: "mock", name: "Simulado (sem custo)" },
            ...state.providers.filter((provider) => provider.enabled),
          ];
          control = `<select data-config-key="${field.key}">
            ${options
              .map(
                (provider) =>
                  `<option value="${escapeHtml(provider.id)}" ${
                    selected === provider.id ? "selected" : ""
                  }>${escapeHtml(provider.name)}</option>`
              )
              .join("")}
          </select>
          <small class="field-help"><a href="/settings/providers">Gerenciar provedores do workspace</a></small>`;
        } else if (field.type === "webhook_url") {
          const endpoint = value
            ? `${window.location.origin}/webhooks/${value}`
            : "Salve o workflow para gerar a URL";
          control = `
            <div class="webhook-field">
              <input readonly value="${escapeHtml(endpoint)}" data-webhook-endpoint="${escapeHtml(endpoint)}">
              <button type="button" class="copy-webhook" ${value ? "" : "disabled"}>Copiar</button>
            </div>
            <small class="field-help">Envie POST com JSON para iniciar este workflow.</small>`;
        } else if (field.type === "textarea") {
          control = `<textarea data-config-key="${field.key}">${escapeHtml(value)}</textarea>`;
        } else if (field.type === "select") {
          control = `<select data-config-key="${field.key}">${field.options
            .map(
              (option) =>
                `<option value="${escapeHtml(option)}" ${String(value) === option ? "selected" : ""}>${escapeHtml(option)}</option>`
            )
            .join("")}</select>`;
        } else {
          control = `<input type="${field.type || "text"}" data-config-key="${field.key}" value="${escapeHtml(value)}">`;
        }
        return `<div class="field"><label>${escapeHtml(field.label)}</label>${control}${
          field.key === "template"
            ? '<small class="field-help">Use {{campo}} para inserir dados do fluxo.</small>'
            : ""
        }</div>`;
      })
      .join("");
    const note =
      node.type === "llm" || node.type === "agent"
        ? '<div class="provider-note">Escolha um provedor cadastrado visualmente. O modelo em branco usa o padrão definido no provedor.</div>'
        : node.type === "webhook"
        ? '<div class="provider-note">A URL é exclusiva deste nó. O corpo JSON recebido vira os dados de entrada e a execução aparece no histórico do workflow.</div>'
        : "";
    dom.inspectorForm.innerHTML = nameField + configFields + note;

    $("[data-node-name]", dom.inspectorForm).addEventListener("change", (event) => {
      snapshot();
      node.name = event.target.value.trim() || meta.name;
      markDirty();
      renderNodes();
      renderInspector();
    });
    $$("[data-config-key]", dom.inspectorForm).forEach((control) => {
      control.addEventListener("change", () => {
        snapshot();
        let value = control.value;
        if (control.type === "number") value = Number(value);
        node.config[control.dataset.configKey] = value;
        markDirty();
        renderNodes();
        renderInspector();
      });
    });
    $(".copy-webhook", dom.inspectorForm)?.addEventListener("click", async () => {
      const endpoint = $("[data-webhook-endpoint]", dom.inspectorForm).dataset.webhookEndpoint;
      await navigator.clipboard.writeText(endpoint);
      toast("URL do webhook copiada.");
    });
  }

  function deleteSelected() {
    if (!state.selectedId) return;
    snapshot();
    state.workflow.nodes = state.workflow.nodes.filter((node) => node.id !== state.selectedId);
    state.workflow.edges = state.workflow.edges.filter(
      (edge) => edge.source !== state.selectedId && edge.target !== state.selectedId
    );
    state.selectedId = null;
    markDirty();
    renderNodes();
    renderInspector();
  }

  function autoLayout() {
    if (!state.workflow.nodes.length) return;
    snapshot();
    const nodes = state.workflow.nodes;
    const inbound = Object.fromEntries(nodes.map((node) => [node.id, 0]));
    const children = {};
    state.workflow.edges.forEach((edge) => {
      inbound[edge.target] = (inbound[edge.target] || 0) + 1;
      (children[edge.source] ||= []).push(edge.target);
    });
    let queue = nodes.filter((node) => inbound[node.id] === 0).map((node) => ({ id: node.id, level: 0 }));
    const levels = {};
    while (queue.length) {
      const current = queue.shift();
      levels[current.id] = Math.max(levels[current.id] || 0, current.level);
      (children[current.id] || []).forEach((id) => {
        inbound[id] -= 1;
        if (inbound[id] === 0) queue.push({ id, level: current.level + 1 });
      });
    }
    const rows = {};
    nodes.forEach((node) => {
      const level = levels[node.id] || 0;
      const row = rows[level] || 0;
      node.position = { x: 80 + level * 280, y: 140 + row * 150 };
      rows[level] = row + 1;
    });
    markDirty();
    renderNodes();
    fitView();
  }

  function fitView() {
    if (!state.workflow.nodes.length) return;
    const xs = state.workflow.nodes.map((node) => node.position.x);
    const ys = state.workflow.nodes.map((node) => node.position.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs) + 218;
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys) + 100;
    const width = dom.canvas.clientWidth;
    const height = dom.canvas.clientHeight;
    state.zoom = Math.min(1.15, Math.max(0.45, Math.min((width - 100) / (maxX - minX), (height - 100) / (maxY - minY))));
    state.pan.x = (width - (maxX - minX) * state.zoom) / 2 - minX * state.zoom;
    state.pan.y = (height - (maxY - minY) * state.zoom) / 2 - minY * state.zoom;
    applyTransform();
  }

  function undo() {
    if (!state.history.length) return;
    state.future.push(cloneWorkflow());
    state.workflow = state.history.pop();
    state.selectedId = null;
    markDirty();
    hydrateWorkflow();
  }

  function redo() {
    if (!state.future.length) return;
    state.history.push(cloneWorkflow());
    state.workflow = state.future.pop();
    state.selectedId = null;
    markDirty();
    hydrateWorkflow();
  }

  async function saveWorkflow(showToast = true) {
    if (!state.workflow) return;
    const payload = {
      name: dom.workflowName.value.trim() || "Workflow sem nome",
      description: state.workflow.description || "",
      nodes: state.workflow.nodes,
      edges: state.workflow.edges,
    };
    const saved = await api(`/api/workflows/${state.workflow.id}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    state.workflow = saved;
    state.dirty = false;
    dom.saveLabel.textContent = "Salvo agora";
    dom.saveDot.classList.remove("dirty");
    dom.version.textContent = `v${saved.version}`;
    renderNodes();
    renderInspector();
    if (showToast) toast("Workflow salvo.");
  }

  function openDrawer() {
    dom.drawer.classList.add("open");
    setTimeout(() => dom.runInput.focus(), 120);
  }

  function setRunStatus(label, type) {
    dom.runStatus.textContent = label;
    dom.runStatus.className = `run-status ${type}`;
  }

  function clearNodeStatuses() {
    $$(".flow-node", dom.nodes).forEach((node) => node.classList.remove("running", "success", "error"));
    $$(".edge-path", dom.edges).forEach((edge) => edge.classList.remove("active", "success"));
  }

  async function executeWorkflow() {
    let input;
    try {
      input = JSON.parse(dom.runInput.value);
    } catch {
      toast("Corrija o JSON de entrada.", "error");
      return;
    }
    $("#confirm-run").disabled = true;
    setRunStatus("Executando", "running");
    dom.resultPlaceholder.classList.add("hidden");
    dom.runTrace.classList.remove("hidden");
    dom.runTrace.innerHTML = '<div class="result-placeholder"><div>···</div><p>O LangGraph está executando os nós...</p></div>';
    clearNodeStatuses();
    state.workflow.nodes.forEach((node, index) => {
      setTimeout(() => {
        clearNodeStatuses();
        $(`[data-node-id="${node.id}"]`, dom.nodes)?.classList.add("running");
      }, index * 180);
    });

    try {
      if (state.dirty) await saveWorkflow(false);
      const result = await api(`/api/workflows/${state.workflow.id}/run`, {
        method: "POST",
        body: JSON.stringify({ input, session_id: "playground" }),
      });
      clearNodeStatuses();
      result.events.forEach((event) => {
        $(`[data-node-id="${event.node_id}"]`, dom.nodes)?.classList.add(event.status);
      });
      setRunStatus(result.status === "success" ? "Concluído" : "Falhou", result.status);
      const output = result.status === "success" ? result.output : result.error;
      dom.runTrace.innerHTML = `
        <pre class="trace-output">${escapeHtml(
          typeof output === "string" ? output : JSON.stringify(output, null, 2)
        )}</pre>
        ${result.events
          .map(
            (event) => `
              <div class="trace-event ${event.status}">
                <span class="trace-event-dot"></span>
                <strong>${escapeHtml(event.node_name)}</strong>
                <span>${event.duration_ms} ms</span>
              </div>`
          )
          .join("")}`;
      toast(result.status === "success" ? "Execução concluída." : result.error, result.status);
    } catch (error) {
      clearNodeStatuses();
      setRunStatus("Erro", "error");
      dom.runTrace.innerHTML = `<pre class="trace-output">${escapeHtml(error.message)}</pre>`;
      toast(error.message, "error");
    } finally {
      $("#confirm-run").disabled = false;
    }
  }

  function hydrateWorkflow() {
    dom.workflowName.value = state.workflow.name;
    dom.version.textContent = `v${state.workflow.version}`;
    renderNodes();
    renderInspector();
    applyTransform();
  }

  function bindGlobalEvents() {
    $("#node-search").addEventListener("input", (event) => renderCatalog(event.target.value));
    document.addEventListener("keydown", (event) => {
      if (event.key === "/" && !event.target.matches("input,textarea")) {
        event.preventDefault();
        $("#node-search").focus();
      }
      if ((event.key === "Delete" || event.key === "Backspace") && !event.target.matches("input,textarea")) deleteSelected();
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        saveWorkflow().catch((error) => toast(error.message, "error"));
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        event.shiftKey ? redo() : undo();
      }
      if (event.key === "Escape") {
        state.connectFrom = null;
        dom.drawer.classList.remove("open");
      }
    });

    dom.canvas.addEventListener("dragover", (event) => {
      if (event.dataTransfer.types.includes("application/agentic-node")) {
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
      }
    });
    dom.canvas.addEventListener("drop", (event) => {
      const type = event.dataTransfer.getData("application/agentic-node");
      if (!type) return;
      event.preventDefault();
      const rect = dom.canvas.getBoundingClientRect();
      addNode(type, {
        x: (event.clientX - rect.left - state.pan.x) / state.zoom - 109,
        y: (event.clientY - rect.top - state.pan.y) / state.zoom - 45,
      });
    });
    dom.canvas.addEventListener("click", (event) => {
      if (event.target === dom.canvas || event.target.classList.contains("canvas-grid")) {
        state.selectedId = null;
        renderNodes();
        renderInspector();
      }
    });

    $("#save-button").addEventListener("click", () =>
      saveWorkflow().catch((error) => toast(error.message, "error"))
    );
    $("#run-button").addEventListener("click", openDrawer);
    $("#drawer-close").addEventListener("click", () => dom.drawer.classList.remove("open"));
    $("#confirm-run").addEventListener("click", executeWorkflow);
    $("#delete-node").addEventListener("click", deleteSelected);
    $("#auto-layout").addEventListener("click", autoLayout);
    $("#undo-button").addEventListener("click", undo);
    $("#redo-button").addEventListener("click", redo);
    $("#fit-view").addEventListener("click", fitView);
    $("#zoom-value").addEventListener("click", fitView);
    $("#zoom-in").addEventListener("click", () => {
      state.zoom = Math.min(1.6, state.zoom + 0.1);
      applyTransform();
    });
    $("#zoom-out").addEventListener("click", () => {
      state.zoom = Math.max(0.35, state.zoom - 0.1);
      applyTransform();
    });
    dom.workflowName.addEventListener("change", () => {
      state.workflow.name = dom.workflowName.value.trim() || "Workflow sem nome";
      markDirty();
    });
    dom.runInput.addEventListener("input", () => {
      try {
        JSON.parse(dom.runInput.value);
        $("#validation-label").textContent = "JSON válido";
        $("#validation-label").classList.remove("invalid");
      } catch {
        $("#validation-label").textContent = "JSON inválido";
        $("#validation-label").classList.add("invalid");
      }
    });
  }

  async function init() {
    try {
      const workflowId = document.querySelector(".app-shell")?.dataset.workflowId;
      const [catalog, workflow, providers] = await Promise.all([
        api("/api/catalog"),
        api(`/api/workflows/${workflowId}`),
        api("/api/providers"),
      ]);
      state.catalog = catalog;
      state.workflow = workflow;
      state.providers = providers;
      renderCatalog();
      hydrateWorkflow();
      bindGlobalEvents();
      setTimeout(fitView, 80);
    } catch (error) {
      toast(`Não foi possível iniciar: ${error.message}`, "error");
    }
  }

  init();
})();
