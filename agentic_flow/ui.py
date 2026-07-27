from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from pyreact import h
from pyreact.server import render_to_static_markup
from sixcons import icon as six_icon
from uikitpr import (
    Badge,
    Button as UIButton,
    IconButton as UIIconButton,
    UIProvider,
    stylesheet as uikit_stylesheet,
)


def Icon(name: str, size: int = 18, class_name: str = "", label: str | None = None):
    """Render a consistent, accessible 6cons icon."""
    return six_icon(
        name,
        size=size,
        stroke_width=1.8,
        class_name=class_name,
        label=label,
    )


def Brand(_props):
    return h(
        "div",
        {"className": "brand"},
        h("div", {"className": "brand-mark"}, Icon("sparkles", 19)),
        h(
            "div",
            None,
            h("strong", None, "Agentic"),
            h("span", None, "FLOW"),
        ),
    )


def WorkspaceSwitcher(props):
    workspace = props["workspace"]
    workspaces = props.get("workspaces", [workspace])
    return h(
        "details",
        {"className": "workspace-menu", "id": "workspace-menu"},
        h(
            "summary",
            {"className": "workspace-trigger", "title": "Trocar workspace"},
            h("span", {"className": "workspace-avatar"}, workspace["name"][:1].upper()),
            h(
                "span",
                {"className": "workspace-trigger-copy"},
                h("small", None, "WORKSPACE ATIVO"),
                h("strong", None, workspace["name"]),
            ),
            h("span", {"className": "workspace-chevron"}, Icon("chevron-down", 15)),
        ),
        h(
            "div",
            {"className": "workspace-popover"},
            h(
                "div",
                {"className": "workspace-popover-head"},
                h("strong", None, "Seus workspaces"),
                h("small", None, f"{len(workspaces)} disponível(is)"),
            ),
            h(
                "div",
                {"className": "workspace-options"},
                *[
                    h(
                        "button",
                        {
                            "type": "button",
                            "className": "workspace-option active"
                            if item["id"] == workspace["id"]
                            else "workspace-option",
                            "data-workspace-id": item["id"],
                        },
                        h("span", {"className": "workspace-option-avatar"}, item["name"][:1].upper()),
                        h(
                            "span",
                            None,
                            h("strong", None, item["name"]),
                            h(
                                "small",
                                None,
                                "Workspace atual"
                                if item["id"] == workspace["id"]
                                else "Abrir workspace",
                            ),
                        ),
                        h(
                            "span",
                            {"className": "workspace-option-check"},
                            Icon("check" if item["id"] == workspace["id"] else "arrow-right", 15),
                        ),
                    )
                    for item in workspaces
                ],
            ),
        ),
    )


def IconButton(props):
    content = (
        Icon(props["icon"], props.get("size", 17))
        if props.get("icon")
        else props.get("label", "")
    )
    return UIIconButton(
        content,
        variant="ghost",
        size="sm",
        class_name=f"icon-button {props.get('className', '')}".strip(),
        id=props.get("id"),
        title=props.get("title", ""),
        **{"aria-label": props.get("title", "")},
    )


def Topbar(_props):
    return h(
        "header",
        {"className": "topbar"},
        h(Brand, None),
        h(
            "div",
            {"className": "workflow-heading"},
            h(
                "a",
                {"className": "back-button", "href": "/dashboard", "title": "Voltar aos workflows"},
                Icon("arrow-left", 18),
            ),
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
            h(IconButton, {"id": "undo-button", "icon": "undo-2", "title": "Desfazer"}),
            h(IconButton, {"id": "redo-button", "icon": "redo-2", "title": "Refazer"}),
            h("span", {"className": "top-separator"}),
            UIButton(
                Icon("save", 16),
                "Salvar",
                variant="outline",
                size="sm",
                class_name="button secondary",
                id="save-button",
            ),
            UIButton(
                Icon("play", 16),
                "Executar",
                variant="primary",
                size="sm",
                class_name="button primary",
                id="run-button",
            ),
            h(IconButton, {"id": "more-button", "icon": "ellipsis", "title": "Mais opções", "className": "more-button"}),
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
            h("button", {"className": "close-sidebar", "aria-label": "Fechar"}, Icon("x", 18)),
        ),
        h(
            "label",
            {"className": "search-box"},
            h("span", None, Icon("search", 16)),
            h("input", {"id": "node-search", "placeholder": "Buscar nós..."}),
            h("kbd", None, "/"),
        ),
        h("div", {"className": "catalog", "id": "node-catalog"}),
        h(
            "div",
            {"className": "sidebar-footer"},
            h("div", {"className": "tip-icon"}, Icon("circle-question-mark", 15)),
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
            h(IconButton, {"id": "select-tool", "icon": "mouse-pointer-2", "title": "Selecionar", "className": "active"}),
            h(IconButton, {"id": "pan-tool", "icon": "hand", "title": "Mover canvas"}),
            h("span", {"className": "toolbar-divider"}),
            h(IconButton, {"id": "auto-layout", "icon": "wand-sparkles", "title": "Organizar automaticamente"}),
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
                h("div", {"className": "empty-icon"}, Icon("workflow", 30)),
                h("h3", None, "Comece seu agente"),
                h("p", None, "Arraste nós do painel ou escolha um template."),
            ),
        ),
        h(
            "div",
            {"className": "zoom-controls"},
            h(IconButton, {"id": "zoom-out", "icon": "zoom-out", "title": "Diminuir zoom"}),
            h("button", {"id": "zoom-value", "className": "zoom-value"}, "100%"),
            h(IconButton, {"id": "zoom-in", "icon": "zoom-in", "title": "Aumentar zoom"}),
            h(IconButton, {"id": "fit-view", "icon": "scan", "title": "Ajustar à tela"}),
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
            h("div", {"className": "inspector-empty-icon"}, Icon("panels-top-left", 27)),
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
                h("button", {"className": "delete-button", "id": "delete-node", "title": "Excluir nó"}, Icon("trash-2", 17)),
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
            h("button", {"className": "drawer-close", "id": "drawer-close", "aria-label": "Fechar"}, Icon("x", 19)),
        ),
        h(
            "div",
            {"className": "drawer-body"},
            h(
                "div",
                {"className": "input-panel"},
                h("div", {"className": "typed-run-inputs", "id": "typed-run-inputs"}),
                h(
                    "details",
                    {"className": "advanced-run-input", "id": "advanced-run-input"},
                    h("summary", None, "Entrada JSON e campos avançados"),
                    h("label", {"htmlFor": "run-input"}, "Entrada JSON"),
                    h(
                        "textarea",
                        {"id": "run-input", "spellcheck": "false"},
                        '{\n  "message": "Crie um resumo sobre agentes autônomos"\n}',
                    ),
                    h(
                        "div",
                        {"className": "asset-input-row"},
                        h(
                            "input",
                            {
                                "id": "asset-field",
                                "value": "file",
                                "placeholder": "campo",
                                "title": "Campo JSON que receberá o arquivo",
                            },
                        ),
                        h(
                            "label",
                            {"className": "button secondary asset-picker", "htmlFor": "asset-file"},
                            "Anexar arquivo",
                        ),
                        h(
                            "input",
                            {
                                "id": "asset-file",
                                "className": "hidden",
                                "type": "file",
                                "accept": ".pdf,.txt,.md,.markdown,.csv,.json,.xml,.html,.yaml,.yml,.docx,.xlsx,image/*,video/*",
                            },
                        ),
                        h("span", {"id": "asset-file-label"}, "PDF, texto, imagem ou vídeo"),
                    ),
                ),
                h(
                    "div",
                    {"className": "drawer-actions"},
                    h("span", {"id": "validation-label"}, "JSON válido"),
                    h(
                        "button",
                        {"className": "button primary", "id": "confirm-run"},
                        Icon("play", 16),
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
                    h("div", None, Icon("play", 23)),
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


def _versioned_asset(source: str) -> str:
    if not source.startswith("/static/"):
        return source
    path = Path(__file__).resolve().parent / "static" / source.removeprefix(
        "/static/"
    )
    try:
        digest = sha256(path.read_bytes()).hexdigest()[:10]
    except OSError:
        return source
    return f"{source}?v={digest}"


def _render_ui(node) -> str:
    return render_to_static_markup(
        UIProvider(
            node,
            theme="dark",
            color_mode="dark",
            with_styles=False,
            with_motion=False,
            full_height=True,
            class_name="agenticflow-ui",
        )
    )


def _document(body: str, title: str, scripts: list[str], body_class: str = "") -> str:
    script_tags = "\n".join(
        f'  <script src="{_versioned_asset(src)}" defer></script>'
        for src in scripts
    )
    stylesheet = _versioned_asset("/static/styles.css")
    design_system = uikit_stylesheet(minified=True)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#0e1220">
  <title>{title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Manrope:wght@600;700&display=swap" rel="stylesheet">
  <style data-uikitpr="core">{design_system}</style>
  <link rel="stylesheet" href="{stylesheet}">
</head>
<body class="{body_class}">
  {body}
{script_tags}
</body>
</html>"""


def render_page(workflow_id: str) -> str:
    body = _render_ui(h(App, {"workflow_id": workflow_id}))
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
                    h("i", None, Icon("arrow-right", 18)),
                    h("span", {"className": "preview-node purple"}, "Pesquisador"),
                    h("i", None, Icon("arrow-right", 18)),
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
    body = _render_ui(h(AuthPage, {"mode": mode}))
    title = "Configuração inicial · Agentic Flow" if mode == "setup" else "Login · Agentic Flow"
    return _document(body, title, ["/static/auth.js"], "auth-body")


def Dashboard(props):
    workflows = props.get("workflows", [])
    user = props["user"]
    workspace = props["workspace"]
    workspaces = props.get("workspaces", [workspace])
    permissions = props.get("permissions", {})
    can_create = permissions.get("create_workflows", False)
    can_edit = permissions.get("edit_workflows", False)
    return h(
        "div",
        {"className": "dashboard-shell"},
        h(
            "header",
            {"className": "dashboard-topbar"},
            h(Brand, None),
            h(WorkspaceSwitcher, {"workspace": workspace, "workspaces": workspaces}),
            h(
                "div",
                {"className": "user-menu"},
                *([
                    h(
                        "a",
                        {
                            "className": "icon-button settings-link",
                            "href": "/settings/access",
                            "title": "Usuários, times e políticas",
                        },
                            Icon("users-round", 17),
                    )
                ] if permissions.get("manage_teams") else []),
                *(
                    [
                        h(
                            "a",
                            {
                                "className": "icon-button settings-link",
                                "href": "/settings/databases",
                                "title": "Bancos de dados",
                            },
                            Icon("database", 17),
                        )
                    ]
                    if permissions.get("manage_databases")
                    else []
                ),
                *(
                    [
                        h(
                            "a",
                            {
                                "className": "icon-button settings-link",
                                "href": "/settings/providers",
                                "title": "Provedores de IA",
                            },
                            Icon("settings-2", 17),
                        )
                    ]
                    if permissions.get("manage_providers")
                    else []
                ),
                h("span", {"className": "user-avatar"}, user["name"][:1].upper()),
                h("div", None, h("strong", None, user["name"]), h("small", None, user["email"])),
                h(
                    "button",
                    {"id": "logout-button", "className": "icon-button", "title": "Sair", "aria-label": "Sair"},
                    Icon("log-out", 17),
                ),
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
                *(
                    [
                        h(
                            "div",
                            {"className": "dashboard-heading-actions"},
                            h(
                                "button",
                                {"className": "button secondary", "id": "template-library-button"},
                                Icon("layout-template", 17),
                                "Usar template",
                            ),
                            h(
                                "button",
                                {"className": "button primary", "id": "new-workflow-button"},
                                Icon("plus", 17),
                                "Novo workflow",
                            ),
                        )
                    ]
                    if can_create
                    else []
                ),
            ),
            h(
                "section",
                {"className": "workflow-grid", "id": "workflow-grid"},
                *[
                    h(
                        "article",
                        {
                            "className": "workflow-card",
                            "data-workflow-card": workflow.id,
                        },
                        h(
                            "a",
                            {
                                "className": "workflow-card-link",
                                "href": f"/workflows/{workflow.id}",
                            },
                            h(
                                "div",
                                {"className": "workflow-card-head"},
                                h("span", {"className": "workflow-card-icon"}, Icon("workflow", 20)),
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
                        ),
                        *(
                            [
                                h(
                                    "button",
                                    {
                                        "className": "workflow-delete-button",
                                        "type": "button",
                                        "title": f"Excluir {workflow.name}",
                                        "aria-label": f"Excluir workflow {workflow.name}",
                                        "data-delete-workflow": workflow.id,
                                        "data-workflow-name": workflow.name,
                                    },
                                    Icon("trash-2", 15),
                                )
                            ]
                            if can_edit
                            else []
                        ),
                    )
                    for workflow in workflows
                ],
                *(
                    [
                        h(
                            "div",
                            {"className": "workflow-empty-state"},
                            "Nenhum workflow neste workspace.",
                        )
                    ]
                    if not workflows and not can_create
                    else []
                ),
                *(
                    [
                        h(
                            "button",
                            {"className": "workflow-card new-card", "id": "new-workflow-card"},
                            h("span", {"className": "new-card-plus"}, Icon("plus", 24)),
                            h("strong", None, "Criar workflow"),
                            h("small", None, "Comece com um canvas vazio"),
                        )
                    ]
                    if can_create
                    else []
                ),
            ),
        ),
        *(
            [
                h(
                    "div",
                    {"className": "modal-backdrop hidden", "id": "delete-workflow-modal"},
                    h(
                        "section",
                        {
                            "className": "workflow-modal delete-workflow-dialog",
                            "role": "dialog",
                            "aria-modal": "true",
                            "aria-labelledby": "delete-workflow-title",
                        },
                        h("span", {"className": "delete-dialog-icon"}, Icon("trash-2", 23)),
                        h("span", {"className": "auth-kicker"}, "EXCLUIR WORKFLOW"),
                        h("h2", {"id": "delete-workflow-title"}, "Excluir este workflow?"),
                        h(
                            "p",
                            None,
                            "O workflow ",
                            h("strong", {"id": "delete-workflow-name"}, ""),
                            " e seu histórico de execuções serão removidos permanentemente.",
                        ),
                        h(
                            "div",
                            {"className": "auth-error hidden", "id": "delete-workflow-error"},
                        ),
                        h(
                            "div",
                            {"className": "delete-dialog-actions"},
                            h(
                                "button",
                                {
                                    "className": "button secondary",
                                    "type": "button",
                                    "id": "cancel-delete-workflow",
                                },
                                "Cancelar",
                            ),
                            h(
                                "button",
                                {
                                    "className": "button danger",
                                    "type": "button",
                                    "id": "confirm-delete-workflow",
                                },
                                "Excluir workflow",
                            ),
                        ),
                    ),
                )
            ]
            if can_edit
            else []
        ),
        h(
            "div",
            {"className": "modal-backdrop hidden", "id": "workflow-modal"},
            h(
                "form",
                {"className": "workflow-modal", "id": "workflow-form"},
                h(
                    "button",
                    {"type": "button", "className": "modal-close", "id": "modal-close", "aria-label": "Fechar"},
                    Icon("x", 18),
                ),
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
        *(
            [
                h(
                    "div",
                    {"className": "modal-backdrop hidden", "id": "template-modal"},
                    h(
                        "section",
                        {"className": "template-library-modal"},
                        h(
                            "header",
                            {"className": "template-library-head"},
                            h(
                                "div",
                                None,
                                h("span", {"className": "auth-kicker"}, "BIBLIOTECA"),
                                h("h2", None, "Comece com um workflow pronto"),
                                h(
                                    "p",
                                    None,
                                    "Escolha uma base, personalize os nós e publique mais rápido.",
                                ),
                            ),
                            h(
                                "button",
                                {
                                    "type": "button",
                                    "className": "modal-close",
                                    "id": "template-modal-close",
                                },
                                Icon("x", 18),
                            ),
                        ),
                        h(
                            "div",
                            {"className": "template-library-toolbar"},
                            h(
                                "div",
                                {"className": "search-box template-search"},
                                h("span", None, Icon("search", 16)),
                                h(
                                    "input",
                                    {
                                        "id": "template-search",
                                        "placeholder": "Buscar templates...",
                                    },
                                ),
                            ),
                            h(
                                "div",
                                {"className": "template-filters", "id": "template-filters"},
                            ),
                        ),
                        h(
                            "div",
                            {"className": "template-grid", "id": "template-grid"},
                            h(
                                "div",
                                {"className": "template-loading"},
                                "Carregando biblioteca...",
                            ),
                        ),
                    ),
                )
            ]
            if can_create
            else []
        ),
    )


def render_dashboard(
    workflows: list,
    user: dict[str, object],
    workspace: dict[str, str],
    workspaces: list[dict] | None = None,
    permissions: dict | None = None,
) -> str:
    body = _render_ui(
        h(
            Dashboard,
            {
                "workflows": workflows,
                "user": user,
                "workspace": workspace,
                "workspaces": workspaces or [workspace],
                "permissions": permissions or {},
            },
        )
    )
    return _document(
        body,
        "Workflows · Agentic Flow",
        ["/static/workspace.js", "/static/dashboard.js"],
    )


def ProvidersPage(props):
    providers = props.get("providers", [])
    provider_types = props.get("provider_types", [])
    user = props["user"]
    workspace = props["workspace"]
    workspaces = props.get("workspaces", [workspace])
    return h(
        "div",
        {"className": "dashboard-shell providers-shell"},
        h(
            "header",
            {"className": "dashboard-topbar"},
            h(Brand, None),
            h(WorkspaceSwitcher, {"workspace": workspace, "workspaces": workspaces}),
            h(
                "div",
                {"className": "user-menu"},
                h(
                    "a",
                    {"className": "button secondary", "href": "/dashboard"},
                    Icon("arrow-left", 16),
                    "Workflows",
                ),
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
                    Icon("plus", 17),
                    "Adicionar provedor",
                ),
            ),
            h(
                "div",
                {"className": "security-banner"},
                h("span", {"className": "security-icon"}, Icon("shield-check", 21)),
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
                            Badge(
                                "Ativo" if provider["enabled"] else "Inativo",
                                tone="success" if provider["enabled"] else "neutral",
                                pill=True,
                                class_name="provider-status active"
                                if provider["enabled"]
                                else "provider-status",
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
                    h("span", {"className": "new-card-plus"}, Icon("plus", 24)),
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
                h(
                    "button",
                    {
                        "type": "button",
                        "className": "modal-close",
                        "id": "provider-modal-close",
                        "aria-label": "Fechar",
                    },
                    Icon("x", 18),
                ),
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
    workspaces: list[dict] | None = None,
) -> str:
    body = _render_ui(
        h(
            ProvidersPage,
            {
                "providers": providers,
                "provider_types": provider_types,
                "user": user,
                "workspace": workspace,
                "workspaces": workspaces or [workspace],
            },
        )
    )
    return _document(
        body,
        "Provedores de IA · Agentic Flow",
        ["/static/workspace.js", "/static/providers.js"],
    )


def DatabasesPage(props):
    connections = props.get("connections", [])
    database_types = props.get("database_types", [])
    user = props["user"]
    workspace = props["workspace"]
    workspaces = props.get("workspaces", [workspace])
    return h(
        "div",
        {"className": "dashboard-shell providers-shell databases-shell"},
        h(
            "header",
            {"className": "dashboard-topbar"},
            h(Brand, None),
            h(WorkspaceSwitcher, {"workspace": workspace, "workspaces": workspaces}),
            h(
                "div",
                {"className": "user-menu"},
                h(
                    "a",
                    {"className": "button secondary", "href": "/settings/providers"},
                    "Provedores de IA",
                ),
                h(
                    "a",
                    {"className": "button secondary", "href": "/dashboard"},
                    Icon("arrow-left", 16),
                    "Workflows",
                ),
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
                    h("span", {"className": "auth-kicker"}, "DADOS DO WORKSPACE"),
                    h("h1", None, "Conexões de bancos"),
                    h(
                        "p",
                        None,
                        "Centralize conexões seguras para agentes analisarem schemas e dados.",
                    ),
                ),
                h(
                    "button",
                    {"className": "button primary", "id": "new-database-button"},
                    Icon("plus", 17),
                    "Adicionar banco",
                ),
            ),
            h(
                "div",
                {"className": "security-banner"},
                h("span", {"className": "security-icon"}, Icon("database", 21)),
                h(
                    "div",
                    None,
                    h("strong", None, "Acesso somente leitura"),
                    h(
                        "p",
                        None,
                        "Senhas e credenciais são criptografadas. Os nós bloqueiam comandos de escrita e limitam o volume retornado.",
                    ),
                ),
            ),
            h(
                "section",
                {"className": "provider-grid", "id": "database-grid"},
                *[
                    h(
                        "article",
                        {
                            "className": "provider-card database-card",
                            "data-database-id": connection["id"],
                        },
                        h(
                            "div",
                            {"className": "provider-card-head"},
                            h(
                                "span",
                                {"className": "provider-logo database-logo"},
                                connection["type"][:2].upper(),
                            ),
                            Badge(
                                "Ativo" if connection["enabled"] else "Inativo",
                                tone="success" if connection["enabled"] else "neutral",
                                pill=True,
                                class_name="provider-status active"
                                if connection["enabled"]
                                else "provider-status",
                            ),
                        ),
                        h("h2", None, connection["name"]),
                        h("p", None, connection["type"].replace("_", " ").title()),
                        h(
                            "code",
                            None,
                            connection["database_name"]
                            if connection["type"] in {"sqlite", "bigquery"}
                            else f"{connection['host']}:{connection.get('port') or ''}/{connection['database_name']}",
                        ),
                        h(
                            "div",
                            {"className": "provider-card-actions"},
                            h(
                                "span",
                                None,
                                "● Credencial protegida"
                                if connection["has_secret"]
                                else "○ Sem credencial",
                            ),
                            h(
                                "button",
                                {
                                    "className": "provider-edit",
                                    "data-edit-database": connection["id"],
                                },
                                "Editar",
                            ),
                        ),
                    )
                    for connection in connections
                ],
                h(
                    "button",
                    {
                        "className": "provider-card provider-new-card",
                        "id": "new-database-card",
                    },
                    h("span", {"className": "new-card-plus"}, Icon("plus", 24)),
                    h("strong", None, "Conectar banco"),
                    h(
                        "small",
                        None,
                        "MySQL, PostgreSQL, SQL Server, SQLite, BigQuery e MariaDB",
                    ),
                ),
            ),
        ),
        h(
            "div",
            {"className": "modal-backdrop hidden", "id": "database-modal"},
            h(
                "form",
                {
                    "className": "workflow-modal provider-modal database-modal",
                    "id": "database-form",
                },
                h(
                    "button",
                    {
                        "type": "button",
                        "className": "modal-close",
                        "id": "database-modal-close",
                        "aria-label": "Fechar",
                    },
                    Icon("x", 18),
                ),
                h("span", {"className": "auth-kicker"}, "BANCO DO WORKSPACE"),
                h("h2", {"id": "database-modal-title"}, "Adicionar banco"),
                h("input", {"type": "hidden", "id": "database-id"}),
                h(
                    "div",
                    {"className": "database-form-grid"},
                    h(
                        "div",
                        {"className": "field"},
                        h("label", {"htmlFor": "database-type"}, "Tipo"),
                        h(
                            "select",
                            {"id": "database-type", "required": True},
                            *[
                                h(
                                    "option",
                                    {"value": item["type"]},
                                    item["name"],
                                )
                                for item in database_types
                            ],
                        ),
                        h(
                            "small",
                            {"className": "field-help", "id": "database-type-help"},
                        ),
                    ),
                    h(
                        "div",
                        {"className": "field"},
                        h("label", {"htmlFor": "database-name"}, "Nome visível"),
                        h("input", {"id": "database-name", "required": True}),
                    ),
                    h(
                        "div",
                        {"className": "field", "id": "database-host-field"},
                        h("label", {"htmlFor": "database-host"}, "Host"),
                        h("input", {"id": "database-host"}),
                    ),
                    h(
                        "div",
                        {"className": "field", "id": "database-port-field"},
                        h("label", {"htmlFor": "database-port"}, "Porta"),
                        h("input", {"id": "database-port", "type": "number"}),
                    ),
                    h(
                        "div",
                        {"className": "field", "id": "database-database-field"},
                        h(
                            "label",
                            {"htmlFor": "database-database"},
                            "Database",
                        ),
                        h(
                            "input",
                            {"id": "database-database", "required": True},
                        ),
                        h(
                            "small",
                            {
                                "className": "field-help",
                                "id": "database-database-help",
                            },
                        ),
                    ),
                    h(
                        "div",
                        {"className": "field", "id": "database-username-field"},
                        h("label", {"htmlFor": "database-username"}, "Usuário"),
                        h("input", {"id": "database-username"}),
                    ),
                    h(
                        "div",
                        {"className": "field database-secret-field"},
                        h(
                            "label",
                            {"htmlFor": "database-secret", "id": "database-secret-label"},
                            "Senha",
                        ),
                        h(
                            "textarea",
                            {
                                "id": "database-secret",
                                "rows": 3,
                                "autocomplete": "new-password",
                            },
                        ),
                        h(
                            "small",
                            {"className": "field-help"},
                            "Ao editar, deixe em branco para manter a credencial atual.",
                        ),
                    ),
                    h(
                        "div",
                        {
                            "className": "field hidden",
                            "id": "database-dataset-field",
                        },
                        h("label", {"htmlFor": "database-dataset"}, "Dataset"),
                        h("input", {"id": "database-dataset"}),
                    ),
                ),
                h(
                    "label",
                    {"className": "toggle-field"},
                    h(
                        "input",
                        {
                            "id": "database-enabled",
                            "type": "checkbox",
                            "checked": True,
                        },
                    ),
                    h("span", None),
                    "Conexão ativa",
                ),
                h("div", {"className": "auth-error hidden", "id": "database-error"}),
                h(
                    "div",
                    {"className": "provider-form-actions"},
                    h(
                        "button",
                        {
                            "type": "button",
                            "className": "button danger hidden",
                            "id": "delete-database",
                        },
                        "Excluir",
                    ),
                    h("span", None),
                    h(
                        "button",
                        {
                            "type": "button",
                            "className": "button secondary hidden",
                            "id": "test-database",
                        },
                        "Testar conexão",
                    ),
                    h(
                        "button",
                        {"className": "button primary", "type": "submit"},
                        "Salvar",
                    ),
                ),
            ),
        ),
    )


def render_databases_page(
    connections: list[dict],
    database_types: list[dict],
    user: dict[str, object],
    workspace: dict[str, str],
    workspaces: list[dict] | None = None,
) -> str:
    body = _render_ui(
        h(
            DatabasesPage,
            {
                "connections": connections,
                "database_types": database_types,
                "user": user,
                "workspace": workspace,
                "workspaces": workspaces or [workspace],
            },
        )
    )
    return _document(
        body,
        "Bancos de dados · Agentic Flow",
        ["/static/workspace.js", "/static/databases.js"],
    )


def AccessPage(props):
    user = props["user"]
    workspace = props["workspace"]
    workspaces = props.get("workspaces", [workspace])
    is_admin = user.get("role") == "admin"
    return h(
        "div",
        {
            "className": "dashboard-shell access-shell",
            "data-current-role": user.get("role", "user"),
        },
        h(
            "header",
            {"className": "dashboard-topbar"},
            h(Brand, None),
            h(WorkspaceSwitcher, {"workspace": workspace, "workspaces": workspaces}),
            h(
                "div",
                {"className": "user-menu"},
                h(
                    "a",
                    {"className": "button secondary", "href": "/dashboard"},
                    Icon("arrow-left", 16),
                    "Workflows",
                ),
                h("span", {"className": "user-avatar"}, user["name"][:1].upper()),
                h("div", None, h("strong", None, user["name"]), h("small", None, user["role"])),
            ),
        ),
        h(
            "main",
            {"className": "dashboard-main access-main"},
            h(
                "section",
                {"className": "dashboard-heading"},
                h(
                    "div",
                    None,
                    h("span", {"className": "auth-kicker"}, "ACESSO E GOVERNANÇA"),
                    h("h1", None, "Usuários, times e políticas"),
                    h(
                        "p",
                        None,
                        "Controle quem acessa cada workspace e o que cada time pode fazer.",
                    ),
                ),
                h(
                    "a",
                    {"className": "button secondary", "href": "/settings/providers"},
                    "Provedores de IA",
                    Icon("arrow-right", 16),
                ),
            ),
            h(
                "section",
                {"className": "governance-banner"},
                h("span", {"className": "governance-icon"}, Icon("shield-check", 22)),
                h(
                    "div",
                    None,
                    h("strong", None, f"Governança de {workspace['name']}"),
                    h(
                        "p",
                        None,
                        "Papéis definem o nível global. Times refinam permissões e o catálogo de nós dentro deste workspace.",
                    ),
                ),
                h(
                    "span",
                    {"className": f"role-badge {user.get('role', 'user')}"},
                    str(user.get("role", "user")).upper(),
                ),
            ),
            h(
                "section",
                {"className": "access-stats", "id": "access-stats"},
                h("article", None, h("strong", None, "—"), h("span", None, "Usuários")),
                h("article", None, h("strong", None, "—"), h("span", None, "Times")),
                h("article", None, h("strong", None, "—"), h("span", None, "Workspaces")),
            ),
            h(
                "nav",
                {"className": "access-tabs", "aria-label": "Seções de governança"},
                h(
                    "button",
                    {
                        "type": "button",
                        "className": "access-tab active",
                        "data-access-tab": "people",
                    },
                    h("span", None, Icon("users-round", 17)),
                    "Pessoas",
                ),
                h(
                    "button",
                    {
                        "type": "button",
                        "className": "access-tab",
                        "data-access-tab": "teams",
                    },
                    h("span", None, Icon("users", 17)),
                    "Times e políticas",
                ),
                *(
                    [
                        h(
                            "button",
                            {
                                "type": "button",
                                "className": "access-tab",
                                "data-access-tab": "workspaces",
                            },
                            h("span", None, Icon("panels-top-left", 17)),
                            "Workspaces",
                        )
                    ]
                    if is_admin
                    else []
                ),
            ),
            h(
                "section",
                {
                    "className": "access-panel active",
                    "data-access-panel": "people",
                },
                h(
                    "div",
                    {"className": "access-section-head"},
                    h(
                        "div",
                        None,
                        h("h2", None, "Pessoas neste workspace"),
                        h("p", None, "Papéis globais e vínculos aprovados pelo administrador."),
                    ),
                    *(
                        [
                            h(
                                "button",
                                {"className": "button primary", "id": "new-user-button"},
                                Icon("plus", 17),
                                "Novo usuário",
                            )
                        ]
                        if is_admin
                        else []
                    ),
                ),
                h("div", {"className": "access-table", "id": "access-users"}),
            ),
            h(
                "section",
                {"className": "access-panel", "data-access-panel": "teams"},
                h(
                    "div",
                    {"className": "access-section-head"},
                    h(
                        "div",
                        None,
                        h("h2", None, "Times e políticas"),
                        h("p", None, "Permissões são combinadas entre os times do usuário."),
                    ),
                    h(
                        "button",
                        {"className": "button primary", "id": "new-team-button"},
                        Icon("plus", 17),
                        "Novo time",
                    ),
                ),
                h("div", {"className": "team-grid", "id": "team-grid"}),
            ),
            *(
                [
                    h(
                        "section",
                        {
                            "className": "access-panel",
                            "data-access-panel": "workspaces",
                        },
                        h(
                            "div",
                            {"className": "access-section-head"},
                            h(
                                "div",
                                None,
                                h("h2", None, "Workspaces da organização"),
                                h("p", None, "Crie ambientes e libere pessoas para cada operação."),
                            ),
                            h(
                                "button",
                                {"className": "button primary", "id": "new-workspace-button"},
                                Icon("plus", 17),
                                "Novo workspace",
                            ),
                        ),
                        h("div", {"className": "access-grid", "id": "workspace-admin-grid"}),
                    )
                ]
                if is_admin
                else []
            ),
        ),
        h(
            "div",
            {"className": "modal-backdrop hidden", "id": "access-modal"},
            h(
                "form",
                {"className": "workflow-modal access-modal", "id": "access-form"},
                h(
                    "button",
                    {
                        "type": "button",
                        "className": "modal-close",
                        "id": "access-modal-close",
                        "aria-label": "Fechar",
                    },
                    Icon("x", 18),
                ),
                h("span", {"className": "auth-kicker", "id": "access-modal-kicker"}, "ACESSO"),
                h("h2", {"id": "access-modal-title"}, "Configurar"),
                h("div", {"id": "access-modal-body"}),
                h("div", {"className": "auth-error hidden", "id": "access-error"}),
                h("button", {"className": "button primary auth-submit", "type": "submit"}, "Salvar"),
            ),
        ),
        h("div", {"className": "toast-region", "id": "toast-region"}),
    )


def render_access_page(
    user: dict[str, object],
    workspace: dict[str, str],
    workspaces: list[dict],
) -> str:
    body = _render_ui(
        h(
            AccessPage,
            {
                "user": user,
                "workspace": workspace,
                "workspaces": workspaces,
            },
        )
    )
    return _document(
        body,
        "Acesso e políticas · Agentic Flow",
        ["/static/workspace.js", "/static/access.js"],
    )
