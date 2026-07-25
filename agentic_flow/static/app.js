(() => {
  "use strict";

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  const state = {
    catalog: [],
    providers: [],
    workflow: null,
    permissions: {},
    selectedId: null,
    connectFrom: null,
    zoom: 1,
    pan: { x: 12, y: 36 },
    history: [],
    future: [],
    dirty: false,
    dragging: null,
    panning: null,
    connectionDrag: null,
    suppressCanvasClick: false,
    suppressHandleClick: false,
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

  function nodePorts(node, direction) {
    const meta = catalogItem(node.type) || {};
    if (direction === "input") {
      return meta.inputs === undefined
        ? [{ id: "input", label: "entrada", kind: "flow", multiple: true }]
        : meta.inputs;
    }
    if (meta.outputs) return meta.outputs;
    return (meta.handles || ["default"]).map((id) => ({
      id,
      label: id === "default" ? "saída" : id,
      kind: "flow",
    }));
  }

  function portOffset(ports, index) {
    if (ports.length === 1) return 45;
    return 29 + index * 34;
  }

  function can(permission) {
    return Boolean(state.permissions?.[permission]);
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

  function formatOutput(value) {
    if (typeof value === "string") {
      return value.startsWith("data:") && value.length > 180
        ? `[data URI omitida da visualização · ${value.length} caracteres]`
        : value;
    }
    return JSON.stringify(
      value,
      (_key, item) =>
        typeof item === "string" && item.startsWith("data:") && item.length > 180
          ? `[data URI omitida · ${item.length} caracteres]`
          : item,
      2
    );
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
                  <div class="catalog-node" draggable="${can("edit_workflows")}" data-node-type="${item.type}">
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
        if (!can("edit_workflows")) {
          event.preventDefault();
          return;
        }
        event.dataTransfer.setData("application/agentic-node", item.dataset.nodeType);
        event.dataTransfer.effectAllowed = "copy";
      });
      item.addEventListener("dblclick", () => addNode(item.dataset.nodeType));
    });
  }

  function nodeSummary(node) {
    if (node.type === "llm") return `${providerName(node.config.provider_id || node.config.provider)} · ${node.config.model || "modelo padrão"}`;
    if (node.type === "agent") {
      const tools = state.workflow?.edges.filter(
        (edge) => edge.target === node.id && edge.target_handle === "tools"
      ).length || 0;
      return `${node.config.role || "Especialista"} · ${tools} ${tools === 1 ? "tool" : "tools"}`;
    }
    if (node.type === "webhook") return node.config.webhook_id ? "Endpoint ativo" : "Salve para ativar";
    if (node.type === "prompt") return "Template dinâmico";
    if (node.type === "file") return `${String(node.config.format || "auto").toUpperCase()} · ${node.config.output_field || "document_text"}`;
    if (node.type === "image") return `${node.config.operation || "inspect"} · ${node.config.output_format || "PNG"}`;
    if (node.type === "video_frames") return `a cada ${node.config.interval_seconds || 1}s · até ${node.config.max_frames || 12} frames`;
    if (node.type === "vector_database") return `${node.config.write_mode || "append"} · base isolada`;
    if (node.type === "rag") {
      const databaseEdge = state.workflow?.edges.find(
        (edge) => edge.target === node.id && edge.target_handle === "database"
      );
      const database = state.workflow?.nodes.find((item) => item.id === databaseEdge?.source);
      return database ? `busca em ${database.name}` : "selecione uma base";
    }
    if (node.type === "mcp_server") return node.config.url || "configure o endpoint";
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
        const inputs = nodePorts(node, "input");
        const outputs = nodePorts(node, "output");
        const inputHandles = inputs
          .map((port, index) => {
            const top = portOffset(inputs, index);
            return `<span class="handle input port-${escapeHtml(port.kind)}"
              style="top:${top}px" data-direction="input" data-kind="${escapeHtml(port.kind)}"
              data-handle="${escapeHtml(port.id)}" title="${escapeHtml(port.label)}"></span>
              <span class="port-label input-label" style="top:${top - 6}px">${escapeHtml(port.label)}</span>`;
          })
          .join("");
        const outputHandles = outputs
          .map((port, index) => {
            const top = portOffset(outputs, index);
            return `<span class="handle output ${escapeHtml(port.id)} port-${escapeHtml(port.kind)}"
              style="top:${top}px" data-direction="output" data-kind="${escapeHtml(port.kind)}"
              data-handle="${escapeHtml(port.id)}" title="${escapeHtml(port.label)}"></span>
              <span class="port-label output-label" style="top:${top - 6}px">${escapeHtml(port.label)}</span>`;
          })
          .join("");
        return `
          <article class="flow-node ${node.id === state.selectedId ? "selected" : ""}"
            data-node-id="${node.id}"
            style="left:${node.position.x}px;top:${node.position.y}px;--node-color:${meta.color}">
            ${inputHandles}
            ${outputHandles}
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
      element.addEventListener("pointerdown", startNodeDrag);
      element.addEventListener("click", (event) => {
        if (event.target.closest(".handle")) return;
        selectNode(element.dataset.nodeId);
      });
      $(".node-menu", element).addEventListener("click", (event) => {
        event.stopPropagation();
        selectNode(element.dataset.nodeId);
      });
      $$(".handle", element).forEach((handle) => {
        handle.addEventListener("pointerdown", (event) => {
          event.stopPropagation();
          if (handle.dataset.direction === "output") {
            startConnectionDrag(event, element.dataset.nodeId, handle);
          }
        });
        handle.addEventListener("click", (event) => {
          if (state.suppressHandleClick) {
            event.stopPropagation();
            return;
          }
          handleConnection(event, element.dataset.nodeId, handle);
        });
      });
    });
  }

  function sourceAnchor(source, sourceHandle = "default") {
    const ports = nodePorts(source, "output");
    const index = Math.max(0, ports.findIndex((port) => port.id === sourceHandle));
    return {
      x: source.position.x + 218,
      y: source.position.y + portOffset(ports, index),
    };
  }

  function targetAnchor(target, targetHandle = "input") {
    const ports = nodePorts(target, "input");
    const index = Math.max(0, ports.findIndex((port) => port.id === targetHandle));
    return {
      x: target.position.x,
      y: target.position.y + portOffset(ports, index),
    };
  }

  function edgePathBetween(sx, sy, tx, ty) {
    const curve = Math.max(70, Math.abs(tx - sx) * 0.45);
    return `M ${sx} ${sy} C ${sx + curve} ${sy}, ${tx - curve} ${ty}, ${tx} ${ty}`;
  }

  function edgePath(source, target, sourceHandle = "default", targetHandle = "input") {
    const start = sourceAnchor(source, sourceHandle);
    const end = targetAnchor(target, targetHandle);
    return edgePathBetween(start.x, start.y, end.x, end.y);
  }

  function renderEdges() {
    if (!state.workflow) return;
    const nodes = Object.fromEntries(state.workflow.nodes.map((node) => [node.id, node]));
    dom.edges.innerHTML = state.workflow.edges
      .filter((edge) => nodes[edge.source] && nodes[edge.target])
      .map((edge) => {
        const source = nodes[edge.source];
        const target = nodes[edge.target];
        const resource = (edge.target_handle || "input") !== "input";
        const label =
          source.type === "condition" && edge.source_handle !== "default"
            ? `<text class="edge-label" x="${(source.position.x + target.position.x + 218) / 2}" y="${(source.position.y + target.position.y) / 2 + 35}">${edge.source_handle === "true" ? "SIM" : "NÃO"}</text>`
            : resource
            ? `<text class="edge-label resource-label" x="${(source.position.x + target.position.x + 218) / 2}" y="${(source.position.y + target.position.y) / 2 + 35}">${escapeHtml(edge.source_handle).toUpperCase()}</text>`
            : "";
        return `<g data-edge-id="${edge.id}"><path class="edge-path ${resource ? "resource-edge" : ""}" d="${edgePath(source, target, edge.source_handle, edge.target_handle || "input")}"></path>${label}</g>`;
      })
      .join("");
    renderConnectionPreview();
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
    const grid = $(".canvas-grid", dom.canvas);
    grid.style.backgroundPosition = `${state.pan.x}px ${state.pan.y}px`;
    grid.style.backgroundSize = `${22 * state.zoom}px ${22 * state.zoom}px`;
    $("#zoom-value").textContent = `${Math.round(state.zoom * 100)}%`;
  }

  function canvasPoint(clientX, clientY) {
    const rect = dom.canvas.getBoundingClientRect();
    return {
      x: (clientX - rect.left - state.pan.x) / state.zoom,
      y: (clientY - rect.top - state.pan.y) / state.zoom,
    };
  }

  function setZoom(nextZoom, clientX = null, clientY = null) {
    const zoom = Math.min(2, Math.max(0.25, nextZoom));
    const rect = dom.canvas.getBoundingClientRect();
    const focusX = clientX == null ? rect.left + rect.width / 2 : clientX;
    const focusY = clientY == null ? rect.top + rect.height / 2 : clientY;
    const localX = focusX - rect.left;
    const localY = focusY - rect.top;
    const worldX = (localX - state.pan.x) / state.zoom;
    const worldY = (localY - state.pan.y) / state.zoom;
    state.pan.x = localX - worldX * zoom;
    state.pan.y = localY - worldY * zoom;
    state.zoom = zoom;
    applyTransform();
  }

  function startNodeDrag(event) {
    if (
      !can("edit_workflows") ||
      event.button !== 0 ||
      event.target.closest(".handle,button") ||
      $("#pan-tool").classList.contains("active")
    ) return;
    const id = event.currentTarget.dataset.nodeId;
    const node = state.workflow.nodes.find((item) => item.id === id);
    if (!node) return;
    snapshot();
    selectNode(id);
    state.dragging = {
      node,
      pointerId: event.pointerId,
      captureTarget: event.currentTarget,
      startX: event.clientX,
      startY: event.clientY,
      originX: node.position.x,
      originY: node.position.y,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.currentTarget.style.cursor = "grabbing";
    event.preventDefault();
  }

  window.addEventListener("pointermove", (event) => {
    if (state.dragging && state.dragging.pointerId === event.pointerId) {
      const drag = state.dragging;
      drag.node.position.x = drag.originX + (event.clientX - drag.startX) / state.zoom;
      drag.node.position.y = drag.originY + (event.clientY - drag.startY) / state.zoom;
      const element = $(`[data-node-id="${drag.node.id}"]`, dom.nodes);
      element.style.left = `${drag.node.position.x}px`;
      element.style.top = `${drag.node.position.y}px`;
      renderEdges();
      renderMinimap();
    }
    if (state.panning && state.panning.pointerId === event.pointerId) {
      const pan = state.panning;
      const dx = event.clientX - pan.startX;
      const dy = event.clientY - pan.startY;
      pan.moved ||= Math.abs(dx) + Math.abs(dy) > 3;
      state.pan.x = pan.originX + dx;
      state.pan.y = pan.originY + dy;
      applyTransform();
    }
    if (state.connectionDrag && state.connectionDrag.pointerId === event.pointerId) {
      const connection = state.connectionDrag;
      connection.clientX = event.clientX;
      connection.clientY = event.clientY;
      connection.moved ||= Math.hypot(
        event.clientX - connection.startX,
        event.clientY - connection.startY
      ) > 3;
      const hoveredNode = document
        .elementFromPoint(event.clientX, event.clientY)
        ?.closest(".flow-node");
      $$(".flow-node.connection-target", dom.nodes).forEach((node) =>
        node.classList.remove("connection-target")
      );
      if (hoveredNode?.dataset.nodeId !== state.connectFrom?.nodeId) {
        hoveredNode?.classList.add("connection-target");
      }
      renderEdges();
    }
  });

  function finishPointerInteraction(event) {
    if (state.dragging && state.dragging.pointerId === event.pointerId) {
      const { captureTarget, pointerId } = state.dragging;
      if (captureTarget?.hasPointerCapture?.(pointerId)) {
        captureTarget.releasePointerCapture(pointerId);
      }
      state.dragging = null;
      markDirty();
    }
    if (state.panning && state.panning.pointerId === event.pointerId) {
      const { pointerId } = state.panning;
      if (state.panning.moved) {
        state.suppressCanvasClick = true;
        setTimeout(() => (state.suppressCanvasClick = false), 0);
      }
      state.panning = null;
      dom.canvas.classList.remove("panning");
      if (dom.canvas.hasPointerCapture?.(pointerId)) {
        dom.canvas.releasePointerCapture(pointerId);
      }
    }
    if (state.connectionDrag && state.connectionDrag.pointerId === event.pointerId) {
      finishConnectionDrag(event);
    }
  }

  window.addEventListener("pointerup", finishPointerInteraction);
  window.addEventListener("pointercancel", finishPointerInteraction);

  function startConnectionDrag(event, nodeId, handle) {
    if (event.button !== 0 || !can("edit_workflows")) return;
    state.connectFrom = { nodeId, handle: handle.dataset.handle };
    state.connectionDrag = {
      pointerId: event.pointerId,
      captureTarget: handle,
      startX: event.clientX,
      startY: event.clientY,
      clientX: event.clientX,
      clientY: event.clientY,
      moved: false,
    };
    handle.setPointerCapture?.(event.pointerId);
    handle.classList.add("connecting");
    renderEdges();
    event.preventDefault();
  }

  function renderConnectionPreview() {
    if (!state.connectionDrag || !state.connectFrom) return;
    const source = state.workflow.nodes.find((node) => node.id === state.connectFrom.nodeId);
    if (!source) return;
    const start = sourceAnchor(source, state.connectFrom.handle);
    const end = canvasPoint(state.connectionDrag.clientX, state.connectionDrag.clientY);
    dom.edges.insertAdjacentHTML(
      "beforeend",
      `<path class="edge-path connection-preview" d="${edgePathBetween(
        start.x,
        start.y,
        end.x,
        end.y
      )}"></path>`
    );
  }

  function compatibleTargetHandle(source, targetId, requestedHandle = "") {
    const sourceNode = state.workflow.nodes.find((node) => node.id === source.nodeId);
    const targetNode = state.workflow.nodes.find((node) => node.id === targetId);
    if (!sourceNode || !targetNode) return null;
    const sourcePort = nodePorts(sourceNode, "output").find(
      (port) => port.id === source.handle
    );
    const targets = nodePorts(targetNode, "input");
    if (requestedHandle) {
      const requested = targets.find((port) => port.id === requestedHandle);
      const occupied = state.workflow.edges.some(
        (edge) =>
          edge.target === targetId &&
          (edge.target_handle || "input") === requested?.id
      );
      return requested?.kind === sourcePort?.kind &&
        (requested.multiple || !occupied)
        ? requested.id
        : null;
    }
    return (
      targets.find((port) => {
        if (port.kind !== sourcePort?.kind) return false;
        return (
          port.multiple ||
          !state.workflow.edges.some(
            (edge) =>
              edge.target === targetId &&
              (edge.target_handle || "input") === port.id
          )
        );
      })?.id || null
    );
  }

  function createConnection(source, targetId, requestedHandle = "") {
    if (!source || source.nodeId === targetId) return false;
    const targetHandle = compatibleTargetHandle(source, targetId, requestedHandle);
    if (!targetHandle) {
      toast("Essas alças não são compatíveis.", "error");
      return false;
    }
    const duplicate = state.workflow.edges.some(
      (edge) =>
        edge.source === source.nodeId &&
        edge.target === targetId &&
        edge.source_handle === source.handle &&
        (edge.target_handle || "input") === targetHandle
    );
    if (duplicate) {
      toast("Esses nós já estão conectados.", "error");
      return false;
    }
    snapshot();
    state.workflow.edges.push({
      id: uid("edge"),
      source: source.nodeId,
      target: targetId,
      source_handle: source.handle,
      target_handle: targetHandle,
    });
    markDirty();
    return true;
  }

  function finishConnectionDrag(event) {
    const drag = state.connectionDrag;
    const source = state.connectFrom;
    const dropElement =
      event.type === "pointercancel"
        ? null
        : document.elementFromPoint(event.clientX, event.clientY);
    const targetNode = dropElement?.closest(".flow-node");
    const inputHandle = dropElement?.closest(".handle.input");
    const droppedOnInput = Boolean(inputHandle);
    const droppedOnNodeBody = Boolean(targetNode && !dropElement?.closest(".handle.output"));
    const { captureTarget, pointerId } = drag;
    state.connectionDrag = null;
    if (captureTarget?.hasPointerCapture?.(pointerId)) {
      captureTarget.releasePointerCapture(pointerId);
    }
    $$(".handle.connecting", dom.nodes).forEach((handle) => handle.classList.remove("connecting"));
    $$(".flow-node.connection-target", dom.nodes).forEach((node) =>
      node.classList.remove("connection-target")
    );
    if (
      targetNode &&
      targetNode.dataset.nodeId !== source?.nodeId &&
      (droppedOnInput || droppedOnNodeBody)
    ) {
      createConnection(
        source,
        targetNode.dataset.nodeId,
        inputHandle?.dataset.handle || ""
      );
      state.connectFrom = null;
      state.suppressHandleClick = true;
      setTimeout(() => (state.suppressHandleClick = false), 0);
    } else if (drag.moved) {
      state.connectFrom = null;
    }
    renderEdges();
  }

  function handleConnection(event, nodeId, handle) {
    event.stopPropagation();
    const kind = handle.dataset.handle;
    if (handle.dataset.direction === "output") {
      state.connectFrom = { nodeId, handle: kind };
      toast("Agora clique em uma alça compatível.");
      $(`[data-node-id="${nodeId}"]`, dom.nodes).classList.add("selected");
      return;
    }
    if (!state.connectFrom || state.connectFrom.nodeId === nodeId) return;
    createConnection(state.connectFrom, nodeId, kind);
    state.connectFrom = null;
    renderEdges();
  }

  function addNode(type, point = null) {
    if (!can("edit_workflows")) return;
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
        } else if (field.type === "node_select") {
          const allowedTypes = field.node_types || [];
          const options = state.workflow.nodes.filter(
            (candidate) =>
              candidate.id !== node.id &&
              (!allowedTypes.length || allowedTypes.includes(candidate.type))
          );
          control = `<select data-config-key="${field.key}">
            <option value="">Nenhum</option>
            ${options
              .map(
                (candidate) =>
                  `<option value="${escapeHtml(candidate.id)}" ${
                    String(value) === candidate.id ? "selected" : ""
                  }>${escapeHtml(candidate.name)}</option>`
              )
              .join("")}
          </select>
          <small class="field-help">Cada nó de Banco de Vetores mantém uma base independente.</small>`;
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
        : node.type === "vector_database"
        ? '<div class="provider-note"><strong id="vector-database-status">Consultando a base…</strong><br>Esta instância possui armazenamento próprio. Conteúdo repetido é deduplicado automaticamente.</div>'
        : node.type === "rag"
        ? '<div class="provider-note">Conecte a alça database de um Banco de Vetores e leve a alça tool até um Agente IA.</div>'
        : node.type === "mcp_server"
        ? '<div class="provider-note">A alça tool disponibiliza as ferramentas do servidor MCP ao agente conectado.</div>'
        : node.type === "webhook"
        ? '<div class="provider-note">A URL é exclusiva deste nó. O corpo JSON recebido vira os dados de entrada e a execução aparece no histórico do workflow.</div>'
        : "";
    dom.inspectorForm.innerHTML = nameField + configFields + note;
    if (node.type === "vector_database") {
      const status = $("#vector-database-status", dom.inspectorForm);
      api(`/api/workflows/${state.workflow.id}/vector-databases/${node.id}`)
        .then((details) => {
          if (state.selectedId === node.id && status.isConnected) {
            const total = Number(details.chunks_total || 0);
            status.textContent = `${total} ${total === 1 ? "trecho indexado" : "trechos indexados"}`;
          }
        })
        .catch(() => {
          if (status.isConnected) status.textContent = "Salve o workflow para criar esta base";
        });
    }

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
    if (!can("edit_workflows")) {
      $$("input,textarea,select,button", dom.inspectorForm).forEach(
        (control) => (control.disabled = true)
      );
    }
  }

  function deleteSelected() {
    if (!state.selectedId || !can("edit_workflows")) return;
    snapshot();
    const removedId = state.selectedId;
    state.workflow.nodes = state.workflow.nodes.filter((node) => node.id !== removedId);
    state.workflow.nodes.forEach((node) => {
      if (node.config.vector_db_node_id === removedId) node.config.vector_db_node_id = "";
    });
    state.workflow.edges = state.workflow.edges.filter(
      (edge) => edge.source !== state.selectedId && edge.target !== state.selectedId
    );
    state.selectedId = null;
    markDirty();
    renderNodes();
    renderInspector();
  }

  function autoLayout() {
    if (!state.workflow.nodes.length || !can("edit_workflows")) return;
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
          formatOutput(output)
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

  function applyPermissions() {
    const editable = can("edit_workflows");
    document.body.classList.toggle("workflow-readonly", !editable);
    dom.workflowName.disabled = !editable;
    $("#save-button").classList.toggle("hidden", !editable);
    $("#run-button").classList.toggle("hidden", !can("run_workflows"));
    $("#auto-layout").classList.toggle("hidden", !editable);
    $("#delete-node").classList.toggle("hidden", !editable);
    $$("input,textarea,select", dom.inspectorForm).forEach(
      (control) => (control.disabled = !editable)
    );
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
        state.connectionDrag = null;
        renderEdges();
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
    dom.canvas.addEventListener("pointerdown", (event) => {
      const panToolActive = $("#pan-tool").classList.contains("active");
      const isBackground =
        event.target === dom.canvas ||
        event.target.classList.contains("canvas-grid") ||
        event.target === dom.stage ||
        event.target === dom.nodes ||
        event.target === dom.edges ||
        Boolean(event.target.closest(".empty-canvas"));
      if (
        (!isBackground && !panToolActive) ||
        (event.button !== 0 && event.button !== 1) ||
        event.target.closest(".handle,button")
      ) return;
      state.panning = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        originX: state.pan.x,
        originY: state.pan.y,
        moved: false,
      };
      dom.canvas.setPointerCapture?.(event.pointerId);
      dom.canvas.classList.add("panning");
      event.preventDefault();
    });
    dom.canvas.addEventListener(
      "wheel",
      (event) => {
        event.preventDefault();
        setZoom(state.zoom * Math.exp(-event.deltaY * 0.0015), event.clientX, event.clientY);
      },
      { passive: false }
    );
    dom.canvas.addEventListener("click", (event) => {
      if (state.suppressCanvasClick) return;
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
    $("#zoom-in").addEventListener("click", () => setZoom(state.zoom + 0.1));
    $("#zoom-out").addEventListener("click", () => setZoom(state.zoom - 0.1));
    $("#pan-tool").addEventListener("click", (event) => {
      event.currentTarget.classList.toggle("active");
      dom.canvas.classList.toggle("pan-tool-active", event.currentTarget.classList.contains("active"));
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
    $("#asset-file").addEventListener("change", (event) => {
      const file = event.target.files?.[0];
      if (!file) return;
      if (file.size > 25 * 1024 * 1024) {
        toast("O arquivo excede o limite de 25 MB.", "error");
        event.target.value = "";
        return;
      }
      const reader = new FileReader();
      reader.addEventListener("load", () => {
        let input;
        try {
          input = JSON.parse(dom.runInput.value);
        } catch {
          input = {};
        }
        const field = $("#asset-field").value.trim() || "file";
        input[field] = {
          name: file.name,
          mime_type: file.type || "application/octet-stream",
          data: reader.result,
        };
        dom.runInput.value = JSON.stringify(input, null, 2);
        dom.runInput.dispatchEvent(new Event("input"));
        $("#asset-file-label").textContent = `${file.name} · ${Math.ceil(file.size / 1024)} KB`;
        toast(`Arquivo anexado no campo “${field}”.`);
      });
      reader.readAsDataURL(file);
    });
  }

  async function init() {
    try {
      const workflowId = document.querySelector(".app-shell")?.dataset.workflowId;
      const [catalog, workflow, providers, context] = await Promise.all([
        api("/api/catalog"),
        api(`/api/workflows/${workflowId}`),
        api("/api/providers"),
        api("/api/auth/me"),
      ]);
      state.catalog = catalog;
      state.workflow = workflow;
      state.providers = providers;
      state.permissions = context.permissions || {};
      renderCatalog();
      hydrateWorkflow();
      applyPermissions();
      bindGlobalEvents();
      setTimeout(fitView, 80);
    } catch (error) {
      toast(`Não foi possível iniciar: ${error.message}`, "error");
    }
  }

  init();
})();
