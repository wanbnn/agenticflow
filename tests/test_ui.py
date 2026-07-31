from pathlib import Path

from agentic_flow.ui import render_auth_page, render_page


STYLESHEET = (
    Path(__file__).resolve().parents[1]
    / "agentic_flow"
    / "static"
    / "styles.css"
)
APP_SCRIPT = STYLESHEET.with_name("app.js")


def test_editor_uses_uikitpr_provider_and_6cons_icons() -> None:
    html = render_page("workflow-test")

    assert 'class="uipr-root min-h-screen agenticflow-ui"' in html
    assert 'data-uipr-theme="dark"' in html
    assert 'data-uikitpr="core"' in html
    assert "uipr-button" in html
    assert "lucide-sparkles" in html
    assert "lucide-play" in html
    assert "lucide-wand-sparkles" in html
    assert 'data-workflow-id="workflow-test"' in html


def test_auth_page_uses_shared_design_system() -> None:
    html = render_auth_page("login")

    assert 'data-uipr-color-mode="dark"' in html
    assert "lucide-arrow-right" in html
    assert "/static/styles.css?v=" in html


def test_dashboard_contrast_uses_tokens_inside_provider_scope() -> None:
    css = STYLESHEET.read_text(encoding="utf-8")

    provider_block = css.split(".agenticflow-ui {", 1)[1].split("}", 1)[0]
    assert "--text: var(--uipr-text);" in provider_block
    assert "--muted: var(--uipr-muted);" in provider_block
    assert ".workflow-card-link," in css
    assert "color: var(--uipr-text);" in css


def test_dashboard_pages_own_their_vertical_scroll_area() -> None:
    css = STYLESHEET.read_text(encoding="utf-8")

    dashboard_block = css.split(".dashboard-shell {", 1)[1].split("}", 1)[0]
    assert "height: 100%;" in dashboard_block
    assert "min-height: 0;" in dashboard_block
    assert "overflow-y: auto;" in dashboard_block


def test_canvas_media_renderer_recognizes_generated_image_collections() -> None:
    script = APP_SCRIPT.read_text(encoding="utf-8")

    assert "Array.isArray(value?.images)" in script
    assert 'node.type === "image_preview"' in script
    assert "node-type-image_preview" in STYLESHEET.read_text(encoding="utf-8")


def test_media_input_nodes_render_inline_file_uploads() -> None:
    script = APP_SCRIPT.read_text(encoding="utf-8")
    css = STYLESHEET.read_text(encoding="utf-8")

    assert "function inlineMediaUpload(node)" in script
    assert 'data-node-card-file="${escapeHtml(node.id)}"' in script
    assert "data-node-upload" in script
    assert "attachTypedFile(element.dataset.nodeId" in script
    assert ".node-inline-upload" in css


def test_inspector_explains_automatic_connection_wiring() -> None:
    script = APP_SCRIPT.read_text(encoding="utf-8")
    css = STYLESHEET.read_text(encoding="utf-8")

    assert "Conexão automática ativa" in script
    assert "sem depender do nome das variáveis" in script
    assert "(opcional)" in script
    assert ".automatic-wiring-note" in css


def test_local_model_ui_exposes_image_input_capabilities() -> None:
    editor = APP_SCRIPT.read_text(encoding="utf-8")
    providers = APP_SCRIPT.with_name("providers.js").read_text(encoding="utf-8")
    css = STYLESHEET.read_text(encoding="utf-8")

    assert "aceita imagem" in editor
    assert "incompatível com imagem" in editor
    assert "modelos incompatíveis foram desabilitados" in editor
    assert "LLMs multimodais" in providers
    assert "Aceita imagem" in providers
    assert "capabilityBadges(model)" in providers
    assert ".model-capability-badges" in css


def test_typed_text_input_does_not_submit_demo_json_as_prompt() -> None:
    script = APP_SCRIPT.read_text(encoding="utf-8")
    html = render_page("workflow-test")

    assert "Crie um resumo sobre agentes autônomos" not in html
    assert 'id="run-input"' in html
    assert "function textInputValue(node)" in script
    assert "advancedInput.hidden = inputs.length > 0 && !hasJsonInput" in script
    assert "let input = {};" in script
    assert "if (readsJsonInput)" in script


def test_template_library_has_responsive_grid_and_compact_filters() -> None:
    css = STYLESHEET.read_text(encoding="utf-8")

    assert "grid-template-rows: auto auto minmax(0, 1fr);" in css
    assert ".template-category-control" in css
    assert ".template-card-description" in css
    assert ".template-setup summary" in css
    assert "grid-auto-rows: max-content;" in css
    assert "height: max-content;" in css
    assert ".template-card > *" in css
    assert "flex-shrink: 0;" in css
    assert ".template-setup[open]" in css
    assert ".template-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }" in css
