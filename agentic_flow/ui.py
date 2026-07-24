from __future__ import annotations

from pyreact import h
from pyreact.server import render_to_static_markup


def Brand(_props):
    return h(
        "div",
        {"className": "brand"},
        h("div", {"className": "brand-mark"}, "A"),
        h(
            "div",
            None,
            h("strong", None, "Agentic"),
            h("span", None, "FLOW"),
        ),
    )


def IconButton(props):
    return h(
        "button",
        {
            "className": f"icon-button {props.get('className', '')}".strip(),
            "id": props.get("id"),
            "title": props.get("title", ""),
            "aria-label": props.get("title", ""),
        },
        props.get("label", ""),
    )


def Topbar(_props):
    return h(
        "header",
        {"className": "topbar"},
        h(Brand, None),
        h(
            "div",
            {"className": "workflow-heading"},
            h("a", {"className": "back-button", "href": "/dashboard", "title": "Voltar aos workflows"}, "‹"),
            h(
                "div",
                None,
                h("input", {"id": "workflow-name", "value": "Agente de pesquisa"}),
                h(
                    "div",
                    {"className": "save-state"},
                    h("span", {"className": "save-dot"}),
                    h("span", {"id": "save-label"}, "Salvo agora"),
                    h("span", {"className": "version-pill", "id": "version-label"}, "v1"),
                ),
            ),
        ),
        h(
            "nav",
            {"className": "top-actions"},
            h(IconButton, {"id": "undo-button", "label": "↶", "title": "Desfazer"}),
            h(IconButton, {"id": "redo-button", "label": "↷", "title": "Refazer"}),
            h("span", {"className": "top-separator"}),
            h(
                "button",
                {"className": "button secondary", "id": "save-button"},
                h("span", {"className": "button-icon"}, "◇"),
                "Salvar",
            ),
            h(
                "button",
                {"className": "button primary", "id": "run-button"},
                h("span", {"className": "play-icon"}, "▶"),
                "Executar",
            ),
            h(
                "button",
                {"className": "more-button", "id": "more-button", "aria-label": "Mais opções"},
                "•••",
            ),
        ),
    )


def Sidebar(_props):
    return h(
        "aside",
        {"className": "sidebar"},
        h(
            "div",
            {"className": "sidebar-title"},
            h("div", None, h("h2", None, "Nós"), h("p", None, "Arraste para o canvas")),
            h("button", {"className": "close-sidebar", "aria-label": "Fechar"}, "×"),
        ),
        h(
            "label",
            {"className": "search-box"},
            h("span", None, "⌕"),
            h("input", {"id": "node-search", "placeholder": "Buscar nós..."}),
            h("kbd", None, "/"),
        ),
        h("div", {"className": "catalog", "id": "node-catalog"}),
        h(
            "div",
            {"className": "sidebar-footer"},
            h("div", {"className": "tip-icon"}, "?"),
            h("span", None, "Arraste um nó e conecte pelas alças laterais."),
        ),
    )


def Canvas(_props):
    return h(
        "main",
        {"className": "workspace"},
        h(
            "div",
            {"className": "canvas-toolbar"},
            h(IconButton, {"id": "select-tool", "label": "↖", "title": "Selecionar", "className": "active"}),
            h(IconButton, {"id": "pan-tool", "label": "✥", "title": "Mover canvas"}),
            h("span", {"className": "toolbar-divider"}),
            h(IconButton, {"id": "auto-layout", "label": "⌘", "title": "Organizar automaticamente"}),
        ),
        h(
            "div",
            {"className": "canvas", "id": "canvas"},
            h("div", {"className": "canvas-grid"}),
            h(
                "div",
                {"className": "canvas-stage", "id": "canvas-stage"},
                h("svg", {"className": "edges-layer", "id": "edges-layer"}),
                h("div", {"className": "nodes-layer", "id": "nodes-layer"}),
            ),
            h(
                "div",
                {"className": "empty-canvas", "id": "empty-canvas"},
                h("div", {"className": "empty-icon"}, "+"),
                h("h3", None, "Comece seu agente"),
                h("p", None, "Arraste nós do painel ou escolha um template."),
            ),
        ),
        h(
            "div",
            {"className": "zoom-controls"},
            h(IconButton, {"id": "zoom-out", "label": "−", "title": "Diminuir zoom"}),
            h("button", {"id": "zoom-value", "className": "zoom-value"}, "100%"),
            h(IconButton, {"id": "zoom-in", "label": "+", "title": "Aumentar zoom"}),
            h(IconButton, {"id": "fit-view", "label": "⌗", "title": "Ajustar à tela"}),
        ),
        h(
            "div",
            {"className": "minimap", "id": "minimap"},
            h("div", {"className": "minimap-label"}, "MINIMAPA"),
            h("div", {"className": "minimap-content", "id": "minimap-content"}),
        ),
    )


def Inspector(_props):
    return h(
        "aside",
        {"className": "inspector", "id": "inspector"},
        h(
            "div",
            {"className": "inspector-empty", "id": "inspector-empty"},
            h("div", {"className": "inspector-empty-icon"}, "◇"),
            h("h3", None, "Selecione um nó"),
            h("p", None, "As configurações aparecerão aqui."),
        ),
        h(
            "div",
            {"className": "inspector-content hidden", "id": "inspector-content"},
            h(
                "div",
                {"className": "inspector-header"},
                h("div", {"className": "node-avatar", "id": "inspector-avatar"}, "AI"),
                h(
                    "div",
                    None,
                    h("span", {"className": "eyebrow"}, "CONFIGURAÇÃO DO NÓ"),
                    h("h2", {"id": "inspector-title"}, "Agente"),
                ),
                h("button", {"className": "delete-button", "id": "delete-node", "title": "Excluir nó"}, "⌫"),
            ),
            h("div", {"className": "inspector-form", "id": "inspector-form"}),
        ),
    )


def RunDrawer(_props):
    return h(
        "section",
        {"className": "run-drawer", "id": "run-drawer"},
        h(
            "div",
            {"className": "drawer-head"},
            h(
                "div",
                None,
                h("span", {"className": "drawer-kicker"}, "PLAYGROUND"),
                h("h2", None, "Executar workflow"),
            ),
            h("button", {"className": "drawer-close", "id": "drawer-close"}, "×"),
        ),
        h(
            "div",
            {"className": "drawer-body"},
            h(
                "div",
                {"className": "input-panel"},
                h("label", {"htmlFor": "run-input"}, "Entrada JSON"),
                h(
                    "textarea",
                    {"id": "run-input", "spellcheck": "false"},
                    '{\n  "message": "Crie um resumo sobre agentes autônomos"\n}',
                ),
                h(
                    "div",
                    {"className": "drawer-actions"},
                    h("span", {"id": "validation-label"}, "JSON válido"),
                    h(
                        "button",
                        {"className": "button primary", "id": "confirm-run"},
                        h("span", {"className": "play-icon"}, "▶"),
                        "Executar agora",
                    ),
                ),
            ),
            h(
                "div",
                {"className": "result-panel"},
                h(
                    "div",
                    {"className": "result-head"},
                    h("span", None, "Resultado"),
                    h("span", {"className": "run-status idle", "id": "run-status"}, "Aguardando"),
                ),
                h(
                    "div",
                    {"className": "result-placeholder", "id": "result-placeholder"},
                    h("div", None, "▶"),
                    h("p", None, "Execute o workflow para ver o resultado e o rastreamento."),
                ),
                h("div", {"className": "run-trace hidden", "id": "run-trace"}),
            ),
        ),
    )


def Toasts(_props):
    return h("div", {"className": "toast-region", "id": "toast-region", "aria-live": "polite"})


def App(props):
    return h(
        "div",
        {"className": "app-shell", "data-workflow-id": props.get("workflow_id", "")},
        h(Topbar, None),
        h("div", {"className": "body-shell"}, h(Sidebar, None), h(Canvas, None), h(Inspector, None)),
        h(RunDrawer, None),
        h(Toasts, None),
    )


def _document(body: str, title: str, scripts: list[str], body_class: str = "") -> str:
    script_tags = "\n".join(f'  <script src="{src}" defer></script>' for src in scripts)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#0c0c11">
  <title>{title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="/static/styles.css">
</head>
<body class="{body_class}">
  {body}
{script_tags}
</body>
</html>"""


def render_page(workflow_id: str) -> str:
    body = render_to_static_markup(h(App, {"workflow_id": workflow_id}))
    return _document(
        body,
        "Agentic Flow · Construtor de agentes",
        ["/static/app.js"],
    )


def AuthPage(props):
    setup = props.get("mode") == "setup"
    return h(
        "main",
        {"className": "auth-shell"},
        h(
            "section",
            {"className": "auth-visual"},
            h(Brand, None),
            h(
                "div",
                {"className": "auth-message"},
                h("span", {"className": "auth-kicker"}, "AGENTES QUE TRABALHAM JUNTOS"),
                h("h1", None, "Crie, conecte e coloque seus agentes em produção."),
                h(
                    "p",
                    None,
                    "Workflows visuais, gatilhos reais e execução rastreável em um só workspace.",
                ),
                h(
                    "div",
                    {"className": "auth-flow-preview"},
                    h("span", {"className": "preview-node orange"}, "Webhook"),
                    h("i", None, "→"),
                    h("span", {"className": "preview-node purple"}, "Pesquisador"),
                    h("i", None, "→"),
                    h("span", {"className": "preview-node pink"}, "Revisor"),
                ),
            ),
        ),
        h(
            "section",
            {"className": "auth-panel"},
            h(
                "div",
                {"className": "auth-card"},
                h("span", {"className": "auth-kicker"}, "PRIMEIRO ACESSO" if setup else "BEM-VINDO DE VOLTA"),
                h("h2", None, "Crie o administrador" if setup else "Entre na sua conta"),
                h(
                    "p",
                    None,
                    (
                        "Este usuário terá controle total do primeiro workspace."
                        if setup
                        else "Acesse seus workspaces e workflows."
                    ),
                ),
                h(
                    "form",
                    {"id": "auth-form", "data-mode": "setup" if setup else "login"},
                    *(
                        [
                            h(
                                "div",
                                {"className": "field"},
                                h("label", {"htmlFor": "name"}, "Seu nome"),
                                h("input", {"id": "name", "name": "name", "required": True, "autocomplete": "name"}),
                            ),
                            h(
                                "div",
                                {"className": "field"},
                                h("label", {"htmlFor": "workspace_name"}, "Nome do workspace"),
                                h(
                                    "input",
                                    {
                                        "id": "workspace_name",
                                        "name": "workspace_name",
                                        "required": True,
                                        "value": "Meu workspace",
                                    },
                                ),
                            ),
                        ]
                        if setup
                        else []
                    ),
                    h(
                        "div",
                        {"className": "field"},
                        h("label", {"htmlFor": "email"}, "E-mail"),
                        h(
                            "input",
                            {
                                "id": "email",
                                "name": "email",
                                "type": "email",
                                "required": True,
                                "autocomplete": "email",
                            },
                        ),
                    ),
                    h(
                        "div",
                        {"className": "field"},
                        h("label", {"htmlFor": "password"}, "Senha"),
                        h(
                            "input",
                            {
                                "id": "password",
                                "name": "password",
                                "type": "password",
                                "required": True,
                                "minlength": "8",
                                "autocomplete": "new-password" if setup else "current-password",
                            },
                        ),
                    ),
                    h("div", {"className": "auth-error hidden", "id": "auth-error"}),
                    h(
                        "button",
                        {"className": "button primary auth-submit", "type": "submit"},
                        "Criar conta e continuar" if setup else "Entrar",
                    ),
                ),
            ),
        ),
    )


def render_auth_page(mode: str) -> str:
    body = render_to_static_markup(h(AuthPage, {"mode": mode}))
    title = "Configuração inicial · Agentic Flow" if mode == "setup" else "Login · Agentic Flow"
    return _document(body, title, ["/static/auth.js"], "auth-body")


def Dashboard(props):
    workflows = props.get("workflows", [])
    user = props["user"]
    workspace = props["workspace"]
    return h(
        "div",
        {"className": "dashboard-shell"},
        h(
            "header",
            {"className": "dashboard-topbar"},
            h(Brand, None),
            h(
                "div",
                {"className": "workspace-switcher"},
                h("span", {"className": "workspace-avatar"}, workspace["name"][:1].upper()),
                h("div", None, h("small", None, "WORKSPACE"), h("strong", None, workspace["name"])),
            ),
            h(
                "div",
                {"className": "user-menu"},
                *(
                    [
                        h(
                            "a",
                            {
                                "className": "icon-button settings-link",
                                "href": "/settings/providers",
                                "title": "Provedores de IA",
                            },
                            "⚙",
                        )
                    ]
                    if user.get("role") == "admin"
                    else []
                ),
                h("span", {"className": "user-avatar"}, user["name"][:1].upper()),
                h("div", None, h("strong", None, user["name"]), h("small", None, user["email"])),
                h("button", {"id": "logout-button", "className": "icon-button", "title": "Sair"}, "↪"),
            ),
        ),
        h(
            "main",
            {"className": "dashboard-main"},
            h(
                "section",
                {"className": "dashboard-heading"},
                h(
                    "div",
                    None,
                    h("span", {"className": "auth-kicker"}, "AUTOMAÇÕES"),
                    h("h1", None, "Workflows"),
                    h("p", None, "Crie e gerencie suas equipes de agentes."),
                ),
                h(
                    "button",
                    {"className": "button primary", "id": "new-workflow-button"},
                    h("span", None, "+"),
                    "Novo workflow",
                ),
            ),
            h(
                "section",
                {"className": "workflow-grid", "id": "workflow-grid"},
                *[
                    h(
                        "a",
                        {"className": "workflow-card", "href": f"/workflows/{workflow.id}"},
                        h(
                            "div",
                            {"className": "workflow-card-head"},
                            h("span", {"className": "workflow-card-icon"}, "⌘"),
                            h("span", {"className": "version-pill"}, f"v{workflow.version}"),
                        ),
                        h("h2", None, workflow.name),
                        h(
                            "p",
                            None,
                            workflow.description or "Workflow de agentes sem descrição.",
                        ),
                        h(
                            "div",
                            {"className": "workflow-meta"},
                            h("span", None, f"{len(workflow.nodes)} nós"),
                            h("span", None, f"{len(workflow.edges)} conexões"),
                        ),
                    )
                    for workflow in workflows
                ],
                h(
                    "button",
                    {"className": "workflow-card new-card", "id": "new-workflow-card"},
                    h("span", {"className": "new-card-plus"}, "+"),
                    h("strong", None, "Criar workflow"),
                    h("small", None, "Comece com um canvas vazio"),
                ),
            ),
        ),
        h(
            "div",
            {"className": "modal-backdrop hidden", "id": "workflow-modal"},
            h(
                "form",
                {"className": "workflow-modal", "id": "workflow-form"},
                h("button", {"type": "button", "className": "modal-close", "id": "modal-close"}, "×"),
                h("span", {"className": "auth-kicker"}, "NOVO WORKFLOW"),
                h("h2", None, "O que vamos automatizar?"),
                h(
                    "div",
                    {"className": "field"},
                    h("label", {"htmlFor": "new-workflow-name"}, "Nome"),
                    h(
                        "input",
                        {
                            "id": "new-workflow-name",
                            "required": True,
                            "placeholder": "Ex.: Atendimento inteligente",
                        },
                    ),
                ),
                h(
                    "div",
                    {"className": "field"},
                    h("label", {"htmlFor": "new-workflow-description"}, "Descrição"),
                    h(
                        "textarea",
                        {
                            "id": "new-workflow-description",
                            "placeholder": "Descreva brevemente o objetivo...",
                        },
                    ),
                ),
                h("div", {"className": "auth-error hidden", "id": "workflow-error"}),
                h("button", {"className": "button primary auth-submit", "type": "submit"}, "Criar workflow"),
            ),
        ),
    )


def render_dashboard(
    workflows: list, user: dict[str, object], workspace: dict[str, str]
) -> str:
    body = render_to_static_markup(
        h(Dashboard, {"workflows": workflows, "user": user, "workspace": workspace})
    )
    return _document(body, "Workflows · Agentic Flow", ["/static/dashboard.js"])


def ProvidersPage(props):
    providers = props.get("providers", [])
    provider_types = props.get("provider_types", [])
    user = props["user"]
    workspace = props["workspace"]
    return h(
        "div",
        {"className": "dashboard-shell providers-shell"},
        h(
            "header",
            {"className": "dashboard-topbar"},
            h(Brand, None),
            h(
                "div",
                {"className": "workspace-switcher"},
                h("span", {"className": "workspace-avatar"}, workspace["name"][:1].upper()),
                h("div", None, h("small", None, "WORKSPACE"), h("strong", None, workspace["name"])),
            ),
            h(
                "div",
                {"className": "user-menu"},
                h("a", {"className": "button secondary", "href": "/dashboard"}, "← Workflows"),
                h("span", {"className": "user-avatar"}, user["name"][:1].upper()),
            ),
        ),
        h(
            "main",
            {"className": "dashboard-main"},
            h(
                "section",
                {"className": "dashboard-heading"},
                h(
                    "div",
                    None,
                    h("span", {"className": "auth-kicker"}, "CONFIGURAÇÕES"),
                    h("h1", None, "Provedores de IA"),
                    h(
                        "p",
                        None,
                        "Cadastre modelos e credenciais uma vez para todo o workspace.",
                    ),
                ),
                h(
                    "button",
                    {"className": "button primary", "id": "new-provider-button"},
                    h("span", None, "+"),
                    "Adicionar provedor",
                ),
            ),
            h(
                "div",
                {"className": "security-banner"},
                h("span", {"className": "security-icon"}, "◆"),
                h(
                    "div",
                    None,
                    h("strong", None, "Credenciais protegidas"),
                    h(
                        "p",
                        None,
                        "As API keys são criptografadas antes de chegar ao banco e nunca são devolvidas ao navegador.",
                    ),
                ),
            ),
            h(
                "section",
                {"className": "provider-grid", "id": "provider-grid"},
                *[
                    h(
                        "article",
                        {"className": "provider-card", "data-provider-id": provider["id"]},
                        h(
                            "div",
                            {"className": "provider-card-head"},
                            h("span", {"className": "provider-logo"}, provider["name"][:2].upper()),
                            h(
                                "span",
                                {
                                    "className": "provider-status active"
                                    if provider["enabled"]
                                    else "provider-status",
                                },
                                "Ativo" if provider["enabled"] else "Inativo",
                            ),
                        ),
                        h("h2", None, provider["name"]),
                        h("p", None, provider["type"].replace("_", " ").title()),
                        h("code", None, provider["base_url"]),
                        h(
                            "div",
                            {"className": "provider-card-actions"},
                            h("span", None, "● Chave salva" if provider["has_api_key"] else "○ Sem chave"),
                            h("button", {"className": "provider-edit", "data-edit-provider": provider["id"]}, "Editar"),
                        ),
                    )
                    for provider in providers
                ],
                h(
                    "button",
                    {"className": "provider-card provider-new-card", "id": "new-provider-card"},
                    h("span", {"className": "new-card-plus"}, "+"),
                    h("strong", None, "Conectar provedor"),
                    h("small", None, "OpenAI, Anthropic, Ollama e compatíveis"),
                ),
            ),
        ),
        h(
            "div",
            {"className": "modal-backdrop hidden", "id": "provider-modal"},
            h(
                "form",
                {"className": "workflow-modal provider-modal", "id": "provider-form"},
                h("button", {"type": "button", "className": "modal-close", "id": "provider-modal-close"}, "×"),
                h("span", {"className": "auth-kicker"}, "PROVEDOR DE IA"),
                h("h2", {"id": "provider-modal-title"}, "Adicionar provedor"),
                h("input", {"type": "hidden", "id": "provider-id"}),
                h(
                    "div",
                    {"className": "field"},
                    h("label", {"htmlFor": "provider-type"}, "Tipo"),
                    h(
                        "select",
                        {"id": "provider-type", "required": True},
                        *[
                            h("option", {"value": item["type"]}, item["name"])
                            for item in provider_types
                        ],
                    ),
                    h("small", {"className": "field-help", "id": "provider-type-help"}),
                ),
                h(
                    "div",
                    {"className": "field"},
                    h("label", {"htmlFor": "provider-name"}, "Nome visível"),
                    h("input", {"id": "provider-name", "required": True}),
                ),
                h(
                    "div",
                    {"className": "field"},
                    h("label", {"htmlFor": "provider-base-url"}, "URL base"),
                    h("input", {"id": "provider-base-url", "required": True}),
                ),
                h(
                    "div",
                    {"className": "field"},
                    h("label", {"htmlFor": "provider-model"}, "Modelo padrão"),
                    h("input", {"id": "provider-model"}),
                ),
                h(
                    "div",
                    {"className": "field"},
                    h("label", {"htmlFor": "provider-api-key"}, "API key"),
                    h(
                        "input",
                        {
                            "id": "provider-api-key",
                            "type": "password",
                            "autocomplete": "new-password",
                            "placeholder": "Cole a chave aqui",
                        },
                    ),
                    h(
                        "small",
                        {"className": "field-help"},
                        "Ao editar, deixe em branco para manter a chave atual.",
                    ),
                ),
                h(
                    "label",
                    {"className": "toggle-field"},
                    h("input", {"id": "provider-enabled", "type": "checkbox", "checked": True}),
                    h("span", None),
                    "Provedor ativo",
                ),
                h("div", {"className": "auth-error hidden", "id": "provider-error"}),
                h(
                    "div",
                    {"className": "provider-form-actions"},
                    h(
                        "button",
                        {"type": "button", "className": "button danger hidden", "id": "delete-provider"},
                        "Excluir",
                    ),
                    h("span", None),
                    h(
                        "button",
                        {"type": "button", "className": "button secondary hidden", "id": "test-provider"},
                        "Testar conexão",
                    ),
                    h("button", {"className": "button primary", "type": "submit"}, "Salvar"),
                ),
            ),
        ),
    )


def render_providers_page(
    providers: list[dict],
    provider_types: list[dict],
    user: dict[str, object],
    workspace: dict[str, str],
) -> str:
    body = render_to_static_markup(
        h(
            ProvidersPage,
            {
                "providers": providers,
                "provider_types": provider_types,
                "user": user,
                "workspace": workspace,
            },
        )
    )
    return _document(
        body,
        "Provedores de IA · Agentic Flow",
        ["/static/providers.js"],
    )
