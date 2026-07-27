from pathlib import Path

from agentic_flow.ui import render_auth_page, render_page


STYLESHEET = (
    Path(__file__).resolve().parents[1]
    / "agentic_flow"
    / "static"
    / "styles.css"
)


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
